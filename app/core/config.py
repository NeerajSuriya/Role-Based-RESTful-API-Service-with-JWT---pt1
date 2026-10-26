from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Role-Based Resource Management API"
    database_url: str = "postgresql+psycopg://localhost/resource_management"
    test_database_url: str | None = None
    jwt_secret_key: str | None = None
    access_token_expire_minutes: int = Field(default=30, gt=0)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
