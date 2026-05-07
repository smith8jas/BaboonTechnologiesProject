from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    app_name: str = "Baboon Technologies API"
    environment: str = "development"
    edgar_user_agent: str
    fred_api_key: str
    openai_api_key: str

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8"
    )

settings = Settings()
