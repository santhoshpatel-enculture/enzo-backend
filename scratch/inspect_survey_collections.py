"""List MongoDB collections that may contain survey data."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def main() -> None:
    uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
    db_name = os.getenv("MONGO_DB_NAME", "enzo_db").strip()
    client = AsyncIOMotorClient(uri)
    db = client[db_name]

    names = await db.list_collection_names()
    keywords = ("survey", "response", "feedback", "assignment", "participant")
    print(f"Database: {db_name}")
    print("Survey-related collections:")
    for name in sorted(names):
        if any(k in name.lower() for k in keywords):
            count = await db[name].count_documents({})
            print(f"  - {name}: {count} documents")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
