"""LLM model catalog and platform routing (primary / fallback)."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class ModelOption:
    id: str
    provider: str
    model: str
    label: str


MODEL_CATALOG: list[ModelOption] = [
    ModelOption("groq:llama3-8b-8192", "groq", "llama3-8b-8192", "Groq · Llama 3 8B"),
    ModelOption("groq:llama-3.1-8b-instant", "groq", "llama-3.1-8b-instant", "Groq · Llama 3.1 8B Instant"),
    ModelOption("groq:llama-3.3-70b-versatile", "groq", "llama-3.3-70b-versatile", "Groq · Llama 3.3 70B"),
    ModelOption("groq:mixtral-8x7b-32768", "groq", "mixtral-8x7b-32768", "Groq · Mixtral 8x7B"),
    ModelOption("openai:gpt-4o-mini", "openai", "gpt-4o-mini", "OpenAI · GPT-4o mini"),
]

CATALOG_BY_ID: dict[str, ModelOption] = {m.id: m for m in MODEL_CATALOG}

DEFAULT_FALLBACK_MODEL_ID = "openai:gpt-4o-mini"


def default_primary_model_id() -> str:
    return f"groq:{settings.groq_model}"


def normalize_model_id(model_id: str | None, *, default: str) -> str:
    if not model_id or not str(model_id).strip():
        return default
    raw = str(model_id).strip()
    if raw in CATALOG_BY_ID:
        return raw
    if ":" not in raw:
        guess = f"groq:{raw}"
        if guess in CATALOG_BY_ID:
            return guess
    return default


def resolve_model_route(cfg: dict) -> tuple[str, str]:
    """Return (primary_model_id, fallback_model_id) from platform config."""
    legacy_groq = cfg.get("groq_model") or settings.groq_model
    if cfg.get("primary_model"):
        primary = normalize_model_id(cfg["primary_model"], default=default_primary_model_id())
    else:
        primary = normalize_model_id(f"groq:{legacy_groq}", default=default_primary_model_id())

    fallback = normalize_model_id(
        cfg.get("fallback_model"),
        default=DEFAULT_FALLBACK_MODEL_ID,
    )
    if primary == fallback:
        fallback = (
            DEFAULT_FALLBACK_MODEL_ID
            if primary != DEFAULT_FALLBACK_MODEL_ID
            else default_primary_model_id()
        )
    return primary, fallback


def parse_model_id(model_id: str) -> tuple[str, str]:
    opt = CATALOG_BY_ID.get(model_id)
    if opt:
        return opt.provider, opt.model
    if ":" in model_id:
        provider, name = model_id.split(":", 1)
        return provider.lower(), name
    return "groq", model_id


def model_label(model_id: str) -> str:
    opt = CATALOG_BY_ID.get(model_id)
    if opt:
        return opt.label
    provider, name = parse_model_id(model_id)
    return f"{provider.title()} · {name}"


def catalog_for_api() -> list[dict]:
    return [
        {"id": m.id, "provider": m.provider, "model": m.model, "label": m.label}
        for m in MODEL_CATALOG
    ]


def provider_configured(provider: str) -> bool:
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "openai":
        return bool(settings.openai_api_key)
    return False
