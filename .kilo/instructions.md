# Kilo Code Strict Rules

## 1. Grounding & No Fabrication
- Answer ONLY from files and context explicitly provided.
- Say "NOT IN CONTEXT" when information is missing. Never guess.
- Never invent APIs, function names, file paths, URLs, or config keys.

## 2. Plan First & Diff Requirement
- Always output a numbered plan and wait for approval before editing any file.
- Show a before/after diff for every code change.

## 3. Destructive Action Gate
- Shell commands, deletions, and external API calls require explicit confirmation.

## 4. Production Environment Quarantine
- The files `dashboard_full.py`, `lollipop_dashboard_full.py`, and `run.bat` are LIVE. READ ONLY. Never write to them.

## 5. Read the Context
- Before beginning work, ALWAYS read `.agents/rules/CONTEXT.md` to see the recently modified files and session constraints.

## 6. DEMONCORE Operating Modes

**DEMONCORE: PLAN_DEEP** — Before writing any code, produce a full dependency
map and blast-radius check (upstream callers, shared state, schema guard).
Hard stop until the user explicitly approves the plan. Mirror `.agents/agents/plan_deep.md`.

**DEMONCORE: ROOT_CAUSE** — Stop writing patches. Produce a verified-vs-assumed
audit table. One root cause, one minimal fix, one stated verification method.
If unresolved after 2 passes, escalate: output `/boost` with the audit table attached.
Mirror `.agents/agents/root_cause.md`.

**DEMONCORE: DEEP_AUDIT** — Deeply audit a specific part of the app for bugs, 
destructive/breaking risks, security gaps, and architectural debt. 
Mirror `.agents/agents/deep_audit.md`.

**FULL_TEST** — Run a complete end-to-end QA sweep of the app via browser automation.
Mirror `.agents/agents/full_test.md`.

**Kilo-specific enforcement:**
- All PLAN_DEEP outputs are saved as `.kilo/plans/<timestamp>-<slug>.md` so
  they appear in Kilo's plan history.
- ROOT_CAUSE audit tables are appended to the active plan document, not dropped
  as inline chat responses, so they persist across sessions.
- DEEP_AUDIT reports are saved as `.kilo/plans/<timestamp>-deep-audit-<scope>.md`
  to persist the findings.
- FULL_TEST QA reports are saved as `.kilo/plans/<timestamp>-full-test-report.md`.
  Auto-patches must not commit to main until the report is approved.
- No mode may open a new Kilo worktree until the user approves the plan.
