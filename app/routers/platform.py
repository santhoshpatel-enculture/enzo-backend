"""Public platform settings for client apps (no secrets)."""

from fastapi import APIRouter

from app.models.platform import PublicAIConfig
from app.services.model_registry import (
    model_label,
    provider_configured,
    resolve_model_route,
)
from app.services.platform_config import get_platform_config

router = APIRouter(prefix="/platform", tags=["Platform"])


@router.get("/ai", response_model=PublicAIConfig)
async def get_public_ai_config():
    """Active primary/fallback models — used by employee and admin frontends."""
    cfg = await get_platform_config()
    primary, fallback = resolve_model_route(cfg)
    updated = cfg.get("updatedAt")
    return PublicAIConfig(
        primaryModel=primary,
        primaryLabel=model_label(primary),
        fallbackModel=fallback,
        fallbackLabel=model_label(fallback),
        streamingEnabled=bool(cfg.get("streaming_enabled", True)),
        groqConfigured=provider_configured("groq"),
        openaiConfigured=provider_configured("openai"),
        updatedAt=updated.isoformat() if hasattr(updated, "isoformat") else None,
    )
