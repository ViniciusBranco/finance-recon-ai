from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from app.core.config import settings

class LLMFactory:
    @staticmethod
    def get_llm(temperature: float = 0.1):
        provider = settings.LLM_PROVIDER.upper()
        
        if provider == "OPENAI":
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER is OPENAI")
            
            return ChatOpenAI(
                model="gpt-4o-mini",
                temperature=temperature,
                openai_api_key=settings.OPENAI_API_KEY
            )
        
        elif provider == "OLLAMA":
            return ChatOllama(
                model="qwen2.5:7b",
                base_url=settings.OLLAMA_BASE_URL,
                temperature=temperature,
                format="json" # Force JSON mode for Ollama where supported
            )
        
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
