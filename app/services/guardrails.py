"""LLM input/output guardrails."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from bson import ObjectId

from app.database import get_db

MAX_USER_MESSAGE_LENGTH = 4000

INPUT_BLOCK_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
        r"disregard\s+(your\s+)?(system\s+)?prompt",
        r"reveal\s+(the\s+)?(system\s+)?prompt",
        r"jailbreak",
        r"bypass\s+(safety|guardrails?)",
    ]
]

PROGRAM_EXFIL_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"(survey|program)\s+answers?\s+for\s+",
        r"show\s+me\s+.+('s|s)\s+(survey|program)\s+response",
        r"individual\s+(survey|program)\s+response",
        r"other\s+employee'?s?\s+feedback",
    ]
]

OUTPUT_BLOCK_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"sk-[a-zA-Z0-9]{20,}",
        r"api[_-]?key\s*[:=]",
        r"here\s+are\s+.+'s\s+(survey|program)\s+answers?",
    ]
]

SAFE_OUTPUT_MESSAGE = (
    "I can't share that information. Program responses are confidential at the "
    "individual level. I can help with your enrollment status or aggregated team insights."
)


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str = ""
    safe_message: str = SAFE_OUTPUT_MESSAGE


def check_user_input(
    message: str,
    *,
    tenant_id: str = "enculture",
    blocked_topics: list[str] | None = None,
) -> GuardrailResult:
    text = (message or "").strip()
    if not text:
        return GuardrailResult(False, "Message cannot be empty")
    if len(text) > MAX_USER_MESSAGE_LENGTH:
        return GuardrailResult(
            False,
            f"Message exceeds maximum length of {MAX_USER_MESSAGE_LENGTH} characters",
        )
    for pat in INPUT_BLOCK_PATTERNS:
        if pat.search(text):
            return GuardrailResult(False, "Message blocked by safety policy")
    for pat in PROGRAM_EXFIL_PATTERNS:
        if pat.search(text):
            return GuardrailResult(
                False,
                "Individual program responses cannot be accessed or shared",
            )
    for topic in blocked_topics or []:
        if topic and topic.lower() in text.lower():
            return GuardrailResult(False, f"Topic not permitted: {topic}")
    return GuardrailResult(True)


def check_assistant_output(content: str) -> GuardrailResult:
    text = content or ""
    for pat in OUTPUT_BLOCK_PATTERNS:
        if pat.search(text):
            return GuardrailResult(False, "Output blocked by safety policy", SAFE_OUTPUT_MESSAGE)
    return GuardrailResult(True)


async def log_guardrail_event(
    *,
    tenant_id: str,
    user_id: ObjectId,
    direction: str,
    reason: str,
    conversation_id: str | None = None,
) -> None:
    db = get_db()
    await db.guardrail_events.insert_one(
        {
            "tenantId": tenant_id,
            "userId": user_id,
            "conversationId": conversation_id,
            "direction": direction,
            "reason": reason,
            "createdAt": datetime.now(timezone.utc),
        }
    )
