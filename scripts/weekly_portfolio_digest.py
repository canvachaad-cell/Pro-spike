"""
scripts/weekly_portfolio_digest.py — Weekly Portfolio Health & Edge Digest for Pro-Spike.

Generates an executive weekend briefing covering:
  1. Realized 7-Day Performance across all 4 strategy ledgers (Win Rate, PnL %, R-Multiple).
  2. Active Portfolio Health (Open positions, Unrealized PnL, Distance to SL/TP, Near-Exit warnings).
  3. High-Conviction Setups Watchlist for the upcoming week from Winner Archetypes.

Dispatches via:
  - Rich HTML Email via Gmail SMTP (forexamplekerala@gmail.com)
  - Mobile Push notification via ntfy.sh (prospike-fawaz-alerts-924)

SAFETY INVARIANT:
  Strictly READ-ONLY on all data files and strategy ledgers. Never calls .to_csv().

CLI:
  python scripts/weekly_portfolio_digest.py --dry-run
  python scripts/weekly_portfolio_digest.py --send
  python scripts/weekly_portfolio_digest.py --days 7 --send
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

# Guard stdout for non-UTF8 Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from notify_channels import _read_env_key, send_email, send_ntfy

DATA_DIR = os.path.join(ROOT_DIR, "data")

LEDGERS = {
    "ALPHA_MARKUPS": ("SBIA Alpha", os.path.join(DATA_DIR, "sbia_ledger.csv")),
    "FLEXGATE": ("FlexGate", os.path.join(DATA_DIR, "flexgate_ledger.csv")),
    "FLEXGATE2": ("FlexGate 2.0", os.path.join(DATA_DIR, "flexgate2_ledger.csv")),
    "CORNER": ("Corner Spike", os.path.join(DATA_DIR, "corner_engine_ledger.csv")),
}

ARCHETYPES_FILE = os.path.join(DATA_DIR, "winner_archetypes_ranked.csv")
LIVE_FILE = os.path.join(DATA_DIR, "dashboard_cloud.csv")
LIVE_FALLBACK = os.path.join(DATA_DIR, "combined_dashboard_live.csv")


def _to_float(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def load_live_price_map() -> dict[str, float]:
    """Build a mapping from SYMBOL -> latest CLOSE price."""
    prices: dict[str, float] = {}
    for p in (LIVE_FILE, LIVE_FALLBACK):
        if not os.path.exists(p):
            continue
        try:
            df = pd.read_csv(p)
            if "SYMBOL" in df.columns and "CLOSE" in df.columns:
                for _, r in df.iterrows():
                    sym = str(r["SYMBOL"]).strip().upper()
                    c = _to_float(r["CLOSE"])
                    if sym and c is not None and sym not in prices:
                        prices[sym] = c
        except Exception:
            continue
    return prices


def collect_digest_data(days: int = 7) -> dict:
    cutoff_dt = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
    live_prices = load_live_price_map()

    recent_exits = []
    active_positions = []

    for engine_key, (engine_label, path) in LEDGERS.items():
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue

        if df.empty or "STATUS" not in df.columns or "SYMBOL" not in df.columns:
            continue

        # 1. Recent Exits
        exited = df[df["STATUS"] != "ACTIVE"].copy()
        if "EXIT_DATE" in exited.columns and not exited.empty:
            exited["EXIT_DATE_DT"] = pd.to_datetime(exited["EXIT_DATE"], errors="coerce")
            in_window = exited[exited["EXIT_DATE_DT"] >= cutoff_dt]

            for _, row in in_window.iterrows():
                sym = str(row["SYMBOL"]).strip().upper()
                entry_p = _to_float(row.get("ENTRY_PRICE"))
                exit_p = _to_float(row.get("EXIT_PRICE"))
                sl_p = _to_float(row.get("STOP_LOSS"))
                status = str(row.get("STATUS", "EXIT"))
                exit_date = str(row.get("EXIT_DATE", ""))[:10]

                pnl_pct = None
                r_mult = None
                if entry_p and exit_p and entry_p > 0:
                    pnl_pct = ((exit_p - entry_p) / entry_p) * 100.0
                    if sl_p and sl_p < entry_p and (entry_p - sl_p) > 0:
                        r_mult = (exit_p - entry_p) / (entry_p - sl_p)

                # Classify exit mechanism accurately
                if status == "SUSPENDED" or (pnl_pct == 0.0 and entry_p == exit_p):
                    status_display = "SUSPENDED"
                elif status == "HIT_TP" or (status in ("HIT_SL", "CHANDELIER_EXIT") and pnl_pct and pnl_pct > 0):
                    status_display = "CHANDELIER_PROFIT" if status in ("HIT_SL", "CHANDELIER_EXIT") else "HIT_TP"
                elif status == "MOMENTUM_LOST" and pnl_pct and pnl_pct > 0:
                    status_display = "MOMENTUM_HARVEST"
                elif status == "MOMENTUM_LOST" and pnl_pct and pnl_pct <= 0:
                    status_display = "MOMENTUM_DECAY"
                else:
                    status_display = status

                recent_exits.append({
                    "engine": engine_label,
                    "symbol": sym,
                    "entry_price": entry_p,
                    "exit_price": exit_p,
                    "exit_date": exit_date,
                    "status": status,
                    "status_display": status_display,
                    "pnl_pct": pnl_pct,
                    "r_mult": r_mult,
                })

        # 2. Active Positions
        active = df[df["STATUS"] == "ACTIVE"].copy()
        for _, row in active.iterrows():
            sym = str(row["SYMBOL"]).strip().upper()
            entry_p = _to_float(row.get("ENTRY_PRICE"))
            sl_p = _to_float(row.get("STOP_LOSS"))
            tp_p = _to_float(row.get("TAKE_PROFIT"))
            entry_date = str(row.get("ENTRY_DATE", ""))[:10]
            current_p = live_prices.get(sym, entry_p)

            unrealized_pnl = None
            dist_sl_pct = None
            dist_tp_pct = None
            urgency = "HEALTHY"

            if entry_p and current_p and entry_p > 0:
                unrealized_pnl = ((current_p - entry_p) / entry_p) * 100.0

            if current_p and sl_p and current_p > 0:
                dist_sl_pct = ((current_p - sl_p) / current_p) * 100.0
                if 0.0 <= dist_sl_pct <= 3.0:
                    urgency = "NEAR_SL"
                elif dist_sl_pct < 0.0:
                    urgency = "BELOW_SL"

            if current_p and tp_p and current_p > 0:
                dist_tp_pct = ((tp_p - current_p) / current_p) * 100.0
                if 0.0 <= dist_tp_pct <= 3.0:
                    urgency = "NEAR_TP" if urgency == "HEALTHY" else urgency

            active_positions.append({
                "engine": engine_label,
                "symbol": sym,
                "entry_date": entry_date,
                "entry_price": entry_p,
                "current_price": current_p,
                "stop_loss": sl_p,
                "take_profit": tp_p,
                "unrealized_pnl": unrealized_pnl,
                "dist_sl_pct": dist_sl_pct,
                "dist_tp_pct": dist_tp_pct,
                "urgency": urgency,
            })

    # 3. Top Candidate Archetypes (Restricted to True Institutional Quality Cohort)
    top_candidates = []
    if os.path.exists(ARCHETYPES_FILE):
        try:
            adf = pd.read_csv(ARCHETYPES_FILE)
            if not adf.empty:
                # Use pre-sorted institutional hierarchy: QUALITY_80 -> A-GRADE -> RULE3_SCORE
                if "QUALITY_80" in adf.columns and "DELIV_GRADE" in adf.columns:
                    q_adf = adf[(adf["QUALITY_80"] == True) & (adf["DELIV_GRADE"].isin(["A-GRADE", "B-GRADE"]))]
                    ranked = q_adf.head(5) if len(q_adf) >= 5 else adf.head(5)
                else:
                    ranked = adf.head(5)

                for _, r in ranked.iterrows():
                    arch = str(r.get("ARCHETYPE", "BREAKOUT")).replace("_", " ").title()
                    cl = _to_float(r.get("CLOSE"))
                    sl = _to_float(r.get("STOP_LOSS"))
                    tp = _to_float(r.get("TAKE_PROFIT"))
                    playbook = "2R Fixed TP (~9 days)" if "Runner" in arch else "Trailing Momentum (~12–18 days)"
                    top_candidates.append({
                        "symbol": str(r.get("SYMBOL", "")).strip().upper(),
                        "archetype": arch,
                        "close": cl,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "ai_prob": _to_float(r.get("AI_WIN_PROBABILITY")),
                        "score": _to_float(r.get("RULE3_SCORE")),
                        "deliv_per": _to_float(r.get("DELIV_PER")),
                        "grade": str(r.get("DELIV_GRADE", "A-GRADE")),
                        "playbook": playbook,
                    })
        except Exception:
            pass

    # Aggregations for Exits: Segregate active market trades from corporate suspensions
    active_trades = [e for e in recent_exits if e["status_display"] != "SUSPENDED"]
    suspended_trades = [e for e in recent_exits if e["status_display"] == "SUSPENDED"]

    # Any trade with positive return (whether TP, trailing Chandelier, or Momentum Harvest) is a WIN
    wins = [e for e in active_trades if e["pnl_pct"] is not None and e["pnl_pct"] > 0]
    losses = [e for e in active_trades if e["pnl_pct"] is not None and e["pnl_pct"] < 0]
    scratches = [e for e in active_trades if e["pnl_pct"] is not None and e["pnl_pct"] == 0]

    total_closed = len(active_trades)
    win_rate = (len(wins) / total_closed * 100.0) if total_closed > 0 else 0.0
    net_pnl_sum = sum(e["pnl_pct"] for e in active_trades if e["pnl_pct"] is not None)
    avg_pnl = (net_pnl_sum / total_closed) if total_closed > 0 else 0.0
    total_r = sum(e["r_mult"] for e in active_trades if e["r_mult"] is not None)

    # Sub-breakdown of wins
    tp_wins = [e for e in wins if e["status_display"] in ("HIT_TP", "CHANDELIER_PROFIT")]
    momentum_wins = [e for e in wins if e["status_display"] == "MOMENTUM_HARVEST"]

    near_sl_count = sum(1 for p in active_positions if p["urgency"] in ("NEAR_SL", "BELOW_SL"))
    near_tp_count = sum(1 for p in active_positions if p["urgency"] == "NEAR_TP")

    return {
        "days": days,
        "cutoff_str": cutoff_str,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_exits": len(recent_exits),
        "total_closed": total_closed,
        "suspended_count": len(suspended_trades),
        "win_count": len(wins),
        "loss_count": len(losses),
        "scratch_count": len(scratches),
        "tp_win_count": len(tp_wins),
        "momentum_win_count": len(momentum_wins),
        "win_rate": win_rate,
        "net_pnl_sum": net_pnl_sum,
        "avg_pnl": avg_pnl,
        "total_r": total_r,
        "recent_exits": recent_exits,
        "total_active": len(active_positions),
        "near_sl_count": near_sl_count,
        "near_tp_count": near_tp_count,
        "active_positions": active_positions,
        "top_candidates": top_candidates,
    }


def format_plain_text(data: dict) -> str:
    lines = [
        "=" * 70,
        f"PRO-SPIKE WEEKLY PORTFOLIO HEALTH & EDGE DIGEST",
        f"Generated: {data['generated_at']} (Past {data['days']} Days, since {data['cutoff_str']})",
        "=" * 70,
        "",
        "--- [1] 7-DAY REALIZED PERFORMANCE ---",
        f"Closed Trades: {data['total_closed']} | Wins: {data['win_count']} (TP/Chandelier: {data['tp_win_count']}, Momentum Harvest: {data['momentum_win_count']}) | Losses: {data['loss_count']}",
        f"Win Rate:      {data['win_rate']:.1f}% ({data['suspended_count']} corporate suspensions excluded from denominator)",
        f"Net PnL Sum:   {data['net_pnl_sum']:+.2f}% (Avg: {data['avg_pnl']:+.2f}% / trade)",
        f"Net R-Book:    {data['total_r']:+.2f}R",
        "",
    ]

    if data["recent_exits"]:
        lines.append(f"{'ENGINE':<14} {'SYMBOL':<12} {'ENTRY':<10} {'EXIT':<10} {'PnL %':<10} {'R-MULT':<8} {'EXIT REASON'}")
        lines.append("-" * 80)
        for e in data["recent_exits"]:
            pnl_s = f"{e['pnl_pct']:+.2f}%" if e['pnl_pct'] is not None else "N/A"
            r_s = f"{e['r_mult']:+.2f}R" if e['r_mult'] is not None else "N/A"
            en_s = f"₹{e['entry_price']:.2f}" if e['entry_price'] else "N/A"
            ex_s = f"₹{e['exit_price']:.2f}" if e['exit_price'] else "N/A"
            lines.append(f"{e['engine']:<14} {e['symbol']:<12} {en_s:<10} {ex_s:<10} {pnl_s:<10} {r_s:<8} {e['status_display']}")
    else:
        lines.append("No position exits recorded in the past 7 days.")

    lines.extend([
        "",
        "--- [2] ACTIVE PORTFOLIO EXPOSURE ---",
        f"Total Active Positions: {data['total_active']}",
        f"Proximity Warnings:     {data['near_sl_count']} Near/Below SL | {data['near_tp_count']} Near Target Profit",
        "",
    ])

    if data["active_positions"]:
        lines.append(f"{'ENGINE':<14} {'SYMBOL':<12} {'ENTRY':<10} {'CURRENT':<10} {'UNREAL PnL':<12} {'SL DIST':<10} {'URGENCY'}")
        lines.append("-" * 80)
        for a in data["active_positions"]:
            en_s = f"₹{a['entry_price']:.2f}" if a['entry_price'] else "N/A"
            cur_s = f"₹{a['current_price']:.2f}" if a['current_price'] else "N/A"
            upnl_s = f"{a['unrealized_pnl']:+.2f}%" if a['unrealized_pnl'] is not None else "N/A"
            dist_s = f"{a['dist_sl_pct']:.1f}%" if a['dist_sl_pct'] is not None else "N/A"
            lines.append(f"{a['engine']:<14} {a['symbol']:<12} {en_s:<10} {cur_s:<10} {upnl_s:<12} {dist_s:<10} {a['urgency']}")

    lines.extend([
        "",
        "--- [3] WINNER ARCHETYPES HIGH-CONVICTION TRADE PLAYBOOK ---",
        "Rule 3 Institutional Cohort (A-Grade Accumulation 60–75% · Tier != Large · ATR >= 3.15%)",
        "",
    ])
    if data["top_candidates"]:
        lines.append(f"{'SYMBOL':<12} {'ARCHETYPE':<18} {'CLOSE':<10} {'SL':<10} {'TARGET':<10} {'DELIV %':<10} {'AI PROB':<10} {'PLAYBOOK'}")
        lines.append("-" * 95)
        for c in data["top_candidates"]:
            cl_s = f"₹{c['close']:.2f}" if c['close'] else "N/A"
            sl_s = f"₹{c['stop_loss']:.2f}" if c['stop_loss'] else "N/A"
            tp_s = f"₹{c['take_profit']:.2f}" if c['take_profit'] else "N/A"
            deliv_s = f"{c['deliv_per']:.1f}%" if c['deliv_per'] is not None else "N/A"
            ai_s = f"{c['ai_prob']:.1f}%" if c['ai_prob'] is not None else "N/A"
            lines.append(f"{c['symbol']:<12} {c['archetype']:<18} {cl_s:<10} {sl_s:<10} {tp_s:<10} {deliv_s:<10} {ai_s:<10} {c['playbook']}")

    lines.extend([
        "",
        "=" * 70,
        "Dashboard Live: https://pro-spike.onrender.com",
        "Notifications:  https://pro-spike.onrender.com/notifications",
        "=" * 70,
    ])
    return "\n".join(lines)


def format_html(data: dict) -> str:
    pnl_color = "#10b981" if data["net_pnl_sum"] >= 0 else "#ef4444"

    # Exits table rows
    exit_rows = ""
    if data["recent_exits"]:
        for e in data["recent_exits"]:
            pnl_val = e["pnl_pct"]
            pnl_str = f"{pnl_val:+.2f}%" if pnl_val is not None else "—"
            c = "#10b981" if (pnl_val or 0) > 0 else ("#94a3b8" if (pnl_val or 0) == 0 else "#ef4444")
            r_str = f"{e['r_mult']:+.2f}R" if e['r_mult'] is not None else "—"
            en_str = f"₹{e['entry_price']:.2f}" if e['entry_price'] else "—"
            ex_str = f"₹{e['exit_price']:.2f}" if e['exit_price'] else "—"

            disp = e["status_display"]
            if disp in ("HIT_TP", "CHANDELIER_PROFIT", "MOMENTUM_HARVEST"):
                badge_bg = "#064e3b"
                badge_fg = "#34d399"
            elif disp in ("HIT_SL", "MOMENTUM_DECAY"):
                badge_bg = "#450a0a"
                badge_fg = "#f87171"
            else:
                badge_bg = "#1e293b"
                badge_fg = "#94a3b8"

            exit_rows += f"""
            <tr style="border-bottom: 1px solid #1e293b;">
              <td style="padding: 10px 8px; color: #94a3b8; font-size: 13px;">{e['engine']}</td>
              <td style="padding: 10px 8px; font-weight: 700; color: #f8fafc; font-size: 14px;">{e['symbol']}</td>
              <td style="padding: 10px 8px; color: #cbd5e1; font-size: 13px;">{en_str}</td>
              <td style="padding: 10px 8px; color: #cbd5e1; font-size: 13px;">{ex_str}</td>
              <td style="padding: 10px 8px; font-weight: 700; color: {c}; font-size: 14px;">{pnl_str}</td>
              <td style="padding: 10px 8px; color: {c}; font-size: 13px;">{r_str}</td>
              <td style="padding: 10px 8px;"><span style="display: inline-block; padding: 2px 8px; border-radius: 9999px; background: {badge_bg}; color: {badge_fg}; font-size: 11px; font-weight: 600;">{disp}</span></td>
            </tr>"""
    else:
        exit_rows = """
        <tr><td colspan="7" style="padding: 16px; text-align: center; color: #94a3b8;">
            No position exits occurred during this lookback window.
        </td></tr>"""

    # Active positions rows
    active_rows = ""
    for a in data["active_positions"]:
        upnl = a["unrealized_pnl"]
        upnl_str = f"{upnl:+.2f}%" if upnl is not None else "—"
        c = "#10b981" if (upnl or 0) >= 0 else "#ef4444"
        cur_str = f"₹{a['current_price']:.2f}" if a['current_price'] else "—"
        sl_str = f"₹{a['stop_loss']:.2f}" if a['stop_loss'] else "—"
        dist_s = f"{a['dist_sl_pct']:.1f}%" if a['dist_sl_pct'] is not None else "—"

        badge_bg = "#1e293b"
        badge_fg = "#94a3b8"
        badge_text = "HEALTHY"

        if a["urgency"] in ("NEAR_SL", "BELOW_SL"):
            badge_bg = "#450a0a"
            badge_fg = "#f87171"
            badge_text = f"⚠️ Near SL ({dist_s})"
        elif a["urgency"] == "NEAR_TP":
            badge_bg = "#064e3b"
            badge_fg = "#34d399"
            badge_text = "🎯 Near TP"

        active_rows += f"""
        <tr style="border-bottom: 1px solid #1e293b;">
          <td style="padding: 8px; color: #94a3b8; font-size: 12px;">{a['engine']}</td>
          <td style="padding: 8px; font-weight: 700; color: #f8fafc; font-size: 13px;">{a['symbol']}</td>
          <td style="padding: 8px; color: #cbd5e1; font-size: 13px;">{cur_str}</td>
          <td style="padding: 8px; font-weight: 700; color: {c}; font-size: 13px;">{upnl_str}</td>
          <td style="padding: 8px; color: #94a3b8; font-size: 12px;">{sl_str}</td>
          <td style="padding: 8px;"><span style="display: inline-block; padding: 2px 8px; border-radius: 9999px; background: {badge_bg}; color: {badge_fg}; font-size: 11px; font-weight: 600;">{badge_text}</span></td>
        </tr>"""

    # Top candidates
    cand_rows = ""
    for c in data["top_candidates"]:
        cl_str = f"₹{c['close']:.2f}" if c['close'] else "—"
        sl_str = f"₹{c['stop_loss']:.2f}" if c['stop_loss'] else "—"
        tp_str = f"₹{c['take_profit']:.2f}" if c['take_profit'] else "—"
        deliv_str = f"{c['deliv_per']:.1f}%" if c['deliv_per'] is not None else "—"
        ai_str = f"{c['ai_prob']:.1f}%" if c['ai_prob'] is not None else "—"

        is_runner = "Runner" in c["archetype"]
        badge_bg = "rgba(90,240,179,0.15)" if is_runner else "rgba(174,198,255,0.15)"
        badge_fg = "#5af0b3" if is_runner else "#aec6ff"
        badge_icon = "🏃" if is_runner else "📈"

        cand_rows += f"""
        <tr style="border-bottom: 1px solid #1e293b;">
          <td style="padding: 10px 8px; font-weight: 700; color: #38bdf8; font-size: 14px;">{c['symbol']}</td>
          <td style="padding: 10px 8px;">
            <span style="display: inline-block; padding: 2px 8px; border-radius: 9999px; background: {badge_bg}; color: {badge_fg}; font-size: 11px; font-weight: 700;">
              {badge_icon} {c['archetype']}
            </span>
          </td>
          <td style="padding: 10px 8px; color: #f8fafc; font-size: 13px; font-weight: 600;">{cl_str}</td>
          <td style="padding: 10px 8px; color: #f87171; font-size: 12px; font-family: monospace;">{sl_str}</td>
          <td style="padding: 10px 8px; color: #34d399; font-size: 12px; font-family: monospace;">{tp_str}</td>
          <td style="padding: 10px 8px; color: #cbd5e1; font-size: 12px;">{deliv_str}</td>
          <td style="padding: 10px 8px; font-weight: 700; color: #a855f7; font-size: 13px;">{ai_str}</td>
          <td style="padding: 10px 8px; color: #94a3b8; font-size: 11px;">{c['playbook']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Pro-Spike Weekly Portfolio Digest</title>
</head>
<body style="margin: 0; padding: 24px; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <div style="max-width: 680px; margin: 0 auto; background: #0f172a; border-radius: 12px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
    
    <!-- Header -->
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 24px 28px; border-bottom: 1px solid #334155;">
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <span style="font-size: 20px; font-weight: 800; letter-spacing: -0.5px; color: #38bdf8;">PRO-SPIKE QUANT</span>
        <span style="font-size: 12px; color: #94a3b8; background: #1e293b; padding: 4px 10px; border-radius: 6px;">Weekend Executive Digest</span>
      </div>
      <p style="margin: 8px 0 0 0; font-size: 13px; color: #94a3b8;">
        Week ending {data['generated_at'][:10]} • Realized window: past {data['days']} days
      </p>
    </div>

    <!-- Stat Bar -->
    <div style="padding: 20px 28px; background: #131d33; border-bottom: 1px solid #1e293b; display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
      <div>
        <div style="font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 600;">7D Realized PnL</div>
        <div style="font-size: 20px; font-weight: 800; color: {pnl_color}; margin-top: 4px;">{data['net_pnl_sum']:+.2f}%</div>
      </div>
      <div>
        <div style="font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 600;">Win Rate</div>
        <div style="font-size: 20px; font-weight: 800; color: #f8fafc; margin-top: 4px;">{data['win_rate']:.1f}%</div>
        <div style="font-size: 11px; color: #64748b;">({data['win_count']} of {data['total_closed']} closed)</div>
      </div>
      <div>
        <div style="font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 600;">Net R-Booked</div>
        <div style="font-size: 20px; font-weight: 800; color: #38bdf8; margin-top: 4px;">{data['total_r']:+.2f}R</div>
      </div>
      <div>
        <div style="font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 600;">Active Trades</div>
        <div style="font-size: 20px; font-weight: 800; color: #f8fafc; margin-top: 4px;">{data['total_active']}</div>
      </div>
    </div>

    <!-- Section 1: Exits -->
    <div style="padding: 24px 28px;">
      <h3 style="margin: 0 0 12px 0; font-size: 15px; font-weight: 700; color: #f8fafc; text-transform: uppercase; letter-spacing: 0.5px;">
        1. Realized Exits ({data['total_closed']} Closed Trades + {data['suspended_count']} Suspended)
      </h3>
      <table style="width: 100%; border-collapse: collapse; text-align: left;">
        <thead>
          <tr style="border-bottom: 2px solid #334155; color: #64748b; font-size: 11px; text-transform: uppercase;">
            <th style="padding: 6px 8px;">Engine</th>
            <th style="padding: 6px 8px;">Symbol</th>
            <th style="padding: 6px 8px;">Entry</th>
            <th style="padding: 6px 8px;">Exit</th>
            <th style="padding: 6px 8px;">Net PnL</th>
            <th style="padding: 6px 8px;">R-Mult</th>
            <th style="padding: 6px 8px;">Exit Mechanism</th>
          </tr>
        </thead>
        <tbody>
          {exit_rows}
        </tbody>
      </table>
    </div>

    <!-- Section 2: Active Positions -->
    <div style="padding: 0 28px 24px 28px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <h3 style="margin: 0; font-size: 15px; font-weight: 700; color: #f8fafc; text-transform: uppercase; letter-spacing: 0.5px;">
          2. Active Portfolio Health ({data['total_active']} Positions)
        </h3>
        <span style="font-size: 12px; color: #f87171; font-weight: 600;">
          {f"⚠️ {data['near_sl_count']} Near SL" if data['near_sl_count'] > 0 else "🟢 All SL Safe"}
        </span>
      </div>
      <table style="width: 100%; border-collapse: collapse; text-align: left;">
        <thead>
          <tr style="border-bottom: 2px solid #334155; color: #64748b; font-size: 11px; text-transform: uppercase;">
            <th style="padding: 6px 8px;">Engine</th>
            <th style="padding: 6px 8px;">Symbol</th>
            <th style="padding: 6px 8px;">Current</th>
            <th style="padding: 6px 8px;">Unreal PnL</th>
            <th style="padding: 6px 8px;">Stop Loss</th>
            <th style="padding: 6px 8px;">Risk Zone</th>
          </tr>
        </thead>
        <tbody>
          {active_rows}
        </tbody>
      </table>
    </div>

    <!-- Section 3: Winner Archetypes High-Conviction Setups -->
    <div style="padding: 0 28px 24px 28px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <h3 style="margin: 0; font-size: 15px; font-weight: 700; color: #f8fafc; text-transform: uppercase; letter-spacing: 0.5px;">
          3. Winner Archetypes Trade Playbook (Forward Setups)
        </h3>
        <span style="font-size: 11px; color: #38bdf8; background: #0c4a6e; padding: 3px 8px; border-radius: 9999px; font-weight: 600;">
          Rule 3 Quality Cohort
        </span>
      </div>
      <table style="width: 100%; border-collapse: collapse; text-align: left;">
        <thead>
          <tr style="border-bottom: 2px solid #334155; color: #64748b; font-size: 11px; text-transform: uppercase;">
            <th style="padding: 6px 8px;">Symbol</th>
            <th style="padding: 6px 8px;">Archetype</th>
            <th style="padding: 6px 8px;">Close</th>
            <th style="padding: 6px 8px;">Stop Loss</th>
            <th style="padding: 6px 8px;">Target</th>
            <th style="padding: 6px 8px;">Delivery</th>
            <th style="padding: 6px 8px;">AI Prob</th>
            <th style="padding: 6px 8px;">Playbook Horizon</th>
          </tr>
        </thead>
        <tbody>
          {cand_rows}
        </tbody>
      </table>
    </div>

    <!-- Footer -->
    <div style="background: #111827; padding: 20px 28px; border-top: 1px solid #1e293b; text-align: center;">
      <a href="https://pro-spike.onrender.com" style="display: inline-block; background: #0284c7; color: #ffffff; text-decoration: none; padding: 8px 18px; border-radius: 6px; font-size: 13px; font-weight: 600; margin: 0 6px;">Open Pro-Spike Web App</a>
      <a href="https://pro-spike.onrender.com/notifications" style="display: inline-block; background: #1e293b; color: #94a3b8; text-decoration: none; padding: 8px 18px; border-radius: 6px; font-size: 13px; font-weight: 600; margin: 0 6px; border: 1px solid #334155;">View Notifications</a>
      <p style="margin: 12px 0 0 0; font-size: 11px; color: #64748b;">
        Pro-Spike Trading Engine • Automated Weekend Portfolio Audit
      </p>
    </div>

  </div>
</body>
</html>"""


def dispatch_digest(days: int = 7, send: bool = False):
    data = collect_digest_data(days=days)
    plain_text = format_plain_text(data)

    if not send:
        print(plain_text)
        print("\n[DRY RUN] Digest computed successfully. To dispatch via email and phone push, rerun with --send.")
        return True

    # 1. Dispatch Email (HTML)
    subject = f"📊 Pro-Spike Weekly Portfolio Digest — {datetime.now().strftime('%b %d, %Y')}"
    html_body = format_html(data)
    ok_email, detail_email = send_email(subject=subject, body=html_body, html=True)
    print(f"Email Dispatch: {'✅ OK' if ok_email else '❌ FAILED'} ({detail_email})")

    # 2. Dispatch Mobile Push (ntfy)
    push_title = f"📊 Pro-Spike Weekly: {data['win_rate']:.0f}% Win Rate ({data['net_pnl_sum']:+.1f}% PnL)"
    push_msg = (
        f"Closed Trades: {data['total_closed']} ({data['win_count']} Wins: {data['tp_win_count']} TP + {data['momentum_win_count']} Momentum)\n"
        f"Net Return: {data['net_pnl_sum']:+.1f}% ({data['total_r']:+.1f}R)\n"
        f"Active Positions: {data['total_active']} open ({data['near_sl_count']} near SL, {data['near_tp_count']} near TP)\n"
    )
    if data["top_candidates"]:
        top = data["top_candidates"][0]
        push_msg += f"Top Setup: {top['symbol']} (AI: {top['ai_prob']:.0f}%, Score: {top['score']:.0f})"

    ok_ntfy, detail_ntfy = send_ntfy(
        title=push_title,
        text=push_msg,
        priority="default" if data["near_sl_count"] == 0 else "high",
        tags="bar_chart,briefcase",
    )
    print(f"Mobile Push Dispatch: {'✅ OK' if ok_ntfy else '❌ FAILED'} ({detail_ntfy})")

    return ok_email or ok_ntfy

    return ok_email or ok_ntfy


def main():
    parser = argparse.ArgumentParser(description="Pro-Spike Weekly Portfolio Health & Edge Digest")
    parser.add_argument("--days", type=int, default=7, help="Lookback window for exited trades (default: 7)")
    parser.add_argument("--send", action="store_true", help="Dispatch digest to Email and Phone Push")
    parser.add_argument("--dry-run", action="store_true", help="Print report to console without sending")
    args = parser.parse_args()

    dispatch_digest(days=args.days, send=args.send and not args.dry_run)


if __name__ == "__main__":
    main()
