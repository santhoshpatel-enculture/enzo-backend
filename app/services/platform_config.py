"""Platform configuration per tenant, stored in MongoDB."""

from datetime import datetime, timezone

from app.config import settings
from app.database import get_db
from app.services.model_registry import (
    DEFAULT_FALLBACK_MODEL_ID,
    default_primary_model_id,
    resolve_model_route,
)
from app.services.prompt_files import (
    ensure_prompt_files,
    read_knowledge_base_file,
    read_system_prompt_file,
)

DEFAULT_CONFIG_ID = "default"

DEFAULT_CONFIG = {
    "groq_model": settings.groq_model,
    "primary_model": default_primary_model_id(),
    "fallback_model": DEFAULT_FALLBACK_MODEL_ID,
    "temperature": 0.7,
    "system_prompt": "",
    "streaming_enabled": True,
    "rate_limit_qpm": 60,
    "extra_knowledge": "",
    "knowledge_base_markdown": "",
    "cost_per_1m_input_tokens": 0.05,
    "cost_per_1m_output_tokens": 0.08,
    "blocked_topics": [],
}


def _defaults_from_files() -> dict:
    ensure_prompt_files()
    return {
        **DEFAULT_CONFIG,
        "system_prompt": read_system_prompt_file(),
        "knowledge_base_markdown": read_knowledge_base_file(),
        "extra_knowledge": read_knowledge_base_file(),
    }


async def seed_platform_config_from_files() -> None:
    """Persist file defaults into MongoDB when default config is missing."""
    db = get_db()
    doc = await db.platform_config.find_one({"_id": DEFAULT_CONFIG_ID})
    file_defaults = _defaults_from_files()
    if not doc:
        await db.platform_config.insert_one(
            {"_id": DEFAULT_CONFIG_ID, **file_defaults, "updatedAt": datetime.now(timezone.utc)}
        )
        return

    patch: dict = {}
    if not (doc.get("system_prompt") or "").strip():
        patch["system_prompt"] = file_defaults["system_prompt"]
    if not (doc.get("extra_knowledge") or "").strip():
        patch["extra_knowledge"] = file_defaults["extra_knowledge"]
    if not (doc.get("knowledge_base_markdown") or "").strip():
        patch["knowledge_base_markdown"] = file_defaults["knowledge_base_markdown"]
    if patch:
        patch["updatedAt"] = datetime.now(timezone.utc)
        await db.platform_config.update_one({"_id": DEFAULT_CONFIG_ID}, {"$set": patch})


async def seed_tenant_configs() -> None:
    """Copy default config to each seeded tenant if missing."""
    from app.services.tenants import DEFAULT_TENANTS, ensure_tenants_seeded

    await ensure_tenants_seeded()
    db = get_db()
    default_doc = await db.platform_config.find_one({"_id": DEFAULT_CONFIG_ID})
    base = {**DEFAULT_CONFIG, **(default_doc or {})}
    for t in DEFAULT_TENANTS:
        tid = t["_id"]
        if tid == DEFAULT_CONFIG_ID:
            continue
        existing = await db.platform_config.find_one({"_id": tid})
        if not existing:
            await db.platform_config.insert_one(
                {
                    "_id": tid,
                    **{k: base.get(k, v) for k, v in DEFAULT_CONFIG.items()},
                    "updatedAt": datetime.now(timezone.utc),
                }
            )


async def get_platform_config(tenant_id: str = DEFAULT_CONFIG_ID) -> dict:
    ensure_prompt_files()
    await seed_platform_config_from_files()
    db = get_db()
    file_defaults = _defaults_from_files()

    default_doc = await db.platform_config.find_one({"_id": DEFAULT_CONFIG_ID})
    default_merged = {**file_defaults, **(default_doc or {})}

    if tenant_id == DEFAULT_CONFIG_ID:
        merged = default_merged
    else:
        tenant_doc = await db.platform_config.find_one({"_id": tenant_id})
        merged = {**default_merged, **(tenant_doc or {})}

    if not (merged.get("system_prompt") or "").strip():
        merged["system_prompt"] = file_defaults["system_prompt"]
    if not (merged.get("extra_knowledge") or "").strip():
        merged["extra_knowledge"] = file_defaults.get("extra_knowledge", "")
    if not merged.get("groq_model"):
        merged["groq_model"] = settings.groq_model

    primary, fallback = resolve_model_route(merged)
    merged["primary_model"] = primary
    merged["fallback_model"] = fallback
    _, primary_name = primary.split(":", 1) if ":" in primary else ("groq", primary)
    if primary.startswith("groq:"):
        merged["groq_model"] = primary_name
    merged["knowledge_base"] = merged.get("knowledge_base_markdown") or merged.get(
        "extra_knowledge", ""
    )
    merged["tenant_id"] = tenant_id
    return merged


async def update_platform_config(tenant_id: str, patch: dict) -> dict:
    db = get_db()
    allowed = {
        "groq_model",
        "primary_model",
        "fallback_model",
        "temperature",
        "system_prompt",
        "streaming_enabled",
        "rate_limit_qpm",
        "extra_knowledge",
        "knowledge_base_markdown",
        "cost_per_1m_input_tokens",
        "cost_per_1m_output_tokens",
        "blocked_topics",
    }
    if "knowledge_base" in patch:
        patch["knowledge_base_markdown"] = patch.pop("knowledge_base")
        patch["extra_knowledge"] = patch["knowledge_base_markdown"]

    update = {k: v for k, v in patch.items() if k in allowed}
    if "primary_model" in update and update["primary_model"]:
        pid = str(update["primary_model"])
        if pid.startswith("groq:"):
            update["groq_model"] = pid.split(":", 1)[1]
    if "groq_model" in update and "primary_model" not in update:
        update["primary_model"] = f"groq:{update['groq_model']}"

    update["updatedAt"] = datetime.now(timezone.utc)
    await db.platform_config.update_one(
        {"_id": tenant_id},
        {"$set": update},
        upsert=True,
    )
    cfg = await get_platform_config(tenant_id)
    if "knowledge_base_markdown" in patch or "extra_knowledge" in patch:
        from app.services.kb_indexer import rebuild_extra_knowledge

        await rebuild_extra_knowledge(tenant_id)
        cfg = await get_platform_config(tenant_id)
    return cfg
