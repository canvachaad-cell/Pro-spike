import pandas as pd
import numpy as np
import json
import os
import sys
import io
import joblib
import yfinance as yf
from datetime import datetime, timedelta
from config import Config

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BACKFILL_MODE = False
INPUT_FILE = Config.COMBINED_FILE if BACKFILL_MODE else "data/combined_dashboard_live.csv"
CONFIG_FILE = "institutional_config.json"
FLEXGATE_ARCHIVE = "data/flexgate_archive.csv"

def score_signals(signals):
    signals = signals.copy()
    signals["MOMENTUM_RAW"] = signals.apply(lambda x: x["DELIV_PER"] / x["DELIV_PER_3M"] if pd.notna(x.get("DELIV_PER_3M")) and x["DELIV_PER_3M"] > 0 else 0, axis=1)
    signals["FOOTPRINT_RAW"] = signals.apply(lambda x: x["DELIVERY_TURNOVER"] / x["DELIVERY_TURNOVER_3M"] if pd.notna(x.get("DELIVERY_TURNOVER_3M")) and x["DELIVERY_TURNOVER_3M"] > 0 else 0, axis=1)
    signals["STABILITY_RAW"] = signals.apply(lambda x: x["ATW"] / x["ATW_3M"] if pd.notna(x.get("ATW_3M")) and x["ATW_3M"] > 0 else 0, axis=1)
    return signals

def calculate_atr_and_risk(df, equity=1000000, max_cap_pct=0.10, is_flexgate=False):
    """Fetch ATR14 from yfinance and calculate Risk parameters"""
    if df.empty:
        return df
        
    df = df.copy()
    symbol_to_yf = {}
    for idx, row in df.iterrows():
        sym = row["SYMBOL"]
        exch = row.get("EXCHANGE", "NSE")
        suffix = ".BO" if exch == "BSE" else ".NS"
        symbol_to_yf[sym] = f"{sym}{suffix}"
        
    yf_symbols = list(set(symbol_to_yf.values()))
    
    print(f"Fetching ATR data for {len(yf_symbols)} symbols ({'FlexGate' if is_flexgate else 'Alpha'})...")
    try:
        data = yf.download(yf_symbols, period="1mo", progress=False, group_by="ticker")
        
        df["ATR14"] = np.nan
        df["STOP_LOSS"] = np.nan
        df["TAKE_PROFIT"] = np.nan
        df["CHANDELIER_EXIT"] = np.nan
        df["REC_POS_SIZE_INR"] = np.nan
        
        max_position = equity * max_cap_pct
        
        for idx, row in df.iterrows():
            sym = row["SYMBOL"]
            close_px = row["CLOSE"]
            
            try:
                yf_sym = symbol_to_yf[sym]
                if len(yf_symbols) == 1:
                    ticker_df = data
                else:
                    ticker_df = data[yf_sym]
                    
                if not ticker_df.empty and len(ticker_df) >= 14:
                    high_low = ticker_df['High'] - ticker_df['Low']
                    high_close = np.abs(ticker_df['High'] - ticker_df['Close'].shift())
                    low_close = np.abs(ticker_df['Low'] - ticker_df['Close'].shift())
                    ranges = pd.concat([high_low, high_close, low_close], axis=1)
                    true_range = np.max(ranges, axis=1)
                    atr14 = true_range.rolling(14).mean().iloc[-1]
                    
                    if pd.notna(atr14) and atr14 > 0:
                        df.at[idx, "ATR14"] = atr14
                        
                        if is_flexgate:
                            # Path B Risk: 3.0x ATR Chandelier Exit
                            df.at[idx, "CHANDELIER_EXIT"] = close_px - (3.0 * atr14)
                            df.at[idx, "STOP_LOSS"] = close_px - (3.0 * atr14) # Used for position sizing calculation
                        else:
                            # Path A Risk: 2.0x SL, 4.0x TP
                            df.at[idx, "STOP_LOSS"] = close_px - (2.0 * atr14)
                            df.at[idx, "TAKE_PROFIT"] = close_px + (4.0 * atr14)
                            
                        sl_dist = 2.0 * atr14 if not is_flexgate else 3.0 * atr14
                        shares_to_buy = (equity * 0.015) / sl_dist
                        pos_size_inr = shares_to_buy * close_px
                        
                        if pos_size_inr > max_position:
                            pos_size_inr = max_position
                            
                        df.at[idx, "REC_POS_SIZE_INR"] = pos_size_inr
            except Exception:
                pass
                
    except Exception as e:
        print(f"Failed to fetch ATR data: {e}")
        
    return df

def process_flexgate_engine(df, current_date):
    """Path B: The Optimized Flex-Gate Base-Loading Engine"""
    print("\nProcessing Path B: SBIA Flex-Gate Base-Loading Engine...")
    
    # Needs metrics
    required = ["DELIV_PER", "DELIVERY_TURNOVER", "ATW", "DELIVERY_TURNOVER_1M", "DELIVERY_TURNOVER_3M", "ATW_1M", "ATW_3M", "DELIV_PER_1M", "VWAP", "VWAP_1M"]
    for c in required:
        if c not in df.columns:
            df[c] = 0.0
            
    # Phase 1: Consolidation
    p1 = (
        (df['DELIV_PER'] >= 50) &
        (df['DELIVERY_TURNOVER'] >= 500_000) &
        (df['ATW'] >= 25_000) &
        (df['DELIVERY_TURNOVER_1M'] > 0) & (df['DELIVERY_TURNOVER_1M'] <= df['DELIVERY_TURNOVER_3M']) &
        (df['ATW_1M'] > 0) & (df['ATW_1M'] <= df['ATW_3M'])
    )
    
    # Phase 2: Anomaly Tripwires
    trigger_a = (df['DELIVERY_TURNOVER_1M'] > 0) & (df['DELIVERY_TURNOVER'] > 2.0 * df['DELIVERY_TURNOVER_1M'])
    
    whale_density = (df['ATW'] / df['VWAP'].replace(0, np.nan)).fillna(0)
    whale_density_1m = (df['ATW_1M'] / df['VWAP_1M'].replace(0, np.nan)).fillna(0)
    trigger_b = (whale_density_1m > 0) & (whale_density > 2.0 * whale_density_1m)
    
    trigger_c = (df['DELIV_PER_1M'] > 0) & (df['DELIV_PER'] > 1.5 * df['DELIV_PER_1M'])
    
    # Accumulation Alert
    df['IS_FLEXGATE_ALERT'] = p1 & (trigger_a | trigger_b | trigger_c)
    
    # Filter to today's alerts
    todays_alerts = df[df['IS_FLEXGATE_ALERT']].copy()
    todays_alerts['DATE'] = current_date
    
    # Append to archive and get 10-day history
    if os.path.exists(FLEXGATE_ARCHIVE):
        archive = pd.read_csv(FLEXGATE_ARCHIVE)
        archive['DATE'] = pd.to_datetime(archive['DATE'])
        # Drop today if already exists to prevent dupes
        archive = archive[archive['DATE'] != current_date]
    else:
        archive = pd.DataFrame(columns=todays_alerts.columns)
        
    updated_archive = pd.concat([archive, todays_alerts], ignore_index=True)
    updated_archive.to_csv(FLEXGATE_ARCHIVE, index=False)
    
    # Find all unique trading dates in archive
    all_dates = sorted(updated_archive['DATE'].unique())
    last_10_dates = all_dates[-10:] if len(all_dates) >= 10 else all_dates
    
    # Filter to last 10 dates
    recent_archive = updated_archive[updated_archive['DATE'].isin(last_10_dates)]
    
    # Phase 3: Exactly TWO accumulation alerts in trailing 10 days
    trigger_counts = recent_archive['SYMBOL'].value_counts()
    exact_two_symbols = trigger_counts[trigger_counts == 2].index.tolist()
    
    flexgate_pool = todays_alerts[todays_alerts['SYMBOL'].isin(exact_two_symbols)].copy()
    
    if flexgate_pool.empty:
        print("Path B: No stocks passed Phase 3 (Exactly TWO alerts) today.")
        # Proceed with empty pool so the 45-day archiving logic still runs and preserves history
        
    # ML Bouncer for FlexGate
    # Need SIS Score. FlexGate uses the same SIS scoring as Alpha, so we calculate it here.
    flexgate_pool = score_signals(flexgate_pool)
    flexgate_pool["MOMENTUM_SCORE"] = flexgate_pool["MOMENTUM_RAW"].rank(pct=True, na_option="bottom")
    flexgate_pool["FOOTPRINT_SCORE"] = flexgate_pool["FOOTPRINT_RAW"].rank(pct=True, na_option="bottom")
    flexgate_pool["STABILITY_SCORE"] = flexgate_pool["STABILITY_RAW"].rank(pct=True, na_option="bottom")
    
    flexgate_pool["SIS"] = ((flexgate_pool['STABILITY_SCORE'] + 1)**0.50 * 
                            (flexgate_pool['FOOTPRINT_SCORE'] + 1)**0.30 * 
                            (flexgate_pool['MOMENTUM_SCORE'] + 1)**0.20) - 1
                            
    # Ensure Implied Trades
    flexgate_pool['Implied_Trades'] = (flexgate_pool['DELIVERY_TURNOVER'] / flexgate_pool['ATW'].replace(0, np.nan)).fillna(0)
    flexgate_pool['Whale_Density'] = (flexgate_pool['ATW'] / flexgate_pool['VWAP'].replace(0, np.nan)).fillna(0)
    
    # Apply ML Gate & Ranges (97_ULTIMATE_PATTERNS Precision Constraints)
    sanity_mask = (
        (flexgate_pool['DELIVERY_TURNOVER'] > 10000000) &  # > 1 Cr
        (flexgate_pool['Whale_Density'] > 0)
    )
    
    if os.path.exists("shadow_box_model.pkl"):
        model = joblib.load("shadow_box_model.pkl")
        features = ['SIS', 'Whale_Density', 'Implied_Trades']
        pred_mask = flexgate_pool[features].notna().all(axis=1)
        
        flexgate_pool["AI_WIN_PROBABILITY"] = 0.0
        if pred_mask.sum() > 0:
            flexgate_pool.loc[pred_mask, "AI_WIN_PROBABILITY"] = model.predict_proba(flexgate_pool.loc[pred_mask, features])[:, 1] * 100
        
        # We no longer block based on AI probability. We just use sanity mask.
        flexgate_final = flexgate_pool[sanity_mask].copy()
        # Add a flag for UI
        flexgate_final["AI_APPROVED"] = flexgate_final["AI_WIN_PROBABILITY"] >= 60.0
    else:
        print("WARNING: shadow_box_model.pkl missing! FlexGate running without AI.")
        flexgate_final = flexgate_pool[sanity_mask].copy()
        flexgate_final["AI_WIN_PROBABILITY"] = 0
        flexgate_final["AI_APPROVED"] = False
        
    flexgate_final = calculate_atr_and_risk(flexgate_final, is_flexgate=True)
    flexgate_final = flexgate_final.sort_values(by=["AI_WIN_PROBABILITY"], ascending=[False])
    
    FLEXGATE_FILE = "data/sbia_flexgate_watchlist.csv"
    if os.path.exists(FLEXGATE_FILE):
        old_flexgate = pd.read_csv(FLEXGATE_FILE)
        old_flexgate["DATE"] = pd.to_datetime(old_flexgate["DATE"], errors="coerce")
        # Keep only the last 45 calendar days
        cutoff = pd.to_datetime(current_date) - pd.Timedelta(days=45)
        old_flexgate = old_flexgate[old_flexgate["DATE"] >= cutoff]
        flexgate_final = pd.concat([old_flexgate, flexgate_final], ignore_index=True)

    # Clean up and save
    if not flexgate_final.empty:
        flexgate_final["DATE"] = pd.to_datetime(flexgate_final["DATE"], errors="coerce")
        flexgate_final = flexgate_final.drop_duplicates(subset=["DATE", "SYMBOL", "EXCHANGE"], keep="last")
        flexgate_final = flexgate_final.sort_values(by=["DATE", "AI_WIN_PROBABILITY"], ascending=[False, False])
        
    # Integrate FlexGate Ledger to track SL simulation
    from ledger_manager import update_flexgate_ledger
    print("Updating FlexGate Trade Ledger and applying SL filters...")
    
    # FIX: Only pass AI APPROVED signals into the active trading ledger
    approved_signals = flexgate_final[flexgate_final["AI_APPROVED"] == True].copy()
    
    flexgate_active, flexgate_ledger_full = update_flexgate_ledger(approved_signals, df, ledger_path="data/flexgate_ledger.csv")
    
    flexgate_active.to_csv(FLEXGATE_FILE, index=False)
    print(f"Path B Output: {len(flexgate_active)} signals currently active in {FLEXGATE_FILE}")
    return flexgate_active


def run_scoring():
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} missing.")
        sys.exit(1)
        
    df = pd.read_csv(INPUT_FILE)
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    if "ISIN" in df.columns:
        # Strict Equity Gate: Only process common equities (ISO 6166: 'INE' prefix)
        df = df[df["ISIN"].fillna("").str.startswith("INE")].copy()
    
    current_date = df["DATE"].dropna().max()
    
    # -----------------------------------------------------------------
    # PATH A: Alpha Markups Engine (12-Condition + ML)
    # -----------------------------------------------------------------
    print("Processing Path A: SBIA Institutional Alpha Engine...")
    from progressive_screener import ProgressiveSpiker
    
    all_scored = []
    for dt in sorted(df["DATE"].dropna().unique()):
        day_df = df[df["DATE"] == dt].copy()
        signals = ProgressiveSpiker(day_df).get_signals()
        if signals.empty: continue
        scored_df = score_signals(signals)
        if scored_df.empty: continue
        scored_df["DATE"] = dt
        all_scored.append(scored_df)

    archive_path = "data/survivors_archive.csv"
    if all_scored:
        scored_df = pd.concat(all_scored, ignore_index=True)
        keep_cols = ["DATE", "SYMBOL", "EXCHANGE", "CLOSE", "DELIV_PER", "ATW", "DELIVERY_TURNOVER",
                     "MOMENTUM_RAW", "FOOTPRINT_RAW", "STABILITY_RAW"]
        hist = scored_df[keep_cols].copy()
        
        if not BACKFILL_MODE and os.path.exists(archive_path):
            old_hist = pd.read_csv(archive_path)
            old_hist["DATE"] = pd.to_datetime(old_hist["DATE"], errors="coerce")
            hist = pd.concat([old_hist, hist], ignore_index=True)
            
        hist = hist.dropna(subset=["DATE", "SYMBOL", "EXCHANGE"])
        hist = hist.drop_duplicates(subset=["DATE", "SYMBOL", "EXCHANGE"], keep="last")
        hist = hist.sort_values(["DATE", "SYMBOL"], ascending=[False, True])
        
        if not BACKFILL_MODE:
            hist.to_csv(archive_path, index=False)
    else:
        if os.path.exists(archive_path):
            hist = pd.read_csv(archive_path)
            hist["DATE"] = pd.to_datetime(hist["DATE"], errors="coerce")
        else:
            hist = pd.DataFrame()
            
    legacy_pool = pd.DataFrame()
    sbia_pool = pd.DataFrame()
    
    if not hist.empty:
        dates_sorted = sorted(hist["DATE"].unique(), reverse=True)
        legacy_cutoff = dates_sorted[min(30, len(dates_sorted))-1]
        legacy_pool = hist[hist["DATE"] >= legacy_cutoff].copy()
        
        sbia_cutoff = dates_sorted[min(45, len(dates_sorted))-1]
        sbia_pool = hist[hist["DATE"] >= sbia_cutoff].copy()

        df_latest = df.set_index("SYMBOL")
        update_cols = ["CLOSE", "DELIV_PER", "DELIVERY_TURNOVER", "ATW", 
                       "DELIV_PER_1W", "DELIV_PER_1M", "DELIV_PER_3M", 
                       "DELIVERY_TURNOVER_1W", "DELIVERY_TURNOVER_1M", "DELIVERY_TURNOVER_3M", 
                       "ATW_1W", "ATW_1M", "ATW_3M"]
                       
        for p in [legacy_pool, sbia_pool]:
            for col in update_cols:
                if col in df_latest.columns:
                    p[col] = p["SYMBOL"].map(df_latest[col]).fillna(p.get(col, 0))

        legacy_pool = score_signals(legacy_pool)
        sbia_pool = score_signals(sbia_pool)
        
        for p in [legacy_pool, sbia_pool]:
            
            p["MOMENTUM_SCORE"] = p["MOMENTUM_RAW"].rank(pct=True, na_option="bottom")
            p["FOOTPRINT_SCORE"] = p["FOOTPRINT_RAW"].rank(pct=True, na_option="bottom")
            p["STABILITY_SCORE"] = p["STABILITY_RAW"].rank(pct=True, na_option="bottom")
            p["DATE"] = pd.to_datetime(p["DATE"], errors="coerce")
            p["TRIGGER_COUNT_30D"] = 1
            for idx, row in p.iterrows():
                window_start = row["DATE"] - pd.Timedelta(days=30)
                count = p[(p["SYMBOL"] == row["SYMBOL"]) & (p["DATE"] <= row["DATE"]) & (p["DATE"] > window_start)].shape[0]
                p.at[idx, "TRIGGER_COUNT_30D"] = count
            
            p["AI_SCORE"] = (
                0.6 * p["STABILITY_SCORE"] +
                0.1 * p["MOMENTUM_SCORE"] +
                0.1 * p["FOOTPRINT_SCORE"] +
                0.2 * (1.0 / p["TRIGGER_COUNT_30D"])
            )
            
            # Legacy binary combined score
            p["COMBINED_SCORE"] = (p["DELIV_PER_1W"] > p["DELIV_PER_1M"]).astype(int) + \
                                  (p["DELIVERY_TURNOVER"] > p["DELIVERY_TURNOVER_1M"]).astype(int) + \
                                  (p["ATW"] > p["ATW_1M"]).astype(int)
                                  
            p["SIS"] = ((p['STABILITY_SCORE'] + 1)**0.50 * 
                        (p['FOOTPRINT_SCORE'] + 1)**0.30 * 
                        (p['MOMENTUM_SCORE'] + 1)**0.20) - 1
                                
            p['Whale_Density'] = (p['ATW'] / p['DELIVERY_TURNOVER'].replace(0, np.nan)).fillna(0) * 100000
            p['Implied_Trades'] = (p['DELIVERY_TURNOVER'] / p['ATW'].replace(0, np.nan)).fillna(0)
            
            if os.path.exists("shadow_box_model.pkl"):
                model = joblib.load("shadow_box_model.pkl")
                features = ['SIS', 'Whale_Density', 'Implied_Trades']
                pred_mask = p[features].notna().all(axis=1)
                
                p["AI_WIN_PROBABILITY"] = 0.0
                if pred_mask.sum() > 0:
                    p.loc[pred_mask, "AI_WIN_PROBABILITY"] = model.predict_proba(p.loc[pred_mask, features])[:, 1] * 100
            else:
                p["AI_WIN_PROBABILITY"] = 0
                
        # Path A Baseline Sanity
        sanity_mask = (
            (sbia_pool['DELIVERY_TURNOVER'] > 10000000) &  # > 1 Cr
            (sbia_pool['Whale_Density'] > 0)
        )
        
        final_sbia_mask = sanity_mask & (sbia_pool["AI_WIN_PROBABILITY"] >= 60.0)
        sbia_alpha_watchlist = sbia_pool[final_sbia_mask].copy()
            
        # Apply Legacy Hard Gates
        print("Applying Legacy Institutional Ranking Gates...")
        legacy_mask = (legacy_pool["AI_SCORE"] > 0.60) & (legacy_pool["SIS"].between(0.15, 0.93))
        legacy_pool = legacy_pool[legacy_mask].copy()

        legacy_watchlist = calculate_atr_and_risk(legacy_pool, is_flexgate=False)
        sbia_alpha_watchlist = calculate_atr_and_risk(sbia_alpha_watchlist, is_flexgate=False)
        
        legacy_watchlist = legacy_watchlist.sort_values(by=["SIS"], ascending=[False])
        sbia_alpha_watchlist = sbia_alpha_watchlist.sort_values(by=["AI_WIN_PROBABILITY"], ascending=[False])
        
        # Integrate SBIA Ledger to track SL/TP
        from ledger_manager import update_sbia_ledger
        print("Updating SBIA Trade Ledger and applying target filters...")
        sbia_alpha_active, sbia_ledger_full = update_sbia_ledger(sbia_alpha_watchlist, df, ledger_path="data/sbia_ledger.csv")

        legacy_watchlist.to_csv("data/legacy_watchlist.csv", index=False)
        # Restore Dash product output (regression in 80006526): the Dash Dashboard
        # and Institutional Signals pages read this file.
        legacy_watchlist.to_csv("data/active_signals_ranked.csv", index=False)
        sbia_alpha_active.to_csv("data/sbia_alpha_watchlist.csv", index=False)

        # Backward compatibility for existing dashboard code expecting this file
        sbia_alpha_active.to_csv("data/sbia_institutional_watchlist.csv", index=False)

        print(f"Path A Output: {len(sbia_alpha_active)} ACTIVE signals written to data/sbia_alpha_watchlist.csv")
    else:
        print("Path A Output: No signals generated.")

    # -----------------------------------------------------------------
    # Freshness probe for the nightly diagnostic gate: today's raw signals.
    # Rewritten on EVERY run (header-only on zero-signal days) so that
    # diagnostic.py can detect when this engine has crashed.
    # -----------------------------------------------------------------
    probe_frames = []
    for pool in (legacy_pool, sbia_pool):
        if isinstance(pool, pd.DataFrame) and not pool.empty and "DATE" in pool.columns:
            probe_frames.append(pool[pool["DATE"] == current_date])
    if probe_frames:
        today_probe = pd.concat(probe_frames, ignore_index=True)
        if not today_probe.empty:
            today_probe = today_probe.drop_duplicates(subset=["DATE", "SYMBOL", "EXCHANGE"], keep="last")
    else:
        today_probe = pd.DataFrame()
    today_probe.to_csv("data/signal_scores_today.csv", index=False)

    # -----------------------------------------------------------------
    # PATH B: FlexGate Base-Loading Engine
    # -----------------------------------------------------------------
    # Uses the full universe from df, isolating exactly to current date.
    df_today = df[df["DATE"] == current_date].copy()
    if not df_today.empty:
        process_flexgate_engine(df_today, current_date)
    else:
        print("Path B Output: No today's data to process.")

if __name__ == "__main__":
    run_scoring()
