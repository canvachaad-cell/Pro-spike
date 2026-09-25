import os
import sys
import io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import glob
import pandas as pd
import requests
import zipfile
from datetime import datetime, timedelta
from nse_downloader_fixed_nov2025 import NSEDownloaderFixed
from bse_downloader_working import BSEDownloaderWorking, normalize_bse_delivery, merge_bse_bhav_delivery
from config import Config

pd.options.mode.chained_assignment = None

import logging
from logging.handlers import RotatingFileHandler

os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("auto_update")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler("logs/auto_update.log", maxBytes=5*1024*1024, backupCount=3)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.exit(1)

sys.excepthook = handle_exception

logger.info("Starting SMART AUTO-UPDATE...")

print("=" * 70)
print("SMART AUTO-UPDATE - NSE + BSE with Real Progressives (v4 ENHANCED)")
print("=" * 70)

holidays = [
    # 2025 (kept for backfill lookback)
    "2025-01-26", "2025-03-14", "2025-03-29", "2025-04-10", "2025-04-14",
    "2025-05-01", "2025-08-15", "2025-10-02", "2025-10-22",
    "2025-11-01", "2025-11-05", "2025-12-25",
    # 2026 (official NSE/BSE trading holidays; validated against repo data)
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31",
    "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26",
    "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-10", "2026-11-24",
    "2026-12-25",
]

# ================================================================
# BACKFILL MISSING DATES (v4 - NOW INCLUDES BSE DELIVERY WITH DATE FIX)
# ================================================================
def get_missing_trading_dates(days_to_check=10):
    """Check which trading dates in the lookback window (including TODAY) are missing any of the 4 feeds:
    1. NSE Bhav (data/nse_raw/nse_bhav_YYYYMMDD.csv)
    2. NSE Delivery (data/nse_raw/nse_delivery_YYYYMMDD.csv)
    3. BSE Bhav (data/bse_raw/bse_bhav_YYYYMMDD.csv)
    4. BSE Delivery (data/bse_delivery_YYYYMMDD.csv)
    """
    today = datetime.now()
    missing_items = []
    # Check from days_to_check days ago up to and including TODAY (i=0)
    for i in range(days_to_check, -1, -1):
        check_date = today - timedelta(days=i)
        # Skip weekends
        if check_date.weekday() >= 5:
            continue
        # Skip holidays
        date_str_dash = check_date.strftime("%Y-%m-%d")
        if date_str_dash in holidays:
            continue
        date_str = check_date.strftime("%Y%m%d")
        
        # Check all 4 feeds individually
        missing_feeds = []
        if not os.path.exists(f"data/nse_raw/nse_bhav_{date_str}.csv"):
            missing_feeds.append("nse_bhav")
        if not os.path.exists(f"data/nse_raw/nse_delivery_{date_str}.csv"):
            missing_feeds.append("nse_deliv")
        if not os.path.exists(f"data/bse_raw/bse_bhav_{date_str}.csv"):
            missing_feeds.append("bse_bhav")
        if not os.path.exists(f"data/bse_delivery_{date_str}.csv"):
            missing_feeds.append("bse_deliv")
            
        if missing_feeds:
            missing_items.append({
                "date": check_date,
                "date_str": date_str,
                "missing": missing_feeds
            })
    return missing_items


def backfill_missing_dates(missing_items):
    """Download specific missing feeds for all incomplete dates (never skips today)"""
    if not missing_items:
        print("✅ All 4 data feeds (NSE Bhav, NSE Delivery, BSE Bhav, BSE Delivery) are fully up to date.\n")
        return

    print(f"\n{'='*70}")
    print(f"⚠️  MISSING / PENDING DATA FEEDS DETECTED")
    print(f"{'='*70}")
    for item in missing_items:
        dt = item["date"]
        missing_str = ", ".join([f.upper() for f in item["missing"]])
        print(f"  📅 {dt.strftime('%Y-%m-%d (%A)')}: Missing [{missing_str}]")
    print(f"{'='*70}\n")
    print("📥 Starting selective download for missing feeds...\n")

    nse_downloader = NSEDownloaderFixed()
    bse_downloader = BSEDownloaderWorking()

    for item in missing_items:
        date_obj = item["date"]
        date_str = item["date_str"]
        missing = item["missing"]
        print(f"🔄 Syncing: {date_obj.strftime('%Y-%m-%d')} (Missing: {', '.join(missing)})")
        
        ok_bhav = "nse_bhav" not in missing
        ok_deliv = "nse_deliv" not in missing
        ok_bse = "bse_bhav" not in missing
        bse_deliv_ok = "bse_deliv" not in missing

        try:
            # 1. NSE Bhavcopy
            if "nse_bhav" in missing:
                _, ok_bhav, _ = nse_downloader.download_nse_bhav_new_format(date_obj)

            # 2. NSE Delivery
            if "nse_deliv" in missing:
                _, ok_deliv, _ = nse_downloader.download_nse_delivery(date_obj)

            # 3. BSE Bhavcopy
            if "bse_bhav" in missing:
                _, ok_bse, _ = bse_downloader.download_bse_bhav(date_obj)

            # 4. BSE Delivery
            if "bse_deliv" in missing:
                df_bse_del, bse_deliv_ok = bse_downloader.download_bse_delivery(date_obj)
                if bse_deliv_ok and df_bse_del is not None:
                    df_bse_del.to_csv(f"data/bse_delivery_{date_str}.csv", index=False)

            msg = "   📊 Status:\n"
            msg += f"      NSE Bhav:  {'✅' if ok_bhav else '⏳ Pending / Failed'}\n"
            msg += f"      NSE Deliv: {'✅' if ok_deliv else '⏳ Pending / Failed'}\n"
            msg += f"      BSE Bhav:  {'✅' if ok_bse else '⏳ Pending / Failed'}\n"
            msg += f"      BSE Deliv: {'✅' if bse_deliv_ok else '⏳ Pending (Not yet uploaded by exchange)'}"
            print(msg)
        except Exception as e:
            print(f"  ⚠️  Error during sync: {e}")
            continue

    print()
    print(f"{'='*70}")
    print("✅ FEED SYNCHRONIZATION COMPLETE")
    print(f"{'='*70}\n")

# -------------------------------
# Helpers (defined BEFORE use)
# -------------------------------
def to_num(s):
    return pd.to_numeric(s, errors="coerce")

def safe_read_csv(path, **kw):
    try:
        return pd.read_csv(path, **kw)
    except Exception as e:
        print(f"Read error: {path} -> {e}")
        return pd.DataFrame()

def ensure_cols(df, cols_with_default):
    for c, v in cols_with_default.items():
        if c not in df.columns:
            df[c] = v
    return df

def normalize_bse_bhav(df):
    # Map BSE schema to standard names
    ren = {
        "BizDt": "DATE",
        "TckrSymb": "SYMBOL",
        "ClsPric": "CLOSE",
        "TtlTradgVol": "TOTTRDQTY",
        "TtlTrfVal": "TOTTRDVAL",
        "TtlNbOfTxsExctd": "NO_OF_TRADES",
    }
    df = df.rename(columns=ren)
    # Parse DATE
    if "DATE" in df.columns:
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    # Numeric conversions
    for c in ["CLOSE","TOTTRDQTY","TOTTRDVAL","NO_OF_TRADES"]:
        if c in df.columns:
            df[c] = to_num(df[c]).fillna(0)
    df["EXCHANGE"] = "BSE"
    # Ensure critical columns exist
    df = ensure_cols(df, {"ISIN": None, "FinInstrmId": None, "SYMBOL": None})
    return df

def normalize_nse_bhav(df, date):
    df = df.copy()
    df["DATE"] = date
    df["EXCHANGE"] = "NSE"
    if "TtlNbOfTxsExctd" in df.columns:
        df["NO_OF_TRADES"] = df["TtlNbOfTxsExctd"]
    for c in ["CLOSE","TOTTRDQTY","TOTTRDVAL","NO_OF_TRADES"]:
        if c in df.columns:
            df[c] = to_num(df[c]).fillna(0)
    # Ensure expected columns
    df = ensure_cols(df, {"ISIN": None, "SYMBOL": None})
    return df


# Run 4-Feed Synchronization (NSE Bhav, NSE Deliv, BSE Bhav, BSE Deliv)
print(f"{'='*70}")
print("[SEARCH] CHECKING 4-FEED COMPLETENESS (NSE/BSE Bhav + Delivery)...")
print(f"{'='*70}")
missing_items = get_missing_trading_dates(days_to_check=10)
backfill_missing_dates(missing_items)

# -------------------------------
# Step 2: Load NSE bhav
# -------------------------------
nse_raw_dir = Config.NSE_RAW_DIR
nse_bhav_files = sorted([f for f in os.listdir(nse_raw_dir) if f.startswith("nse_bhav_")])
print(f"\n📥 Loading {len(nse_bhav_files)} NSE bhav files...")

nse_frames = []
for fn in nse_bhav_files:
    date_str = fn.replace("nse_bhav_", "").replace(".csv", "")
    d = datetime.strptime(date_str, "%Y%m%d")
    df = safe_read_csv(os.path.join(nse_raw_dir, fn))
    if df.empty: continue
    df = normalize_nse_bhav(df, d)
    nse_frames.append(df)

df_nse = pd.concat(nse_frames, ignore_index=True) if nse_frames else pd.DataFrame()
print(f"✅ NSE records: {len(df_nse)}")

# -------------------------------
# Step 3: Load BSE bhav
# -------------------------------
print(f"📥 Loading BSE bhav data...")
bse_raw_dir = os.path.join(os.path.dirname(nse_raw_dir), "bse_raw")
bse_bhav_files = sorted(glob.glob(os.path.join(bse_raw_dir, "bse_bhav_*.csv")))

bse_frames = []
if bse_bhav_files:
    print(f"Found {len(bse_bhav_files)} BSE bhav files")
    for fp in bse_bhav_files:
        df = safe_read_csv(fp)
        if df.empty: continue
        df = normalize_bse_bhav(df)
        bse_frames.append(df)

df_bse = pd.concat(bse_frames, ignore_index=True) if bse_frames else pd.DataFrame()
print(f"✅ BSE records: {len(df_bse)}")

# -------------------------------
# Step 4: Load NSE delivery
# -------------------------------
print(f"\n📥 Loading NSE delivery data...")
nse_delivery_files = sorted([f for f in os.listdir(nse_raw_dir) if f.startswith("nse_delivery_")])

nse_del_frames = []
for fn in nse_delivery_files:
    date_str = fn.replace("nse_delivery_", "").replace(".csv", "")
    d = datetime.strptime(date_str, "%Y%m%d")
    df = safe_read_csv(os.path.join(nse_raw_dir, fn))
    if df.empty: continue
    # normalize
    if " SYMBOL" in df.columns:
        df = df.rename(columns={" SYMBOL":"SYMBOL"})
    df = normalize_bse_delivery(df)  # reuse standardizer
    df["DATE"] = d
    nse_del_frames.append(df)

df_nse_deliv = pd.concat(nse_del_frames, ignore_index=True) if nse_del_frames else pd.DataFrame()
print(f"✅ NSE delivery rows: {len(df_nse_deliv)}")

# -------------------------------
# Step 5: Load BSE delivery (v4 - DATE now pre-injected)
# -------------------------------
print(f"📥 Loading BSE delivery data...")
bse_delivery_files = sorted(glob.glob("data/bse_delivery_*.csv"))

bse_del_frames = []
for fp in bse_delivery_files:
    date_str = os.path.basename(fp).replace("bse_delivery_", "").replace(".csv","")
    d = datetime.strptime(date_str, "%Y%m%d")
    df = safe_read_csv(fp)
    if df.empty: continue
    df = normalize_bse_delivery(df)
    # v4 FIX: Do NOT overwrite DATE - it should already exist from download
    # Only inject if missing (for backward compat with old CSVs)
    if "DATE" not in df.columns or df["DATE"].isna().all():
        df["DATE"] = d
    bse_del_frames.append(df)

df_bse_deliv = pd.concat(bse_del_frames, ignore_index=True) if bse_del_frames else pd.DataFrame()
print(f"✅ BSE delivery rows: {len(df_bse_deliv)}")


# -------------------------------
# Save Exact Status JSON
# -------------------------------
import json
import pandas as pd
try:
    def _parse_status_date(val):
        """Parse a DATE cell that may be a Timestamp, int/float (YYYYMMDD or
        DDMMYYYY) or string. Returns a Timestamp or None if unparseable."""
        try:
            if pd.isna(val):
                return None
        except Exception:
            pass
        if isinstance(val, (pd.Timestamp, datetime)):
            return pd.Timestamp(val)
        s = str(val).strip()
        if s.endswith(".0"):
            s = s[:-2]
        dt = pd.to_datetime(s, format='%Y%m%d', errors='coerce')
        if pd.isna(dt):
            dt = pd.to_datetime(s, format='%d%m%Y', errors='coerce')
        if pd.isna(dt):
            dt = pd.to_datetime(s, errors='coerce')
        return None if pd.isna(dt) else dt

    def get_max_date(df, label='feed'):
        if df is None or df.empty or 'DATE' not in df.columns:
            print(f"⚠️  data_status[{label}]: no DATE data — reporting 'Missing'")
            return 'Missing'
        parsed_max = None
        for val in df['DATE'].dropna().unique():
            dt = _parse_status_date(val)
            if dt is None:
                print(f"🚨 data_status[{label}]: unparseable DATE value {val!r} — "
                      f"source files for this feed are MALFORMED. Reporting 'Missing'.")
                return 'Missing'
            if parsed_max is None or dt > parsed_max:
                parsed_max = dt
        if parsed_max is None:
            print(f"⚠️  data_status[{label}]: all DATE values are NaN — reporting 'Missing'")
            return 'Missing'
        return parsed_max.strftime('%d %b %Y')

    status_data = {
        'nse_bhav_date': get_max_date(df_nse, 'nse_bhav'),
        'nse_deliv_date': get_max_date(df_nse_deliv, 'nse_deliv'),
        'bse_bhav_date': get_max_date(df_bse, 'bse_bhav'),
        'bse_deliv_date': get_max_date(df_bse_deliv, 'bse_deliv'),
        'last_run': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open('data/data_status.json', 'w') as f:
        json.dump(status_data, f, indent=4)
except Exception as e:
    print(f'Error saving data_status.json: {e}')


# -------------------------------
# Step 6: Merge delivery into NSE
# -------------------------------
if not df_nse.empty and not df_nse_deliv.empty:
    # NSE merge via SYMBOL + DATE
    cols_keep = [c for c in ["SYMBOL","DATE","DELIV_PER","DELIV_QTY"] if c in df_nse_deliv.columns]
    df_nse = df_nse.merge(df_nse_deliv[cols_keep], on=["SYMBOL","DATE"], how="left")
else:
    df_nse = ensure_cols(df_nse, {"DELIV_PER":0, "DELIV_QTY":0})

# -------------------------------
# Step 7: Merge delivery into BSE
# -------------------------------
print("\n🔀 Merging BSE delivery data...")
df_bse = merge_bse_bhav_delivery(df_bse, df_bse_deliv)
bse_merged_count = len(df_bse[df_bse["DELIV_PER"] > 0])
print(f"✅ BSE stocks with delivery data merged: {bse_merged_count}/{len(df_bse)}")


from datetime import datetime

def log_bse_delivery_stats(df_bse, run_date=None):
    if run_date is None:
        run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(df_bse)
    zero_delivery = (df_bse['DELIV_PER'] == 0).sum()
    partial_delivery = ((df_bse['DELIV_PER'] > 0) & (df_bse['DELIV_PER'] < 100)).sum()
    full_delivery = (df_bse['DELIV_PER'] == 100).sum()

    stats = {
        'run_date': run_date,
        'total_bse_rows': total,
        'zero_delivery': zero_delivery,
        'partial_delivery': partial_delivery,
        'full_delivery': full_delivery,
    }

    log_file = "data/debug_bse_row_counts.csv"
    df_stats = pd.DataFrame([stats])
    if os.path.exists(log_file):
        df_stats.to_csv(log_file, mode='a', header=False, index=False)
    else:
        df_stats.to_csv(log_file, index=False)
    print("📊 Logged BSE delivery stats:", stats)

# Immediately after your existing merge:
log_bse_delivery_stats(df_bse)

# -------------------------------
# Step 8: Combine NSE + BSE, dedupe by ISIN+DATE (NSE priority)
# -------------------------------
print("\n🔀 Combining NSE + BSE and deduplicating by ISIN+DATE (NSE priority)")

df_all = pd.concat([df_nse, df_bse], ignore_index=True, sort=False)
print(f"Total rows before dedup: {len(df_all)}")
print(f"Count by exchange before dedup:\n{df_all['EXCHANGE'].value_counts()}")

# Set DATE and latest_date
if "DATE" in df_all.columns:
    latest_date = pd.to_datetime(df_all["DATE"], errors="coerce").max()
else:
    latest_date = None

df_all["EXCH_PRIORITY"] = df_all["EXCHANGE"].apply(lambda x: 0 if x == "NSE" else 1)

has_isin = "ISIN" in df_all.columns and df_all["ISIN"].notna().sum() > 0
if has_isin:
    df_all = df_all.sort_values(["ISIN", "DATE", "EXCH_PRIORITY"])
    before_dedup = len(df_all)
    df_all = df_all.drop_duplicates(subset=["ISIN", "DATE"], keep="first")
    after_dedup = len(df_all)
    print(f"Total rows after dedup: {after_dedup}")
    print(f"Rows removed: {before_dedup - after_dedup}")
    print(f"Count by exchange after dedup:\n{df_all['EXCHANGE'].value_counts()}")
else:
    print("⚠️  ISIN missing or empty, falling back to SYMBOL deduplication")
    df_all = df_all.sort_values(["SYMBOL", "DATE", "EXCH_PRIORITY"])
    before_dedup = len(df_all)
    df_all = df_all.drop_duplicates(subset=["SYMBOL", "DATE"], keep="first")
    after_dedup = len(df_all)
    print(f"Total rows after dedup: {after_dedup}")
    print(f"Rows removed: {before_dedup - after_dedup}")
    print(f"Count by exchange after dedup:\n{df_all['EXCHANGE'].value_counts()}")

df_all.drop(columns=["EXCH_PRIORITY"], inplace=True, errors="ignore")

# ======================================================================
# Step 9: Compute metrics + filter universe
# ======================================================================
df_all = ensure_cols(df_all, {"CLOSE":0,"TOTTRDQTY":0,"TOTTRDVAL":0, "NO_OF_TRADES":0,"DELIV_QTY":0,"DELIV_PER":0})

for c in ["CLOSE","TOTTRDQTY","TOTTRDVAL","DELIV_QTY","DELIV_PER"]:
    df_all[c] = to_num(df_all[c]).fillna(0)

# Core metrics
df_all["DELIVERY_TURNOVER"] = df_all["DELIV_QTY"] * df_all["CLOSE"]
df_all["ATW"] = (df_all["TOTTRDVAL"] / df_all["NO_OF_TRADES"].replace(0, pd.NA)).fillna(0)

# ===== UNIVERSE FILTERING (COMBINED MASK TO PREVENT MEMORY THRASHING) =====
import time
t0 = time.time()
before = len(df_all)

# Base mask starts as all True
mask = pd.Series(True, index=df_all.index)

# 0. STRICT EQUITY ISIN FILTER (NSDL / CDSL ISO 6166: 'INE' = Indian Equity)
# Eliminates all 'INF' (Mutual Funds / ETFs), 'IN0'/'IN1' (G-Secs/Bonds), and 'IN9' (preference/rights)
if "ISIN" in df_all.columns:
    mask &= df_all["ISIN"].fillna("").str.startswith("INE")

# 1. Filter SERIES (keep NSE EQ & all BSE)
if "SERIES" in df_all.columns:
    mask &= ((df_all["EXCHANGE"]=="NSE") & (df_all["SERIES"]=="EQ")) | (df_all["EXCHANGE"]=="BSE")

# 2. Exclude generic ETFs/FUNDS/INDEX (optimized regex without case=False)
if "SYMBOL" in df_all.columns:
    syms_upper = df_all["SYMBOL"].fillna("").str.upper()
    mask &= ~syms_upper.str.contains(
        "ETF|LIQID|LIQUID|FUND|INDEX|NIFTY|SENSEX|GLOBE|BEES|HDFCPVTBAN|HDFCPSU|BANKPSU|MOMENTUM|LOWVOL|ESILVER|BBNPP|PSUBANK|GOLD|SILVER|EQUAL|NIFBAN|NIF100|GROWW",
        regex=True
    )

# 3. Explicitly drop known bad ISINs
bad_isins = [
    "INE148I07PY7", "INE1O3X15025", "INE296G07200", "INE296G07226",
    "INE306N08342", "INE443L08172", "INE501X07554", "INE501X08081",
    "INE549K08293", "INE612U07118", "INE733E07JR2", "INE787H07362",
    "INE836K07312", "INE939X07093",
]
if "ISIN" in df_all.columns:
    mask &= ~df_all["ISIN"].isin(bad_isins)

# 4. Exclude NON-EQUITY BSE INSTRUMENTS (BONDS, T-BILLS, SGBs, G-SECS)
if "SYMBOL" in df_all.columns:
    bond_prefixes = ('GS', 'SGB', 'SDL', 'MHSDL', 'ZC', 'CS', 'EELZ')
    bond_suffixes = ('TB', 'PP')
    
    mask_prefix = syms_upper.str.startswith(bond_prefixes)
    mask_suffix = syms_upper.str.endswith(bond_suffixes)
    # Numeric prefix check ONLY for BSE
    mask_numeric_bse = (df_all["SYMBOL"].fillna("").str.match(r'^\d')) & (df_all["EXCHANGE"] == "BSE")
    
    mask &= ~(mask_prefix | mask_suffix | mask_numeric_bse)

# Apply mask once, eliminating redundant deep copies
df_all = df_all[mask].copy()

after = len(df_all)
t1 = time.time()
print(f"Filtered universe in single pass: {before} -> {after} rows (took {t1-t0:.2f}s)")

# -------------------------------
# Step 10: Calculate progressive averages
# -------------------------------
print("\n📈 Calculating progressive averages...")

if "DATE" not in df_all.columns:
    raise ValueError("DATE column missing in df_all before progressive averages")

# Verify DATE is already datetime (parsed at line 488) to avoid re-parsing 1.5M rows
assert pd.api.types.is_datetime64_any_dtype(df_all["DATE"]), "DATE column must be datetime"

# Pre-sort to eliminate 5,600+ inner sorts in the loop
df_all = df_all.sort_values(["SYMBOL", "DATE"])

# Pre-filter to symbols that traded on the latest market date to eliminate dead iterations
active_today_symbols = set(df_all[df_all["DATE"] == latest_date]["SYMBOL"].dropna())
total_active = len(active_today_symbols)
grouped_symbols = df_all[df_all["SYMBOL"].isin(active_today_symbols)].groupby("SYMBOL")
results = []
processed = 0

for symbol, df_stock in grouped_symbols:
    if df_stock.empty:
        continue

    # GUARD: only include symbols that traded on the latest market date
    # Since df_all is pre-sorted by DATE ascending, the latest row is the last one.
    latest = df_stock.iloc[-1]
    if latest["DATE"] != latest_date:
        continue

    # Historical rows (excluding latest), reversed so newest is first
    # Avoids expensive sort_values() call inside the loop
    hist = df_stock.iloc[:-1][::-1]

    df_1w = hist.head(5)
    df_1m = hist.head(22)
    df_3m = hist.head(66)

    # Check if this stock is likely a T2T stock (consistently ~100% delivery)
    # Using mean >= 95.0% instead of .any() so normal stocks like PAYTM aren't banished 
    # just because they hit a circuit limit on one day
    has_100_deliv = bool(df_stock["DELIV_PER"].mean() >= 95.0)

    # Calculate VWAP logic
    latest_tottrdval = latest.get("TOTTRDVAL", 0)
    latest_volume = latest.get("TOTTRDQTY", 0)
    latest_vwap = (latest_tottrdval / latest_volume) if (pd.notna(latest_volume) and latest_volume > 0) else latest.get("CLOSE", 0)
    
    # Calculate 1M VWAP (using 22 days)
    if len(df_1m) > 0:
        hist_1m_tottrdval = df_1m["TOTTRDVAL"].sum()
        hist_1m_volume = df_1m["TOTTRDQTY"].sum()
        vwap_1m = (hist_1m_tottrdval / hist_1m_volume) if (pd.notna(hist_1m_volume) and hist_1m_volume > 0) else df_1m["CLOSE"].mean()
    else:
        vwap_1m = latest_vwap

    latest_atw = latest.get("ATW", 0)
    atw_1m = df_1m["ATW"].mean() if len(df_1m) > 0 else latest_atw

    results.append({
        "DATE": latest_date,
        "SYMBOL": symbol,
        "ISIN": latest.get("ISIN", None),
        "EXCHANGE": latest.get("EXCHANGE", "NSE"),
        "CLOSE": latest.get("CLOSE", 0),
        "DELIV_PER": latest.get("DELIV_PER", 0),
        "DELIVERY_TURNOVER": latest.get("DELIVERY_TURNOVER", 0),
        "TOTAL_TURNOVER": latest_tottrdval,
        "VOLUME": latest_volume,
        "VWAP": latest_vwap,
        "VWAP_1M": vwap_1m,
        "WHALE_DENSITY": (latest_atw / latest_vwap) if (latest_vwap > 0) else 0,
        "WHALE_DENSITY_1M": (atw_1m / vwap_1m) if (vwap_1m > 0) else 0,
        "ATW": latest_atw,
        "EVER_100_DELIV": has_100_deliv,
        "DELIV_PER_1W": df_1w["DELIV_PER"].mean() if len(df_1w) > 0 else latest.get("DELIV_PER", 0),
        "DELIV_PER_1M": df_1m["DELIV_PER"].mean() if len(df_1m) > 0 else latest.get("DELIV_PER", 0),
        "DELIV_PER_3M": df_3m["DELIV_PER"].mean() if len(df_3m) > 0 else latest.get("DELIV_PER", 0),
        "DELIVERY_TURNOVER_1W": df_1w["DELIVERY_TURNOVER"].mean() if len(df_1w) > 0 else latest.get("DELIVERY_TURNOVER", 0),
        "DELIVERY_TURNOVER_1M": df_1m["DELIVERY_TURNOVER"].mean() if len(df_1m) > 0 else latest.get("DELIVERY_TURNOVER", 0),
        "DELIVERY_TURNOVER_3M": df_3m["DELIVERY_TURNOVER"].mean() if len(df_3m) > 0 else latest.get("DELIVERY_TURNOVER", 0),
        "ATW_1W": df_1w["ATW"].mean() if len(df_1w) > 0 else latest_atw,
        "ATW_1M": atw_1m,
        "ATW_3M": df_3m["ATW"].mean() if len(df_3m) > 0 else latest_atw,
    })

    processed += 1
    if processed % 500 == 0:
        print(f"Processed {processed}/{total_active} active equity stocks...")

print(f"✅ Processed all {processed}/{total_active} active equity stocks (100% complete).")
df_final = pd.DataFrame(results)

# -------------------------------
# Step 11: Save outputs
# -------------------------------
os.makedirs(os.path.dirname(Config.COMBINED_FILE), exist_ok=True)
dashboard_file = "data/combined_dashboard_live.csv"

import time
import shutil

for attempt in range(5):
    try:
        df_final.to_csv(dashboard_file, index=False)
        df_final.to_csv(Config.COMBINED_FILE, index=False)
        shutil.copy("data/combined_dashboard_live.csv", "data/dashboard_cloud.csv")
        logger.info(f"Successfully wrote output files on attempt {attempt+1}")
        break
    except PermissionError as e:
        logger.warning(f"PermissionError writing outputs (attempt {attempt+1}/5): {e}. Retrying in 2 seconds...")
        time.sleep(2)
else:
    logger.error("Failed to write output files after 5 attempts due to PermissionError.")
    sys.exit(1)

print("\n" + "="*70)
print("✅ SUCCESS!")
print(f"  Total Stocks: {len(df_final)} (NSE + BSE deduplicated by ISIN/DATE)")
print(f"  NSE Stocks: {len(df_final[df_final['EXCHANGE']=='NSE'])}")
print(f"  BSE Stocks: {len(df_final[df_final['EXCHANGE']=='BSE'])}")
if pd.notna(latest_date):
    print(f"  Latest Date: {latest_date.strftime('%d %b %Y')}")
print(f"  Dashboard (LIVE): {dashboard_file}")
print(f"  Legacy (Backtest): {Config.COMBINED_FILE}")
print("="*70)

print("Calculating institutional metrics...")
try:
    import subprocess
    os.makedirs("logs", exist_ok=True)
    METRICS_LOG = os.path.join("logs", "metrics_errors.log")

    def run_metrics_engine(engine_name, script):
        """Run a metrics engine, print full stderr and log to file on failure."""
        print(f"Running {engine_name}...")
        try:
            result = subprocess.run(
                [sys.executable, script],
                timeout=300, capture_output=True, text=True,
                encoding='utf-8', errors='replace',
            )
        except subprocess.TimeoutExpired:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(METRICS_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*70}\n[{stamp}] {script} TIMED OUT after 300s\n")
            print(f"🚨 {engine_name} TIMED OUT after 300s — logged to {METRICS_LOG}")
            return False
        if result.returncode == 0:
            print(f"{engine_name} metrics calculated successfully")
            return True
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stderr_full = result.stderr or "(no stderr captured)"
        print(f"🚨 {engine_name} FAILED (return code {result.returncode}). Full stderr:")
        print(stderr_full)
        with open(METRICS_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*70}\n[{stamp}] {script} failed, return code {result.returncode}\n")
            f.write(stderr_full)
            if result.stdout:
                f.write(f"\n--- stdout (last 2000 chars) ---\n{result.stdout[-2000:]}\n")
        print(f"🚨 Full error details appended to {METRICS_LOG}")
        return False

    ok_a = run_metrics_engine("Legacy Institutional", "calculate_active_signals.py")
    ok_b = run_metrics_engine("FlexGate 2.0 ML", "flexgate_2_scanner.py")
    ok_c = run_metrics_engine("Corner Spike", "corner_spike_scanner.py")
    ok_d = run_metrics_engine("Winner Archetypes", "rank_archetypes.py")
    if not (ok_a and ok_b and ok_c and ok_d):
        print(f"🚨 METRICS ENGINES FAILED — active_signals, ledgers, corner_engine, or winner_archetypes may be stale. See {METRICS_LOG}.")

        
    # Freshness Check
    import pandas as pd
    import os
    if os.path.exists("data/combined_dashboard_live.csv") and os.path.exists("data/signal_scores_today.csv"):
        try:
            live_df = pd.read_csv("data/combined_dashboard_live.csv")
            sig_df = pd.read_csv("data/signal_scores_today.csv")
            live_max = str(live_df['DATE'].max())
            sig_max = str(sig_df['DATE'].max())
            if live_max != sig_max:
                print(f"🚨 FRESHNESS WARNING: signal_scores_today.csv is stale! (Live: {live_max}, Signals: {sig_max})")
                with open(METRICS_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n[FRESHNESS WARNING] signal_scores_today.csv is stale! (Live: {live_max}, Signals: {sig_max})\n")
        except Exception as e:
            print(f"Could not perform freshness check: {e}")
            
except Exception as e:
    print(f"🚨 Metrics calculations failed (non-critical): {e}")

# ---- Ledger exit alerts (HIT_TP / HIT_SL / MOMENTUM_LOST / SUSPENDED) ----
# Reads ledgers READ-ONLY; never mutates them. Mirrors this file's existing
# "non-critical + print" pattern while ALSO logging loudly (NO SILENT FAILURES).
try:
    from alert_engine import dispatch_ledger_alerts
    dispatch_ledger_alerts()
except Exception as e:
    print(f"🚨 Alert engine failed (non-critical): {e}")
    logger.exception("Alert engine failed")

import sys
sys.exit(0)

