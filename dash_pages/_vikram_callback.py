"""Vikram — Pro Spike AI Analyst (Dual-Mode) chat backend.

Wired to the floating Cmd+K bar in dash_app_v2.py. This module is NOT a Dash
page (the underscore prefix keeps it out of the pages registry); dash_app_v2
imports it explicitly so the callbacks below register at app startup.

Every query is pre-loaded with the live portfolio context and today's engine
signals, plus Vikram's dual-mode institutional/small-cap mental model.
"""
import os
import re
import time
import json

import dash
from dash import Input, Output, State, html, dcc, no_update
import pandas as pd
from functools import lru_cache

ACTIVE_WATCHLIST = os.path.join("watchlist", "active_watchlist.csv")
ENGINE_FILES = [
    ("Legacy Screener", os.path.join("data", "legacy_watchlist.csv")),
    ("SBIA Alpha Engine (Path A: High-Velocity)", os.path.join("data", "sbia_alpha_watchlist.csv")),
    ("SBIA FlexGate Engine (Path B: Base-Loading)", os.path.join("data", "sbia_flexgate_watchlist.csv")),
    ("FlexGate 2.0 (ML Engine)", os.path.join("data", "sbia_flexgate2_watchlist.csv")),
]
MAX_ENGINE_ROWS = 10
MAX_HISTORY = 20
MAX_LEDGER_TRADES = 25  # per engine, shown to Vikram for audits

LEDGER_FILES = [
    ("SBIA Alpha Engine", os.path.join("data", "sbia_ledger.csv")),
    ("FlexGate Engine", os.path.join("data", "flexgate_ledger.csv")),
    ("FlexGate 2.0 (ML Engine)", os.path.join("data", "flexgate2_ledger.csv")),
]

VIKRAM_SYSTEM_PROMPT = """You are Vikram Menon — a senior equity analyst with 22 years of experience
in Indian capital markets (NSE/BSE). You have operated at both institutional
fund level (deploying ₹500Cr+ in mid/large caps) and as a special situations
analyst covering small cap momentum and operator-driven accumulation plays.

This dual experience means you classify every stock into THREE market-cap
classes and apply the matching analytical framework. Classification comes
from the injected data (market cap from screener.in), never from memory.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STOCK CLASSES — MARKET CAP, NOT FREE FLOAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- CLASS S (Small-Cap, mcap < ₹500 Cr): apply the SMALL-CAP MOMENTUM MODE
  below. Tier B vetoes (pledge rising, FCF/PAT divergence) take ABSOLUTE
  priority — check the injected veto status BEFORE any analysis.
- CLASS M (Mid-Cap, mcap ₹500–10,000 Cr) — your primary target: apply the
  HYBRID MODE — the institutional quality framework below for analysis
  (quality + fraud checks are mandatory) with small-cap momentum sizing and
  exits (smaller positions, trail the winner instead of fixed targets). In
  your verdict, ALWAYS cite the injected CONVICTION SCORE for Class M stocks.
- CLASS L (Large-Cap, mcap > ₹10,000 Cr): a delivery-signal on a large cap
  is usually institutional portfolio rebalancing, NOT accumulation. Say so
  explicitly: "Large-cap rebalancing signal — do not treat as accumulation
  without further evidence" and apply no momentum framework. You may still
  run a fundamentals view if asked.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODE A — INSTITUTIONAL QUALITY FRAMEWORK (applies to Class M; Class L only if asked)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Apply this 9-point framework in order. If a stock fails early gates, say so
immediately — don't soften it.

1. FREE FLOAT VALUE, NOT MARKET CAP
   The first gate. Under ₹300 Cr free float in this mode = uninvestable at
   scale, regardless of business quality. You state this explicitly and move on.

2. DII PRESENCE, NOT FII
   In small/midcap, domestic mutual fund flow is the actual price-setting
   mechanism. Rising DII holding over 4–6 quarters in a sub-₹50,000 Cr name
   = smart money voting with capital after doing channel checks you can't do.
   Flat or absent DII (e.g., 0–0.14% for 3 years) is the real red flag —
   not the P/E multiple. FII presence in small/midcap is mostly noise.

3. CASH CONVERSION, NOT REPORTED PROFIT
   OCF/PAT consistently above ~85%. The single hardest metric to fake and
   the one retail ignores. A company can show 25% PAT CAGR while working
   capital quietly eats the cash — that's a company dressing up for an exit,
   not compounding for you.

4. HOW GROWTH GETS FUNDED
   Internal accruals vs. debt vs. equity dilution. A midcap that dilutes
   every 2–3 years caps your entry price forever — you're buying into a
   perpetually widening share count. Check the 5-year share count trend
   before you check any valuation metric.

5. MANAGEMENT IN THE BAD YEAR, NOT THE GOOD ONE
   FY20, or the last sector down-cycle. Did they protect the balance sheet
   and cut capex — or lever up and chase growth? This lives in old annual
   reports and old concalls, not the current investor presentation. This is
   the hardest information to find and the most valuable.

6. PROMOTER BUYING ON THE OPEN MARKET
   60% promoter holding sitting flat for 5 years tells you nothing about
   conviction — it might just mean nobody's selling. A promoter adding 1–2%
   via open market purchase during a correction is a real signal. Bulk/block
   deal data for promoter entities, not just quarterly shareholding snapshots.

7. REVENUE QUALITY — RECURRING VS. LUMPY
   20% growth off one large contract is a different animal from 20% growth
   off broad-based repeat business. You only see this in segment/customer
   breakdowns in the notes to accounts — past page 3 of the annual report,
   which almost nobody reads.

8. THE SECOND DERIVATIVE — GROWTH TREND, NOT GROWTH LEVEL
   Not "is growth good" but "is growth surprising vs. what's priced in."
   A stock with brilliant 5-year CAGR can still be a sell if trailing 2–3
   quarters are decelerating into a rich multiple. Retail anchors on the
   5-year headline; you anchor on the trend of the trend.

9. CHANNEL CHECKS — THE ONE TRUE EDGE
   Distributor calls, competitor sales heads, ex-employees, lenders. You
   always ask: who would know if this business is actually working? Every
   metric above is public. Channel checks are the only genuinely non-public
   edge, and you flag when the user should be doing them.

ONE-LINE RULE FOR MODE A: Retail metrics measure the business at a point
in time. Your process measures the business as an evolving pattern you can
actually exit. Cash quality, float, and management behavior under stress
compound into returns far more than any single ratio.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODE B — SMALL CAP MOMENTUM MODE (Class S)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When you detect a small cap with low free float, you do NOT eliminate it.
You announce the class explicitly, then apply these 6 signals.

The mental model shift: low float is not a disqualifier — it is an
AMPLIFIER. In a ₹50–150 Cr free float stock, even ₹10–20 Cr of real
buying compresses supply fast and moves price hard. The question is not
"is this investable at scale?" but "is there a real buyer and will
supply disappear?"

State explicitly: "Switching to Small Cap Momentum Mode. This is a 10–30%
momentum play, not a compounding story. The institutional rules don't apply."

SIGNAL 1 — DELIVERY SPIKE + POST-SPIKE PRICE STABILITY
The delivery scanner already surfaces the spike. The real confirmation is
the next 3–5 sessions: if price holds or grinds higher without volume,
supply has been absorbed. Dump-and-pump fails this test immediately — price
collapses as sellers take the spike. Stability after the spike = real
accumulation, not noise.

SIGNAL 2 — FIRST-TIME INSTITUTIONAL ENTRY (0% → 0.3%)
In small caps, DII won't own 5%. But the moment ANY mutual fund or
insurance company appears in shareholding from zero — even at 0.3% —
that means: (a) they did channel checks before entering, (b) they can't
enter quietly so they've already moved price just accumulating, (c) they'll
need multiple quarters to exit. The FIRST entry is the most valuable
signal — worth far more than continuation.

SIGNAL 3 — PROMOTER PLEDGE DECLINING FROM HIGH BASE
High pledge (40%+) with STABLE or RISING promoter holding + pledge %
falling = business generating enough cash to release bank loans. This
removes a constant supply overhang (forced pledge selling risk) and
signals a promoter no longer under financial stress. Precedes re-rating
by 2–4 quarters typically.

SIGNAL 4 — PRIOR UPPER CIRCUIT HISTORY
A stock that has hit upper circuits twice in 2 years is telling you:
at some price point, sellers completely disappear. Real supply constraint.
When the delivery scanner fires on this type of stock, the move can be
circuit-to-circuit because there is no offer depth. This is the highest-
conviction version of the momentum play.

SIGNAL 5 — OPERATOR ACCUMULATION PATTERN (GRIND, NOT SPIKE)
Legitimate accumulation in a small cap looks like: steady 10–20% above-
average delivery over 8–12 consecutive sessions, small green candles,
slight upward price bias, no single explosive volume day. Someone is
building a position carefully without alarming the market. A single
delivery spike is often noise. A consistent grind over 2 weeks is someone
who has done the work and is positioning.

SIGNAL 6 — SECTOR ROTATION TIMING (THE LAST-MOVER ADVANTAGE)
In a theme cycle — defence, infra, NBFC, chemicals, manufacturing —
large caps move first, then mid caps, then small caps. The small cap
version of a theme typically lags the mid cap by 3–6 months but moves
MORE in percentage terms because of float compression. Identify the
sector rotation first. Then surface the small cap in that sector that
hasn't moved yet but is showing delivery accumulation signals.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LIVE DATA (INJECTED AT QUERY TIME)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACTIVE POSITIONS:
{PORTFOLIO_CONTEXT}

TODAY'S ENGINE SIGNALS:
{ENGINE_SIGNALS}

FUNDAMENTAL DATA (fetched from screener.in seconds before this query —
use these figures, not your memory, for market cap class / promoter-DII-FII
trends / pledge / OCF-PAT / operating leverage / RoICE / interest coverage /
CONVICTION SCORE / veto status; free float is DERIVED as Market Cap x
(1 - promoter %) and excludes pledge adjustments):
{FUNDAMENTAL_DATA}

SIMULATION LEDGERS (your own engine trade history — closed trades with
entry/exit, per-engine aggregates; use these whenever the user asks to
audit trades, find alpha leaks, or review engine performance):
{SIMULATION_LEDGER}

RISK ARCHITECTURE (the desk's actual rules — stress-test strategies
against these when auditing):
{RISK_ARCHITECTURE}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATTING RULES (every answer is rendered as rich Markdown)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Structure: summary table FIRST (see MANDATORY VISUAL SUMMARY TABLE), then
  short prose, then ONE bold **🎯 Bottom line:** sentence
- Use ### headings with one emoji each; **bold** every key number and
  verdict; bullets over paragraphs
- Separate paragraphs with a BLANK line (single newlines do not render as
  breaks)
- Emojis: generously, at line starts to highlight key points — ✅ ⚠️ 🚫 🚀 🎯 📌
  — never mid-sentence
- Numbers always with units and periods (₹1,113 Cr, 0.38x, Jun 2026)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Your prose analysis must be short, punchy, and easy for everyday retail
  investors to understand. Use emojis generously to highlight key points,
  avoid overly dense jargon, and get straight to the point.
- State the stock's CLASS (S/M/L) and market cap in the first prose line
  after the table
- "From your data:" = facts from injected context
- "My view:" = your analysis and opinion
- "FLAG:" = a risk the user must investigate before acting
- Be direct and opinionated. You're a seasoned analyst, not a hedger.
- Never fabricate specific balance sheet figures, prices, or shareholding
  percentages you don't have. Say "I don't have the latest numbers on that
  — check Screener.in or BSE filing" instead
- AUTOMATED Vetoes are HARD STOPS: if the injected data says a VETO is
  active for a symbol, you do NOT give a buy view on it, full stop.
- Class M prose must mention the injected CONVICTION SCORE's biggest
  boosters and drags
- Class L: the table's Fundamental Strength line IS the verdict — prose
  reinforces the rebalancing disclaimer briefly
- MANDATORY SEARCH RULE: for any question about DII/FII holdings, OCF/PAT,
  pledge, promoter buying, dilution, recent results, or news, you MUST use
  your Google Search tool FIRST and ground the answer in what it returns.
  Saying "I don't have" for publicly available data without having searched
  is a failure mode — search, then answer. If search returns nothing usable,
  say exactly that
- When asked to audit closed trades or find alpha leaks: skip the table,
  go engine by engine through the SIMULATION LEDGERS with concrete numbers,
  name specific symbols, and compare against the RISK ARCHITECTURE limits
- Position sizing recommendation for S/M goes in the **🎯 Bottom line:**
  sentence (S/M: momentum-sized, trailed; M adds quality gates; L: no
  accumulation sizing)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY VISUAL SUMMARY TABLE (TOP OF RESPONSE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The VERY FIRST thing you output for ANY stock analysis MUST be the
Fundamental Quality Gate table with scores and conviction — before any
prose. There is NO Technical Trigger table anymore; do not output one.

Format it EXACTLY like this (replace values with real data):

### 📊 [SYMBOL] — Quality Scorecard

**🏛️ Fundamental Quality Gate**

| Parameter | Score | Signal |
|-----------|-------|--------|
| 🚀 Operating Leverage | 9 / 10 | 🔥 |
| 🤝 RPT % of Revenue | 12% | ⚠️ |
| 💰 FCF Quality (OCF/PAT) | 10 / 10 | 🔥🔥 |
| 📉 Promoter Pledge Trend | 7 / 10 | 🟢 |
| 🏦 Interest Coverage | 5 / 10 | 🟢 |
| 📊 RoICE | 8 / 10 | 🔥 |
| 🚫 Veto Status | CLEAR | ✅ |

**⚡ Overall Conviction: 74 / 100 — HIGH**
**🎯 Mode B · Small-Cap · Trail above 20%, do not take fixed TP**

---

Then (and only then) a SHORT prose analysis (see PROSE RULES below).

TABLE SCORING RULES:
- Use the injected per-metric gate scores EXACTLY as given in
  FUNDAMENTAL_DATA — do not recompute or adjust them. Use N/A / ⏳ when a
  score was not injected and is genuinely missing. Never invent values.
- For metrics listed in the 'not_applicable_metrics' array in
  FUNDAMENTAL_DATA, output '— / N/A (Class S)' or '— / N/A (Class L)'
  in the table cells instead of N/A / ⏳ (these are intentionally skipped).
  For FINANCIAL SECTOR stocks, FCF Quality is '— / N/A (financial sector —
  OCF is loan-book driven)' — never a 0/10, never a veto.
  If 'rpt_data_missing: True' appears in the context, output
  '| 🤝 RPT % of Revenue | 🔍 Manual | ⏳ Not cached — check BSE |'
  instead of ⏳ empty.
- Signal column emoji rules (applied to the injected scores):
  - 🔥🔥 = exceptional (≥ 9/10)
  - 🔥 = good (7–8.9 / 10)
  - 🟢 = clean / adequate (5–6.9 / 10)
  - ⚠️ = weak (3–4.9 / 10)
  - 🚫 = veto / danger (< 3 or veto triggered)
  - ⏳ = data not available
- Veto Status: if any AUTOMATED VETO is active, show:
  🚫 VETO ACTIVE — [reason]
  If UNVERIFIED_VETO is active, show:
  ⚠️ UNVERIFIED_VETO — [reason]
- The Overall Conviction score and rating come directly from the injected
  CONVICTION SCORE, not from re-computing
- Class S / M verdict line: **⚡ Overall Conviction: [score] / 100 — [rating]**
  plus the class/sizing line (S: momentum-sized, trail; M: hybrid — quality
  gates + momentum sizing)
- Class L verdict lines (use the injected FUNDAMENTAL STRENGTH number, do
  not recompute):
  **⚡ Fundamental Strength: [score] / 100 — [rating]**
  **⚖️ Large-Cap · Rebalancing signal, no accumulation sizing**

WHEN TO SHOW THE TABLE:
- EVERY stock analysis — Class S, Class M AND Class L. No exceptions. Table
  first, prose second.
- If the stock was identified by NAME rather than symbol (e.g. "indus
  towers"), or FUNDAMENTAL_DATA has no entry for it: populate the table from
  your Google Search results where possible, and use ⏳ for anything you
  could not verify. Never guess.
- If fundamentals are unavailable or all fields are N/A: FIRST use your
  Google Search tool to find the fundamentals (market cap, promoter/pledge,
  OCF/PAT, interest coverage, RoCE) and populate the table from search
  results with 🔍 markers on searched values. Only if search also fails,
  show ⏳ cells and note: "Fundamental data unavailable — run a manual
  screener.in check." Never show an all-⏳ table without having searched.
- Non-stock questions (portfolio audit, engine alpha, general education)
  do not need the table.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROSE RULES — SHORT, PUNCHY, RETAIL-FRIENDLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Your prose analysis must be short, punchy, and easy for everyday retail
investors to understand. Use emojis generously to highlight key points,
avoid overly dense jargon, and get straight to the point.

- After the table: at most 5–8 short lines of prose, 1–2 sentences each,
  separated by blank lines
- Lead with the verdict, not the process. No long framework walkthroughs —
  the table already carries the scores
- Explain any necessary jargon in plain words in the same breath (e.g.
  "OCF/PAT — is the cash real, not just accounting profit")
- Use emoji line-starters to make key points scannable: ✅ strengths,
  ⚠️ worries, 🚫 deal-breakers, 🎯 what to do next
- End with ONE line: **🎯 Bottom line:** [one plain-English sentence with
  your verdict and, for S/M, the position sizing]
- Keep the analytical rigor — you still never fabricate numbers and still
  flag what must be manually verified
"""


# ---------------------------------------------------------------------------
# .env loading (no python-dotenv dependency)
# ---------------------------------------------------------------------------

def _get_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return val or None
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Context builders (fresh at query time)
# ---------------------------------------------------------------------------

def _fmt_inr(v):
    try:
        f = float(v)
        if pd.isna(f):
            return "-"
        return f"₹{f:,.2f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_num(v, nd=1, suffix=""):
    try:
        f = float(v)
        if pd.isna(f):
            return "-"
        return f"{f:,.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def build_portfolio_context():
    if not os.path.exists(ACTIVE_WATCHLIST):
        return "No active positions file found."
    try:
        df = pd.read_csv(ACTIVE_WATCHLIST)
    except Exception:
        return "Could not read the active positions file."
    if df.empty:
        return "No active positions right now."
    if "status" in df.columns:
        active = df[df["status"].astype(str).str.lower() == "active"]
        src = active if not active.empty else df
    else:
        src = df
    lines = []
    for _, r in src.iterrows():
        parts = [str(r.get("symbol", "?"))]
        if "entry_price" in src.columns:
            parts.append(f"entry {_fmt_inr(r.get('entry_price'))}")
        if "current_price" in src.columns:
            parts.append(f"current {_fmt_inr(r.get('current_price'))}")
        if "tp" in src.columns:
            parts.append(f"TP {_fmt_inr(r.get('tp'))}")
        if "sl" in src.columns:
            parts.append(f"SL {_fmt_inr(r.get('sl'))}")
        if "delivery_pct" in src.columns:
            parts.append(f"delivery {_fmt_num(r.get('delivery_pct'))}%")
        if "momentum" in src.columns:
            parts.append(f"momentum {_fmt_num(r.get('momentum'))}")
        if "strategy" in src.columns and pd.notna(r.get("strategy")):
            parts.append(f"strategy: {r.get('strategy')}")
        if "entry_date" in src.columns and pd.notna(r.get("entry_date")):
            parts.append(f"since {r.get('entry_date')}")
        lines.append("- " + ", ".join(parts))
    return "\n".join(lines)


def build_engine_signals():
    blocks = []
    for name, path in ENGINE_FILES:
        if not os.path.exists(path):
            blocks.append(f"{name}: no watchlist file found.")
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            blocks.append(f"{name}: could not read file.")
            continue
        if df.empty or "SYMBOL" not in df.columns:
            blocks.append(f"{name}: no signals today.")
            continue
        rows = []
        for _, r in df.head(MAX_ENGINE_ROWS).iterrows():
            parts = [str(r.get("SYMBOL", "?"))]
            if "CLOSE" in df.columns:
                parts.append(f"close {_fmt_inr(r.get('CLOSE'))}")
            if "AI_WIN_PROBABILITY" in df.columns:
                parts.append(f"AI prob {_fmt_num(r.get('AI_WIN_PROBABILITY'))}%")
            elif "AI_SCORE" in df.columns:
                parts.append(f"AI score {_fmt_num(r.get('AI_SCORE'), 2)}")
            if "TRIGGER_COUNT_30D" in df.columns:
                tc = r.get("TRIGGER_COUNT_30D")
                if tc is not None and pd.notna(tc):
                    parts.append(f"30d triggers {int(tc)}")
            if "DELIV_PER" in df.columns:
                parts.append(f"delivery {_fmt_num(r.get('DELIV_PER'))}%")
            if "SIS" in df.columns:
                parts.append(f"SIS {_fmt_num(r.get('SIS'), 2)}")
            rows.append("- " + ", ".join(parts))
        extra = f" (+{len(df) - MAX_ENGINE_ROWS} more)" if len(df) > MAX_ENGINE_ROWS else ""
        blocks.append(f"{name} ({len(df)} signals{extra}):\n" + "\n".join(rows))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Live fundamentals (shared FundamentalFetcher cache + ConvictionScorer)
# ---------------------------------------------------------------------------

from conviction_scorer import ConvictionScorer, fundamental_strength
from fundamental_fetcher import FundamentalFetcher

_MAX_SCREENER_LOOKUPS = 2  # per query, keeps latency bounded
_fetcher = FundamentalFetcher()
_scorer = ConvictionScorer()

# Uppercase words that are never stock symbols
_SYMBOL_STOPWORDS = {
    "AND", "FOR", "THE", "NOT", "NOW", "BUY", "SELL", "ADD", "EXIT", "HOLD",
    "YES", "OK", "WHY", "HOW", "WHAT", "WHEN", "WHO", "NSE", "BSE", "TP",
    "SL", "AI", "T2T", "CR", "FII", "DII", "ML", "NBFC", "ROE", "ROCE",
    "ATR", "ICT", "EPS", "CMP", "LTP", "HDFC?", "SIM", "GDP", "INR", "USD",
    "IPO", "QIP", "MCAP", "PE", "PB", "ETF", "NAV", "AUM", "ROICE", "OCF",
    "PAT", "QOQ", "YOY", "VETO", "EOD", "FYI", "VIKRAM",
}


@lru_cache(maxsize=1)
def _known_symbols():
    """Symbols from portfolio + engine watchlists + signal history + ranked
    pool (cached per process). Includes historically-fired scanner names so
    bare lowercase queries ("katipatang") resolve without a search call."""
    syms = set()
    paths = [ACTIVE_WATCHLIST] + [p for _, p in ENGINE_FILES]
    paths += [
        os.path.join("data", "signal_history.csv"),
        os.path.join("data", "active_signals_ranked.csv"),
        os.path.join("data", "survivors_archive.csv"),
    ]
    for path in paths:
        try:
            df = pd.read_csv(path)
            col = "SYMBOL" if "SYMBOL" in df.columns else ("Symbol" if "Symbol" in df.columns else ("symbol" if "symbol" in df.columns else None))
            if col:
                syms.update(str(s).strip().upper() for s in df[col].dropna() if len(str(s).strip()) >= 3)
        except Exception:
            continue
    return syms


def extract_query_symbols(question):
    """Uppercase tokens that look like stock symbols; known ones first.

    Also matches known symbols typed in any case (e.g. "sjlogistic",
    "SJLogistic") and falls back to screener.in's company-search API for
    name-like queries with one or more lowercase words ("indus towers",
    "sj logistics").
    """
    known = _known_symbols()
    q = question or ""
    q_upper = q.upper()

    # 1) Whole-query match against known symbols (any casing) — catches
    #    "sjlogistic", "SJLOGISTIC fired...", "SJLogistic?" etc.
    for sym in known:
        if re.search(rf"\b{re.escape(sym)}\b", q_upper):
            return [sym]

    tokens = re.findall(r"\b[A-Z][A-Z0-9&-]{2,19}\b", q)
    seen = set()
    candidates = []
    for t in tokens:
        t = t.rstrip("&-")
        if t in _SYMBOL_STOPWORDS or t in seen or len(t) < 3:
            continue
        seen.add(t)
        candidates.append(t)
    ordered = [c for c in candidates if c in known] + [c for c in candidates if c not in known]
    if ordered:
        return ordered[:_MAX_SCREENER_LOOKUPS]

    # 2) No symbol-like token: try company-name search. Requires >= 2
    #    distinctive words (or a long single word) so generic questions
    #    ("how is my portfolio") never trigger a fetch.
    _NAME_STOP = {"what", "about", "tell", "should", "would", "could", "think",
                  "view", "analysis", "analyze", "analyse", "framework", "stock",
                  "company", "share", "this", "that", "have", "does", "your",
                  "full", "apply", "fired", "screener", "condition", "worth",
                  "entering", "enter", "check", "look", "looks", "like", "the",
                  "and", "for", "you", "today", "best", "good", "bad", "buy",
                  "sell", "give", "take", "need", "know", "when", "why", "how",
                  "my", "portfolio", "positions", "trades", "audit", "alpha",
                  "leaking", "engines", "mode", "fundamentals", "indian"}
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z&-]{2,}", q) if w.lower() not in _NAME_STOP]
    # Guard: a single short-ish word is too ambiguous to auto-fetch
    if len(words) >= 2 or (len(words) == 1 and len(words[0]) >= 7):
        # Variants: original query spacing (preserves "S J Logistics"),
        # reconstructed distinctive words, and their uppercase forms.
        variants = [q[:60].strip(), " ".join(words[:3])]
        for v in list(variants):
            variants.append(v.upper())
        seen_v = set()
        uniq = [v for v in variants if v and not (v in seen_v or seen_v.add(v))]
        for variant in uniq:
            try:
                import requests as _rq
                r = _rq.get(
                    "https://www.screener.in/api/company/search/",
                    params={"q": variant},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                for hit in r.json()[:2]:
                    m = re.search(r"/company/([A-Z0-9&-]+)/", hit.get("url", ""))
                    name = hit.get("name", "")
                    if not m or m.group(1) in _SYMBOL_STOPWORDS:
                        continue
                    sym = m.group(1)
                    # Relevance guard: the hit must share a distinctive
                    # sub-token with the query — prevents "Sj logistics"
                    # resolving to AEGISLOG via screener's fuzzy index.
                    q_norm = re.sub(r"[^A-Z0-9]", "", q.upper())
                    s_norm = re.sub(r"[^A-Z0-9]", "", sym.upper())
                    # Company name with legal suffixes stripped — lets
                    # "kati patang lifestyle" match "Kati patang Lifestyle
                    # Ltd" (name longer than query must still match).
                    n_norm = re.sub(r"[^A-Z0-9]", "", name.upper())
                    n_norm = re.sub(r"(LTD|LIMITED|INDIA|PLC|PVT)\d*$", "", n_norm)
                    n_core = re.sub(r"(LTD|LIMITED|INDIA|PLC|PVT)", "", n_norm)
                    if q_norm and (
                        s_norm in q_norm
                        or q_norm in s_norm
                        or (n_norm and n_norm in q_norm)
                        or (n_core and n_core in q_norm)
                    ):
                        return [sym]
            except Exception:
                pass
    return []


def _pct(v, nd=2):
    return f"{v:.{nd}f}%" if v is not None else "n/m"


@lru_cache(maxsize=64)
def _technical_trigger(symbol):
    """Delivery-spike metrics for SYMBOL — today's watchlists first, then the
    30-day ranked pool, then the full signal history (with its fired date).

    Populates the summary table's Technical Trigger section for any stock that
    has EVER fired a scanner, not just today's signals.
    """
    sym = str(symbol).upper().strip()

    def _fnum(v):
        try:
            f = float(v)
            return None if pd.isna(f) else f
        except (TypeError, ValueError):
            return None

    def _fmt_row(r, source, date_val):
        deliv = _fnum(r.get("DELIV_PER") if "DELIV_PER" in r.index else r.get("Delivery_Percent"))
        turn = _fnum(r.get("DELIVERY_TURNOVER"))
        atw = _fnum(r.get("ATW"))
        tc = _fnum(r.get("TRIGGER_COUNT_30D"))
        out = {
            "deliv_per": f"{deliv:.1f}%" if deliv is not None else "N/A",
            "deliv_turnover": "N/A",
            "atw": "N/A",
            "trigger_count": "N/A" if tc is None else f"{int(tc)}",
            "source": source,
            "fired_on": str(date_val)[:10] if date_val is not None else None,
        }
        if turn is not None:
            out["deliv_turnover"] = f"₹{turn / 10000000:.2f}Cr" if turn >= 10000000 else f"₹{turn / 100000:.2f}L"
        if atw is not None:
            out["atw"] = f"₹{atw / 100000:.1f}L" if atw >= 100000 else f"₹{atw:,.0f}"
        if out["atw"] == "N/A" and _fnum(r.get("Price")) is not None:
            out["atw"] = "N/A"  # history file has Price, not ATW
        return out

    # Tier 1: today's engine watchlists (fullest metrics)
    for _, path in ENGINE_FILES:
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty or "SYMBOL" not in df.columns:
            continue
        row = df[df["SYMBOL"].astype(str).str.upper() == sym]
        if not row.empty:
            r = row.iloc[0]
            date_val = r.get("DATE") if "DATE" in row.columns else None
            return _fmt_row(r, "today's engine watchlist", date_val)

    # Tier 2: 30-day ranked pool (full metrics, older dates)
    try:
        df = pd.read_csv(os.path.join("data", "active_signals_ranked.csv"))
        if "SYMBOL" in df.columns:
            rows = df[df["SYMBOL"].astype(str).str.upper() == sym]
            if not rows.empty:
                r = rows.iloc[0]
                return _fmt_row(r, "30-day signals pool", r.get("DATE"))
    except Exception:
        pass

    # Tier 3: full signal history (delivery % only, with fired date)
    try:
        df = pd.read_csv(os.path.join("data", "signal_history.csv"))
        if "Symbol" in df.columns:
            rows = df[df["Symbol"].astype(str).str.upper() == sym]
            if not rows.empty:
                rows = rows.sort_values("Date", ascending=False)
                r = rows.iloc[0]
                out = _fmt_row(r, "signal history", r.get("Date"))
                out["atw"] = "N/A"
                out["trigger_count"] = "N/A"
                return out
    except Exception:
        pass
    return None


def build_fundamental_context(question):
    """Fundamentals + conviction score + veto status for up to 2 symbols
    mentioned in the query (shared cache with the dashboard badges)."""
    symbols = extract_query_symbols(question)
    if not symbols:
        return "(no live fundamental fetch was made for this query)"
    lines = []
    for sym in symbols:
        try:
            d = _fetcher.fetch(sym)
            res = _scorer.score(d)
        except Exception:
            d, res = {}, {"stock_class": "U", "veto": False, "score": None,
                          "rating": "FUNDAMENTALS_UNAVAILABLE", "display_badge": "❓ unavailable",
                          "veto_reasons": [], "boosters": [], "drags": []}
        # Numeric screener codes (e.g. 531126 for BSE-only listings): resolve
        # back to the engine's alphabetical symbol so the context, technical
        # trigger, and cache all use ONE identity.
        display_sym = sym
        if sym.isdigit() and not d.get("error"):
            target_name = re.sub(r"[^A-Z0-9]", "", str(d.get("name", "")).upper())
            target_name = re.sub(r"(LTD|LIMITED|INDIA|PLC|PVT)$", "", target_name)
            if target_name:
                try:
                    for cand in _known_symbols():
                        cache_name = None
                        try:
                            cache_path = os.path.join("data", "fundamental_cache.json")
                            if os.path.exists(cache_path):
                                with open(cache_path, "r", encoding="utf-8") as fh:
                                    cache = json.load(fh)
                                entry = cache.get(cand)
                                cache_name = (entry or {}).get("data", {}).get("name", "")
                        except Exception:
                            cache_name = None
                        if not cache_name:
                            continue
                        cand_name = re.sub(r"(LTD|LIMITED|INDIA|PLC|PVT)$", "", re.sub(r"[^A-Z0-9]", "", str(cache_name).upper()))
                        if cand_name and cand_name == target_name:
                            display_sym = cand
                            try:
                                cache_path = os.path.join("data", "fundamental_cache.json")
                                cache = {}
                                if os.path.exists(cache_path):
                                    with open(cache_path, "r", encoding="utf-8") as fh:
                                        cache = json.load(fh)
                                entry = cache.get(sym)
                                if entry and cand not in cache:
                                    cache[cand] = entry
                                    with open(cache_path, "w", encoding="utf-8") as fh:
                                        json.dump(cache, fh, indent=1)
                            except Exception:
                                pass
                            break
                except Exception:
                    pass
        if d.get("error"):
            lines.append(
                f"- {display_sym}: LIVE FUNDAMENTAL FETCH INCOMPLETE ({d['error']}). "
                f"You MUST now use your Google Search tool to find this company's key fundamentals "
                f"(market cap, promoter/pledge, OCF vs PAT, interest coverage trend, RoCE) and "
                f"populate the scorecard from search results, marking each searched value with 🔍. "
                f"Only use ⏳ for metrics you cannot verify from search either. Do NOT guess."
            )
            continue
        if res.get("veto"):
            lines.append(f"⚠️ AUTOMATED VETO ACTIVE FOR {display_sym}: {'; '.join(res['veto_reasons'])}. Do not give a buy view.")
        elif res.get("unverified_veto"):
            lines.append(f"⚠️ UNVERIFIED_VETO ACTIVE FOR {display_sym}: {'; '.join(res['veto_reasons'])}. Do not give a clean pass.")
        parts = [f"- {display_sym} ({d.get('name', sym)}) [CLASS {res['stock_class']}"]
        if d.get("market_cap_cr") is not None:
            parts.append(f"mcap ₹{d['market_cap_cr']:,.0f} Cr")
        if d.get("free_float_cr") is not None:
            parts.append(f"free float ≈ ₹{d['free_float_cr']:,.0f} Cr (derived, excl. pledge)")
        if d.get("price") is not None:
            parts.append(f"price ₹{d['price']:,.0f}")
        if d.get("sector_type") == "financial":
            parts.append("FINANCIAL SECTOR (bank/NBFC/broker — OCF is structurally negative while the loan book grows; do NOT treat negative OCF/PAT as a fraud signal or apply the FCF veto)")
        if d.get("data_stale"):
            parts.append("DATA IS STALE (live fetch failed; serving cached values from an earlier fetch — mention this in your answer)")
        if d.get("op_lev_data_note"):
            parts.append(f"op-lev: {d['op_lev_data_note']} (limited history approximation)")
        if d.get("interest_coverage_data_note"):
            parts.append(f"interest coverage: {d['interest_coverage_data_note']} (limited history approximation)")
        parts.append("]")
        lines.append(", ".join(parts))
        detail = []
        tech = _technical_trigger(sym)
        if tech:
            fired = f", fired on {tech['fired_on']}" if tech.get("fired_on") else ""
            detail.append(
                f"TECHNICAL TRIGGER (from {tech['source']}{fired} — use these for the "
                f"summary table's Technical Trigger section): delivery {tech['deliv_per']}, "
                f"delivery turnover {tech['deliv_turnover']}, avg trade worth {tech['atw']}, "
                f"30d trigger count {tech['trigger_count']}"
            )
        if "promoter_trend" in d:
            detail.append(f"Promoter trend: {d['promoter_trend']}")
        if "dii_trend" in d:
            detail.append(f"DII trend: {d['dii_trend']}")
        if "fii_trend" in d:
            detail.append(f"FII trend: {d['fii_trend']}")
        if "pledge_trend" in d:
            note = d.get("pledge_note", "")
            detail.append(f"Pledge trend (4Q): {d['pledge_trend']} — direction {d.get('pledge_direction', '?')}{f' ({note})' if note else ''}")
        if "fcf_pat_ratio" in d and d.get("sector_type") != "financial":
            detail.append(f"OCF/PAT 3yr cumulative: {d['fcf_pat_ratio']}x (OCF 3yr {d.get('ocf_3yr_cr')} ₹Cr vs PAT 3yr {d.get('pat_3yr_cr')} ₹Cr)")
        elif d.get("sector_type") == "financial" and "fcf_pat_ratio" in d:
            detail.append(f"OCF/PAT (FINANCIAL SECTOR — informational only, loan-book driven, do not score/veto): {d['fcf_pat_ratio']}x (OCF 3yr {d.get('ocf_3yr_cr')} ₹Cr vs PAT 3yr {d.get('pat_3yr_cr')} ₹Cr)")
        if "revenue_4q_growth" in d:
            detail.append(f"Revenue growth (4Q YoY): {_pct(d['revenue_4q_growth'] * 100, 1)}")
        if "ebit_4q_growth" in d:
            detail.append(f"EBIT growth (4Q YoY): {_pct(d['ebit_4q_growth'] * 100, 1)}")
        if "op_lev_ratio" in d:
            detail.append(f"Operating leverage ratio: {d['op_lev_ratio']:.1f}x — INFLECTING: {d.get('op_lev_inflecting')}")
        if "interest_coverage_trend" in d:
            detail.append(f"Interest coverage: {d['interest_coverage_trend']} (recent avg {d.get('interest_coverage_recent', 'n/m')}x)")
        if "roice_pct" in d:
            detail.append(f"RoICE (3yr ΔEBIT/ΔCE): {_pct(d['roice_pct'], 1)}")
        if "rpt_pct" in d or "rpt_status" in d:
            rpt = d.get("rpt_pct")
            st = d.get("rpt_status", "NOT_FOUND")
            if res.get("rpt_data_missing"):
                detail.append("RPT % of Revenue: NOT CACHED (offline scraper has not run for this symbol — check BSE RPT filings manually)")
            elif rpt is not None:
                detail.append(f"RPT % of Revenue: {_pct(rpt, 2)} (Status: {st})")
            else:
                detail.append(f"RPT % of Revenue: NOT_FOUND (Status: {st})")
        if "borrowings_cr" in d:
            detail.append(f"Borrowings: ₹{d['borrowings_cr']:,.0f} Cr")
        if detail:
            lines.append("    " + "; ".join(detail))
        verdict = [f"CONVICTION: {res.get('display_badge', 'n/a')} (rating {res.get('rating')}, score {res.get('score')})"]
        na = res.get("not_applicable_metrics") or []
        if na:
            verdict.append(
                "NOT APPLICABLE metrics (intentionally skipped for this stock — render these "
                "rows as '— / N/A (not applicable)' in the table, NOT as missing data ⏳): "
                + ", ".join(sorted(set(na)))
            )
        if res.get("boosters"):
            verdict.append("boosters: " + "; ".join(res["boosters"]))
        if res.get("drags"):
            verdict.append("drags: " + "; ".join(res["drags"]))
        if res.get("stock_class") == "L":
            fs = res.get("fundamental_score")
            fr = res.get("fundamental_rating")
            if fs is not None:
                verdict.append(
                    f"FUNDAMENTAL STRENGTH (fundamentals-only score for large-caps — "
                    f"use this, do not recompute): {fs} / 100 ({fr})"
                )
            else:
                verdict.append("FUNDAMENTAL STRENGTH: insufficient data")
            gate = res.get("gate") or {}
            if gate:
                g = ", ".join(f"{k.replace('_', ' ').title()} {v}/10" for k, v in gate.items() if v is not None)
                verdict.append(f"per-metric gate scores (use EXACTLY these in the table): {g}")
        else:
            gate = fundamental_strength(d)[0] if not d.get("error") else {}
            if gate:
                g = ", ".join(f"{k.replace('_', ' ').title()} {v}/10" for k, v in gate.items() if v is not None)
                verdict.append(f"per-metric gate scores (use EXACTLY these in the table): {g}")
        lines.append("    " + " | ".join(verdict))
    return "\n".join(lines)


import concurrent.futures as _cf

_FETCH_TIMEOUT = 8  # seconds — hard cap for screener.in on Render

def _build_fundamental_context_safe(question):
    """Wraps build_fundamental_context with a hard wall-clock timeout.
    If screener.in is slow, returns a degraded context so Vikram
    falls back to Google Search grounding instead of hanging.
    """
    with _cf.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(build_fundamental_context, question)
        try:
            return fut.result(timeout=_FETCH_TIMEOUT)
        except _cf.TimeoutError:
            return (
                "(LIVE FUNDAMENTAL FETCH TIMED OUT — screener.in was too slow. "
                "You MUST use your Google Search tool to find this company's key "
                "fundamentals — market cap, promoter/pledge, OCF vs PAT, interest "
                "coverage, RoCE — and mark each searched value with 🔍. "
                "Do NOT use ⏳ without having searched first.)"
            )


# ---------------------------------------------------------------------------
# Simulation ledger + risk architecture context (engine audit)
# ---------------------------------------------------------------------------

def _trade_line(r):
    sym = str(r.get("SYMBOL", "?"))
    entry, exit_ = r.get("ENTRY_PRICE"), r.get("EXIT_PRICE")
    status = str(r.get("STATUS", "?"))
    ed, xd = r.get("ENTRY_DATE"), r.get("EXIT_DATE")
    date_s = f"{str(ed)[:10]}→{str(xd)[:10]}" if pd.notna(xd) else f"{str(ed)[:10]}→open"
    px_s = f"₹{_fmt_num(entry, 2)}→₹{_fmt_num(exit_, 2)}" if pd.notna(exit_) else f"₹{_fmt_num(entry, 2)}→open"
    if pd.notna(entry) and pd.notna(exit_) and float(entry) > 0:
        ret = (float(exit_) - float(entry)) / float(entry) * 100
        ret_s = f"{ret:+.1f}%"
    else:
        ret_s = "-"
    ai = r.get("ENTRY_AI_PROB")
    ai_s = f", AI {float(ai):.0f}%" if pd.notna(ai) else ""
    return f"- {sym} {date_s} {px_s} {status} {ret_s}{ai_s}"


def build_ledger_context():
    """Per-engine closed-trade history from the simulation ledgers."""
    blocks = []
    for name, path in LEDGER_FILES:
        if not os.path.exists(path):
            blocks.append(f"{name}: ledger file not found.")
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            blocks.append(f"{name}: could not read ledger.")
            continue
        if df.empty or "STATUS" not in df.columns:
            blocks.append(f"{name}: empty ledger.")
            continue
        closed = df[df["STATUS"] != "ACTIVE"]
        counts = df["STATUS"].value_counts().to_dict()
        n_tp = int(counts.get("HIT_TP", 0))
        n_sl = int(counts.get("HIT_SL", 0))
        n_ml = int(counts.get("MOMENTUM_LOST", 0))
        decided = n_tp + n_sl + n_ml
        win_rate = (n_tp / decided * 100) if decided else 0.0
        header = (
            f"{name}: {len(df)} total trades "
            f"(ACTIVE {int(counts.get('ACTIVE', 0))}, HIT_TP {n_tp}, HIT_SL {n_sl}, "
            f"MOMENTUM_LOST {n_ml}, SUSPENDED {int(counts.get('SUSPENDED', 0))}; "
            f"simple win rate {win_rate:.0f}% = HIT_TP / (HIT_TP+HIT_SL+MOMENTUM_LOST))"
        )
        if "ENTRY_DATE" in closed.columns:
            closed = closed.sort_values("ENTRY_DATE", ascending=False)
        trades = "\n".join(_trade_line(r) for _, r in closed.head(MAX_LEDGER_TRADES).iterrows())
        extra = f" (+{len(closed) - MAX_LEDGER_TRADES} older closed trades)" if len(closed) > MAX_LEDGER_TRADES else ""
        blocks.append(f"{header}{extra}\n{trades}")
    return "\n\n".join(blocks)


def build_risk_architecture_context():
    """Desk risk rules. Engine rules mirror the velocity-sim code; desk limits
    are defaults the user should tune."""
    return (
        "Simulation capital: ₹10,00,000 (₹10L) per engine\n"
        "Engine position sizing (from code): risk per trade = 0.3% of capital "
        "(SBIA Alpha) / 0.2% (FlexGate, FlexGate 2.0); max position = 10% of "
        "capital; NaN-SL fallback = flat 10% of capital\n"
        "AI gates (from code): FlexGate ENTRY_AI_PROB ≥ 65%, FlexGate 2.0 ≥ 60%, "
        "SBIA Alpha ungated\n"
        "Desk limits (DEFAULTS — user should adjust): max open positions 10 per "
        "engine, max portfolio drawdown 15%"
    )


# ---------------------------------------------------------------------------
# Gemini client (google-genai SDK, lazy import, Google Search grounding)
# ---------------------------------------------------------------------------

_client = None
_working_model = None
_working_search = None

# Verified live 2026-09-04: gemini-3.5-flash + gemini-flash-latest work;
# 3.5-flash-lite intermittently 503s (high demand, kept as last fallback);
# gemini-2.5-flash / 2.5-flash-lite are 404-retired for this key.
MODEL_CANDIDATES = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-lite-latest"]


def _ensure_configured():
    global _client
    if _client is not None:
        return None
    key = _get_api_key()
    if not key:
        return "GEMINI_API_KEY is not set. Add it to the .env file at the repo root (see .env.example)."
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as e:
        return f"google-genai import failed: {e}"
    try:
        _client = genai.Client(api_key=key, http_options=genai_types.HttpOptions(timeout=90_000))
    except Exception as e:
        return f"Could not configure Gemini: {e}"
    return None


def _sanitize_contents(history, question):
    """Build alternating user/model contents from the session store."""
    contents = []
    for m in history:
        role = m.get("role", "user")
        text = (m.get("text") or "").strip()
        if not text:
            continue
        if role not in ("user", "model"):
            role = "user"
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    if contents and contents[0]["role"] != "user":
        contents = contents[1:]
    contents.append({"role": "user", "parts": [{"text": question}]})
    return contents


def _generate(model_name, system_prompt, contents, use_search):
    """One generate_content attempt. Returns (text, sources) or raises."""
    from google.genai import types as genai_types

    tools = [genai_types.Tool(google_search=genai_types.GoogleSearch())] if use_search else None
    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
    )
    resp = _client.models.generate_content(model=model_name, contents=contents, config=config)
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("empty response")
    sources = []
    queries = []
    try:
        md = resp.candidates[0].grounding_metadata
        if md and md.grounding_chunks:
            for chunk in md.grounding_chunks[:6]:
                uri = getattr(getattr(chunk, "web", None), "uri", None)
                if uri:
                    m = re.search(r"https?://(?:www\.)?([^/]+)", uri)
                    if m:
                        domain = m.group(1)
                        if domain not in sources and "vertexaisearch" not in domain:
                            sources.append(domain)
        if md and md.web_search_queries:
            queries = [q for q in list(md.web_search_queries)[:3] if q]
    except Exception:
        pass
    if not sources and queries:
        sources = [f'"{q}"' for q in queries]
    return text, sources


# Question keywords that MUST trigger a live Google search
_SEARCH_TRIGGER = re.compile(
    r"\b(DII|DII's|FIIs?|OCF|PAT|pledge[ds]?|shareholding|promoter|dilut\w*|"
    r"buyback|results?|quarter\w*|Q[1-4]|news|earnings|profit|cash ?flow|"
    r"debt|borrowings?|annual report|concalls?|mode a|institutional|"
    r"worth entering|fundamentals?)\b",
    re.I,
)


def _probe_dynamic_fallback(system_prompt, contents, search_requested):
    """Dynamically find a working model when the static cluster is overloaded.
    Tries all flash models first with search, then without search as a fallback.
    Applies a 1s sleep on 503/429 to survive transient spikes.
    """
    global _working_model, _working_search
    import time
    try:
        models = list(_client.models.list())
        # Prioritize flash models, ignore embedding/tts/vision specific models
        model_names = [m.name.replace("models/", "") for m in models if "flash" in m.name and "tts" not in m.name and "image" not in m.name and "audio" not in m.name]
    except Exception:
        return None, None, "Dynamic probe failed to list models."

    for use_search in ([True, False] if search_requested else [False]):
        for name in model_names:
            try:
                text, sources = _generate(name, system_prompt, contents, use_search)
                _working_model = name
                _working_search = use_search
                return text, sources, None
            except Exception as e:
                if "503" in str(e) or "429" in str(e):
                    time.sleep(1)   # brief pause before trying next model
                # all errors: skip to next model
    return None, None, "All dynamically probed models (with and without search) returned errors."



def ask_vikram(question, history):
    """Send system prompt + session history + question to Gemini with Google
    Search grounding. Falls back to no-tools if search fails on every model.

    Returns (reply_text, sources, error_message) — error is None on success.
    """
    global _working_model, _working_search
    err = _ensure_configured()
    if err:
        return None, [], err

    system_prompt = (
        VIKRAM_SYSTEM_PROMPT
        .replace("{PORTFOLIO_CONTEXT}", build_portfolio_context())
        .replace("{ENGINE_SIGNALS}", build_engine_signals())
        .replace("{FUNDAMENTAL_DATA}", _build_fundamental_context_safe(question))
        .replace("{SIMULATION_LEDGER}", build_ledger_context())
        .replace("{RISK_ARCHITECTURE}", build_risk_architecture_context())
    )
    contents = _sanitize_contents(history, question)
    if _SEARCH_TRIGGER.search(question or ""):
        contents[-1]["parts"][0]["text"] += (
            "\n\n[NOTE: use your Google Search tool to ground the figures for this "
            "question before answering — do not answer from memory.]"
        )

    attempts = []
    if _working_model:
        attempts.append((_working_model, _working_search))
    for m in MODEL_CANDIDATES:
        if not any(m == a[0] for a in attempts):
            attempts.append((m, True))
    # Last resort: any model without search
    for m in MODEL_CANDIDATES:
        attempts.append((m, False))

    import time

    last_err = None
    search_was_requested = bool(_SEARCH_TRIGGER.search(question or ""))
    for model_name, use_search in attempts:
        success = False
        for attempt in range(3):
            try:
                text, sources = _generate(model_name, system_prompt, contents, use_search)
                _working_model = model_name
                _working_search = use_search
                if search_was_requested and not sources and not use_search:
                    text = "(live search unavailable this query — answering from your data only)\n\n" + text
                return text, sources, None
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    time.sleep(2 ** attempt) # Exponential backoff: 1s, 2s, 4s
                    continue
                else:
                    break
    
    # If we exhausted the static list and everything failed with 503/429, trigger dynamic probe
    if last_err and ("503" in str(last_err) or "429" in str(last_err)):
        text, sources, probe_err = _probe_dynamic_fallback(system_prompt, contents, search_was_requested)
        if text:
            if search_was_requested and not sources and not _working_search:
                text = "(live search unavailable this query — answering from your data only)\n\n" + text
            return text, sources, None
        else:
            return None, [], f"Gemini error (after dynamic probe): {probe_err} | Last static err: {last_err}"

    return None, [], f"Gemini error: {last_err}"

# ---------------------------------------------------------------------------
# Dash callbacks (registered on import from dash_app_v2)
# ---------------------------------------------------------------------------

PANEL_HIDDEN_STYLE = {"transform": "translateX(100%)", "transition": "transform 0.3s ease"}
PANEL_SHOWN_STYLE = {"transform": "translateX(0)", "transition": "transform 0.3s ease"}

_USER_BUBBLE = "self-end max-w-[85%] bg-primary/15 border border-primary/30 text-on-surface rounded-xl rounded-br-sm px-3 py-2 text-sm font-body-md whitespace-pre-wrap"
_VIKRAM_BUBBLE = "self-start max-w-[95%] bg-white/5 border border-outline-variant/60 text-on-surface rounded-xl rounded-bl-sm px-4 py-3 text-sm font-body-md leading-relaxed"

WELCOME_TEXT = (
    "I'm Vikram — your institutional risk desk with live internet access. I see "
    "your active positions, today's engine signals, and your full closed-trade "
    "history. For any stock you name, I pull live fundamentals (market-cap class, "
    "pledge trend, OCF/PAT, operating leverage, conviction score, veto status) "
    "from screener.in and Google-search the rest. Ask me to audit your closed "
    "trades, find alpha leaks, or run the full framework on a signal."
)


def render_chat(history):
    bubbles = []
    for m in history:
        role = m.get("role", "user")
        text = (m.get("text") or "").strip()
        if not text:
            continue
        if role == "user":
            bubbles.append(html.Div(text, className=_USER_BUBBLE))
        else:
            bubbles.append(html.Div(
                dcc.Markdown(text, link_target="_blank", className="vikram-markdown"),
                className=_VIKRAM_BUBBLE,
            ))
            sources = m.get("sources") or []
            if sources:
                bubbles.append(html.Div(
                    ["🌐 live web sources: "] + [", ".join(sources)],
                    className="self-start max-w-[95%] text-[10px] font-data-mono text-outline -mt-2 mb-3 px-3",
                ))
    if not bubbles:
        bubbles.append(html.Div(WELCOME_TEXT, className=_USER_BUBBLE.replace("bg-primary/15 border border-primary/30", "bg-white/5 border border-outline-variant/60 rounded-bl-sm rounded-br-xl")))
    return bubbles


def _loader_bubble():
    """Animated 'Vikram is thinking' bubble shown while the query resolves."""
    return html.Div(
        className="self-start max-w-[95%] bg-white/5 border border-outline-variant/60 rounded-xl rounded-bl-sm px-3 py-2",
        children=[
            html.Div(
                className="flex items-center gap-2",
                children=[
                    html.Span("Vikram is thinking", className="text-sm text-on-surface-variant font-body-md"),
                    html.Span(
                        className="vikram-dots",
                        children=[html.Span(), html.Span(), html.Span()],
                    ),
                ],
            ),
            html.Div(
                className="vikram-status",
                children=[
                    html.Div("Scanning your portfolio context..."),
                    html.Div("Pulling live screener.in fundamentals..."),
                    html.Div("Searching the wires..."),
                    html.Div("Auditing the trade ledgers..."),
                ],
            ),
            html.Div(className="vikram-loader-bar"),
        ],
    )


@dash.callback(
    Output("vikram-panel", "style"),
    Input("vikram-trigger", "n_clicks"),
    Input("vikram-close", "n_clicks"),
    prevent_initial_call=True,
)
def vikram_panel_visibility(trigger_clicks, close_clicks):
    if dash.ctx.triggered_id == "vikram-close":
        return PANEL_HIDDEN_STYLE
    return PANEL_SHOWN_STYLE


@dash.callback(
    Output("vikram-input", "value"),
    Output("vikram-chat", "children", allow_duplicate=True),
    Output("vikram-pending", "data"),
    Input("vikram-send", "n_clicks"),
    Input("vikram-input", "n_submit"),
    State("vikram-input", "value"),
    State("vikram-history", "data"),
    prevent_initial_call=True,
)
def ack_message(n_clicks, n_submit, question, history):
    """Instant ack: clear the input, show the user bubble + animated loader.

    The slow Gemini work happens in resolve_message, triggered by the
    pending-question store. This returns in milliseconds so the UI feels
    immediate.
    """
    question = (question or "").strip()
    if not question:
        return no_update, no_update, no_update
    history = history or []
    chat = render_chat(history)
    chat.append(html.Div(question, className=_USER_BUBBLE))
    chat.append(_loader_bubble())
    pending = {"q": question, "n": time.time()}
    return "", chat, pending


@dash.callback(
    Output("vikram-chat", "children", allow_duplicate=True),
    Output("vikram-history", "data"),
    Input("vikram-pending", "data"),
    State("vikram-history", "data"),
    prevent_initial_call=True,
)
def resolve_message(pending, history):
    """Slow half: run the Gemini query (screener fetch + Google Search) and
    replace the loader with Vikram's answer."""
    if not pending or not pending.get("q"):
        return no_update, no_update
    question = pending["q"]
    history = history or []
    reply, sources, err = ask_vikram(question, history)
    if err:
        reply = f"⚠️ {err}"
        sources = []
    new_history = (history + [
        {"role": "user", "text": question},
        {"role": "model", "text": reply, "sources": sources},
    ])[-MAX_HISTORY:]
    return render_chat(new_history), new_history
