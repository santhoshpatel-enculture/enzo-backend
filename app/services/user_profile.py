"""Map MongoDB user documents to API UserProfile models."""

from app.models.user import UserProfile
from app.services.admin_rbac import get_admin_role, get_admin_tenant_ids, is_admin_user


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def get_employee_user_id(doc: dict) -> str | None:
    """Business user id used for org hierarchy edges."""
    basic = _as_dict(doc.get("basicDetails"))
    uid = basic.get("userId") or basic.get("userIdNormalized")
    if uid:
        return str(uid).strip()
    return None


def get_manager_display_name(doc: dict) -> str:
    manager = doc.get("managerName")
    if manager:
        return str(manager).strip()

    m_details = _as_dict(doc.get("managerDetails"))
    name = m_details.get("name")
    if name:
        return str(name).strip()

    first = m_details.get("managerFirstName", "")
    last = m_details.get("managerLastName", "")
    combined = f"{first} {last}".strip()
    return combined or "Not Specified"


def user_doc_to_profile(doc: dict) -> UserProfile:
    """Convert a MongoDB user document to a UserProfile response."""
    basic = _as_dict(doc.get("basicDetails"))
    demographics = _as_dict(doc.get("demographicDetails"))
    m_details = _as_dict(doc.get("managerDetails"))

    first_name = basic.get("firstName", "")
    last_name = basic.get("lastName", "")
    dept = demographics.get("department", "Not Specified")
    desg = demographics.get("designation", "Not Specified")
    loc = demographics.get("location", "Not Specified")

    manager_email = m_details.get("managerEmailId") or m_details.get("email")
    manager_id = m_details.get("managerId")
    if manager_id is not None:
        manager_id = str(manager_id).strip() or None

    role = doc.get("enzoRole") or "Employee"
    if isinstance(role, list):
        role = "Employee"

    return UserProfile(
        id=str(doc["_id"]),
        email=doc.get("email", ""),
        firstName=first_name,
        lastName=last_name,
        department=dept,
        designation=desg,
        manager=get_manager_display_name(doc),
        location=loc,
        isAdmin=is_admin_user(doc),
        role=str(role),
        userId=get_employee_user_id(doc),
        managerId=manager_id,
        managerEmail=str(manager_email).strip() if manager_email else None,
        mustChangePassword=bool(doc.get("mustChangePassword", False)),
        adminRole=get_admin_role(doc),
        adminTenantIds=get_admin_tenant_ids(doc),
        tenantId=doc.get("tenantId"),
        createdAt=doc.get("createdAt"),
    )
