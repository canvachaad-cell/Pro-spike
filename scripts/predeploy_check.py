import os
import sys
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()

def check_git_status():
    print("Checking git status...")
    code, out, err = run_cmd("git status --porcelain")
    
    # We want to ensure no critical config/schema files are unstaged/untracked
    # But it's okay if logs/ or temp data are untracked.
    if code != 0:
        print(f"ERROR: git status failed: {err}")
        return False
        
    critical_files = ['schema_contracts.py', 'config/vikram_runtime.json', 'fundamental_fetcher.py']
    for line in out.splitlines():
        if any(cf in line for cf in critical_files):
            print(f"ERROR: Critical file {line} has uncommitted changes.")
            print("Please commit all schema and config changes before deploying.")
            return False
            
    print("Git status OK.")
    return True

def verify_configs():
    print("Verifying config JSON...")
    if not os.path.exists("config/vikram_runtime.json"):
        print("ERROR: config/vikram_runtime.json missing!")
        return False
        
    try:
        with open("config/vikram_runtime.json") as f:
            data = json.load(f)
            
        from schema_contracts import validate_runtime_config
        validate_runtime_config(data)
    except Exception as e:
        print(f"ERROR: Config validation failed: {e}")
        return False
        
    print("Config validation OK.")
    return True

def run_tests():
    print("Running Golden Regression Suite...")
    code, out, err = run_cmd("python -m pytest tests/")
    if code != 0:
        print("ERROR: Tests failed!")
        print(out)
        return False
    print("Tests passed.")
    return True

def main():
    print("=== PRE-DEPLOY PARITY CHECK ===")
    if not check_git_status():
        sys.exit(1)
        
    if not verify_configs():
        sys.exit(1)
        
    if not run_tests():
        sys.exit(1)
        
    print("\n[OK] All pre-deploy checks passed. Safe to push.")

if __name__ == "__main__":
    main()
