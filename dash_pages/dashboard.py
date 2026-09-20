import dash
from dash import html, dcc, Input, Output
import pandas as pd
import os
from functools import lru_cache

from fundamental_fetcher import FundamentalFetcher, CACHE_PATH as FUND_CACHE_PATH
from conviction_scorer import ConvictionScorer

dash.register_page(__name__, path='/', name='Dashboard', title='Pro Spike - Dashboard')

FALLBACK_TOTAL_SCANNED = 5518
FALLBACK_NSE = 2543
FALLBACK_BSE = 2975

@lru_cache(maxsize=1)
def load_universe_stats():
    """Derive universe counts from the live combined file (cached per process)."""
    try:
        df = pd.read_csv(os.path.join("data", "combined_dashboard_live.csv"), usecols=["EXCHANGE", "DATE"])
        nse = int((df["EXCHANGE"] == "NSE").sum())
        bse = int((df["EXCHANGE"] == "BSE").sum())
        as_of = pd.to_datetime(df["DATE"], errors="coerce").max()
        return len(df), nse, bse, as_of
    except Exception:
        return FALLBACK_TOTAL_SCANNED, FALLBACK_NSE, FALLBACK_BSE, None


@lru_cache(maxsize=1)
def load_t2t_map():
    """SYMBOL -> EVER_100_DELIV from the live universe file.

    The ranked signals CSV does not populate EVER_100_DELIV (all NaN), so the
    T2T status is cross-referenced from combined_dashboard_live.csv.
    """
    try:
        df = pd.read_csv(os.path.join("data", "combined_dashboard_live.csv"), usecols=["SYMBOL", "EVER_100_DELIV"])
        return dict(zip(df["SYMBOL"], df["EVER_100_DELIV"]))
    except Exception:
        return {}


def load_latest_signals():
    """Read survivors_archive.csv and keep ONLY the latest date's signals.

    This ensures 12-condition signal parity with the Streamlit dashboard.
    """
    path = os.path.join("data", "survivors_archive.csv")
    if not os.path.exists(path):
        return pd.DataFrame(), None
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(), None
    if "DATE" in df.columns:
        dates = pd.to_datetime(df["DATE"], errors="coerce")
        if dates.notna().any():
            latest = dates.max()
            return df[dates == latest].copy(), latest
    return df, None


def format_turnover(deliv_turn):
    """Consistent Indian formatting: Crores / Lakhs / raw rupees."""
    if deliv_turn >= 10000000:
        return f"₹ {deliv_turn / 10000000:.2f}Cr"
    if deliv_turn >= 100000:
        return f"₹ {deliv_turn / 100000:.2f}L"
    return f"₹ {deliv_turn:,.0f}"


_fetcher = FundamentalFetcher()
_scorer = ConvictionScorer()

_CLASS_PILL = {
    "S": "bg-[#e74c3c]/15 text-[#e74c3c] border-[#e74c3c]/30",
    "M": "bg-[#FFB300]/15 text-[#FFB300] border-[#FFB300]/30",
    "L": "bg-[#38bdf8]/15 text-[#38bdf8] border-[#38bdf8]/30",
    "U": "bg-white/5 text-on-surface-variant border-outline-variant/50",
}
_CLASS_TITLE = {
    "S": "Small cap (<₹500 Cr mcap) — momentum sizing, Tier B vetoes apply",
    "M": "Mid cap (₹500–10,000 Cr mcap) — hybrid mode, full conviction score",
    "L": "Large cap (>₹10,000 Cr mcap) — rebalancing disclaimer, no score",
    "U": "Fundamentals unavailable — screener.in fetch failed",
}


@lru_cache(maxsize=64)
def _signal_badges(symbol, cache_mtime):
    """Class + conviction + veto badges for a signal card.

    cache_mtime (mtime of data/fundamental_cache.json) keys the lru cache so
    refreshed fundamentals produce fresh scores within a server session.
    """
    try:
        fund = _fetcher.fetch(symbol)
        res = _scorer.score(fund)
    except Exception:
        fund, res = {}, None
    if res is None:
        res = {"stock_class": "U", "veto": False, "score": None,
               "rating": "FUNDAMENTALS_UNAVAILABLE", "display_badge": "❓ Fundamentals unavailable",
               "veto_reasons": []}
    cls = res.get("stock_class", "U")
    badges = [
        html.Span(
            f"[{cls}]",
            title=_CLASS_TITLE.get(cls, ""),
            className=f"text-[9px] font-bold tracking-wider px-1.5 py-0.5 rounded-full border {_CLASS_PILL.get(cls, _CLASS_PILL['U'])}",
        )
    ]
    if res.get("veto"):
        reason = (res.get("veto_reasons") or ["fundamental veto"])[0]
        badges.append(html.Span(
            f"🚫 VETO: {reason}",
            className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-[#e74c3c]/20 text-[#ff6b6b] border border-[#e74c3c]/40",
        ))
        return badges
    display = res.get("display_badge") or "❓ Fundamentals unavailable"
    color = {
        "HIGH_CONVICTION": "text-[#2ecc71] border-[#2ecc71]/40 bg-[#2ecc71]/10",
        "MODERATE": "text-on-surface-variant border-outline-variant/60 bg-white/5",
        "LOW": "text-[#FFB300] border-[#FFB300]/40 bg-[#FFB300]/10",
        "LARGE_CAP_DISCLAIMER": "text-[#FFB300] border-[#FFB300]/40 bg-[#FFB300]/10",
        "FUNDAMENTALS_UNAVAILABLE": "text-on-surface-variant border-outline-variant/60 bg-white/5",
    }.get(res.get("rating"), "text-on-surface-variant border-outline-variant/60 bg-white/5")
    badges.append(html.Span(
        display,
        className=f"text-[9px] font-semibold px-1.5 py-0.5 rounded-full border {color}",
    ))
    return badges


def _badges_for(symbol):
    try:
        mtime = os.path.getmtime(FUND_CACHE_PATH)
    except OSError:
        mtime = 0
    return _signal_badges(str(symbol).upper(), mtime)


def build_signal_rows(df):
    """Render the top-10 signal cards for the dashboard preview."""
    rows = []
    for i, row in df.head(10).iterrows():
        sym = str(row.get("SYMBOL", "N/A"))
        exch = str(row.get("EXCHANGE", "N/A"))
        try:
            close = float(row.get("CLOSE", 0))
        except Exception:
            close = 0.0
        try:
            deliv_per = float(row.get("DELIV_PER", 0))
        except Exception:
            deliv_per = 0.0
        try:
            deliv_turn = float(row.get("DELIVERY_TURNOVER", 0))
        except Exception:
            deliv_turn = 0.0
        try:
            atw = float(row.get("ATW", 0))
        except Exception:
            atw = 0.0

        turnover_str = format_turnover(deliv_turn)

        # Exchange badge styling
        badge_bg = "bg-[#38bdf8]/15 text-[#38bdf8] border-[#38bdf8]/30" if exch.upper() == "NSE" else "bg-[#34d399]/20 text-[#34d399] border-[#34d399]/30"

        rows.append(html.Div(
            className="glass-panel p-4 rounded-xl mb-3 flex flex-wrap items-center justify-between gap-4 hover:-translate-y-1 hover:shadow-lg hover:shadow-primary/10 transition-all duration-300 cursor-pointer group relative z-10 hover:z-20",
            children=[
                # Left side: Symbol & Exchange
                html.Div(
                    className="flex items-center gap-4 min-w-[150px]",
                    children=[
                        html.Span(className="w-2.5 h-2.5 rounded-full bg-primary inline-block shadow-[0_0_8px_rgba(90,240,179,0.8)]"),
                        html.Div(
                            children=[
                                html.Div(sym, className="font-headline-sm text-lg font-semibold text-on-surface group-hover:text-primary transition-colors"),
                                html.Div(exch, className=f"text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full border {badge_bg} inline-block mt-1"),
                                html.Div(_badges_for(sym), className="flex items-center gap-1.5 mt-1.5 flex-wrap"),
                            ]
                        )
                    ]
                ),
                # Middle: Micro-chart (Sparkline representation)
                html.Div(
                    className="hidden md:flex flex-1 max-w-[120px] items-center gap-2",
                    children=[
                        html.Div("CLOSE", className="text-[10px] text-on-surface-variant font-label-caps"),
                        html.Div(f"{close:,.2f}", className="font-data-md text-on-surface font-medium"),
                        # Fake sparkline
                        html.Div(
                            className="flex items-end gap-0.5 h-6",
                            children=[
                                html.Div(className="w-1 bg-on-surface-variant/40 rounded-t-sm h-[30%]"),
                                html.Div(className="w-1 bg-on-surface-variant/40 rounded-t-sm h-[50%]"),
                                html.Div(className="w-1 bg-on-surface-variant/40 rounded-t-sm h-[40%]"),
                                html.Div(className="w-1 bg-on-surface-variant/40 rounded-t-sm h-[80%]"),
                                html.Div(className="w-1 bg-primary rounded-t-sm h-[100%] shadow-[0_0_4px_rgba(90,240,179,0.8)]"),
                            ]
                        )
                    ]
                ),
                # Right side: Stats
                html.Div(
                    className="flex items-center gap-6",
                    children=[
                        html.Div(
                            className="flex flex-col text-right hidden sm:flex",
                            children=[
                                html.Span("DELIVERY", className="text-[10px] text-on-surface-variant font-label-caps"),
                                html.Span(f"{deliv_per:.1f}%", className="font-data-md text-primary font-medium")
                            ]
                        ),
                        html.Div(
                            className="flex flex-col text-right",
                            children=[
                                html.Span("TURNOVER", className="text-[10px] text-on-surface-variant font-label-caps"),
                                html.Span(turnover_str, className="font-data-md text-on-surface font-medium")
                            ]
                        ),
                        html.Span("arrow_drop_down", className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors")
                    ]
                )
            ]
        ))
    return rows

def _filter_t2t(df, hide_t2t):
    """Filter T2T (100% delivery) stocks. Default ON — Streamlit parity.

    T2T status comes from the live universe map since the ranked CSV leaves
    EVER_100_DELIV as NaN. Unknown symbols are kept (only *known* T2T hidden).
    """
    if not hide_t2t:
        return df
    t2t_map = load_t2t_map()
    if not t2t_map:
        return df
    mask = df["SYMBOL"].map(lambda s: t2t_map.get(s) is True)
    return df[~mask]


def layout():
    total_scanned, nse_count, bse_count, as_of = load_universe_stats()
    as_of_str = as_of.strftime("%d %b %Y") if as_of is not None else "—"

    df_latest, latest_date = load_latest_signals()
    signals_asof = latest_date.strftime("%d %b %Y") if latest_date is not None else "—"

    if df_latest.empty:
        active_signals = 0
        signal_rows = [html.Div("No active signals today.", className="p-4 font-body-md text-outline text-center glass-panel rounded-xl")]
    else:
        df_display = _filter_t2t(df_latest, hide_t2t=True)
        active_signals = len(df_display)
        signal_rows = build_signal_rows(df_display)
        if active_signals == 0:
            signal_rows = [html.Div("All of today's signals are T2T (100% delivery) — toggle 'Hide T2T' off to view them.", className="p-4 font-body-md text-outline text-center glass-panel rounded-xl")]

    return html.Div(
        className="flex flex-col w-full px-[24px] py-[24px] max-w-[1600px] mx-auto",
        children=[
            # Header Row
            html.Header(
                className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 mb-8",
                children=[
                    html.Div([
                        html.H1(
                            className="font-display-lg text-[28px] md:text-[48px] leading-[1.2] md:leading-[56px] font-bold text-on-surface mb-2 tracking-tight",
                            children=[
                                html.Span("Pro Spike", className="block font-label-sm text-[12px] leading-[16px] font-bold text-primary tracking-widest uppercase mb-1"),
                                html.Span("Dashboard", className="block font-display-lg text-[28px] md:text-[48px] leading-[1.2] md:leading-[56px] font-bold text-on-surface tracking-tight")
                            ]
                        )
                    ]),
                    # Live Status Pill
                    html.Div(
                        className="relative flex items-center gap-3 px-4 py-2 rounded-full bg-primary/5 border border-primary/20 backdrop-blur-md overflow-hidden animate-shimmer",
                        children=[
                            html.Div(className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse-glow z-10"),
                            html.Span("Live Scanning: Phase 1 MVP", className="font-label-sm text-[12px] font-bold text-primary uppercase tracking-widest z-10 relative")
                        ]
                    )
                ]
            ),
            
            # Bento Grid
            html.Section(
                className="grid grid-cols-1 xl:grid-cols-3 gap-6",
                children=[
                    # Left Column (Dominant Signals Area - span 2 columns)
                    html.Div(
                        className="xl:col-span-2 flex flex-col gap-4 order-1 xl:order-1",
                        children=[
                            html.Div(
                                className="glass-panel p-6 rounded-2xl flex flex-col relative overflow-hidden h-full",
                                children=[
                                    html.Div(className="absolute inset-0 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none"),
                                    html.Div(
                                        className="flex justify-between items-end mb-6 z-10",
                                        children=[
                                            html.Div(
                                                children=[
                                                    html.H2("12-Condition Signals", className="font-headline-lg text-[24px] font-semibold text-on-surface-variant"),
                                                    html.Div(
                                                        className="flex items-baseline gap-2 mt-2",
                                                        children=[
                                                            html.Span(str(active_signals), id="signals-count", className="font-display-lg text-[64px] font-bold text-primary leading-none tracking-tighter animate-number-roll"),
                                                            html.Span("Signals Passing", className="font-label-sm text-on-surface-variant uppercase tracking-wider")
                                                        ]
                                                    ),
                                                    html.Div(f"As of {signals_asof} (signals file)", className="text-[10px] text-outline mt-2")
                                                ]
                                            ),
                                            html.Div(
                                                className="flex flex-col items-end gap-2",
                                                children=[
                                                    html.Span("Hide T2T", className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase"),
                                                    html.Div(
                                                        html.Div(
                                                            id="toggle",
                                                            className="relative inline-block w-12 align-middle select-none transition duration-200 ease-in cursor-pointer",
                                                            children=[
                                                                html.Div(id="toggle-knob", className="absolute block w-6 h-6 rounded-full bg-surface-container-highest border-2 border-primary z-10 transition-all duration-300 left-6"),
                                                                html.Div(id="toggle-bg", className="block overflow-hidden h-6 rounded-full bg-primary/40 transition-colors duration-300")
                                                            ]
                                                        )
                                                    )
                                                ]
                                            ),
                                        ]
                                    ),
                                    # Visual Data Grid
                                    html.Div(
                                        id="signals-grid",
                                        className="flex flex-col z-10 mt-2",
                                        children=signal_rows
                                    )
                                ]
                            )
                        ]
                    ),
                    
                    # Right Column (Stats Tiles - span 1 column)
                    html.Div(
                        className="flex flex-col gap-6 order-2 xl:order-2",
                        children=[
                            # Total Stocks Bento Tile
                            html.Div(
                                className="glass-panel rounded-2xl p-6 relative overflow-hidden group hover:-translate-y-1 transition-all duration-300 shadow-lg hover:shadow-secondary/10",
                                children=[
                                    html.Div(className="absolute top-0 right-0 p-4 text-secondary/60 group-hover:text-secondary/80 transition-colors", children=[html.Span("stacked_bar_chart", **{"aria-hidden": "true"}, className="material-symbols-outlined text-[48px]")]),
                                    html.Div("Total Scanned", className="font-label-sm text-[12px] font-bold text-on-surface-variant tracking-widest uppercase mb-1"),
                                    html.Div(f"{total_scanned:,}", className="font-display-lg text-[40px] font-bold text-secondary animate-number-roll"),
                                    html.Div(f"As of {as_of_str}", className="text-[10px] text-on-surface-variant mt-4")
                                ]
                            ),
                            # Secondary Stats Grid
                            html.Div(
                                className="grid grid-cols-2 gap-4",
                                children=[
                                    html.Div(
                                        className="glass-panel rounded-2xl p-5 flex flex-col justify-between hover:bg-white/5 transition-colors",
                                        children=[
                                            html.Div("NSE Stocks", className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase"),
                                            html.Div(f"{nse_count:,}", className="font-headline-md text-[24px] font-semibold text-on-surface mt-2 animate-number-roll")
                                        ]
                                    ),
                                    html.Div(
                                        className="glass-panel rounded-2xl p-5 flex flex-col justify-between hover:bg-white/5 transition-colors",
                                        children=[
                                            html.Div("BSE Stocks", className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase"),
                                            html.Div(f"{bse_count:,}", className="font-headline-md text-[24px] font-semibold text-on-surface mt-2 animate-number-roll")
                                        ]
                                    )
                                ]
                            ),
                            # Action Tile
                            html.Div(
                                className="glass-panel rounded-2xl p-6 mt-auto bg-gradient-to-br from-surface-container-high to-surface border-primary/20",
                                children=[
                                    html.H3("System Health", className="font-label-sm font-bold text-on-surface-variant uppercase mb-4"),
                                    html.Div(
                                        className="flex items-center gap-3 mb-2",
                                        children=[
                                            html.Span("check_circle", className="material-symbols-outlined text-primary text-[20px]"),
                                            html.Span("Real-time data stream optimal", className="text-sm text-on-surface")
                                        ]
                                    ),
                                    html.Div(
                                        className="flex items-center gap-3",
                                        children=[
                                            html.Span("check_circle", className="material-symbols-outlined text-primary text-[20px]"),
                                            html.Span("ML inference engine idle", className="text-sm text-on-surface")
                                        ]
                                    )
                                ]
                            )
                        ]
                    )
                ]
            )
        ]
    )


_KNOB_ON = "absolute block w-6 h-6 rounded-full bg-surface-container-highest border-2 border-primary z-10 transition-all duration-300 left-6"
_KNOB_OFF = "absolute block w-6 h-6 rounded-full bg-surface-container-highest border-2 border-outline-variant z-10 transition-all duration-300 left-0"
_BG_ON = "block overflow-hidden h-6 rounded-full bg-primary/40 transition-colors duration-300"
_BG_OFF = "block overflow-hidden h-6 rounded-full bg-surface-container transition-colors duration-300"

_EMPTY_MSG = "No active signals today."
_ALL_T2T_MSG = "All of today's signals are T2T (100% delivery) — toggle 'Hide T2T' off to view them."


@dash.callback(
    Output("signals-count", "children"),
    Output("signals-grid", "children"),
    Output("toggle-knob", "className"),
    Output("toggle-bg", "className"),
    Input("toggle", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_t2t_filter(n_clicks):
    """Hide T2T is ON by default (Streamlit parity). Odd clicks turn it OFF."""
    hide_t2t = (n_clicks % 2 == 0)
    df_latest, _ = load_latest_signals()
    if df_latest.empty:
        count, rows = 0, [html.Div(_EMPTY_MSG, className="p-4 font-body-md text-outline text-center glass-panel rounded-xl")]
    else:
        df_display = _filter_t2t(df_latest, hide_t2t)
        count = len(df_display)
        if count == 0:
            rows = [html.Div(_ALL_T2T_MSG, className="p-4 font-body-md text-outline text-center glass-panel rounded-xl")]
        else:
            rows = build_signal_rows(df_display)
    knob = _KNOB_ON if hide_t2t else _KNOB_OFF
    bg = _BG_ON if hide_t2t else _BG_OFF
    return str(count), rows, knob, bg
