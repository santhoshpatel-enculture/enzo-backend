"""Profile route — returns the current user's profile details."""

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models.user import UserProfile
from app.services.user_profile import user_doc_to_profile

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("", response_model=UserProfile)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's full profile."""
    return user_doc_to_profile(current_user)
