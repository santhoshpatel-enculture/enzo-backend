"""Tenant seeding and lookup."""

from app.database import get_db

DEFAULT_TENANTS = [
    {"_id": "enculture", "name": "Enculture"},
    {"_id": "acme", "name": "Acme Corp"},
    {"_id": "globex", "name": "Globex Corp"},
    {"_id": "initech", "name": "Initech Co"},
    {"_id": "umbrella", "name": "Umbrella Corp"},
]


async def ensure_tenants_seeded() -> None:
    db = get_db()
    count = await db.tenants.count_documents({})
    if count == 0:
        await db.tenants.insert_many(DEFAULT_TENANTS)


async def get_tenant_map() -> dict[str, str]:
    db = get_db()
    await ensure_tenants_seeded()
    tenants = await db.tenants.find({}).to_list(100)
    return {t["_id"]: t.get("name", t["_id"]) for t in tenants}
