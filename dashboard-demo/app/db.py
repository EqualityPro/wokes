"""
Database layer (SQLite).

This module shows the core of MULTI-TENANCY:
- Every row of user-owned data carries a `user_id`.
- Every query is ALWAYS filtered by `user_id`, so one user can never
  read or write another user's data.

We use the standard library `sqlite3` (no external DB needed) so you can
run this demo anywhere. The same patterns map 1:1 to PostgreSQL later.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "data.sqlite"

# Neutral example feature flags. In a real app these are whatever toggles
# your product exposes. Every new user gets this set seeded (all OFF).
DEFAULT_FEATURES = [
    "email_notifications",
    "weekly_summary",
    "dark_mode",
    "auto_backup",
    "beta_features",
]

# Neutral example settings keys with their default values.
DEFAULT_SETTINGS = {
    "display_name": "",
    "timezone": "UTC",
    "items_per_page": "25",
}


@contextmanager
def get_conn():
    """Open a connection with row access by column name, and always close it."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce foreign keys so deleting a user cleans up their data.
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist yet."""
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS feature_flags (
                user_id      INTEGER NOT NULL,
                feature_name TEXT NOT NULL,
                enabled      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, feature_name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER NOT NULL,
                key     TEXT NOT NULL,
                value   TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (user_id, key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )


# ----------------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------------
def create_user(email: str, password_hash: str) -> int:
    """Insert a new user and seed their default features + settings."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password_hash),
        )
        user_id = cur.lastrowid

        # Seed per-user feature flags (all OFF by default).
        conn.executemany(
            "INSERT INTO feature_flags (user_id, feature_name, enabled) VALUES (?, ?, 0)",
            [(user_id, name) for name in DEFAULT_FEATURES],
        )
        # Seed per-user settings with defaults.
        conn.executemany(
            "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
            [(user_id, k, v) for k, v in DEFAULT_SETTINGS.items()],
        )
        return user_id


def get_user_by_email(email: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        return row


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row


# ----------------------------------------------------------------------------
# Feature flags  (ALWAYS scoped by user_id -> tenant isolation)
# ----------------------------------------------------------------------------
def get_features(user_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT feature_name, enabled FROM feature_flags WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r["feature_name"]: bool(r["enabled"]) for r in rows}


def set_feature(user_id: int, feature_name: str, enabled: bool):
    # Note the WHERE user_id = ? : a user can only flip THEIR OWN flags.
    with get_conn() as conn:
        conn.execute(
            "UPDATE feature_flags SET enabled = ? WHERE user_id = ? AND feature_name = ?",
            (1 if enabled else 0, user_id, feature_name),
        )


# ----------------------------------------------------------------------------
# Settings  (ALWAYS scoped by user_id -> tenant isolation)
# ----------------------------------------------------------------------------
def get_settings(user_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}


def set_setting(user_id: int, key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE user_settings SET value = ? WHERE user_id = ? AND key = ?",
            (value, user_id, key),
        )
