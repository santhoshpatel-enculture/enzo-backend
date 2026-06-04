"""Program routes — anonymous participation metadata only."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.deps import get_current_user
from app.models.program import ProgramListResponse, ProgramSummary, ProgramDetail
from app.models.vibe_check import (
    VibeCheckStatusResponse,
    VibeCheckSubmitRequest,
    VibeCheckSubmitResponse,
)
from app.services.programs import list_user_programs, get_user_program_detail
from app.services.vibe_check import get_completion_status, submit_responses

router = APIRouter(prefix="/programs", tags=["Programs"])


@router.get("", response_model=ProgramListResponse)
async def list_programs(current_user: dict = Depends(get_current_user)):
    """List programs the user is enrolled in (no answer payloads)."""
    db = get_db()
    rows = await list_user_programs(
        db, current_user["_id"], (current_user.get("email") or "").lower()
    )
    programs = [ProgramSummary(**r) for r in rows]
    return ProgramListResponse(programs=programs, total=len(programs))


@router.get("/ai-vibe-check-2026/status", response_model=VibeCheckStatusResponse)
async def vibe_check_status(current_user: dict = Depends(get_current_user)):
    """Whether the signed-in user has completed the AI Vibe Check program."""
    db = get_db()
    status_doc = await get_completion_status(db, current_user["_id"])
    return VibeCheckStatusResponse(
        completed=status_doc["completed"],
        submittedAt=status_doc["submittedAt"],
    )


@router.post("/ai-vibe-check-2026/submit", response_model=VibeCheckSubmitResponse)
async def vibe_check_submit(
    body: VibeCheckSubmitRequest,
    current_user: dict = Depends(get_current_user),
):
    """Submit AI Vibe Check responses (stored per user; not exposed to managers)."""
    if not body.answers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answers are required",
        )
    db = get_db()
    submitted_at = await submit_responses(
        db,
        current_user["_id"],
        (current_user.get("email") or "").lower(),
        body.answers,
    )
    return VibeCheckSubmitResponse(
        message="Your responses have been received. Thank you!",
        submittedAt=submitted_at,
    )


@router.get("/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Program participation detail — metadata only; answers never returned."""
    db = get_db()
    detail = await get_user_program_detail(
        db,
        current_user["_id"],
        (current_user.get("email") or "").lower(),
        program_id,
    )
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Program not found",
        )
    return ProgramDetail(**detail)
