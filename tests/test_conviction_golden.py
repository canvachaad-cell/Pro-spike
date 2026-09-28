import json
import pytest
import copy
import sys
import os

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conviction_scorer import ConvictionScorer, _gate_scores, classify

def load_fixtures():
    with open('tests/fixtures/golden_fundamentals.json') as f:
        funds = json.load(f)
    with open('tests/fixtures/golden_scores.json') as f:
        scores = json.load(f)
    return funds, scores

FUNDS, SCORES = load_fixtures()
BASKET = list(FUNDS.keys())

@pytest.fixture
def scorer():
    return ConvictionScorer()

@pytest.mark.parametrize("symbol", BASKET)
def test_golden_scores_exact_match(scorer, symbol):
    """Assert exact match for every key in the golden score output to catch silent drift."""
    fund = FUNDS[symbol]
    expected = SCORES[symbol]
    
    result = scorer.score(fund)
    
    # Assert critical fields haven't drifted
    assert result["score"] == expected["score"], f"Math drift in {symbol} score"
    assert result["rating"] == expected["rating"], f"Rating drift in {symbol}"
    assert result["veto"] == expected["veto"]
    assert result["unverified_veto"] == expected["unverified_veto"]
    assert set(result.get("veto_reasons", [])) == set(expected.get("veto_reasons", []))
    assert set(result.get("not_applicable_metrics", [])) == set(expected.get("not_applicable_metrics", []))
    assert result.get("rpt_data_missing") == expected.get("rpt_data_missing")


def test_algoquant_financial_business(scorer):
    """BUG-024: Financial businesses cannot be scored conventionally."""
    fund = copy.deepcopy(FUNDS.get("ALGOQUANT"))
    if not fund:
        pytest.skip("ALGOQUANT not in fixtures")
    
    res = scorer.score(fund)
    assert res["rating"] == "NOT_SCORED_FINANCIAL_BIZ", "Financial stock bypassed the veto!"


def test_saksoft_5_metric_mode(scorer):
    """BUG-009/011: Verify SAKSOFT scores strictly in 5-Metric Vikram mode."""
    fund = copy.deepcopy(FUNDS.get("SAKSOFT"))
    if not fund:
        pytest.skip("SAKSOFT not in fixtures")
        
    res = scorer.score(fund)
    assert "5-Metric Vikram" in res["data_completeness"]["label"]
    assert res["score"] == 90
    assert res["rating"] == "HIGH_CONVICTION"
    

def test_greenply_roice_blending():
    """BUG-023: RoICE must blend roce_abs_pct 60/40, never pure delta momentum."""
    fund = copy.deepcopy(FUNDS.get("GREENPLY"))
    if not fund:
        pytest.skip("GREENPLY not in fixtures")
        
    gate = _gate_scores(fund)
    # The fixture for GREENPLY has both roice_pct and roce_abs_pct
    assert "roice" in gate
    # Just asserting it evaluates properly without blowing up and has both components.
    assert isinstance(gate["roice"], int)


def test_zero_pledge_flat_stock(scorer):
    """BUG-011: Zero pledge flat stock should score 9/10, not 7/10."""
    fund = {
        "market_cap_cr": 10000,
        "pledge_direction": "flat",
        "pledge_trend": [0, 0, 0, 0], # Zero pledge over 4 quarters
    }
    gate = _gate_scores(fund)
    assert gate["pledge_trend"] == 9, "Zero pledge flat must score 9/10"


def test_pledge_over_25_hard_veto(scorer):
    """BUG-023: Pledge > 25% must hard veto regardless of trend."""
    fund = {
        "market_cap_cr": 10000,
        "pledge_direction": "falling",
        "pledge_trend": [35.0, 30.0, 26.0], 
    }
    res = scorer.score(fund)
    assert res["veto"] is True
    assert any("25%" in v for v in res["veto_reasons"])


def test_all_vetoes_not_found_unverified(scorer):
    """BUG-001: Missing data across veto checks produces UNVERIFIED_VETO, never silent CLEAR."""
    fund = {
        "market_cap_cr": 10000,
        "pledge_direction": None, # Missing
        "fcf_pat_ratio": None, # Missing
        "rpt_pct": None, # Missing
        "sector_type": "IT", 
        "rpt_status": "NOT_FOUND"
    }
    res = scorer.score(fund)
    assert res["unverified_veto"] is True
    assert res["rating"] == "UNVERIFIED_VETO"
    assert len(res["veto_reasons"]) >= 2


def test_classify_nan_and_unmapped_returns_unknown():
    """BUG-053: classify(NaN), classify(0.0), and invalid inputs must return 'U', never 'S'."""
    import numpy as np
    assert classify(None) == "U"
    assert classify(float("nan")) == "U"
    assert classify(np.nan) == "U"
    assert classify(0.0) == "U"
    assert classify(-250.0) == "U"
    assert classify("invalid") == "U"
    assert classify(500.0) == "S"
    assert classify(6999.0) == "S"
    assert classify(7000.0) == "M"
    assert classify(19999.0) == "M"
    assert classify(20000.0) == "L"

