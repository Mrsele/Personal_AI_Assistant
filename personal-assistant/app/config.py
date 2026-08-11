from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str

    # OpenAI / Compatible API (DeepSeek, OpenRouter, Groq, etc.)
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_base_url: Optional[str] = None

    # Database
    database_url: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # App
    secret_key: str
    base_url: str = "http://localhost:8000"
    webhook_url: Optional[str] = None  # If set, use webhook; else polling
    log_level: str = "INFO"

    # Conversation history kept per user
    max_conversation_turns: int = 20

    # Optional DB config for Docker
    postgres_password: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
