import os
from google import genai
from google.genai import types

def find_working_model():
    from dotenv import load_dotenv
    load_dotenv()
    
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("No GEMINI_API_KEY found.")
        return
        
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=15000))
    
    print("Fetching available models...")
    try:
        models = list(client.models.list())
        model_names = [m.name for m in models if "flash" in m.name or "pro" in m.name]
        print(f"Found {len(model_names)} candidate models.")
    except Exception as e:
        print(f"Failed to list models: {e}")
        # fallback list just in case list() fails
        model_names = [
            "gemini-2.0-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash-8b", 
            "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash"
        ]
        
    working = []
    for name in model_names:
        name = name.replace("models/", "")
        print(f"\nTesting {name}...")
        try:
            resp = client.models.generate_content(
                model=name,
                contents="Reply with the word SUCCESS",
            )
            text = getattr(resp, "text", "")
            print(f"  [OK] {name} -> {text.strip() if text else 'Empty Response'}")
            working.append(name)
        except Exception as e:
            print(f"  [FAILED] {name} -> {e}")
            
    print("\n--- SUMMARY ---")
    print("Working models:", working)

if __name__ == "__main__":
    find_working_model()
