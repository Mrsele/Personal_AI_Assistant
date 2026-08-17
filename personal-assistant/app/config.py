import os
from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str

    # OpenAI / Compatible API (DeepSeek, OpenRouter, Groq, etc.)
    openai_api_key: str
    openai_model: str = "openai/gpt-oss-120b"
    openai_base_url: Optional[str] = None

    # Database
    database_url: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: Optional[str] = None

    # App
    secret_key: str = "supersecretkey123"
    base_url: str = "http://localhost:8000"
    webhook_url: Optional[str] = None  # If set, use webhook; else polling
    log_level: str = "INFO"

    # Conversation history kept per user
    max_conversation_turns: int = 20

    # Optional DB config for Docker
    postgres_password: Optional[str] = None

    @model_validator(mode="after")
    def resolve_render_urls(self):
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if render_url:
            render_url = render_url.rstrip("/")
            if not self.base_url or "localhost" in self.base_url:
                self.base_url = render_url
            if not self.google_redirect_uri or "localhost" in self.google_redirect_uri:
                self.google_redirect_uri = f"{render_url}/auth/google/callback"
        elif not self.google_redirect_uri:
            self.google_redirect_uri = f"{self.base_url.rstrip('/')}/auth/google/callback"
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
