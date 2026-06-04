"""One-time copy of Enzo-required collections from enculture → enzo_db.

Reads only from enculture; writes only to enzo_db.
Collections: users, insightactions
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SOURCE_DB = "enculture"
TARGET_DB = "enzo_db"
COLLECTIONS = ("users", "insightactions")
BATCH_SIZE = 500


async def copy_collection(client, name: str) -> int:
    src = client[SOURCE_DB][name]
    dst = client[TARGET_DB][name]

    existing = await dst.count_documents({})
    if existing:
        print(f"  {name}: target already has {existing} docs — skipping copy")
        return existing

    batch: list[dict] = []
    total = 0
    async for doc in src.find({}):
        batch.append(doc)
        if len(batch) >= BATCH_SIZE:
            await dst.insert_many(batch, ordered=False)
            total += len(batch)
            print(f"  {name}: copied {total}...")
            batch = []

    if batch:
        await dst.insert_many(batch, ordered=False)
        total += len(batch)

    print(f"  {name}: done ({total} documents)")
    return total


async def main() -> None:
    uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
    client = AsyncIOMotorClient(uri)
    await client.admin.command("ping")

    print(f"Copying {COLLECTIONS} from '{SOURCE_DB}' → '{TARGET_DB}'")
    for coll in COLLECTIONS:
        await copy_collection(client, coll)

    target = client[TARGET_DB]
    for coll in COLLECTIONS:
        n = await target[coll].count_documents({})
        print(f"Verify {TARGET_DB}.{coll}: {n} documents")

    client.close()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(main())
