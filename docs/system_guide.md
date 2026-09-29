# Pro-spike System Guide — Vikram Knowledge Base
> **Purpose:** Single source of truth for Vikram (the AI assistant) and future agents.  
> **Format:** Every topic has a **Simple Terms** section (plain English) and a **Deep Dive** section (exact numbers, files, columns).  
> **Maintained by:** Append new sections here after every major feature change. Never delete — mark old sections `[DEPRECATED]`.

---

## Table of Contents
1. [What is Pro-spike?](#1-what-is-pro-spike)
2. [Daily Data Pipeline](#2-daily-data-pipeline)
3. [Data Schemas (CSV Column Reference)](#3-data-schemas)
4. [The 12-Condition Progressive Screener (Path A — Entry)](#4-the-12-condition-progressive-screener)
5. [SBIA Alpha Engine (Path A — Full)](#5-sbia-alpha-engine-path-a)
6. [FlexGate Engine (Path B)](#6-flexgate-engine-path-b)
7. [FlexGate 2.0 (Path B — ML Upgraded)](#7-flexgate-20-path-b--ml-upgraded)
8. [Corner Spike Engine (Micro/Small-Cap)](#8-corner-spike-engine)
8b. [Winner Archetypes Engine](#8b-winner-archetypes-engine)
8c. [Institutional Edge & Live Signals](#8c-institutional-edge--live-signals)
9. [Vikram Quality Score (Conviction Scorer)](#9-vikram-quality-score-conviction-scorer)
10. [The Ledger System](#10-the-ledger-system)
11. [Alert & Notification Bridge](#11-alert--notification-bridge)
12. [Live Intraday Breach Bridge](#12-live-intraday-breach-bridge)
13. [Dashboard Architecture (Dash App)](#13-dashboard-architecture-dash-app)
14. [Key Metrics Glossary](#14-key-metrics-glossary)
15. [Immutable Rules & Anti-Patterns](#15-immutable-rules--anti-patterns)

---

## 1. What is Pro-spike?

### Simple Terms
Pro-spike is a quantitative stock screening and trading assistant for Indian markets (NSE + BSE). Every day it downloads official market data, runs stocks through multiple filtering engines, and sends alerts when something interesting happens — a stock breaking out, hitting a stop-loss, or showing unusual institutional buying.

### Deep Dive
- **Language / Stack:** Python 3.x, Pandas, NumPy, Scikit-learn, YFinance, Dash (Plotly), Streamlit
- **Target:** Quantitative traders tracking institutional accumulation, delivery volume surges, and breakouts
- **Two dashboards:**
  - **Dash App** (`dash_app_v2.py`) — dev/local, port 8050 — primary development workspace
  - **Streamlit App** (`dashboard_full.py`, `lollipop_dashboard_full.py`) — production, deployed on Render — **READ-ONLY, never edit**
- **Git remotes:** Two remotes — `prospike` (Dash repo) and `origin` (Streamlit / live dashboard). Daily data pushes must go to **BOTH**.

---

## 2. Daily Data Pipeline

### Simple Terms
Every trading day, a script downloads two things from BSE and NSE: the price data (how stocks closed) and the delivery data (how many shares were actually "delivered" vs. just traded intraday). These get combined into one big CSV that all the engines read.

### Deep Dive
**Orchestrator:** `auto_update_smart.py` — run with `python auto_update_smart.py`

**Step-by-step execution order:**
1. **Missing-date detection** (`get_missing_trading_dates`) — looks back 10 days for gaps in any of 4 feeds:
   - `data/nse_raw/nse_bhav_YYYYMMDD.csv` (NSE closing prices)
   - `data/nse_raw/nse_delivery_YYYYMMDD.csv` (NSE delivery quantities)
   - `data/bse_raw/bse_bhav_YYYYMMDD.csv` (BSE closing prices)
   - `data/bse_delivery_YYYYMMDD.csv` (BSE delivery %)
2. **NSE download** via `NSEDownloaderFixed` from `nse_downloader_fixed_nov2025.py`
3. **BSE download** via `BSEDownloaderWorking` + `normalize_bse_delivery` + `merge_bse_bhav_delivery` from `bse_downloader_working.py`
4. **Merge** into `data/combined_dashboard_live.csv` (master input for all engines)
5. **Run `calculate_active_signals.py`** — Path A (Alpha) + Path B (FlexGate)
6. **Run `flexgate_2_scanner.py`** — FlexGate 2.0 (separate ML model)
7. **Run `corner_spike_scanner.py`** — Corner Spike Engine
8. **Run `alert_engine.py`** — Detect ledger transitions, dispatch ntfy/email/WhatsApp alerts
9. **Git push** to both remotes

**Key config:** `config.py` and `institutional_config.json`

**Holiday list:** Hardcoded in `auto_update_smart.py` lines 43-53. Weekends and holidays are skipped automatically.

**BSE delivery date format:** Integer `YYYYMMDD` (e.g. `20260929`), NOT a hyphenated string. This is a critical schema contract.

---

## 3. Data Schemas

### Simple Terms
Think of these as the column names in each spreadsheet file. The AI must never guess a column name — it must always check here or read the actual file header.

### Deep Dive

#### Master Input
- **`data/combined_dashboard_live.csv`**: `DATE, SYMBOL, EXCHANGE, ISIN, CLOSE, VWAP, DELIV_PER, DELIVERY_TURNOVER, ATW, DELIV_PER_1W, DELIV_PER_1M, DELIV_PER_3M, DELIVERY_TURNOVER_1W, DELIVERY_TURNOVER_1M, DELIVERY_TURNOVER_3M, ATW_1W, ATW_1M, ATW_3M, VWAP_1M`

#### Watchlist Outputs
- **`data/legacy_watchlist.csv`** / **`data/active_signals_ranked.csv`**: `DATE, SYMBOL, EXCHANGE, CLOSE, AI_SCORE, SIS, Whale_Density, Implied_Trades, STABILITY_RAW, TRIGGER_COUNT_30D, DELIV_PER, DELIVERY_TURNOVER, ATW`
- **`data/sbia_alpha_watchlist.csv`** (also `sbia_institutional_watchlist.csv`): `DATE, SYMBOL, EXCHANGE, ENTRY_PRICE, CLOSE, AI_WIN_PROBABILITY, SIS, Whale_Density, Implied_Trades, STOP_LOSS, TAKE_PROFIT, REC_POS_SIZE_INR, ATR14`
- **`data/sbia_flexgate_watchlist.csv`**: `DATE, SYMBOL, EXCHANGE, ENTRY_PRICE, CLOSE, AI_WIN_PROBABILITY, AI_STATUS, CHANDELIER_EXIT, REC_POS_SIZE_INR, ATR14`
- **`data/sbia_flexgate2_watchlist.csv`**: same schema as flexgate watchlist
- **`data/corner_engine_watchlist.csv`**: Corner Spike active signals
- **`data/winner_archetypes_ranked.csv`**: `SYMBOL, ARCHETYPE, PROMOTER_DIRECTION, ATR_PCT, FLOAT_ABSORPTION_PCT, ATW, SCORE`

#### Ledgers (Paper Trading Tracking)
- **`data/sbia_ledger.csv`**: `ENTRY_DATE, SYMBOL, ENTRY_PRICE, ATR14, STOP_LOSS, TAKE_PROFIT, ENTRY_AI_PROB, ENTRY_WHALE_DENSITY, REC_POS_SIZE_INR, STATUS, EXIT_DATE, EXIT_PRICE`
- **`data/flexgate_ledger.csv`**: same schema
- **`data/flexgate2_ledger.csv`**: same schema (uses CHANDELIER_EXIT internally)
- **`data/corner_engine_ledger.csv`**: Corner Spike paper trades

**STATUS values** (exactly these strings, no others): `ACTIVE`, `HIT_TP`, `HIT_SL`, `SUSPENDED`, `MOMENTUM_LOST`

#### Alert System
- **`data/alerts_log.csv`**: Append-only event log of all dispatched alerts
- **`data/alerts_state.json`**: Fast-path cache of last-known STATUS per symbol

#### Fundamental Cache
- **`data/fundamental_cache.json`**: JSON object keyed by SYMBOL. Keys per entry: `symbol, url, name, market_cap_cr, price, promoter_trend, promoter_holding, dii_trend, dii_holding, fii_trend, fii_holding, pledge_trend, pledge_direction, pledge_note, revenue_ttm_cr, revenue_4q_growth, ebit_4q_growth, op_lev_ratio, op_lev_inflecting, interest_coverage_trend, interest_coverage_recent, ocf_3yr_cr, pat_3yr_cr, fcf_pat_ratio, roice_pct, rpt_status, rpt_pct`

---

## 4. The 12-Condition Progressive Screener

### Simple Terms
This is the front door. A stock must pass 12 tests to even be considered for the Alpha engine. The core idea: delivery percentage, delivery turnover, and average trade size must all be growing — not just high today, but higher than last week, which is higher than last month, which is higher than 3 months ago.

### Deep Dive
**File:** `progressive_screener.py` — `class ProgressiveSpiker`
**Called by:** `calculate_active_signals.py` -> `run_scoring()` -> Path A loop

**The 12 conditions:**

| # | Condition | Type | Threshold |
|---|-----------|------|-----------|
| 1 | `DELIV_PER >= 50` | Baseline | Config: `PROGRESSIVE_SPIKE.delivery_pct_min` (default 50) |
| 2 | `DELIVERY_TURNOVER >= 5,000,000` | Baseline | Config: `PROGRESSIVE_SPIKE.delivery_turnover_min` (default 5M) |
| 3 | `ATW >= 25,000` | Baseline | Config: `PROGRESSIVE_SPIKE.atw_min` (default 25,000) |
| 4 | `DELIV_PER > DELIV_PER_1W` | Progressive | Today > Last Week |
| 5 | `DELIV_PER_1W > DELIV_PER_1M` | Progressive | Last Week > Last Month |
| 6 | `DELIV_PER_1M > DELIV_PER_3M` | Progressive | Last Month > 3M ago |
| 7 | `DELIVERY_TURNOVER > DELIVERY_TURNOVER_1W` | Progressive | Monotonic growth |
| 8 | `DELIVERY_TURNOVER_1W > DELIVERY_TURNOVER_1M` | Progressive | Monotonic growth |
| 9 | `DELIVERY_TURNOVER_1M > DELIVERY_TURNOVER_3M` | Progressive | Monotonic growth |
| 10 | `ATW > ATW_1W` | Progressive | Monotonic growth |
| 11 | `ATW_1W > ATW_1M` | Progressive | Monotonic growth |
| 12 | `ATW_1M > ATW_3M` | Progressive | Monotonic growth |

**Key constraint:** All 9 progressive conditions require **strict monotonic growth** across 4 time periods (Today > 1W > 1M > 3M). If *any* of the 12 fail, the stock is dropped.

**Date filter:** Only processes stocks within 5 days of the latest date in the dataset (stale data is excluded automatically).

---

## 5. SBIA Alpha Engine (Path A)

### Simple Terms
After the 12-condition gate, the Alpha Engine scores the surviving stocks, runs them through a Random Forest AI model, and builds a ranked watchlist. Think of it as: first the bouncer (12 conditions) lets you into the club, then the VIP judge (AI model) decides who gets the best seats.

### Deep Dive
**File:** `calculate_active_signals.py` -> `run_scoring()` -> Path A block (lines 254-403)
**Output:** `data/sbia_alpha_watchlist.csv`, `data/legacy_watchlist.csv`, `data/active_signals_ranked.csv`

**Scoring pipeline:**

1. **`score_signals()`** computes 3 raw scores:
   - `MOMENTUM_RAW = DELIV_PER / DELIV_PER_3M`
   - `FOOTPRINT_RAW = DELIVERY_TURNOVER / DELIVERY_TURNOVER_3M`
   - `STABILITY_RAW = ATW / ATW_3M`

2. **Percentile ranking** — ranks each raw score within the day's universe (0-1 scale)

3. **SIS (Spike Intensity Score):**
   `SIS = ((STABILITY_SCORE+1)^0.50 x (FOOTPRINT_SCORE+1)^0.30 x (MOMENTUM_SCORE+1)^0.20) - 1`

4. **Whale Density:** `ATW / DELIVERY_TURNOVER x 100,000`

5. **Implied Trades:** `DELIVERY_TURNOVER / ATW`

6. **AI model:** `shadow_box_model.pkl` (Random Forest) — features: `[SIS, Whale_Density, Implied_Trades]` -> outputs `AI_WIN_PROBABILITY` (0-100%)

7. **Final filters:**
   - `DELIVERY_TURNOVER > 10,000,000` (>1 Cr) — sanity floor
   - `Whale_Density > 0`
   - `AI_WIN_PROBABILITY >= 60.0` -> **SBIA Alpha watchlist**
   - `AI_SCORE > 0.60` AND `SIS between [0.15, 0.93]` -> **Legacy watchlist**

8. **ATR & Risk sizing** (`calculate_atr_and_risk()`):
   - Fetches 1-month OHLC from yfinance (`.NS` or `.BO` suffix)
   - `ATR14` = 14-day True Range rolling mean
   - `STOP_LOSS = CLOSE - 2.0 x ATR14`
   - `TAKE_PROFIT = CLOSE + 4.0 x ATR14`
   - `REC_POS_SIZE_INR` = 1.5% capital risk / SL distance x CLOSE, capped at 10% capital

9. **SBIA Ledger integration** via `update_sbia_ledger()` from `ledger_manager.py`

**AI Score formula (Legacy only):**
`AI_SCORE = 0.6 x STABILITY_SCORE + 0.1 x MOMENTUM_SCORE + 0.1 x FOOTPRINT_SCORE + 0.2 x (1/TRIGGER_COUNT_30D)`

---

## 6. FlexGate Engine (Path B)

### Simple Terms
FlexGate is looking for "base-loading" — stocks that have been quietly accumulating for weeks and are suddenly seeing a big jump in activity today. The trick: it needs to fire an alert on at least 2 different days in a 10-day window before it signals a real entry.

### Deep Dive
**File:** `calculate_active_signals.py` -> `process_flexgate_engine()` (lines 101-237)
**Output:** `data/sbia_flexgate_watchlist.csv`
**Archive:** `data/flexgate_archive.csv` (10-day rolling history)

**3-Phase logic:**

**Phase 1 — Consolidation Gate** (stock was quiet recently):
```
DELIV_PER >= 50
DELIVERY_TURNOVER >= 500,000
ATW >= 25,000
DELIVERY_TURNOVER_1M > 0  AND  DELIVERY_TURNOVER_1M <= DELIVERY_TURNOVER_3M  # was consolidating
ATW_1M > 0  AND  ATW_1M <= ATW_3M                                              # avg trade shrinking
```

**Phase 2 — Anomaly Tripwires** (today something changed). AT LEAST ONE of:
- **Trigger A:** `DELIVERY_TURNOVER > 2.0 x DELIVERY_TURNOVER_1M` (volume explosion)
- **Trigger B:** `whale_density > 2.0 x whale_density_1m` (big buyers appeared)
- **Trigger C:** `DELIV_PER > 1.5 x DELIV_PER_1M` (delivery % surged)

**Phase 3 — Patience Gate:** Symbol must appear in the archive **exactly TWICE** in the trailing 10 trading days. Not once. Not three times. Exactly two.

**AI Model:** `shadow_box_model.pkl` — features: `[SIS, Whale_Density, Implied_Trades]` -> `AI_WIN_PROBABILITY >= 60.0` -> `AI_APPROVED = True`

**Risk sizing:**
- `CHANDELIER_EXIT = CLOSE - 3.0 x ATR14` (wider stop for base-loading)
- Position sizing: 2.0% capital risk / SL distance x CLOSE

---

## 7. FlexGate 2.0 (Path B — ML Upgraded)

### Simple Terms
FlexGate 2.0 is the more sophisticated version of FlexGate with a better AI brain. It uses the same Phase 1+2+3 logic, but applies a stricter "heuristic bouncer" before reaching the ML model, and uses 8 features instead of 3.

### Deep Dive
**File:** `flexgate_2_scanner.py` -> `process_flexgate_engine()`
**ML Model:** `flexgate_rf_model.pkl` (a different, richer Random Forest — 3.7MB vs shadow_box 180KB)
**Output:** `data/sbia_flexgate2_watchlist.csv`
**Ledger:** `data/flexgate2_ledger.csv`

**8 ML features:**
```
WHALE_PCTL, Implied_Trades, SIS, STABILITY_SCORE,
Phase1_ATW_Ratio, Phase2_Volume_Spike, Close_vs_VWAP_Pct_Distance, ATR_Pct
```

**Heuristic Bouncer (hard filters BEFORE ML):**
- `ATR_Pct >= 3.5` (must be volatile enough — dead stocks excluded)
- `Implied_Trades < 220,000` (not a retail frenzy stock)
- NOT `(Phase2_Volume_Spike > 4.0 AND Implied_Trades <= 30,000)` (exclude exhaustion traps)

**AI gate:** `AI_WIN_PROBABILITY >= 60.0` -> `AI_APPROVED = True`

**Risk:** `CHANDELIER_EXIT = CLOSE - 3.0 x ATR14`

---

## 8. Corner Spike Engine

### Simple Terms
Corner Spike specialises in very small and micro-cap stocks — the ones other engines ignore because they're too small. It applies extra fundamental checks to avoid pump-and-dump traps, and only enters when there's real volatility expansion.

### Deep Dive
**File:** `corner_spike_scanner.py`
**Outputs:** `data/corner_engine_watchlist.csv`, `data/corner_engine_ledger.csv`
**Target universe:** Micro-cap (<500 Cr) and Small-cap (<5,000 Cr)

**Key filters (6 DEMONCORE-hardened fixes):**
1. **Volatility gate:** `ATR14% >= 2.5%` — real expansion required
2. **Concurrency gate:** Throttles when active candidates > 35 (prevents crowding)
3. **Fundamental veto:** Integrates `check_fcf_veto()` and `check_pledge_veto()` from `conviction_scorer.py` — any VETO_TRIGGERED stock is hard-excluded
4. **Anti-exhaustion sweet spot:** `50% <= DELIV_PER <= 85%` — above 85% is late-stage trap
5. **Deduplication:** Verifies ticker has not completed a winning run in the past 45 days
6. **Ranking hierarchy:**
   - Priority 1: Promoter direction (`increasing` > `flat` > `decreasing`)
   - Priority 2: Archetype (Micro-Cap Squeeze > Small-Cap Breakout)
   - Priority 3: Real ATR%
   - Priority 4: Float Absorption % and ATW ticket size

**Archetype data feed:** `data/winner_archetypes_ranked.csv` (produced by `rank_archetypes.py`)

---

## 8b. Winner Archetypes Engine

### Simple Terms
The Winner Archetypes system analyzes every stock that passes Pro-spike's screeners and classifies them by their behavioral trading "personality":
- 🏃 **Clean Runner (The Sprinter):** Closes near its daily high (CDH ≥ 0.50) with price above VWAP and clean volume expansion. This stock is being pushed upward with aggressive institutional buying conviction. It moves cleanly and swiftly — best for high-momentum breakout entries.
- 🐢 **Grind Compounder (The Marathon Runner):** Closes in the lower half of its daily range (CDH < 0.40) but shows massive institutional "whale" activity (Whale Density ≥ 12.0). Big players are quietly absorbing supply without pushing price up or alerting retail traders. Like a marathon runner, it moves slow and steady — best for patient swing accumulation.
- ⚪ **Unclassified:** Doesn't fit either extreme pattern cleanly.

**Rule 3 Quality Cohort (80% Win-Rate Universe):**
A strict, verified cohort with delivery between 50% and 80% (avoiding retail churn <50% and volume exhaustion >80%) and high volatility. In historical desk tests across 25 closed trades, this cohort delivered an **80.0% Win Rate** and ₹62,985 net PnL.

### Deep Dive
- **Script:** `rank_archetypes.py` -> `score_universe()`
- **Output:** `data/winner_archetypes_ranked.csv`
- **Archive:** `data/winner_archetypes_archive.csv`
- **Anchor Performance Metrics:** n = 25 trades (±5), Win Rate = 80.0% (±5%), PnL = ₹62,985 (±₹10,000)

**Market Cap Tiers:**
- MICRO: `< ₹2,000 Cr`
- SMALLISH: `₹2,000 – ₹7,000 Cr`
- MID: `₹7,000 – ₹20,000 Cr`
- LARGE: `> ₹20,000 Cr` (excluded from cohort)

**Mathematical Formats:**
- **Close-to-Daily-High (CDH):** `(Close - Low) / (High - Low)` — measures closing position relative to the daily range.
- **VWAP Divergence (VWAP_DIV):** `(Close / AvgPrice - 1) × 100` — percentage distance above/below intraday VWAP.
- **Whale Density:** `(ATW / VWAP) × 100,000` — institutional ticket concentration.
- **Archetype Classification Logic:**
  - `CLEAN_RUNNER`: `CDH >= 0.50 AND VWAP_DIV > 0` OR `(no CDH) AND ATR_PCT >= 3.4 AND 50 <= DELIV_PER <= 80 AND Whale_Density < 20`
  - `GRIND_COMPOUNDER`: `CDH < 0.40 AND Whale_Density >= 12.0` OR `(no CDH) AND Whale_Density >= 12.0 AND DELIV_PER >= 55.0`
- **Rule 3 Composite Score (0–100):**
  - `ATR_norm = clip((ATR_PCT - 3.0) / 5.0, 0, 1) × 30` (30 pts)
  - `DELIV_norm = clip((80 - DELIV_PER) / 80, 0, 1) × 25` (25 pts)
  - `CDH_norm = clip((CDH - 0.4) / 0.6, 0, 1) × 25` (25 pts)
  - `Turn_norm = clip(DELIVERY_TURNOVER / 10,000,000, 0, 1) × 20` (20 pts)

---

## 8c. Institutional Edge & Live Signals

### Simple Terms
The Institutional Edge report surfaces stocks with significant domestic mutual fund (DII) and institutional footprints where heavy accumulation is taking place ahead of quarterly updates.

### Deep Dive
- **File:** `data/institutional_edge_report.csv`
- **Key Columns:** `SYMBOL`, `MARKET_CAP_CR`, `DII_HOLDING_PCT`, `DII_CHANGE_4Q`, `DELIV_TURNOVER_CR`, `CONVICTION_RATING`
- **Signal Triggers:** Sustained DII holding increases over 2+ quarters, high delivery turnover relative to market cap, and zero promoter pledge.

---

## 9. Vikram Quality Score (Conviction Scorer)

### Simple Terms
Vikram is the fundamental quality judge. It looks at a company's financial health — how efficiently it's growing, whether promoters are pledging shares, whether the cash flow matches the profits. Vikram gives a score and can issue a hard VETO that blocks a stock from any engine.

### Deep Dive
**File:** `conviction_scorer.py`

**Market cap classification:**
- Small (S): `< 7,000 Cr`
- Mid (M): `7,000 – 20,000 Cr`
- Large (L): `>= 20,000 Cr`
- Unknown (U): Missing / zero market cap

**5-Metric Quality Stack (weights):**

| Metric | Weight | Type | Veto Trigger |
|--------|--------|------|--------------|
| Operating Leverage (op_leverage) | 30% | Score | — |
| Promoter Pledge Trend (pledge_trend) | 25% | **VETO** | Pledge > 25% OR rising >= 0.5% |
| FCF/PAT Divergence (fcf_quality) | 20% | Score + **VETO** | Ratio outside [0.33, 3.0] |
| Interest Coverage Trend (interest_coverage) | 20% | Score | — |
| RoICE (roice) | 5% | Score | — |

**Veto mechanics (IMMUTABLE — never change):**
- `check_pledge_veto(pledge_pct, pledge_direction)` -> `VetoResult(status="VETO_TRIGGERED" / "CLEAR" / "UNVERIFIED")`
- `check_fcf_veto(ratio, is_financial)` -> same pattern
- **Missing veto data -> `UNVERIFIED_VETO`** (never silently passes)
- **Score metrics only** renormalize when data is missing; veto metrics **never** renormalize

**Empirical backing (Sep 2026 — IMMUTABLE):**
- Clean fundamentals: +14.83% peak MFE, +8.15% net return
- Vetoed names: +7.22% peak MFE, +1.37% net return
- Promoter pledge = 100% lethal in small-caps (0/5 winners, -1.03% return)

**Fundamental data source:** `fundamental_fetcher.py` -> scrapes screener.in -> cached in `data/fundamental_cache.json`

**RPT (Related Party Transactions):** `data/rpt_cache.json` — populated by offline BSE scraper. When missing, displayed as "NOT CACHED" not as VETO.

---

## 10. The Ledger System

### Simple Terms
The ledger is the desk's authoritative trade logbook. Whenever any engine triggers an entry signal, it is recorded with an `ACTIVE` status, the exact entry date, and entry price. Daily updates monitor live prices against profit targets (TP) and stop losses (SL), updating the record to `HIT_TP`, `HIT_SL`, or `MOMENTUM_LOST`.

### Deep Dive
**Active Ledgers Across Engines:**
1. `data/sbia_ledger.csv` — SBIA Alpha Engine (High-Velocity Breakouts, 2R / 4x ATR targets)
2. `data/flexgate_ledger.csv` — FlexGate 1.0 (Base-Loading, Chandelier SL)
3. `data/flexgate2_ledger.csv` — FlexGate 2.0 (ML Upgraded, Chandelier SL)
4. `data/corner_engine_ledger.csv` — Corner Spike Engine (Micro/Small-Cap Base Squeezes)
5. `data/trades_ledger.csv` — Consolidated Portfolio Ledger

**Common Ledger Schema:**
- `SYMBOL`: Ticker symbol (NSE/BSE)
- `STATUS`: Current trade state (`ACTIVE`, `HIT_TP`, `HIT_SL`, `MOMENTUM_LOST`, `SUSPENDED`)
- `ENTRY_DATE` & `ENTRY_PRICE`: Position initiation date and price
- `EXIT_DATE` & `EXIT_PRICE`: Position exit date and execution price
- `PNL_PCT` & `PNL_INR`: Trade profit/loss percentage and absolute rupee return
- `DAYS_HELD`: Total calendar/trading duration of the trade
- `EXIT_REASON`: Trigger details (e.g. `HIT_TP (+20.0%)`, `CHANDELIER_BREACH`, `STOP_LOSS (-7.0%)`)
- `ENGINE`: Originating screening engine

**STATUS lifecycle:**
```
New signal -> ACTIVE
ACTIVE -> HIT_TP  (close >= TAKE_PROFIT or CHANDELIER_EXIT crossed)
ACTIVE -> HIT_SL  (close <= STOP_LOSS)
ACTIVE -> MOMENTUM_LOST  (delivery metrics collapse)
ACTIVE -> SUSPENDED  (manual or data gap)
```

**SAFETY INVARIANT (must never be broken):**
- `alert_engine.py` reads ledgers with `pd.read_csv()` and **never calls `.to_csv()` on a ledger DataFrame**
- Only ever writes to: `data/alerts_log.csv` and `data/alerts_state.json`

**Velocity simulation capital rules (IMMUTABLE):**
- Capital = 1,000,000 (10 Lakhs)
- SBIA risk per trade: 0.3%
- FlexGate risk per trade: 0.2%
- FlexGate 2.0 risk per trade: 0.2%
- NaN-SL fallback: flat 10% capital allocation
- Max per trade: 10% capital

**Unqualified stocks (never enter any ledger):** `COALINDIA`, `KOTAKBANK`, `BANKBETA`
**Manually tracked (never auto-purge):** `NOVUS`

---

## 11. Alert & Notification Bridge

### Simple Terms
When a ledger entry changes status (e.g. a stop-loss is hit, or a new signal fires), the alert engine sends you a push notification on your phone (via ntfy), an email, and optionally a WhatsApp message.

### Deep Dive
**Files:** `alert_engine.py`, `notify_channels.py`

**Channels:**
- **ntfy.sh** — HTTP push notification, topic name is the secret key in `.env`
- **Email** — Gmail SMTP over SSL, configured in `.env`
- **WhatsApp** — CallMeBot REST API

**Required `.env` keys:**
```
NTFY_TOPIC=<your-topic>
GMAIL_SENDER=<email>
GMAIL_APP_PASSWORD=<app-password>
GMAIL_RECIPIENT=<email>
CALLMEBOT_PHONE=<+91xxxxxxxxxx>
CALLMEBOT_API_KEY=<key>
```

**Alert engine operation:**
1. Load `data/alerts_state.json` (previous known STATUS per symbol)
2. Read all 4 ledgers: `sbia_ledger.csv`, `flexgate_ledger.csv`, `flexgate2_ledger.csv`, `corner_engine_ledger.csv`
3. Detect transitions: new ACTIVE entries, or STATUS changes (HIT_TP, HIT_SL, MOMENTUM_LOST, SUSPENDED)
4. De-duplicate against `data/alerts_log.csv` (no repeat alerts for same event)
5. Dispatch to all configured channels
6. Write new state to `alerts_state.json`

**CLI flags:**
```bash
python alert_engine.py --dry-run        # Print what would be sent, don't actually send
python alert_engine.py --test-channel   # Send a test ping to verify channels work
python alert_engine.py --only FLEXGATE  # Run only one engine
python alert_engine.py --no-send        # Process but don't dispatch
```

---

## 12. Live Intraday Breach Bridge

### Simple Terms
During market hours, the system watches your watchlist stocks and sends an alert if one hits its stop-loss or target price in real time — without waiting for the end-of-day ledger update.

### Deep Dive
**File:** `alert_engine.py` — `_LIVE_BREACH_LOCK`, intraday breach functions
**Live price source:** `live_price_fetcher.py` (yfinance intraday data)
**Dash integration:** `dash_pages/watchlist.py` — background daemon thread with 120-second `dcc.Interval` polling

**CLI flags:**
```bash
python alert_engine.py --live-breach        # Start live breach monitor
python alert_engine.py --live-breach-force  # Force-run even outside market hours
```

**Architecture rules:**
- Background worker runs in a **daemon thread** (`threading.Thread(daemon=True)`)
- Uses `threading.Lock` (`_LIVE_BREACH_LOCK`) to prevent concurrent runs
- **NEVER call yfinance inside a synchronous Dash callback** (causes Gunicorn timeout / browser freeze)
- SWR (stale-while-revalidate) cache: results cached in memory, refreshed on background thread only

---

## 13. Dashboard Architecture (Dash App)

### Simple Terms
The main dashboard is a Plotly Dash app. It has multiple pages (tabs), each reading from the CSV files the engines produce. The Vikram AI assistant is embedded in a sidebar and can answer questions about any stock.

### Deep Dive
**Entry point:** `dash_app_v2.py` (run: `python dash_app_v2.py`)
**Pages directory:** `dash_pages/`

| Page file | URL route | Content |
|-----------|-----------|---------|
| `dash_pages/overview.py` | `/` | Portfolio summary, market KPIs |
| `dash_pages/signals.py` | `/signals` | Legacy screener signals |
| `dash_pages/institutional_signals.py` | `/institutional` | SBIA Alpha watchlist |
| `dash_pages/watchlist.py` | `/watchlist` | Live Radar + Intraday breach monitor |
| `dash_pages/winner_archetypes.py` | `/archetypes` | Corner Spike archetypes |
| `dash_pages/notifications.py` | `/notifications` | Alert history log |
| `dash_pages/_vikram_callback.py` | (sidebar) | Vikram AI chatbot backend |

**Design system:**
- Dark-mode, fintech terminal aesthetic
- CSS: `assets/style.css` (legacy variables) + Tailwind M3 tokens via CDN
- Key classes: `glass-panel`, `details.glass-panel` for layout cards
- Callbacks: `@dash.callback` (NOT `app.callback`)
- Data loading: `@lru_cache` keyed on file `mtime` to prevent N+1 reads

**Production boundary (CRITICAL):**
- `dashboard_full.py`, `lollipop_dashboard_full.py`, `run.bat` -> **READ-ONLY**. Development is in `dash_app_v2.py` and `dash_pages/` only.

---

## 14. Key Metrics Glossary

| Term | Simple Explanation | Formula / Source |
|------|-------------------|---------|
| **DELIV_PER** | % of traded shares that were actually delivered (not reversed intraday). High = real conviction | `Delivery Qty / Traded Qty x 100` |
| **DELIVERY_TURNOVER** | Total rupee value of delivered shares | `Delivery Qty x VWAP` |
| **ATW** (Average Trade Worth) | Average rupee value per trade. High (>25K) = institutional, low (<5K) = retail | `Delivery Turnover / Number of Trades` |
| **SIS** (Spike Intensity Score) | Composite momentum+footprint+stability. Above 0.15 = interesting, above 0.93 = possible manipulation | `(S+1)^0.5 x (F+1)^0.3 x (M+1)^0.2 - 1` |
| **Whale Density** | Ratio of ATW to VWAP — higher = fewer, larger buyers dominating | `ATW / VWAP x 100,000` |
| **Implied Trades** | How many institutional-sized orders happened | `DELIVERY_TURNOVER / ATW` |
| **ATR14** | Average True Range over 14 days — measures volatility | True Range rolling 14-day mean (from yfinance) |
| **CHANDELIER_EXIT** | FlexGate's trailing stop based on ATR. Wider than Alpha's stop | `CLOSE - 3.0 x ATR14` |
| **AI_WIN_PROBABILITY** | ML model's estimate of a winning trade (0-100%) | Random Forest predict_proba output |
| **N_CONCURRENT** | How many signals are active on the same day — higher = crowding risk | Count per DATE group |
| **TRIGGER_COUNT_30D** | How many times this stock has signaled in the last 30 days (scarcity factor) | Rolling count in survivors_archive |
| **Phase2_Volume_Spike** | FlexGate 2.0: today's delivery turnover vs 1-month average | `DELIVERY_TURNOVER / DELIVERY_TURNOVER_1M` |
| **WHALE_PCTL** | Percentile rank of Whale Density in today's universe | `Whale_Density.rank(pct=True) x 100` |

---

## 15. Immutable Rules & Anti-Patterns

> These rules were established through empirical evidence and must never be changed without a full DEMONCORE ROOT_CAUSE audit and explicit user confirmation.

### Immutable Rules
1. **Veto metrics never renormalize.** Missing pledge or FCF data -> `UNVERIFIED_VETO`. Not optional.
2. **Ledger files are read-only from `alert_engine.py`.** Never call `.to_csv()` on a ledger DataFrame inside the alert engine.
3. **No yfinance inside synchronous Dash callbacks.** Causes Gunicorn timeout. Always use background threads.
4. **No empty try/except blocks.** Fail loudly. Silent failures corrupt data ledgers.
5. **NOVUS is never auto-purged** from any ledger.
6. **BSE delivery date is integer YYYYMMDD**, not hyphenated string.
7. **All AI thresholds = 60%.** Path A, Path B FlexGate, and FlexGate 2.0 all use >= 60.0 as AI_WIN_PROBABILITY gate.
8. **12-condition screener requires strict monotonic growth** across all 4 time periods for all 3 metrics. Partial monotonic growth is not accepted.

### Anti-Patterns (Proven to Fail)
| What looks tempting | Why it fails |
|---|---|
| Increasing scraper timeouts | Indicates layout/anti-bot changes, not network lag |
| `try/except: pass` in data ingestion | Silently corrupts ledgers and downstream signals |
| Direct editing of `dashboard_full.py` | Breaks live production Streamlit app |
| Guessing CSV column names | Schema mismatches crash pandas silently |
| Moving veto metrics to scoring | Simpson's Paradox — small-cap vetoed names massively underperform |
| Running yfinance in Dash callbacks | Gunicorn worker timeout, browser freeze |
| Trusting scraped data without validation | Layout changes produce invalid float/date types |

---

## Appendix: How to Ask Vikram Questions

**Simple answer needed?** Ask: *"What is FlexGate?"*
-> Vikram gives the 2-3 line plain-English version from the "Simple Terms" section above.

**Deep dive needed?** Ask: *"Explain the FlexGate Phase 3 patience gate"* or *"What are the exact 12-condition thresholds?"*
-> Vikram references the "Deep Dive" section with exact numbers, file paths, and formulas.

**Architecture question?** Ask: *"Which files does the alert engine write to?"* or *"What's the data flow from download to signal?"*
-> Vikram traces through the pipeline documentation above.

---

*Last updated: 2026-09-29 — Vikram Knowledge Base v1.0 (initial creation)*
*Append new features below this line. Never delete entries — mark as `[DEPRECATED]` if obsolete.*
