from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./waitlist.db"
    MAX_WAITLIST_PER_STUDENT: int = 5
    NOTIFICATION_TIMEOUT_MINUTES: int = 30
    MAX_NOTIFICATION_RETRIES: int = 5
    NOTIFICATION_RETRY_INTERVAL_MINUTES: int = 5
    MEMBER_LEVEL_SCORE_NORMAL: int = 0
    MEMBER_LEVEL_SCORE_SILVER: int = 10
    MEMBER_LEVEL_SCORE_GOLD: int = 20
    MEMBER_LEVEL_SCORE_PLATINUM: int = 30
    RETURNING_STUDENT_BONUS: int = 15
    URGENT_BONUS: int = 50
    API_V1_PREFIX: str = "/api/v1"


settings = Settings()
