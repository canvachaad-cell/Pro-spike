import time
from dash_pages._vikram_callback import ask_vikram

print("Starting Vikram 503 Monitoring Loop...")
question = "Tell me about HDFCBANK fundamentals"
history = []

attempt = 1
while True:
    print(f"\n--- Attempt {attempt} ---")
    text, sources, err = ask_vikram(question, history)
    
    if err:
        print(f"FAILED: {err}")
        if "503" in str(err) or "429" in str(err):
            print("API is still congested. Waiting 10 seconds before next ping...")
            time.sleep(10)
            attempt += 1
        else:
            print("Unknown error occurred. Stopping loop.")
            break
    else:
        print(f"\nSUCCESS! Google API cluster is back online.")
        print(f"Sources: {sources}")
        print(f"Text snippet: {text[:200]}...")
        break
