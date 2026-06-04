"""Read/write canonical prompt markdown files for admin editing."""

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = _BACKEND_ROOT / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.md"
KNOWLEDGE_BASE_PATH = PROMPTS_DIR / "knowledge_base.md"

_FALLBACK_SYSTEM = (
    "You are Enzo, a helpful employee assistant for Enculture. "
    "Answer user questions clearly and concisely."
)
_FALLBACK_KB = ""


def ensure_prompt_files() -> None:
    """Create prompts directory and default files if missing."""
    # Vercel bundles prompts/ read-only; avoid writes to the deployment filesystem.
    if os.getenv("VERCEL"):
        return

    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    if not SYSTEM_PROMPT_PATH.exists():
        SYSTEM_PROMPT_PATH.write_text(_FALLBACK_SYSTEM, encoding="utf-8")
    if not KNOWLEDGE_BASE_PATH.exists():
        KNOWLEDGE_BASE_PATH.write_text(_FALLBACK_KB, encoding="utf-8")


def read_system_prompt_file() -> str:
    ensure_prompt_files()
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK_SYSTEM


def read_knowledge_base_file() -> str:
    ensure_prompt_files()
    try:
        return KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK_KB


def write_system_prompt_file(content: str) -> None:
    ensure_prompt_files()
    SYSTEM_PROMPT_PATH.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_knowledge_base_file(content: str) -> None:
    ensure_prompt_files()
    KNOWLEDGE_BASE_PATH.write_text(content.rstrip() + "\n", encoding="utf-8")


def prompt_file_meta() -> dict:
    return {
        "system_prompt_file": "prompts/system_prompt.md",
        "knowledge_base_file": "prompts/knowledge_base.md",
    }
