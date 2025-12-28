import google.generativeai as genai
import os
import sys

# Ensure we can import app modules if needed
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app.core.config import settings

def check_gemini():
    api_key = settings.GOOGLE_API_KEY
    if not api_key:
        print("[ERROR] GOOGLE_API_KEY is not set in environment or .env file.")
        print("Please add GOOGLE_API_KEY=your_key_here to .env")
        return

    print(f"Checking connectivity with API Key: {api_key[:5]}...{api_key[-5:]}")
    
    try:
        genai.configure(api_key=api_key)
        
        print("\n=== Available Gemini Models ===")
        print(f"{'Name':<30} | {'Methods':<30}")
        print("-" * 100)
        
        compatible_models = []
        
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"{m.name:<30} | {str(m.supported_generation_methods):<30}")
                compatible_models.append(m.name)
                
        if not compatible_models:
            print("\n[WARNING] No models found that support 'generateContent'.")
            return

        # Pick a model to test
        # Prefer gemini-1.5-pro-latest, then gemini-1.5-flash, then any
        test_model_name = "models/gemini-1.5-flash" 
        if "models/gemini-1.5-pro" in compatible_models:
             test_model_name = "models/gemini-1.5-pro"
        elif compatible_models:
             test_model_name = compatible_models[0]

        print(f"\n\n=== Connectivity Test: {test_model_name} ===")
        model = genai.GenerativeModel(test_model_name)
        
        print("Sending 'Hello World' prompt...")
        response = model.generate_content("Hello World")
        
        print(f"Response: {response.text.strip()}")
        
        # Check usage metadata
        print("\n=== Token Usage Metadata ===")
        if hasattr(response, "usage_metadata"):
            print(response.usage_metadata)
            print("[SUCCESS] Usage metadata is available.")
        else:
            # Sometimes it's a property or dict
            try:
                print(response._result.usage_metadata)
                print("[SUCCESS] Usage metadata found in _result.")
            except:
                print("[WARNING] Could not find direct usage_metadata on response object.")
                print(dir(response))

        print("\n\n=== Configuration Instructions ===")
        print("To use Gemini in this project, ensure your .env has:")
        print("LLM_PROVIDER=GEMINI")
        print(f"GOOGLE_API_KEY={api_key}")
        print(f"Target Model (in Code): {test_model_name}")

    except Exception as e:
        print(f"\n[CRITICAL ERROR] Failed to connect to Gemini API: {e}")

if __name__ == "__main__":
    check_gemini()
