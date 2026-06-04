"""Admin console API — metrics, users, config, KB, conversations, tasks."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pymongo.errors import PyMongoError

from app.admin_deps import require_permission
from app.services.admin_rbac import resolve_admin_tenant_id
from app.services.admin_scope import conversation_filter_for_tenant
from app.config import settings
from app.database import get_db
from app.models.admin import (
    AdminConversationSummary,
    AdminMetrics,
    AdminTaskOut,
    AdminUserCreate,
    AdminUserFilterOptions,
    AdminUserOut,
    AdminUsersListResponse,
    AdminUserUpdate,
    KbDocumentOut,
    ModelOptionOut,
    PlatformConfigOut,
    PlatformConfigUpdate,
    TelemetryPricingUpdate,
    TelemetrySummary,
    TelemetryTenantRow,
    TelemetryUserRow,
    TenantBreakdownItem,
    TenantBudgetOut,
    TenantBudgetUpdate,
    FeedbackSummaryRow,
    TopUserUsage,
)
from app.routers.tasks import _doc_to_task
from app.security import hash_password
from app.services import conversation_store as conv_store
from app.services.kb_indexer import (
    delete_kb_document,
    extract_text_from_bytes,
    save_kb_document,
)
from app.services.tenant_budget import (
    get_period_usage,
    get_tenant_budgets,
    update_tenant_budgets,
)
from app.services.model_registry import catalog_for_api, resolve_model_route
from app.services.platform_config import get_platform_config, update_platform_config
from app.services.admin_rbac import get_admin_role, tenant_filter_for_user
from app.services.admin_users import (
    build_filter_options,
    build_users_by_business_id,
    load_active_user_docs,
    partition_users_for_admin,
    user_doc_to_admin_fields,
)
from app.services.tenants import ensure_tenants_seeded, get_tenant_map
from app.services.user_profile import get_employee_user_id
from app.services.prompt_files import prompt_file_meta, read_knowledge_base_file
from app.services.usage_telemetry import (
    get_ops_telemetry,
    get_telemetry_summary,
    get_telemetry_timeseries,
    get_telemetry_users,
)

logger = logging.getLogger("enzo.admin")
router = APIRouter(prefix="/admin", tags=["Admin"])


def _write_error(exc: Exception) -> HTTPException:
    logger.error("Admin write failed: %s", exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database write failed. Check MongoDB permissions.",
    )


def _user_doc_to_admin_out(
    doc: dict,
    tenant_map: dict[str, str],
    users_by_business_id: dict[str, dict] | None = None,
) -> AdminUserOut:
    if users_by_business_id is None:
        bid = get_employee_user_id(doc)
        users_by_business_id = {bid: doc} if bid else {}
    return AdminUserOut(**user_doc_to_admin_fields(doc, tenant_map, users_by_business_id))


def _config_to_out(cfg: dict) -> PlatformConfigOut:
    meta = prompt_file_meta()
    primary, fallback = resolve_model_route(cfg)
    return PlatformConfigOut(
        groq_model=cfg.get("groq_model", settings.groq_model),
        primary_model=primary,
        fallback_model=fallback,
        available_models=[ModelOptionOut(**m) for m in catalog_for_api()],
        temperature=float(cfg.get("temperature", 0.7)),
        system_prompt=cfg.get("system_prompt", ""),
        knowledge_base=cfg.get("knowledge_base", read_knowledge_base_file()),
        streaming_enabled=bool(cfg.get("streaming_enabled", True)),
        rate_limit_qpm=int(cfg.get("rate_limit_qpm", 60)),
        groq_api_key_set=bool(settings.groq_api_key),
        openai_api_key_set=bool(settings.openai_api_key),
        system_prompt_file=meta["system_prompt_file"],
        knowledge_base_file=meta["knowledge_base_file"],
        cost_per_1m_input_tokens=float(cfg.get("cost_per_1m_input_tokens", 0.05)),
        cost_per_1m_output_tokens=float(cfg.get("cost_per_1m_output_tokens", 0.08)),
    )


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    return f"{int(size_bytes / 1024)} KB"


@router.get("/metrics", response_model=AdminMetrics)
async def get_metrics(
    request: Request,
    _admin: dict = Depends(require_permission("telemetry:read")),
):
    db = get_db()
    await ensure_tenants_seeded()
    summary = await get_telemetry_summary()
    user_query = {"isDeleted": {"$ne": True}}
    total_users = await db.users.count_documents({})
    active_users = await db.users.count_documents(user_query)
    total_tasks = await db.insightactions.count_documents({"isDeleted": {"$ne": True}})
    total_conversations = await db.conversations.count_documents({})

    tenant_breakdown = [
        TenantBreakdownItem(
            tenantId=t["tenantId"],
            name=t["name"],
            users=t["users"],
            conversations=t["conversations"],
            userMessages=t["userMessages"],
            assistantMessages=t["assistantMessages"],
            totalMessages=t["totalMessages"],
            promptTokens=t["promptTokens"],
            completionTokens=t["completionTokens"],
            totalTokens=t["totalTokens"],
            tokensEstimate=t["tokensDisplay"],
            estimatedCostUsd=t["estimatedCostUsd"],
            costDisplay=t["costDisplay"],
            percentage=t["percentage"],
        )
        for t in summary["tenantBreakdown"]
    ]

    user_rows = await get_telemetry_users(limit=10)
    top_users = [
        TopUserUsage(
            email=u["email"],
            tenant=u["tenantName"],
            chats=u["conversations"],
            userMessages=u["userMessages"],
            assistantMessages=u["assistantMessages"],
            totalMessages=u["totalMessages"],
            tokens=u["tokensDisplay"],
            costDisplay=u["costDisplay"],
            lastActive=u["lastActive"],
        )
        for u in user_rows
    ]

    return AdminMetrics(
        totalUsers=total_users,
        activeUsers=active_users,
        totalTasks=total_tasks,
        totalConversations=total_conversations,
        tokensEstimate=summary["tokensDisplay"],
        tenantBreakdown=tenant_breakdown,
        topUsers=top_users,
    )


@router.get("/telemetry/summary", response_model=TelemetrySummary)
async def telemetry_summary(
    days: int = Query(30, ge=1, le=365),
    tenant_id: str | None = Query(None),
    _admin: dict = Depends(require_permission("telemetry:read")),
):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    summary = await get_telemetry_summary(start, end)
    timeseries = await get_telemetry_timeseries(start, end, tenant_id)
    users = await get_telemetry_users(start, end, tenant_id, limit=50)
    ops = await get_ops_telemetry()
    return TelemetrySummary(
        periodStart=summary["periodStart"],
        periodEnd=summary["periodEnd"],
        totalUserMessages=summary["totalUserMessages"],
        totalAssistantMessages=summary["totalAssistantMessages"],
        totalMessages=summary["totalMessages"],
        promptTokens=summary["promptTokens"],
        completionTokens=summary["completionTokens"],
        totalTokens=summary["totalTokens"],
        tokensDisplay=summary["tokensDisplay"],
        estimatedCostUsd=summary["estimatedCostUsd"],
        costDisplay=summary["costDisplay"],
        activeUsers=summary["activeUsers"],
        tenantBreakdown=[TelemetryTenantRow(**t) for t in summary["tenantBreakdown"]],
        timeseries=timeseries,
        ops=ops,
        users=[TelemetryUserRow(**u) for u in users],
    )


@router.get("/telemetry/users", response_model=list[TelemetryUserRow])
async def telemetry_users(
    days: int = Query(30, ge=1, le=365),
    tenant_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _admin: dict = Depends(require_permission("telemetry:read")),
):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    rows = await get_telemetry_users(start, end, tenant_id, limit)
    return [TelemetryUserRow(**u) for u in rows]


@router.put("/telemetry/pricing", response_model=PlatformConfigOut)
async def update_telemetry_pricing(
    request: Request,
    body: TelemetryPricingUpdate,
    _admin: dict = Depends(require_permission("telemetry:pricing")),
):
    tenant_id = resolve_admin_tenant_id(request, _admin)
    patch = body.model_dump(exclude_none=True)
    try:
        cfg = await update_platform_config(tenant_id, patch)
    except PyMongoError as e:
        raise _write_error(e) from e
    return _config_to_out(cfg)


@router.get("/tenants/{tenant_id}/budget", response_model=TenantBudgetOut)
async def get_tenant_budget(
    tenant_id: str,
    request: Request,
    _admin: dict = Depends(require_permission("telemetry:read")),
):
    from app.services.admin_rbac import can_access_tenant

    if not can_access_tenant(_admin, tenant_id):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    budgets = await get_tenant_budgets(tenant_id)
    usage = await get_period_usage(tenant_id)
    return TenantBudgetOut(
        tenantId=tenant_id,
        monthlyTokenLimit=int(budgets.get("monthlyTokenLimit", 0)),
        monthlyCostUsdLimit=float(budgets.get("monthlyCostUsdLimit", 0)),
        alertThresholdPct=int(budgets.get("alertThresholdPct", 80)),
        usageTokens=usage["totalTokens"],
        usageCostUsd=usage["estimatedCostUsd"],
    )


@router.put("/tenants/{tenant_id}/budget", response_model=TenantBudgetOut)
async def put_tenant_budget(
    tenant_id: str,
    body: TenantBudgetUpdate,
    request: Request,
    _admin: dict = Depends(require_permission("budgets:write")),
):
    from app.services.admin_rbac import can_access_tenant

    if not can_access_tenant(_admin, tenant_id):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    budgets = await update_tenant_budgets(tenant_id, body.model_dump(exclude_none=True))
    usage = await get_period_usage(tenant_id)
    return TenantBudgetOut(
        tenantId=tenant_id,
        monthlyTokenLimit=int(budgets.get("monthlyTokenLimit", 0)),
        monthlyCostUsdLimit=float(budgets.get("monthlyCostUsdLimit", 0)),
        alertThresholdPct=int(budgets.get("alertThresholdPct", 80)),
        usageTokens=usage["totalTokens"],
        usageCostUsd=usage["estimatedCostUsd"],
    )


@router.get("/feedback/summary", response_model=list[FeedbackSummaryRow])
async def feedback_summary(
    request: Request,
    _admin: dict = Depends(require_permission("feedback:read")),
):
    db = get_db()
    tfilter = tenant_filter_for_user(_admin, request)
    match: dict = {}
    if tfilter:
        user_ids = await db.users.find(
            {**tfilter, "isDeleted": {"$ne": True}}, {"_id": 1}
        ).to_list(5000)
        match["userId"] = {"$in": [u["_id"] for u in user_ids]}
    pipeline: list = []
    if match:
        pipeline.append({"$match": match})
    pipeline.append({"$group": {"_id": "$rating", "count": {"$sum": 1}}})
    rows = await db.message_feedback.aggregate(pipeline).to_list(20)
    up = sum(r["count"] for r in rows if r["_id"] == "up")
    down = sum(r["count"] for r in rows if r["_id"] == "down")
    tid = tfilter.get("tenantId") if tfilter else "all"
    return [FeedbackSummaryRow(tenantId=tid, up=up, down=down, total=up + down)]


@router.get("/users", response_model=AdminUsersListResponse)
async def list_users(
    request: Request,
    _admin: dict = Depends(require_permission("users:read")),
):
    db = get_db()
    tenant_map = await get_tenant_map()
    role = get_admin_role(_admin)
    tfilter = tenant_filter_for_user(_admin, request)
    if role == "super_admin":
        tfilter = None
    query = {"isDeleted": {"$ne": True}}
    if tfilter:
        query.update(tfilter)
    cap = settings.admin_users_list_limit
    cursor = db.users.find(query).sort("createdAt", -1)
    if cap and cap > 0:
        all_docs = await cursor.limit(cap).to_list(cap)
    else:
        all_docs = await cursor.to_list(length=None)
    real_docs, dummy_count = partition_users_for_admin(all_docs)
    users_by_business_id = build_users_by_business_id(all_docs)
    users = [
        AdminUserOut(**user_doc_to_admin_fields(d, tenant_map, users_by_business_id))
        for d in real_docs
    ]
    opts = build_filter_options([u.model_dump() for u in users])
    return AdminUsersListResponse(
        users=users,
        filterOptions=AdminUserFilterOptions(**opts),
        total=len(users),
        totalInDatabase=len(all_docs),
        dummyUserCount=dummy_count,
    )


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    request: Request,
    _admin: dict = Depends(require_permission("users:write")),
):
    db = get_db()
    tenant_map = await get_tenant_map()
    scoped_tid = resolve_admin_tenant_id(request, _admin)
    email = body.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    now = datetime.now(timezone.utc)
    doc = {
        "email": email,
        "password": hash_password(body.password),
        "enzoRole": body.role,
        "tenantId": body.tenantId or scoped_tid,
        "isDeleted": False,
        "basicDetails": {
            "firstName": body.firstName,
            "lastName": body.lastName,
            "emailId": email,
        },
        "demographicDetails": {
            "department": body.department,
            "designation": body.designation,
            "location": "Not Specified",
        },
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        result = await db.users.insert_one(doc)
        doc["_id"] = result.inserted_id
    except PyMongoError as e:
        raise _write_error(e) from e
    users_by_business_id: dict[str, dict] = {}
    bid = get_employee_user_id(doc)
    if bid:
        users_by_business_id[bid] = doc
    return _user_doc_to_admin_out(doc, tenant_map, users_by_business_id)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    request: Request,
    _admin: dict = Depends(require_permission("users:write")),
):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id")
    db = get_db()
    tenant_map = await get_tenant_map()
    doc = await db.users.find_one({"_id": ObjectId(user_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")

    update: dict = {"updatedAt": datetime.now(timezone.utc)}
    if body.role is not None:
        update["enzoRole"] = body.role
    if body.tenantId is not None:
        update["tenantId"] = body.tenantId
    if body.password:
        update["password"] = hash_password(body.password)
    if body.firstName is not None:
        update["basicDetails.firstName"] = body.firstName
    if body.lastName is not None:
        update["basicDetails.lastName"] = body.lastName
    if body.department is not None:
        update["demographicDetails.department"] = body.department
    if body.designation is not None:
        update["demographicDetails.designation"] = body.designation
    if body.adminRole is not None:
        if get_admin_role(_admin) != "super_admin":
            raise HTTPException(status_code=403, detail="Only super_admin can assign admin roles")
        update["adminRole"] = body.adminRole or None
    if body.adminTenantIds is not None:
        if get_admin_role(_admin) != "super_admin":
            raise HTTPException(status_code=403, detail="Only super_admin can assign admin tenants")
        update["adminTenantIds"] = body.adminTenantIds

    try:
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update})
    except PyMongoError as e:
        raise _write_error(e) from e

    doc = await db.users.find_one({"_id": ObjectId(user_id)})
    all_docs = await load_active_user_docs(db)
    users_by_business_id = build_users_by_business_id(all_docs)
    return _user_doc_to_admin_out(doc, tenant_map, users_by_business_id)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    _admin: dict = Depends(require_permission("users:write")),
):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id")
    db = get_db()
    try:
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"isDeleted": True, "updatedAt": datetime.now(timezone.utc)}},
        )
    except PyMongoError as e:
        raise _write_error(e) from e
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    from app.services.auth_tokens import revoke_all_refresh_tokens

    await revoke_all_refresh_tokens(ObjectId(user_id))
    return {"message": "User deleted"}


@router.get("/config", response_model=PlatformConfigOut)
async def get_config(
    request: Request,
    _admin: dict = Depends(require_permission("config:write")),
):
    tenant_id = resolve_admin_tenant_id(request, _admin)
    cfg = await get_platform_config(tenant_id)
    return _config_to_out(cfg)


@router.put("/config", response_model=PlatformConfigOut)
async def put_config(
    body: PlatformConfigUpdate,
    request: Request,
    _admin: dict = Depends(require_permission("config:write")),
):
    tenant_id = resolve_admin_tenant_id(request, _admin)
    patch = body.model_dump(exclude_none=True)
    try:
        cfg = await update_platform_config(tenant_id, patch)
    except PyMongoError as e:
        raise _write_error(e) from e
    return _config_to_out(cfg)


@router.get("/kb", response_model=list[KbDocumentOut])
async def list_kb(
    request: Request,
    _admin: dict = Depends(require_permission("kb:write")),
):
    db = get_db()
    tenant_id = resolve_admin_tenant_id(request, _admin)
    docs = await db.kb_documents.find({"tenantId": tenant_id}).sort("uploadedAt", -1).to_list(200)
    out = []
    for d in docs:
        uploaded = d.get("uploadedAt")
        out.append(
            KbDocumentOut(
                id=str(d["_id"]),
                name=d.get("name", ""),
                size=_format_size(d.get("sizeBytes", 0)),
                status=d.get("status", "pending"),
                uploadedAt=uploaded.strftime("%Y-%m-%d") if uploaded else "",
            )
        )
    return out


@router.post("/kb/upload", response_model=KbDocumentOut)
async def upload_kb(
    request: Request,
    file: UploadFile = File(...),
    _admin: dict = Depends(require_permission("kb:write")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt", ".json"):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    content = await file.read()
    max_bytes = settings.admin_max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.admin_max_upload_mb}MB limit")

    tenant_id = resolve_admin_tenant_id(request, _admin)
    try:
        text = extract_text_from_bytes(content, file.filename)
        doc_id = await save_kb_document(
            tenant_id=tenant_id,
            name=file.filename,
            size_bytes=len(content),
            file_bytes=content,
            extracted_text=text,
            uploaded_by=_admin["_id"],
        )
    except (PyMongoError, ValueError, RuntimeError) as e:
        if isinstance(e, PyMongoError):
            raise _write_error(e) from e
        raise HTTPException(status_code=400, detail=str(e)) from e

    return KbDocumentOut(
        id=doc_id,
        name=file.filename,
        size=_format_size(len(content)),
        status="indexed",
        uploadedAt=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )


@router.delete("/kb/{doc_id}")
async def remove_kb(
    doc_id: str,
    request: Request,
    _admin: dict = Depends(require_permission("kb:write")),
):
    tenant_id = resolve_admin_tenant_id(request, _admin)
    try:
        ok = await delete_kb_document(doc_id, tenant_id=tenant_id)
    except PyMongoError as e:
        raise _write_error(e) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document removed"}


@router.get("/conversations", response_model=list[AdminConversationSummary])
async def list_conversations(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _admin: dict = Depends(require_permission("audit:read")),
):
    db = get_db()
    conv_filter = await conversation_filter_for_tenant(
        tenant_filter_for_user(_admin, request)
    )
    cursor = db.conversations.find(conv_filter).sort("updatedAt", -1).skip(skip).limit(limit)
    convs = await cursor.to_list(limit)
    email_cache: dict[str, str] = {}
    summaries = []
    for conv in convs:
        uid = conv.get("userId")
        uid_str = str(uid)
        if uid_str not in email_cache:
            user = await db.users.find_one({"_id": uid})
            email_cache[uid_str] = user.get("email", "unknown") if user else "unknown"
        summaries.append(
            AdminConversationSummary(
                id=conv["_id"],
                userEmail=email_cache[uid_str],
                title=conv.get("title", ""),
                messageCount=len(conv.get("messages", [])),
                updatedAt=conv.get("updatedAt", datetime.now(timezone.utc)),
            )
        )
    return summaries


@router.get("/conversations/{conversation_id}")
async def get_conversation_detail(
    conversation_id: str,
    _admin: dict = Depends(require_permission("audit:read")),
):
    conv = await conv_store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db = get_db()
    user = await db.users.find_one({"_id": conv.get("userId")})
    return {
        "id": conversation_id,
        "userEmail": user.get("email", "") if user else "",
        "title": conv.get("title", ""),
        "messages": conv.get("messages", []),
        "createdAt": conv.get("createdAt"),
        "updatedAt": conv.get("updatedAt"),
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_admin(
    conversation_id: str,
    _admin: dict = Depends(require_permission("audit:delete")),
):
    deleted = await conv_store.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"message": "Conversation deleted"}


@router.get("/tasks")
async def list_admin_tasks(
    user_id: str | None = Query(None),
    status: str | None = Query(None),
    priority: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    _admin: dict = Depends(require_permission("users:read")),
):
    db = get_db()
    query: dict = {"isDeleted": {"$ne": True}}
    if user_id and ObjectId.is_valid(user_id):
        query["userId"] = ObjectId(user_id)
    if status:
        query["status"] = status
    if priority:
        if priority in ("high", "critical"):
            query["bookmarked"] = True
        elif priority in ("medium", "low"):
            query["bookmarked"] = {"$ne": True}

    total = await db.insightactions.count_documents(query)
    cursor = db.insightactions.find(query).sort("createdAt", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)

    email_cache: dict[str, str] = {}
    tasks_out = []
    for d in docs:
        uid = d.get("userId")
        uid_str = str(uid)
        if uid_str not in email_cache:
            user = await db.users.find_one({"_id": uid})
            email_cache[uid_str] = user.get("email", "") if user else ""
        task = _doc_to_task(d)
        tasks_out.append(
            AdminTaskOut(
                id=task.id,
                userId=task.userId,
                userEmail=email_cache[uid_str],
                title=task.title,
                description=task.description,
                status=task.status,
                priority=task.priority,
                dueDate=task.dueDate,
                createdAt=task.createdAt,
            )
        )
    return {"tasks": tasks_out, "total": total}
