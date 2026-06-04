"""Task Pydantic schemas."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class TaskPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TaskOut(BaseModel):
    """Task returned by the API."""
    id: str
    userId: str
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    dueDate: datetime | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class TaskListResponse(BaseModel):
    """Paginated task list."""
    tasks: list[TaskOut]
    total: int
