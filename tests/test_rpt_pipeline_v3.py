import os
import sys
from datetime import datetime
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.bse_rpt_scraper import generate_date_windows, RPT_ANNOUNCEMENT_RE
from conviction_scorer import ConvictionScorer, _gate_scores
from fundamental_fetcher import FundamentalFetcher
from rpt_fetcher import RPTFetcher


def test_generate_date_windows():
    windows = generate_date_windows(start_date_str="20230101", end_date_str="20240630", chunk_days=350)
    assert len(windows) >= 2
    # Reverse chronological order: first window ends at end_date
    assert windows[0][1] == "20240630"
    # Last window starts at start_date
    assert windows[-1][0] == "20230101"

    for w_from, w_to in windows:
        d_from = datetime.strptime(w_from, "%Y%m%d")
        d_to = datetime.strptime(w_to, "%Y%m%d")
        span = (d_to - d_from).days
        assert span <= 350, f"Window {w_from}-{w_to} exceeds 350 days: {span}"
        assert d_to >= d_from


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Related Party Transactions for the half year ended March 31, 2024", True),
        ("Regulation 23(9) Disclosure of RPT", True),
        ("Compliance under Reg 23(9) of SEBI LODR Regulations, 2015", True),
        ("Disclosure under Reg. 23(9) of SEBI (LODR) Regulations, 2015", True),
        ("Submission of RPT details for H2 FY24", True),
        ("Outcome of Board Meeting held on May 15, 2024", False),
        ("Financial Results for the quarter and year ended March 31, 2024", False),
        ("Shareholding Pattern for the quarter ended December 31, 2023", False),
    ],
)
def test_rpt_announcement_regex(text, expected):
    assert bool(RPT_ANNOUNCEMENT_RE.search(text)) == expected


def test_scorer_exempt_status():
    scorer = ConvictionScorer()
    fund = {
        "market_cap_cr": 8000.0,
        "op_lev_ratio": 2.5,
        "pledge_trend": [0.0],
        "pledge_direction": "flat",
        "interest_coverage_trend": "improving",
        "roice_pct": 22.0,
        "fcf_pat_ratio": 1.1,
        "rpt_status": "EXEMPT",
        "rpt_pct": None,
    }

    # Verify gate score gives 10/10 for EXEMPT
    gate = _gate_scores(fund)
    assert gate["rpt_pct"] == 10

    # Verify full score runs in 6-Metric Mode and does not treat rpt as missing
    res = scorer.score(fund)
    assert res["rpt_data_missing"] is False
    assert res["rpt_fetch_status"] == "EXEMPT"
    assert "rpt_pct" not in res["not_applicable_metrics"]
    assert "6-Metric Mode" in res["data_completeness"]["label"]
    assert res["score"] is not None
    assert res["score"] >= 75
