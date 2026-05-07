from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Baboon Technologies API"
    environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    edgar_user_agent: str
    model_config = {"env_file": ".env"}

settings = Settings()
