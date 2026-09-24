"""
Winner Archetypes Data Module (winner_archetype_data.py)
========================================================
Pure data loading, caching, and feature enrichment for /winner-archetypes.
Zero side-effects, zero writes to production data.
"""

import os
from functools import lru_cache
import pandas as pd
import numpy as np

RANKED_FILE = os.path.join("data", "winner_archetypes_ranked.csv")
ALPHA_WATCHLIST = os.path.join("data", "sbia_alpha_watchlist.csv")
SBIA_LEDGER = os.path.join("data", "sbia_ledger.csv")
NON_EQUITY_GATE = {"GILT5BETA", "GILT10BETA"}


@lru_cache(maxsize=16)
def _read_csv_cached(path: str, mtime: float):
    """Cached CSV reader keyed on file modification time."""
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _load(path: str):
    """Safe cached reader that invalidates automatically when the file changes."""
    if not os.path.exists(path):
        return None
    try:
        return _read_csv_cached(path, os.path.getmtime(path))
    except OSError:
        return None


def _gate(df: pd.DataFrame) -> pd.DataFrame:
    """Filter out non-equity symbols."""
    if df is None or df.empty or "SYMBOL" not in df.columns:
        return df
    return df[~df["SYMBOL"].isin(NON_EQUITY_GATE)].copy()


def _ensure_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Derive visual range coordinates and missing indicator columns."""
    if df is None or df.empty:
        return df

    df = df.copy()

    # ATR_PCT
    if "ATR_PCT" not in df.columns and {"ATR14", "CLOSE"}.issubset(df.columns):
        df["ATR_PCT"] = df["ATR14"] / df["CLOSE"].replace(0, np.nan) * 100

    # Range & Entry fills for visual risk/reward track
    span = df.get("TAKE_PROFIT", 0) - df.get("STOP_LOSS", 0)
    span = span.replace(0, np.nan)

    if "RANGE_FILL_PCT" not in df.columns:
        curr_dist = df.get("CLOSE", 0) - df.get("STOP_LOSS", 0)
        df["RANGE_FILL_PCT"] = (curr_dist / span * 100).clip(0, 100).fillna(50.0)

    if "ENTRY_FILL_PCT" not in df.columns:
        entry_dist = df.get("ENTRY_PRICE", 0) - df.get("STOP_LOSS", 0)
        df["ENTRY_FILL_PCT"] = (entry_dist / span * 100).clip(0, 100).fillna(33.0)

    # Format numeric defaults
    if "AI_WIN_PROBABILITY" in df.columns:
        df["AI_WIN_PROBABILITY"] = pd.to_numeric(df["AI_WIN_PROBABILITY"], errors="coerce").fillna(55.0)
    else:
        df["AI_WIN_PROBABILITY"] = 55.0

    if "Whale_Density" not in df.columns:
        df["Whale_Density"] = df.get("WHALE_DENSITY", np.nan)

    return df


def _derive_watchlist_fallback(df: pd.DataFrame) -> pd.DataFrame:
    """If ranked file is missing, apply Rule 3 proxy to alpha watchlist."""
    if df is None or df.empty:
        return df

    df = df.copy()
    df["SOURCE_NAME"] = "Watchlist Fallback"

    # ATR_PCT
    if "ATR_PCT" not in df.columns and {"ATR14", "CLOSE"}.issubset(df.columns):
        df["ATR_PCT"] = df["ATR14"] / df["CLOSE"].replace(0, np.nan) * 100

    # Archetype heuristic
    def get_archetype_proxy(r):
        atr_pct = r.get("ATR_PCT", 0.0)
        deliv = r.get("DELIV_PER", 50.0)
        whd = r.get("Whale_Density", 0.0)
        if atr_pct >= 3.4 and deliv <= 80 and whd < 20.0:
            return "CLEAN_RUNNER"
        if whd >= 12.0 and deliv >= 55.0:
            return "GRIND_COMPOUNDER"
        return "UNCLASSIFIED"

    df["ARCHETYPE"] = df.apply(get_archetype_proxy, axis=1)

    # Quality 80 proxy
    def check_q80_proxy(r):
        deliv = r.get("DELIV_PER", np.nan)
        atr_pct = r.get("ATR_PCT", np.nan)
        if pd.isna(deliv) or deliv > 80.0 or deliv < 50.0:
            return False
        return atr_pct >= 3.4 if pd.notna(atr_pct) else False

    def get_proxy_deliv_grade(d):
        if pd.isna(d) or d < 50.0:
            return "RETAIL"
        if 60.0 <= d <= 75.0:
            return "A-GRADE"
        if (50.0 <= d < 60.0) or (75.0 < d <= 80.0):
            return "B-GRADE"
        return "C-GRADE"

    df["QUALITY_80"] = df.apply(check_q80_proxy, axis=1)
    df["DELIV_GRADE"] = df.get("DELIV_PER", pd.Series(50.0, index=df.index)).apply(get_proxy_deliv_grade)
    df["RULE3_SCORE"] = 75.0

    return _ensure_derived(df)


def load_signals() -> pd.DataFrame:
    """
    Loads ranked signals.
    Priority 1: data/winner_archetypes_ranked.csv (Full ranked universe)
    Priority 2: data/sbia_alpha_watchlist.csv (Watchlist fallback)
    """
    if os.path.exists(RANKED_FILE):
        df = _load(RANKED_FILE)
        if df is not None and not df.empty:
            df = df.copy()
            df["SOURCE_NAME"] = "Ranked Universe"
            return _ensure_derived(_gate(df))

    # Priority 2: Watchlist fallback
    df = _load(ALPHA_WATCHLIST)
    if df is not None and not df.empty:
        return _derive_watchlist_fallback(_gate(df))

    return pd.DataFrame()


def _streak(sym: str, closed_df: pd.DataFrame) -> int:
    """Calculate consecutive HIT_TP winning streak for a symbol."""
    trades = closed_df[closed_df["SYMBOL"] == sym].sort_values("ENTRY_DATE")["STATUS"].tolist()
    n = 0
    for s in reversed(trades):
        if s == "HIT_TP":
            n += 1
        else:
            break
    return n


def build_radar_df(ledger_df: pd.DataFrame, today: pd.Timestamp = None) -> pd.DataFrame:
    """
    Builds the 14-Day Re-Entry Radar dataset.
    Rule: Lockout is OUTCOME-CONDITIONAL (blocked after LOSS, permitted after WIN).
    """
    if ledger_df is None or ledger_df.empty:
        return pd.DataFrame()

    if today is None:
        today = pd.Timestamp.now().normalize()

    df = ledger_df.copy()
    df["EXIT_DATE"] = pd.to_datetime(df["EXIT_DATE"], errors="coerce")
    df["ENTRY_DATE"] = pd.to_datetime(df["ENTRY_DATE"], errors="coerce")

    active_syms = set(df[df["STATUS"] == "ACTIVE"]["SYMBOL"])
    closed = df[df["STATUS"].isin(["HIT_TP", "HIT_SL", "MOMENTUM_LOST"])].copy()

    if closed.empty:
        return pd.DataFrame()

    # Most recent closed trade per symbol
    latest = closed.sort_values("EXIT_DATE").groupby("SYMBOL").last().reset_index()
    latest["days_since_exit"] = (today - latest["EXIT_DATE"]).dt.days.fillna(999).astype(int)

    # State Assignment
    latest["RADAR_STATE"] = "ELIGIBLE"

    # Outcome-conditional: blocked if last trade was HIT_SL or ML_LOSS (net loss)
    # Calculate R if needed
    if "PNL_INR" not in latest.columns and {"ENTRY_PRICE", "STOP_LOSS", "EXIT_PRICE"}.issubset(latest.columns):
        sld = (latest["ENTRY_PRICE"] - latest["STOP_LOSS"]).abs().replace(0, 1.0)
        shares = 3000.0 / sld
        latest["PNL_INR"] = np.where(
            latest["STATUS"] == "HIT_TP", 6000.0,
            np.where(
                latest["STATUS"] == "HIT_SL", -3000.0,
                np.where(latest["STATUS"] == "SUSPENDED", 0.0, shares * (latest["EXIT_PRICE"] - latest["ENTRY_PRICE"]))
            )
        )
    elif "PNL_INR" not in latest.columns:
        latest["PNL_INR"] = np.where(latest["STATUS"] == "HIT_TP", 6000.0, np.where(latest["STATUS"] == "HIT_SL", -3000.0, 0.0))

    latest["R"] = latest["PNL_INR"] / 3000.0

    # Locked if HIT_SL or losing MOMENTUM_LOST
    loss_mask = (latest["STATUS"] == "HIT_SL") | ((latest["STATUS"] == "MOMENTUM_LOST") & (latest["R"] < 0))
    latest.loc[loss_mask, "RADAR_STATE"] = "LOCKED"

    # Overridden to OPEN if currently in active trade
    latest.loc[latest["SYMBOL"].isin(active_syms), "RADAR_STATE"] = "OPEN"

    # Winning streak: 2+ consecutive HIT_TPs
    latest["WIN_STREAK"] = latest["SYMBOL"].apply(lambda s: _streak(s, closed))
    streak_mask = (latest["WIN_STREAK"] >= 2) & (latest["RADAR_STATE"] == "ELIGIBLE")
    latest.loc[streak_mask, "RADAR_STATE"] = "STREAK"

    # Sort priority: LOCKED first, then OPEN, then STREAK, then ELIGIBLE
    priority = {"LOCKED": 0, "OPEN": 1, "STREAK": 2, "ELIGIBLE": 3}
    latest["_p"] = latest["RADAR_STATE"].map(priority).fillna(9)
    res = latest.sort_values(["_p", "days_since_exit"]).drop(columns=["_p"])

    return res
