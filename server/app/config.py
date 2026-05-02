from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    allowed_origins: list[str] = ["http://localhost:5173"]
    app_name: str = "server"
    clerk_expected_audience: str = ""
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_publishable_key: str = ""
    clerk_secret_key: str = ""
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/dbname"
    debug: bool = False
    environment: str = "production"
    github_app_id: int = 0
    github_app_slug: str = ""
    github_private_key_path: str = ""
    github_private_key: str = ""
    github_webhook_secret: str = ""
    internal_cron_secret: str = ""
    seed_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    seed_tenant_name: str = "dev"
    sentry_dsn: str = ""

    @model_validator(mode="after")
    def _fix_database_url(self) -> "Settings":
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self

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
