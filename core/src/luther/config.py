from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://luther:luther@localhost:5432/luther"
    encryption_key: str = "change-me-in-production-32chars!"
    gateway_secret: str = "shared-secret-between-services"
    core_host: str = "0.0.0.0"
    core_port: int = 8000

    model_config = {"env_prefix": "LUTHER_"}


settings = Settings()
