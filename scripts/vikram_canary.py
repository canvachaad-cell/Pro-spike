import json
import os
import time
import requests
import sys

# Ensure logs dir exists
os.makedirs("logs", exist_ok=True)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'vikram_runtime.json')

def run_canary():
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
    except Exception as e:
        log_result("ERROR", f"Failed to load config: {e}")
        return

    probe_timeout = config.get("probe_timeout_s", 10)
    candidates = config.get("model_candidates", [])

    results = []
    for model in candidates:
        provider = model.get("provider")
        model_id = model.get("id")
        base_url = model.get("base_url")
        
        start = time.time()
        success = False
        err_msg = ""
        
        try:
            if provider == "google":
                api_key = os.environ.get("GEMINI_API_KEY", "")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
                payload = {"contents": [{"parts": [{"text": "Reply exactly with OK"}]}]}
                resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=probe_timeout)
                resp.raise_for_status()
                success = True
            else:
                err_msg = f"Unknown provider {provider}"
        except Exception as e:
            err_msg = str(e)
            
        latency = round(time.time() - start, 2)
        status = "PASS" if success else "FAIL"
        
        log_line = f"[{status}] {provider}/{model_id} - {latency}s"
        if err_msg:
            log_line += f" ({err_msg})"
        results.append(log_line)
        
    with open("logs/canary.log", "a") as f:
        f.write(f"--- Canary Run {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        for r in results:
            f.write(f"{r}\n")
        f.write("\n")
        
    print("Canary run complete. Wrote to logs/canary.log")


def log_result(status, msg):
    with open("logs/canary.log", "a") as f:
        f.write(f"[{status}] {time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
        
if __name__ == "__main__":
    run_canary()
