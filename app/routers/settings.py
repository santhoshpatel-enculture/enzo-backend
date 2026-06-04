"""Settings routes — per-user preferences stored on user document."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.database import get_db
from app.deps import get_current_user
from app.models.settings import UserSettings

router = APIRouter(prefix="/settings", tags=["Settings"])

_DEFAULTS = UserSettings().model_dump()


def _merge_settings(stored: dict | None) -> UserSettings:
    merged = {**_DEFAULTS, **(stored or {})}
    return UserSettings(**merged)


@router.get("", response_model=UserSettings)
async def get_settings(current_user: dict = Depends(get_current_user)):
    """Get user settings (merged with defaults)."""
    stored = current_user.get("enzoSettings")
    return _merge_settings(stored if isinstance(stored, dict) else None)


@router.put("", response_model=UserSettings)
async def update_settings(
    body: UserSettings,
    current_user: dict = Depends(get_current_user),
):
    """Persist user settings on the user document."""
    db = get_db()
    payload = body.model_dump()
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "enzoSettings": payload,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    return body
