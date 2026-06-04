"""MongoDB-backed conversation storage."""

import uuid
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.database import get_db


def new_message_id() -> str:
    return str(uuid.uuid4())


def _serialize_message(msg: dict) -> dict:
    ts = msg.get("timestamp")
    if hasattr(ts, "isoformat"):
        ts = ts.isoformat()
    out = {
        "messageId": msg.get("messageId") or new_message_id(),
        "role": msg.get("role", "user"),
        "content": msg.get("content", ""),
        "timestamp": ts,
    }
    if msg.get("feedback"):
        fb = msg["feedback"]
        if hasattr(fb.get("at"), "isoformat"):
            fb = {**fb, "at": fb["at"].isoformat()}
        out["feedback"] = fb
    return out


async def get_conversation(conversation_id: str) -> dict | None:
    db = get_db()
    return await db.conversations.find_one({"_id": conversation_id})


async def create_conversation(user_id: ObjectId, title: str) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    conversation_id = str(uuid.uuid4())
    doc = {
        "_id": conversation_id,
        "userId": user_id,
        "title": title,
        "messages": [],
        "createdAt": now,
        "updatedAt": now,
    }
    await db.conversations.insert_one(doc)
    return doc


async def append_message(conversation_id: str, message: dict) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    if "messageId" not in message:
        message = {**message, "messageId": new_message_id()}
    await db.conversations.update_one(
        {"_id": conversation_id},
        {
            "$push": {"messages": _serialize_message(message)},
            "$set": {"updatedAt": now},
        },
    )


async def set_message_feedback(
    conversation_id: str,
    user_id: ObjectId,
    message_id: str,
    rating: str,
    comment: str | None = None,
) -> bool:
    db = get_db()
    conv = await require_owned_conversation(conversation_id, user_id)
    messages = conv.get("messages", [])
    idx = next(
        (i for i, m in enumerate(messages) if m.get("messageId") == message_id),
        None,
    )
    if idx is None:
        return False
    msg = messages[idx]
    if msg.get("role") != "assistant":
        return False
    now = datetime.now(timezone.utc)
    feedback = {"rating": rating, "at": now}
    if comment:
        feedback["comment"] = comment[:500]
    await db.conversations.update_one(
        {"_id": conversation_id, "userId": user_id},
        {
            "$set": {
                f"messages.{idx}.feedback": feedback,
                "updatedAt": now,
            }
        },
    )
    await db.message_feedback.insert_one(
        {
            "conversationId": conversation_id,
            "messageId": message_id,
            "userId": user_id,
            "rating": rating,
            "comment": comment,
            "createdAt": now,
        }
    )
    return True


async def list_user_conversations(user_id: ObjectId) -> list[dict]:
    db = get_db()
    cursor = db.conversations.find({"userId": user_id}).sort("updatedAt", -1)
    return await cursor.to_list(200)


async def delete_conversation(conversation_id: str) -> bool:
    db = get_db()
    result = await db.conversations.delete_one({"_id": conversation_id})
    return result.deleted_count > 0


async def delete_all_user_conversations(user_id: ObjectId) -> int:
    db = get_db()
    result = await db.conversations.delete_many({"userId": user_id})
    return result.deleted_count


async def require_owned_conversation(conversation_id: str, user_id: ObjectId) -> dict:
    conv = await get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if conv.get("userId") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return conv
