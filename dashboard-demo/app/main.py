"""
FastAPI app: a generic multi-tenant dashboard.

Routes
------
GET  /                 -> redirect to /dashboard (or /login if not logged in)
GET  /register         -> registration form
POST /register         -> create account, log in, redirect to dashboard
GET  /login            -> login form
POST /login            -> verify credentials, start session
GET  /logout           -> clear session
GET  /dashboard        -> show THIS user's feature toggles + settings
POST /dashboard/features -> flip a feature flag for THIS user
POST /dashboard/settings -> save settings for THIS user

The whole point: after login we read the user id from the session and use it
to scope every database call. A logged-in user only ever sees their own data.
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import db, auth

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Multi-tenant Dashboard Demo")

# SECRET_KEY signs the session cookie so it can't be tampered with.
# In production load this from an env var / secrets manager, never hardcode.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-only-change-me-in-production"),
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def _startup():
    db.init_db()


# ----------------------------------------------------------------------------
# Auth dependency: "who is the current user?"
# ----------------------------------------------------------------------------
def get_current_user(request: Request):
    """Return the logged-in user row, or None if not authenticated."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get_user_by_id(user_id)


def require_user(request: Request):
    """Use on protected routes. Raises a redirect-to-login if not authenticated."""
    user = get_current_user(request)
    if user is None:
        # 303 makes the browser issue a GET to /login
        raise HTTPException(
            status_code=303, headers={"Location": "/login"}
        )
    return user


# ----------------------------------------------------------------------------
# Public routes
# ----------------------------------------------------------------------------
@app.get("/")
def index(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html", {"request": request, "error": None}
    )


@app.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()
    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Password must be at least 8 characters."},
            status_code=400,
        )
    if db.get_user_by_email(email):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "That email is already registered."},
            status_code=400,
        )

    user_id = db.create_user(email, auth.hash_password(password))
    request.session["user_id"] = user_id  # log them in immediately
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()
    user = db.get_user_by_email(email)
    # Same generic error whether email is unknown or password is wrong,
    # so attackers can't tell which emails exist.
    if user is None or not auth.verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password."},
            status_code=401,
        )

    request.session["user_id"] = user["id"]
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ----------------------------------------------------------------------------
# Protected routes (require a logged-in user)
# ----------------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(require_user)):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "email": user["email"],
            # Scoped by user["id"] -> only THIS user's data.
            "features": db.get_features(user["id"]),
            "settings": db.get_settings(user["id"]),
            "saved": request.query_params.get("saved"),
        },
    )


@app.post("/dashboard/features")
async def update_features(request: Request, user=Depends(require_user)):
    """
    Checkboxes only POST when checked. So: read the submitted form, then for
    every known feature set enabled = (feature present in form).
    """
    form = await request.form()
    current = db.get_features(user["id"])
    for feature_name in current:
        db.set_feature(user["id"], feature_name, feature_name in form)
    return RedirectResponse("/dashboard?saved=features", status_code=303)


@app.post("/dashboard/settings")
def update_settings(
    request: Request,
    user=Depends(require_user),
    display_name: str = Form(""),
    timezone: str = Form("UTC"),
    items_per_page: str = Form("25"),
):
    db.set_setting(user["id"], "display_name", display_name.strip())
    db.set_setting(user["id"], "timezone", timezone.strip())
    # keep it numeric and sane
    ipp = items_per_page.strip()
    if not ipp.isdigit() or not (1 <= int(ipp) <= 200):
        ipp = "25"
    db.set_setting(user["id"], "items_per_page", ipp)
    return RedirectResponse("/dashboard?saved=settings", status_code=303)
