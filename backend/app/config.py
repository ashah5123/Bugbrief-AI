from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / 'backend' / '.env', extra='ignore')
    database_url: str = f"sqlite:///{ROOT / 'data' / 'bugbrief.db'}"
    attachments_dir: Path = ROOT / 'data' / 'attachments'
    agency_access_code: str = ''
    agency_code_path: Path = ROOT / 'data' / 'agency-access.txt'
    public_ai_daily_limit: int = Field(default=6, ge=1, le=20)
    public_submissions_daily_limit: int = Field(default=10, ge=1, le=100)
    gemini_api_key: str = ''
    free_tier_confirmed: bool = False
    gemini_model: str = 'gemini-3.5-flash-lite'
    ai_daily_limit: int = Field(default=20, ge=1, le=100)
    ai_timeout_seconds: int = Field(default=45, ge=1, le=90)

settings = Settings()
