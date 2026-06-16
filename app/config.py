from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./waitlist.db"
    MAX_WAITLIST_PER_STUDENT: int = 5
    NOTIFICATION_TIMEOUT_MINUTES: int = 30
    API_V1_PREFIX: str = "/api/v1"


settings = Settings()
