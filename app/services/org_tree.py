"""Org hierarchy helpers — manager chain, reportees, scoped trees."""

from __future__ import annotations

from app.services.user_profile import _as_dict, get_employee_user_id, get_manager_display_name


def get_org_scope(_user_doc: dict) -> str:
    """Org chart always shows the signed-in user's reporting line only."""
    return "lineage"


def get_manager_business_id(doc: dict) -> str | None:
    m_details = _as_dict(doc.get("managerDetails"))
    manager_id = m_details.get("managerId")
    if not manager_id:
        return None
    mid = str(manager_id).strip()
    return mid or None


def doc_to_person_summary(doc: dict) -> dict:
    basic = _as_dict(doc.get("basicDetails"))
    demo = _as_dict(doc.get("demographicDetails"))
    manager_id = get_manager_business_id(doc)
    return {
        "id": str(doc["_id"]),
        "userId": get_employee_user_id(doc),
        "email": doc.get("email", ""),
        "firstName": basic.get("firstName", ""),
        "lastName": basic.get("lastName", ""),
        "designation": demo.get("designation", ""),
        "department": demo.get("department", ""),
        "managerId": manager_id,
    }


def doc_to_tree_node(
    doc: dict,
    bid: str,
    users_by_business_id: dict[str, dict],
    children_map: dict[str, list[str]],
    included: set[str],
) -> dict:
    basic = _as_dict(doc.get("basicDetails"))
    demo = _as_dict(doc.get("demographicDetails"))
    return {
        "id": str(doc["_id"]),
        "userId": bid,
        "label": f"{basic.get('firstName', '')} {basic.get('lastName', '')}".strip(),
        "email": doc.get("email", "") or "",
        "designation": demo.get("designation", ""),
        "department": demo.get("department", ""),
        "managerId": get_manager_business_id(doc),
        "children": build_subtree(
            bid,
            users_by_business_id,
            children_map,
            included,
        ),
    }


async def find_manager_doc(db, user_doc: dict) -> dict | None:
    m_details = _as_dict(user_doc.get("managerDetails"))
    manager_id = m_details.get("managerId")
    if not manager_id:
        return None

    manager_id = str(manager_id).strip()

    mgr = await db.users.find_one(
        {
            "isDeleted": {"$ne": True},
            "$or": [
                {"basicDetails.userId": manager_id},
                {"basicDetails.userIdNormalized": manager_id.lower()},
            ],
        }
    )
    if mgr:
        return mgr

    mgr_email = m_details.get("managerEmailId")
    if mgr_email:
        mgr = await db.users.find_one(
            {"email": str(mgr_email).lower(), "isDeleted": {"$ne": True}}
        )
        if mgr:
            return mgr

    mgr_name = get_manager_display_name(user_doc)
    if mgr_name and mgr_name != "Not Specified":
        parts = mgr_name.split(None, 1)
        if len(parts) == 2:
            mgr = await db.users.find_one(
                {
                    "isDeleted": {"$ne": True},
                    "basicDetails.firstName": parts[0],
                    "basicDetails.lastName": parts[1],
                }
            )
            if mgr:
                return mgr

    return None


async def find_reportees(db, user_doc: dict) -> list[dict]:
    employee_id = get_employee_user_id(user_doc)
    if not employee_id:
        return []

    cursor = db.users.find(
        {
            "isDeleted": {"$ne": True},
            "$or": [
                {"managerDetails.managerId": employee_id},
                {"managerDetails.managerId": employee_id.lower()},
            ],
        }
    )
    return await cursor.to_list(500)


async def load_active_users(db, tenant_id: str | None = None) -> list[dict]:
    query: dict = {"isDeleted": {"$ne": True}}
    if tenant_id:
        query["tenantId"] = tenant_id
    cursor = db.users.find(query).limit(500)
    return await cursor.to_list(500)


def build_subtree(
    root_user_id: str | None,
    users_by_business_id: dict[str, dict],
    children_map: dict[str, list[str]],
    included: set[str],
) -> list[dict]:
    if not root_user_id or root_user_id not in included:
        return []

    nodes = []
    for child_id in sorted(children_map.get(root_user_id, [])):
        if child_id not in included or child_id not in users_by_business_id:
            continue
        doc = users_by_business_id[child_id]
        nodes.append(
            doc_to_tree_node(
                doc,
                child_id,
                users_by_business_id,
                children_map,
                included,
            )
        )
    return nodes


def _node_key(doc: dict) -> str:
    """Stable key for tree edges; prefer business userId, else Mongo id string."""
    return get_employee_user_id(doc) or str(doc["_id"])


async def build_manager_chain_top_down(db, user_doc: dict) -> list[dict]:
    """Direct manager first when walking up; returned top-down (CEO → … → your manager)."""
    chain_bottom_up: list[dict] = []
    current = user_doc
    seen: set[str] = {str(user_doc["_id"])}

    for _ in range(50):
        mgr = await find_manager_doc(db, current)
        if not mgr:
            break
        oid = str(mgr["_id"])
        if oid in seen:
            break
        seen.add(oid)
        chain_bottom_up.append(mgr)
        current = mgr

    chain_bottom_up.reverse()
    return chain_bottom_up


def collect_reportee_ids(
    root_key: str,
    users_by_business_id: dict[str, dict],
    children_map: dict[str, list[str]],
) -> set[str]:
    """All direct and indirect reportees below root_key."""
    included: set[str] = set()
    stack = [root_key]
    while stack:
        uid = stack.pop()
        for child in children_map.get(uid, []):
            if child in users_by_business_id and child not in included:
                included.add(child)
                stack.append(child)
    return included


def doc_to_tree_node_with_children(
    doc: dict,
    node_key: str,
    children: list[dict],
) -> dict:
    basic = _as_dict(doc.get("basicDetails"))
    demo = _as_dict(doc.get("demographicDetails"))
    return {
        "id": str(doc["_id"]),
        "userId": get_employee_user_id(doc),
        "label": f"{basic.get('firstName', '')} {basic.get('lastName', '')}".strip(),
        "email": doc.get("email", "") or "",
        "designation": demo.get("designation", ""),
        "department": demo.get("department", ""),
        "managerId": get_manager_business_id(doc),
        "children": children,
    }


def count_tree_nodes(nodes: list[dict]) -> int:
    total = 0
    stack = list(nodes)
    while stack:
        n = stack.pop()
        total += 1
        stack.extend(n.get("children") or [])
    return total


def nest_manager_chain(
    chain: list[dict],
    focal_node: dict,
) -> list[dict]:
    """Linear tree: top leader → … → focal user (with reportee subtree on focal)."""
    if not chain:
        return [focal_node]

    def at(index: int) -> dict:
        doc = chain[index]
        key = _node_key(doc)
        if index + 1 < len(chain):
            child = at(index + 1)
        else:
            child = focal_node
        return doc_to_tree_node_with_children(doc, key, [child])

    return [at(0)]


async def build_org_tree(db, user_doc: dict, _scope: str) -> tuple[list[dict], int]:
    """Single-root tree: full manager chain above, you, then all reportees below."""
    employee_id = get_employee_user_id(user_doc)
    user_key = employee_id or str(user_doc["_id"])
    tenant_id = user_doc.get("tenantId")

    all_users = await load_active_users(db, tenant_id)
    users_by_business_id: dict[str, dict] = {}
    children_map: dict[str, list[str]] = {}

    for doc in all_users:
        key = _node_key(doc)
        users_by_business_id[key] = doc
        mid = get_manager_business_id(doc)
        if mid:
            children_map.setdefault(mid, []).append(key)

    users_by_business_id[user_key] = user_doc

    manager_chain = await build_manager_chain_top_down(db, user_doc)

    reportee_keys = collect_reportee_ids(
        user_key, users_by_business_id, children_map
    )
    included = {user_key, *reportee_keys}
    for mgr in manager_chain:
        included.add(_node_key(mgr))

    reportee_children = build_subtree(
        user_key,
        users_by_business_id,
        children_map,
        included,
    )

    focal_node = doc_to_tree_node_with_children(
        user_doc, user_key, reportee_children
    )

    roots = nest_manager_chain(manager_chain, focal_node)
    return roots, count_tree_nodes(roots)
