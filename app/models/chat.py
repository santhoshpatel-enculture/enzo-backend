"""Chat history Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single message in a conversation."""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str
    timestamp: datetime | None = None


class ChatRequest(BaseModel):
    """Incoming chat message from the user."""
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None


class ChatFeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    rating: str = Field(..., pattern="^(up|down)$")
    comment: str | None = Field(None, max_length=500)


class ChatResponse(BaseModel):
    """Non-streaming chat response."""
    reply: str
    conversation_id: str


class ConversationSummary(BaseModel):
    """Summary of a conversation for the history sidebar."""
    id: str
    title: str
    lastMessage: str
    updatedAt: datetime
    messageCount: int
