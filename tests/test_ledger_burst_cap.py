import pytest
import pandas as pd
import sys
import os

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ledger_manager import check_signal_eligibility


def test_burst_governor_single_date_cap():
    """BUG-058: Only top 5 candidates per date are admitted; 6th+ hit CROWDING_BURST_CAP."""
    empty_ledger = pd.DataFrame(columns=['ENTRY_DATE', 'SYMBOL', 'STATUS', 'EXIT_DATE', 'EXIT_PRICE'])
    dt = "2026-03-27"
    
    candidates = [f"SYM_{i}" for i in range(1, 9)]
    accepted = []
    rejected = []
    
    same_day_count = 0
    for sym in candidates:
        eligible, reason = check_signal_eligibility(
            empty_ledger, sym, dt, cooldown_days=14, same_day_entries=same_day_count, max_daily_burst=5
        )
        if eligible:
            accepted.append(sym)
            same_day_count += 1
        else:
            rejected.append((sym, reason))
            
    assert len(accepted) == 5
    assert accepted == ["SYM_1", "SYM_2", "SYM_3", "SYM_4", "SYM_5"]
    assert len(rejected) == 3
    for sym, reason in rejected:
        assert "CROWDING_BURST_CAP" in reason
        assert "2026-03-27" in reason


def test_burst_governor_respects_existing_ledger_entries():
    """BUG-058: When ledger already has entries for a date, governor accounts for them."""
    existing_data = [
        {'ENTRY_DATE': '2026-03-27', 'SYMBOL': 'OLD_1', 'STATUS': 'ACTIVE', 'EXIT_DATE': None, 'EXIT_PRICE': None},
        {'ENTRY_DATE': '2026-03-27', 'SYMBOL': 'OLD_2', 'STATUS': 'ACTIVE', 'EXIT_DATE': None, 'EXIT_PRICE': None},
        {'ENTRY_DATE': '2026-03-27', 'SYMBOL': 'OLD_3', 'STATUS': 'ACTIVE', 'EXIT_DATE': None, 'EXIT_PRICE': None},
    ]
    ledger_df = pd.DataFrame(existing_data)
    dt = "2026-03-27"
    
    # 1st new candidate: 3 existing + 0 batch = 3 < 5 -> eligible
    eligible1, reason1 = check_signal_eligibility(
        ledger_df, "NEW_1", dt, cooldown_days=14, same_day_entries=0, max_daily_burst=5
    )
    assert eligible1 is True
    
    # 2nd new candidate: 3 existing + 1 batch = 4 < 5 -> eligible
    eligible2, reason2 = check_signal_eligibility(
        ledger_df, "NEW_2", dt, cooldown_days=14, same_day_entries=1, max_daily_burst=5
    )
    assert eligible2 is True
    
    # 3rd new candidate: 3 existing + 2 batch = 5 >= 5 -> CROWDING_BURST_CAP
    eligible3, reason3 = check_signal_eligibility(
        ledger_df, "NEW_3", dt, cooldown_days=14, same_day_entries=2, max_daily_burst=5
    )
    assert eligible3 is False
    assert "CROWDING_BURST_CAP" in reason3
    assert "5 >= 5" in reason3


def test_burst_governor_already_active_priority():
    """Symbol-specific ALREADY_ACTIVE takes precedence and does not misreport as burst cap."""
    ledger_df = pd.DataFrame([
        {'ENTRY_DATE': '2026-03-20', 'SYMBOL': 'RELIANCE', 'STATUS': 'ACTIVE', 'EXIT_DATE': None, 'EXIT_PRICE': None},
    ])
    dt = "2026-03-27"
    
    # Even if same_day_entries=5, the symbol itself is already active
    eligible, reason = check_signal_eligibility(
        ledger_df, "RELIANCE", dt, cooldown_days=14, same_day_entries=5, max_daily_burst=5
    )
    assert eligible is False
    assert reason == "ALREADY_ACTIVE"


def test_burst_governor_post_loss_priority():
    """Symbol-specific POST_LOSS_LOCKOUT takes precedence over crowding burst cap."""
    ledger_df = pd.DataFrame([
        {'ENTRY_DATE': '2026-03-20', 'SYMBOL': 'INFY', 'STATUS': 'HIT_SL', 'EXIT_DATE': '2026-03-23', 'EXIT_PRICE': 1400.0, 'ENTRY_PRICE': 1500.0},
    ])
    dt = "2026-03-27"  # 4 days since exit < 14 days
    
    eligible, reason = check_signal_eligibility(
        ledger_df, "INFY", dt, cooldown_days=14, same_day_entries=5, max_daily_burst=5
    )
    assert eligible is False
    assert "POST_LOSS_LOCKOUT" in reason


def test_burst_governor_multi_day_independence():
    """Burst cap on Day 1 does not throttle Day 2."""
    ledger_df = pd.DataFrame([
        {'ENTRY_DATE': '2026-03-26', 'SYMBOL': f'DAY1_{i}', 'STATUS': 'ACTIVE', 'EXIT_DATE': None, 'EXIT_PRICE': None}
        for i in range(5)
    ])
    
    # Day 2 candidate
    dt_day2 = "2026-03-27"
    eligible, reason = check_signal_eligibility(
        ledger_df, "DAY2_1", dt_day2, cooldown_days=14, same_day_entries=0, max_daily_burst=5
    )
    assert eligible is True
    assert reason == "FIRST_ENTRY"
