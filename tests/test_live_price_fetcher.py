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
    render_risk_radar_banner,
    get_live_quotes,
    CACHE_FILE,
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


def test_render_risk_radar_banner_deduplication():
    """Verify multiple tranches of the same symbol collapse into 1 badge with [N tranches] tag."""
    synthetic_summary = {
        "total_active": 2,
        "unique_symbols": 1,
        "near_sl": [
            {
                "symbol": "INDUSTOWER",
                "engine": "FlexGate",
                "cmp": 369.35,
                "effective_sl": 361.91,
                "sl_dist_pct": 2.0,
            },
            {
                "symbol": "INDUSTOWER",
                "engine": "FlexGate",
                "cmp": 369.35,
                "effective_sl": 363.10,
                "sl_dist_pct": 1.7,
            },
        ],
        "near_tp": [],
        "breached_sl": [],
        "healthy_count": 0,
        "last_updated": "12:30 PM",
    }
    card = render_risk_radar_banner(synthetic_summary)
    assert card is not None
    badge_container = card.children[1]
    badges = badge_container.children
    # Should only have 1 badge because INDUSTOWER was deduplicated
    assert len(badges) == 1
    badge_text = badges[0].children
    assert "INDUSTOWER" in badge_text
    assert "[2 tranches]" in badge_text
    # Should show the tighter SL distance (1.7% / 363.10)
    assert "1.7%" in badge_text
    assert "363.10" in badge_text


def test_get_live_quotes_stale_while_revalidate(monkeypatch):
    """Verify Stale-While-Revalidate returns cached quotes instantly even when expired."""
    import time
    import json
    import live_price_fetcher

    refreshed_called = []
    monkeypatch.setattr(
        live_price_fetcher,
        "_trigger_background_refresh",
        lambda symbols, max_workers=10: refreshed_called.append(symbols)
    )

    test_quotes = {
        "GRASIM": {
            "cmp": 3190.0,
            "exchange": "NSE",
            "timestamp": time.time() - 600,  # 10 minutes old
            "time_str": "12:00:00 PM",
            "source": "cached",
        }
    }
    payload = {
        "timestamp": time.time() - 600,
        "updated_at": "10 minutes ago",
        "quotes": test_quotes,
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    t0 = time.perf_counter()
    quotes = get_live_quotes(["GRASIM"], force_refresh=False, ttl_seconds=300)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Must return immediately (< 500ms) without blocking
    assert elapsed_ms < 500
    assert "GRASIM" in quotes
    assert quotes["GRASIM"]["cmp"] == 3190.0
    assert len(refreshed_called) == 1

