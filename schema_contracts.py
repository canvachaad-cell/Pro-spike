import pandas as pd
from typing import Union

class SchemaDriftError(Exception):
    def __init__(self, source, missing=None, type_mismatches=None):
        self.source = source
        self.missing = missing or []
        self.type_mismatches = type_mismatches or []
        
        msg = f"Schema Drift Detected in '{source}'."
        if self.missing:
            msg += f" Missing required columns: {self.missing}."
        if self.type_mismatches:
            msg += f" Type mismatches: {self.type_mismatches}."
        super().__init__(msg)


# Machine-readable contracts derived strictly from DATA-SCHEMA.md
CONTRACTS = {
    "legacy_watchlist": {
        "type": "dataframe",
        "columns": {
            "DATE": None, "SYMBOL": None, "EXCHANGE": None, "CLOSE": None, 
            "AI_SCORE": None, "SIS": None, "Whale_Density": None, 
            "Implied_Trades": None, "STABILITY_RAW": None, "TRIGGER_COUNT_30D": None, 
            "DELIV_PER": None, "DELIVERY_TURNOVER": None, "ATW": None
        }
    },
    "sbia_alpha_watchlist": {
        "type": "dataframe",
        "columns": {
            "DATE": None, "SYMBOL": None, "EXCHANGE": None, "ENTRY_PRICE": None, 
            "CLOSE": None, "AI_WIN_PROBABILITY": None, "SIS": None, 
            "Whale_Density": None, "Implied_Trades": None, "STOP_LOSS": None, 
            "TAKE_PROFIT": None, "REC_POS_SIZE_INR": None, "ATR14": None
        }
    },
    "sbia_flexgate_watchlist": {
        "type": "dataframe",
        "columns": {
            "DATE": None, "SYMBOL": None, "EXCHANGE": None, "ENTRY_PRICE": None, 
            "CLOSE": None, "AI_WIN_PROBABILITY": None, "AI_STATUS": None, 
            "CHANDELIER_EXIT": None, "REC_POS_SIZE_INR": None, "ATR14": None
        }
    },
    "ledger": {
        "type": "dataframe",
        "columns": {
            "ENTRY_DATE": None, "SYMBOL": None, "ENTRY_PRICE": None, "ATR14": None, 
            "STOP_LOSS": None, "TAKE_PROFIT": None, "ENTRY_AI_PROB": None, 
            "ENTRY_WHALE_DENSITY": None, "REC_POS_SIZE_INR": None, "STATUS": None, 
            "EXIT_DATE": None, "EXIT_PRICE": None
        }
    },
    "bse_delivery": {
        "type": "dataframe",
        "columns": {
            "DATE": "int64", # Explicit rule from DATA-SCHEMA.md
            "SYMBOL": None, 
            "DELIV_QTY": None, 
            "DELIV_PER": None
        }
    },
    "fundamental_fetcher": {
        "type": "dict",
        "keys": {
            "symbol", "url", "name", "market_cap_cr", "price", "promoter_trend", 
            "promoter_holding", "dii_trend", "dii_holding", "fii_trend", "fii_holding", 
            "pledge_trend", "pledge_direction", "pledge_note", "quarterly_quarters", 
            "revenue_ttm_cr", "revenue_4q_growth", "ebit_4q_growth", "op_lev_ratio", 
            "op_lev_inflecting", "interest_coverage_trend", "interest_coverage_recent", 
            "ocf_3yr_cr", "pat_3yr_cr", "fcf_pat_ratio", "roice_pct", "roce_abs_pct", 
            "borrowings_cr", "free_float_cr", "rpt_status", "rpt_pct", "rpt_amount_cr"
        }
    }
}


def validate(name: str, data: Union[pd.DataFrame, dict]) -> Union[pd.DataFrame, dict]:
    """
    Validates a DataFrame or Dictionary against the strict data schema contract.
    Raises SchemaDriftError loudly on failure. No warnings, no coercion.
    """
    if name not in CONTRACTS:
        raise ValueError(f"Unknown schema contract: '{name}'")
        
    contract = CONTRACTS[name]
    missing = []
    type_mismatches = []
    
    if contract["type"] == "dataframe":
        if not isinstance(data, pd.DataFrame):
            raise SchemaDriftError(name, type_mismatches=[f"Expected DataFrame, got {type(data).__name__}"])
            
        expected_cols = contract["columns"]
        
        # Check missing columns
        for col in expected_cols:
            if col not in data.columns:
                missing.append(col)
                
        # Check explicit types if specified
        if not missing:
            for col, expected_type in expected_cols.items():
                if expected_type:
                    # pandas dtypes check
                    actual_type = str(data[col].dtype)
                    if expected_type == "int64" and "int" not in actual_type:
                         type_mismatches.append(f"{col}: expected {expected_type}, got {actual_type}")
                         
    elif contract["type"] == "dict":
        if not isinstance(data, dict):
            raise SchemaDriftError(name, type_mismatches=[f"Expected dict, got {type(data).__name__}"])
            
        expected_keys = contract["keys"]
        for k in expected_keys:
            if k not in data:
                missing.append(k)

    if missing or type_mismatches:
        raise SchemaDriftError(name, missing=missing, type_mismatches=type_mismatches)
        
    return data


def validate_runtime_config(config_data: dict) -> dict:
    """
    Validates the vikram_runtime.json config structure.
    Ensures all keys are present and types are correct before the app starts.
    """
    missing = []
    type_mismatches = []
    
    required_keys = ['model_candidates', 'api_timeout_ms', 'probe_timeout_s', 'worker_counts']
    for k in required_keys:
        if k not in config_data:
            missing.append(k)
            
    if not missing:
        if not isinstance(config_data['model_candidates'], list):
            type_mismatches.append("model_candidates: expected list")
        else:
            for i, model in enumerate(config_data['model_candidates']):
                if 'id' not in model or 'provider' not in model:
                    missing.append(f"model_candidates[{i}] missing 'id' or 'provider'")
                    
        if not isinstance(config_data['api_timeout_ms'], int):
            type_mismatches.append("api_timeout_ms: expected int")
            
        if not isinstance(config_data.get('worker_counts', {}), dict):
            type_mismatches.append("worker_counts: expected dict")

    if missing or type_mismatches:
        raise SchemaDriftError("vikram_runtime.json", missing=missing, type_mismatches=type_mismatches)
        
    return config_data
