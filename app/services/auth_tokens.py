"""Access and refresh token lifecycle."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import Response

from app.config import settings
from app.database import get_db
from app.security import create_access_token


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def access_token_for_user(user_id: ObjectId) -> tuple[str, int]:
    expires_min = settings.jwt_access_expiration_minutes
    token = create_access_token(
        data={"sub": str(user_id), "type": "access"},
        expires_delta=timedelta(minutes=expires_min),
    )
    return token, expires_min * 60


async def issue_refresh_token(
    user_id: ObjectId,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    raw = secrets.token_urlsafe(48)
    db = get_db()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.jwt_refresh_expiration_days)
    await db.refresh_tokens.insert_one(
        {
            "userId": user_id,
            "tokenHash": _hash_token(raw),
            "expiresAt": expires,
            "revokedAt": None,
            "createdAt": now,
            "userAgent": user_agent,
            "ip": ip,
        }
    )
    return raw


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_token,
        httponly=True,
        secure=settings.refresh_cookie_secure or settings.app_env in ("production", "prod"),
        samesite="lax",
        max_age=settings.jwt_refresh_expiration_days * 86400,
        path="/api/auth",
        domain=settings.refresh_cookie_domain or None,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/api/auth",
        domain=settings.refresh_cookie_domain or None,
    )


async def rotate_refresh_token(
    raw_token: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[ObjectId, str] | None:
    db = get_db()
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    doc = await db.refresh_tokens.find_one(
        {"tokenHash": token_hash, "revokedAt": None, "expiresAt": {"$gt": now}}
    )
    if not doc:
        return None

    await db.refresh_tokens.update_one(
        {"_id": doc["_id"]},
        {"$set": {"revokedAt": now}},
    )
    user_id = doc["userId"]
    new_raw = await issue_refresh_token(user_id, user_agent=user_agent, ip=ip)
    return user_id, new_raw


async def revoke_refresh_token(raw_token: str) -> None:
    db = get_db()
    await db.refresh_tokens.update_one(
        {"tokenHash": _hash_token(raw_token)},
        {"$set": {"revokedAt": datetime.now(timezone.utc)}},
    )


async def revoke_all_refresh_tokens(user_id: ObjectId) -> None:
    db = get_db()
    await db.refresh_tokens.update_many(
        {"userId": user_id, "revokedAt": None},
        {"$set": {"revokedAt": datetime.now(timezone.utc)}},
    )
