"""Program API schemas — metadata only; no individual answers."""

from datetime import datetime
from pydantic import BaseModel


class ProgramSummary(BaseModel):
    id: str
    title: str
    status: str
    dueAt: datetime | None = None
    completedAt: datetime | None = None
    isAnonymous: bool = True
    answersVisible: bool = False


class ProgramDetail(ProgramSummary):
    description: str | None = None
    participationStatus: str


class ProgramListResponse(BaseModel):
    programs: list[ProgramSummary]
    total: int
