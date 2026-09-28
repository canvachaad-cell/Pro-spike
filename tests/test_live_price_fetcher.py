import pytest
import sys
import os

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live_price_fetcher import (
    _fetch_single_quote,
    compute_trade_proximity,
    get_portfolio_proximity_summary,
    get_active_symbols,
)


def test_fetch_single_quote_nse():
    """Verify live quote fetching for a liquid NSE ticker returns positive float."""
    sym, px = _fetch_single_quote("GRASIM", "NSE")
    assert sym == "GRASIM"
    assert px is not None
    assert isinstance(px, float)
    assert px > 0


def test_fetch_single_quote_bse():
    """Verify live quote fetching for a BSE ticker returns positive float."""
    sym, px = _fetch_single_quote("EXHICON", "BSE")
    assert sym == "EXHICON"
    assert px is not None
    assert isinstance(px, float)
    assert px > 0


def test_compute_trade_proximity_thresholds():
    """Verify real-time SL/TP proximity classifications and badge urgency tiers."""
    # 1. Breached SL
    breach = compute_trade_proximity(symbol="TEST", entry_price=105.0, stop_loss=100.0, take_profit=120.0, cmp=95.0)
    assert breach["urgency"] == "BREACHED_SL"
    assert "BELOW SL" in breach["badge_text"]

    # 2. Near SL (within 3.0%)
    # sl = 100.0, cmp = 102.0 -> (102 - 100) / 102 = 1.96%
    near_sl = compute_trade_proximity(symbol="TEST", entry_price=105.0, stop_loss=100.0, take_profit=120.0, cmp=102.0)
    assert near_sl["urgency"] == "NEAR_SL"
    assert near_sl["sl_dist_pct"] == pytest.approx(1.96, rel=1e-2)
    assert "to SL" in near_sl["badge_text"]

    # 3. Near TP (within 3.0%)
    # tp = 120.0, cmp = 118.0 -> (120 - 118) / 118 = 1.69%
    near_tp = compute_trade_proximity(symbol="TEST", entry_price=105.0, stop_loss=100.0, take_profit=120.0, cmp=118.0)
    assert near_tp["urgency"] == "NEAR_TP"
    assert "to TP" in near_tp["badge_text"]

    # 4. Hit TP
    hit_tp = compute_trade_proximity(symbol="TEST", entry_price=105.0, stop_loss=100.0, take_profit=120.0, cmp=125.0)
    assert hit_tp["urgency"] == "HIT_TP"
    assert "HIT TARGET" in hit_tp["badge_text"]

    # 5. Healthy buffer
    # cmp = 110.0, sl = 100.0 -> dist = (110 - 100) / 110 = 9.09% > 3.0%
    healthy = compute_trade_proximity(symbol="TEST", entry_price=105.0, stop_loss=100.0, take_profit=130.0, cmp=110.0)
    assert healthy["urgency"] == "HEALTHY"
    assert "buffer" in healthy["badge_text"]


def test_get_portfolio_proximity_summary_contract():
    """Verify get_portfolio_proximity_summary returns complete contract keys."""
    summary = get_portfolio_proximity_summary(force_refresh=False)
    assert "total_active" in summary
    assert "unique_symbols" in summary
    assert "near_sl" in summary
    assert "near_tp" in summary
    assert "breached_sl" in summary
    assert "healthy_count" in summary
    assert "quotes" in summary
    assert isinstance(summary["quotes"], dict)
    assert summary["total_active"] >= 0
