import os
import dash
from dash import html, dcc, Input, Output, callback
from dash_iconify import DashIconify
import pandas as pd
from functools import lru_cache

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


def _load_available_symbols():
    syms = []
    for path in (RANKED_SIGNALS_FILE, LEGACY_WATCHLIST_FILE):
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                col = "SYMBOL" if "SYMBOL" in df.columns else ("Symbol" if "Symbol" in df.columns else None)
                if col:
                    for s in df[col].dropna().astype(str).str.upper().unique():
                        if s and s not in syms:
                            syms.append(s)
            except Exception:
                pass
    if not syms:
        syms = ["JOJO", "NATFIT", "GGAUTO", "PAYTM", "SAKSOFT", "GREENPLY", "EMAMILTD"]
    return sorted(syms)


def _get_signal_row(symbol):
    sym = str(symbol).upper().strip()
    for path in (RANKED_SIGNALS_FILE, LEGACY_WATCHLIST_FILE):
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
        # Page Title Banner
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
                # Stock Selector
                html.Div(
                    className="flex items-center gap-3 w-full md:w-auto",
                    children=[
                        html.Label("Target Stock:", className="font-label-caps text-xs text-on-surface-variant whitespace-nowrap uppercase tracking-wider"),
                        dcc.Dropdown(
                            id="momentum-stock-selector",
                            options=[{"label": s, "value": s} for s in _load_available_symbols()],
                            value=_load_available_symbols()[0] if _load_available_symbols() else "JOJO",
                            clearable=False,
                            className="w-48 text-sm font-data-mono bg-surface-container-low text-on-surface border-outline-variant",
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
        return html.Div("Please select a stock.", className="text-on-surface-variant p-8 text-center")

    sym = str(symbol).upper().strip()
    fund = _fetcher.fetch(sym) or {}
    signal_row = _get_signal_row(sym)

    vikram_res = _vikram_scorer.score(fund)
    momentum_res = _momentum_scorer.score(signal_row, fund)

    # 1. Global Veto Status Banner
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
                            "Empirical Rule: Micro/small-cap breakouts with active vetoes (pledge >25% or FCF divergence) suffer severe multi-week decay. Tactical momentum entry is blocked.",
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
                                html.Span(" • Zero promoter pledge & verified 3-year cash flow conversion.", className="text-xs text-on-surface-variant ml-2"),
                            ]
                        ),
                    ]
                ),
                html.Span("✅ PASS", className="px-3 py-1 rounded-full text-xs font-bold font-data-mono bg-secondary/20 text-secondary border border-secondary/30"),
            ]
        )

    # 2. Dual-Engine Scores Summary Cards
    vikram_score = vikram_res.get("score")
    vikram_rating = vikram_res.get("rating", "UNAVAILABLE")
    
    mom_score = momentum_res.get("momentum_score", 0)
    mom_tier = momentum_res.get("momentum_tier", "WEAK")
    part_a_pts = momentum_res.get("part_a_contrib", 0.0)
    part_b_pts = momentum_res.get("part_b_contrib", 0.0)

    # Tier color styling
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
                                            html.H4("Vikram 5-Metric Scorer", className="font-headline-sm font-bold text-on-surface text-base"),
                                            html.Span("Baseline Quality Gatekeeper", className="font-label-caps text-xs text-outline"),
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
                        "Evaluates long-term operational health: Op-Lev (30%), Pledge (25%), FCF Quality (20%), Interest Coverage (20%), RoICE (5%).",
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
                                            html.H4("Momentum Score", className="font-headline-sm font-bold text-on-surface text-base"),
                                            html.Span("Tactical Entry & Float Squeeze Trigger", className="font-label-caps text-xs text-outline"),
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
                        "Measures institutional cornering velocity today: Float Mechanics (55% weight) combined with Live Ledger Winner Weights (45% weight).",
                        className="text-xs text-on-surface-variant mt-2 leading-relaxed",
                    ),
                ]
            ),
        ]
    )

    # 3. Sub-Part A Breakdown Table: Float Mechanics (55%)
    part_a_data = momentum_res.get("part_a_breakdown", {})
    table_a_rows = []
    
    metric_labels_a = [
        ("delivery_pct", "Delivery %", "Institutional accumulation ratio"),
        ("delivery_turnover", "Delivery Turnover", "Optimal micro-cap volume (sweet spot ₹3.5–5.0 Cr)"),
        ("float_absorbed", "Daily Float Absorbed %", "Depletion of freely floating shares (>1.5%)"),
        ("intraday_mae", "Intraday MAE (Max Dip)", "Buyer defense strength (no intraday dip > -1.8%)"),
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
                            html.Div(desc, className="text-xs text-outline"),
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

    # 4. Sub-Part B Breakdown Table: Empirical Fundamentals (45%)
    part_b_data = momentum_res.get("part_b_breakdown", {})
    table_b_rows = []

    metric_labels_b = [
        ("fcf_quality", "FCF / PAT Cash Quality", "30%", "20%", "Cash conversion is #1 truth engine of multi-bagger runners"),
        ("pledge_trend", "Promoter Pledge Trend", "30%", "25%", "100% of clean small-cap breakout winners had 0.00% pledge"),
        ("interest_coverage", "Interest Coverage Solvency", "25%", "20%", "Solvency buffer to eliminate small-cap credit distress traps"),
        ("op_leverage", "Operating Leverage", "10%", "30%", "Demoted from 38% — entry-day noise, descriptive not predictive"),
        ("roice", "RoICE Delta %", "5%", "5%", "Noise reduction for lumpy small-cap capex cycles"),
    ]

    for key, name, mom_w, vik_w, rationale in metric_labels_b:
        m_info = part_b_data.get(key, {})
        score_val = m_info.get("gate_score")
        score_str = f"{score_val}/10" if score_val is not None else "N/A"
        pts = m_info.get("pts", 0.0)

        badge_color = "text-secondary bg-secondary-container/20 border-secondary/40" if (score_val or 0) >= 8 else (
            "text-[#FFB300] bg-[#FFB300]/15 border-[#FFB300]/30" if (score_val or 0) >= 5 else "text-error bg-error-container/20 border-error/30"
        )

        table_b_rows.append(
            html.Tr(
                className="border-b border-outline-variant/20 hover:bg-white/[0.02] transition-colors",
                children=[
                    html.Td(
                        className="py-3 px-4",
                        children=[
                            html.Div(name, className="font-bold text-sm text-on-surface"),
                            html.Div(rationale, className="text-xs text-outline"),
                        ]
                    ),
                    html.Td(
                        html.Span(score_str, className=f"px-2 py-0.5 rounded text-xs font-bold font-data-mono border {badge_color}"),
                        className="py-3 px-4"
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

    # 5. Composite Actionable Recommendation Banner
    if is_vetoed:
        rec_title = "🚫 EXECUTION BLOCKED"
        rec_desc = f"Hard veto triggered ({veto_reasons[0] if veto_reasons else 'governance/cash divergence'}). Do not initiate any position."
        rec_style = "border-error/40 bg-error-container/20 text-error"
    elif mom_score >= 85 and (vikram_score or 0) >= 70:
        rec_title = "🟢 ELITE CONVICTION SETUP — MAXIMUM ALLOCATION"
        rec_desc = "All three gates aligned: Veto Clear + Pristine Vikram Fundamentals + Institutional Float Cornering (>1.5% absorbed). Prime tactical execution candidate."
        rec_style = "border-secondary/50 bg-secondary-container/20 text-secondary"
    elif mom_score >= 70 and (vikram_score or 0) >= 45:
        rec_title = "🔵 HIGH CONVICTION SETUP — STANDARD ALLOCATION"
        rec_desc = "Strong float accumulation backed by acceptable solvency. Trail winners using trailing ATR chandelier exits."
        rec_style = "border-[#38bdf8]/40 bg-[#38bdf8]/10 text-[#38bdf8]"
    elif mom_score >= 55:
        rec_title = "🟡 MODERATE SETUP — WATCHLIST / REDUCED SIZING"
        rec_desc = "Partial float mechanics detected or slower turnover velocity. Wait for clean consolidation breakout."
        rec_style = "border-[#FFB300]/40 bg-[#FFB300]/10 text-[#FFB300]"
    else:
        rec_title = "🔴 WEAK SETUP — SKIP ENTRY"
        rec_desc = "Insufficient float cornering volume or weak fundamental scoring. Do not allocate capital."
        rec_style = "border-outline-variant/50 bg-white/5 text-outline"

    recommendation_card = html.Div(
        className=f"p-6 rounded-2xl border {rec_style} flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-xl",
        children=[
            html.Div(
                children=[
                    html.H3(rec_title, className="font-headline-sm font-bold tracking-wide text-lg"),
                    html.P(rec_desc, className="text-sm font-body-md text-on-surface mt-1"),
                ]
            ),
            html.Div(
                className="flex items-center gap-2 font-data-mono text-xs font-bold px-3 py-1.5 rounded-lg bg-black/40 border border-white/10 text-on-surface whitespace-nowrap",
                children=[
                    html.Span("PRO-SPIKE DUAL-ENGINE v3"),
                ]
            ),
        ]
    )

    return html.Div(
        className="flex flex-col gap-6",
        children=[
            veto_banner,
            cards_row,
            
            # Sub-Part A Section
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
                                                html.Th("Threshold Benchmark", className="py-2.5 px-4"),
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

            # Sub-Part B Section
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

            recommendation_card,
        ]
    )
