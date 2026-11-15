"""Учётные записи: хэширование паролей (scrypt), сессии в HttpOnly-cookie, защита от CSRF.

* Пароль хранится как scrypt (N=2^14, r=8, p=1) с солью 16 байт — только стандартная библиотека.
* Сессия — случайный токен 32 байта в cookie ``agro_session`` (HttpOnly, SameSite=Lax);
  в базе хранится только SHA-256 токена.
* Изменяющие запросы требуют заголовок ``X-Requested-With: agro``: браузер не отправит его
  с чужого сайта без CORS-разрешения, а CORS открыт только для своих адресов.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response

from . import db
from .config import get_settings

COOKIE = "agro_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "agro"
SCRYPT = {"n": 2**14, "r": 8, "p": 1}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
MIN_PASSWORD = 8

_failed: dict[str, list[float]] = {}
MAX_FAILS, FAIL_WINDOW_S = 10, 900


# ---------------------------------------------------------------- пароли
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **SCRYPT)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64), dklen=32, n=int(n), r=int(r), p=int(p)
        )
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


def validate_credentials(email: str, password: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, detail="invalid_email")
    if len(password) < MIN_PASSWORD or len(password) > 256:
        raise HTTPException(422, detail="weak_password")
    return email


# ---------------------------------------------------------------- ограничение попыток входа
def check_rate(email: str) -> None:
    now = time.monotonic()
    attempts = [t for t in _failed.get(email, []) if now - t < FAIL_WINDOW_S]
    _failed[email] = attempts
    if len(attempts) >= MAX_FAILS:
        raise HTTPException(429, detail="too_many_attempts")


def record_failure(email: str) -> None:
    _failed.setdefault(email, []).append(time.monotonic())


def clear_failures(email: str) -> None:
    _failed.pop(email, None)


# ---------------------------------------------------------------- сессии
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(response: Response, user_id: int) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=settings.session_days)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (_hash_token(token), user_id, db.now_iso(), expires.isoformat(timespec="seconds")),
        )
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def destroy_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
    response.delete_cookie(COOKIE, path="/")


def public_user(row: dict) -> dict:
    return {k: row[k] for k in ("id", "email", "name", "farm_name", "lang", "is_demo", "created_at")} | {
        "is_demo": bool(row["is_demo"])
    }


def optional_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db.connect() as conn:
        row = conn.execute(
            "SELECT u.* , s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (_hash_token(token),),
        ).fetchone()
    if row is None or row["expires_at"] < datetime.now(UTC).isoformat(timespec="seconds"):
        return None
    return dict(row)


def current_user(request: Request) -> dict:
    user = optional_user(request)
    if user is None:
        raise HTTPException(401, detail="not_authenticated")
    return user


def require_csrf(request: Request) -> None:
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(403, detail="csrf_header_missing")


def authed(user: dict = Depends(current_user), _: None = Depends(require_csrf)) -> dict:
    """Пользователь для изменяющих запросов: сессия + CSRF-заголовок."""
    return user
