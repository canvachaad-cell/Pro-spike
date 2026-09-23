"""
Winner Archetypes Dashboard Page (/winner-archetypes)
=====================================================
Built for Pro-Spike Indian Equities Quantitative Trading Platform.
Features:
1. Top KPI HUD: 80% Win-Rate Quality Meter (Rule 3)
2. Segmented Archetype Switcher: Clean Runners vs Grind Compounders (5-Zone Cards)
3. 14-Day Outcome-Conditional Re-Entry Radar: Emerald Streaks vs Amber Post-Loss Lockouts
"""

import dash
from dash import html, dcc, Input, Output, callback
import pandas as pd
import numpy as np
import winner_archetype_data as wad

dash.register_page(
    __name__,
    path="/winner-archetypes",
    name="Winner Archetypes",
    title="Pro Spike — Winner Archetypes",
    description="80% quality cohort: tier-conditional ATR gate · DELIV_PER ≤ 80 · verified ₹62,985",
)

# Tab styling matching institutional_signals.py
TAB_STYLE = {
    "background": "rgba(255,255,255,0.03)",
    "border": "1px solid rgba(255,255,255,0.08)",
    "borderRadius": "12px",
    "padding": "10px 18px",
    "marginRight": "8px",
    "marginBottom": "0",
    "color": "var(--text-secondary)",
    "fontWeight": "600",
    "fontSize": "13px",
    "letterSpacing": "0.02em",
    "minHeight": "44px",
    "display": "flex",
    "alignItems": "center",
    "whiteSpace": "nowrap",
    "flex": "0 0 auto",
    "width": "auto",
    "cursor": "pointer",
    "transition": "all 0.2s ease",
}

TAB_STYLE_SELECTED = {
    **TAB_STYLE,
    "background": "rgba(255,255,255,0.08)",
    "borderColor": "rgba(90,240,179,0.5)",
    "color": "var(--text-primary)",
    "boxShadow": "0 0 15px rgba(90,240,179,0.15)",
}

ARCHETYPE_STYLES = {
    "CLEAN_RUNNER": {
        "border": "rgba(90,240,179,0.35)",
        "badge_cls": "bg-primary/15 text-primary border-primary/40",
        "badge": "🏃 RUNNER",
        "route_icon": "bolt",
        "route_text": "2R Fixed TP · 4×ATR target · ~9-day resolution",
    },
    "GRIND_COMPOUNDER": {
        "border": "rgba(174,198,255,0.30)",
        "badge_cls": "bg-secondary/15 text-secondary border-secondary/40",
        "badge": "📈 COMPOUNDER",
        "route_icon": "timelapse",
        "route_text": "MOMENTUM_LOST exit · ≥10-day hold · bank green trims",
    },
    "UNCLASSIFIED": {
        "border": "rgba(255,255,255,0.08)",
        "badge_cls": "bg-white/10 text-on-surface-variant border-outline-variant/30",
        "badge": "⬜ SIGNAL",
        "route_icon": "analytics",
        "route_text": "Screened Signal — verify ATR & Delivery sweet spot before entry",
    },
}


# Helper UI Components
def _stat_tile(label, value, accent="text-on-surface", icon=None, sub_text=None):
    return html.Div(
        className="glass-panel rounded-2xl p-5 flex flex-col justify-between border border-white/5",
        children=[
            html.Div(
                className="flex items-center justify-between",
                children=[
                    html.Div(
                        label,
                        className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase tracking-widest",
                    ),
                    html.Span(
                        icon,
                        className="material-symbols-outlined text-[18px] text-on-surface-variant",
                    ) if icon else None,
                ],
            ),
            html.Div(
                str(value),
                className=f"font-headline-md text-[24px] font-semibold {accent} mt-2 tracking-tight",
            ),
            html.Div(
                sub_text,
                className="text-[11px] text-on-surface-variant mt-1 font-body-sm",
            ) if sub_text else None,
        ],
    )


def _tier_chip(mktcap_cr):
    try:
        v = float(mktcap_cr)
        if v < 2000:
            label, cls = "MICRO <₹2K Cr", "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
        elif v < 7000:
            label, cls = "SMALLISH <₹7K Cr", "bg-teal-500/10 text-teal-300 border-teal-500/30"
        elif v < 20000:
            label, cls = "MID <₹20K Cr", "bg-secondary/15 text-secondary border-secondary/30"
        else:
            label, cls = "LARGE", "bg-error/15 text-error border-error/30"
    except (TypeError, ValueError):
        label, cls = "TIER: N/A", "border-dashed border-outline-variant/40 text-on-surface-variant"

    return html.Span(
        label,
        className=f"text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border {cls} whitespace-nowrap",
    )


def _empty_panel(msg):
    return html.Div(
        className="col-span-full glass-panel rounded-2xl p-12 text-center flex flex-col items-center justify-center gap-3 border border-white/5",
        children=[
            html.Span("inventory_2", className="material-symbols-outlined text-[36px] text-on-surface-variant"),
            html.P(msg, className="text-on-surface-variant text-sm font-body-md"),
        ],
    )


# Tier 1: KPI HUD
def _kpi_hud(signals_df, radar_df):
    total_signals = len(signals_df) if signals_df is not None else 0
    source_name = "Ranked Universe" if (signals_df is not None and not signals_df.empty and signals_df.get("SOURCE_NAME", pd.Series()).iloc[0] == "Ranked Universe") else "Watchlist Fallback"

    # Quality count
    if signals_df is not None and not signals_df.empty and "QUALITY_80" in signals_df.columns:
        quality_count = int(signals_df["QUALITY_80"].sum())
    else:
        quality_count = 0

    # Radar stats
    if radar_df is not None and not radar_df.empty:
        locked_count = int((radar_df["RADAR_STATE"] == "LOCKED").sum())
        streak_count = int((radar_df["RADAR_STATE"] == "STREAK").sum())
    else:
        locked_count = 0
        streak_count = 0

    as_of_str = pd.Timestamp.now().strftime("%d %b %Y")

    return html.Section(
        className="w-full",
        children=[
            html.Div(
                className="glass-panel rounded-2xl p-6 mb-6 border border-white/10 shadow-xl",
                children=[
                    # Header row
                    html.Div(
                        className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6",
                        children=[
                            html.Div(
                                children=[
                                    html.Div(
                                        className="flex items-center gap-3",
                                        children=[
                                            html.H1(
                                                "Winner Archetypes",
                                                className="font-display-lg text-[30px] md:text-[36px] font-bold text-on-surface tracking-tight",
                                            ),
                                            html.Span(
                                                "80% WIN RATE QUALITY GATE",
                                                className="hidden sm:inline-block bg-primary/10 text-primary border border-primary/30 text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full",
                                            ),
                                        ],
                                    ),
                                    html.P(
                                        "SBIA Alpha Engine · Rule 3: tier ≠ LARGE (<₹20K Cr) · DELIV ≤ 80% · Tier-Conditional ATR (MID ≥ 3.15%)",
                                        className="font-body-md text-on-surface-variant text-sm mt-1",
                                    ),
                                ]
                            ),
                            html.Div(
                                className="flex items-center gap-2 flex-wrap",
                                children=[
                                    html.Span(
                                        f"🏆 {source_name}",
                                        className="bg-secondary/10 text-secondary border border-secondary/30 text-[11px] font-semibold px-3 py-1 rounded-full whitespace-nowrap",
                                    ),
                                    html.Span(
                                        f"📅 {as_of_str}",
                                        className="bg-white/5 text-on-surface-variant border border-white/10 text-[11px] font-mono px-3 py-1 rounded-full whitespace-nowrap",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # Stat Tiles Grid
                    html.Div(
                        className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5",
                        children=[
                            _stat_tile(
                                "Universe Scored",
                                f"{total_signals:,}",
                                accent="text-secondary",
                                icon="filter_list",
                                sub_text="full equities coverage",
                            ),
                            _stat_tile(
                                "80% Quality Tier",
                                f"{quality_count:,}",
                                accent="text-primary",
                                icon="emoji_events",
                                sub_text="passes Rule 3 filter",
                            ),
                            _stat_tile(
                                "Post-Loss Blocked",
                                f"{locked_count}",
                                accent="text-error",
                                icon="lock",
                                sub_text="14-day outcome lockout",
                            ),
                            _stat_tile(
                                "Winning Streaks",
                                f"{streak_count}",
                                accent="text-primary",
                                icon="local_fire_department",
                                sub_text="re-entry allowed ✓",
                            ),
                        ],
                    ),
                    # Rule Pills & Grounded Caption
                    html.Div(
                        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-white/5",
                        children=[
                            html.Div(
                                className="flex flex-wrap items-center gap-2",
                                children=[
                                    html.Span(
                                        "Rule 3 Specification:",
                                        className="text-[11px] font-bold text-on-surface uppercase tracking-wider mr-1",
                                    ),
                                    html.Span(
                                        "⚙️ tier ≠ LARGE (<₹20K Cr)",
                                        className="bg-white/5 border border-white/10 text-on-surface text-[10px] font-mono px-2.5 py-1 rounded-lg",
                                    ),
                                    html.Span(
                                        "⚙️ MID → ATR% ≥ 3.15%",
                                        className="bg-white/5 border border-white/10 text-on-surface text-[10px] font-mono px-2.5 py-1 rounded-lg",
                                    ),
                                    html.Span(
                                        "⚙️ MICRO / SMALLISH → Ungated",
                                        className="bg-white/5 border border-white/10 text-emerald-300 text-[10px] font-mono px-2.5 py-1 rounded-lg",
                                    ),
                                    html.Span(
                                        "✅ DELIV_PER ≤ 80%",
                                        className="bg-primary/10 border border-primary/30 text-primary text-[10px] font-mono px-2.5 py-1 rounded-lg",
                                    ),
                                ],
                            ),
                            html.Div(
                                "Verified: 80.0% win · 0.840R · +₹62,985 PnL · n=25 [MID=11 SMALLISH=9 MICRO=5]",
                                className="text-[11px] text-on-surface-variant/80 italic font-mono",
                            ),
                        ],
                    ),
                ],
            )
        ],
    )


# 5-Zone Ticker Card
def _ticker_card(row):
    sym = str(row.get("SYMBOL", "UNKNOWN")).strip()
    exch = str(row.get("EXCHANGE", "NSE")).strip()
    close_val = float(row.get("CLOSE", 0.0)) if pd.notna(row.get("CLOSE")) else 0.0

    archetype = str(row.get("ARCHETYPE", "UNCLASSIFIED")).strip()
    style_spec = ARCHETYPE_STYLES.get(archetype, ARCHETYPE_STYLES["UNCLASSIFIED"])
    is_quality = bool(row.get("QUALITY_80", False))
    deliv_grade = str(row.get("DELIV_GRADE", "UNKNOWN")).strip()

    # Zone 1: Symbol Line
    symbol_line = html.Div(
        className="flex justify-between items-start gap-2",
        children=[
            html.Div(
                children=[
                    html.Span(
                        sym,
                        className="font-headline-md text-[22px] md:text-[24px] font-bold text-on-surface tracking-tight block",
                    ),
                    html.Span(
                        f"{exch} · ₹{close_val:,.2f}",
                        className="font-mono text-[12px] text-on-surface-variant mt-0.5 block",
                    ),
                ]
            ),
            html.Div(
                className="flex flex-wrap gap-1.5 justify-end items-center max-w-[65%]",
                children=[
                    html.Span(
                        style_spec["badge"],
                        className=f"text-[9px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full border {style_spec['badge_cls']}",
                    ),
                    html.Span(
                        "🏆 80% TIER",
                        className="bg-primary/15 text-primary border border-primary/40 text-[9px] font-bold uppercase tracking-widest px-2 py-1 rounded-full",
                    ) if is_quality else None,
                    html.Span(
                        deliv_grade,
                        className="bg-secondary/15 text-secondary border border-secondary/30 text-[9px] font-bold uppercase tracking-widest px-2 py-1 rounded-full",
                    ) if deliv_grade in ("A-GRADE", "B-GRADE") else None,
                    _tier_chip(row.get("MKTCAP_CR")),
                ],
            ),
        ],
    )

    # Zone 2: Risk / Reward Range Bar
    sl_val = float(row.get("STOP_LOSS", close_val * 0.95))
    tp_val = float(row.get("TAKE_PROFIT", close_val * 1.10))
    entry_val = float(row.get("ENTRY_PRICE", close_val))

    span = tp_val - sl_val if tp_val > sl_val else 1.0
    entry_fill = min(max((entry_val - sl_val) / span * 100, 5), 90)
    curr_fill = min(max((close_val - sl_val) / span * 100, 0), 100)

    range_bar = html.Div(
        className="flex flex-col gap-1.5 bg-black/20 p-2.5 rounded-xl border border-white/5",
        children=[
            html.Div(
                className="relative h-2 rounded-full bg-white/10 overflow-hidden",
                children=[
                    # Red risk zone
                    html.Div(
                        style={"width": f"{entry_fill}%"},
                        className="absolute left-0 top-0 h-full bg-gradient-to-r from-error/60 to-error/20",
                    ),
                    # Green reward zone
                    html.Div(
                        style={"left": f"{entry_fill}%", "width": f"{100 - entry_fill}%"},
                        className="absolute top-0 h-full bg-gradient-to-r from-primary/20 to-primary/60",
                    ),
                    # Current price tick
                    html.Div(
                        style={"left": f"{curr_fill}%"},
                        className="absolute top-0 w-1.5 h-full bg-white -translate-x-1/2 shadow-[0_0_8px_rgba(255,255,255,0.9)] rounded-full",
                    ),
                ],
            ),
            html.Div(
                className="flex justify-between items-center text-[10px] font-mono text-on-surface-variant px-0.5",
                children=[
                    html.Span(f"SL ₹{sl_val:,.1f}", className="text-error font-medium"),
                    html.Span(f"ENTRY ₹{entry_val:,.1f}", className="text-on-surface-variant"),
                    html.Span(f"TP ₹{tp_val:,.1f}", className="text-primary font-medium"),
                ],
            ),
        ],
    )

    # Zone 3: Metric Badge Row
    atr_pct = float(row.get("ATR_PCT", 0.0)) if pd.notna(row.get("ATR_PCT")) else 0.0
    atr_color = "text-primary" if atr_pct >= 3.15 else "text-on-surface-variant"

    deliv_per = float(row.get("DELIV_PER", 0.0)) if pd.notna(row.get("DELIV_PER")) else 0.0
    deliv_color = "text-primary" if deliv_per < 65.0 else ("text-secondary" if deliv_per <= 80.0 else "text-amber-400")

    whd = float(row.get("Whale_Density", 0.0)) if pd.notna(row.get("Whale_Density")) else 0.0
    whd_color = "text-secondary" if whd >= 12.0 else "text-on-surface-variant"

    badge_row = html.Div(
        className="grid grid-cols-3 gap-2",
        children=[
            html.Div(
                className="bg-white/5 rounded-xl p-2.5 flex flex-col gap-0.5 border border-white/5",
                children=[
                    html.Div("ATR14 %", className="text-[9px] uppercase tracking-widest text-on-surface-variant font-bold"),
                    html.Div(f"{atr_pct:.2f}%" if atr_pct > 0 else "—", className=f"text-[14px] font-mono font-semibold {atr_color}"),
                ],
            ),
            html.Div(
                className="bg-white/5 rounded-xl p-2.5 flex flex-col gap-0.5 border border-white/5",
                children=[
                    html.Div("DELIVERY %", className="text-[9px] uppercase tracking-widest text-on-surface-variant font-bold"),
                    html.Div(f"{deliv_per:.1f}%" if deliv_per > 0 else "—", className=f"text-[14px] font-mono font-semibold {deliv_color}"),
                ],
            ),
            html.Div(
                className="bg-white/5 rounded-xl p-2.5 flex flex-col gap-0.5 border border-white/5",
                children=[
                    html.Div("WHALE DENSITY", className="text-[9px] uppercase tracking-widest text-on-surface-variant font-bold"),
                    html.Div(f"{whd:.1f}x" if whd > 0 else "—", className=f"text-[14px] font-mono font-semibold {whd_color}"),
                ],
            ),
        ],
    )

    # Zone 4: AI Win Probability Bar
    ai_prob = float(row.get("AI_WIN_PROBABILITY", 55.0))
    prob_accent = "bg-primary" if ai_prob >= 75.0 else ("bg-secondary" if ai_prob >= 60.0 else "bg-on-surface-variant/60")
    prob_text_accent = "text-primary" if ai_prob >= 75.0 else ("text-secondary" if ai_prob >= 60.0 else "text-on-surface-variant")

    ai_bar = html.Div(
        className="flex items-center gap-3 px-1",
        children=[
            html.Span("AI WIN PROB", className="text-[9px] uppercase tracking-widest text-on-surface-variant font-bold whitespace-nowrap"),
            html.Div(
                className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden",
                children=[
                    html.Div(
                        style={"width": f"{min(ai_prob, 100)}%"},
                        className=f"h-full rounded-full {prob_accent}",
                    )
                ],
            ),
            html.Span(f"{ai_prob:.0f}%", className=f"font-mono text-[12px] font-semibold {prob_text_accent}"),
        ],
    )

    # Zone 5: Execution Route Footer
    exec_route = html.Div(
        className="flex items-center gap-2 border-t border-white/10 pt-3 mt-1",
        children=[
            html.Span(
                style_spec["route_icon"],
                className="material-symbols-outlined text-[16px] text-primary flex-shrink-0",
            ),
            html.Span(
                style_spec["route_text"],
                className="text-[11px] font-medium text-on-surface-variant leading-tight",
            ),
        ],
    )

    return html.Article(
        className="glass-panel rounded-2xl p-5 flex flex-col gap-4 border transition-all duration-200 ease-in-out hover:shadow-[0_0_24px_rgba(174,198,255,0.12)] hover:scale-[1.01]",
        style={"borderColor": style_spec["border"]},
        tabIndex="0",
        role="article",
        **{"aria-label": f"{sym} {archetype} signal card"},
        children=[
            symbol_line,
            range_bar,
            badge_row,
            ai_bar,
            exec_route,
        ],
    )


# Tier 2: Archetype Switcher Shell
def _archetype_switcher_shell():
    tabs = dcc.Tabs(
        id="archetype-tabs",
        value="QUALITY",
        children=[
            dcc.Tab(label="🏆 80% Quality Cohort", value="QUALITY", style=TAB_STYLE, selected_style=TAB_STYLE_SELECTED),
            dcc.Tab(label="🏃 Clean Breakout Runners", value="CLEAN_RUNNER", style=TAB_STYLE, selected_style=TAB_STYLE_SELECTED),
            dcc.Tab(label="📈 Grind Compounders", value="GRIND_COMPOUNDER", style=TAB_STYLE, selected_style=TAB_STYLE_SELECTED),
            dcc.Tab(label="⬜ All Screened Signals", value="ALL", style=TAB_STYLE, selected_style=TAB_STYLE_SELECTED),
        ],
        style={"border": "none", "background": "transparent"},
        colors={"border": "transparent", "primary": "transparent", "background": "transparent"},
    )

    return html.Section(
        className="w-full flex flex-col gap-5",
        children=[
            html.Div(
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3",
                children=[
                    html.Div(
                        children=[
                            html.H2(
                                "Execution Archetype Switcher",
                                className="font-headline-lg text-[22px] font-bold text-on-surface tracking-tight",
                            ),
                            html.P(
                                "Segmented execution routes: 2R Fixed TP for Clean Runners vs 10-Day Momentum Bank for Compounders.",
                                className="text-on-surface-variant text-sm font-body-md",
                            ),
                        ]
                    ),
                ],
            ),
            html.Div(
                className="overflow-x-auto pb-1 flex",
                children=[tabs],
            ),
            html.Div(
                id="archetype-card-grid",
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5",
                children=[_empty_panel("Loading signals...")],
            ),
        ],
    )


# Tier 3: 14-Day Re-Entry Radar Table
def _reentry_radar(radar_df):
    if radar_df is None or radar_df.empty:
        return html.Section(
            className="w-full mt-6",
            children=[
                html.Div(
                    className="glass-panel rounded-2xl p-6 border border-white/5",
                    children=[
                        html.H2("14-Day Re-Entry Radar", className="font-headline-lg text-[22px] font-bold text-on-surface mb-2"),
                        html.P("No historical closed trades found in ledger.", className="text-on-surface-variant text-sm"),
                    ],
                )
            ],
        )

    # Sub-groups
    locked_group = radar_df[radar_df["RADAR_STATE"] == "LOCKED"]
    streak_group = radar_df[radar_df["RADAR_STATE"] == "STREAK"]
    open_group = radar_df[radar_df["RADAR_STATE"] == "OPEN"]
    eligible_group = radar_df[radar_df["RADAR_STATE"] == "ELIGIBLE"].head(20)

    def _render_table_group(title, sub, count, df_sub, theme="neutral"):
        if df_sub.empty:
            return None

        theme_styles = {
            "amber": {
                "container_cls": "border-l-4 border-amber-500 bg-amber-500/5",
                "badge_cls": "bg-amber-500/20 text-amber-300 border-amber-500/40",
                "icon": "lock",
                "action_text": "Do not re-enter (86.7% failure rate)",
                "action_cls": "text-amber-400 italic text-[11px]",
            },
            "emerald": {
                "container_cls": "border-l-4 border-emerald-500 bg-emerald-500/5",
                "badge_cls": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
                "icon": "local_fire_department",
                "action_text": "Re-entry permitted ✓ (+6.6R edge)",
                "action_cls": "text-emerald-300 font-semibold text-[11px]",
            },
            "blue": {
                "container_cls": "border-l-4 border-secondary bg-secondary/5",
                "badge_cls": "bg-secondary/20 text-secondary border-secondary/40",
                "icon": "pause_circle",
                "action_text": "Active position — max 1 trade enforced",
                "action_cls": "text-on-surface-variant italic text-[11px]",
            },
            "neutral": {
                "container_cls": "border-l-4 border-white/20 bg-white/5",
                "badge_cls": "bg-white/10 text-on-surface-variant border-outline-variant/30",
                "icon": "lock_open",
                "action_text": "Monitor for fresh setup",
                "action_cls": "text-on-surface-variant italic text-[11px]",
            },
        }

        th = theme_styles.get(theme, theme_styles["neutral"])

        header_row = html.Div(
            className="grid grid-cols-12 px-4 py-2.5 font-label-caps text-[11px] font-bold text-on-surface-variant uppercase tracking-wider border-b border-white/5",
            children=[
                html.Div("Ticker", className="col-span-3"),
                html.Div("Last Closed Status", className="col-span-3"),
                html.Div("Days Since Exit", className="col-span-2 text-right"),
                html.Div("Radar State", className="col-span-2 text-center"),
                html.Div("Action Advisory", className="col-span-2 text-right"),
            ],
        )

        rows = []
        for _, r in df_sub.iterrows():
            sym = str(r.get("SYMBOL", ""))
            status = str(r.get("STATUS", ""))
            days = r.get("days_since_exit", 0)
            days_str = f"{days}d ago" if days < 900 else "Recent"

            # Status badge
            if status == "HIT_TP":
                st_cls = "bg-primary/15 text-primary border-primary/30"
            elif status == "HIT_SL":
                st_cls = "bg-error/15 text-error border-error/30"
            else:
                st_cls = "bg-secondary/15 text-secondary border-secondary/30"

            radar_state = str(r.get("RADAR_STATE", ""))
            streak_cnt = r.get("WIN_STREAK", 0)
            state_label = f"🔥 {streak_cnt}× HIT_TP" if radar_state == "STREAK" else radar_state

            rows.append(
                html.Div(
                    className="grid grid-cols-12 px-4 py-3 items-center border-b border-white/5 hover:bg-white/5 transition-colors text-sm",
                    children=[
                        html.Div(
                            sym,
                            className="col-span-3 font-mono font-bold text-on-surface text-[13px]",
                        ),
                        html.Div(
                            className="col-span-3 flex items-center gap-1.5",
                            children=[
                                html.Span(
                                    status,
                                    className=f"text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border {st_cls}",
                                )
                            ],
                        ),
                        html.Div(
                            days_str,
                            className="col-span-2 text-right font-mono text-on-surface-variant text-[12px]",
                        ),
                        html.Div(
                            className="col-span-2 flex justify-center",
                            children=[
                                html.Span(
                                    state_label,
                                    className=f"text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full border {th['badge_cls']}",
                                )
                            ],
                        ),
                        html.Div(
                            th["action_text"],
                            className=f"col-span-2 text-right {th['action_cls']}",
                        ),
                    ],
                )
            )

        return html.Div(
            className=f"glass-panel rounded-2xl overflow-hidden mb-5 {th['container_cls']}",
            children=[
                html.Div(
                    className="p-4 flex items-center justify-between border-b border-white/5",
                    children=[
                        html.Div(
                            className="flex items-center gap-2",
                            children=[
                                html.Span(th["icon"], className="material-symbols-outlined text-[18px] text-on-surface"),
                                html.Span(title, className="font-headline-sm text-[15px] font-bold text-on-surface"),
                                html.Span(f"({count})", className="text-on-surface-variant text-xs font-mono"),
                            ],
                        ),
                        html.Span(sub, className="text-[11px] text-on-surface-variant italic"),
                    ],
                ),
                html.Div(
                    className="table-scroll-wrapper",
                    tabIndex="0",
                    **{"aria-label": f"{title} Table"},
                    children=[
                        html.Div(
                            style={"minWidth": "680px"},
                            children=[header_row] + rows,
                        )
                    ],
                ),
            ],
        )

    return html.Section(
        className="w-full mt-4 flex flex-col gap-4",
        children=[
            html.Div(
                children=[
                    html.H2(
                        "14-Day Outcome-Conditional Re-Entry Radar",
                        className="font-headline-lg text-[22px] font-bold text-on-surface tracking-tight",
                    ),
                    html.P(
                        "Asymmetric Re-Entry Edge: Block repeat trades after a LOSS (13.3% win, -₹26,368). Allow repeats immediately after a WIN (57.1% win, +₹19,914).",
                        className="text-on-surface-variant text-sm font-body-md mt-0.5",
                    ),
                ]
            ),
            _render_table_group(
                "Locked Out: Post-Loss Blocked",
                "Prior closed trade was a loss — 86.7% fail rate",
                len(locked_group),
                locked_group,
                theme="amber",
            ),
            _render_table_group(
                "Winning Streaks: Re-Entry Permitted",
                "Prior trade banked 2R+ TP — +6.6R verified edge",
                len(streak_group),
                streak_group,
                theme="emerald",
            ),
            _render_table_group(
                "Position Active: Max 1 Enforced",
                "Currently in live ledger — do not stack duplicate entry",
                len(open_group),
                open_group,
                theme="blue",
            ),
            _render_table_group(
                "Eligible Universe (Recent Exits)",
                "No outcome-based lockout active",
                len(eligible_group),
                eligible_group,
                theme="neutral",
            ),
        ],
    )


# Interactive Callbacks
@callback(
    Output("archetype-card-grid", "children"),
    Input("archetype-tabs", "value"),
)
def update_card_grid(tab):
    df = wad.load_signals()
    if df is None or df.empty:
        return [_empty_panel("Run rank_archetypes.py to populate the ranked universe.")]

    if tab == "QUALITY":
        mask = df.get("QUALITY_80", pd.Series(False, index=df.index)).fillna(False).astype(bool)
        filtered = df[mask]
    elif tab == "ALL":
        filtered = df
    else:
        col = df.get("ARCHETYPE", pd.Series("UNCLASSIFIED", index=df.index))
        filtered = df[col == tab]

    if filtered.empty:
        empty_messages = {
            "QUALITY": "No symbols pass Rule 3 quality gate today.",
            "CLEAN_RUNNER": "No Clean Breakout Runners identified today.",
            "GRIND_COMPOUNDER": "No Grind Compounders identified today.",
            "ALL": "No screened signals available.",
        }
        return [_empty_panel(empty_messages.get(tab, "No signals found for this category."))]

    # Limit to top 30 to maintain high frame rate
    display_rows = filtered.head(30)
    return [_ticker_card(row) for _, row in display_rows.iterrows()]


# Page Layout Assembly
def layout():
    signals_df = wad.load_signals()
    ledger_raw = wad._load(wad.SBIA_LEDGER)
    today = pd.Timestamp.now().normalize()
    radar_df = wad.build_radar_df(ledger_raw, today) if ledger_raw is not None else pd.DataFrame()

    return html.Div(
        className="flex flex-col w-full px-[16px] md:px-[24px] py-[24px] max-w-[1600px] mx-auto gap-8",
        children=[
            _kpi_hud(signals_df, radar_df),
            _archetype_switcher_shell(),
            _reentry_radar(radar_df),
        ],
    )
