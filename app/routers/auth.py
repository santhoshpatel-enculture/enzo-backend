"""Authentication routes — login, refresh, logout, SSO, change password."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.config import settings
from app.deps import get_current_user
from app.database import get_db
from app.security import verify_password, hash_password
from app.models.user import (
    UserLogin,
    UserProfile,
    AuthResponse,
    ChangePasswordRequest,
)
from app.services.auth_tokens import (
    access_token_for_user,
    clear_refresh_cookie,
    issue_refresh_token,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
    set_refresh_cookie,
)
from app.services.user_profile import user_doc_to_profile

logger = logging.getLogger("enzo.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])

DEFAULT_BOOTSTRAP_PASSWORD = "Test@1234"


def _auth_response(user: dict, access_token: str, expires_in: int) -> AuthResponse:
    return AuthResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=user_doc_to_profile(user),
    )


async def _authenticate_password_user(email: str, password: str) -> dict:
    db = get_db()
    user = await db.users.find_one({"email": email.lower()})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if user.get("isDeleted"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )
    if not verify_password(password, user.get("password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return user


@router.post("/login", response_model=AuthResponse)
async def login(body: UserLogin, request: Request, response: Response):
    """Authenticate with email and password; sets refresh cookie."""
    user = await _authenticate_password_user(body.email, body.password)
    logger.info("User authenticated: user_id=%s", str(user["_id"]))

    access, expires_in = access_token_for_user(user["_id"])
    raw_refresh = await issue_refresh_token(
        user["_id"],
        user_agent=request.headers.get("User-Agent"),
        ip=request.client.host if request.client else None,
    )
    set_refresh_cookie(response, raw_refresh)
    return _auth_response(user, access, expires_in)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_session(request: Request, response: Response):
    """Rotate refresh token and issue new access token."""
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )
    rotated = await rotate_refresh_token(
        raw,
        user_agent=request.headers.get("User-Agent"),
        ip=request.client.host if request.client else None,
    )
    if not rotated:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user_id, new_raw = rotated
    db = get_db()
    user = await db.users.find_one({"_id": user_id})
    if not user or user.get("isDeleted"):
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    set_refresh_cookie(response, new_raw)
    access, expires_in = access_token_for_user(user_id)
    return _auth_response(user, access, expires_in)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    if body.currentPassword == body.newPassword:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )
    if not verify_password(body.currentPassword, current_user.get("password", "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if (
        current_user.get("mustChangePassword")
        and body.newPassword == DEFAULT_BOOTSTRAP_PASSWORD
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose a password other than the default temporary password",
        )

    db = get_db()
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "password": hash_password(body.newPassword),
                "mustChangePassword": False,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    await revoke_all_refresh_tokens(current_user["_id"])
    raw_refresh = await issue_refresh_token(current_user["_id"])
    set_refresh_cookie(response, raw_refresh)
    return {"message": "Password updated successfully"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    raw = request.cookies.get(settings.refresh_cookie_name)
    if raw:
        await revoke_refresh_token(raw)
    clear_refresh_cookie(response)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: dict = Depends(get_current_user)):
    return user_doc_to_profile(current_user)
