# Pro-spike Quantitative Audit — Consolidated Findings Report
**System:** `Pro-spike` trading engine (Python 3 / Dash / pandas / scikit-learn; Indian NSE+BSE market data)  
**Audit period:** 23 September 2026  
**Auditor:** automated code+data audit (all numbers below are re-computed from repo files, not quoted from prior docs)  
**Scope:** small-cap (`< ₹7,000 Cr`) winner cohorts; the AI win-probability model stack; 7 exploratory signal angles; data-availability and data-integrity checks  

> **How to read this.** Every claim is tagged **[MEASURED]** (computed from repo data), **[READ]** (read directly from source code/model binaries), or **[INFERRED]** (reasoned, not fully proven). Anything not supported by repo data is explicitly marked **NOT IN CONTEXT** rather than filled in. Sample sizes are given as `n` on every statistical claim, and `n < 10` cuts are flagged underpowered.

---

## 1. Executive summary

| # | Finding | Confidence |
|---|---|---|
| 1 | The AI win-probability score **does rank** (AUC 0.624, p=0.008) but is **badly miscalibrated** — Brier 0.3266 vs base-rate 0.2018, Hosmer-Lemeshow p=0.0000; it over-predicts by 12–42 pp in *every* bucket | High [MEASURED] |
| 2 | **Root cause:** the models were trained on **ONE month** (July 2026, 82 rows) with a *same-month* "holdout" (base rate 75% vs 44% train) and **no walk-forward validation** | High [MEASURED] |
| 3 | Model confidence is **flat (67–74%)** across months while actual win rate collapses **85.7% → 45.3% → 20.0%**. It is most confident in its worst month | High [MEASURED] |
| 4 | **61.5% of the 8-feature model's weight** sits on duplicated/non-predictive features; the one feature that verifies (`ATR_Pct`) holds only 14.9% | High [READ+MEASURED] |
| 5 | Two of three model inputs are **exact reciprocals** of each other — one input counted twice | High [MEASURED, algebraically proven] |
| 6 | The `AI_WIN_PROBABILITY >= 60` gate is **100% non-binding** on 2 of 3 engines and its label is wrong (delivers 52.6% not 60%) | High [MEASURED] |
| 7 | One column name is produced by **two different models with three distributional scales** | High [READ+MEASURED] |
| 8 | The edge is **NOT period luck** — temporal-clustering permutation p = 0.985/0.250. But **signal crowding** costs real win rate (40.8% → 17.6%, Fisher p=0.0150) | High [MEASURED] |
| 9 | **Promoter stake direction** is the strongest new signal found (90% / 43% / 25% win rate, monotone, Fisher p=0.0037) and is independent of the veto system | Medium-high [MEASURED, n=10 top bucket] |
| 10 | Engine quality dominates everything: small-cap win rate **60.0% (SBIA) vs 22.2% (FlexGate 2) vs 18.2% (legacy)** | High [MEASURED, small n] |

**Bottom line:** the trading *edge* looks more durable than expected, but the *model layer that gates and ranks trades* is currently the weakest part of the system, and its errors are structural (training design), not cosmetic.

---

## 2. System and data inventory

### 2.1 Ledgers (trade records)
| File | Rows | Key columns |
|---|---|---|
| `data/sbia_ledger.csv` | 135 (125 closed, 9 ACTIVE, 1 SUSPENDED) | ENTRY_DATE, SYMBOL, ENTRY_PRICE, ATR14, STOP_LOSS, TAKE_PROFIT, ENTRY_AI_PROB, ENTRY_WHALE_DENSITY, ENTRY_IMPLIED_TRADES, STATUS, EXIT_DATE, EXIT_PRICE |
| `data/flexgate_ledger.csv` | 79 | same 12-column schema |
| `data/flexgate2_ledger.csv` | 21 | same 12-column schema |
| `data/trades_ledger.csv` | 119 | ticker, trigger_date, engine, market_cap_class, raw_status, return_pct, outcome_tag, market_cap_cr, bse_scrip |
| `scratch/tagged_trades_all_189.csv` | 189 | adds mae_pct, mfe_pct, worst_daily_drop, veto_status, trigger_metric, veto_reasons, stock_class, exit_mechanism |

### 2.2 Price / order-flow panels
| Source | Coverage | Use |
|---|---|---|
| `data/bse_raw/bse_bhav_*.csv` | **271 sessions, 2025-08-04 → 2026-09-22, continuous (15–23 files/month)** | the ONLY continuous price panel → MAE/MFE, volatility, 52-week, market breadth |
| `data/nse_raw/nse_delivery_*.csv` | 559 files; **261 in 2024**, 105 in 2025, 188 in 2026 | NSE-specific order flow |
| `data/bse_delivery_*.csv` | 278 files, 2025-08-04 → 2026-09-22 | BSE delivery qty/% (keyed by **6-digit scrip code** in the `SYMBOL` column) |
| `data/historical_full_universe.csv` | **1,125,834 rows, 2025-08-08 → 2026-08-12, every month populated** | full feature panel (scores + 1W/1M baselines) |
| `data/flexgate_archive.csv` | 1,554 rows, 2026-08-12 → 2026-09-22 | alert-day features only (VWAP, SIS, WHALE_DENSITY) |
| `data/df_sig_2022_2024.csv` | 1,745 rows, 2022-12-27 → 2024-10-21 | features only, **no labels** |

### 2.3 Cohort recipe (pinned, and *verified* to reproduce the published baseline)
```python
stock_class = classify(market_cap_cr)      # S < 7000 <= M < 20000 <= L ; NaN -> U
winner      = status == 'HIT_TP' | exit_mechanism == 'CHANDELIER_PROFIT' | return_pct >= 3.0
win rate    = share with outcome_tag == 'WINNER'      # NOT return_pct > 0
```
**Critical nuance:** "win rate" in the published docs is the share tagged `outcome_tag == 'WINNER'`, **not** the share with a positive return. The two differ materially (61.5% vs 69.2% on one cohort) because a trade can close green yet be tagged LOSER (e.g. SMCGLOBAL at +0.76%). Any reimplementation must use the tagged definition.

### 2.4 Verified metric formulas
```python
NSE  DELIVERY_TURNOVER_₹ = DELIV_QTY × CLOSE_PRICE
     ATW_₹               = TURNOVER_LACS × 1e5 / NO_OF_TRADES
BSE  DELIVERY_TURNOVER_₹ = DELIV_QTY × ClsPric
     ATW_₹               = TtlTrfVal / TtlNbOfTxsExctd
BOTH float_absorbed_pct  = (DELIVERY_TURNOVER_₹ / 1e7) / free_float_cr × 100
```
All four verified by exact reproduction of published rows, e.g. **PRARUH** (BSE scrip 544538, 2026-08-28): DT ₹4.883 Cr, ATW **₹697,620.0 exactly**, float absorbed 8.57%, delivery 100.0%.

**Unit traps that must not be re-introduced:**
- `data/flexgate_archive.csv` stores `DELIVERY_TURNOVER` in **absolute ₹** (÷1e7 for ₹Cr) and `ATW` in **₹/trade** — *not* `TOTTRDVAL/1000`.
- `data/bse_delivery_*.csv`: the column **named** `SYMBOL` actually holds the 6-digit BSE scrip code.
- `data/bse_raw/bse_bhav_*.csv`: `TckrSymb` **rotates over time** (ASHIKA → ASHIKAG) → joins must use `FinInstrmId`.
- `momentum_scorer.score_delivery_turnover()` expects **₹ Cr** while raw panels carry ₹.

---

## 3. What could NOT be measured — **NOT IN CONTEXT**

Stated explicitly because three of seven requested analyses had **zero supporting data** in the repo:

| Requested analysis | Repo status | Substituted? |
|---|---|---|
| Nifty / Sensex index trend at entry | **No index series exists.** Every `NIFTY`/`SENSEX` string in the repo is an *exclusion filter* for non-equity symbols (e.g. `rank_archetypes.py:27`) | Proxied: equal-weighted market index + breadth built from the repo's own universe |
| India VIX level | **No VIX data of any kind** | Not proxied |
| Bulk / block deal disclosures (named buyers) | **No disclosure data exists** (only HTML/JS noise in `bse_page.html`) | Proxied: per-stock block-print z-score vs its own 60-session baseline |
| Earnings / results announcement dates | **No dates anywhere** — the 35-key fundamental payload has no date field; `rpt_cache.json` has none | Proxied: deterministic quarter-end proximity (calendared, not real announcement dates) |

**All three proxies are labelled as proxies** in code, output and docs. They are not Nifty, not deal disclosures, and not earnings dates.

---

## 4. Data-quality defects discovered

| ID | Defect | Evidence | Status |
|---|---|---|---|
| **BUG-053** | `conviction_scorer.classify(NaN)` returns `'S'` (guards only `is None`) → **silently promotes unmapped tickers into the small-cap cohort** | 4 rows in the 119 ledger, **29 rows in the 189 ledger** (ABSL10BANK, GROWWLIQID, MOCAPITAL, TATSILV, ADON, BFSI, … — ETFs/new listings) | OPEN |
| **BUG-054** | **10 NSE delivery files named `date + 1`** (content is the previous trading day). Correctly-named twin file also exists → duplication, not loss | 20260115→20260114, 20260126→20260123, 20260303→20260302, 20260326→20260325, 20260331→20260330, 20260403→20260402, 20260414→20260413, 20260501→20260430, 20260528→20260527, 20260626→20260625. BSE files: **0** mismatches | OPEN (downloader) |
| **BUG-055** | NSE bhavcopy encodes a **blank delivery qty as the literal `' -'`** | 188 occurrences in `DELIV_QTY`/`DELIV_PER`; a `float()` cast crashes, a naive coercion would fabricate zero delivery | Fixed inside the audit harness (counted as missing, never zero-filled) |
| **BUG-056** | Duplicate `(SYMBOL, DATE)` rows from **non-EQ series** | AARTISURF 2026-06-29: `EQ` ₹370.50 vs `P1` ₹244.35; IIFL 2026-09-16: `EQ` vs `T0`. 55,225 non-EQ rows dropped in-window | Fixed inside harness (`SERIES == 'EQ'`, the existing codebase convention) |
| **D5** | Tagged `mae_pct` provenance is **not** reproducible from raw lows, while `mfe_pct` is | ASHIKA 543766: tagged MFE `25.0938` reproduces exactly (`25.094`); tagged MAE `−1.926` vs recomputed `−2.152` (raw low ₹391.10 on 2026-07-23) | OPEN — reported as a diagnostic |
| **BUG-046** (pre-existing) | Day-0 lookback contamination (`>= entry_dt`) in the historical pipeline | documented in `docs/known_bugs.md` | Relevant risk for any retraining |

---

## 5. Round 1 — small-cap Vetoed vs Clean winner audit

### 5.1 Empirical baseline was reproduced **exactly**
| Block | Published | Reproduced | Verdict |
|---|---|---|---|
| B0: 7 day-of-entry order-flow anchor rows (28 checks) | — | all exact, incl. PRARUH ATW ₹697,620.0 | 28/28 PASS |
| B1: 119-trade ledger, `stock_class='S'` | CLEAR 13 / VETO 33 | **13 / 33** | exact |
| B2: 189-trade universe, `stock_class='S'` | CLEAR 20 / VETO 43; ret 6.72/3.47, med 5.60/0.83, MFE 14.02/10.98, MAE −5.73/−4.77 | **identical to 2dp** | exact |
| B4: operating-leverage winsorization, outlier-excluded | MWU 0.0077 / Welch 0.0049 | **0.0077 / 0.0049** | exact |
| Harness result | — | **83 PASS / 0 FAIL / 14 KNOWN**, exit code 0 | clean |

**The one apparent discrepancy (published Clean N=12 vs reproduced 13) was fully attributed**, not force-matched: the extra trade is **UTIAMC** — the single clean winner qualifying *only* via the profitable-chandelier clause at **+1.02%** (entry == exit == 2026-09-02), i.e. below the +3.0% bar the prior audit effectively applied. Excluding it reconciles **all 13 remaining checks**. The headline cohort deliberately keeps it.

### 5.2 Headline: strict `< ₹7,000 Cr` winners — CLEAR n=11 vs VETOED n=19

| Metric | med C | mean C | med V | mean V | p_MWU | p_Welch | p_Levene |
|---|---|---|---|---|---|---|---|
| `return_pct` | +9.620 | +15.864 | +10.764 | +13.278 | 0.5467 | 0.5570 | 0.3747 |
| MFE (tagged) | +17.548 | +21.746 | +14.186 | +19.155 | 0.3016 | 0.6222 | 0.5486 |
| MAE (tagged) | −1.979 | −4.428 | −1.705 | −3.275 | 0.4384 | 0.5070 | 0.1250 |
| MAE (raw recomputed) | −1.979 | −4.990 | −0.767 | −1.649 | 0.1205 | 0.0970 | **0.0153** |
| **`atw_rupees`** | **316,687** | 58,593 | **62,218** | 158,817 | **0.0477** | **0.0217** | **0.0094** |
| **`float_absorbed_pct`** | **0.652** | 0.796 | **1.354** | 1.994 | **0.0388** | **0.0222** | 0.1164 |
| **`op_lev_ratio` (raw)** | **1.214** | 1.388 | **0.744** | 1.441 | **0.0197** | 0.9620 | 0.1484 |
| `roice_pct` | +7.00 | −32.78 | +11.40 | +15.37 | 0.1748 | 0.2709 | 0.0362 |
| `interest_coverage_recent` | 3.720 | 2.120 | 2.250 | 3.546 | 0.6952 | 0.4859 | 0.1117 |
| `fcf_pat_ratio` | +0.500 | −0.734 | −0.170 | −0.537 | 0.3656 | 0.9504 | 0.7026 |
| `pledge_last` | 0.000 | 0.000 | 0.000 | 0.000 | 1.0000 | — | — |

**Finding: inside the strict small-cap winner cohort there is NO statistically significant return, MFE or MAE difference between clean and vetoed names.** The published "10× median edge" is a pooled/ledger-level result, not a small-cap-winner result.

### 5.3 The real divergence is microstructure, and it replicates

| Cohort | n | float cornering (absorb ≥1.5%) | organic leverage (op_lev ≥2) | median ATW | median absorb |
|---|---|---|---|---|---|
| CLEAR winners | 11 | **2 (18.2%)** | 1 | ₹316,687 | 0.65% |
| VETOED winners | 19 | **9 (47.4%)** | 1 | ₹62,218 | 1.35% |

Vetoed winners are **2.6× more likely to absorb ≥1.5% of free float** and show a **fat-tailed ATW** distribution (mean ₹158,817 ≫ median ₹62,218 = a few very large prints). Clean winners show the inverse shape: high median ATW, low mean = broad participation. The ATW divergence **replicates on the independent 119-baseline ledger** (CLEAR median ₹387,762 vs VETO ₹77,477; p_MWU 0.0489, p_Welch 0.0363).

### 5.4 Universal commonalities (shared by BOTH cohorts)
| Commonality | CLEAR | VETOED | Verdict |
|---|---|---|---|
| Promoter pledge | median/mean **0.00%** | median/mean **0.00%** | ✅ confirmed, p=1.0000 |
| Tagged MAE | median −1.98% | median −1.71% | ✅ confirmed, p=0.4384 |
| Entry-day delivery % | median **89.9%** | median **84.6%** | ✅ shared but **non-discriminating** (p=0.8464) |
| Hold duration | 11.0 d | 10.0 d | ✅ shared (p=0.3874) |
| Organic op-lev at entry | 1 of 11 ≥ 2.0× | 1 of 19 ≥ 2.0× | ✅ **neither** ran on visible earnings leverage |

### 5.5 The decisive test: descriptive traits vs causal edges
Spearman ρ vs `return_pct` across the **full** strict small-cap cohort (all 65 trades):

| Metric | n | ρ | p |
|---|---|---|---|
| atw_rupees | 65 | +0.152 | 0.2262 |
| deliv_per | 65 | +0.189 | 0.1316 |
| delivery_turnover_cr | 65 | −0.194 | 0.1222 |
| float_absorbed_pct | 62 | −0.060 | 0.6409 |
| op_lev_ratio | 38 | +0.024 | 0.8843 |
| fcf_pat_ratio | 62 | +0.115 | 0.3743 |
| roice_pct | 43 | −0.016 | 0.9173 |

**Not one metric is a significant predictor of return.** Therefore the significant between-cohort differences above are **cohort descriptors, not trading edges** — a screen built on them would be fitting noise.

### 5.6 Corrections to the commissioning brief (all verified)
1. `data/fundamental_scores.csv` does **not** contain `fcf_pat_ratio` or pledge — both live only in the JSON caches.
2. `data/sbia_ledger.csv` is **N=135**, not 112, and has **no market-cap column**.
3. `market_cap_class` in `trades_ledger.csv` is **stale legacy** (26 `S` rows vs the correct 48; ASHIKA ₹2,952 Cr labelled `M`) — BUG-001 residue.
4. `ATW` / `DELIV_PER` / `DELIVERY_TURNOVER` are **raw-panel/watchlist** fields, not ledger fields.
5. Scrip-code resolution is **necessary**: 15 of 35 small-cap cohort tickers are BSE-only yet all resolve via 6-digit scrip codes.

Coverage/integrity: order-flow **100% resolved (0 missing)**; veto re-derivation from current caches agrees with frozen labels on **116/119 (97.5%)** and **186/189 (98.4%)**.
