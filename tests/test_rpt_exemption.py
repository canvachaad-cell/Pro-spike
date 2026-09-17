import pytest
import sys
import os
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.bse_rpt_scraper import EXEMPTION_RE

CASES = [
    ("Non-applicability of Related Party Disclosure under regulation 23(9) of SEBI LODR", True),
    ("As per Regulation 23(9), the company is not required to submit this disclosure", True),
    ("Regulation 23 (9) shall not apply to the company...", True),
    ("Board Meeting intimation. Agenda item 4 is not applicable for this quarter.", False),
    ("Remarks on approval by audit committee: Not Applicable", False),
    ("Pledge disclosure filed. Regulation 31 compliance complete. Not applicable otherwise.", False),
]

@pytest.mark.parametrize("text,expected", CASES)
def test_exemption_regex(text, expected):
    assert bool(EXEMPTION_RE.search(text)) == expected
