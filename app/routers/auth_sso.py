"""Microsoft Entra ID SSO (OIDC)."""

import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.config import settings
from app.database import get_db
from app.services.auth_tokens import (
    access_token_for_user,
    issue_refresh_token,
    set_refresh_cookie,
)

logger = logging.getLogger("enzo.auth_sso")
router = APIRouter(prefix="/auth/sso", tags=["Authentication"])


def _microsoft_enabled() -> bool:
    return bool(
        settings.oidc_microsoft_client_id
        and settings.oidc_microsoft_client_secret
        and settings.oidc_microsoft_redirect_uri
    )


def _authority() -> str:
    tenant = settings.oidc_microsoft_tenant_id or "common"
    return f"https://login.microsoftonline.com/{tenant}/v2.0"


@router.get("/microsoft/enabled")
async def microsoft_sso_enabled():
    return {"enabled": _microsoft_enabled()}


@router.get("/microsoft/start")
async def microsoft_start(request: Request):
    if not _microsoft_enabled():
        raise HTTPException(status_code=503, detail="Microsoft SSO is not configured")
    app_target = request.query_params.get("app", "frontend")
    state = app_target if app_target in ("frontend", "admin") else "frontend"
    params = {
        "client_id": settings.oidc_microsoft_client_id,
        "response_type": "code",
        "redirect_uri": settings.oidc_microsoft_redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": state,
    }
    url = f"{_authority()}/authorize?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        target = settings.admin_frontend_url if state == "admin" else settings.frontend_url
        return RedirectResponse(f"{target}/login?error=sso_failed")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code missing")
    if not _microsoft_enabled():
        raise HTTPException(status_code=503, detail="Microsoft SSO is not configured")

    token_url = f"{_authority()}/token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(
            token_url,
            data={
                "client_id": settings.oidc_microsoft_client_id,
                "client_secret": settings.oidc_microsoft_client_secret,
                "code": code,
                "redirect_uri": settings.oidc_microsoft_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code >= 400:
            logger.error("Microsoft token error: %s", token_resp.text[:300])
            target = settings.admin_frontend_url if state == "admin" else settings.frontend_url
            return RedirectResponse(f"{target}/login?error=sso_token")
        tokens = token_resp.json()
        id_token = tokens.get("id_token")
        access = tokens.get("access_token")

        email = None
        sub = None
        if id_token:
            from jose import jwt as jose_jwt

            claims = jose_jwt.get_unverified_claims(id_token)
            email = (claims.get("email") or claims.get("preferred_username") or "").lower()
            sub = claims.get("sub")
        if not email and access:
            me_resp = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access}"},
            )
            if me_resp.status_code < 400:
                me = me_resp.json()
                email = (me.get("mail") or me.get("userPrincipalName") or "").lower()
                sub = me.get("id")

    if not email:
        target = settings.admin_frontend_url if state == "admin" else settings.frontend_url
        return RedirectResponse(f"{target}/login?error=sso_no_email")

    db = get_db()
    user = await db.users.find_one({"email": email})
    if not user:
        target = settings.admin_frontend_url if state == "admin" else settings.frontend_url
        return RedirectResponse(f"{target}/login?error=sso_user_not_found")
    if user.get("isDeleted"):
        target = settings.admin_frontend_url if state == "admin" else settings.frontend_url
        return RedirectResponse(f"{target}/login?error=sso_deactivated")

    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "ssoProvider": "microsoft",
                "ssoSubject": sub,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )

    raw_refresh = await issue_refresh_token(user["_id"])
    set_refresh_cookie(response, raw_refresh)

    base = settings.admin_frontend_url if state == "admin" else settings.frontend_url
    return RedirectResponse(f"{base}/auth/callback?sso=1")
