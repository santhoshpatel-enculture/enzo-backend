"""Program participation metadata — anonymous; never returns answers."""

import logging
from datetime import datetime

from bson import ObjectId

logger = logging.getLogger("enzo.programs")

# Candidate Enculture collection names (first match wins)
_ASSIGNMENT_COLLECTIONS = (
    "surveyassignments",
    "survey_assignments",
    "usersurveyassignments",
    "participantsurveys",
)
_PROGRAM_COLLECTIONS = ("surveys", "cultureSurveys", "culture_surveys")


async def _collection_exists(db, name: str) -> bool:
    names = await db.list_collection_names()
    return name in names


async def _find_assignment_collection(db) -> str | None:
    for name in _ASSIGNMENT_COLLECTIONS:
        if await _collection_exists(db, name):
            return name
    return None


def _parse_status(doc: dict) -> str:
    for key in ("status", "surveyStatus", "completionStatus", "state"):
        val = doc.get(key)
        if val is not None:
            if isinstance(val, str):
                return val
            return str(val)
    if doc.get("completedAt") or doc.get("completed") or doc.get("isCompleted"):
        return "completed"
    return "pending"


def _get_datetime(doc: dict, *keys: str) -> datetime | None:
    for key in keys:
        val = doc.get(key)
        if isinstance(val, datetime):
            return val
    return None


async def list_user_programs(db, user_id: ObjectId, email: str) -> list[dict]:
    """List program participation rows for a user (metadata only)."""
    coll_name = await _find_assignment_collection(db)
    if not coll_name:
        logger.debug("No program assignment collection found in database")
        return []

    coll = db[coll_name]
    query = {
        "$or": [
            {"userId": user_id},
            {"userId": str(user_id)},
            {"userEmail": email},
            {"email": email},
        ],
        "isDeleted": {"$ne": True},
    }
    cursor = coll.find(query).sort("updatedAt", -1).limit(100)
    docs = await cursor.to_list(100)

    programs: list[dict] = []
    for doc in docs:
        program_id = doc.get("surveyId") or doc.get("survey_id") or doc.get("_id")
        title = doc.get("title") or doc.get("surveyTitle") or doc.get("name") or "Program"

        if program_id and not doc.get("title"):
            for sname in _PROGRAM_COLLECTIONS:
                if await _collection_exists(db, sname):
                    sdoc = await db[sname].find_one(
                        {"_id": program_id}
                        if isinstance(program_id, ObjectId)
                        else {"_id": ObjectId(program_id)}
                        if ObjectId.is_valid(str(program_id))
                        else {"surveyId": program_id}
                    )
                    if not sdoc and ObjectId.is_valid(str(program_id)):
                        try:
                            sdoc = await db[sname].find_one({"_id": ObjectId(str(program_id))})
                        except Exception:
                            sdoc = None
                    if sdoc:
                        title = sdoc.get("title") or sdoc.get("name") or title
                    break

        programs.append(
            {
                "id": str(doc.get("_id", program_id)),
                "title": str(title),
                "status": _parse_status(doc),
                "dueAt": _get_datetime(doc, "dueAt", "dueDate", "endDate"),
                "completedAt": _get_datetime(doc, "completedAt", "submittedAt"),
                "isAnonymous": True,
                "answersVisible": False,
            }
        )
    return programs


async def get_user_program_detail(
    db, user_id: ObjectId, email: str, program_participation_id: str
) -> dict | None:
    """Get one participation record; never includes answers."""
    coll_name = await _find_assignment_collection(db)
    if not coll_name:
        return None

    coll = db[coll_name]
    ownership = {
        "$or": [
            {"userId": user_id},
            {"userId": str(user_id)},
            {"userEmail": email},
            {"email": email},
        ],
    }
    id_filter: dict
    if ObjectId.is_valid(program_participation_id):
        id_filter = {"_id": ObjectId(program_participation_id)}
    else:
        id_filter = {
            "$or": [
                {"surveyId": program_participation_id},
                {"survey_id": program_participation_id},
            ]
        }

    doc = await coll.find_one(
        {
            "$and": [
                ownership,
                id_filter,
                {"isDeleted": {"$ne": True}},
            ]
        }
    )
    if not doc:
        return None

    status = _parse_status(doc)
    description = doc.get("description") or doc.get("surveyDescription")
    return {
        "id": str(doc.get("_id")),
        "title": doc.get("title") or doc.get("surveyTitle") or "Program",
        "status": status,
        "dueAt": _get_datetime(doc, "dueAt", "dueDate", "endDate"),
        "completedAt": _get_datetime(doc, "completedAt", "submittedAt"),
        "isAnonymous": True,
        "answersVisible": False,
        "description": description,
        "participationStatus": status,
    }
