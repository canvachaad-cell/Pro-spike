# Hidden Pattern Discovery — Round 2 (New Angles Only)

**Project:** `Pro-spike` Quantitative Trading Engine
**Date:** 23 September 2026
**Status:** Completed, Empirically Verified, Reproducible
**Harness:** `scratch/verify_smallcap_round2_angles.py` (exit 0, 540 lines of output)
**Evidence matrix:** `scratch/smallcap_round2_features.csv` (65 rows x 78 cols)
**Cohort:** strict `< ₹7,000 Cr` small-caps from `scratch/tagged_trades_all_189.csv`
(65 trades; 31 brief-winners; **CLEAR 11 vs VETOED 19** winners). Win = tagged
`outcome_tag == 'WINNER'`, consistent with Round 1.

Round 1 metrics are **not** recomputed here. Nothing below duplicates the Round-1 exclusion
list (delivery%, turnover, ATW level, float-absorbed%, MAE/MFE, promoter holding *level*,
interest coverage, operating leverage, RoICE, FCF/PAT, market-cap buckets, whale density,
implied trades, SIS, AI win probability, ATR% at entry, day-of-week, re-trigger count,
FII/DII trend, shareholder count, sector clustering, days-to-new-high, pre-entry behaviour).

> **Priority note.** Tier A below was run first and is the most important section in this
> report: `ENTRY_AI_PROB`, `WHALE_DENSITY`, `IMPLIED_TRADES`, `ATR_PCT` and `SIS` are
> **real, already-computed, in-repo columns that had never been tested against actual
> outcomes**. The answer on the model's own confidence score is not flattering.

---

## 0. Data availability — established empirically, before any analysis

| Item | Repo status | Treatment |
| :--- | :--- | :--- |
| `ENTRY_AI_PROB`, `ENTRY_WHALE_DENSITY`, `ENTRY_IMPLIED_TRADES`, `ATR14` | **Real** — all three ledgers share one 12-column schema | **Tier A, tested directly.** 189/189 coverage |
| `SIS` | **Real but watchlist-scoped** — 61/189 cohort rows | Tested, coverage flagged |
| Angle 2 (clustering) | **Real** — pure ledger date arithmetic | Full test |
| Angle 5 (promoter direction) | **Real** — `promoter_trend` quarterly series, 59/65 rows | Full test, no proxy |
| Angle 6 (trailing high/low) | **Real** — BSE panel, 271 sessions, only continuous price history in-repo | Full test, per-row history reported |
| Angle 7 (realised-vol trend) | **Real** — same panel | Full test |
| **Angle 1a/b — Nifty, Sensex, India VIX** | **NOT IN CONTEXT** — zero index/VIX series exist. Every `NIFTY/SENSEX` string in the repo is an *exclusion filter* (e.g. `rank_archetypes.py:27`) | **PROXY** delivered (1c) |
| **Angle 3 — named bulk/block deals** | **NOT IN CONTEXT** — zero disclosure data of any kind. No named buyer can be identified | **PROXY** delivered |
| **Angle 4 — earnings dates** | **NOT IN CONTEXT** — the 35-key fundamental payload has no date field; `rpt_cache.json` has none either | **PROXY** delivered |

**Price panel:** `data/bse_raw/bse_bhav_*.csv` — the only continuous series (271 sessions,
2025-08-04 → 2026-09-22, 15–23 files per month). `historical_full_universe.csv` was rejected:
it stops at 2026-08-12, before ~30% of the cohort's entries. The trading calendar is derived
from the panel's own `BizDt` values (no stale holiday list). All windows are strictly before
the entry date — **no lookahead**.

---

# TIER A — The unvalidated model / flow confidence scores

Full 189-trade universe: **53 tagged winners vs 136 tagged losers**.

### A1. Coverage (no imputation)

| Column | Full cohort | Strict small-cap |
| :--- | ---: | ---: |
| `ENTRY_AI_PROB` | 189/189 | 65/65 |
| `WHALE_DENSITY` | 189/189 | 65/65 |
| `IMPLIED_TRADES` | 189/189 | 65/65 |
| `ATR_PCT` (= ATR14 ÷ entry price) | 178/189 | 63/65 |
| `SIS` | **61/189 (partial)** | 24/65 |

### A2. Win-vs-loss separation — and A3. predictive power

| Score | nW | nL | med win | med loss | p_MWU | p_Welch | **AUC** | p_AUC | rho vs return | p_rho | Verdict |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| **`ATR_PCT`** | 53 | 125 | 3.650 | 2.778 | **0.0011** | **0.0063** | **0.655** | **0.0011** | +0.034 | 0.652 | **SIGNAL (win/loss only)** |
| **`ENTRY_AI_PROB`** | 53 | 136 | 69.90 | 66.22 | **0.0082** | **0.0003** | **0.624** | **0.0082** | **+0.255** | **0.0004** | **SIGNAL — but see A4** |
| `WHALE_DENSITY` | 53 | 136 | 63.15 | 55.89 | 0.4674 | 0.0523 | 0.466 | 0.4674 | +0.069 | 0.344 | **NOISE** |
| `IMPLIED_TRADES` | 53 | 136 | 5 514 | 6 110 | 0.3980 | 0.4390 | 0.460 | 0.3980 | −0.175 | 0.0160 | **NOISE** (AUC ns) |
| `SIS` | 11 | 50 | 0.68 | 0.777 | 0.0633 | **0.0479** | **0.319** | 0.0633 | +0.007 | 0.959 | **NOISE / inverted hint** |

**Reading:**
* **`ATR_PCT` is the single best win/loss discriminator in the whole system** (AUC 0.655).
  But its `rho` against *return size* is 0.034 (p = 0.652) — it separates winners from losers
  without predicting how far a winner runs. Consistent with Round 1's "winners need room".
* **`ENTRY_AI_PROB` does carry real signal** (AUC 0.624, p = 0.008; rho +0.255, p = 0.0004).
  The RF model is **not** blind. That is a genuine result.
* **`WHALE_DENSITY`, `IMPLIED_TRADES` and `SIS` are not predictors.** `WHALE_DENSITY`'s
  mean/median divergence (mean 249 vs 3 026) is pure tail noise. `SIS` is *inverted* in
  direction (higher SIS → lower win rate) but underpowered at n = 11.

### A4. Calibration of `ENTRY_AI_PROB` — THE HEADLINE FINDING

`ENTRY_AI_PROB` is a probability, so its ordering and its level both matter.

| Cohort | n | tagged win rate | Brier (model) | Brier (base rate) | Verdict |
| :--- | ---: | ---: | ---: | ---: | :--- |
| Full 189 | 189 | 28.0% | **0.3266** | 0.2018 | model is **WORSE than the base rate** |
| Strict `< ₹7,000 Cr` | 65 | 47.7% | **0.2692** | 0.2495 | model is **WORSE than the base rate** |

**Full-189 calibration curve — every bucket over-predicts:**

| Predicted bucket | n | predicted % | actual % | gap |
| :--- | ---: | ---: | ---: | ---: |
| 18.5 – 31.6 % | 7 | 26.4 | 14.3 | −12.1 |
| 31.6 – 44.5 % | 14 | 36.9 | **0.0** | **−36.9** |
| 44.5 – 57.5 % | 18 | 49.1 | **11.1** | **−38.0** |
| 57.5 – 70.5 % | 77 | 65.6 | 32.5 | **−33.1** |
| 70.5 – 83.4 % | 73 | 75.9 | 34.2 | **−41.7** |

Hosmer-Lemeshow **χ² = 125.79, df = 3, p = 0.0000** → conclusively **miscalibrated**.
Strict small-cap subset: χ² = 13.55, df = 3, p = 0.0036 → same failure.

**What this means.** The model **ranks** acceptably (AUC 0.624) but is systematically
**over-confident by roughly 20–42 percentage points**, and never once predicts at the level
it claims. A "76% win probability" print is empirically associated with a ~34% win rate.
This is a **calibration defect, not a discrimination defect** — and it is the single most
actionable finding across both rounds, because the number is surfaced in the UI.

### A5. Quartile behaviour

| `ENTRY_AI_PROB` quartile | n | win % | mean ret % |
| :--- | ---: | ---: | ---: |
| 18.6 – 61.0 | 48 | **12.5** | −3.16 |
| 61.0 – 68.0 | 50 | 30.0 | +0.88 |
| 68.0 – 73.3 | 45 | 35.6 | +1.31 |
| 73.3 – 83.4 | 46 | 34.8 | **+3.90** |

Monotone across the first three quartiles; Fisher top-vs-bottom **p = 0.0274** (16/32 vs 6/42).
The *ordinal* information is real — only the *level* is wrong.

`SIS` quartiles run the wrong way (29.4% → 14.3% → 20.0% → **6.7%**), Fisher p = 0.1748 —
directionally inverted but not significant at n = 15/quartile.

### A6. Do the scores differ by veto status? (strict small-cap winners, CLEAR 11 vs VETOED 19)

| Score | median CLEAN | median VETOED | p_MWU | p_Welch |
| :--- | ---: | ---: | ---: | ---: |
| `ENTRY_AI_PROB` % | 75.95 | 69.90 | 0.2188 | 0.1728 |
| `WHALE_DENSITY` | 99.6 | 290.9 | 0.1681 | 0.4727 |
| `IMPLIED_TRADES` | 1 004 | 344 | 0.2628 | 0.6982 |
| `ATR_PCT` % | 4.92 | 3.89 | 0.2819 | 0.1074 |
| `SIS` | 0.63 | 0.776 | 0.0358 | 0.0183 | *(n = 3 vs 5 — underpowered)* |

The model mildly prefers CLEAN names, but **not significantly** — so the veto system and the
RF score are measuring different things, not disagreeing.


---

# The seven new angles — one table each

## Angle 2 — Concurrent winner clustering **(PRIORITY)**
Pure ledger date arithmetic; no proxy, no external data.

| Cohort | n | winners | weeks | top-2-week winner share | **perm p (top-2)** | between-week return SS | **perm p (dispersion)** |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ALL strict small-cap | 65 | 31 | 8 | 45.2% | **0.9850** | 398.9 | **0.9272** |
| strict small-cap winners | 31 | 31 | 8 | 45.2% | 1.0000 | 855.3 | 0.3133 |
| FULL 189 universe | 189 | 53 | 11 | 34.0% | **0.9883** | 1 058.9 | **0.2502** |
| CLEAN winners | 11 | 11 | 6 | 54.5% | 1.0000 | — | 0.3685 |
| VETOED winners | 19 | 19 | 7 | 47.4% | 1.0000 | — | 0.4589 |

**Concurrency density** (`N_CONCURRENT_3D` = other cohort trades within ±3 sessions):

| Cohort | low-density quartile | high-density quartile | mean ret low vs high | p_MWU | win % low vs high | **Fisher p** |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| strict small-cap | ≤ 10 (n=17) | ≥ 27 (n=22) | +3.81% vs +0.59% | 0.2286 | 58.8% vs 36.4% | 0.2057 |
| **FULL 189** | ≤ 14 (n=49) | ≥ 57 (n=51) | +1.12% vs −1.23% | 0.1192 | 40.8% vs 17.6% | **0.0150** |

**VERDICT — the clear answer you asked for:**
* **The edge is NOT period luck.** Every temporal-concentration permutation p-value is
  **large** (0.25 – 0.99; the smallest is 0.2502 on the full universe, and 0.9272 / 0.9850 on
  the small-cap cohort). Outcomes are **not** clustered in time beyond chance. Wins are
  scattered across all 8–11 weeks, so this is **not** "small-caps as a whole did well in
  August". That materially raises confidence in the edge's durability.
* **But crowding has a measurable cost.** Independently of *when* trades fire, trades that fire
  while many other trades are firing do materially worse: on the full 189 universe
  **40.8% → 17.6% win rate (Fisher p = 0.0150)**. That is a *cross-sectional density* effect,
  not a period effect, and it is the one actionable timing caution in this report.
* Honest caveat: the monthly win rate does drift down (small-cap Jul 85.7% → Aug 45.3% →
  Sep 20.0%; universe 45.5% → 27.8% → 3.3%). September has only n=5 / n=30, and a monotone
  drift is not the same thing as clustering — my dispersion tests place the drift inside
  chance. Flagged, not concluded.

## Angle 1c — Market regime / breadth at entry — **PROXY**
*NOT IN CONTEXT: Nifty, Sensex and India VIX do not exist in this repo. Proxy =
equal-weighted market index + breadth (% of the decontaminated universe above its 50-session
mean), both built from the BSE panel. Regime = index vs its own 20/50-session MAs.*

| Cut | group A | group B | p_MWU | p_Welch / Fisher | Verdict |
| :--- | :--- | :--- | ---: | ---: | :--- |
| Clean vs Vetoed — `BREADTH_PCT` | 46.15 | 47.22 | 0.1609 | 0.5106 | noise |
| Clean vs Vetoed — `MKT_20D_PCT` | +0.73 | +0.66 | 0.4503 | 0.3493 | noise |
| Clean vs Vetoed — `MKT_60D_PCT` | +0.14 | +1.01 | 0.1883 | 0.1728 | noise |
| **By regime, win % (all small-cap)** | chop **42.0%** (n=50) | uptrend **66.7%** (n=12) | — | Fisher 0.1974 | hint, ns |
| By breadth ≥ 50% | False 47.5% (n=59) | True 50.0% (n=6) | — | Fisher 1.0000 | noise |
| Win vs loss — `BREADTH_PCT` | 46.74 | 46.56 | 0.5581 | 0.6276 | noise |
| Win vs loss — `MKT_60D_PCT` | +0.60 | +0.88 | 0.2184 | 0.1528 | noise |

**VERDICT — NOISE.** Mean return in an uptrend (+9.04%) is more than double chop (+3.45%) and
the uptrend win rate is 66.7%, but with n = 12 that does **not** clear significance (Fisher
p = 0.1974), and every proxy test is flat. Do **not** build a regime filter on this.

## Angle 3 — Block-print anomaly — **PROXY**
*NOT IN CONTEXT: the repo holds **no** bulk-deal or block-deal disclosures, so no named buyer
can ever be identified. Proxy = entry-day block print as a z-score against the stock's **own**
trailing 60-session baseline (Round 1 used only the absolute cross-sectional level).*

| Cut | nA | median A | median B | p_MWU | p_Welch | Verdict |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| Clean vs Vetoed — `ATW_Z60` | 8 / 16 | 1.010 | 0.229 | 0.1500 | 0.2398 | noise |
| Clean vs Vetoed — `ENTRY_NTRADES_BSE` | 8 / 16 | 270 | 103 | 0.2090 | 0.2482 | noise |
| Win vs loss — `ATW_Z60` | 25 / 23 | 0.820 | 0.338 | 0.6647 | 0.2556 | noise |
| Win vs loss — `NTRADES_Z60` | 25 / 23 | 0.780 | −0.114 | 0.2313 | 0.7801 | noise |
| Win vs loss — `ENTRY_ATW_BSE` ₹ | 25 / 23 | 44 335 | 25 378 | 0.5773 | 0.9596 | noise |
| Win vs loss — `ENTRY_NTRADES_BSE` | 25 / 23 | 160 | 143 | 0.6647 | 0.5568 | noise |
| `ATW_Z60` quartiles (win %) | 12/12/13/11 | 58.3 / 33.3 / 53.8 / 63.6 | — | Fisher 1.0000 | — | noise |

**VERDICT — NOISE.** The relative block-print measure produces neither a cohort difference nor
a monotone quartile ladder. Note the sign inconsistency: on this BSE-internal measure CLEAN
winners show the *higher* `ATW_Z60` (1.01 vs 0.229), the **opposite** of Round 1's
cross-exchange absolute ATW finding — a further reason not to act on the ATW family.

## Angle 4 — Corporate-event proximity — **PROXY**
*NOT IN CONTEXT: no earnings or announcement dates exist anywhere in this repo. Proxy =
deterministic quarter-end proximity. Indian results typically land 30–60 days after period
end — this is a **calendar proxy, not an announcement date**.*

| Days since last quarter-end | n | wins | win % | mean ret % | median ret % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 0–15 d | 0 | 0 | — | — | — |
| 16–30 d | 5 | 5 | **100.0** | +7.11 | +6.37 |
| 31–45 d | 17 | 8 | 47.1 | +4.44 | +0.83 |
| 46–60 d | 35 | 14 | 40.0 | +3.58 | 0.00 |
| > 60 d | 8 | 4 | 50.0 | +7.09 | +2.51 |

Fisher 16–30 d vs > 60 d: **p = 0.1049**. Clean vs Vetoed winners — `DAYS_SINCE_QE`
(51.0 vs 52.0, p_MWU = 0.3537) and `DAYS_TO_NEXT_QE` (41.0 vs 40.0, p_MWU = 0.3537): both flat.

**VERDICT — NOISE.** The only lopsided bucket (16–30 d, 5/5) is underpowered at n = 5 and is a
pure calendar artefact. No earnings-reaction or pre-earnings pattern is detectable.

## Angle 5 — Promoter action **direction** (real data, no proxy)

| Promoter direction | n | wins | win % | mean ret % | median ret % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| **increasing** | 10 | 9 | **90.0** | **+9.53** | +7.75 |
| flat | 37 | 16 | 43.2 | +3.29 | +0.83 |
| **decreasing** | 12 | 3 | **25.0** | **+0.96** | −1.95 |

**Fisher increasing vs decreasing: p = 0.0037** (9/1 vs 3/9). Clean vs Vetoed winner deltas:
`PROMOTER_DELTA_1Q_PP` 0.00 vs 0.00 (p_MWU = 0.2919, p_Welch = 0.1213);
`PROMOTER_DELTA_2Q_PP` 0.02 vs 0.00 (p_MWU = 0.4509, p_Welch = 0.1503).
Series available for 59/65 strict small-cap trades.

**VERDICT — SIGNAL, and the strongest genuinely-new finding in Round 2.** Monotone across all
three buckets (90% → 43% → 25% win rate; +9.53% → +3.29% → +0.96% mean return) at p = 0.0037.
Critically it is **independent of veto status** — the stake deltas do not differ meaningfully
between CLEAN and VETOED winners, so it is a *cross-cutting* signal rather than a restatement
of the FCF/PAT veto.

**Caveats, stated plainly:** (a) `increasing` is n = 10, exactly at the underpowered boundary;
(b) a stake rise can also come from a buyback, a creeping acquisition or a preferential
allotment — this is **not** proof of an open-market purchase, only of *direction*;
(c) quarter labels are period-ends and correctness depends on the fetcher having captured the
latest filed quarter.

## Angle 6 — Trailing high / low proximity (real data, no proxy)
*Window = min(252, available) sessions **strictly before** entry. 21 of 65 trades have < 120
sessions of history — flagged per row, never silently accepted.*

| Cut | nA / nB | median A | median B | p_MWU | p_Welch | Verdict |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| Clean vs Vetoed — `PCT_FROM_HIGH` | 8 / 16 | −26.36 | −18.66 | 0.8782 | 0.1380 | noise |
| Clean vs Vetoed — `PCT_FROM_LOW` | 8 / 16 | +25.03 | +40.01 | 0.3743 | 0.8292 | noise |
| Clean vs Vetoed — `RANGE_POSITION` | 8 / 16 | 0.380 | 0.336 | 0.9756 | 0.8520 | noise |
| Win vs loss — `PCT_FROM_HIGH` | 25 / 23 | −21.93 | −25.88 | 0.6203 | 0.7553 | noise |
| Win vs loss — `PCT_FROM_LOW` | 25 / 23 | +29.46 | +37.23 | 0.7569 | 0.9894 | noise |
| Win vs loss — `RANGE_POSITION` | 25 / 23 | 0.430 | 0.339 | 0.6797 | 0.7554 | noise |
| Buckets within 2% → < −20% (win %) | 3/4/1/8/31 | 66.7 / 50.0 / 0.0 / 62.5 / 48.4 | — | Fisher 1.0000 | — | noise |
| `PCT_FROM_LOW` quartiles (win %) | 12 each | 41.7 / 66.7 / 50.0 / 50.0 | — | Fisher 1.0000 | — | noise |

**VERDICT — NOISE.** No momentum-continuation vs turnaround-recovery separation at all — on
either framing, in either cohort. The "why is different money buying" question is **not**
answerable from price geometry.

## Angle 7 — The stock's own volatility trend (real data, no proxy)

| Cut | nA / nB | median A | median B | p_MWU | p_Welch | Verdict |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| **Clean vs Vetoed — `VOL_RATIO_20_60`** | 8 / 16 | **1.150** | **0.994** | **0.0465** | **0.0232** | **SIGNAL (conditional)** |
| Clean vs Vetoed — `VOL_DELTA_PCT` | 8 / 16 | +4.52 | −13.11 | 0.0808 | 0.0799 | suggestive |
| Clean vs Vetoed — `VOL20_PCT` | 8 / 16 | 2.34 | 3.00 | 0.7828 | 0.8793 | noise |
| Clean vs Vetoed — `VOL60_PCT` | 8 / 16 | 2.75 | 2.89 | 0.4811 | 0.3379 | noise |
| Win vs loss — `VOL_RATIO_20_60` | 25 / 21 | 0.960 | 0.992 | 0.2607 | 0.1405 | noise |
| Win vs loss — `VOL_DELTA_PCT` | 25 / 21 | −6.69 | −5.67 | 0.9824 | 0.9757 | noise |
| `VOL_EXPANDING` → win % | False 25 / True 21 | 56.0 / 52.4 | — | Fisher 1.0000 | — | noise |
| `VOL_DELTA_PCT` quartiles (win %) | 12/11/11/12 | 50.0 / 63.6 / 54.5 / 50.0 | — | Fisher 1.0000 | — | noise |

**VERDICT — CONDITIONAL SIGNAL.** Realised volatility was **expanding into the signal for CLEAN
winners** (ratio 1.15 > 1) and **flat-to-contracting for VETOED winners** (0.994); the
vol-trend delta points the same way (+4.5% vs −13.1%, p ≈ 0.08). But the identical metric is
**pure noise for win-vs-loss** (p ≥ 0.14). It separates the two *winner* cohorts without
predicting who wins — a descriptive trait, not an edge.

---

# Summary — what added signal, what was noise

## 1. ANGLE 2 IS THE ONE TO TAKE TO THE BANK (your priority question)

**The edge is NOT period-specific.** Temporal-concentration permutation tests return
**p = 0.9850 and 0.9272** on the strict small-cap cohort and **p = 0.9883 / 0.2502** on the
full 189 universe. Winner counts are *less* concentrated in the best two weeks than a random
draw would produce. With 31 winners spread across 8 distinct weeks (Jul 16 → Sep 04), the wins
are scattered — **not** one lucky window. **Verdict: the edge looks durable, not a period
artefact.**

**The caveat that comes with it matters:** *cross-sectional crowding* is a real cost even
though *calendar clustering* is not. On the full universe, trades fired when ≥ 57 other cohort
trades were firing won **17.6%** of the time versus **40.8%** for the low-density quartile
(Fisher **p = 0.0150**). The edge does not decay because of *when* it is — it decays because of
*how many signals fire at once*.

## 2. Scoreboard — Tier A plus all seven angles

| # | Angle | Data status | Verdict | Strongest evidence |
| ---: | :--- | :--- | :--- | :--- |
| **A** | **`ENTRY_AI_PROB` (RF model)** | **Real, 189/189** | **CALIBRATION DEFECT** | AUC 0.624 (p=0.008) **but** Brier 0.3266 vs base 0.2018; HL χ²=125.8, p=0.0000; over-predicts 12–42 pp in **every** bucket |
| **A** | `ATR_PCT` | Real, 178/189 | **SIGNAL (win/loss only)** | AUC **0.655**, p=0.0011 — best discriminator in the system; rho vs return 0.034 (p=0.652) |
| **A** | `WHALE_DENSITY` | Real, 189/189 | **NOISE** | AUC 0.466, p=0.467; mean/median gap is tail noise |
| **A** | `IMPLIED_TRADES` | Real, 189/189 | **NOISE** | AUC 0.460, p=0.398 |
| **A** | `SIS` | Real but 61/189 | **NOISE / inverted hint** | AUC 0.319, p=0.063; quartile win % 29→14→20→**7** |
| **2** | Concurrent winner clustering | Real, full | ✅ **CLEAR ANSWER — durable** | perm p **0.9850 / 0.2502** → no clustering; crowding Fisher **p=0.0150** |
| **1c** | Market regime / breadth | **PROXY** | ❌ **NOISE** | all p ≥ 0.15; uptrend n=12 only, Fisher 0.1974 |
| **3** | Block-print anomaly | **PROXY** | ❌ **NOISE** | all p ≥ 0.15; quartile Fisher 1.0000; sign flips vs Round 1 |
| **4** | Quarter-end proximity | **PROXY** | ❌ **NOISE** | Fisher 0.1049 on an n=5 bucket; Clean/Vetoed p = 0.354 |
| **5** | **Promoter direction** | **Real, 59/65** | ✅ **SIGNAL — best new find** | win % 90 / 43 / 25 monotone; Fisher **p = 0.0037**; independent of veto status |
| **6** | Trailing high / low | Real (21/65 short history) | ❌ **NOISE** | every p ≥ 0.14; bucketed Fisher 1.0000 |
| **7** | Own-volatility trend | Real | ⚠️ **CONDITIONAL** | Clean vs Vetoed `VOL_RATIO_20_60` p=0.0465/0.0232, but win-vs-loss p ≥ 0.14 |

## 3. The three things worth acting on (in order)

1. **Fix `ENTRY_AI_PROB` calibration.** It is the number shown to the user, it is
   systematically ~20–42 pp too high, and it is worse than simply quoting the base rate. The
   *ranking* is fine (AUC 0.624) — this is a **Platt / isotonic recalibration** job, not a
   model rebuild. Until then, do not read a displayed 76% as a 76% win probability.
2. **Promoter stake direction is a live, independent signal** (p = 0.0037, monotone). It is not
   in the veto stack and not in the score. Worth its own review before any wiring — and it is
   direction-only, not proof of open-market buying.
3. **Crowding guard.** Signal density predicts outcome (p = 0.0150) while no calendar effect
   exists anywhere. A "too many signals at once" throttle is the only timing rule this data
   supports; a period-based cooldown is **not** supported.

## 4. Explicitly not supported by this data

Nifty/Sensex/VIX regime filters (no data; proxy flat), named bulk/block-deal detection (no
data exists), earnings-proximity selection (no data exists), 52-week high/low positioning (no
signal), `WHALE_DENSITY` / `IMPLIED_TRADES` / `SIS` as predictive scores (no signal), and
ATW-family measures as a signal (Round 1 and Round 2 disagree on sign).

## 5. Limitations

1. **Small N throughout.** Strict small-cap = 65 trades / 31 winners; CLEAR 11 vs VETOED 19.
   Several cuts sit at or below n = 10 and carry `[UNDERPOWERED n<10]` in the raw output.
2. **Multiple comparisons.** ~40 p-values across Tier A + 7 angles, uncorrected. Under a
   Bonferroni-style α the **promoter-direction** result (p = 0.0037) survives; the Angle-7
   `VOL_RATIO` result (p ≈ 0.02–0.05) does not.
3. **Tier A's win/loss sample is not the veto cohort.** A2–A4 use all 189 trades (53 winners /
   136 losers) because that is where the power is; A6 is the strict Clean-vs-Vetoed view.
4. **`SIS` coverage is only 61/189**, so its null is the weakest in Tier A.
5. **`ENTRY_AI_PROB` is a model output, not an independent measurement** — its AUC partly
   reflects its own training features, so it is not orthogonal evidence. The calibration
   finding is independent of that caveat.
6. **Proxies are proxies.** Angles 1c, 3 and 4 are in-repo substitutes, labelled `PROXY` in
   both the code and this report. They are **not** Nifty, **not** bulk-deal disclosures and
   **not** earnings dates.

## 6. Reproduce

```bash
python -m py_compile scratch/verify_smallcap_round2_angles.py
python -X utf8 scratch/verify_smallcap_round2_angles.py            # -> exit 0
python -X utf8 scratch/verify_smallcap_round2_angles.py --emit-csv # + feature matrix
#   -> scratch/smallcap_round2_features.csv  (65 rows x 78 cols)
```

The permutation test is seeded (`RNG_SEED = 20260923`, 10,000 draws), so those p-values are
stable across runs. `conviction_scorer.py` was imported read-only and is byte-identical.



