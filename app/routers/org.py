"""Org hierarchy routes — manager, reportees, scoped tree."""

from fastapi import APIRouter, Depends

from app.database import get_db
from app.deps import get_current_user
from app.models.org import (
    OrgPersonSummary,
    OrgReporteesResponse,
    OrgTreeResponse,
    OrgTreeNode,
)
from app.services.org_tree import (
    doc_to_person_summary,
    find_manager_doc,
    find_reportees,
    build_org_tree,
    get_org_scope,
)

router = APIRouter(prefix="/org", tags=["Org"])


@router.get("/manager", response_model=OrgPersonSummary | None)
async def get_manager(current_user: dict = Depends(get_current_user)):
    """Return the current user's reporting manager, if any."""
    db = get_db()
    mgr = await find_manager_doc(db, current_user)
    if not mgr:
        return None
    return OrgPersonSummary(**doc_to_person_summary(mgr))


@router.get("/reportees", response_model=OrgReporteesResponse)
async def get_reportees(current_user: dict = Depends(get_current_user)):
    """Return direct reports for the current user."""
    db = get_db()
    docs = await find_reportees(db, current_user)
    reportees = [OrgPersonSummary(**doc_to_person_summary(d)) for d in docs]
    return OrgReporteesResponse(reportees=reportees, total=len(reportees))


@router.get("/tree", response_model=OrgTreeResponse)
async def get_org_tree(current_user: dict = Depends(get_current_user)):
    """Return org tree for the current user's reporting line only."""
    db = get_db()
    scope = get_org_scope(current_user)
    roots_data, node_count = await build_org_tree(db, current_user, scope)
    roots = [OrgTreeNode(**r) for r in roots_data]
    return OrgTreeResponse(
        roots=roots,
        scope=scope,
        nodeCount=node_count,
        focalUserId=str(current_user["_id"]),
    )
