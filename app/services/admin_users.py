"""Admin user list helpers — demographics, manager/team resolution."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.config import settings
from app.services.user_profile import _as_dict, get_employee_user_id, get_manager_display_name


def get_user_name_parts(doc: dict) -> tuple[str, str]:
    """Resolve first/last name from basicDetails (primary store in MongoDB)."""
    basic = _as_dict(doc.get("basicDetails"))
    first = str(basic.get("firstName") or doc.get("firstName") or "").strip()
    last = str(basic.get("lastName") or doc.get("lastName") or "").strip()
    return first, last


def has_display_name(doc: dict) -> bool:
    """True when the user has a non-empty first or last name."""
    first, last = get_user_name_parts(doc)
    return bool(first or last)


def is_dummy_user(doc: dict) -> bool:
    """Placeholder rows: missing both first and last name."""
    return not has_display_name(doc)


async def load_active_user_docs(db) -> list[dict]:
    """Load all active (non-deleted) users for admin listing."""
    query = {"isDeleted": {"$ne": True}}
    cursor = db.users.find(query).sort("createdAt", -1)
    cap = settings.admin_users_list_limit
    if cap and cap > 0:
        cursor = cursor.limit(cap)
        return await cursor.to_list(cap)
    return await cursor.to_list(length=None)


def build_users_by_business_id(docs: list[dict]) -> dict[str, dict]:
    users_by_business_id: dict[str, dict] = {}
    for doc in docs:
        bid = get_employee_user_id(doc)
        if bid:
            users_by_business_id[bid] = doc
    return users_by_business_id


def partition_users_for_admin(docs: list[dict]) -> tuple[list[dict], int]:
    """Split into table rows (named users) vs dummy/unnamed count."""
    real: list[dict] = []
    dummy_count = 0
    for doc in docs:
        if is_dummy_user(doc):
            dummy_count += 1
        else:
            real.append(doc)
    return real, dummy_count


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def extract_age(demo: dict) -> int | None:
    raw_age = demo.get("age")
    if raw_age is not None:
        try:
            age = int(raw_age)
            if 0 < age < 130:
                return age
        except (TypeError, ValueError):
            pass

    dob = demo.get("dateOfBirth") or demo.get("dob") or demo.get("birthDate")
    born = _parse_date(dob)
    if not born:
        return None
    today = datetime.now(timezone.utc).date()
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return years if 0 < years < 130 else None


def extract_gender(demo: dict) -> str:
    for key in ("gender", "sex", "Gender", "Sex"):
        val = demo.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def extract_team(demo: dict) -> str:
    for key in ("team", "teamName", "businessUnit", "unit", "group"):
        val = demo.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def resolve_manager_label(
    doc: dict,
    users_by_business_id: dict[str, dict],
) -> tuple[str | None, str | None]:
    m_details = _as_dict(doc.get("managerDetails"))
    manager_id = m_details.get("managerId")
    if not manager_id:
        return None, None
    manager_id = str(manager_id).strip()
    mgr_doc = users_by_business_id.get(manager_id)
    if mgr_doc:
        basic = _as_dict(mgr_doc.get("basicDetails"))
        name = f"{basic.get('firstName', '')} {basic.get('lastName', '')}".strip()
        return manager_id, name or manager_id
    return manager_id, get_manager_display_name(doc) if get_manager_display_name(doc) != "Not Specified" else manager_id


def user_doc_to_admin_fields(
    doc: dict,
    tenant_map: dict[str, str],
    users_by_business_id: dict[str, dict],
) -> dict:
    demo = _as_dict(doc.get("demographicDetails"))
    tenant_id = doc.get("tenantId")
    manager_id, manager_name = resolve_manager_label(doc, users_by_business_id)
    team = extract_team(demo) or demo.get("department", "") or ""
    first_name, last_name = get_user_name_parts(doc)

    return {
        "id": str(doc["_id"]),
        "email": doc.get("email", ""),
        "firstName": first_name,
        "lastName": last_name,
        "department": demo.get("department", "") or "",
        "designation": demo.get("designation", "") or "",
        "location": demo.get("location", "") or "",
        "team": team,
        "gender": extract_gender(demo),
        "age": extract_age(demo),
        "role": doc.get("enzoRole", "Employee"),
        "tenantId": tenant_id,
        "tenantName": tenant_map.get(tenant_id) if tenant_id else None,
        "managerId": manager_id,
        "managerName": manager_name,
        "userId": get_employee_user_id(doc),
        "createdAt": doc.get("createdAt"),
    }


def build_filter_options(users: list[dict]) -> dict:
    tenants: dict[str, str] = {}
    departments: set[str] = set()
    teams: set[str] = set()
    genders: set[str] = set()
    roles: set[str] = set()
    managers: set[str] = set()

    for u in users:
        tid = u.get("tenantId")
        if tid:
            tenants[tid] = u.get("tenantName") or tid
        if u.get("department"):
            departments.add(u["department"])
        if u.get("team"):
            teams.add(u["team"])
        if u.get("gender"):
            genders.add(u["gender"])
        if u.get("role"):
            roles.add(u["role"])
        if u.get("managerName"):
            managers.add(u["managerName"])

    return {
        "tenants": [{"id": k, "name": v} for k, v in sorted(tenants.items(), key=lambda x: x[1].lower())],
        "departments": sorted(departments, key=str.lower),
        "teams": sorted(teams, key=str.lower),
        "genders": sorted(genders, key=str.lower),
        "roles": sorted(roles, key=str.lower),
        "managers": sorted(managers, key=str.lower),
    }
