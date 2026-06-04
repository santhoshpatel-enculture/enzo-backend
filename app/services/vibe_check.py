"""AI Vibe Check 2026 — store anonymous participation responses."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId

SURVEY_ID = "ai-vibe-check-2026"
COLLECTION = "survey_responses"


async def get_completion_status(db, user_id: ObjectId) -> dict:
    doc = await db[COLLECTION].find_one(
        {"surveyId": SURVEY_ID, "userId": user_id, "isDeleted": {"$ne": True}}
    )
    if not doc:
        return {"completed": False, "submittedAt": None}
    return {
        "completed": True,
        "submittedAt": doc.get("submittedAt"),
    }


async def submit_responses(db, user_id: ObjectId, email: str, answers: dict) -> datetime:
    now = datetime.now(timezone.utc)
    existing = await db[COLLECTION].find_one(
        {"surveyId": SURVEY_ID, "userId": user_id, "isDeleted": {"$ne": True}}
    )
    payload = {
        "surveyId": SURVEY_ID,
        "userId": user_id,
        "email": email,
        "answers": answers,
        "submittedAt": now,
        "updatedAt": now,
        "isDeleted": False,
    }
    if existing:
        await db[COLLECTION].update_one({"_id": existing["_id"]}, {"$set": payload})
    else:
        payload["createdAt"] = now
        await db[COLLECTION].insert_one(payload)
    return now
