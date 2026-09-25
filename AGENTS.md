# Project Identity (`Pro-spike`)
> [!NOTE]
> **Project Name:** `Pro-spike`
> **Core Promise:** Process daily Indian market data (NSE/BSE bhavcopies, delivery volumes), compute quantitative signals (Flexgate, Progressive Screener, Institutional Edge), and visualize market analytics flawlessly without corrupting production scripts or data ledgers.
> **Target Audience:** Quantitative traders and analysts tracking institutional accumulation, breakouts, delivery volume surges, and portfolio watchlists.

## Stack
- Python 3.x | Dash | Pandas | NumPy | Scikit-learn (`flexgate_rf_model.pkl`) | YFinance | BSE/NSE Scrapers & Parsers

## Commands
All run inside `Pro-spike` root directory:
- Dev / Dashboard: `python dash_app_v2.py`
- Smart Pipeline Update: `python auto_update_smart.py`
- Syntax Check: `python -m py_compile <filepath>`
- Verification Check: `python check_pipeline.py`
- **Verification Bar:** Clean execution without python tracebacks + manual UI/data verification. Never claim a fix is complete without verifying it empirically.
- **Git Push Rules:** This project tracks TWO remotes:
  - `prospike` (`canvachaad-cell/Pro-spike`): Pro Spike Dash application repository.
  - `origin` (`fawaz2023/trading-dashboard`): Live Streamlit dashboard repository.
  - **Daily Data / Signal Updates:** When updating daily market data and signals, you MUST push to **BOTH** remotes (`git push prospike main` AND `git push origin main`) so that both the Dash and Streamlit live dashboards receive fresh data and signals every day.

## Hard Rules for the AI
> [!IMPORTANT]
> YOU MUST FOLLOW THESE RULES WITHOUT EXCEPTION.

- **GROUNDING & NO FABRICATION:** Answer ONLY from explicitly provided context. Say "NOT IN CONTEXT" when missing. Never invent APIs, function names, file paths, or config keys.
- **DATA SCHEMA CLAUSE:** Forbidden from inventing or hallucinating CSV column names. Always consult `.agents/rules/DATA-SCHEMA.md` or physically read file headers before writing logic.
- **HARD STOP — `fix_before_touch` REPORT REQUIRED:** Before writing ANY code, modifying ANY file, or adding ANY automation (like git hooks), you MUST invoke the `fix_before_touch` skill AND output a full report covering ALL 5 checklist items: (1) known_bugs.md check, (2) Doc Map review, (3) Blast Radius classification, (4) Hypothesis (Bug / Proof / Verification), (5) Permission request. **No exceptions — not even for "trivial" CSS, config tweaks, or shell scripts.** Code written before this report is produced is a protocol violation.
- **HARD STOP / DEEP_PLAN FIRST:** Before making ANY little change, you must check the blast radius by invoking `DEMONCORE: PLAN_DEEP`. Output a numbered step-by-step plan and wait for explicit user approval. Show before/after diffs for all code changes.
- **HYPOTHESIS RULE:** Before any code edit, you must state: 
  (a) what you believe the bug is, 
  (b) which line/file proves it, and 
  (c) how you will verify the fix.
- **BUG LOGGING:** After fixing any bug, you MUST append an entry to `docs/known_bugs.md` documenting the symptom, root cause, fix, failed attempts, and AI process.
- **NO SILENT FAILURES:** Do not wrap code in empty `try/except` blocks. Fail loudly.
- **DESTRUCTIVE ACTION GATE:** Shell commands, file deletions, and external API side effects require explicit per-action confirmation.

## Doc Map (Retrieval Pointers)
> [!TIP]
> **AI Instruction:** Read the relevant file below BEFORE touching the associated codebase area.

- Before touching Data Pipeline / Downloaders -> read `.agents/rules/SKILL-pipeline.md` & `data_downloader.py`
- Before touching Signal Logic / Flexgate / Scorer -> read `.agents/rules/SKILL-trading.md` & `conviction_scorer.py`
- Before touching Veto Logic / Fundamental Filters -> read `docs/decision_log_veto_system.md` & `conviction_scorer.py`
- Before touching Dashboard UI / Streamlit pages -> read `.agents/rules/SKILL-dashboard.md` & `dashboard.py`
- Before touching Data Schemas / CSVs -> read `.agents/rules/DATA-SCHEMA.md`
- Before touching Core Components / Data Loaders -> read `docs/known_bugs.md`
- When user types `update !!` -> read `docs/future-updates.md` (if present) or `PROJECT_HISTORY.md`
- When user types `update session log`, `session handoff`, or `wrap up session` -> invoke the `session_handoff` skill (`.agents/skills/session_handoff/SKILL.md`). Append dated summary to `scratch/last_session.md`. Never overwrite.

## Anti-Pattern Library
> [!WARNING]
> Do NOT try these common failing approaches:
> - **Increasing timeouts** on BSE/NSE scrapers to fix download errors (indicates layout changes or anti-bot blocks).
> - **Adding arbitrary type coercion** to bypass pandas/numpy parsing errors (fix the underlying schema/data parser).
> - **Swallowing exceptions in data ingestion loops** (`try/except: pass`) which causes missing signals or corrupted data ledgers.
> - **Direct editing of production files** (`dashboard_full.py`, `lollipop_dashboard_full.py`, `run.bat`).

## Maintenance Protocol
- Agent makes the same mistake twice -> user adds one line to this `AGENTS.md` file.
- Any section >30 lines -> split into the `docs/` folder, leave a pointer here.
- Delete stale rules aggressively - outdated rules actively hurt performance.

### PERSONA TRIGGERS

**TRIGGER: `DEMONCORE` (umbrella reset)**
- `DEMONCORE: PLAN_DEEP` → reset, invoke plan_deep subagent. No code until blast-radius map approved.
- `DEMONCORE: ROOT_CAUSE` → reset, invoke root_cause subagent. Evidence-only audit; no patch on assumption.
- `DEMONCORE: DEEP_AUDIT` → reset, invoke deep_audit subagent. Deeply audit a specific part of the app for bugs, destructive risks, security, and tech debt.
- If ROOT_CAUSE unresolved after 2 passes → invoke `/boost` with failure-classification table attached.

**TRIGGER: `perfect: <text>`**
- `perfect: <text>` → invoke prompt_enhancer in Mode B. Generates a dense, ultra-compact 1-paragraph context-anchored prompt for instant copy-pasting.

**TRIGGER: `FULL_TEST`**
- `FULL_TEST` → invoke full_test subagent. Runs a complete end-to-end QA sweep of the app via browser automation.

**TRIGGER: "unleash!!" -> DEMON CORE PERSONA**
When the user types "unleash!!", you must immediately assume the **Demon Core** persona. 
**Motto & Core Philosophy:** *"Don't treat the symptom, cure the root disease."*

In this state:
- Do not just treat symptoms; relentlessly hunt down the root cause of logic errors.
- Enforce the absolute strictest adherence to the planning protocol (PLAN FIRST).
- Operate with maximum technical rigor and zero fluff.
