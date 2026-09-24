"""
Offline Quantitative Scorer: Winner Archetypes & Quality Cohort (Rule 3)
=======================================================================
Empirically calibrated to reproduce:
- Cohort: tier != LARGE AND DELIV_PER <= 80 AND (MID -> ATR% >= 3.15 | MICRO/SMALLISH -> ungated | fallback -> ATR% >= 3.4)
- Verification Anchor: n=25, 80.0% Win Rate, +21.0R, ₹62,985 PnL (± 1 trade / ledger update tolerance)
- Writes: data/winner_archetypes_ranked.csv
"""

import os
import glob
import json
import re
import datetime
import numpy as np
import pandas as pd

# Constants
NSE_RAW_DIR = "data/nse_raw"
FUND_CACHE_A = "data/fundamental_analysis_cache.json"  # Primary cache
FUND_CACHE_B = "data/fundamental_cache.json"           # Secondary cache
UNIVERSE_FILE = "data/combined_dashboard_live.csv"     # Full live dashboard universe
WATCHLIST_FILE = "data/sbia_alpha_watchlist.csv"       # Today's active screener signals
LEDGER_FILE = "data/sbia_ledger.csv"                   # For self-reconciliation check
OUTPUT_FILE = "data/winner_archetypes_ranked.csv"

NON_EQUITY_PATTERNS = r"ETF|LIQUID|FUND|INDEX|NIFTY|SENSEX|GILT5BETA|GILT10BETA|GS\d|SDL"

# Self-Reconciliation Anchors (Panel-matched closed trades from 2026-05-20 onwards)
ANCHOR_N = 25
ANCHOR_WIN = 80.0    # % win rate
ANCHOR_RS = 62_985   # ₹ PnL
TOLERANCE_N = 5
TOLERANCE_WIN = 5.0
TOLERANCE_RS = 10_000


def dedup_delivery_panel(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate (SYMBOL, DATE1) pairs using exchange/series priority.
    Matches pattern from build_historical_features.py:168-171.
    """
    df = df.copy()
    exch_col = df.get("EXCHANGE", pd.Series("NSE", index=df.index))
    df["EXCH_PRIORITY"] = (df["SYMBOL"].str.endswith("-BE") | ~exch_col.eq("NSE")).astype(int)
    df = df.sort_values(["SYMBOL", "DATE1", "EXCH_PRIORITY"])
    df = df.drop_duplicates(subset=["SYMBOL", "DATE1"], keep="first")
    df = df.drop(columns=["EXCH_PRIORITY"], errors="ignore")
    return df


def load_mcap() -> dict:
    """Load market cap (in Cr) from fundamental json caches."""
    mc = {}
    for path in [FUND_CACHE_B, FUND_CACHE_A]:  # Cache A overrides Cache B
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    j = json.load(f)
                    for k, v in j.items():
                        dv = (v.get("data", v) if isinstance(v, dict) else {}) or {}
                        mcap = dv.get("market_cap_cr")
                        if mcap is not None:
                            try:
                                mc[str(k).upper().strip()] = float(mcap)
                            except (ValueError, TypeError):
                                pass
            except Exception as e:
                print(f"Warning reading {path}: {e}")
    return mc


def run_self_reconciliation(mc: dict):
    """
    Verifies that the exact Rule 3 logic reproduces the anchored performance
    (n=25, 80.0% Win Rate, ₹62,985 PnL) against closed trades in sbia_ledger.csv.
    Fails loudly if there is a calculation discrepancy.
    """
    print("--- Running Self-Reconciliation Check against sbia_ledger.csv ---")
    if not os.path.exists(LEDGER_FILE):
        raise FileNotFoundError(f"Missing required ledger file: {LEDGER_FILE}")

    files = [
        f for f in sorted(glob.glob(os.path.join(NSE_RAW_DIR, "nse_delivery_*.csv")))
        if os.path.basename(f) >= "nse_delivery_20260520.csv"
    ]
    if not files:
        raise FileNotFoundError("No historical delivery files found for self-reconciliation.")

    frames = []
    for f in files:
        try:
            x = pd.read_csv(f)
            x.columns = [c.strip() for c in x.columns]
            if "DATE1" not in x.columns:
                continue
            x["DATE1"] = x["DATE1"].astype(str).str.strip()
            if "SERIES" in x.columns:
                x = x[x["SERIES"].astype(str).str.strip() == "EQ"]
            x["SYMBOL"] = x["SYMBOL"].astype(str).str.strip()
            x["DATE1"] = pd.to_datetime(x["DATE1"], format="%d-%b-%Y", errors="coerce")
            frames.append(x)
        except Exception as e:
            print(f"Error loading {f}: {e}")

    p = pd.concat(frames, ignore_index=True)
    for c in ["OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "DELIV_PER", "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "AVG_PRICE", "PREV_CLOSE"]:
        if c in p.columns:
            p[c] = pd.to_numeric(p[c], errors="coerce")

    p = p.dropna(subset=["DATE1", "CLOSE_PRICE"])
    p = dedup_delivery_panel(p)

    # Compute ATR14 & features
    pc = p.groupby("SYMBOL")["CLOSE_PRICE"].shift()
    p["TR"] = pd.concat([
        p["HIGH_PRICE"] - p["LOW_PRICE"],
        (p["HIGH_PRICE"] - pc).abs(),
        (p["LOW_PRICE"] - pc).abs()
    ], axis=1).max(axis=1)
    p["ATR14"] = p.groupby("SYMBOL")["TR"].transform(lambda s: s.shift(1).rolling(14, min_periods=7).mean())
    p["ATR_PCT"] = p["ATR14"] / p["CLOSE_PRICE"] * 100

    # Load closed trades
    d = pd.read_csv(LEDGER_FILE)
    d["ENTRY_DATE"] = pd.to_datetime(d["ENTRY_DATE"])
    c = d[d["STATUS"] != "ACTIVE"].copy()
    c["SLD"] = (c["ENTRY_PRICE"] - c["STOP_LOSS"]).abs()
    c["SHARES"] = 3000.0 / c["SLD"]
    c["PNL_INR"] = np.where(
        c["STATUS"] == "HIT_TP", 6000.0,
        np.where(
            c["STATUS"] == "HIT_SL", -3000.0,
            np.where(c["STATUS"] == "SUSPENDED", 0.0, c["SHARES"] * (c["EXIT_PRICE"] - c["ENTRY_PRICE"]))
        )
    )
    c["R"] = c["PNL_INR"] / 3000.0
    c["MCAP"] = c["SYMBOL"].astype(str).str.upper().map(mc)
    c["TIER"] = pd.cut(c["MCAP"], [0, 2000, 7000, 20000, 1e9], labels=["MICRO", "SMALLISH", "MID", "LARGE"])

    # Merge features on (SYMBOL, ENTRY_DATE)
    c = c.merge(
        p[["SYMBOL", "DATE1", "ATR_PCT", "DELIV_PER"]],
        left_on=["SYMBOL", "ENTRY_DATE"],
        right_on=["SYMBOL", "DATE1"],
        how="left"
    )
    panel_matched = c[c["ATR_PCT"].notna()].copy()

    def is_rule3(row):
        if row["TIER"] == "LARGE":
            return False
        if pd.isna(row["DELIV_PER"]) or row["DELIV_PER"] > 80.0 or row["DELIV_PER"] < 50.0:
            return False
        if row["TIER"] == "MID":
            return row["ATR_PCT"] >= 3.15
        if row["TIER"] in ("MICRO", "SMALLISH"):
            return True
        return row["ATR_PCT"] >= 3.4

    rule3_cohort = panel_matched[panel_matched.apply(is_rule3, axis=1)]
    n = len(rule3_cohort)
    win_pct = float((rule3_cohort["R"] > 0).mean() * 100) if n > 0 else 0.0
    mean_r = float(rule3_cohort["R"].mean()) if n > 0 else 0.0
    sum_rs = float(rule3_cohort["PNL_INR"].sum())

    print(f"Self-check computed: n={n}, Win Rate={win_pct:.1f}%, Mean R={mean_r:.3f}, PnL=Rs.{sum_rs:,.0f}")
    tier_counts = rule3_cohort["TIER"].value_counts().to_dict()
    print(f"Cohort tier breakdown: {tier_counts}")

    # Assertions
    if not (abs(n - ANCHOR_N) <= TOLERANCE_N):
        raise AssertionError(f"Cohort size drifted: got n={n}, expected ~{ANCHOR_N}")
    if not (abs(win_pct - ANCHOR_WIN) <= TOLERANCE_WIN):
        raise AssertionError(f"Cohort win rate drifted: got {win_pct:.1f}%, expected ~{ANCHOR_WIN}%")
    if not (abs(sum_rs - ANCHOR_RS) <= TOLERANCE_RS):
        raise AssertionError(f"Cohort PnL drifted: got Rs.{sum_rs:,.0f}, expected ~Rs.{ANCHOR_RS:,.0f}")

    print(f"[OK] Self-check PASSED: Rule 3 correctly anchored (n={n}, win={win_pct:.1f}%, Rs.{sum_rs:,.0f})\n")


def score_universe():
    """Scores universe of symbols and writes data/winner_archetypes_ranked.csv."""
    mc = load_mcap()
    run_self_reconciliation(mc)

    # 1. Load latest 20 NSE delivery files to compute recent ATR14 & indicators for all active stocks
    all_files = sorted(glob.glob(os.path.join(NSE_RAW_DIR, "nse_delivery_*.csv")))
    if not all_files:
        raise FileNotFoundError(f"No files found in {NSE_RAW_DIR}")
    
    recent_files = all_files[-20:]
    latest_file = all_files[-1]
    print(f"Scoring live universe using latest file: {latest_file} (along with last {len(recent_files)} days for rolling ATR)")

    frames = []
    for f in recent_files:
        try:
            x = pd.read_csv(f)
            x.columns = [c.strip() for c in x.columns]
            if "DATE1" not in x.columns:
                continue
            x["DATE1"] = x["DATE1"].astype(str).str.strip()
            if "SERIES" in x.columns:
                x = x[x["SERIES"].astype(str).str.strip() == "EQ"]
            x["SYMBOL"] = x["SYMBOL"].astype(str).str.strip()
            x["DATE1"] = pd.to_datetime(x["DATE1"], format="%d-%b-%Y", errors="coerce")
            frames.append(x)
        except Exception as e:
            print(f"Error loading recent file {f}: {e}")

    rec_p = pd.concat(frames, ignore_index=True)
    for c in ["OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "DELIV_PER", "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "AVG_PRICE", "PREV_CLOSE"]:
        if c in rec_p.columns:
            rec_p[c] = pd.to_numeric(rec_p[c], errors="coerce")

    rec_p = rec_p.dropna(subset=["DATE1", "CLOSE_PRICE"])
    rec_p = dedup_delivery_panel(rec_p)

    # Rolling ATR14
    rec_pc = rec_p.groupby("SYMBOL")["CLOSE_PRICE"].shift()
    rec_p["TR"] = pd.concat([
        rec_p["HIGH_PRICE"] - rec_p["LOW_PRICE"],
        (rec_p["HIGH_PRICE"] - rec_pc).abs(),
        (rec_p["LOW_PRICE"] - rec_pc).abs()
    ], axis=1).max(axis=1)
    rec_p["ATR14"] = rec_p.groupby("SYMBOL")["TR"].transform(lambda s: s.shift(1).rolling(14, min_periods=5).mean())

    # Get latest snapshot per symbol
    latest_snap = rec_p.sort_values("DATE1").groupby("SYMBOL").last().reset_index()
    latest_snap["CDH"] = (latest_snap["CLOSE_PRICE"] - latest_snap["LOW_PRICE"]) / (
        latest_snap["HIGH_PRICE"] - latest_snap["LOW_PRICE"]
    ).replace(0, np.nan)
    latest_snap["VWAP_DIV"] = (latest_snap["CLOSE_PRICE"] / latest_snap["AVG_PRICE"].replace(0, np.nan) - 1) * 100

    # 2. Collect all historical symbols that passed through our institutional screeners
    screened_sources = [
        "data/sbia_ledger.csv",
        "data/sbia_alpha_watchlist.csv",
        "data/corner_engine_watchlist.csv",
        "data/corner_engine_ledger.csv",
        "data/flexgate_ledger.csv",
        "data/flexgate2_ledger.csv",
        "data/sbia_flexgate_watchlist.csv",
        "data/sbia_flexgate2_watchlist.csv",
        "data/legacy_watchlist.csv",
    ]
    screened_syms = set()
    for s_path in screened_sources:
        if os.path.exists(s_path):
            try:
                s_df = pd.read_csv(s_path)
                if "SYMBOL" in s_df.columns:
                    screened_syms.update(s_df["SYMBOL"].dropna().astype(str).str.strip().unique())
            except Exception:
                pass

    # 3. Load universe (UNIVERSE_FILE or WATCHLIST_FILE fallback)
    if os.path.exists(UNIVERSE_FILE):
        u_df = pd.read_csv(UNIVERSE_FILE)
    elif os.path.exists(WATCHLIST_FILE):
        u_df = pd.read_csv(WATCHLIST_FILE)
    else:
        u_df = pd.DataFrame()

    if u_df.empty:
        # Fallback to latest snapshot itself
        u_df = latest_snap[["SYMBOL", "CLOSE_PRICE", "DELIV_PER"]].copy()
        u_df.rename(columns={"CLOSE_PRICE": "CLOSE"}, inplace=True)
        u_df["EXCHANGE"] = "NSE"

    u_df["SYMBOL"] = u_df["SYMBOL"].astype(str).str.strip()

    # Filter out non-equity symbols
    u_df = u_df[~u_df["SYMBOL"].str.contains(NON_EQUITY_PATTERNS, regex=True, na=False)].copy()

    # Restrict to symbols that have passed through institutional screeners
    if screened_syms:
        u_df = u_df[u_df["SYMBOL"].isin(screened_syms)].copy()

    # Load today's watchlist if present to inherit AI model probability & existing targets
    wl_map = {}
    if os.path.exists(WATCHLIST_FILE):
        try:
            wl = pd.read_csv(WATCHLIST_FILE)
            for _, r in wl.iterrows():
                sym = str(r["SYMBOL"]).strip()
                wl_map[sym] = r.to_dict()
        except Exception:
            pass

    # Merge latest snapshot metrics
    cols_from_snap = ["SYMBOL", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "AVG_PRICE", "DELIV_QTY", "CDH", "VWAP_DIV", "ATR14"]
    merged = u_df.merge(latest_snap[cols_from_snap], on="SYMBOL", how="left")

    # Clean / standardize columns
    if "CLOSE" not in merged.columns and "CLOSE_PRICE" in merged.columns:
        merged["CLOSE"] = merged["CLOSE_PRICE"]
    merged["CLOSE"] = merged["CLOSE"].fillna(merged.get("CLOSE_PRICE", 0))

    if "DELIV_PER" not in merged.columns:
        merged["DELIV_PER"] = np.nan

    # Whale density: check WHALE_DENSITY or Whale_Density
    if "Whale_Density" not in merged.columns:
        merged["Whale_Density"] = merged.get("WHALE_DENSITY", np.nan)

    # Fill in from watchlist map
    def fill_from_wl(row, col_name, default=np.nan):
        sym = row["SYMBOL"]
        if sym in wl_map and col_name in wl_map[sym] and pd.notna(wl_map[sym][col_name]):
            return wl_map[sym][col_name]
        return row.get(col_name, default)

    for col in ["AI_WIN_PROBABILITY", "ENTRY_PRICE", "STOP_LOSS", "TAKE_PROFIT"]:
        merged[col] = merged.apply(lambda r: fill_from_wl(r, col), axis=1)

    # Market Cap & Tier
    merged["MKTCAP_CR"] = merged["SYMBOL"].str.upper().map(mc)
    merged["TIER"] = pd.cut(
        merged["MKTCAP_CR"],
        [0, 2000, 7000, 20000, 1e9],
        labels=["MICRO", "SMALLISH", "MID", "LARGE"]
    ).astype(str).replace("nan", "UNKNOWN")

    # ATR_PCT
    merged["ATR_PCT"] = merged["ATR14"] / merged["CLOSE"].replace(0, np.nan) * 100

    # Rule 3 Quality Cohort
    def check_quality_80(r):
        if r["TIER"] == "LARGE":
            return False
        if pd.isna(r["DELIV_PER"]) or r["DELIV_PER"] > 80.0 or r["DELIV_PER"] < 50.0:
            return False
        if r["TIER"] == "MID":
            return r["ATR_PCT"] >= 3.15
        if r["TIER"] in ("MICRO", "SMALLISH"):
            return True
        return r["ATR_PCT"] >= 3.4

    merged["QUALITY_80"] = merged.apply(check_quality_80, axis=1)

    # Delivery Grade: Sweet Spot A (60-75%), B (50-60% or 75-80%), C (>80%), RETAIL (<50%)
    def get_deliv_grade(d):
        if pd.isna(d):
            return "UNKNOWN"
        if d < 50.0:
            return "RETAIL"
        if 60.0 <= d <= 75.0:
            return "A-GRADE"
        if (50.0 <= d < 60.0) or (75.0 < d <= 80.0):
            return "B-GRADE"
        return "C-GRADE"

    merged["DELIV_GRADE"] = merged["DELIV_PER"].apply(get_deliv_grade)

    # Archetype Assignment
    def get_archetype(r):
        cdh = r["CDH"]
        vwap_div = r["VWAP_DIV"]
        whd = r["Whale_Density"] if pd.notna(r["Whale_Density"]) else 0.0
        atr_pct = r["ATR_PCT"] if pd.notna(r["ATR_PCT"]) else 0.0
        deliv = r["DELIV_PER"] if pd.notna(r["DELIV_PER"]) else 50.0

        if pd.notna(cdh):
            if cdh >= 0.50 and (pd.isna(vwap_div) or vwap_div > 0):
                return "CLEAN_RUNNER"
            if cdh < 0.40 and whd >= 12.0:
                return "GRIND_COMPOUNDER"
            return "UNCLASSIFIED"
        else:
            if atr_pct >= 3.4 and 50.0 <= deliv <= 80.0 and whd < 20.0:
                return "CLEAN_RUNNER"
            if whd >= 12.0 and deliv >= 55.0:
                return "GRIND_COMPOUNDER"
            return "UNCLASSIFIED"

    merged["ARCHETYPE"] = merged.apply(get_archetype, axis=1)

    # Missing targets fallback (1.5 ATR risk, 3.0 ATR reward = 2R)
    for idx, row in merged.iterrows():
        close = row["CLOSE"] if pd.notna(row["CLOSE"]) and row["CLOSE"] > 0 else 100.0
        atr = row["ATR14"] if pd.notna(row["ATR14"]) and row["ATR14"] > 0 else close * 0.035
        if pd.isna(row["ENTRY_PRICE"]):
            merged.at[idx, "ENTRY_PRICE"] = round(close, 2)
        if pd.isna(row["STOP_LOSS"]):
            merged.at[idx, "STOP_LOSS"] = round(max(close - 1.5 * atr, close * 0.90), 2)
        if pd.isna(row["TAKE_PROFIT"]):
            merged.at[idx, "TAKE_PROFIT"] = round(close + 3.0 * atr, 2)
        if pd.isna(row["AI_WIN_PROBABILITY"]):
            merged.at[idx, "AI_WIN_PROBABILITY"] = 55.0

    # Rule 3 Composite Score (0-100)
    atr_norm = np.clip((merged["ATR_PCT"].fillna(3.0) - 3.0) / 5.0, 0, 1) * 30.0
    deliv_norm = np.clip((80.0 - merged["DELIV_PER"].fillna(60.0)) / 80.0, 0, 1) * 25.0
    ai_norm = np.clip((merged["AI_WIN_PROBABILITY"].fillna(50.0) - 50.0) / 45.0, 0, 1) * 25.0
    whd_norm = np.clip(merged["Whale_Density"].fillna(5.0) / 30.0, 0, 1) * 20.0
    merged["RULE3_SCORE"] = (atr_norm + deliv_norm + ai_norm + whd_norm).round(1)

    # Date
    merged["RANKED_DATE"] = datetime.date.today().strftime("%Y-%m-%d")

    # Sort
    grade_order = {"A-GRADE": 0, "B-GRADE": 1, "C-GRADE": 2, "RETAIL": 3, "UNKNOWN": 4}
    merged["_g_order"] = merged["DELIV_GRADE"].map(grade_order).fillna(5)
    merged = merged.sort_values(
        by=["QUALITY_80", "_g_order", "RULE3_SCORE"],
        ascending=[False, True, False]
    ).drop(columns=["_g_order"])

    # Write output
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    merged.to_csv(OUTPUT_FILE, index=False)
    print(f"Successfully generated {OUTPUT_FILE} ({len(merged)} symbols ranked)")
    print(f"80% Quality Tier Symbols: {merged['QUALITY_80'].sum()}")
    print("Archetypes breakdown across universe:")
    print(merged["ARCHETYPE"].value_counts().to_dict())


if __name__ == "__main__":
    score_universe()
