from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # App
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")
    CONCURRENCY_LIMIT: int = Field(default=3)
    DEFAULT_SCRAPE_DELAY_SECONDS: float = Field(default=1.5)

    # Database
    DATABASE_URL: str = Field(default=f"sqlite+aiosqlite:///{BASE_DIR}/data/apex_prices.db")

    # Telegram Alerting
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_CHAT_ID: str = Field(default="")
    TELEGRAM_ENABLED: bool = Field(default=False)

    # Price Rules
    MIN_DISCOUNT_PERCENT_ALERT: float = Field(default=10.0)
    HISTORICAL_WINDOW_DAYS: int = Field(default=30)

    # Directories
    DATA_DIR: Path = Field(default=BASE_DIR / "data")
    REPORTS_DIR: Path = Field(default=BASE_DIR / "reports")

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return settings
