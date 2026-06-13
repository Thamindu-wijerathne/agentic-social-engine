from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    LOG_LEVEL: str = "INFO"

    # --- Anthropic (Claude) ---
    CLAUDE_API_KEY: str
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    CLAUDE_MODEL_FAST: str = "claude-haiku-4-20250514"

    # --- News API ---
    NEWS_API_KEY: str

    # --- GNews API ---
    GNEWS_API_KEY: str

    # --- Facebook ---
    facebook_app_id: str | None = None
    facebook_app_secret: str | None = None
    facebook_access_token: str | None = None
    facebook_page_id: str | None = None

    # --- Supabase ---
    SUPABASE_URL: str | None = None
    SUPABASE_API_KEY: str | None = None
    SUPABASE_SECRET_KEY: str | None = None

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
    )


settings = Settings()
