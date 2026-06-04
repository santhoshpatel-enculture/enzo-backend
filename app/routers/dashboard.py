"""Dashboard summary route — aggregated stats and AI daily insights."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from bson import ObjectId

from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
async def get_dashboard_summary(current_user: dict = Depends(get_current_user)):
    """Return dashboard metrics for the current user."""
    db = get_db()
    user_id = current_user["_id"]

    # Query tasks from insightactions
    base_query = {
        "userId": ObjectId(user_id),
        "isDeleted": {"$ne": True}
    }
    
    total_tasks = await db.insightactions.count_documents(base_query)
    
    pending_tasks = await db.insightactions.count_documents({
        **base_query,
        "status": "pending"
    })
    
    in_progress_tasks = await db.insightactions.count_documents({
        **base_query,
        "status": "in_progress"
    })
    
    completed_tasks = await db.insightactions.count_documents({
        **base_query,
        "status": "completed"
    })
    
    critical_tasks = await db.insightactions.count_documents({
        **base_query,
        "bookmarked": True,
        "status": {"$ne": "completed"}
    })

    recent_conversations = await db.conversations.count_documents(
        {"userId": ObjectId(user_id)}
    )

    # Build insights
    insights = []
    if critical_tasks > 0:
        insights.append({
            "type": "warning",
            "title": "Critical Tasks",
            "message": f"You have {critical_tasks} critical/high-priority action item(s) that need attention.",
            "icon": "alert-triangle",
        })
    if pending_tasks > 2:
        insights.append({
            "type": "suggestion",
            "title": "Productivity Tip",
            "message": "Consider prioritizing your pending tasks. Start with the most urgent ones to stay on track.",
            "icon": "lightbulb",
        })
    if completed_tasks > 0:
        completion_rate = round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        insights.append({
            "type": "success",
            "title": "Progress Update",
            "message": f"Great job! You've completed {completion_rate}% of your tasks ({completed_tasks}/{total_tasks}).",
            "icon": "check-circle",
        })

    # Map user profile details safely
    basic = current_user.get("basicDetails", {})
    demographics = current_user.get("demographicDetails", {})
    
    first_name = basic.get("firstName", "") if isinstance(basic, dict) else getattr(basic, "firstName", "")
    last_name = basic.get("lastName", "") if isinstance(basic, dict) else getattr(basic, "lastName", "")
    dept = demographics.get("department", "Not Specified") if isinstance(demographics, dict) else getattr(demographics, "department", "Not Specified")
    desg = demographics.get("designation", "Not Specified") if isinstance(demographics, dict) else getattr(demographics, "designation", "Not Specified")

    return {
        "user": {
            "firstName": first_name,
            "lastName": last_name,
            "department": dept,
            "designation": desg,
        },
        "metrics": {
            "totalTasks": total_tasks,
            "pendingTasks": pending_tasks,
            "inProgressTasks": in_progress_tasks,
            "completedTasks": completed_tasks,
            "criticalTasks": critical_tasks,
            "upcomingDeadlines": 0, # simulated
            "recentConversations": recent_conversations,
        },
        "insights": insights,
    }
