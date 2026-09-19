---
name: "Trading Domain Skill"
description: "Loaded when working on SBIA, FlexGate, ledgers, or velocity simulations."
---

# TRADING DOMAIN DIRECTIVES

## 1. Engine Terminology
Always use these exact canonical names:
- **Legacy Screener** (Tab 1)
- **SBIA Alpha Engine** (Tab 2, High-Velocity)
- **FlexGate Engine** (Tab 3, Base-Loading)
- **FlexGate 2.0** (Tab 4, ML Engine)

## 2. Velocity Simulation Arithmetic (IMMUTABLE)
Any velocity simulation must strictly follow this logic:
- `capital = 1000000.0` (₹10 Lakhs)
- **SBIA Risk:** `0.003` (no AI threshold)
- **FlexGate Risk:** `0.002` (AI threshold `65.0`)
- **FlexGate 2.0 Risk:** `0.002` (AI threshold `60.0`)
- **NaN-SL Fallback:** If STOP_LOSS is NaN or entry <= sl, allocate a flat `10%` of capital.
- **Capital Cap:** Max allocation per trade is `10%` of capital.
- **Wins/Losses:** Increment Wins if STATUS in `['HIT_TP', 'MOMENTUM_LOST']` AND `r_pnl > 0`. Increment Losses if STATUS == `HIT_SL` OR `r_pnl < 0`.

## 3. Ledger Rules & Safety
- **STATUS values:** Must be exactly one of: `ACTIVE`, `HIT_TP`, `HIT_SL`, `SUSPENDED`, `MOMENTUM_LOST`.
- **CRITICAL - DO NOT PURGE:** The stock `NOVUS` is manually tracked. Do NOT purge it from `flexgate_ledger.csv` or `flexgate2_ledger.csv`.
- **Unqualified Stocks:** `COALINDIA`, `KOTAKBANK`, `BANKBETA` are strictly unqualified.

## 4. Exchange Handling
When calling external APIs (like yfinance), append exchange suffixes:
- BSE: `.BO`
- NSE: `.NS`

## 5. Fundamental Veto Policy (IMMUTABLE DECISION — Sep 2026)
- **Hard Entry Blockers:** Do NOT loosen or shift Veto metrics (`FCF/PAT Divergence`, `Promoter Pledge`, `RPT %`) to position-sizing controls. They remain strict entry-blocking vetoes.
- **Empirical Grounding (Simpson's Paradox Resolution):** In small-caps (< ₹7,000 Cr), clean fundamentals outperform vetoed names with **+14.83% vs +7.22% peak upside** (MFE, $p=0.0456$) and **+8.15% vs +1.37% net return**. Loosening vetoes directly reduces small-cap expectancy.
- **Promoter Pledge:** 100% lethal in small-caps ($0/5$ winners, $-1.03\%$ return) — strictly non-negotiable hard veto.
- **Reference:** Read `docs/decision_log_veto_system.md` before proposing any changes to conviction scoring or veto states.
