"""Set default password Test@1234 and mustChangePassword for active users.

Usage (from Enzo-backend with venv active):
  python scratch/set_default_passwords.py
  python scratch/set_default_passwords.py --email user@enculture.ai
"""

import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.security import hash_password  # noqa: E402

DEFAULT_PASSWORD = "Test@1234"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", help="Only update this email")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Update all non-deleted users (default: only users missing password)",
    )
    args = parser.parse_args()

    uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
    db_name = os.getenv("MONGO_DB_NAME", "enzo_db").strip()
    client = AsyncIOMotorClient(uri)
    db = client[db_name]

    query: dict = {"isDeleted": {"$ne": True}}
    if args.email:
        query["email"] = args.email.lower()
    elif not args.all:
        query["$or"] = [
            {"password": {"$exists": False}},
            {"password": ""},
            {"password": None},
        ]

    hashed = hash_password(DEFAULT_PASSWORD)
    now = datetime.now(timezone.utc)
    updated = 0

    async for doc in db.users.find(query, {"email": 1}):
        await db.users.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "password": hashed,
                    "mustChangePassword": True,
                    "updatedAt": now,
                }
            },
        )
        updated += 1
        print(f"Updated: {doc.get('email')}")

    print(f"Done. Updated {updated} user(s). Default password: {DEFAULT_PASSWORD}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
