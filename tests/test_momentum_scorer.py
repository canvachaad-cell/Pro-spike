import os
import sys
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from momentum_scorer import (
    MomentumScorer,
    score_delivery_pct,
    score_delivery_turnover,
    score_float_absorbed,
    score_mae,
    MOMENTUM_WEIGHTS_B,
)


def test_momentum_weights_b_sum():
    assert pytest.approx(sum(MOMENTUM_WEIGHTS_B.values()), 0.0001) == 1.0


def test_score_delivery_pct():
    assert score_delivery_pct(98.0) == 10
    assert score_delivery_pct(92.0) == 8
    assert score_delivery_pct(88.0) == 6
    assert score_delivery_pct(82.0) == 3
    assert score_delivery_pct(75.0) == 0
    assert score_delivery_pct(None) == 0


def test_score_delivery_turnover():
    assert score_delivery_turnover(4.2) == 10  # in 3.5 - 5.0 Cr
    assert score_delivery_turnover(3.0) == 7   # in 2.5 - 3.5 Cr
    assert score_delivery_turnover(6.0) == 7   # in 5.0 - 7.5 Cr
    assert score_delivery_turnover(2.0) == 4   # in 1.5 - 2.5 Cr
    assert score_delivery_turnover(0.5) == 1   # < 1.5 Cr
    assert score_delivery_turnover(15.0) == 1  # > 10 Cr
    assert score_delivery_turnover(None) == 0


def test_score_float_absorbed():
    assert score_float_absorbed(4.0) == 10  # >= 3.5%
    assert score_float_absorbed(2.8) == 8   # >= 2.5%
    assert score_float_absorbed(1.8) == 6   # >= 1.5%
    assert score_float_absorbed(1.2) == 3   # >= 1.0%
    assert score_float_absorbed(0.5) == 0   # < 1.0%
    assert score_float_absorbed(None) == 0


def test_score_mae():
    assert score_mae(0.5) == 10
    assert score_mae(0.0) == 10
    assert score_mae(-0.4) == 8
    assert score_mae(-1.2) == 6
    assert score_mae(-2.0) == 3
    assert score_mae(-3.5) == 0
    assert score_mae(None) == 5


def test_veto_blocks_momentum_scorer():
    scorer = MomentumScorer()
    signal_row = {
        "DELIV_PER": 95.0,
        "DELIVERY_TURNOVER": 42000000.0,  # 4.2 Cr
        "FLOAT_ABSORBED_PCT": 3.0,
        "MAE": -0.5,
    }
    # Stock with 35% pledge (violates 25% max)
    fund_vetoed = {
        "market_cap_cr": 1500.0,
        "pledge_direction": "flat",
        "pledge_trend": [35.0, 35.0],
        "fcf_pat_ratio": 1.0,
    }
    res = scorer.score(signal_row, fund_vetoed)
    assert res["blocked_by_veto"] is True
    assert res["momentum_tier"] == "BLOCKED"
    assert res["momentum_score"] == 0
    assert len(res["veto_reasons"]) > 0


def test_clean_stock_scoring():
    scorer = MomentumScorer()
    signal_row = {
        "DELIV_PER": 92.0,
        "DELIVERY_TURNOVER": 40000000.0,  # 4.0 Cr
        "FLOAT_ABSORBED_PCT": 2.6,
        "MAE": -0.6,
    }
    fund_clean = {
        "market_cap_cr": 1200.0,
        "free_float_cr": 100.0,
        "pledge_direction": "flat",
        "pledge_trend": [0.0, 0.0],
        "fcf_pat_ratio": 1.2,
        "interest_coverage_trend": "improving",
        "op_lev_ratio": 2.5,
        "roice_pct": 25.0,
        "roce_abs_pct": 20.0,
    }
    res = scorer.score(signal_row, fund_clean)
    assert res["blocked_by_veto"] is False
    assert res["momentum_score"] >= 70
    assert res["momentum_tier"] in ("HIGH", "ELITE")
    assert "part_a_breakdown" in res
    assert "part_b_breakdown" in res
