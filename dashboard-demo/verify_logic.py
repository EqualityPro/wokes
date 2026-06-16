"""
Quick verification of the core logic WITHOUT the web server.
Proves: password hashing works, and one user CANNOT affect another's data.
Run:  python3 verify_logic.py
"""
import os
import tempfile
from pathlib import Path

# Use a throwaway DB file so we don't touch the real one.
tmp = Path(tempfile.mkdtemp()) / "verify.sqlite"
import app.db as db
db.DB_PATH = tmp

from app import auth

db.init_db()

# --- password hashing -------------------------------------------------------
h = auth.hash_password("correct horse battery staple")
assert "$" in h and "correct" not in h, "raw password must not be stored"
assert auth.verify_password("correct horse battery staple", h) is True
assert auth.verify_password("wrong password", h) is False
print("[ok] password hashing: stored as hash, verifies correctly, rejects wrong pw")

# --- create two separate tenants -------------------------------------------
alice = db.create_user("alice@example.com", auth.hash_password("alice-pass-123"))
bob = db.create_user("bob@example.com", auth.hash_password("bob-pass-123"))
print(f"[ok] created two users: alice=#{alice}, bob=#{bob}")

# Each starts with the same seeded features, all OFF.
assert db.get_features(alice) == db.get_features(bob)
assert all(v is False for v in db.get_features(alice).values())
print("[ok] both users seeded with default features (all OFF)")

# --- Alice flips a feature and changes a setting ----------------------------
db.set_feature(alice, "dark_mode", True)
db.set_setting(alice, "display_name", "Alice A")

# --- ISOLATION: Bob must be completely unaffected ---------------------------
assert db.get_features(alice)["dark_mode"] is True
assert db.get_features(bob)["dark_mode"] is False, "ISOLATION BROKEN: Bob saw Alice's toggle!"
assert db.get_settings(alice)["display_name"] == "Alice A"
assert db.get_settings(bob)["display_name"] == "", "ISOLATION BROKEN: Bob saw Alice's setting!"
print("[ok] tenant isolation: Alice's changes did NOT leak into Bob's data")

# --- lookups ----------------------------------------------------------------
assert db.get_user_by_email("alice@example.com")["id"] == alice
assert db.get_user_by_email("nobody@example.com") is None
print("[ok] user lookup by email works")

print("\nALL CHECKS PASSED \u2705")
