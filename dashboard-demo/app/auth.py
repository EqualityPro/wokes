"""
Authentication helpers.

Two ideas demonstrated here:

1. PASSWORD HASHING
   We never store the raw password. We store a one-way hash.
   Here we use PBKDF2-HMAC-SHA256 from the Python standard library
   (`hashlib`), which is a solid, dependency-free choice. In production
   you'd commonly use bcrypt or argon2 instead - the principle is identical:
   hash on register, re-hash the typed password on login and compare.

2. SESSION
   After a successful login we just store the user's id in a signed
   session cookie (handled by Starlette's SessionMiddleware). The cookie is
   tamper-proof because it's cryptographically signed with SECRET_KEY.
"""

import hashlib
import hmac
import os

_PBKDF2_ROUNDS = 200_000
_ALGO = "sha256"


def hash_password(password: str) -> str:
    """Return a string of the form  algo$rounds$salt_hex$hash_hex."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_{_ALGO}${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Re-hash the supplied password with the stored salt and compare safely."""
    try:
        algo_part, rounds_str, salt_hex, hash_hex = stored.split("$")
        algo = algo_part.replace("pbkdf2_", "")
        rounds = int(rounds_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False

    dk = hashlib.pbkdf2_hmac(algo, password.encode("utf-8"), salt, rounds)
    # constant-time comparison to avoid timing attacks
    return hmac.compare_digest(dk, expected)
