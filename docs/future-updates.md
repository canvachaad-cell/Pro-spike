# Pro-Spike Development Roadmap & Task Queue

> **Status:** Active Tracking  
> **Last Updated:** 25 September 2026  
> **Reference:** Auto-loaded via `update !!` command  

---

## 📌 Priority Task Queue

### Task 1: Multi-Channel Trade Exit Notification Engine (Phase 1: Alpha + Corner)
- [ ] **Category:** Alerts & Notifications
- [ ] **Priority:** HIGH
- [ ] **Engines Covered in Phase 1:**
  1. **SBIA Alpha Engine** (`data/sbia_ledger.csv`)
  2. **Corner Spike Scanner** (`data/corner_engine_ledger.csv`)
- [ ] **Exit Triggers to Monitor:**
  - `HIT_SL` (Stop Loss breached)
  - `HIT_TP` (Target Profit reached)
  - `MOMENTUM_LOST` (Time/velocity decay or momentum breakdown)
- [ ] **Notification Channels:**
  - [ ] **In-App / Web Dashboard:** Top header toast banner / Notification Bell center on `/dashboard` and `/institutional-signals` showing timestamped exit cards with PnL.
  - [ ] **Email Dispatcher:** SMTP / API integration sending rich HTML trade cards (Symbol, Entry Date/Price, Exit Date/Price, Net PnL %, Net R-Multiple, Reason).
  - [ ] **WhatsApp Alert Bridge:** Twilio / WhatsApp Business API / Webhook integration dispatching instant structured text alerts.
- [ ] **Technical Architecture:**
  - Create `notifications/` module with `trade_alerter.py` and `dispatcher.py`.
  - Add state diffing in `ledger_manager.py` / `corner_spike_scanner.py`: compare pre-update vs post-update trade status to detect the exact transition from `ACTIVE` -> `HIT_SL` / `HIT_TP` / `MOMENTUM_LOST`.
  - Store unread alerts in `data/alerts_queue.json` for Dash UI consumption.
- [ ] **Verification Bar:**
  - Mock ledger exit event -> Assert alert appears in Dash UI toast, email sent via local test server, WhatsApp payload dispatched with valid exit metadata.

---

### Task 2: Winner Archetypes AI Win Probability Calibration (Fix 55% Static Fallback)
- [ ] **Category:** ML Engine / UI Bug Fix
- [ ] **Priority:** HIGH
- [ ] **Files Affected:**
  - `rank_archetypes.py` (L315-L317)
  - `winner_archetype_data.py` (L69-L73)
  - `dash_pages/winner_archetypes.py` (L426)
  - `data/winner_archetypes_ranked.csv`
- [ ] **Symptom:**
  - 176 out of 178 cards on `/winner-archetypes` display identical **55% AI Win Probability**.
- [ ] **Root Cause:**
  - `rank_archetypes.py:283-317` attempts to map `AI_WIN_PROBABILITY` solely from `data/sbia_alpha_watchlist.csv` (which contains only 2 signals for the latest session).
  - For the remaining 176 symbols screened from historical ledgers, `AI_WIN_PROBABILITY` is `NaN`.
  - `winner_archetype_data.py:70` and `dash_pages/winner_archetypes.py:426` apply a hardcoded `.fillna(55.0)` fallback.
- [ ] **Implementation Fix:**
  - Load `shadow_box_model.pkl` in `rank_archetypes.py` and compute the live model prediction for every symbol:
    ```python
    features = ['SIS', 'Whale_Density', 'Implied_Trades']
    model.predict_proba(df[features])[:, 1] * 100
    ```
  - Map pre-calculated AI probabilities from `data/active_signals_ranked.csv`, `data/signal_scores_today.csv`, `data/flexgate2_ledger.csv`, and `data/corner_engine_ledger.csv`.
- [ ] **Verification Bar:**
  - `data/winner_archetypes_ranked.csv` has a diverse, empirically calculated probability distribution across all 178 cards (ranging between 40% and 95%), with zero fallback clustering at 55%.

---

### Task 3: Legacy FlexGate Active Trades UI Synchronization
- [ ] **Category:** Signal Ledger & UI Data Flow
- [ ] **Priority:** MEDIUM-HIGH
- [ ] **Files Affected:**
  - `calculate_active_signals.py` (L208-L234)
  - `ledger_manager.py` (L444-L469)
  - `dash_pages/institutional_signals.py` (L408-L450, L707-L708)
  - `data/sbia_flexgate_watchlist.csv`
  - `data/flexgate_ledger.csv`
- [ ] **Symptom:**
  - New active trades (e.g. `MOTHERSON` entered on 2026-09-24, `GRASIM`, `INDUSTOWER`, `TATASTEEL`) exist in `data/flexgate_ledger.csv` with `STATUS == 'ACTIVE'`, but are missing from the main table in Tab 3 (Legacy FlexGate) on `/institutional-signals`.
  - Main table displays only 5 older historical rows (last row: `BRGIL` from 2026-09-10).
- [ ] **Root Cause:**
  - `dash_pages/institutional_signals.py:707` renders the top table from `FLEXGATE_FILE` (`data/sbia_flexgate_watchlist.csv`).
  - In `calculate_active_signals.py:209-234`, `sbia_flexgate_watchlist.csv` is populated via `filtered_flex`, which filters by existing keys in `flex_watchlist`. Trades that entered the ledger on days when the raw 10-day 2-alert condition did not re-trigger are omitted from `sbia_flexgate_watchlist.csv`.
- [ ] **Implementation Fix:**
  - Synchronize `sbia_flexgate_watchlist.csv` directly with all `STATUS == 'ACTIVE'` records from `data/flexgate_ledger.csv`.
  - Hydrate active ledger records with current market metrics (`CLOSE`, `DELIV_PER`, current `Whale_Density`) from `data/combined_dashboard_live.csv` so the top table in Tab 3 accurately reflects all active open positions in real time.
- [ ] **Verification Bar:**
  - Open `/institutional-signals` Tab 3 -> Verify all 11 active positions from `flexgate_ledger.csv` (including `MOTHERSON`) appear in the main FlexGate active table with live prices and dynamic Chandelier trailing stop losses.

---

## 📅 Execution Roadmap
| Phase | Task | Primary Dependency | Complexity |
| :---: | :--- | :--- | :---: |
| **Phase 1** | Task 2: Winner Archetypes AI Probability Model Scoring | `shadow_box_model.pkl` | Low-Medium |
| **Phase 2** | Task 3: Legacy FlexGate Active Ledger Table Sync | `calculate_active_signals.py` | Medium |
| **Phase 3** | Task 1: Real-Time Trade Exit Alerts (Web + Email + WhatsApp) | Webhook / SMTP APIs | Medium-High |
