from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Finance Recon AI"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/finance_recon"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    LLM_PROVIDER: str = "OLLAMA" # OLLAMA or OPENAI
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None
    GEMINI_MODEL_NAME: str = "gemini-2.5-pro"
    OPENAI_MODEL_NAME: str = "gpt-5.2"
    USD_BRL_RATE: float = 5.85

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
