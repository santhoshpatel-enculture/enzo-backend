"""Public platform AI configuration (no secrets)."""

from pydantic import BaseModel


class ModelOptionOut(BaseModel):
    id: str
    provider: str
    model: str
    label: str


class PublicAIConfig(BaseModel):
    primaryModel: str
    primaryLabel: str
    fallbackModel: str
    fallbackLabel: str
    streamingEnabled: bool
    groqConfigured: bool
    openaiConfigured: bool
    updatedAt: str | None = None
