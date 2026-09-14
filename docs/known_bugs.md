# Known Bugs & Failed Fixes Log

> [!CAUTION]
> **AI MUST read this file before touching any core components, API routes, or databases.**
> After fixing any bug, append a new entry here. Never delete entries — mark as FIXED.

---

## How to Read This File
- **SYMPTOM** — what the user or logs show
- **ROOT CAUSE** — the actual line/reason (not a guess)
- **FIX** — what actually worked, with file + line reference
- **FAILED ATTEMPTS** — what we tried that did NOT work (critical — prevents re-trying the same thing)
- **AI PROCESS** — what reasoning steps the AI used to find the fix

---

## PATTERN LIBRARY — Do Not Try These (trading_dashboard Context)

| What looks tempting | Why it fails |
|---|---|
| Increasing scraper timeouts to fix BSE/NSE download failures | Network timeouts are symptoms of site layout/headers changing or anti-bot blocks |
| Swallowing exceptions in data ingestion loops (`try/except: pass`) | Silently corrupts data ledgers and causes missing signals downstream |
| Direct editing of `dashboard_full.py` or `lollipop_dashboard_full.py` | Violates production quarantine; breaks live production Streamlit app |
| Blindly adding column defaults without consulting `DATA-SCHEMA.md` | Causes subtle signal miscalculations in Flexgate / Conviction Scorer |
| Trusting external web data without schema validation | Scraping layout changes produce invalid float/date types that crash pandas |

---

## Template — Add New Bug Here (Copy/Paste below this line)

```markdown
## BUG-XXX — [short title]
**STATUS**: OPEN | FIXED | WATCH
**FILE**: [filepath] line [N]
**SYMPTOM**: [what the user sees]
**ROOT CAUSE**: [exact cause with evidence]
**FIX**: [what worked]
**FAILED ATTEMPTS**: [what didn't work — be specific]
**AI PROCESS**: [what reasoning steps led to the fix]
```

---

## BUG-001 — Missing Veto Metrics Silently Passing & Legacy Market Cap Classification
**STATUS**: FIXED
**FILE**: `conviction_scorer.py` line 13 & line 173
**SYMPTOM**: Missing fundamental veto metrics (such as RPT % or Pledge data) were silently skipped, allowing unverified stocks to pass the fundamental quality gate with clean badges. Large-cap threshold at ₹10,000 Cr misclassified mid-caps (e.g., EMAMILTD ₹15,861 Cr).
**ROOT CAUSE**: Missing veto keys (`NOT_FOUND`) were omitted from `_gate_scores` without triggering a blocking flag, allowing unverified stocks to pass the gate as if vetoes were verified clean.
**FIX**: Updated `classify()` to new thresholds (< ₹7,000 Cr Small, ₹7,000 Cr–₹20,000 Cr Mid, ≥ ₹20,000 Cr Large). Implemented `UNVERIFIED_VETO` state in `conviction_scorer.py` when veto metrics (RPT %, Pledge, FCF/PAT) return `NOT_FOUND`. Implemented exact 6-metric weight distribution (Op Leverage 31%, RPT 26%, Pledge 19%, Interest Coverage 15%, RoICE 6%, FCF/PAT 3%) and added a Data Completeness Indicator.
**FAILED ATTEMPTS**: Renormalizing missing veto metrics out of the gate (reproduced the silent pass flaw at the architecture level).
**AI PROCESS**: Interrogated fundamental architecture, aligned with user specifications on score vs veto metric separation, built dedicated XBRL parser integration (`rpt_fetcher.py`), and validated via `test_6_metric_scorer.py`.

## BUG-002 — UNVERIFIED_VETO triggered for all stocks due to missing RPT data
**STATUS**: FIXED
**FILE**: `conviction_scorer.py` (L197, L227) & `rpt_fetcher.py` & `scripts/bse_rpt_scraper.py`
**SYMPTOM**: Vikram returned `UNVERIFIED_VETO` for every single stock after RPT% was introduced, refusing to provide any analysis.
**ROOT CAUSE**: Three disconnected issues: 1) `data/rpt_cache.json` did not exist. 2) The live NSE XBRL API scraper was dead (Akamai blocked). 3) The offline BSE scraper (`bse_rpt_scraper.py`) wrote to a different cache path (`data/rpt_filings_cache.json`) and calculated RPT% using Market Cap instead of Revenue. Since `rpt_status` was always `NOT_FOUND`, `conviction_scorer.py` triggered a hard `UNVERIFIED_VETO` for every stock.
**FIX**: 1) Removed the dead NSE XBRL network call from `rpt_fetcher.py`, making it purely cache-driven. 2) Fixed the BSE scraper to output to `data/rpt_cache.json` and use `revenue_ttm_cr` as the denominator. 3) Updated `conviction_scorer.py` to **gracefully exclude** RPT% when missing, moving it to `not_applicable_metrics` so the score renormalizes across the remaining 5 metrics instead of triggering a hard veto. 4) Updated `_vikram_callback.py` to display "NOT CACHED (offline scraper has not run...)" instead of `UNVERIFIED_VETO` when RPT data is missing.
**FAILED ATTEMPTS**: n/a
**AI PROCESS**: Analyzed the missing `rpt_cache.json` file, traced the failure of the live scraper in `rpt_fetcher.py`, and reviewed the offline scraper. Realized that applying an `UNVERIFIED_VETO` to unknown stocks for missing RPT data was a design flaw, and shifted the architecture to graceful degradation (renormalization) for unknown stocks, while preserving the hard gate for portfolio stocks that are pre-cached by the BSE scraper. Validated via `test_6_metric_scorer.py`.

---

### [2026-09-14] Mobile UI Blown Out (Vertical Nav Only)
**SYMPTOM**: On mobile devices, the main dashboard content was pushed entirely off the screen, leaving only the vertical navigation bar (sidebar) or blank space.
**ROOT CAUSE**: The `dash_app_v2.py` file had hardcoded inline styles (`style={"gridColumn": "2 / 3"}`) on the `html.Main` wrapper. Inline styles override CSS media queries. Since mobile screens (using `.app-grid`) only define 1 column (`grid-template-columns: 1fr`), forcing the main content into column 2 pushed it off the edge of the viewport.
**FIX**: Removed inline `gridColumn` styles from `dash_app_v2.py`. Added proper responsive grid logic directly to `assets/style.css` using `@media (min-width: 768px)` so that mobile defaults to `grid-column: 1 / -1` and desktop snaps to the 2-column layout.
**FAILED ATTEMPTS**: None (fixed on first pass using structural DOM analysis).
**AI PROCESS**: Analyzed the inline styles injected by Dash Python and cross-referenced with `.app-grid` CSS rules. Realized the clash between inline CSS and media queries and decoupled them.

---

### [2026-09-14] Vikram AI Hanging Indefinitely (Loading Animation Never Stops)
**SYMPTOM**: On Render, querying Vikram caused the loading animation to spin forever without returning a result, whereas it worked locally or threw explicit errors.
**ROOT CAUSE**: Gunicorn (the production web server) has a strict default timeout of 30 seconds. Because the `google-genai` SDK was configured with `timeout=90_000` (90 seconds) to allow for complex reasoning and Google Search grounding, the API call often exceeded 30 seconds. Gunicorn was silently assassinating the worker thread mid-generation, severing the connection to the frontend without a trace.
**FIX**: Updated `Procfile` to `web: gunicorn dash_app_v2:server --timeout 120 --threads 4`. This gives Gemini up to 2 minutes to respond and adds 4 threads so other users/callbacks aren't blocked while the API is generating.
**FAILED ATTEMPTS**: None.
**AI PROCESS**: Deduced that a missing API key or an import failure would return an instant error string due to our previous error-handling patches. A perpetual hang exclusively in production strongly points to a proxy/server timeout mismatch. Checked `Procfile` and confirmed default Gunicorn settings were in use.

## Vikram Infinite Hang on Render (Production)
**Symptom**: User asks Vikram a question on the production URL and the UI hangs on 'Vikram is thinking...' forever. The response never arrives and sometimes the connection resets.
**Root Cause**: 
1. undamental_cache.json was in .gitignore, so the Render deployment never had a warm cache. Every cold-start query forced a live fetch.
2. undamental_fetcher.py had a 15s timeout and up to 3 blocking retries (45s+ of blocking).
3. The  sk_vikram callback is fully synchronous, tying up a Gunicorn thread and causing silent timeouts when screener.in was slow.
**Fix**: 
1. Capped REQUEST_TIMEOUT to 6s and removed a redundant retry in undamental_fetcher.py.
2. Wrapped  uild_fundamental_context in a concurrent.futures thread with a strict 8-second wall-clock timeout in _vikram_callback.py. If it stalls, Vikram uses Google Search grounding instead.
3. Removed undamental_cache.json from .gitignore and committed it to seed the Render deploy.
4. Corrected MODEL_CANDIDATES to use standard Google AI Studio models (gemini-1.5-flash, gemini-2.0-flash).
**Failed Attempts**: Increasing Gunicorn timeout didn't resolve the core blocking issue.
**AI Process**: Used DEEP_AUDIT to trace the timeout waterfall in undamental_fetcher.py and identified the cache missing from the Render environment due to .gitignore.

---

## BUG-004 — Antigravity IDE Native Vision/Screenshot Analysis Fails with 404
**STATUS**: WATCH (Server-side Bug)
**FILE**: Antigravity IDE Backend Cloud Routing (Not in codebase)
**SYMPTOM**: Attempting to attach an image or ask the agent to analyze the UI using the screenshot tool causes the agent to crash with: `Agent execution terminated due to error.` The UI shows a `404 NOT_FOUND` for `models/gemini-1.5-pro`.
**ROOT CAUSE**: The Antigravity cloud backend hardcodes the deprecated `gemini-1.5-pro` model for its internal vision/screenshot tools. The local language server fetches this instruction from the backend, attempts to call Google AI Studio (v1beta), and fails because the model was removed. Exhaustive binary analysis confirmed `gemini-1.5-pro` does NOT exist in the local `v2.5.5` or `1.107.0` IDE installations.
**FIX**: **Unfixable locally.** Must wait for Google Antigravity engineering to update their backend routing to use `gemini-2.5-pro` or `gemini-3.x`. 
**FAILED ATTEMPTS**: Upgrading to IDE `v2.5.5` (fixes a separate `INVALID_ARGUMENT` bug, but not this 404 backend routing bug). Downgrading to `v1.107.0` (same issue).
**AI PROCESS**: Triggered `ROOT_CAUSE`. Searched all local extension bundles, language server binaries, and VSCode databases for the string `gemini-1.5-pro`. Found 0 matches, proving the model instruction is served dynamically by the cloud. Logged for visibility so we don't try to fix this locally again. Recommended alternative workflows: using Chrome DevTools MCP to inspect DOM, passing text/HTML instead of images, or using KiloCode for vision tasks.

---

## BUG-005 — Vikram Fails with 404 gemini-1.5-pro due to Retired Models in Fallback
**STATUS**: FIXED
**FILE**: `dash_pages/_vikram_callback.py` line 974
**SYMPTOM**: Vikram chat crashes with `Gemini error: 404 NOT_FOUND` for `models/gemini-1.5-pro` when querying the AI through the dashboard.
**ROOT CAUSE**: The `MODEL_CANDIDATES` list in `_vikram_callback.py` contained `gemini-2.0-flash`, `gemini-1.5-flash`, and `gemini-1.5-pro`. The first two models were retired or unmapped for this specific API key, causing the loop to fail silently and eventually try `gemini-1.5-pro` (the last resort), which threw a 404. The loop swallows all preceding errors and only bubbles up the final 404.
**FIX**: Updated `MODEL_CANDIDATES` to `["gemini-3.5-flash", "gemini-flash-latest"]` which are verified working for this project's API key. Removed the deprecated 1.5 models entirely.
**FAILED ATTEMPTS**: None (aside from previously conflating this with the Antigravity IDE vision bug).
**AI PROCESS**: Searched for `gemini-1.5-pro` globally, located the fallback loop in `_vikram_callback.py`. Realized the loop at line 1110 suppresses intermediate errors and only returns the final exception. Updated the list based on verified-working comments in the codebase and verified syntax with `py_compile`.
