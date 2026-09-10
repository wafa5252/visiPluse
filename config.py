"""
Centralized configuration. All secrets and environment-specific values are
read from environment variables / .env — never hardcoded — so the same
codebase can move from dev to staging to production safely.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./visipulse.db"

    jwt_secret_key: str = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:3000"

    anomaly_risk_threshold: float = 60.0
    critical_risk_threshold: float = 85.0

    env: str = "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
