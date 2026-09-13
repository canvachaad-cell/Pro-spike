# Claude — Cold Re-Audit Prompt: Antigravity groupby Optimization

**Role:** You are a senior performance-engineering auditor specializing in Python/pandas data pipelines. You re-audit a change another AI agent ("Antigravity") made to a production stock-scanner pipeline, independently verifying every claim rather than trusting any prior audit (including a prior one by a different model, whose findings are listed only as claims to re-check).

**Output format:** Severity-ranked findings only — P0 (breaking/incorrect results), P1 (serious risk), P2 (minor), P3 (note). Each finding: severity, `file:line`, one-line description, concrete fix. Then a final verdict table on each original claim: VERIFIED / REFUTED / PARTIALLY VERIFIED, with your own measured evidence. No praise, no padding.

---

## 1. Context

**Repo:** Plotly Dash trading dashboard + nightly pandas pipeline (Windows, Python 3.12 venv).
**The change under audit:** commit `7e84b47b` ("Auto-update: 05-09-2026 15:49:16.39"), which claims to fix a severe pipeline bottleneck.

**HARD CONSTRAINT:** `dashboard_full.py`, `lollipop_dashboard_full.py`, `run.bat` are LIVE production Streamlit — READ-ONLY, do not audit or modify them. Do not run any script that writes to `data/` (the pipeline scripts mutate production CSVs); benchmark on copies in a temp directory.

## 2. The Claims Under Audit (from Antigravity)

1. The old code "forced Python to linearly scan 2.2 million rows to find matching symbols, exactly 5,659 times" — "over 12.4 billion string comparisons... every single day".
2. The cure: replaced the per-symbol boolean-mask scan with a pandas C-level `groupby("SYMBOL")` partition, iterated once.
3. Result: "What used to bleed 40 minutes of your time every evening is now executed flawlessly in less than 3 seconds."
4. Implied: results are identical; data for Sep 4 was "clean, processed, and successfully written".

## 3. Where the Change Lives (verify with `git show 7e84b47b`)

- `calculate_real_progressives.py` (~line 187): `symbols = df_all["SYMBOL"].unique()` + `df_all[df_all["SYMBOL"] == symbol]` in a loop → `grouped_symbols = df_all.groupby("SYMBOL")` + `for symbol, df_stock in grouped_symbols:` with per-group `.sort_values("DATE")`.
- `auto_update_smart.py` (~line 575): the identical pattern change.
- Same commit also contains: `auto_update_smart.py` lines 4–5 — the UTF-8 stdout wrapper (`sys.stdout = io.TextIOWrapper(...)`) COMMENTED OUT. Flagged by the prior audit as an unrelated, smuggled change with UnicodeEncodeError risk on cp1252 consoles when the script prints ✅/⚠️/₹. Re-assess that risk yourself: check what the script prints, how it's launched (`auto_update_daily.bat` / scheduled task), and what console codepage applies.
- `dash_pages/_vikram_callback.py` in the same commit is an unrelated model-list reorder — out of scope.

## 4. Re-Audit Protocol (do these yourself, don't trust prior numbers)

### ① Correctness equivalence
- Read both loops in full (`calculate_real_progressives.py` ~150–254, `auto_update_smart.py` ~540–660). Beyond the grouping swap, check: NaN-symbol handling (`unique()` vs groupby's default NaN-drop), per-group `sort_values("DATE")` semantics, use of `latest_date` inside groups, and any variable that referenced the old `symbols` list after the change.
- Verify output row-ordering: groupby yields alphabetical symbol order; the old loop used insertion order. Trace whether any downstream consumer (`df_final` → CSVs → dashboard readers in `dash_pages/`, `build_historical_features.py`, `evaluate_institutional_edge.py`) depends on row order.
- Check `len(grouped_symbols)` usage in progress prints — correct? (`len()` on a GroupBy gives n_groups.)

### ② Performance — benchmark independently
- Build a scale-matched synthetic corpus (2.2M rows, 5,659 symbols, shuffled, DATE + numeric payload) in a temp dir. Time: (a) old mask-scan pattern over a 200-symbol sample, extrapolated; (b) new groupby pattern over ALL groups, including the per-group sort. Report both.
- Prior audit measured ~174 min (extrapolated old) → 12.2 s (new) on this machine — 855x. If your numbers differ materially, say so and explain (corpus shape, dtype, cache state).
- Judge the "40 min → <3 s" claim against your measurements: plausible corpus? does "<3 s" hold once per-group sorts are included?

### ③ Data integrity of the Sep-4 outputs (read-only checks)
- `git show 7e84b47b --stat` — the commit rewrote `data/combined_dashboard_live.csv` and `data/dashboard_cloud.csv` (~11.2k lines each), plus watchlists/ledgers. Spot-check: row counts, no all-NaN columns, SYMBOL/DATE/CLOSE sane, and `data/active_signals_ranked.csv` latest-date filtering still consistent with what `dash_pages/dashboard.py:load_latest_signals()` expects.

### ④ Pipeline safety
- Reassess the stdout-wrapper comment-out (`auto_update_smart.py:4-5`). Determine the actual failure mode: does any print in the file contain non-ASCII? What happens under `cmd /c` with cp1252? Is there a log redirect that changes stdout encoding? P-level it.

## 5. Deliverables

1. Claim-by-claim verdict table (4 claims above) with your evidence.
2. Any NEW findings the prior audits missed (especially correctness edge cases in the group bodies — e.g., `latest_date` computed before/after grouping, empty-group handling, duplicate symbol+date rows).
3. A minimal, concrete remediation list (diff-style), including whether to revert the stdout wrapper.
4. Explicit statement of anything you could NOT verify and why.

## 6. Out of Scope
- Streamlit production files, the nightly scheduler config, ML retraining, the Vikram AI panel, any redesign work. Audit and rank only.
