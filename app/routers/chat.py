"""Chat routes — MongoDB-backed conversations with streaming responses."""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.database import get_db
from app.deps import get_current_user
from app.models.chat import ChatFeedbackRequest, ChatRequest, ConversationSummary
from app.services.prompt_manager import build_enzo_system_prompt, build_conversation_messages
from app.services.llm import chat_completion_with_fallback
from app.services.model_registry import resolve_model_route
from app.services.platform_config import get_platform_config
from app.services import conversation_store as conv_store
from app.services.usage_telemetry import record_usage_event
from app.services.guardrails import (
    check_assistant_output,
    check_user_input,
    log_guardrail_event,
)
from app.services.tenant_budget import assert_within_budget

logger = logging.getLogger("enzo.chat")
router = APIRouter(prefix="/chat", tags=["Chat"])


async def _load_user_context(user_doc: dict) -> tuple[dict, list[dict]]:
    db = get_db()
    user_id = user_doc["_id"]

    basic = user_doc.get("basicDetails", {})
    demographics = user_doc.get("demographicDetails", {})

    first_name = basic.get("firstName", "") if isinstance(basic, dict) else ""
    last_name = basic.get("lastName", "") if isinstance(basic, dict) else ""
    dept = demographics.get("department", "Not Specified") if isinstance(demographics, dict) else "Not Specified"
    desg = demographics.get("designation", "Not Specified") if isinstance(demographics, dict) else "Not Specified"
    loc = demographics.get("location", "Not Specified") if isinstance(demographics, dict) else "Not Specified"

    manager = user_doc.get("managerName")
    if not manager:
        m_details = user_doc.get("managerDetails", {})
        if isinstance(m_details, dict):
            manager = (
                m_details.get("name")
                or f"{m_details.get('managerFirstName', '')} {m_details.get('managerLastName', '')}".strip()
                or "Not Specified"
            )
    if not manager:
        manager = "Not Specified"

    profile = {
        "firstName": first_name,
        "lastName": last_name,
        "email": user_doc.get("email", ""),
        "department": dept,
        "designation": desg,
        "manager": manager,
        "location": loc,
    }

    cursor = db.insightactions.find(
        {"userId": ObjectId(user_id), "status": {"$ne": "completed"}, "isDeleted": {"$ne": True}}
    ).sort("createdAt", -1).limit(10)

    task_docs = await cursor.to_list(10)
    tasks = []
    for t in task_docs:
        created = t.get("createdAt")
        due = t.get("dueDate")
        if not due and created:
            due = created + timedelta(days=7)
        tasks.append({
            "title": t.get("title", ""),
            "status": t.get("status", ""),
            "priority": "high" if t.get("bookmarked") else "medium",
            "dueDate": str(due) if due else "No deadline",
        })

    return profile, tasks


@router.post("/message")
async def send_message(
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["_id"]
    tenant_id = current_user.get("tenantId") or "enculture"
    now = datetime.now(timezone.utc)

    platform = await get_platform_config(tenant_id)
    input_check = check_user_input(
        body.message,
        tenant_id=tenant_id,
        blocked_topics=platform.get("blocked_topics"),
    )
    if not input_check.allowed:
        await log_guardrail_event(
            tenant_id=tenant_id,
            user_id=user_id,
            direction="input",
            reason=input_check.reason,
            conversation_id=body.conversation_id,
        )
        raise HTTPException(status_code=400, detail=input_check.reason)

    await assert_within_budget(tenant_id)

    conversation_id = body.conversation_id
    if conversation_id:
        conv = await conv_store.require_owned_conversation(conversation_id, user_id)
        chat_history_messages = conv.get("messages", [])
    else:
        title = body.message[:50].strip() + ("…" if len(body.message) > 50 else "")
        conv = await conv_store.create_conversation(user_id, title)
        conversation_id = conv["_id"]
        chat_history_messages = []

    user_msg = {
        "messageId": conv_store.new_message_id(),
        "role": "user",
        "content": body.message,
        "timestamp": now,
    }
    await conv_store.append_message(conversation_id, user_msg)
    chat_history_messages = chat_history_messages + [user_msg]

    profile, tasks = await _load_user_context(current_user)
    system_prompt = build_enzo_system_prompt(
        user_profile=profile,
        user_tasks=tasks,
        extra_knowledge=platform.get("extra_knowledge", ""),
        custom_instructions=platform.get("system_prompt", ""),
    )
    messages = build_conversation_messages(
        system_prompt, chat_history_messages[:-1], body.message
    )

    temperature = float(platform.get("temperature", 0.7))
    streaming = platform.get("streaming_enabled", True)
    primary_id, fallback_id = resolve_model_route(platform)

    async def _stream():
        full_reply = []
        started = time.perf_counter()
        req_status = "success"
        model_used = primary_id
        used_fallback = False
        guardrail_blocked = False
        try:
            result, model_used, used_fallback = await chat_completion_with_fallback(
                messages,
                primary_model_id=primary_id,
                fallback_model_id=fallback_id,
                stream=streaming,
                max_tokens=500,
                temperature=temperature,
            )
            if streaming:
                async for chunk in result:
                    full_reply.append(chunk)
                    yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"
            else:
                full_reply.append(result)
                yield f"data: {json.dumps(result)}\n\n"
                yield "data: [DONE]\n\n"
        except Exception:
            req_status = "error"
            raise
        finally:
            reply_text = "".join(full_reply)
            output_check = check_assistant_output(reply_text)
            if not output_check.allowed:
                guardrail_blocked = True
                reply_text = output_check.safe_message
                await log_guardrail_event(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    direction="output",
                    reason=output_check.reason,
                    conversation_id=conversation_id,
                )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if reply_text:
                assistant_msg = {
                    "messageId": conv_store.new_message_id(),
                    "role": "assistant",
                    "content": reply_text,
                    "timestamp": datetime.now(timezone.utc),
                }
                await conv_store.append_message(conversation_id, assistant_msg)
            if guardrail_blocked:
                yield f"data: {json.dumps({'guardrail_blocked': True})}\n\n"
            telemetry_model = model_used
            if used_fallback:
                telemetry_model = f"{model_used} (fallback)"
            try:
                await record_usage_event(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    model=telemetry_model,
                    user_message=body.message,
                    assistant_message=reply_text,
                    latency_ms=latency_ms,
                    status=req_status,
                )
            except Exception as exc:
                logger.warning("Failed to record usage telemetry: %s", exc)

    headers = {
        "Cache-Control": "no-cache",
        "X-Conversation-Id": conversation_id,
        "X-Primary-Model": primary_id,
        "X-Fallback-Model": fallback_id,
    }

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/feedback")
async def submit_feedback(
    body: ChatFeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    ok = await conv_store.set_message_feedback(
        body.conversation_id,
        current_user["_id"],
        body.message_id,
        body.rating,
        body.comment,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found or not feedback-eligible")
    return {"message": "Feedback recorded"}


@router.get("/history", response_model=list[ConversationSummary])
async def get_chat_history(current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    convs = await conv_store.list_user_conversations(user_id)

    summaries = []
    for conv in convs:
        msgs = conv.get("messages", [])
        last_msg = msgs[-1]["content"][:80] if msgs else ""
        updated = conv.get("updatedAt", datetime.now(timezone.utc))
        summaries.append(
            ConversationSummary(
                id=conv["_id"],
                title=conv.get("title", ""),
                lastMessage=last_msg,
                updatedAt=updated,
                messageCount=len(msgs),
            )
        )
    return summaries


@router.get("/history/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    conv = await conv_store.require_owned_conversation(
        conversation_id, current_user["_id"]
    )
    return {
        "id": conversation_id,
        "title": conv.get("title", ""),
        "messages": conv.get("messages", []),
        "createdAt": conv.get("createdAt"),
        "updatedAt": conv.get("updatedAt"),
    }


@router.delete("/history/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    await conv_store.require_owned_conversation(conversation_id, current_user["_id"])
    deleted = await conv_store.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {"message": "Conversation deleted"}


@router.delete("/history")
async def clear_all_history(current_user: dict = Depends(get_current_user)):
    count = await conv_store.delete_all_user_conversations(current_user["_id"])
    return {"message": f"Deleted {count} conversation(s)"}
