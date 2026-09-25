# AI Probability — Weight Audit & Root Cause

**Project:** `Pro-spike` Quantitative Trading Engine
**Date:** 23 September 2026
**Trigger:** Round-2 finding that `ENTRY_AI_PROB` is miscalibrated (`docs/known_bugs.md` BUG-057).
**Question:** if the AI probability is wrong, *where* is the weighting wrong, and what carries more weight?
**Method:** read the actual shipped models and their real `feature_importances_`, read the feature
construction and gate code, then test the gate against realised outcomes.

---

## 0. Answer in one paragraph

`AI_WIN_PROBABILITY` is produced by **two different models** that share one column name, and both are
**trained on a single month (July 2026, 82 trades)** with no walk-forward validation. Inside the
8-feature model, **61.5% of the weight sits on features that independently fail predictive tests**
(the ATW/DT order-flow family and the SIS/STABILITY family), while the **one feature that does verify —
`ATR_Pct` — holds only 14.9%**. Inside the 3-feature model, **two of the three inputs are exact
reciprocals of each other** (`Whale_Density` and `Implied_Trades`), so 66.5% of its weight is one
piece of information counted twice. The score is then used as a **hard gate at 60**, which is
**100% non-binding** for two of the three engines (every ledger row already passes it), and whose
label is wrong: names above the gate actually win **52.6%**, not 60%. The measured over-confidence is
**entirely an out-of-sample effect**: in the training month the model is *conservative*
(actual 85.7% vs predicted ~69%), and by September it is *wildly* over-confident
(actual 20.0% vs predicted 73.7%). **This is model staleness, not a scaling bug.**

---

## 1. How the column is actually produced

| Path | Model file | Features | Gate applied |
| :--- | :--- | ---: | :--- |
| SBIA Alpha + FlexGate legacy (`calculate_active_signals.py:187-193`, `:345-351`) | **`shadow_box_model.pkl`** | **3** | `AI_WIN_PROBABILITY >= 60.0` (`:198`, `:361`) |
| FlexGate 2.0 (`flexgate_2_scanner.py:218`) | **`flexgate_rf_model.pkl`** | **8** | `AI_APPROVED = AI_WIN_PROBABILITY >= 60.0` (`:233`) |

Both are `RandomForestClassifier`. **There is no weight-blended composite anywhere** — despite my
initial regex hunt for `w·AI_SCORE`, `AI_WIN_PROBABILITY` is never combined with other metrics by a
weight. It is used three ways only: **(1) a hard ≥60 gate, (2) a descending sort key, (3) a UI badge.**
So "the weightage" of the AI probability is really two separate things — the model's *internal*
feature weights, and the *external* gate threshold.

---

## 2. What weighs more — Model 1 (`shadow_box_model.pkl`, 3 features)

`n_estimators=100`, **`max_depth=4`**, `class_weight='balanced'`.

| Feature | Importance | What it actually is |
| :--- | ---: | :--- |
| `Whale_Density` | **0.3532** | `(ATW / DELIVERY_TURNOVER) × 100000` |
| `SIS` | 0.3350 | `(STABILITY+1)^0.50 × (FOOTPRINT+1)^0.30 × (MOMENTUM+1)^0.20 − 1` |
| `Implied_Trades` | 0.3118 | **`DELIVERY_TURNOVER / ATW`** |

**`Whale_Density` and `Implied_Trades` are exact reciprocals**: `IT = 100000 / WD`. They are the same
number twice. So **0.6650 of the model's weight covers one single input ratio** (ATW ÷ delivery
turnover), and the remaining 0.3350 goes to `SIS` — a pre-weighted composite that already bakes in
STABILITY 50% / FOOTPRINT 30% / MOMENTUM 20%.

**Empirical proof of the redundancy**, from `ablation_output.json`:

| Ablation test | Accuracy | Precision | F1 |
| :--- | ---: | ---: | ---: |
| A: `SIS` alone | **0.5007** | 0.5687 | 0.4556 |
| B: `Whale_Density` alone | 0.5471 | 0.5400 | 0.4716 |
| C: `SIS` + `Whale_Density` | **0.6573529411764707** | **0.679047619047619** | **0.6106959706959707** |
| D: `SIS` + `Implied_Trades` | **0.6573529411764707** | **0.679047619047619** | **0.6106959706959707** |
| E: `SIS` + `Whale_Density` + `Implied_Trades` | 0.6691 | 0.6738 | 0.6262 |

Tests **C and D are bit-identical to 16 decimal places.** The only way that is possible is if
`Whale_Density` and `Implied_Trades` carry identical information — confirming the reciprocal identity
from the data side. **`SIS` alone is 50.07% accuracy: a coin flip.**

Note the ablation's own VIF check *passed* this: VIFs were 1.95 / 1.28 / 1.67. VIF measures **linear**
collinearity, and `1/x` is not linear — so the diagnostic missed it. Likewise `ml_data_prep.py`'s
"drop features correlated > 0.75" rule would not fire (observed corr −0.325), because a reciprocal
relationship does not produce a high Pearson correlation. **The redundancy is invisible to both
existing guards.**

---

## 3. What weighs more — Model 2 (`flexgate_rf_model.pkl`, 8 features)

`n_estimators=500`, `max_depth=7`, `class_weight='balanced'`.

| Rank | Feature | Importance | Family |
| ---: | :--- | ---: | :--- |
| 1 | **`ATR_Pct`** | **0.1493** | volatility |
| 2 | `STABILITY_SCORE` | 0.1320 | order-flow stability |
| 3 | `Implied_Trades` | 0.1230 | **ATW/DT family** (`DT / ATW`) |
| 4 | `Phase2_Volume_Spike` | 0.1230 | `DELIVERY_TURNOVER / DT_1M` |
| 5 | `WHALE_PCTL` | 0.1228 | **ATW/DT family** (percentile of `ATW / DT`) |
| 6 | `SIS` | 0.1198 | composite (50% STABILITY) |
| 7 | `Phase1_ATW_Ratio` | 0.1177 | **ATW family** (`ATW_1M / ATW_3M`) |
| 8 | `Close_vs_VWAP_Pct_Distance` | 0.1124 | price location |

### The distribution itself is the first red flag
Importances span only **0.1124 → 0.1493** — essentially **flat**. A forest trained on data where a
feature genuinely separates the classes produces a *peaked* importance profile. A near-uniform profile
is the signature of a forest splitting on noise, which would leave every feature with roughly
`1/n_features = 0.125`. Observed weights sit within ±0.024 of that. **This is an 8-feature model
behaving like an 8-way arbitrary split.**

### Grouped weight — the real answer to "what weighs more"

| Family | Features | Combined weight |
| :--- | :--- | ---: |
| **ATW / DT order-flow family** | `WHALE_PCTL` + `Implied_Trades` + `Phase1_ATW_Ratio` | **0.3635** |
| **STABILITY / SIS family** (overlapping by construction — SIS is 50% STABILITY) | `STABILITY_SCORE` + `SIS` | **0.2518** |
| Volatility | `ATR_Pct` | 0.1493 |
| Delivery-volume spike | `Phase2_Volume_Spike` | 0.1230 |
| Price location | `Close_vs_VWAP_Pct_Distance` | 0.1124 |

**So the single heaviest item is `ATR_Pct` at 0.1493 — but it is not the heaviest *block*.**
The ATW/DT block (0.3635) is **2.4× its size**, and the ATW/DT + STABILITY/SIS blocks together hold
**0.6153 — 61.5% of the model's total weight.**

## 4. Is that weight justified? — model weights vs independent evidence

Cross-referencing each feature against the Round-1/Round-2 independent tests on the trade ledger:

| Feature family | Model weight | Independent test result | Justified? |
| :--- | ---: | :--- | :--- |
| **`ATR_Pct`** | 0.1493 | **AUC 0.655, p = 0.0011** (best discriminator in the system) | ✅ **YES** |
| ATW/DT family | 0.3635 | `WHALE_DENSITY` AUC 0.466 (p 0.467); `IMPLIED_TRADES` AUC 0.460 (p 0.398); relative `ATW_Z60` p 0.665 | ❌ **NO** |
| STABILITY / SIS family | 0.2518 | `SIS` AUC 0.319 (p 0.063) — **inverted**, quartile win % 29→14→20→**7** | ❌ **NO** (worse than nothing) |
| `Phase2_Volume_Spike` | 0.1230 | delivery-turnover family — Round 1 found delivery/turnover non-discriminating | ❌ untested/negative |
| `Close_vs_VWAP_Pct_Distance` | 0.1124 | not separately tested | ⚠️ unknown |

**Conclusion on weighting:** the model allocates **14.9% of its weight to the only feature that
verifies, and 61.5% to features that fail or invert.** The weighting is not merely mis-tuned — it is
**inverted relative to the evidence**. The near-uniform importance profile means the forest never
found the signal that `ATR_Pct` empirically carries, most likely because there was not enough
training data for it to dominate (see §6).

---

## 5. Where the weight actually bites: the `>= 60` gate

Measured on the 65 strict `< ₹7,000 Cr` trades:

| Cut | n | % of cohort | **actual win %** | mean return |
| :--- | ---: | ---: | ---: | ---: |
| all | 65 | 100% | 47.7 | — |
| **`>= 60` (the gate)** | **57** | **87.7%** | **52.6** | +5.85% |
| `>= 70` | 33 | 50.8% | 54.5 | +7.19% |
| `>= 75` | 14 | 21.5% | **78.6** | +12.47% |
| `< 60` (rejected) | 8 | 12.3% | **12.5** | −5.00% |

Three separate problems:

1. **The label is wrong.** The `>= 60` gate delivers a **52.6%** win rate, not 60% — the ~7 pp gap
   matches BUG-057's over-prediction.
2. **It is nearly non-binding.** 87.7% of trades pass. As a filter it removes only 12% of the flow.
   Worse, per engine it is **100% non-binding**:

| Engine | ledger rows | `>= 60` pass rate | small-cap actual win % | prob sd |
| :--- | ---: | ---: | ---: | ---: |
| `sbia_ledger.csv` | 135 | **135/135 = 100.0%** | **60.0** | 6.69 |
| `flexgate2_ledger.csv` | 21 | **21/21 = 100.0%** | **22.2** | **1.56** |
| `flexgate_ledger.csv` | 79 | 34/79 = 43.0% | **18.2** | **17.01** |

3. **The column is not on one scale.** Standard deviations of 1.56 / 6.69 / 17.01 for the same column
   name mean `ENTRY_AI_PROB` **mixes two models and three distributional regimes**. FlexGate 2's
   probabilities barely vary at all (69.65 – 74.70) yet its small-caps won only 22.2% of the time —
   a near-constant score cannot be a working probability.

**Also note:** because only gate-passing names enter the watchlist and hence the ledger, the ledger is
a **survivor sample of the gate**. Any calibration measured on it is **selection-biased downward**, and
the `< 60` row above (n = 8) exists only for trades pulled from other engines with lower scales.
This is a stated limitation, not a correction.

**And a finding larger than the AI probability:** small-cap win rate by engine is
**60.0% (SBIA) vs 22.2% (FlexGate 2) vs 18.2% (legacy)**. Engine quality matters far more than the
score's calibration.


---

## 6. ROOT CAUSE — the model was trained on ONE month

`data/ml/train.csv` (66 rows) + `data/ml/holdout.csv` (16 rows) = **82 rows total**, dated
**2026-07-01 → 2026-07-31**, across 56 symbols. The entire training and holdout set spans **a single
calendar month**.

| Split | n | `IS_PROFITABLE` base rate |
| :--- | ---: | ---: |
| train | 66 | 44.1% |
| **holdout** | 16 | **75.0%** |
| combined | 82 | 47.6% |

Two problems in that table alone:
* The "temporal holdout" is the **tail of the same month**, not a different market regime — so it is
  not a genuine out-of-sample test.
* The holdout base rate (75.0%) is **31 pp higher** than the training base rate (44.1%). A holdout
  that far from its own training set is a distribution shift, not a validation set.

### The consequence, measured on the live cohort

| Entry month | n | mean `AI_PROB` | **actual win %** | mean return |
| :--- | ---: | ---: | ---: | ---: |
| **2026-07** (**the training window**) | 7 | 69.09 | **85.7** | +5.91% |
| 2026-08 | 53 | 67.24 | **45.3** | +4.66% |
| **2026-09** | 5 | **73.74** ← *most confident* | **20.0** ← *worst* | +0.99% |

**The model's confidence is flat (67 – 74%) across all three months while the realised win rate
collapses 85.7% → 45.3% → 20.0%.** In the training month it is *conservative* (actual 85.7% vs
predicted ~69%); by September it is over-confident by **~54 pp**, and September is the month it feels
**best** about. That is a model with no out-of-sample awareness whatsoever.

This dovetails with Round 2's Angle 2 result: **July 2026 was the single best month in the whole
sample.** The model was fit to the best month and then applied to the worst.

### Why this supersedes the Round-2 recommendation

Round 2 (BUG-057) recommended **isotonic/Platt recalibration, "no retrain needed."** **That
recommendation is withdrawn.** A monotone rescaling cannot repair a model whose *ranking* degrades
out-of-sample — September's highest-probability names won 20% of the time. Recalibrating a stale
model would fit a correction curve to a regime that no longer exists. The correct remedy is
**retraining on a rolling multi-month window with walk-forward validation**.

## 7. Corrected recommendations, in priority order

| # | Action | Rationale | Confidence |
| ---: | :--- | :--- | :--- |
| 1 | **Retrain on a rolling 3–6 month window with walk-forward validation** (train months 1..k, test k+1, roll). Report out-of-sample AUC and calibration per fold. | Single-month fit + same-month "holdout" is the root cause of BUG-057 and of the flat importance profile | High — measured directly |
| 2 | **Do not trust, size, or gate on `ENTRY_AI_PROB` absolute values until (1) is done.** | Above the gate: actual 52.6% vs 60% claimed; September top bucket 20% actual vs 73.7% claimed | High |
| 3 | **De-duplicate the ATW/DT family before retraining.** Keep ONE of `Whale_Density` / `Implied_Trades` / `WHALE_PCTL` (reciprocal or rank-equivalent), and drop `SIS` **or** `STABILITY_SCORE` (SIS is 50% STABILITY by construction). | 61.5% of current weight sits on duplicated, non-predictive information | High — algebraic identity + bit-identical ablation |
| 4 | **Raise `ATR_Pct`'s prominence.** | Only feature that both carries weight and verifies (AUC 0.655, p = 0.0011); already ranked #1 but at only 14.9% | Medium-high |
| 5 | **Re-place the gate.** `>= 60` is 100% non-binding on two engines and mislabelled. Data hints at `>= 75` (78.6% actual, n = 14 — underpowered). Re-derive per engine **after** retraining. | Gate admits 87.7% of flow at a true ~53% win rate | Medium |
| 6 | **Replace the guard-rails that failed to catch this.** VIF and a `abs(corr) > 0.75` rule both miss reciprocal pairs — use rank correlation on `1/x` transforms, or explicit algebraic checks. | The redundancy survived both existing diagnostics | High |
| 7 | **Fix provenance:** one column name, two models, three scales. Store the model id/hash and version alongside each score. | sd 1.56 / 6.69 / 17.01 under one name | High |

## 8. Limitations

1. **Ledger selection bias.** Only gate-passing trades reach the ledger, so calibration is measured on
   a gate-selected sample and is biased downward at the low end. The *within-sample ordering* (AUC)
   and the *monthly drift* remain valid.
2. **The `flexgate_rf_model.pkl` training script is not in the repo.** Its 8-feature set, 500 trees and
   depth 7 match `flexgate_2_scanner.py:218` exactly, but nothing in the repo generates it —
   `train_ml_model.py` produces a **3-feature, 100-tree, depth-4** model instead. The 8-feature
   model's training provenance is therefore **unknown** and cannot be audited further.
3. **Small N on the per-month cut** (July n = 7, September n = 5). The monotone collapse is consistent
   across months, but those two cells are individually underpowered.
4. **`Close_vs_VWAP_Pct_Distance` and `Phase2_Volume_Spike`** have not been independently tested
   against outcomes; their status above is inferential, not measured.

## 9. Reproduce

```bash
# model internals - real importances, not inferred
python -X utf8 -c "import joblib; m=joblib.load('shadow_box_model.pkl'); print(m.feature_names_in_, m.feature_importances_)"
python -X utf8 -c "import joblib; m=joblib.load('flexgate_rf_model.pkl'); print(m.feature_names_in_, m.feature_importances_)"

# ablation (tests C and D are bit-identical)
python -X utf8 -c "import json; print(json.load(open('ablation_output.json'))['results'])"

# training window
python -X utf8 -c "import pandas as pd; d=pd.concat([pd.read_csv('data/ml/train.csv'),pd.read_csv('data/ml/holdout.csv')]); print(d.shape, d.ENTRY_DATE.min(), d.ENTRY_DATE.max(), d.IS_PROFITABLE.mean())"

# gate audit + monthly drift matrix
python -X utf8 scratch/verify_smallcap_round2_angles.py --emit-csv
#   -> scratch/smallcap_round2_features.csv
```

No production file was modified. `conviction_scorer.py`, both `.pkl` models and every ledger are
untouched — this audit is read-only.

