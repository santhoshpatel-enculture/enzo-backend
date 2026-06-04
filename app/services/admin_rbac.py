"""Admin RBAC — roles, permissions, and tenant scope."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.config import settings

ADMIN_ROLES = frozenset({"super_admin", "tenant_admin", "support", "read_only"})

PERMISSIONS: dict[str, frozenset[str]] = {
    "users:write": frozenset({"super_admin", "tenant_admin"}),
    "users:read": frozenset({"super_admin", "tenant_admin", "support", "read_only"}),
    "config:write": frozenset({"super_admin", "tenant_admin"}),
    "kb:write": frozenset({"super_admin", "tenant_admin"}),
    "audit:read": frozenset({"super_admin", "tenant_admin", "support", "read_only"}),
    "audit:delete": frozenset({"super_admin"}),
    "telemetry:read": frozenset({"super_admin", "tenant_admin", "support", "read_only"}),
    "telemetry:pricing": frozenset({"super_admin"}),
    "budgets:write": frozenset({"super_admin", "tenant_admin"}),
    "feedback:read": frozenset({"super_admin", "tenant_admin", "support", "read_only"}),
}


def get_admin_role(user_doc: dict) -> str | None:
    role = user_doc.get("adminRole")
    if role and role in ADMIN_ROLES:
        return role
    email = (user_doc.get("email") or "").strip().lower()
    if email in settings.admin_email_list:
        return "super_admin"
    return None


def get_admin_tenant_ids(user_doc: dict) -> list[str]:
    ids = user_doc.get("adminTenantIds") or []
    if isinstance(ids, list):
        return [str(t).strip() for t in ids if t]
    return []


def is_admin_user(user_doc: dict) -> bool:
    return get_admin_role(user_doc) is not None


def has_permission(user_doc: dict, permission: str) -> bool:
    role = get_admin_role(user_doc)
    if not role:
        return False
    allowed = PERMISSIONS.get(permission)
    if not allowed:
        return False
    return role in allowed


def can_access_tenant(user_doc: dict, tenant_id: str) -> bool:
    role = get_admin_role(user_doc)
    if not role:
        return False
    if role == "super_admin":
        return True
    return tenant_id in get_admin_tenant_ids(user_doc)


def resolve_admin_tenant_id(request: Request, user_doc: dict) -> str:
    """Resolve active admin tenant from header or role defaults."""
    role = get_admin_role(user_doc)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    header_tid = (request.headers.get("X-Admin-Tenant-Id") or "").strip()
    if role == "super_admin":
        if header_tid:
            return header_tid
        return "enculture"

    tenant_ids = get_admin_tenant_ids(user_doc)
    if not tenant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant assigned for admin account",
        )
    if header_tid:
        if header_tid not in tenant_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for this tenant",
            )
        return header_tid
    return tenant_ids[0]


def tenant_filter_for_user(user_doc: dict, request: Request) -> dict | None:
    """Mongo filter fragment for tenantId, or None if super_admin sees all."""
    role = get_admin_role(user_doc)
    if role == "super_admin":
        header_tid = (request.headers.get("X-Admin-Tenant-Id") or "").strip()
        if header_tid:
            return {"tenantId": header_tid}
        return None
    tid = resolve_admin_tenant_id(request, user_doc)
    return {"tenantId": tid}


async def bootstrap_admin_roles(db) -> None:
    """Map ADMIN_EMAILS to super_admin once (idempotent)."""
    for email in settings.admin_email_list:
        await db.users.update_one(
            {"email": email, "adminRole": {"$exists": False}},
            {"$set": {"adminRole": "super_admin", "adminTenantIds": []}},
        )
