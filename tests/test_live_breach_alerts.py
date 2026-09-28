import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alert_engine import (
    scan_live_breaches,
    dedup_live_breaches,
    build_live_breach_digest,
    dispatch_live_breach_alerts,
    _live_breach_worker,
    _BREACH_PRIORITY_MAP,
)


@pytest.fixture
def synthetic_summary():
    """Create a realistic portfolio proximity summary with multiple tranches and urgency tiers."""
    return {
        "total_active": 4,
        "unique_symbols": 3,
        "breached_sl": [
            {
                "engine": "FlexGate",
                "symbol": "INDUSTOWER",
                "urgency": "BREACHED_SL",
                "cmp": 358.65,
                "effective_sl": 361.91,
                "take_profit": None,
                "entry_price": 384.50,
                "pnl_pct": -6.72,
                "sl_dist_pct": -0.91,
                "tp_dist_pct": None,
                "badge_text": "🚨 BELOW SL (361.91)",
            },
            {
                "engine": "FlexGate",
                "symbol": "INDUSTOWER",
                "urgency": "BREACHED_SL",
                "cmp": 358.65,
                "effective_sl": 363.10,
                "take_profit": None,
                "entry_price": 380.00,
                "pnl_pct": -5.62,
                "sl_dist_pct": -1.24,
                "tp_dist_pct": None,
                "badge_text": "🚨 BELOW SL (363.10)",
            },
        ],
        "near_sl": [
            {
                "engine": "SBIA Alpha",
                "symbol": "GROWW",
                "urgency": "NEAR_SL",
                "cmp": 183.04,
                "effective_sl": 180.45,
                "take_profit": 215.28,
                "entry_price": 192.00,
                "pnl_pct": -4.67,
                "sl_dist_pct": 1.41,
                "tp_dist_pct": 17.61,
                "badge_text": "⚠️ 1.4% to SL",
            }
        ],
        "near_tp": [
            {
                "engine": "Corner Spike",
                "symbol": "TARGETCORP",
                "urgency": "HIT_TP",
                "cmp": 510.00,
                "effective_sl": 450.00,
                "take_profit": 500.00,
                "entry_price": 460.00,
                "pnl_pct": 10.87,
                "sl_dist_pct": 11.76,
                "tp_dist_pct": -2.00,
                "badge_text": "🚀 HIT TARGET (500.00)",
            }
        ],
        "healthy_count": 5,
        "last_updated": "03:40 PM",
    }


def test_scan_live_breaches_filtering_and_grouping(synthetic_summary):
    """Verify scan_live_breaches filters actionable tiers and combines multi-tranche positions."""
    rows = scan_live_breaches(synthetic_summary)
    assert len(rows) == 3  # INDUSTOWER (grouped), GROWW, TARGETCORP

    # Find grouped INDUSTOWER
    indus = next(r for r in rows if r["symbol"] == "INDUSTOWER")
    assert indus["engine"] == "FlexGate"
    assert indus["urgency"] == "BREACHED_SL"
    assert indus["tranche_count"] == 2
    # Should pick worst sl_dist_pct (-1.24 is worse than -0.91)
    assert indus["effective_sl"] == 363.10


def test_build_live_breach_digest(synthetic_summary):
    """Verify notification digest builds formatted card with correct counters, badges, and tranches."""
    rows = scan_live_breaches(synthetic_summary)
    title, body = build_live_breach_digest(rows)

    assert "🚨 Pro Spike — 3 live breach alert(s)" in title
    assert "Breached SL: 1" in body
    assert "Near SL: 1" in body
    assert "Hit TP: 1" in body
    assert "*INDUSTOWER* [FlexGate · 2 tranches]" in body
    assert "CMP ₹358.65 | SL ₹363.10" in body
    assert "*GROWW* [SBIA Alpha]" in body


def test_dedup_live_breaches_prevents_duplicate_dispatch():
    """Verify dedup_live_breaches suppresses already-dispatched breach events for the day."""
    rows = [
        {"engine": "FlexGate", "symbol": "INDUSTOWER", "urgency": "BREACHED_SL"},
        {"engine": "SBIA Alpha", "symbol": "GROWW", "urgency": "NEAR_SL"},
    ]

    with patch("alert_engine.load_state", return_value={
        "live_breach_history": {
            "2026-09-28|FlexGate|INDUSTOWER|BREACHED_SL": "2026-09-28 10:00:00"
        }
    }):
        with patch("alert_engine.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-09-28"
            new_rows, history = dedup_live_breaches(rows)
            assert len(new_rows) == 1
            assert new_rows[0]["symbol"] == "GROWW"
            assert new_rows[0]["_dedup_key"] == "2026-09-28|SBIA Alpha|GROWW|NEAR_SL"


def test_dispatch_live_breach_alerts_dry_run(synthetic_summary):
    """Verify dispatch_live_breach_alerts executes cleanly in dry_run mode without network calls."""
    with patch("alert_engine.send_ntfy") as mock_ntfy:
        with patch("alert_engine.send_email") as mock_mail:
            with patch("alert_engine.send_whatsapp") as mock_wa:
                count = dispatch_live_breach_alerts(dry_run=True, summary=synthetic_summary)
                assert count == 3
                mock_ntfy.assert_not_called()
                mock_mail.assert_not_called()
                mock_wa.assert_not_called()


def test_live_breach_worker_non_blocking_execution(synthetic_summary):
    """Verify _live_breach_worker runs without throwing exceptions."""
    with patch("alert_engine.dispatch_live_breach_alerts") as mock_dispatch:
        _live_breach_worker(summary=synthetic_summary)
        mock_dispatch.assert_called_once_with(summary=synthetic_summary)
