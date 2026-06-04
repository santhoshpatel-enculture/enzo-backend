"""User settings Pydantic schemas."""

from pydantic import BaseModel


class UserSettings(BaseModel):
    """User preference settings."""
    theme: str = "dark"
    language: str = "en"
    notifications_enabled: bool = True
    ai_suggestions_enabled: bool = True
    compact_mode: bool = False
