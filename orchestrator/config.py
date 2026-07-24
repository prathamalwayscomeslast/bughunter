from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    webhook_secret: str
    github_app_id: str
    github_private_key_path: str
    github_webhook_enabled: bool = True
    database_url: str
    redis_url: str


# Module-level singleton — imported by the rest of the codebase.
# If any required env var is missing, this raises a ValidationError at startup
# (fast-fail) rather than silently returning None somewhere deep in a call.
settings = Settings()

# Convenience aliases so existing import sites (config.REDIS_URL, etc.) keep working.
WEBHOOK_SECRET = settings.webhook_secret
GITHUB_APP_ID = settings.github_app_id
GITHUB_PRIVATE_KEY_PATH = settings.github_private_key_path
DATABASE_URL = settings.database_url
REDIS_URL = settings.redis_url
