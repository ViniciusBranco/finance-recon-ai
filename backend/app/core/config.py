from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Finance Recon AI"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/finance_recon"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
