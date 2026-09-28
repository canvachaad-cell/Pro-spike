import os
import sys
import pandas as pd
import numpy as np
import pytest

# Ensure Dash app is initialized before importing pages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dash_app_v2
from dash_pages.institutional_signals import _fmt_date
from ledger_manager import _hydrate_missing_active_watchlist


def test_fmt_date_mixed_strings():
    """Verify _fmt_date parses both full timestamp strings and date-only strings without NaT coercion."""
    s = pd.Series([
        "2026-09-25 00:00:00",
        "2026-09-24 00:00:00",
        "2026-09-23",
        "2026-09-21",
        "2026-08-31 00:00:00",
    ])
    formatted = _fmt_date(s)
    expected = [
        "25 Sep 2026",
        "24 Sep 2026",
        "23 Sep 2026",
        "21 Sep 2026",
        "31 Aug 2026",
    ]
    assert list(formatted) == expected


def test_alpha_watchlist_data_completeness():
    """Verify data/sbia_alpha_watchlist.csv has 10 complete rows with non-null SIS and DATE."""
    path = os.path.join("data", "sbia_alpha_watchlist.csv")
    assert os.path.exists(path), f"Watchlist {path} not found"
    df = pd.read_csv(path)
    assert len(df) == 10, f"Expected 10 rows in alpha watchlist, got {len(df)}"

    # Verify no NaN values in essential columns
    for col in ["SYMBOL", "DATE", "SIS", "AI_WIN_PROBABILITY", "ENTRY_PRICE", "STOP_LOSS", "TAKE_PROFIT"]:
        assert col in df.columns, f"Missing required column {col}"
        nan_count = df[col].isna().sum()
        assert nan_count == 0, f"Column {col} has {nan_count} unexpected NaN values"

    # Specific stock sanity checks
    nath = df[df["SYMBOL"] == "NATHBIOGEN"].iloc[0]
    assert float(nath["SIS"]) > 0.90, f"Expected NATHBIOGEN SIS > 0.90, got {nath['SIS']}"

    groww = df[df["SYMBOL"] == "GROWW"].iloc[0]
    assert float(groww["SIS"]) < 0.10, f"Expected GROWW SIS < 0.10, got {groww['SIS']}"
    assert float(groww["AI_WIN_PROBABILITY"]) > 90.0, f"Expected GROWW AI prob > 90%, got {groww['AI_WIN_PROBABILITY']}"


def test_alpha_table_sorting():
    """Verify that descending date sorting places GROWW on 31 Aug 2026 at the bottom."""
    path = os.path.join("data", "sbia_alpha_watchlist.csv")
    df = pd.read_csv(path)

    df["_DATE_SORT"] = pd.to_datetime(df["DATE"], format="mixed", errors="coerce")
    df_sorted = df.sort_values(by="_DATE_SORT", ascending=False).reset_index(drop=True)

    # First row should be from 25 Sep 2026
    assert df_sorted.iloc[0]["_DATE_SORT"] == pd.Timestamp("2026-09-25")
    # Last row should be GROWW from 31 Aug 2026
    assert df_sorted.iloc[-1]["SYMBOL"] == "GROWW"
    assert df_sorted.iloc[-1]["_DATE_SORT"] == pd.Timestamp("2026-08-31")


def test_hydrate_active_watchlist_mixed_dates():
    """Verify _hydrate_missing_active_watchlist handles mixed dates and resolves SIS."""
    active_ledger = pd.DataFrame([{
        "SYMBOL": "TESTSYM",
        "ENTRY_DATE": "2026-09-20",
        "ENTRY_PRICE": 100.0,
        "STOP_LOSS": 94.0,
        "TAKE_PROFIT": 112.0,
        "ENTRY_AI_PROB": 70.0,
        "ENTRY_SIS": 0.85,
        "STATUS": "ACTIVE"
    }])
    filtered_wl = pd.DataFrame([{
        "SYMBOL": "EXISTING",
        "DATE": "2026-09-25 00:00:00",
        "DATE_DT": pd.Timestamp("2026-09-25"),
        "SIS": 0.92,
    }])
    latest_px = pd.DataFrame([{"SYMBOL": "TESTSYM", "CLOSE": 101.5, "EXCHANGE": "NSE"}])

    hydrated = _hydrate_missing_active_watchlist(
        filtered_wl, active_ledger, latest_px, is_flexgate=False
    )
    assert len(hydrated) == 2
    test_row = hydrated[hydrated["SYMBOL"] == "TESTSYM"].iloc[0]
    assert test_row["SIS"] == 0.85
    assert test_row["DATE"] == "2026-09-20"
