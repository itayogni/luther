from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://luther:luther@localhost:5432/luther"
    encryption_key: str = "change-me-in-production-32chars!"
    gateway_secret: str = "shared-secret-between-services"
    core_host: str = "0.0.0.0"
    core_port: int = 8000
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    allowed_chat_name: str = "לותר ואני"
    allowed_group_jid: str = ""  # Set to the WhatsApp group JID for iron-rule enforcement

    model_config = SettingsConfigDict(env_prefix="LUTHER_", env_file=".env", extra="ignore")


settings = Settings()
