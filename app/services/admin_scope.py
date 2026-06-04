"""Admin query scoping by tenant."""

from bson import ObjectId

from app.database import get_db


async def user_ids_for_tenant(tenant_id: str) -> list[ObjectId]:
    db = get_db()
    users = await db.users.find(
        {"tenantId": tenant_id, "isDeleted": {"$ne": True}},
        {"_id": 1},
    ).to_list(10000)
    return [u["_id"] for u in users]


async def conversation_filter_for_tenant(tenant_filter: dict | None) -> dict:
    if not tenant_filter:
        return {}
    tenant_id = tenant_filter.get("tenantId")
    if not tenant_id:
        return {}
    user_ids = await user_ids_for_tenant(tenant_id)
    if not user_ids:
        return {"userId": {"$in": []}}
    return {"userId": {"$in": user_ids}}
