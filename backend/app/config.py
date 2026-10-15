from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / 'backend' / '.env', extra='ignore')
    database_url: str = f"sqlite:///{ROOT / 'data' / 'bugbrief.db'}"
    gemini_api_key: str = ''
    free_tier_confirmed: bool = False
    gemini_model: str = 'gemini-3.5-flash-lite'
    ai_daily_limit: int = Field(default=20, ge=1, le=100)
    ai_timeout_seconds: int = Field(default=45, ge=1, le=90)

settings = Settings()
