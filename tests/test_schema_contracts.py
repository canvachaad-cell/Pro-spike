import pytest
import pandas as pd
import sys
import os

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schema_contracts import validate, SchemaDriftError

def test_valid_dataframe():
    """Test a perfectly valid dataframe against the bse_delivery schema."""
    df = pd.DataFrame({
        "DATE": [20260831, 20260901],
        "SYMBOL": ["ALGOQUANT", "SAKSOFT"],
        "DELIV_QTY": [1000, 2000],
        "DELIV_PER": [50.5, 60.2]
    })
    
    # Should not raise any exceptions
    validated_df = validate("bse_delivery", df)
    assert len(validated_df) == 2


def test_missing_column_dataframe():
    """Test a dataframe missing a required column (silent drift)."""
    df = pd.DataFrame({
        "DATE": [20260831],
        "SYMBOL": ["ALGOQUANT"],
        # DELIV_QTY is missing
        "DELIV_PER": [50.5]
    })
    
    with pytest.raises(SchemaDriftError) as exc_info:
        validate("bse_delivery", df)
        
    assert "Missing required columns: ['DELIV_QTY']" in str(exc_info.value)
    assert exc_info.value.missing == ["DELIV_QTY"]


def test_type_mismatch_dataframe():
    """Test a dataframe with the wrong data type (e.g. string date instead of int64)."""
    df = pd.DataFrame({
        "DATE": ["2026-08-31"], # String instead of int64
        "SYMBOL": ["ALGOQUANT"],
        "DELIV_QTY": [1000],
        "DELIV_PER": [50.5]
    })
    
    with pytest.raises(SchemaDriftError) as exc_info:
        validate("bse_delivery", df)
        
    assert "Type mismatches" in str(exc_info.value)
    assert "DATE: expected int64" in str(exc_info.value)


def test_valid_dict():
    """Test a perfectly valid dict against the fundamental_fetcher schema."""
    data = {k: "dummy" for k in [
        "symbol", "url", "name", "market_cap_cr", "price", "promoter_trend", 
        "promoter_holding", "dii_trend", "dii_holding", "fii_trend", "fii_holding", 
        "pledge_trend", "pledge_direction", "pledge_note", "quarterly_quarters", 
        "revenue_ttm_cr", "revenue_4q_growth", "ebit_4q_growth", "op_lev_ratio", 
        "op_lev_inflecting", "interest_coverage_trend", "interest_coverage_recent", 
        "ocf_3yr_cr", "pat_3yr_cr", "fcf_pat_ratio", "roice_pct", "roce_abs_pct", 
        "borrowings_cr", "free_float_cr", "rpt_status", "rpt_pct", "rpt_amount_cr"
    ]}
    
    validated_data = validate("fundamental_fetcher", data)
    assert validated_data["symbol"] == "dummy"


def test_missing_key_dict():
    """Test a fundamental fetcher dict missing several keys."""
    data = {
        "symbol": "ALGOQUANT",
        "market_cap_cr": 1836.0
        # Missing everything else
    }
    
    with pytest.raises(SchemaDriftError) as exc_info:
        validate("fundamental_fetcher", data)
        
    assert "Missing required columns" in str(exc_info.value)
    assert "roice_pct" in exc_info.value.missing
    assert "url" in exc_info.value.missing


def test_unknown_schema():
    """Test asking for a schema that does not exist."""
    df = pd.DataFrame()
    with pytest.raises(ValueError, match="Unknown schema contract: 'imaginary_schema'"):
        validate("imaginary_schema", df)


def test_valid_runtime_config():
    from schema_contracts import validate_runtime_config
    config = {
        'model_candidates': [{'id': 'test', 'provider': 'google'}],
        'api_timeout_ms': 25000,
        'probe_timeout_s': 10,
        'worker_counts': {'local': 4}
    }
    validated = validate_runtime_config(config)
    assert validated['api_timeout_ms'] == 25000

def test_malformed_runtime_config():
    from schema_contracts import validate_runtime_config
    config = {
        'model_candidates': [{'id': 'test'}], # Missing provider
        'api_timeout_ms': "25000", # String instead of int
        'probe_timeout_s': 10,
        # missing worker_counts
    }
    with pytest.raises(SchemaDriftError) as exc_info:
        validate_runtime_config(config)
        
    assert "missing" in str(exc_info.value).lower()


def test_fundamental_fetcher_missing_keys_backfilled():
    """Verify that FundamentalFetcher._apply_overrides fills missing keys with None."""
    from fundamental_fetcher import FundamentalFetcher
    from schema_contracts import CONTRACTS

    fetcher = FundamentalFetcher()
    partial_data = {"symbol": "TEST", "market_cap_cr": 500.0}
    validated = fetcher._apply_overrides("TEST", partial_data)

    expected_keys = CONTRACTS["fundamental_fetcher"]["keys"]
    assert len(expected_keys) == 32
    for k in expected_keys:
        assert k in validated
    assert validated["promoter_holding"] is None
    assert validated["market_cap_cr"] == 500.0


def test_fundamental_fetcher_zero_promoter_handling():
    """Verify zero-promoter extraction sets holding=0.0 and free_float = mcap."""
    from fundamental_fetcher import FundamentalFetcher

    fetcher = FundamentalFetcher()
    headers = ["", "Sep 2024", "Dec 2024"]
    data = {
        "FIIs": ["30.0%", "32.0%"],
        "DIIs": ["20.0%", "21.0%"],
        "Public": ["50.0%", "47.0%"]
    }
    out = {"market_cap_cr": 10000.0}
    fetcher._extract_shareholding(out, headers, data)
    fetcher._derive_free_float(out)

    assert out["promoter_holding"] == 0.0
    assert "0.0%" in out["promoter_trend"]
    assert out["fii_holding"] == 32.0
    assert out["dii_holding"] == 21.0
    assert out["free_float_cr"] == 10000.0
