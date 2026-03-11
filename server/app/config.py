from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "server"
    debug: bool = False
    environment: str = "production"
    database_url: str = "postgresql+asyncpg://distilled:distilled@localhost:5432/distilled"
    github_app_id: int = 0
    github_private_key_path: str = ""
    github_webhook_secret: str = ""
    seed_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    seed_tenant_name: str = "dev"
    internal_cron_secret: str = ""


settings = Settings()
