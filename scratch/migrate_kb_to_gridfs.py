"""Migrate legacy kb_documents with storedPath to GridFS."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import connect_db, close_db, get_db
from app.services.kb_indexer import migrate_legacy_file_to_gridfs


async def main() -> None:
    await connect_db()
    db = get_db()
    cursor = db.kb_documents.find({"storedPath": {"$exists": True, "$ne": None}})
    docs = await cursor.to_list(500)
    for doc in docs:
        await migrate_legacy_file_to_gridfs(doc)
        if not doc.get("tenantId"):
            await db.kb_documents.update_one(
                {"_id": doc["_id"]},
                {"$set": {"tenantId": "enculture"}},
            )
    await close_db()
    print(f"Migrated {len(docs)} KB document(s).")


if __name__ == "__main__":
    asyncio.run(main())
