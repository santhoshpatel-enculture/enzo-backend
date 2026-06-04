"""Usage telemetry — record LLM usage and aggregate by tenant/user."""

from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.database import get_db
from app.services.platform_config import get_platform_config
from app.services.tenants import get_tenant_map

DEFAULT_INPUT_COST_PER_1M = 0.05
DEFAULT_OUTPUT_COST_PER_1M = 0.08


def estimate_tokens(text: str) -> int:
    return max(0, len(text or "") // 4)


def compute_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    input_per_1m: float,
    output_per_1m: float,
) -> float:
    return (prompt_tokens / 1_000_000 * input_per_1m) + (
        completion_tokens / 1_000_000 * output_per_1m
    )


async def _pricing() -> tuple[float, float]:
    cfg = await get_platform_config()
    return (
        float(cfg.get("cost_per_1m_input_tokens", DEFAULT_INPUT_COST_PER_1M)),
        float(cfg.get("cost_per_1m_output_tokens", DEFAULT_OUTPUT_COST_PER_1M)),
    )


async def record_usage_event(
    *,
    user_id: ObjectId,
    tenant_id: str,
    conversation_id: str,
    model: str,
    user_message: str,
    assistant_message: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    latency_ms: int | None = None,
    status: str = "success",
) -> None:
    db = get_db()
    pt = prompt_tokens if prompt_tokens is not None else estimate_tokens(user_message)
    ct = completion_tokens if completion_tokens is not None else estimate_tokens(assistant_message)
    inp_cost, out_cost = await _pricing()
    cost = compute_cost_usd(pt, ct, inp_cost, out_cost)
    now = datetime.now(timezone.utc)
    await db.usage_events.insert_one(
        {
            "userId": user_id,
            "tenantId": tenant_id or "enculture",
            "conversationId": conversation_id,
            "model": model,
            "userMessages": 1,
            "assistantMessages": 1 if assistant_message else 0,
            "promptTokens": pt,
            "completionTokens": ct,
            "totalTokens": pt + ct,
            "estimatedCostUsd": round(cost, 6),
            "latencyMs": latency_ms,
            "status": status,
            "createdAt": now,
        }
    )


def _parse_range(from_dt: datetime | None, to_dt: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end = to_dt or now
    start = from_dt or (end - timedelta(days=30))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return start, end


def _format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def _format_cost(usd: float) -> str:
    if usd >= 100:
        return f"${usd:.2f}"
    if usd >= 1:
        return f"${usd:.3f}"
    return f"${usd:.4f}"


async def _message_stats_from_conversations(
    start: datetime, end: datetime, tenant_id: str | None = None, user_id: ObjectId | None = None
) -> dict:
    """Fallback aggregation from conversation messages when usage_events sparse."""
    db = get_db()
    user_ids: list[ObjectId] | None = None
    if tenant_id:
        user_docs = await db.users.find(
            {"tenantId": tenant_id, "isDeleted": {"$ne": True}}, {"_id": 1}
        ).to_list(5000)
        user_ids = [u["_id"] for u in user_docs]
    if user_id:
        user_ids = [user_id]

    match: dict = {"updatedAt": {"$gte": start, "$lte": end}}
    if user_ids is not None:
        match["userId"] = {"$in": user_ids}

    user_msgs = 0
    assistant_msgs = 0
    prompt_t = 0
    completion_t = 0
    conversations = 0

    async for conv in db.conversations.find(match, {"messages": 1}):
        conversations += 1
        for msg in conv.get("messages", []):
            role = msg.get("role")
            content = msg.get("content", "")
            ts = msg.get("timestamp")
            if ts:
                try:
                    if isinstance(ts, str):
                        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        parsed = ts
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if parsed < start or parsed > end:
                        continue
                except (ValueError, TypeError):
                    pass
            if role == "user":
                user_msgs += 1
                prompt_t += estimate_tokens(content)
            elif role == "assistant":
                assistant_msgs += 1
                completion_t += estimate_tokens(content)

    inp_cost, out_cost = await _pricing()
    cost = compute_cost_usd(prompt_t, completion_t, inp_cost, out_cost)
    return {
        "userMessages": user_msgs,
        "assistantMessages": assistant_msgs,
        "totalMessages": user_msgs + assistant_msgs,
        "promptTokens": prompt_t,
        "completionTokens": completion_t,
        "totalTokens": prompt_t + completion_t,
        "estimatedCostUsd": cost,
        "conversations": conversations,
    }


async def _aggregate_usage_events(
    start: datetime, end: datetime, group_by: str, tenant_id: str | None = None
) -> list[dict]:
    db = get_db()
    match: dict = {"createdAt": {"$gte": start, "$lte": end}}
    if tenant_id:
        match["tenantId"] = tenant_id

    group_id = f"${group_by}"
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": group_id,
                "userMessages": {"$sum": "$userMessages"},
                "assistantMessages": {"$sum": "$assistantMessages"},
                "promptTokens": {"$sum": "$promptTokens"},
                "completionTokens": {"$sum": "$completionTokens"},
                "totalTokens": {"$sum": "$totalTokens"},
                "estimatedCostUsd": {"$sum": "$estimatedCostUsd"},
                "conversations": {"$addToSet": "$conversationId"},
                "events": {"$sum": 1},
            }
        },
    ]
    results = []
    async for row in db.usage_events.aggregate(pipeline):
        results.append(row)
    return results


async def get_telemetry_summary(
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> dict:
    start, end = _parse_range(from_dt, to_dt)
    db = get_db()
    tenant_map = await get_tenant_map()

    event_count = await db.usage_events.count_documents(
        {"createdAt": {"$gte": start, "$lte": end}}
    )

    if event_count > 0:
        platform = await _aggregate_usage_events(start, end, "tenantId")
        by_tenant = {r["_id"]: r for r in platform}
    else:
        by_tenant = {}

    tenant_rows = []
    total_user_msgs = 0
    total_assistant_msgs = 0
    total_prompt = 0
    total_completion = 0
    total_cost = 0.0

    for tid, name in tenant_map.items():
        if tid in by_tenant:
            r = by_tenant[tid]
            um = int(r.get("userMessages", 0))
            am = int(r.get("assistantMessages", 0))
            pt = int(r.get("promptTokens", 0))
            ct = int(r.get("completionTokens", 0))
            cost = float(r.get("estimatedCostUsd", 0))
            convs = len(r.get("conversations", []))
        else:
            stats = await _message_stats_from_conversations(start, end, tenant_id=tid)
            um = stats["userMessages"]
            am = stats["assistantMessages"]
            pt = stats["promptTokens"]
            ct = stats["completionTokens"]
            cost = stats["estimatedCostUsd"]
            convs = stats["conversations"]

        u_count = await db.users.count_documents(
            {"tenantId": tid, "isDeleted": {"$ne": True}}
        )
        total_user_msgs += um
        total_assistant_msgs += am
        total_prompt += pt
        total_completion += ct
        total_cost += cost

        tenant_rows.append(
            {
                "tenantId": tid,
                "name": name,
                "users": u_count,
                "conversations": convs,
                "userMessages": um,
                "assistantMessages": am,
                "totalMessages": um + am,
                "promptTokens": pt,
                "completionTokens": ct,
                "totalTokens": pt + ct,
                "tokensDisplay": _format_tokens(pt + ct),
                "estimatedCostUsd": round(cost, 4),
                "costDisplay": _format_cost(cost),
            }
        )

    tenant_rows.sort(key=lambda x: x["totalTokens"], reverse=True)
    max_tokens = max((t["totalTokens"] for t in tenant_rows), default=1) or 1
    for t in tenant_rows:
        t["percentage"] = min(100, int((t["totalTokens"] / max_tokens) * 100))

    active_users = await db.usage_events.distinct(
        "userId", {"createdAt": {"$gte": start, "$lte": end}}
    )
    if not active_users:
        active_users = []

    return {
        "periodStart": start.isoformat(),
        "periodEnd": end.isoformat(),
        "totalUserMessages": total_user_msgs,
        "totalAssistantMessages": total_assistant_msgs,
        "totalMessages": total_user_msgs + total_assistant_msgs,
        "promptTokens": total_prompt,
        "completionTokens": total_completion,
        "totalTokens": total_prompt + total_completion,
        "tokensDisplay": _format_tokens(total_prompt + total_completion),
        "estimatedCostUsd": round(total_cost, 4),
        "costDisplay": _format_cost(total_cost),
        "activeUsers": len(active_users),
        "tenantBreakdown": tenant_rows,
    }


async def get_telemetry_users(
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    tenant_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    start, end = _parse_range(from_dt, to_dt)
    db = get_db()
    tenant_map = await get_tenant_map()

    match: dict = {"createdAt": {"$gte": start, "$lte": end}}
    if tenant_id:
        match["tenantId"] = tenant_id

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$userId",
                "tenantId": {"$first": "$tenantId"},
                "userMessages": {"$sum": "$userMessages"},
                "assistantMessages": {"$sum": "$assistantMessages"},
                "promptTokens": {"$sum": "$promptTokens"},
                "completionTokens": {"$sum": "$completionTokens"},
                "totalTokens": {"$sum": "$totalTokens"},
                "estimatedCostUsd": {"$sum": "$estimatedCostUsd"},
                "conversations": {"$addToSet": "$conversationId"},
                "lastAt": {"$max": "$createdAt"},
            }
        },
        {"$sort": {"totalTokens": -1}},
        {"$limit": limit},
    ]

    rows = []
    async for r in db.usage_events.aggregate(pipeline):
        rows.append(r)

    if not rows:
        query = {"isDeleted": {"$ne": True}}
        if tenant_id:
            query["tenantId"] = tenant_id
        users = await db.users.find(query).limit(limit).to_list(limit)
        for u in users:
            stats = await _message_stats_from_conversations(
                start, end, user_id=u["_id"]
            )
            if stats["totalMessages"] == 0:
                continue
            tid = u.get("tenantId") or "enculture"
            rows.append(
                {
                    "_id": u["_id"],
                    "tenantId": tid,
                    **stats,
                    "conversations": stats["conversations"],
                    "lastAt": u.get("updatedAt"),
                }
            )

    out = []
    for r in rows:
        uid = r["_id"]
        user = await db.users.find_one({"_id": uid})
        if not user:
            continue
        tid = r.get("tenantId") or user.get("tenantId") or "enculture"
        pt = int(r.get("promptTokens", 0))
        ct = int(r.get("completionTokens", 0))
        cost = float(r.get("estimatedCostUsd", 0))
        um = int(r.get("userMessages", 0))
        am = int(r.get("assistantMessages", 0))
        convs = r.get("conversations")
        conv_count = len(convs) if isinstance(convs, list) else int(convs or 0)
        last = r.get("lastAt")
        last_active = "—"
        if last:
            delta = datetime.now(timezone.utc) - (
                last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
            )
            if delta.days:
                last_active = f"{delta.days}d ago"
            elif delta.seconds >= 3600:
                last_active = f"{delta.seconds // 3600}h ago"
            else:
                last_active = f"{max(1, delta.seconds // 60)}m ago"

        out.append(
            {
                "userId": str(uid),
                "email": user.get("email", ""),
                "tenantId": tid,
                "tenantName": tenant_map.get(tid, tid),
                "conversations": conv_count,
                "userMessages": um,
                "assistantMessages": am,
                "totalMessages": um + am,
                "promptTokens": pt,
                "completionTokens": ct,
                "totalTokens": pt + ct,
                "tokensDisplay": _format_tokens(pt + ct),
                "estimatedCostUsd": round(cost, 4),
                "costDisplay": _format_cost(cost),
                "lastActive": last_active,
            }
        )
    return out


async def get_telemetry_timeseries(
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    tenant_id: str | None = None,
) -> list[dict]:
    start, end = _parse_range(from_dt, to_dt)
    db = get_db()
    match: dict = {"createdAt": {"$gte": start, "$lte": end}}
    if tenant_id:
        match["tenantId"] = tenant_id

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {
                    "$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"},
                },
                "userMessages": {"$sum": "$userMessages"},
                "assistantMessages": {"$sum": "$assistantMessages"},
                "totalTokens": {"$sum": "$totalTokens"},
                "estimatedCostUsd": {"$sum": "$estimatedCostUsd"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    points = []
    async for row in db.usage_events.aggregate(pipeline):
        points.append(
            {
                "date": row["_id"],
                "userMessages": int(row.get("userMessages", 0)),
                "assistantMessages": int(row.get("assistantMessages", 0)),
                "totalTokens": int(row.get("totalTokens", 0)),
                "estimatedCostUsd": round(float(row.get("estimatedCostUsd", 0)), 4),
            }
        )
    return points


async def get_ops_telemetry() -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)

    errors = await db.usage_events.count_documents(
        {"createdAt": {"$gte": day_ago}, "status": {"$ne": "success"}}
    )
    success = await db.usage_events.count_documents(
        {"createdAt": {"$gte": day_ago}, "status": "success"}
    )
    total_events = errors + success
    error_rate = round((errors / total_events * 100), 1) if total_events else 0.0

    latencies = []
    async for ev in db.usage_events.find(
        {"createdAt": {"$gte": day_ago}, "latencyMs": {"$exists": True}},
        {"latencyMs": 1},
    ).limit(500):
        if ev.get("latencyMs") is not None:
            latencies.append(ev["latencyMs"])

    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

    from app.config import settings

    return {
        "last24hRequests": total_events,
        "errorRatePercent": error_rate,
        "avgLatencyMs": avg_latency,
        "groqConfigured": bool(settings.groq_api_key),
    }
