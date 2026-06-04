"""Tasks routes — list, filter by status/priority, and upcoming deadlines.

Security: All queries are scoped to the authenticated user's ID
(ownership validation on every request).
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from bson import ObjectId

from app.database import get_db
from app.deps import get_current_user
from app.models.task import TaskOut, TaskListResponse

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _doc_to_task(doc: dict) -> TaskOut:
    # default priority mapping from bookmarked status
    is_high = doc.get("bookmarked", False)
    priority = "high" if is_high else "medium"
    
    # default due date calculation (7 days after creation if not specified)
    created = doc.get("createdAt")
    due = doc.get("dueDate")
    if not due and created:
        due = created + timedelta(days=7)

    return TaskOut(
        id=str(doc["_id"]),
        userId=str(doc["userId"]),
        title=doc.get("title", ""),
        description=doc.get("what", "") or doc.get("why", "") or doc.get("description", ""),
        status=doc.get("status", "pending"),
        priority=priority,
        dueDate=due,
        createdAt=created,
        updatedAt=doc.get("updatedAt"),
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: str | None = Query(None, description="Filter by status"),
    priority: str | None = Query(None, description="Filter by priority"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """List the current user's tasks from the insightactions collection."""
    db = get_db()
    user_id = current_user["_id"]

    query: dict = {
        "userId": ObjectId(user_id),
        "isDeleted": {"$ne": True}
    }
    
    if status:
        query["status"] = status
    if priority:
        # map requested priority back to bookmarked filter
        if priority in ("high", "critical"):
            query["bookmarked"] = True
        elif priority in ("medium", "low"):
            query["bookmarked"] = {"$ne": True}

    total = await db.insightactions.count_documents(query)
    cursor = db.insightactions.find(query).sort("createdAt", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    tasks = [_doc_to_task(d) for d in docs]
    return TaskListResponse(tasks=tasks, total=total)


@router.get("/pending", response_model=TaskListResponse)
async def pending_tasks(current_user: dict = Depends(get_current_user)):
    """List tasks with status 'pending'."""
    db = get_db()
    query = {
        "userId": ObjectId(current_user["_id"]), 
        "status": "pending",
        "isDeleted": {"$ne": True}
    }
    docs = await db.insightactions.find(query).sort("createdAt", -1).to_list(100)
    tasks = [_doc_to_task(d) for d in docs]
    return TaskListResponse(tasks=tasks, total=len(tasks))


@router.get("/critical", response_model=TaskListResponse)
async def critical_tasks(current_user: dict = Depends(get_current_user)):
    """List bookmarked (priority high/critical) tasks that are not completed."""
    db = get_db()
    query = {
        "userId": ObjectId(current_user["_id"]),
        "bookmarked": True,
        "status": {"$ne": "completed"},
        "isDeleted": {"$ne": True}
    }
    docs = await db.insightactions.find(query).sort("createdAt", -1).to_list(100)
    tasks = [_doc_to_task(d) for d in docs]
    return TaskListResponse(tasks=tasks, total=len(tasks))


@router.get("/upcoming", response_model=TaskListResponse)
async def upcoming_tasks(
    days: int = Query(7, ge=1, le=30),
    current_user: dict = Depends(get_current_user),
):
    """List upcoming tasks created or due recently."""
    db = get_db()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    
    # Query tasks that are not completed
    query = {
        "userId": ObjectId(current_user["_id"]),
        "status": {"$ne": "completed"},
        "isDeleted": {"$ne": True}
    }
    docs = await db.insightactions.find(query).sort("createdAt", -1).to_list(100)
    
    # Filter based on simulated due date in python (since dueDate is computed dynamically)
    tasks = []
    for d in docs:
        task = _doc_to_task(d)
        if task.dueDate and now <= task.dueDate <= cutoff:
            tasks.append(task)
            
    return TaskListResponse(tasks=tasks, total=len(tasks))
