from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Baboon Technologies API"
    environment: str = "development"
    edgar_user_agent: str
    fred_api_key: str
    openai_api_key: str
    llm_provider: str
    llm_model: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

settings = Settings()