"""
alert_engine.py — Ledger exit alert detector for Pro-spike.

Reads the four engine ledgers READ-ONLY, detects STATUS transitions
(ACTIVE -> HIT_TP / HIT_SL / MOMENTUM_LOST / SUSPENDED) plus new ACTIVE entries,
de-duplicates against an append-only event log, and dispatches notifications.

SAFETY INVARIANT (must never be broken):
    This module opens every ledger with pd.read_csv() and NEVER calls .to_csv()
    on a ledger DataFrame. It only ever writes to:
        data/alerts_log.csv     (append-only event log)
        data/alerts_state.json  (fast-path last-known-status cache)

    Verified by:
        git --no-pager diff --stat data/*ledger*.csv    -> must be EMPTY

Invoked from auto_update_smart.py after all engines finish.
CLI:
    python alert_engine.py --dry-run
    python alert_engine.py --test-channel
    python alert_engine.py --only ALPHA_MARKUPS
    python alert_engine.py --no-send
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

import pandas as pd

from notify_channels import (
    _read_env_key,
    alerts_enabled,
    channel_status,
    send_email,
    send_ntfy,
    send_whatsapp,
)

# ---------------------------------------------------------------------------
# UTF-8 stdout guard — same shape as auto_update_smart.py:2-5 and
# corner_spike_scanner.py:56-58, so ₹ renders on Windows consoles.
# ---------------------------------------------------------------------------
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(ROOT_DIR, "logs"), exist_ok=True)

logger = logging.getLogger("alerts")   # reused from notify_channels if already configured
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _h = RotatingFileHandler(
        os.path.join(ROOT_DIR, "logs", "alerts.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    _h.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_h)

DATA_DIR = os.path.join(ROOT_DIR, "data")
ALERTS_LOG = os.path.join(DATA_DIR, "alerts_log.csv")
ALERTS_STATE = os.path.join(DATA_DIR, "alerts_state.json")
LIVE_FILE = os.path.join(DATA_DIR, "dashboard_cloud.csv")

# Engine -> ledger path.
# ALPHA_MARKUPS (data/sbia_ledger.csv) is Path A, the "Alpha Markups Engine
# (12-Condition + ML)" — see calculate_active_signals.py:248 and :378.
LEDGERS = {
    "ALPHA_MARKUPS": os.path.join(DATA_DIR, "sbia_ledger.csv"),
    "FLEXGATE": os.path.join(DATA_DIR, "flexgate_ledger.csv"),
    "FLEXGATE2": os.path.join(DATA_DIR, "flexgate2_ledger.csv"),
    "CORNER": os.path.join(DATA_DIR, "corner_engine_ledger.csv"),
}

ENGINE_LABELS = {
    "ALPHA_MARKUPS": "Alpha Markups",
    "FLEXGATE": "FlexGate",
    "FLEXGATE2": "FlexGate 2.0",
    "CORNER": "Corner Spike",
}

# STATUS enum is IMMUTABLE (.agents/rules/SKILL-trading.md:26). READ-ONLY.
STATUS_ACTIVE = "ACTIVE"
EXIT_TYPES = {
    "HIT_TP": ("EXIT_TP", "high"),
    "HIT_SL": ("EXIT_SL", "high"),
    "MOMENTUM_LOST": ("EXIT_MOMENTUM", "default"),
    "SUSPENDED": ("EXIT_SUSPENDED", "low"),
}

LOG_COLUMNS = [
    "event_key", "event_type", "engine", "symbol", "entry_date", "entry_price",
    "exit_date", "exit_price", "stop_loss", "take_profit", "pnl_pct",
    "detected_at", "lag_days", "priority",
    "notified_whatsapp", "notified_ntfy", "notified_email",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _to_date_str(v) -> str:
    ts = pd.to_datetime(v, errors="coerce")
    return "" if pd.isna(ts) else ts.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Read-only ledger loading
# ---------------------------------------------------------------------------
def read_ledger(path: str):
    """READ-ONLY ledger load. Never mutates, never writes back."""
    if not os.path.exists(path):
        logger.warning("read_ledger: %s missing — skipping", path)
        return None
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
        logger.exception("read_ledger: failed to parse %s", path)
        return None
    if df.empty or "STATUS" not in df.columns or "SYMBOL" not in df.columns:
        logger.warning("read_ledger: %s unusable (empty or missing SYMBOL/STATUS)", path)
        return None
    return df


# ---------------------------------------------------------------------------
# State + append-only log
# ---------------------------------------------------------------------------
def load_state() -> dict:
    if not os.path.exists(ALERTS_STATE):
        return {}
    try:
        with open(ALERTS_STATE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("load_state: unreadable (%s) — rebuilding from alerts_log.csv", exc)
        return {}


def save_state(state: dict) -> None:
    try:
        with open(ALERTS_STATE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)
    except OSError:
        # Not fatal: the append-only log is the authoritative dedup source.
        logger.exception("save_state: write failed — dedup still safe via alerts_log.csv")


def load_log() -> pd.DataFrame:
    if not os.path.exists(ALERTS_LOG):
        return pd.DataFrame(columns=LOG_COLUMNS)
    try:
        df = pd.read_csv(ALERTS_LOG)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
        logger.exception("load_log: unreadable — treating as empty")
        return pd.DataFrame(columns=LOG_COLUMNS)
    for col in LOG_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df


def append_log(events: list) -> None:
    if not events:
        return
    new_df = pd.DataFrame(events)
    for col in LOG_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = ""
    new_df = new_df[LOG_COLUMNS]

    if os.path.exists(ALERTS_LOG):
        combined = pd.concat([load_log(), new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(ALERTS_LOG, index=False)
    logger.info("append_log: +%d events -> %s (total %d)",
                len(events), ALERTS_LOG, len(combined))


def is_first_run() -> bool:
    return not os.path.exists(ALERTS_STATE) and not os.path.exists(ALERTS_LOG)


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------
def _emit(events, existing_keys, *, event_key, event_type, engine, symbol, row,
          entry_date, exit_date, exit_price, detected_at, priority) -> None:
    """Build an event dict unless it already exists in the append-only log."""
    if event_key in existing_keys:
        return

    entry_price = _to_float(row.get("ENTRY_PRICE"))
    pnl_pct = ""
    if entry_price not in (None, 0) and exit_price is not None:
        pnl_pct = round((exit_price - entry_price) / entry_price * 100, 2)

    lag_days = ""
    if exit_date:
        try:
            lag_days = (datetime.strptime(detected_at[:10], "%Y-%m-%d")
                        - datetime.strptime(exit_date, "%Y-%m-%d")).days
        except ValueError:
            logger.warning("_emit: unparseable dates for %s (%s / %s)",
                           symbol, exit_date, detected_at)

    events.append({
        "event_key": event_key,
        "event_type": event_type,
        "engine": engine,
        "symbol": symbol,
        "entry_date": entry_date,
        "entry_price": entry_price if entry_price is not None else "",
        "exit_date": exit_date,
        "exit_price": exit_price if exit_price is not None else "",
        "stop_loss": _to_float(row.get("STOP_LOSS")) or "",
        "take_profit": _to_float(row.get("TAKE_PROFIT")) or "",
        "pnl_pct": pnl_pct,
        "detected_at": detected_at,
        "lag_days": lag_days,
        "priority": priority,
        "notified_whatsapp": "",
        "notified_ntfy": "",
        "notified_email": "",
    })
    existing_keys.add(event_key)


def scan_ledgers(only: str | None = None):
    """Compare each ledger row's current STATUS against the last status on record.

    Returns (events: list[dict], new_state: dict).
    """
    state = load_state()
    new_state = dict(state)
    existing_keys = set(load_log()["event_key"].astype(str))
    detected_at = _now_str()
    events: list = []

    targets = {only: LEDGERS[only]} if (only and only in LEDGERS) else LEDGERS

    for engine, path in targets.items():
        df = read_ledger(path)
        if df is None:
            continue

        for _, row in df.iterrows():
            symbol = str(row.get("SYMBOL", "")).strip()
            if not symbol:
                continue
            status = str(row.get("STATUS", "")).strip()
            if not status:
                continue
            entry_date = _to_date_str(row.get("ENTRY_DATE"))

            state_key = f"{engine}|{symbol}|{entry_date}"
            prev_status = state.get(state_key)

            if status == STATUS_ACTIVE:
                if prev_status != STATUS_ACTIVE:
                    _emit(
                        events, existing_keys,
                        event_key=f"{engine}|{symbol}|{entry_date}|{STATUS_ACTIVE}",
                        event_type="NEW_ENTRY" if prev_status is None else "REACTIVATED",
                        engine=engine, symbol=symbol, row=row, entry_date=entry_date,
                        exit_date="", exit_price=None,
                        detected_at=detected_at, priority="default",
                    )
            elif status in EXIT_TYPES:
                event_type, priority = EXIT_TYPES[status]
                _emit(
                    events, existing_keys,
                    event_key=f"{engine}|{symbol}|{entry_date}|{status}",
                    event_type=event_type,
                    engine=engine, symbol=symbol, row=row, entry_date=entry_date,
                    exit_date=_to_date_str(row.get("EXIT_DATE")),
                    exit_price=_to_float(row.get("EXIT_PRICE")),
                    detected_at=detected_at, priority=priority,
                )

            new_state[state_key] = status

    return events, new_state


# ---------------------------------------------------------------------------
# Phase 4 — SAME-DAY actionable band alerts (opt-in)
# ---------------------------------------------------------------------------
def compute_approach_alerts(pct: float = 1.5) -> list:
    """Flag ACTIVE positions whose LATEST close is within `pct`% of SL or TP.

    Why this exists: ledger exits are detected from a REPLAYED historical price
    path (ledger_manager.py:206), so EXIT_DATE can be BACKDATED. This function
    uses the latest close in data/dashboard_cloud.csv instead, giving a same-day
    heads-up. It is keyed per symbol per day, so it may legitimately re-fire on
    consecutive days and does NOT participate in the alerts_log.csv dedup.
    """
    if not os.path.exists(LIVE_FILE):
        logger.warning("compute_approach_alerts: %s missing", LIVE_FILE)
        return []

    try:
        live = pd.read_csv(LIVE_FILE, usecols=["SYMBOL", "CLOSE"])
    except (OSError, ValueError, pd.errors.ParserError):
        logger.exception("compute_approach_alerts: cannot read %s", LIVE_FILE)
        return []

    live = live.dropna(subset=["SYMBOL", "CLOSE"]).drop_duplicates("SYMBOL", keep="last")
    closes = dict(zip(live["SYMBOL"].astype(str), live["CLOSE"]))

    out = []
    for engine, path in LEDGERS.items():
        df = read_ledger(path)
        if df is None:
            continue
        active = df[df["STATUS"] == STATUS_ACTIVE]
        for _, row in active.iterrows():
            symbol = str(row.get("SYMBOL", "")).strip()
            close = _to_float(closes.get(symbol))
            sl = _to_float(row.get("STOP_LOSS"))
            tp = _to_float(row.get("TAKE_PROFIT"))
            if close is None:
                continue

            if sl not in (None, 0) and close > sl:
                if (close - sl) / close * 100 <= pct:
                    out.append({"engine": engine, "symbol": symbol,
                                "event_type": "APPROACHING_SL", "close": close,
                                "level": sl, "distance_pct": round((close - sl) / close * 100, 2)})
            if tp not in (None, 0) and close < tp:
                if (tp - close) / close * 100 <= pct:
                    out.append({"engine": engine, "symbol": symbol,
                                "event_type": "APPROACHING_TP", "close": close,
                                "level": tp, "distance_pct": round((tp - close) / close * 100, 2)})
    return out


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------
ICON_MAP = {"EXIT_TP": "🟢", "EXIT_SL": "🔴",
            "EXIT_MOMENTUM": "🟠", "EXIT_SUSPENDED": "⚪"}


def _format_event(e: dict) -> str:
    label = ENGINE_LABELS.get(e["engine"], e["engine"])
    symbol = e["symbol"]

    if e["event_type"] in ("NEW_ENTRY", "REACTIVATED"):
        head = "NEW ENTRY" if e["event_type"] == "NEW_ENTRY" else "RE-ENTRY"
        return (f"🆕 *{head}* — {symbol}\n"
                f"{label}\n"
                f"Entry ₹{e['entry_price']} | SL ₹{e['stop_loss']} | TP ₹{e['take_profit']}")

    icon = ICON_MAP.get(e["event_type"], "•")
    head = e["event_type"].replace("EXIT_", "EXIT — ")
    pnl = f"  ({e['pnl_pct']:+.2f}%)" if isinstance(e["pnl_pct"], (int, float)) else ""

    last = f"Detected {str(e['detected_at'])[:10]}"
    if isinstance(e["lag_days"], int) and e["lag_days"] > 0:
        last += f"  (lag {e['lag_days']}d ⚠️)"

    return (f"{icon} *{head}*\n"
            f"*{symbol}* · {label}\n"
            f"Entry ₹{e['entry_price']} → Exit ₹{e['exit_price']}{pnl}\n"
            f"Entry {e['entry_date']} | Exit {e['exit_date'] or '—'}\n"
            f"{last}")


def _top_priority(events: list) -> str:
    order = {"low": 0, "default": 1, "high": 2, "urgent": 3}
    return max((e.get("priority", "default") for e in events),
               key=lambda p: order.get(p, 1), default="default")


def build_digest(events: list):
    """One batched message. CallMeBot's free tier is personal-use only —
    never send one message per stock."""
    exits = [e for e in events if str(e["event_type"]).startswith("EXIT")]
    entries = [e for e in events if not str(e["event_type"]).startswith("EXIT")]
    tp = sum(1 for e in exits if e["event_type"] == "EXIT_TP")
    sl = sum(1 for e in exits if e["event_type"] == "EXIT_SL")
    mo = sum(1 for e in exits if e["event_type"] == "EXIT_MOMENTUM")

    title = f"Pro Spike — {len(events)} ledger alert(s)"
    lines = [
        f"*PRO SPIKE LEDGER ALERTS* — {len(events)} event(s)",
        f"Exits: {len(exits)} (TP {tp} / SL {sl} / Momentum {mo}) | New entries: {len(entries)}",
        "",
    ]
    for e in events[:10]:
        lines.append(_format_event(e))
        lines.append("")
    if len(events) > 10:
        lines.append(f"…and {len(events) - 10} more — see /notifications")
    return title, "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def dispatch_ledger_alerts(dry_run: bool = False, no_send: bool = False,
                           only: str | None = None, force: bool = False) -> int:
    """Detect, dedup, dispatch, log. Returns the number of NEW events."""
    if not alerts_enabled():
        print("Alerts: disabled (ALERTS_ENABLED=0).")
        return 0

    # First ever run: baseline the state silently so we never spam dozens of
    # historical NEW_ENTRY messages on install day.
    if is_first_run() and not force:
        _, new_state = scan_ledgers(only=only)
        save_state(new_state)
        print(f"Alerts: initialised. Baselined {len(new_state)} ledger row(s). "
              f"No notifications sent for pre-existing positions. "
              f"Future transitions will alert.")
        return 0

    events, new_state = scan_ledgers(only=only)

    if not events:
        print("Alerts: no new ledger events.")
        save_state(new_state)
        return 0

    title, body = build_digest(events)
    print(f"Alerts: {len(events)} new event(s)")
    print(body)

    if dry_run:
        print("[DRY RUN] Nothing sent, nothing logged.")
        return len(events)

    ok_wa = ok_ntfy = ok_mail = False
    detail_wa = detail_ntfy = detail_mail = "SKIPPED"

    if no_send:
        detail_wa = detail_ntfy = detail_mail = "SKIPPED(--no-send)"
    else:
        ok_wa, detail_wa = send_whatsapp(body)
        ok_ntfy, detail_ntfy = send_ntfy(title, body,
                                         priority=_top_priority(events),
                                         tags="chart_with_upwards_trend")
        ok_mail, detail_mail = send_email(title, body)
        print(f"  whatsapp: {ok_wa} ({detail_wa})")
        print(f"  ntfy    : {ok_ntfy} ({detail_ntfy})")
        print(f"  email   : {ok_mail} ({detail_mail})")
        if not any((ok_wa, ok_ntfy, ok_mail)):
            logger.error("dispatch: ALL channels failed or unconfigured — "
                         "events were logged but NOT delivered")

    for e in events:
        e["notified_whatsapp"] = ok_wa
        e["notified_ntfy"] = ok_ntfy
        e["notified_email"] = ok_mail

    append_log(events)
    save_state(new_state)
    return len(events)


def _test_channel():
    print("Configured channels:", channel_status())
    title = "Pro Spike — channel test"
    body = ("✅ Pro Spike alert channel test.\n"
            "If you can read this, ledger exit alerts will reach you.")
    ok, detail = send_whatsapp(body)
    print(f"whatsapp: {ok} ({detail})")
    ok, detail = send_ntfy(title, body, priority="default", tags="white_check_mark")
    print(f"ntfy    : {ok} ({detail})")
    ok, detail = send_email(title, body)
    print(f"email   : {ok} ({detail})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Pro-spike ledger exit alert engine")
    ap.add_argument("--dry-run", action="store_true",
                    help="Detect and print events; send and log nothing")
    ap.add_argument("--no-send", action="store_true",
                    help="Detect and log events; skip all outbound messages")
    ap.add_argument("--only", choices=sorted(LEDGERS.keys()),
                    help="Restrict to a single engine ledger")
    ap.add_argument("--force", action="store_true",
                    help="Skip the first-run silent baseline")
    ap.add_argument("--test-channel", action="store_true",
                    help="Send exactly one message to each configured channel")
    ap.add_argument("--approaching", action="store_true",
                    help="Phase 4: report ACTIVE positions near their SL/TP")
    ap.add_argument("--approach-pct", type=float,
                    default=float(_read_env_key("ALERT_APPROACH_PCT") or 1.5),
                    help="Band width for --approaching (default 1.5)")
    args = ap.parse_args()

    if args.test_channel:
        _test_channel()
        return 0

    if args.approaching:
        rows = compute_approach_alerts(args.approach_pct)
        if not rows:
            print(f"Approaching: no ACTIVE position within {args.approach_pct}% of SL/TP.")
            return 0
        for r in rows:
            print(f"{r['event_type']:<15} {r['symbol']:<14} {r['engine']:<14} "
                  f"close ₹{r['close']} vs level ₹{r['level']} ({r['distance_pct']}%)")
        return 0

    n = dispatch_ledger_alerts(dry_run=args.dry_run, no_send=args.no_send,
                               only=args.only, force=args.force)
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
