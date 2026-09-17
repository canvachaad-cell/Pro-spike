import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Append the directory containing dash_pages to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from dash_pages._vikram_callback import ask_vikram

def run_test():
    print("Testing Vikram chat callback...")
    try:
        text, sources, error = ask_vikram("What is the current status of the market?", [])
        if error:
            print(f"FAILED: {error}")
        else:
            print(f"SUCCESS! Received response (length {len(text)}). Sources: {sources}")
            print("-" * 50)
            print(text[:200] + "..." if len(text) > 200 else text)
    except Exception as e:
        print(f"EXCEPTION THROWN: {e}")

if __name__ == "__main__":
    run_test()
