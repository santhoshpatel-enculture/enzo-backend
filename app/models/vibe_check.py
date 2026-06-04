"""AI Vibe Check 2026 program submission schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class VibeCheckSubmitRequest(BaseModel):
    answers: dict[str, str | list[str]] = Field(..., description="Question id -> answer")


class VibeCheckStatusResponse(BaseModel):
    programId: str = "ai-vibe-check-2026"
    completed: bool
    submittedAt: datetime | None = None


class VibeCheckSubmitResponse(BaseModel):
    message: str
    programId: str = "ai-vibe-check-2026"
    submittedAt: datetime
