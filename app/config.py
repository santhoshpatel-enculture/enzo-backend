"""Enzo backend configuration — loads secrets from environment variables.

Security notes:
- JWT_SECRET_KEY MUST be set via environment or jwt_secret.txt.
  A random ephemeral fallback is generated ONLY for non-production local dev
  and a severe warning is logged. Never hardcode secrets.
- GROQ_API_KEY must be set for AI features to work.
"""

import os
import secrets
import logging
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import field_validator

logger = logging.getLogger("enzo.config")


def _resolve_jwt_secret() -> str:
    """Resolve JWT secret: env → file → ephemeral (dev only)."""
    from_env = os.getenv("JWT_SECRET_KEY", "").strip()
    if from_env:
        return from_env

    secret_file = Path("jwt_secret.txt")
    if secret_file.exists():
        content = secret_file.read_text().strip()
        if content:
            return content

    # Production without a secret: allow the app to boot (e.g. Vercel health checks)
    # but auth routes will fail until JWT_SECRET_KEY is set in the dashboard.
    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env in ("production", "prod"):
        logger.critical(
            "JWT_SECRET_KEY is not set. Set it in Vercel Environment Variables. "
            "Authentication endpoints will not work until configured."
        )
        return ""

    ephemeral = secrets.token_hex(32)
    logger.warning(
        "JWT_SECRET_KEY not configured. Generated ephemeral secret. "
        "This is instance-isolated and NOT suitable for production or "
        "horizontal scaling. Set JWT_SECRET_KEY in your environment."
    )
    return ephemeral


class Settings(BaseSettings):
    # MongoDB
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db_name: str = "enzo_db"

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # legacy; use jwt_access_expiration_minutes
    jwt_access_expiration_minutes: int = 15
    jwt_refresh_expiration_days: int = 7
    refresh_cookie_name: str = "enzo_refresh_token"
    refresh_cookie_secure: bool = False
    refresh_cookie_domain: str = ""

    # Microsoft Entra OIDC (optional)
    oidc_microsoft_client_id: str = ""
    oidc_microsoft_client_secret: str = ""
    oidc_microsoft_tenant_id: str = "common"
    oidc_microsoft_redirect_uri: str = ""
    frontend_url: str = "http://localhost:5173"
    admin_frontend_url: str = "http://localhost:5174"

    # Groq LLM
    groq_api_key: str = ""
    groq_model: str = "llama3-8b-8192"

    # OpenAI LLM (fallback provider)
    openai_api_key: str = ""

    # Application
    app_env: str = "development"
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175,"
        "https://enzo-enculture.vercel.app,"
        "https://enzo-admin.vercel.app"
    )

    # Admin console
    admin_emails: str = "admin@enculture.ai,santhosh@enculture.ai"
    admin_upload_dir: str = ""
    admin_max_upload_mb: int = 10
    admin_users_list_limit: int = 0  # 0 = no cap (load all active users)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.jwt_secret_key:
            self.jwt_secret_key = _resolve_jwt_secret()
        if not self.admin_upload_dir:
            self.admin_upload_dir = (
                "/tmp/enzo-kb" if os.getenv("VERCEL") else "uploads/kb"
            )

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        if v not in allowed:
            raise ValueError(f"jwt_algorithm must be one of {allowed}")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    @property
    def jwt_configured(self) -> bool:
        return bool(self.jwt_secret_key.strip())


settings = Settings()
