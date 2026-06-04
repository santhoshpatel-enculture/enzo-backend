"""Per-tenant usage budgets enforced before LLM calls."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.database import get_db

DEFAULT_BUDGETS = {
    "monthlyTokenLimit": 0,
    "monthlyCostUsdLimit": 0.0,
    "alertThresholdPct": 80,
}


async def get_tenant_budgets(tenant_id: str) -> dict:
    db = get_db()
    doc = await db.tenants.find_one({"_id": tenant_id})
    if not doc:
        return dict(DEFAULT_BUDGETS)
    budgets = doc.get("budgets") or {}
    return {**DEFAULT_BUDGETS, **budgets}


async def update_tenant_budgets(tenant_id: str, patch: dict) -> dict:
    db = get_db()
    allowed = {"monthlyTokenLimit", "monthlyCostUsdLimit", "alertThresholdPct"}
    current = await get_tenant_budgets(tenant_id)
    merged = {**current, **{k: v for k, v in patch.items() if k in allowed}}
    await db.tenants.update_one(
        {"_id": tenant_id},
        {
            "$set": {
                "budgets": merged,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    return merged


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def get_period_usage(tenant_id: str, *, now: datetime | None = None) -> dict:
    db = get_db()
    now = now or datetime.now(timezone.utc)
    start = _month_start(now)
    pipeline = [
        {"$match": {"tenantId": tenant_id, "createdAt": {"$gte": start, "$lte": now}}},
        {
            "$group": {
                "_id": None,
                "totalTokens": {"$sum": "$totalTokens"},
                "estimatedCostUsd": {"$sum": "$estimatedCostUsd"},
            }
        },
    ]
    rows = await db.usage_events.aggregate(pipeline).to_list(1)
    if not rows:
        return {"totalTokens": 0, "estimatedCostUsd": 0.0}
    return {
        "totalTokens": int(rows[0].get("totalTokens", 0)),
        "estimatedCostUsd": float(rows[0].get("estimatedCostUsd", 0)),
    }


async def assert_within_budget(
    tenant_id: str,
    *,
    estimated_increment_tokens: int = 500,
) -> dict:
    budgets = await get_tenant_budgets(tenant_id)
    usage = await get_period_usage(tenant_id)

    token_limit = int(budgets.get("monthlyTokenLimit") or 0)
    cost_limit = float(budgets.get("monthlyCostUsdLimit") or 0)

    if token_limit > 0:
        projected = usage["totalTokens"] + estimated_increment_tokens
        if projected > token_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Tenant monthly token budget exceeded ({usage['totalTokens']}/{token_limit}). "
                    "Contact your administrator."
                ),
            )

    if cost_limit > 0 and usage["estimatedCostUsd"] >= cost_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Tenant monthly cost budget exceeded (${usage['estimatedCostUsd']:.2f}/${cost_limit:.2f}). "
                "Contact your administrator."
            ),
        )

    return {"usage": usage, "budgets": budgets}
