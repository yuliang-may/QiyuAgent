"""Lightweight local auth helpers for the web product shell."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time


PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iteration_text, salt, digest = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iteration_text),
        ).hex()
        return hmac.compare_digest(expected, digest)
    except Exception:
        return False


def create_session_token(user_id: str, secret_key: str) -> str:
    issued_at = str(int(time.time()))
    payload = f"{user_id}.{issued_at}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token = f"{payload}.{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def read_session_token(
    token: str,
    secret_key: str,
    *,
    max_age_sec: int,
) -> str | None:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        user_id, issued_at_text, signature = decoded.rsplit(".", 2)
        payload = f"{user_id}.{issued_at_text}"
        expected = hmac.new(
            secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        issued_at = int(issued_at_text)
        if (int(time.time()) - issued_at) > max_age_sec:
            return None
        return user_id
    except Exception:
        return None
