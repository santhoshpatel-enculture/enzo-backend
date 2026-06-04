"""LLM service — Groq and OpenAI with primary / fallback routing."""

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.config import settings
from app.services.model_registry import (
    parse_model_id,
    provider_configured,
)

logger = logging.getLogger("enzo.llm")

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class LLMProviderError(Exception):
    """Raised when a provider call fails (triggers fallback)."""

    def __init__(self, provider: str, model: str, message: str):
        self.provider = provider
        self.model = model
        super().__init__(message)


def _api_key_for(provider: str) -> str:
    if provider == "groq":
        return settings.groq_api_key
    if provider == "openai":
        return settings.openai_api_key
    return ""


def _chat_url_for(provider: str) -> str:
    if provider == "openai":
        return OPENAI_CHAT_URL
    return GROQ_CHAT_URL


async def _request_chat(
    provider: str,
    model: str,
    messages: list[dict],
    *,
    stream: bool,
    temperature: float,
    max_tokens: int,
) -> str | AsyncGenerator[str, None]:
    api_key = _api_key_for(provider)
    if not api_key:
        raise LLMProviderError(
            provider,
            model,
            f"{provider.upper()} API key is not configured on the server.",
        )

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = _chat_url_for(provider)

    if stream:
        return _stream_response(url, payload, headers, provider, model)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise LLMProviderError(
                provider,
                model,
                f"{provider} API error {resp.status_code}: {resp.text[:500]}",
            )
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _stream_response(
    url: str,
    payload: dict,
    headers: dict,
    provider: str,
    model: str,
) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise LLMProviderError(
                    provider,
                    model,
                    f"{provider} API error {resp.status_code}: {body.decode()[:500]}",
                )
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[len("data: ") :]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def _offline_response(stream: bool) -> str | AsyncGenerator[str, None]:
    msg = (
        "I'm not able to connect to the AI service right now. "
        "Please ask your administrator to configure Groq or OpenAI API keys."
    )
    if stream:

        async def _gen():
            yield msg

        return _gen()
    return msg


async def chat_completion(
    messages: list[dict],
    *,
    model_id: str,
    stream: bool = False,
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> str | AsyncGenerator[str, None]:
    """Call a single model by catalog id (e.g. openai:gpt-4o-mini)."""
    provider, model = parse_model_id(model_id)
    return await _request_chat(
        provider,
        model,
        messages,
        stream=stream,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def chat_completion_with_fallback(
    messages: list[dict],
    *,
    primary_model_id: str,
    fallback_model_id: str,
    stream: bool = False,
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> tuple[str | AsyncGenerator[str, None], str, bool]:
    """
    Try primary model, then fallback.

    Returns (result, model_id_used, used_fallback).
    """
    primary_provider, _ = parse_model_id(primary_model_id)
    fallback_provider, _ = parse_model_id(fallback_model_id)

    if not provider_configured(primary_provider) and not provider_configured(
        fallback_provider
    ):
        result = _offline_response(stream)
        return result, primary_model_id, False

    errors: list[str] = []
    for idx, model_id in enumerate((primary_model_id, fallback_model_id)):
        provider, _ = parse_model_id(model_id)
        if not provider_configured(provider):
            errors.append(f"{provider} not configured")
            continue
        try:
            result = await chat_completion(
                messages,
                model_id=model_id,
                stream=stream,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return result, model_id, idx > 0
        except (LLMProviderError, httpx.HTTPError, KeyError, IndexError) as exc:
            logger.warning("Model %s failed: %s", model_id, exc)
            errors.append(str(exc))
            continue

    detail = "; ".join(errors) or "All models failed"
    raise LLMProviderError("routing", primary_model_id, detail)


# Backward-compatible alias used by older imports
async def chat_completion_legacy(
    messages: list[dict],
    *,
    stream: bool = False,
    temperature: float = 0.7,
    max_tokens: int = 500,
    model: str | None = None,
) -> str | AsyncGenerator[str, None]:
    model_id = f"groq:{model}" if model and ":" not in model else (model or f"groq:{settings.groq_model}")
    return await chat_completion(
        messages,
        model_id=model_id,
        stream=stream,
        temperature=temperature,
        max_tokens=max_tokens,
    )
