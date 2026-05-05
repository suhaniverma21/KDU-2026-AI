from __future__ import annotations

import time
from typing import Any

import jwt
from fastapi import Cookie, HTTPException, status

from .config import settings
from .models import AuthContext


def mint_internal_jwt(user_id: str, thread_id: str) -> str:
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "thread_id": thread_id,
        "issued_at": now,
        "expires_at": now + settings.jwt_ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_private_key, algorithm=settings.jwt_algorithm)


def decode_internal_jwt(token: str) -> AuthContext:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session.") from exc

    expires_at = int(payload["expires_at"])
    now = int(time.time())
    if expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")

    return AuthContext(
        user_id=str(payload["user_id"]),
        thread_id=str(payload["thread_id"]),
        issued_at=int(payload["issued_at"]),
        expires_at=expires_at,
    )


def get_cookie_token(cookie_token: str | None = Cookie(default=None, alias=settings.jwt_cookie_name)) -> str:
    if not cookie_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session.")
    return cookie_token


def get_auth_context(cookie_token: str | None = Cookie(default=None, alias=settings.jwt_cookie_name)) -> AuthContext:
    if not cookie_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session.")
    return decode_internal_jwt(cookie_token)


def should_refresh(expires_at: int) -> bool:
    return expires_at - int(time.time()) <= settings.refresh_window_seconds
