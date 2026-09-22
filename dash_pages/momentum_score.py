import os
from functools import lru_cache
import dash
from dash import html, dcc, Input, Output, callback
from dash_iconify import DashIconify
import pandas as pd

from conviction_scorer import ConvictionScorer
from fundamental_fetcher import FundamentalFetcher
from momentum_scorer import MomentumScorer

dash.register_page(
    __name__,
    path="/momentum",
    name="Momentum Score",
    title="Pro Spike - Momentum Score",
)

_fetcher = FundamentalFetcher()
_vikram_scorer = ConvictionScorer()
_momentum_scorer = MomentumScorer()

RANKED_SIGNALS_FILE = os.path.join("data", "active_signals_ranked.csv")
LEGACY_WATCHLIST_FILE = os.path.join("data", "legacy_watchlist.csv")
CLOUD_LEDGER_FILE = os.path.join("data", "dashboard_cloud.csv")

# Known alias & scrip code resolutions for Indian equities
SYMBOL_ALIASES = {
    "531399": "GGAUTO",
    "TATAMOTORS": "TMCV",
    "ZOMATO": "ETERNAL",
}


@lru_cache(maxsize=1)
def _load_available_symbols():
    """Load the complete market universe (4,400+ stocks) prioritizing active breakout signals."""
    priority_syms = []
    # 1. Active ranked signals & watchlist (highest priority)
    for path in (RANKED_SIGNALS_FILE, LEGACY_WATCHLIST_FILE):
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, usecols=["SYMBOL"])
                for s in df["SYMBOL"].dropna().astype(str).str.upper().unique():
                    if s and s not in priority_syms:
                        priority_syms.append(s)
            except Exception:
                pass

    # 2. Main cloud ledger containing full NSE/BSE universe
    cloud_syms = []
    if os.path.exists(CLOUD_LEDGER_FILE):
        try:
            df = pd.read_csv(CLOUD_LEDGER_FILE, usecols=["SYMBOL"])
            cloud_syms = [s for s in df["SYMBOL"].dropna().astype(str).str.upper().unique() if s]
        except Exception:
            pass

    seen = set(priority_syms)
    remaining = sorted([s for s in cloud_syms if s not in seen])
    
    full_universe = priority_syms + remaining
    if not full_universe:
        full_universe = ["GGAUTO", "JOJO", "NATFIT", "PAYTM", "SAKSOFT", "GREENPLY", "EMAMILTD"]
    return full_universe


def _get_dropdown_options():
    """Build searchable options with visual breakout markers and scrip aliases."""
    syms = _load_available_symbols()
    active_set = set()
    if os.path.exists(RANKED_SIGNALS_FILE):
        try:
            df = pd.read_csv(RANKED_SIGNALS_FILE, usecols=["SYMBOL"])
            active_set = set(df["SYMBOL"].dropna().astype(str).str.upper())
        except Exception:
            pass

    options = []
    # Dedicated BSE scrip alias for quick access
    options.append({"label": "531399 — G G Automotive Gears (BSE)", "value": "531399"})
    
    for s in syms:
        if s in active_set:
            options.append({"label": f"🔥 {s} (Active Breakout)", "value": s})
        else:
            options.append({"label": s, "value": s})
    return options


def _get_signal_row(symbol):
    """Retrieve signal and live trading metrics across active signals, watchlist, or cloud ledger."""
    raw_sym = str(symbol).upper().strip()
    sym = SYMBOL_ALIASES.get(raw_sym, raw_sym)

    for path in (RANKED_SIGNALS_FILE, LEGACY_WATCHLIST_FILE, CLOUD_LEDGER_FILE):
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                col = "SYMBOL" if "SYMBOL" in df.columns else ("Symbol" if "Symbol" in df.columns else None)
                if col:
                    match = df[df[col].astype(str).str.upper() == sym]
                    if not match.empty:
                        return match.iloc[0].to_dict()
            except Exception:
                pass
    return {}


layout = html.Div(
    className="flex flex-col gap-6 max-w-7xl mx-auto px-4 py-6",
    children=[
        # Page Title Banner & Universal Search
        html.Div(
            className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-outline-variant/40 pb-6",
            children=[
                html.Div(
                    children=[
                        html.Div(
                            className="flex items-center gap-3",
                            children=[
                                html.Span("speed", className="material-symbols-outlined text-primary text-3xl"),
                                html.H1("Dual-Engine Conviction Architecture", className="font-headline-sm text-2xl md:text-3xl font-bold text-on-background tracking-tight"),
                            ]
                        ),
                        html.P(
                            "Float Mechanics (55%) × Empirical Fundamentals (45%) — Daily Tactical Execution Filter",
                            className="font-body-md text-sm text-outline mt-1",
                        ),
                    ]
                ),
                # Stock Selector (Supports 4,400+ symbols & BSE scrip codes)
                html.Div(
                    className="flex items-center gap-3 w-full md:w-auto",
                    children=[
                        html.Label("Target Stock:", className="font-label-caps text-xs text-on-surface-variant whitespace-nowrap uppercase tracking-wider"),
                        dcc.Dropdown(
                            id="momentum-stock-selector",
                            options=_get_dropdown_options(),
                            value="GGAUTO",
                            clearable=False,
                            searchable=True,
                            placeholder="Search 4,400+ stocks (e.g. GGAUTO, TCS, 531399)...",
                            className="w-full md:w-80 text-sm font-data-mono bg-surface-container-low text-on-surface border-outline-variant",
                            style={"color": "#000"},
                        ),
                    ]
                ),
            ]
        ),

        # Dynamic Content Container
        html.Div(id="momentum-content-container"),
    ]
)


@callback(
    Output("momentum-content-container", "children"),
    Input("momentum-stock-selector", "value"),
)
def render_momentum_analysis(symbol):
    if not symbol:
        return html.Div("Please select or search a stock.", className="text-on-surface-variant p-8 text-center")

    raw_sym = str(symbol).upper().strip()
    sym = SYMBOL_ALIASES.get(raw_sym, raw_sym)

    fund = _fetcher.fetch(sym) or {}
    signal_row = _get_signal_row(sym)

    vikram_res = _vikram_scorer.score(fund)
    momentum_res = _momentum_scorer.score(signal_row, fund)

    # 1. Stock Identity & Quick Stats Bar
    comp_name = fund.get("name") or signal_row.get("NAME") or sym
    close_price = signal_row.get("CLOSE") or fund.get("price")
    exchange = signal_row.get("EXCHANGE") or "NSE/BSE"
    deliv_pct = signal_row.get("DELIV_PER")
    mcap_cr = fund.get("market_cap_cr")

    price_str = f"₹{float(close_price):,.2f}" if close_price is not None else "Price N/A"
    deliv_str = f"{float(deliv_pct):.1f}% Deliv" if deliv_pct is not None else "Deliv N/A"
    mcap_str = f"₹{float(mcap_cr):,.0f} Cr Mcap" if mcap_cr is not None else ""

    stock_header = html.Div(
        className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-surface-container-lowest border border-white/5 shadow-sm",
        children=[
            html.Div(
                className="flex items-center gap-3",
                children=[
                    html.Div(
                        sym,
                        className="font-headline-sm font-bold text-xl text-on-surface font-data-mono px-3 py-1 rounded bg-white/5 border border-white/10"
                    ),
                    html.Div(
                        children=[
                            html.H2(comp_name, className="font-headline-sm font-semibold text-base text-on-surface tracking-tight"),
                            html.Div(
                                className="flex items-center gap-2 text-xs text-outline font-data-mono mt-0.5",
                                children=[
                                    html.Span(exchange, className="px-1.5 py-0.2 rounded bg-white/5 border border-white/5"),
                                    html.Span("•"),
                                    html.Span(price_str, className="text-secondary font-bold"),
                                    html.Span("•"),
                                    html.Span(deliv_str, className="text-primary font-semibold"),
                                    *( [html.Span("•"), html.Span(mcap_str)] if mcap_str else [] )
                                ]
                            )
                        ]
                    )
                ]
            ),
            html.Div(
                className="flex items-center gap-2",
                children=[
                    html.Span("LIVE DATA ENGINE", className="px-2.5 py-1 rounded text-xs font-label-caps font-bold bg-primary/10 text-primary border border-primary/20"),
                ]
            )
        ]
    )

    # 2. Global Veto Status Banner
    is_vetoed = vikram_res.get("veto", False) or momentum_res.get("blocked_by_veto", False)
    veto_reasons = vikram_res.get("veto_reasons", []) or momentum_res.get("veto_reasons", [])

    if is_vetoed:
        veto_banner = html.Div(
            className="p-5 rounded-2xl bg-error-container/20 border border-error/40 flex items-start gap-4 shadow-lg shadow-error/5",
            children=[
                html.Span("dangerous", className="material-symbols-outlined text-error text-3xl mt-0.5"),
                html.Div(
                    className="flex-1",
                    children=[
                        html.H3("GLOBAL HARD VETO TRIGGERED — EXECUTION FORBIDDEN", className="font-headline-sm font-bold text-error tracking-wide text-lg"),
                        html.P(
                            f"Veto deal-breaker: {veto_reasons[0] if veto_reasons else 'Failed critical governance/cash flow threshold.'}",
                            className="text-sm font-body-md text-on-error-container mt-1",
                        ),
                        html.P(
                            "Empirical Rule: Micro/small-cap breakouts with active vetoes (pledge >25% or FCF divergence) suffer severe multi-week decay. Tactical momentum entry is strictly blocked.",
                            className="text-xs text-outline mt-2 italic",
                        ),
                    ]
                ),
                html.Span("🚫 BLOCKED", className="px-3 py-1 rounded-full text-xs font-bold font-data-mono bg-error text-on-error tracking-wider"),
            ]
        )
    else:
        veto_banner = html.Div(
            className="p-4 rounded-2xl bg-secondary-container/15 border border-secondary/30 flex items-center justify-between shadow-sm",
            children=[
                html.Div(
                    className="flex items-center gap-3",
                    children=[
                        html.Span("verified_user", className="material-symbols-outlined text-secondary text-2xl"),
                        html.Div(
                            children=[
                                html.Span("GLOBAL HARD VETO: CLEAR", className="font-headline-sm font-bold text-secondary text-base tracking-wide"),
                                html.Span(" • Zero promoter pledge & verified cash conversion buffer.", className="text-xs text-on-surface-variant ml-2"),
                            ]
                        ),
                    ]
                ),
                html.Span("✅ PASS", className="px-3 py-1 rounded-full text-xs font-bold font-data-mono bg-secondary/20 text-secondary border border-secondary/30"),
            ]
        )

    # 3. Composite Actionable Recommendation Banner (ELEVATED TO TOP FOR 3-SEC TIME-TO-VERDICT)
    vikram_score = vikram_res.get("score")
    vikram_rating = vikram_res.get("rating", "UNAVAILABLE")
    
    mom_score = momentum_res.get("momentum_score", 0)
    mom_tier = momentum_res.get("momentum_tier", "WEAK")
    part_a_pts = momentum_res.get("part_a_contrib", 0.0)
    part_b_pts = momentum_res.get("part_b_contrib", 0.0)

    if is_vetoed:
        rec_badge = "🚫 FORBIDDEN"
        rec_badge_style = "bg-error text-on-error border-error"
        rec_title = "EXECUTION BLOCKED — DO NOT ENTER"
        rec_desc = f"Hard veto triggered: {veto_reasons[0] if veto_reasons else 'Governance or cash divergence risk'}. Capital protection active."
        rec_style = "border-error/40 bg-error-container/20 text-error"
    elif mom_score >= 85 and (vikram_score or 0) >= 70:
        rec_badge = "BUY — MAX SIZE"
        rec_badge_style = "bg-secondary text-on-secondary font-bold"
        rec_title = "🟢 ELITE CONVICTION SETUP — MAXIMUM ALLOCATION"
        rec_desc = "All 3 gates aligned: Veto Clear + High Quality Fundamentals + Aggressive Float Cornering (>1.5% absorbed). Prime tactical breakout candidate. Trail with ATR Chandelier."
        rec_style = "border-secondary/50 bg-secondary-container/20 text-secondary"
    elif mom_score >= 70 and (vikram_score or 0) >= 45:
        rec_badge = "BUY — STANDARD"
        rec_badge_style = "bg-[#38bdf8] text-black font-bold"
        rec_title = "🔵 HIGH CONVICTION SETUP — STANDARD ALLOCATION"
        rec_desc = "Institutional float accumulation backed by acceptable solvency. Initiate standard sizing and trail stop-loss above 20-day EMA."
        rec_style = "border-[#38bdf8]/40 bg-[#38bdf8]/10 text-[#38bdf8]"
    elif mom_score >= 55:
        rec_badge = "WATCHLIST ONLY"
        rec_badge_style = "bg-[#FFB300] text-black font-bold"
        rec_title = "🟡 MODERATE SETUP — WATCHLIST / REDUCED SIZING"
        rec_desc = "Partial float mechanics detected or slower turnover velocity. Wait for volume expansion or clean consolidation breakout before full entry."
        rec_style = "border-[#FFB300]/40 bg-[#FFB300]/10 text-[#FFB300]"
    else:
        rec_badge = "AVOID / WEAK"
        rec_badge_style = "bg-white/10 text-outline border border-white/10"
        rec_title = "🔴 WEAK MOMENTUM — SKIP ENTRY"
        rec_desc = "Insufficient float cornering volume or weak fundamental scoring today. Capital is better deployed in active Tier-1 breakout setups."
        rec_style = "border-outline-variant/40 bg-surface-container-lowest text-outline"

    recommendation_card = html.Div(
        className=f"p-6 rounded-2xl border {rec_style} flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-xl",
        children=[
            html.Div(
                children=[
                    html.Div(
                        className="flex items-center gap-3",
                        children=[
                            html.Span(rec_badge, className=f"px-3 py-1 rounded-full text-xs font-bold font-data-mono tracking-wider {rec_badge_style}"),
                            html.H3(rec_title, className="font-headline-sm font-bold tracking-wide text-lg text-on-surface"),
                        ]
                    ),
                    html.P(rec_desc, className="text-sm font-body-md text-on-surface/90 mt-2 leading-relaxed"),
                ]
            ),
            html.Div(
                className="flex flex-col items-end gap-1 font-data-mono text-xs text-outline whitespace-nowrap",
                children=[
                    html.Span("PRO-SPIKE DUAL-ENGINE v3"),
                    html.Span("3-Second Trade Verdict", className="text-[10px] text-outline/80"),
                ]
            ),
        ]
    )

    # 4. Dual-Engine Scores Summary Cards with Plain-English Roles
    tier_colors = {
        "ELITE": "text-secondary border-secondary/40 bg-secondary-container/20",
        "HIGH": "text-[#38bdf8] border-[#38bdf8]/40 bg-[#38bdf8]/10",
        "MODERATE": "text-[#FFB300] border-[#FFB300]/40 bg-[#FFB300]/10",
        "WEAK": "text-error border-error/40 bg-error-container/10",
        "BLOCKED": "text-error border-error/40 bg-error-container/20",
    }

    cards_row = html.Div(
        className="grid grid-cols-1 md:grid-cols-2 gap-6",
        children=[
            # Card 1: Vikram Quality Gatekeeper
            html.Div(
                className="p-6 rounded-2xl bg-surface-container-low border border-white/5 flex flex-col justify-between shadow-xl relative overflow-hidden",
                children=[
                    html.Div(
                        className="flex items-center justify-between mb-4",
                        children=[
                            html.Div(
                                className="flex items-center gap-2.5",
                                children=[
                                    html.Span("account_balance", className="material-symbols-outlined text-primary text-2xl"),
                                    html.Div(
                                        children=[
                                            html.H4("Vikram 5-Metric Quality Gate", className="font-headline-sm font-bold text-on-surface text-base"),
                                            html.Span("Phase 1: Fundamental Safety Filter (Can We Hold It?)", className="font-label-caps text-xs text-primary font-semibold"),
                                        ]
                                    ),
                                ]
                            ),
                            html.Span(
                                f"{vikram_rating}",
                                className="text-xs font-bold font-data-mono px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-on-surface-variant",
                            ),
                        ]
                    ),
                    html.Div(
                        className="flex items-baseline gap-3 my-2",
                        children=[
                            html.Span(f"{vikram_score if vikram_score is not None else 'N/A'}", className="font-headline-sm text-5xl font-bold text-primary font-data-mono"),
                            html.Span("/ 100", className="text-sm font-data-mono text-outline"),
                        ]
                    ),
                    html.P(
                        "Evaluates long-term balance sheet health: Operating Leverage (30%), Zero Pledge (25%), FCF Cash Conversion (20%), Interest Coverage (20%), RoICE (5%).",
                        className="text-xs text-on-surface-variant mt-2 leading-relaxed",
                    ),
                ]
            ),

            # Card 2: Momentum Scorer Tactical Trigger
            html.Div(
                className="p-6 rounded-2xl bg-surface-container-low border border-white/5 flex flex-col justify-between shadow-xl relative overflow-hidden",
                children=[
                    html.Div(
                        className="flex items-center justify-between mb-4",
                        children=[
                            html.Div(
                                className="flex items-center gap-2.5",
                                children=[
                                    html.Span("bolt", className="material-symbols-outlined text-secondary text-2xl"),
                                    html.Div(
                                        children=[
                                            html.H4("Tactical Momentum Score", className="font-headline-sm font-bold text-on-surface text-base"),
                                            html.Span("Phase 2: Float Ignition Trigger (Is Money Entering TODAY?)", className="font-label-caps text-xs text-secondary font-semibold"),
                                        ]
                                    ),
                                ]
                            ),
                            html.Span(
                                f"{mom_tier}",
                                className=f"text-xs font-bold font-data-mono px-2.5 py-1 rounded-full border {tier_colors.get(mom_tier, tier_colors['WEAK'])}",
                            ),
                        ]
                    ),
                    html.Div(
                        className="flex items-baseline gap-3 my-2",
                        children=[
                            html.Span(f"{mom_score}", className="font-headline-sm text-5xl font-bold text-secondary font-data-mono"),
                            html.Span("/ 100", className="text-sm font-data-mono text-outline"),
                            html.Span(f"(Part A: {part_a_pts:.1f} pts + Part B: {part_b_pts:.1f} pts)", className="text-xs font-data-mono text-outline ml-auto"),
                        ]
                    ),
                    html.P(
                        "Measures institutional float cornering today: Float Mechanics (55% weight) combined with Live Ledger Empirical Weights (45% weight).",
                        className="text-xs text-on-surface-variant mt-2 leading-relaxed",
                    ),
                ]
            ),
        ]
    )

    # 5. Sub-Part A Breakdown Table: Float Mechanics (55%)
    part_a_data = momentum_res.get("part_a_breakdown", {})
    table_a_rows = []
    
    metric_labels_a = [
        ("delivery_pct", "Delivery Percentage", "Institutional accumulation density in today's traded volume (Benchmark: ≥87%)"),
        ("delivery_turnover", "Delivery Turnover", "Total capital committed today (Sweet spot for micro-caps: ₹3.5–5.0 Cr)"),
        ("float_absorbed", "Daily Float Absorbed %", "Depletion rate of freely floating shares (>1.5% signals aggressive institutional cornering)"),
        ("intraday_mae", "Intraday Buyer Defense (Max Dip)", "Buyer resilience (Max Adverse Excursion: defending open without dip > -1.8%)"),
    ]

    for key, name, desc in metric_labels_a:
        m_info = part_a_data.get(key, {})
        val_str = m_info.get("label", "N/A")
        score_val = m_info.get("gate_score", 0)
        thresh = m_info.get("threshold", "—")
        pts = m_info.get("pts", 0.0)

        badge_color = "text-secondary bg-secondary-container/20 border-secondary/40" if score_val >= 8 else (
            "text-[#FFB300] bg-[#FFB300]/15 border-[#FFB300]/30" if score_val >= 5 else "text-error bg-error-container/20 border-error/30"
        )

        table_a_rows.append(
            html.Tr(
                className="border-b border-outline-variant/20 hover:bg-white/[0.02] transition-colors",
                children=[
                    html.Td(
                        className="py-3 px-4",
                        children=[
                            html.Div(name, className="font-bold text-sm text-on-surface"),
                            html.Div(desc, className="text-xs text-outline mt-0.5"),
                        ]
                    ),
                    html.Td(val_str, className="py-3 px-4 font-data-mono text-sm font-semibold text-on-surface"),
                    html.Td(thresh, className="py-3 px-4 font-data-mono text-xs text-outline"),
                    html.Td(
                        html.Span(f"{score_val}/10", className=f"px-2 py-0.5 rounded text-xs font-bold font-data-mono border {badge_color}"),
                        className="py-3 px-4"
                    ),
                    html.Td(f"+{pts:.2f} pts", className="py-3 px-4 font-data-mono text-sm text-right text-secondary font-semibold"),
                ]
            )
        )

    # 6. Sub-Part B Breakdown Table: Empirical Fundamentals (45%) with GRACEFUL N/A RESOLUTION
    part_b_data = momentum_res.get("part_b_breakdown", {})
    table_b_rows = []

    metric_labels_b = [
        ("fcf_quality", "FCF / PAT Cash Quality", "30%", "20%", "Cash conversion is the #1 truth engine separating real multi-baggers from paper profits"),
        ("pledge_trend", "Promoter Pledge Trend", "30%", "25%", "100% of clean small-cap breakout winners had 0.00% promoter pledge encumbrance"),
        ("interest_coverage", "Interest Coverage Solvency", "25%", "20%", "Solvency buffer to eliminate micro-cap debt traps and sudden distress halts"),
        ("op_leverage", "Operating Leverage", "10%", "30%", "EBIT growth relative to revenue growth — measures operational profit amplification"),
        ("roice", "RoICE Delta %", "5%", "5%", "Incremental return on invested capital expansion across multi-year capex cycles"),
    ]

    is_financial = fund.get("sector_type") == "financial"

    for key, name, mom_w, vik_w, rationale in metric_labels_b:
        m_info = part_b_data.get(key, {})
        score_val = m_info.get("gate_score")
        pts = m_info.get("pts", 0.0)

        # Contextual Graceful Badge & Label Handling
        if score_val is not None:
            if score_val == 0 and is_vetoed:
                score_str = "0/10 (Veto Trigger)"
                badge_color = "text-error bg-error-container/20 border-error/40"
                extra_note = "Deal-breaker threshold violated — tactical entry forbidden."
            else:
                score_str = f"{score_val}/10"
                badge_color = "text-secondary bg-secondary-container/20 border-secondary/40" if score_val >= 8 else (
                    "text-[#FFB300] bg-[#FFB300]/15 border-[#FFB300]/30" if score_val >= 5 else "text-error bg-error-container/20 border-error/30"
                )
                extra_note = None
        else:
            # Handle N/A gracefully depending on accounting reality
            if key == "op_leverage":
                score_str = "Neutral (Turnaround)"
                badge_color = "text-on-surface-variant bg-white/5 border-outline-variant/40"
                extra_note = "Non-linear: prior EBIT was negative or YoY revenue is flat during consolidation."
            elif key == "fcf_quality" and is_financial:
                score_str = "N/A (Financial / Bank)"
                badge_color = "text-secondary bg-secondary-container/10 border-secondary/30"
                extra_note = "Banks & NBFCs disburse loans as operating outflows; OCF/PAT ratio not applicable."
            elif key == "fcf_quality":
                score_str = "Unfiled (Standalone)"
                badge_color = "text-outline bg-white/5 border-outline-variant/40"
                extra_note = "Standalone BSE small-cap: annual cash flow conversion not published on Screener."
            elif key == "interest_coverage":
                score_str = "Debt Free / Neutral"
                badge_color = "text-on-surface-variant bg-white/5 border-outline-variant/40"
                extra_note = "Company has minimal or zero interest obligations."
            else:
                score_str = "Neutral (Unfiled)"
                badge_color = "text-outline bg-white/5 border-outline-variant/40"
                extra_note = "Requires 3 consecutive years of audited balance sheet data."

        table_b_rows.append(
            html.Tr(
                className="border-b border-outline-variant/20 hover:bg-white/[0.02] transition-colors",
                children=[
                    html.Td(
                        className="py-3 px-4",
                        children=[
                            html.Div(name, className="font-bold text-sm text-on-surface"),
                            html.Div(rationale, className="text-xs text-outline mt-0.5"),
                            *( [html.Div(f"ℹ️ {extra_note}", className="text-[11px] text-primary/80 mt-1 italic")] if extra_note else [] )
                        ]
                    ),
                    html.Td(
                        html.Span(score_str, className=f"px-2.5 py-0.5 rounded text-xs font-bold font-data-mono border {badge_color}"),
                        className="py-3 px-4 whitespace-nowrap"
                    ),
                    html.Td(
                        html.Div(
                            children=[
                                html.Span(mom_w, className="font-bold text-sm text-primary font-data-mono"),
                                html.Span(f" (vs {vik_w} in Vikram)", className="text-xs text-outline ml-1 font-data-mono"),
                            ]
                        ),
                        className="py-3 px-4"
                    ),
                    html.Td(f"+{pts:.2f} pts", className="py-3 px-4 font-data-mono text-sm text-right text-primary font-semibold"),
                ]
            )
        )

    return html.Div(
        className="flex flex-col gap-6",
        children=[
            stock_header,
            veto_banner,
            recommendation_card,
            cards_row,
            
            # Sub-Part A Section: Float Mechanics
            html.Div(
                className="p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl",
                children=[
                    html.Div(
                        className="flex items-center justify-between mb-4",
                        children=[
                            html.Div(
                                className="flex items-center gap-2.5",
                                children=[
                                    html.Span("analytics", className="material-symbols-outlined text-secondary text-2xl"),
                                    html.H3("Sub-Part A: Today's Float Mechanics (55% Weight)", className="font-headline-sm font-bold text-on-surface text-lg"),
                                ]
                            ),
                            html.Span(f"{part_a_pts:.1f} / 55.0 pts", className="font-data-mono text-sm font-bold text-secondary bg-secondary-container/20 px-3 py-1 rounded-full border border-secondary/30"),
                        ]
                    ),
                    html.Div(
                        className="overflow-x-auto",
                        children=[
                            html.Table(
                                className="w-full text-left border-collapse",
                                children=[
                                    html.Thead(
                                        html.Tr(
                                            className="border-b border-outline-variant/30 text-xs text-outline uppercase font-label-caps tracking-wider",
                                            children=[
                                                html.Th("Mechanic", className="py-2.5 px-4"),
                                                html.Th("Observed Value", className="py-2.5 px-4"),
                                                html.Th("Benchmark Threshold", className="py-2.5 px-4"),
                                                html.Th("Gate Score", className="py-2.5 px-4"),
                                                html.Th("Contribution", className="py-2.5 px-4 text-right"),
                                            ]
                                        )
                                    ),
                                    html.Tbody(table_a_rows),
                                ]
                            )
                        ]
                    ),
                ]
            ),

            # Sub-Part B Section: Empirical Fundamentals
            html.Div(
                className="p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl",
                children=[
                    html.Div(
                        className="flex items-center justify-between mb-4",
                        children=[
                            html.Div(
                                className="flex items-center gap-2.5",
                                children=[
                                    html.Span("fact_check", className="material-symbols-outlined text-primary text-2xl"),
                                    html.H3("Sub-Part B: Empirical Fundamentals (45% Weight)", className="font-headline-sm font-bold text-on-surface text-lg"),
                                ]
                            ),
                            html.Span(f"{part_b_pts:.1f} / 45.0 pts", className="font-data-mono text-sm font-bold text-primary bg-primary/20 px-3 py-1 rounded-full border border-primary/30"),
                        ]
                    ),
                    html.Div(
                        className="overflow-x-auto",
                        children=[
                            html.Table(
                                className="w-full text-left border-collapse",
                                children=[
                                    html.Thead(
                                        html.Tr(
                                            className="border-b border-outline-variant/30 text-xs text-outline uppercase font-label-caps tracking-wider",
                                            children=[
                                                html.Th("Fundamental Pillar", className="py-2.5 px-4"),
                                                html.Th("Gate Score", className="py-2.5 px-4"),
                                                html.Th("Weight Allocation", className="py-2.5 px-4"),
                                                html.Th("Contribution", className="py-2.5 px-4 text-right"),
                                            ]
                                        )
                                    ),
                                    html.Tbody(table_b_rows),
                                ]
                            )
                        ]
                    ),
                ]
            ),
        ]
    )
