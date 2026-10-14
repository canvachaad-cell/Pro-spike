#!/usr/bin/env bash
# Pro-spike Git Pre-Push Hook
# Verifies that scratch/last_session.md has been updated before pushing.

# Auto-update commits from the daily pipeline are exempt
COMMIT_MSG=$(git log -1 --format="%s")
if [[ "$COMMIT_MSG" == Auto-update:* ]]; then
    echo "🤖 [Pro-spike Hook] Auto-update commit detected — session log check skipped."
    exit 0
fi

echo "🔍 [Pro-spike Hook] Checking session log freshness..."

SESSION_LOG="scratch/last_session.md"

if [ ! -f "$SESSION_LOG" ]; then
    echo "❌ [ERROR] $SESSION_LOG not found! Session log is missing."
    echo "👉 Please run the session_handoff skill before pushing."
    exit 1
fi

# Find the latest '## Session — YYYY-MM-DD' entry in last_session.md (supports both em-dash and hyphen)
LAST_LOG_DATE=$(grep -E '^## (Last )?Session [—-]' "$SESSION_LOG" | tail -n 1 | sed -E 's/.*([0-9]{4}-[0-9]{2}-[0-9]{2}).*/\1/')

if [ -z "$LAST_LOG_DATE" ]; then
    echo "❌ [ERROR] Could not parse any session date from $SESSION_LOG!"
    echo "👉 Please run the session_handoff skill to create a valid session entry."
    exit 1
fi

# Get the date of the latest commit being pushed or HEAD
LAST_COMMIT_DATE=$(git log -1 --format="%as")

echo "ℹ️  Last session log date: $LAST_LOG_DATE"
echo "ℹ️  Last commit date:      $LAST_COMMIT_DATE"

# Compare dates (lexicographical comparison works for YYYY-MM-DD)
if [[ "$LAST_LOG_DATE" < "$LAST_COMMIT_DATE" ]]; then
    echo "⚠️  [BLOCKED] SESSION LOG IS STALE!"
    echo "    Commit date ($LAST_COMMIT_DATE) is newer than session log date ($LAST_LOG_DATE)."
    echo "👉 Please invoke session_handoff to summarize your recent work before pushing."
    echo "    To bypass (emergency only): git push --no-verify"
    exit 1
fi

echo "✅ [Pro-spike Hook] Session log is up to date ($LAST_LOG_DATE >= $LAST_COMMIT_DATE). Proceeding with push."
exit 0
