from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings

class LLMFactory:
    @staticmethod
    def get_llm(temperature: float = 0.0):
        provider = settings.LLM_PROVIDER.upper()
        
        if provider == "GEMINI":
            print(f"DEBUG: Initializing Gemini with model: {settings.GEMINI_MODEL_NAME}")
        elif provider == "OPENAI":
            print(f"DEBUG: Initializing OpenAI with model: {settings.OPENAI_MODEL_NAME}")
            
        if provider == "OPENAI":
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER is OPENAI")
            
            return ChatOpenAI(
                model=settings.OPENAI_MODEL_NAME,
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
            
        elif provider == "GEMINI":
            if not settings.GOOGLE_API_KEY:
                raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER is GEMINI")
            
            return ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL_NAME,
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=temperature,
                convert_system_message_to_human=True
            )
        
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
