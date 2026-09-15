---
name: "Data Schema Skill"
description: "Loaded when the agent needs to know the shape of data files."
---

# DYNAMIC SCHEMA DISCOVERY PROTOCOL

> AUTOMATED RULE: Never guess column names or JSON keys. Always verify against these known schemas or use head/jq to inspect files.

## 1. Known CSV Schemas

### Watchlists
- **legacy_watchlist.csv**: `DATE, SYMBOL, EXCHANGE, CLOSE, AI_SCORE, SIS, Whale_Density, Implied_Trades, STABILITY_RAW, TRIGGER_COUNT_30D, DELIV_PER, DELIVERY_TURNOVER, ATW`
- **sbia_alpha_watchlist.csv**: `DATE, SYMBOL, EXCHANGE, ENTRY_PRICE, CLOSE, AI_WIN_PROBABILITY, SIS, Whale_Density, Implied_Trades, STOP_LOSS, TAKE_PROFIT, REC_POS_SIZE_INR, ATR14`
- **sbia_flexgate_watchlist.csv**: `DATE, SYMBOL, EXCHANGE, ENTRY_PRICE, CLOSE, AI_WIN_PROBABILITY, AI_STATUS, CHANDELIER_EXIT, REC_POS_SIZE_INR, ATR14`
- **sbia_flexgate2_watchlist.csv**: `DATE, SYMBOL, EXCHANGE, ENTRY_PRICE, CLOSE, AI_WIN_PROBABILITY, AI_STATUS, CHANDELIER_EXIT, REC_POS_SIZE_INR, ATR14`

### Ledgers
- **sbia_ledger.csv / flexgate_ledger.csv / flexgate2_ledger.csv**: `ENTRY_DATE, SYMBOL, ENTRY_PRICE, ATR14, STOP_LOSS, TAKE_PROFIT, ENTRY_AI_PROB, ENTRY_WHALE_DENSITY, REC_POS_SIZE_INR, STATUS, EXIT_DATE, EXIT_PRICE`
*(Note: FlexGate ledgers use CHANDELIER_EXIT logic but schema headers remain consistent for simulation).*

### Real-Time Data
- **dashboard_cloud.csv**: Must contain `SYMBOL` and `CLOSE` for MTM (Mark-to-Market) calculations.

### BSE Delivery Data
- `bse_delivery_YYYYMMDD.csv`: Format is `DATE,SYMBOL,DELIV_QTY,DELIV_PER`.
- **CRITICAL:** `DATE` is formatted as an integer `YYYYMMDD` (e.g., `20260831`), NOT a date string with hyphens.

## 2. Dynamic Discovery
If a file is not listed above, run a quick discovery first:
- `Get-Content -Path file.csv -TotalCount 3` (PowerShell)
- `print(df.head())` or `print(df.columns)` in Python scripts.

## 3. Fundamental Data
### `fundamental_fetcher.py` output format:
- **JSON Payload Keys**: `symbol`, `url`, `name`, `market_cap_cr`, `price`, `promoter_trend`, `promoter_holding`, `dii_trend`, `dii_holding`, `fii_trend`, `fii_holding`, `pledge_trend`, `pledge_direction`, `pledge_note`, `quarterly_quarters`, `revenue_ttm_cr`, `revenue_4q_growth`, `ebit_4q_growth`, `op_lev_ratio`, `op_lev_inflecting`, `interest_coverage_trend`, `interest_coverage_recent`, `ocf_3yr_cr`, `pat_3yr_cr`, `fcf_pat_ratio`, `roice_pct`, `roce_abs_pct`, `borrowings_cr`, `free_float_cr`, `rpt_status`, `rpt_pct`, `rpt_amount_cr`
- **Optional/Conditional Keys**: `sector_type`, `business_model_changed`, `business_model_change_year`, `business_model_change_note` (Added via MANUAL_SECTOR_OVERRIDES)
