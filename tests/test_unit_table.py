import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.bse_rpt_scraper import UNIT_TO_CR

def test_unit_table_internal_consistency():
    # Anchored to arithmetic identities, not to any PDF:
    assert UNIT_TO_CR["crore"] == 1.0
    assert UNIT_TO_CR["lakh"] == pytest.approx(0.01)          # 100 lakh = 1 Cr
    assert UNIT_TO_CR["million"] == pytest.approx(0.1)        # 10 million = 1 Cr
    assert UNIT_TO_CR["thousand"] == pytest.approx(0.00001)   # 100k thousand = 1 Cr
    assert UNIT_TO_CR["rupees"] == pytest.approx(1e-7)        # 1 Cr = 1e7 rupees
    
    # Cross-checks: ratios between entries
    assert UNIT_TO_CR["lakh"] * 100 == pytest.approx(UNIT_TO_CR["crore"])
    assert UNIT_TO_CR["million"] * 10 == pytest.approx(UNIT_TO_CR["crore"])
    assert UNIT_TO_CR["thousand"] * 1000 == pytest.approx(UNIT_TO_CR["lakh"])
