"""
Flask app: a generic multi-tenant dashboard.

Why Flask (not FastAPI) here?
- Flask and all its dependencies are PURE PYTHON. No Rust, no C compiler.
  That means it installs instantly even on Termux/Android or locked hosts,
  unlike FastAPI which needs to compile pydantic-core (Rust).

The interesting logic lives in db.py (tenant isolation) and auth.py (password
hashing). This file is just the thin HTTP layer wiring them to web routes.

Routes
------
GET  /                    -> redirect to /dashboard (or /login if not logged in)
GET/POST /register        -> create account, log in
GET/POST /login           -> verify credentials, start session
GET  /logout              -> clear session
GET  /dashboard           -> show THIS user's feature toggles + settings
POST /dashboard/features  -> flip this user's feature flags
POST /dashboard/settings  -> save this user's settings

After login we read the user id from the signed session cookie and use it to
scope every database call, so a user only ever sees their own data.
"""

import os
from pathlib import Path

from flask import Flask, request, render_template, redirect, session

from . import db, auth

BASE_DIR = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static",
)

# secret_key signs the session cookie so it can't be tampered with.
# In production load this from an env var / secrets manager, never hardcode.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me-in-production")

# Create tables on startup.
db.init_db()


def current_user():
    """Return the logged-in user row, or None if not authenticated."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.get_user_by_id(user_id)


# ----------------------------------------------------------------------------
# Public routes
# ----------------------------------------------------------------------------
@app.route("/")
def index():
    if session.get("user_id"):
        return redirect("/dashboard")
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", error=None)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if len(password) < 8:
        return render_template(
            "register.html", error="Password must be at least 8 characters."
        ), 400
    if db.get_user_by_email(email):
        return render_template(
            "register.html", error="That email is already registered."
        ), 400

    user_id = db.create_user(email, auth.hash_password(password))
    session["user_id"] = user_id  # log them in immediately
    return redirect("/dashboard")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    user = db.get_user_by_email(email)

    # Same generic error whether the email is unknown or the password is wrong,
    # so attackers can't tell which emails exist.
    if user is None or not auth.verify_password(password, user["password_hash"]):
        return render_template(
            "login.html", error="Invalid email or password."
        ), 401

    session["user_id"] = user["id"]
    return redirect("/dashboard")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ----------------------------------------------------------------------------
# Protected routes (require a logged-in user)
# ----------------------------------------------------------------------------
@app.route("/dashboard")
def dashboard():
    user = current_user()
    if user is None:
        return redirect("/login")

    return render_template(
        "dashboard.html",
        email=user["email"],
        # Scoped by user["id"] -> only THIS user's data.
        features=db.get_features(user["id"]),
        settings=db.get_settings(user["id"]),
        saved=request.args.get("saved"),
    )


@app.route("/dashboard/features", methods=["POST"])
def update_features():
    user = current_user()
    if user is None:
        return redirect("/login")

    # Checkboxes only submit when checked. For each known feature, set
    # enabled = (feature present in the submitted form).
    current = db.get_features(user["id"])
    for feature_name in current:
        db.set_feature(user["id"], feature_name, feature_name in request.form)
    return redirect("/dashboard?saved=features")


@app.route("/dashboard/settings", methods=["POST"])
def update_settings():
    user = current_user()
    if user is None:
        return redirect("/login")

    display_name = (request.form.get("display_name") or "").strip()
    timezone = (request.form.get("timezone") or "UTC").strip()

    ipp = (request.form.get("items_per_page") or "25").strip()
    if not ipp.isdigit() or not (1 <= int(ipp) <= 200):
        ipp = "25"

    db.set_setting(user["id"], "display_name", display_name)
    db.set_setting(user["id"], "timezone", timezone)
    db.set_setting(user["id"], "items_per_page", ipp)
    return redirect("/dashboard?saved=settings")
