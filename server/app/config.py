from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "server"
    debug: bool = False
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/dbname"
    github_app_id: int = 0
    github_private_key_path: str = ""
    github_webhook_secret: str = ""
    seed_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    seed_tenant_name: str = "dev"
    internal_cron_secret: str = ""
    allowed_origins: list[str] = ["http://localhost:5173"]
    clerk_jwks_url: str = ""
    clerk_publishable_key: str = ""
    clerk_secret_key: str = ""
    clerk_expected_audience: str = ""
    clerk_issuer: str = ""
    github_app_slug: str = ""

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        if self.environment == "production":
            missing = [
                field
                for field in [
                    "github_webhook_secret",
                    "internal_cron_secret",
                    "clerk_secret_key",
                    "clerk_jwks_url",
                ]
                if not getattr(self, field)
            ]
            if missing:
                raise ValueError(f"Required secrets not set for production: {', '.join(missing)}")
        return self


settings = Settings()
