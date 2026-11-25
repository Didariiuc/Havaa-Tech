from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    app_name: str = "Havaa Tech API"
    database_url: str = "sqlite:///./solarwise.db"
    jwt_secret: str = "change-me-now"
    jwt_expire_minutes: int = 1440
    google_api_key: str = ""
    primary_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.5-flash-lite"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-20b"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "solarwise-policies"
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    refund_approval_threshold: float = 2000
    max_agent_tool_calls: int = 8
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
settings = Settings()
