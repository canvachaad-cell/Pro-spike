# Ledger Exit Alerts

## What it does
Detects STATUS transitions in the four engine ledgers and notifies you:
`HIT_TP` · `HIT_SL` · `MOMENTUM_LOST` · `SUSPENDED` · new `ACTIVE` entries.

Ledgers covered: `data/sbia_ledger.csv` (Alpha Markups), `data/flexgate_ledger.csv`,
`data/flexgate2_ledger.csv`, `data/corner_engine_ledger.csv`.

## Safety
`alert_engine.py` opens every ledger READ-ONLY and never writes to one.
Prove it:  `git --no-pager diff --stat data/*ledger*.csv`  → must be empty.

## Channels
| Channel | Provider | Cost |
|---|---|---|
| WhatsApp | CallMeBot | Free, personal use only |
| Phone push | ntfy.sh | Free, no account |
| Email | Gmail SMTP SSL | Free |

## WhatsApp activation (one time)
1. Add `+34 694 23 41 84` to your phone contacts.
2. Send this WhatsApp message to that contact:
   `I allow callmebot to send me messages`
3. The bot replies: `API Activated for your phone number. Your APIKEY is 123123`
4. Put that key in `.env` as `CALLMEBOT_APIKEY`.

Free tier is personal use only. If the key doesn't arrive within 2 minutes, retry after 24h.
Because of this, the engine sends ONE batched digest per run — never one message per stock.

## ntfy.sh
Install the ntfy app, subscribe to a long random topic, and put it in `.env` as
`NTFY_TOPIC`. Public topics are world-readable — the topic name is the password.

## Environment variables
    ALERTS_ENABLED=1
    WHATSAPP_PHONE=+919876543210
    CALLMEBOT_APIKEY=
    NTFY_TOPIC=
    ALERT_EMAIL_TO=
    ALERT_EMAIL_FROM=
    GMAIL_APP_PASSWORD=
    ALERT_APPROACH_PCT=1.5

## CLI
    python alert_engine.py --test-channel        # send one test to each channel
    python alert_engine.py --dry-run             # detect + print, send nothing
    python alert_engine.py --only ALPHA_MARKUPS  # Alpha Markups ledger only
    python alert_engine.py --no-send             # log events, skip messages
    python alert_engine.py --approaching         # same-day SL/TP proximity report

## Why some alerts arrive backdated
`ledger_manager.py` detects exits by REPLAYING a historical yfinance price path
(`ledger_manager.py:206`), then stamps `EXIT_DATE` with the date the level was crossed
(`:214`, `:222`). If the nightly pipeline misses days, an alert for an exit that happened
last week can be raised today. Every alert therefore carries `entry_date`, `exit_date`,
`detected_at` and `lag_days` so a stale alert is never mistaken for a live one.

Use `--approaching` for same-day actionable warnings: it compares the LATEST close from
`data/dashboard_cloud.csv` against each ACTIVE position's SL/TP.

## Website freshness caveat
The live Dash site is deployed on Render from GitHub. `data/alerts_log.csv` is committed,
so the `/notifications` page is only as fresh as the last `git push`. WhatsApp/ntfy alerts
are near-instant from the local nightly job.
