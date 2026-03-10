from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "server"
    debug: bool = False


settings = Settings()
