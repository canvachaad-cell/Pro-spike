# Pro-Spike Development Roadmap & Task Queue

> **Status:** Active Tracking  
> **Last Updated:** 25 September 2026  
> **Reference:** Auto-loaded via `update !!` command  

---

## 📌 Priority Task Queue

### Task 1: Multi-Channel Trade Exit Notification Engine (Phase 1: Alpha + Corner)
- [x] **Category:** Alerts & Notifications
- [x] **Priority:** HIGH
- [x] **Engines Covered in Phase 1:**
  1. **SBIA Alpha Engine** (`data/sbia_ledger.csv`)
  2. **Corner Spike Scanner** (`data/corner_engine_ledger.csv`)
- [x] **Exit Triggers to Monitor:**
  - `HIT_SL` (Stop Loss breached)
  - `HIT_TP` (Target Profit reached)
  - `MOMENTUM_LOST` (Time/velocity decay or momentum breakdown)
- [x] **Notification Channels:**
  - [x] **In-App / Web Dashboard:** Top header Notification Bell with unread badge counter (`#notif-badge`) on `/notifications` showing timestamped exit cards with PnL.
  - [x] **Email Dispatcher:** Gmail SMTP over SSL (`notify_channels.py`) sending rich structured trade cards (Symbol, Entry Date/Price, Exit Date/Price, Net PnL %, Net R-Multiple, Reason) to `forexamplekerala@gmail.com`.
  - [x] **Mobile Push Bridge:** Instant high-priority push notifications via `ntfy.sh` topic `prospike-fawaz-alerts-924` (iOS/Android/Web).
- [x] **Technical Architecture:**
  - Created `notify_channels.py` and `alert_engine.py` (read-only diff detector; never corrupts ledgers).
  - Added state diffing in `alert_engine.py`: compares pre-update vs post-update trade status to detect the exact transition from `ACTIVE` -> `HIT_SL` / `HIT_TP` / `MOMENTUM_LOST` / `SUSPENDED`.
  - Persistent dedup log in `data/alerts_log.csv` and state caching in `data/alerts_state.json`.
- [x] **Verification Bar:**
  - Verified with `python alert_engine.py --test-channel` -> `ntfy : True (OK)`, `email : True (OK)`, live push received on phone, email verified in Gmail inbox.

---

### Task 2: Winner Archetypes AI Win Probability Calibration (Fix 55% Static Fallback)
- [x] **Category:** ML Engine / UI Bug Fix
- [x] **Priority:** HIGH
- [x] **Files Affected:**
  - `rank_archetypes.py`
  - `winner_archetype_data.py`
  - `dash_pages/winner_archetypes.py`
  - `data/winner_archetypes_ranked.csv`
- [x] **Symptom:**
  - 176 out of 178 cards on `/winner-archetypes` display identical **55% AI Win Probability**.
- [x] **Root Cause:**
  - `rank_archetypes.py:283-317` attempts to map `AI_WIN_PROBABILITY` solely from `data/sbia_alpha_watchlist.csv` (which contains only 2 signals for the latest session).
  - For the remaining 176 symbols screened from historical ledgers, `AI_WIN_PROBABILITY` is `NaN`.
  - `winner_archetype_data.py:70` and `dash_pages/winner_archetypes.py:426` apply a hardcoded `.fillna(55.0)` fallback.
- [x] **Implementation Fix:**
  - Multi-source AI inheritance across 9 institutional sources in priority order with 100% coverage (17.2% to 83.42%).
  - Anchored candidate setup cards to current market `CLOSE` with fresh 1.5 ATR risk and 3.0 ATR reward; centered visual risk-reward sliders at 33.3% (`BUG-075`).
  - Restored 25% AI weighting to composite `RULE3_SCORE`.
  - Integrated `rank_archetypes.py` into daily pipeline `auto_update_smart.py`.
- [x] **Verification Bar:**
  - `data/winner_archetypes_ranked.csv` has a diverse, empirically calculated probability distribution across all 178 cards, with zero fallback clustering at 55%. Verified in browser and Playwright.

---

### Task 3: Legacy FlexGate Active Trades UI Synchronization
- [x] **Category:** Signal Ledger & UI Data Flow
- [x] **Priority:** MEDIUM-HIGH
- [x] **Files Affected:**
  - `calculate_active_signals.py` (L208-L234)
  - `ledger_manager.py` (L444-L469)
  - `dash_pages/institutional_signals.py` (L408-L450, L707-L708)
  - `data/sbia_flexgate_watchlist.csv`
  - `data/flexgate_ledger.csv`
- [x] **Symptom:**
  - New active trades (e.g. `MOTHERSON` entered on 2026-09-24, `GRASIM`, `INDUSTOWER`, `TATASTEEL`) exist in `data/flexgate_ledger.csv` with `STATUS == 'ACTIVE'`, but are missing from the main table in Tab 3 (Legacy FlexGate) on `/institutional-signals`.
  - Main table displays only 5 older historical rows (last row: `BRGIL` from 2026-09-10).
- [x] **Root Cause:**
  - `dash_pages/institutional_signals.py:707` renders the top table from `FLEXGATE_FILE` (`data/sbia_flexgate_watchlist.csv`).
  - In `calculate_active_signals.py:209-234`, `sbia_flexgate_watchlist.csv` was populated via `filtered_flex`, which filters by existing keys in `flex_watchlist`. Trades that entered the ledger on days when the raw 10-day 2-alert condition did not re-trigger are omitted from `sbia_flexgate_watchlist.csv`.
- [x] **Implementation Fix:**
  - Synchronize `sbia_flexgate_watchlist.csv` directly with all `STATUS == 'ACTIVE'` records from `data/flexgate_ledger.csv`.
  - Hydrate active ledger records with current market metrics (`CLOSE`, `DELIV_PER`, current `Whale_Density`) from `data/combined_dashboard_live.csv` so the top table in Tab 3 accurately reflects all active open positions in real time.
- [x] **Verification Bar:**
  - Open `/institutional-signals` Tab 3 -> Verify all 11 active positions from `flexgate_ledger.csv` (including `MOTHERSON`) appear in the main FlexGate active table with live prices and dynamic Chandelier trailing stop losses. (VERIFIED with Playwright screenshot + tests).

---

## 📅 Execution Roadmap
| Phase | Task | Primary Dependency | Complexity |
| :---: | :--- | :--- | :---: |
| **Phase 1** | Task 2: Winner Archetypes AI Probability Model Scoring | `shadow_box_model.pkl` | Low-Medium |
| **Phase 2** | Task 3: Legacy FlexGate Active Ledger Table Sync | `calculate_active_signals.py` | Medium |
| **Phase 3** | Task 1: Real-Time Trade Exit Alerts (Web + Email + WhatsApp) | Webhook / SMTP APIs | Medium-High |
