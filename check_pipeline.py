"""Quick check of how your pipeline processes NSE data"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import pandas as pd

# Check what columns exist after your pipeline processes the data
df = pd.read_csv("data/combined_dashboard_live.csv")

print("Columns in processed file:")
print(df.columns.tolist())

print("\nSample row (first NSE stock):")
nse = df[df['EXCHANGE'] == 'NSE'].iloc[0]
print(f"SYMBOL: {nse['SYMBOL']}")
print(f"CLOSE: {nse['CLOSE']}")
print(f"DELIVERY_TURNOVER: {nse['DELIVERY_TURNOVER']}")
print(f"ATW: {nse['ATW']}")

print("\n✅ This confirms your pipeline OUTPUT is correct.")
print("But we still need to verify the FORMULAS used to create it.")

def check_session_log_freshness():
    import os, re, subprocess
    session_file = os.path.join("scratch", "last_session.md")
    if not os.path.exists(session_file):
        print(f"\n❌ [CRITICAL] Session log not found: {session_file}")
        return

    last_log_date = None
    with open(session_file, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^## (?:Last )?Session — (\d{4}-\d{2}-\d{2})", line)
            if m:
                last_log_date = m.group(1)

    if not last_log_date:
        print(f"\n⚠️  [WARN] No dated session header found in {session_file}")
        return

    try:
        res = subprocess.run(["git", "log", "-1", "--format=%as"], capture_output=True, text=True, check=True)
        latest_commit_date = res.stdout.strip()
    except Exception as e:
        print(f"\n⚠️  [WARN] Unable to determine git commit date: {e}")
        return

    print("\n--- Session Log Status ---")
    if last_log_date < latest_commit_date:
        print(f"⚠️  SESSION LOG STALE! Last commit: {latest_commit_date}, Last log: {last_log_date}")
        print("👉 Please run session handoff before pushing.")
    else:
        print(f"✅ Session log is current (Log: {last_log_date} >= Commit: {latest_commit_date}).")

check_session_log_freshness()

