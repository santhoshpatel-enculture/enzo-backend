"""Admin FastAPI dependencies with RBAC."""

from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.deps import get_current_user
from app.services.admin_rbac import (
    has_permission,
    is_admin_user,
    resolve_admin_tenant_id,
    tenant_filter_for_user,
)


async def require_admin_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_permission(permission: str) -> Callable:
    async def _checker(
        request: Request,
        admin: dict = Depends(require_admin_user),
    ) -> dict:
        if not has_permission(admin, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        request.state.admin_user = admin
        request.state.admin_tenant_id = resolve_admin_tenant_id(request, admin)
        request.state.admin_tenant_filter = tenant_filter_for_user(admin, request)
        return admin

    return _checker


async def get_admin_context(
    request: Request,
    admin: dict = Depends(require_admin_user),
) -> tuple[dict, str, dict | None]:
    tid = resolve_admin_tenant_id(request, admin)
    tfilter = tenant_filter_for_user(admin, request)
    return admin, tid, tfilter
