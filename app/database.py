"""MongoDB async connection via Motor for the read-only Enzo app."""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

logger = logging.getLogger("enzo.database")

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """Open MongoDB connection and ensure basic indices (gracefully handling read-only limits)."""
    global _client, _db
    _client = AsyncIOMotorClient(settings.mongo_uri)
    _db = _client[settings.mongo_db_name]
    
    # Verify connectivity
    await _client.admin.command("ping")
    logger.info("Connected to MongoDB: %s / %s", settings.mongo_uri, settings.mongo_db_name)
    
    # Ensure indices gracefully
    await _ensure_indices_gracefully()


async def close_db() -> None:
    """Gracefully close MongoDB connection."""
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed.")


def get_db() -> AsyncIOMotorDatabase:
    """Return the database handle. Raises if not connected."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return _db


def is_db_connected() -> bool:
    return _db is not None


async def _ensure_indices_gracefully() -> None:
    """Try to build read optimization indices, ignoring errors if DB user is read-only."""
    db = get_db()
    try:
        # Try to ensure index on users.email
        await db.users.create_index("email", unique=True)
        # Try to ensure index on insightactions.userId
        await db.insightactions.create_index("userId")
        await db.insightactions.create_index([("userId", 1), ("status", 1)])
        await db.conversations.create_index("userId")
        await db.conversations.create_index([("userId", 1), ("updatedAt", -1)])
        await db.kb_documents.create_index("status")
        await db.users.create_index("tenantId")
        await db.usage_events.create_index([("tenantId", 1), ("createdAt", -1)])
        await db.usage_events.create_index([("userId", 1), ("createdAt", -1)])
        await db.usage_events.create_index("createdAt")
        logger.info("Database indices verified/created.")
    except Exception as e:
        logger.warning(
            "Could not create database indexes (likely read-only DB connection permissions): %s", 
            str(e)
        )
