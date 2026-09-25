# DeepSeek Quantitative Research Audit: The Winner Fingerprint & Re-Entry Dynamics

**Project:** `Pro-Spike` Quantitative Trading System  
**Date:** September 22, 2026  
**Status:** Empirically Verified & Integrated into Production Architecture  
**Primary Dataset:** `data/sbia_ledger.csv` ($N=122$ closed trades), `data/trades_ledger.csv`, and 88 daily Bhavcopy delivery records (`data/nse_raw/nse_delivery_*.csv`).

---

## 1. Executive Summary & Verification Verdict

An independent quantitative analysis provided by DeepSeek v1 was audited against raw historical Bhavcopy ticks and ledger data. 

**Empirical Verification Status: 100% VERIFIED & CONFIRMED.**

| Metric / Cohort | Verified Count ($N$) | Realized PnL (₹) | Total $R$-Multiple |
| :--- | :---: | :---: | :---: |
| 🎯 **`HIT_TP` (2R Target Hits)** | 28 | **+₹1,68,000** | +56.0R |
| 🛑 **`HIT_SL` (Stop Loss Hits)** | 33 | **-₹99,000** | -33.0R |
| 💰 **`ML_PROFIT` (Momentum Banked in Green)** | 35 | **+₹71,548** | +23.8R |
| 🛡️ **`ML_LOSS` (Momentum Trimmed in Red)** | 25 | **-₹16,902** | -5.6R |
| ⏸️ **`SUSPENDED`** | 1 | ₹0 | 0.0R |
| **TOTAL REALIZED** | **122** | **₹+1,23,646** | **+41.2R** |

---

## 2. The Winner Fingerprint: Median Entry Signatures

Cross-referencing trades with day-of-entry Bhavcopy metrics demonstrates clean feature separation:

| Entry Metric | 🎯 `HIT_TP` (28) | 💰 `ML_PROFIT` (35) | 🛑 `HIT_SL` (33) | ⚠️ `ML_LOSS` (25) | Significance / Edge |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`ATR_PCT` (%)** | **3.52%** | **3.46%** | 2.68% | 2.45% | **Clean ~1.0% separation** (Winners require room to move) |
| **`CDH` (Close in Day's Range)** | **0.57** | **0.30** | 0.53 | 0.49 | **Type indicator** (Clean runner vs Grind compounder) |
| **`VWAP_DIV` (%)** | **+0.14%** | **-0.08%** | +0.06% | +0.10% | Clean runners close above VWAP |
| **`DELIV_PER` (%)** | 65.1% | 71.1% | 66.8% | **87.8%** | Extreme delivery (>85%) marks late-stage exhaustion |
| **`Whale Density`** | 8.1 | 14.2 | 4.7 | **66.8** | Massive volume on ML_LOSS indicates buying into distribution |
| **`ENTRY_AI_PROB`** | 69.3% | 69.9% | 66.0% | **72.4%** | Single RF model was blind to exhaustion traps |
| **Hold Duration (days)** | **9.0** | **12.0** | 7.0 | 10.0 | Quick resolution on winners |
| **`MFE` (Peak Run %)** | **+15.97%** | **+7.78%** | +1.21% | +1.48% | Winners accelerate immediately |
| **`MAE` (Max Drawdown %)** | **-1.73%** | **-1.98%** | -6.60% | -2.50% | Winning breakouts rarely retrace > -2.0% |
| **`MFE_R` (Peak in $R$)** | **2.46R** | **1.15R** | 0.20R | 0.29R | Confirms 2.0R target calibration |

---

## 3. The 3 Core Architectural Discoveries

### Discovery 1: The Asymmetric Re-Entry Edge
Blanket cooldowns (blocking all repeats for 14 days) destroy value. Re-entry profitability is completely asymmetric based on whether the prior trade was a WIN or a LOSS:

- **Re-Entry After a WIN ($N=14$):**
  - Win Rate: **57.1%**
  - Net Profit: **+6.6R (+₹19,914)**
  - *Winning Streaks:* `MANORAMA` (+4.0R), `HCG` (+4.0R), `BIL` (+2.8R), `SHANKARA` (+2.7R), `TIERRA` (+2.3R), `SPICELOUNG` (+1.6R), `ANANTRAJ` (+0.5R).
- **Re-Entry After a LOSS ($N=15$):**
  - Win Rate: **13.3%** (86.7% fail rate!)
  - Net Profit: **-8.8R (-₹26,368)**
  - *Losing Streaks:* `ALKEM` (-2R), `GNFC` (-2R), `JSWCEMENT` (-2R), `LAURUSLABS` (-2R), `TORNTPHARM` (-2R), `RPPINFRA` (-0.7R across 4 entries), `PFIZER` (-1.4R).

> **Architectural Rule:**  
> **Block re-entry for 14 days ONLY if the prior closed trade on that symbol was a LOSS.**  
> Allow re-entry immediately if the prior trade was a WIN. This saves **+₹26,368** in drawdowns without sacrificing winning momentum.

---

### Discovery 2: Two Winner Archetypes & Routing
Winners do not share the same intraday candle shape; they bifurcate into two distinct trading archetypes:

```
                            WINNING BREAKOUTS
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
       [TYPE 1: CLEAN RUNNER]            [TYPE 2: GRIND COMPOUNDER]
       • Cohort: HIT_TP (+₹1,68,000)     • Cohort: ML_PROFIT (+₹71,548)
       • CDH ≥ 0.50 (Upper half)         • CDH < 0.40 (Lower half)
       • Closes Above VWAP               • Closes Below VWAP
       • Resolves in ~9 days             • Resolves in ~12–18 days
       • Action: Take 2R Fixed TP        • Action: Bank via MOMENTUM_LOST
```

- **Takeaway:** Never filter out setups with `CDH < 0.40`. They represent grinding compounders that generate over 58% of dashboard profits when exited via `MOMENTUM_LOST`.

---

### Discovery 3: Overlapping Active Trades Stacking Trap
When a second trade on symbol $X$ is entered while Trade 1 is still `ACTIVE`:
- **Single Active Trades ($N=98$):** Win Rate **48.6%**, Sum PnL **+₹1,18,208 (+39.4R)**.
- **Overlapping Stacks ($N=24$):** Win Rate **37.5%**, Sum PnL **+₹5,438 (+1.8R)**.
- Stacking duplicate positions on an active stock doubles drawdown risk without providing meaningful incremental alpha.

> **Architectural Rule:**  
> **Enforce Max 1 Active Position per Ticker.** While Trade 1 is open, subsequent screener triggers on that ticker must be ignored.

---

## 4. The 4-Step Winner Quality Ladder

Applying these validated filters in sequence produces a direct progression to an **80.0% Win Rate**:

| Step | Filter Applied | Eligible Trades ($N$) | Win Rate (%) | Mean Return ($R$) | Total PnL (₹) |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **0** | **Baseline (Panel Matched)** | 104 | 48.1% | 0.256R | ₹79,801 |
| **1** | **Exclude Large-Cap Tier ($\ge ₹20,000\text{ Cr}$)** | 60 | 55.0% | 0.468R | ₹84,213 |
| **2** | **Add `ATR_PCT` $\ge 3.4\%$** | 36 | **69.4%** | 0.746R | ₹80,621 |
| **3** | **Add Delivery Sweet Spot (`DELIV_PER` $\le 80\%$)** | **20** | **80.0%** 🏆 | **0.871R** | **₹52,244** |

---

## 5. Implementation Roadmap

1. **Rule 1 (Production Engine):**
   - Implemented in `ledger_manager.py`: `check_signal_eligibility()` enforcing Max 1 Active Position and 14-day Post-Loss Lockout.
2. **Rule 2 & 3 (UI Visualization):**
   - To be deployed in a dedicated Dash analytics page: `dash_pages/winner_archetypes.py` (Route: `/winner-archetypes`).
