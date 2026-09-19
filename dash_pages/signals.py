import dash
from dash import html, dcc
import pandas as pd
import os
from functools import lru_cache
from datetime import datetime
from progressive_screener import ProgressiveSpiker

dash.register_page(__name__, path='/signals', name='Signals', title='Pro Spike - Signals')

LIVE_FILE = os.path.join("data", "combined_dashboard_live.csv")
HISTORY_FILE = os.path.join("data", "signal_history.csv")


def log_signal_to_history(symbol, exchange, close, deliv_per, momentum_score):
    """Log signal to history file (deduped per day+symbol). Ported from dashboard_full.py."""
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:
            f.write("Date,Symbol,Exchange,Price,Delivery_Percent,Momentum_Score\n")
    try:
        df_history = pd.read_csv(HISTORY_FILE)
        if ((df_history["Date"] == today) & (df_history["Symbol"] == symbol)).any():
            return
    except Exception:
        pass
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{today},{symbol},{exchange},{close},{deliv_per:.2f},{momentum_score:.1f}\n")


@lru_cache(maxsize=4)
def load_signal_data(mtime):
    """Load universe, run the 12-condition scanner, compute momentum scores.
    Cached per file mtime so page renders stay cheap."""
    try:
        df = pd.read_csv(LIVE_FILE)
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

    if "DATE" not in df.columns or df["DATE"].isna().all():
        return df, pd.DataFrame()

    df_filt = df[df["EVER_100_DELIV"] == False] if "EVER_100_DELIV" in df.columns else df
    try:
        signals = ProgressiveSpiker(df_filt).get_signals()
    except Exception:
        signals = pd.DataFrame()

    if signals.empty:
        return df, signals

    with pd.option_context("mode.chained_assignment", None):
        deliv_momentum = ((signals["DELIV_PER"] - signals["DELIV_PER_1W"]) / signals["DELIV_PER_1W"] * 100).clip(0, 33)
        turnover_momentum = ((signals["DELIVERY_TURNOVER"] - signals["DELIVERY_TURNOVER_1W"]) / signals["DELIVERY_TURNOVER_1W"] * 100).clip(0, 33)
        atw_momentum = ((signals["ATW"] - signals["ATW_1W"]) / signals["ATW_1W"] * 100).clip(0, 34)
        signals["MOMENTUM_SCORE"] = (deliv_momentum + turnover_momentum + atw_momentum).round(1)
        signals = signals.sort_values("MOMENTUM_SCORE", ascending=False)

        for _, row in signals.iterrows():
            log_signal_to_history(
                row["SYMBOL"],
                row.get("EXCHANGE", "NSE"),
                row["CLOSE"],
                row["DELIV_PER"],
                row["MOMENTUM_SCORE"],
            )
    return df, signals


def metric_tile(label, value, accent="text-primary"):
    return html.Div(
        className="glass-panel rounded-2xl p-5 flex flex-col justify-between",
        children=[
            html.Div(label, className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase tracking-widest"),
            html.Div(str(value), className=f"font-headline-md text-[24px] font-semibold {accent} mt-2")
        ]
    )


def format_cr(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    if v > 10000000:
        return f"₹{v/10000000:.2f}Cr"
    return f"₹{v:,.0f}"


def build_signals_table(signals):
    if signals.empty:
        return html.Div("No signals found today", className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")

    header = html.Div(
        className="grid grid-cols-7 gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant",
        children=[
            html.Div("Symbol"), html.Div("Exch"), html.Div("Close"),
            html.Div("Delivery"), html.Div("Deliv Turnover"), html.Div("ATW"), html.Div("Momentum"),
        ]
    )
    rows = []
    for _, r in signals.head(100).iterrows():
        exch = str(r.get("EXCHANGE", "NSE"))
        badge = "bg-[#38bdf8]/15 text-[#38bdf8] border border-[#38bdf8]/30" if exch.upper() == "NSE" else "bg-[#34d399]/20 text-[#34d399] border border-[#34d399]/30"
        mom = float(r.get("MOMENTUM_SCORE", 0) or 0)
        rows.append(html.Div(
            className="grid grid-cols-7 gap-2 px-4 py-3 items-center hover:bg-white/5 transition-colors border-b border-outline-variant/40",
            children=[
                html.Div(str(r.get("SYMBOL", "")), className="font-data-md text-on-surface font-semibold"),
                html.Div(exch, className=f"text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full border border-transparent w-fit {badge}"),
                html.Div(f"₹{float(r.get('CLOSE', 0)):,.2f}", className="font-data-md text-on-surface"),
                html.Div(f"{float(r.get('DELIV_PER', 0)):.1f}%", className="font-data-md text-primary"),
                html.Div(format_cr(r.get("DELIVERY_TURNOVER", 0)), className="font-data-md text-on-surface"),
                html.Div(format_cr(r.get("ATW", 0)), className="font-data-md text-on-surface"),
                html.Div(
                    className="flex items-center gap-2",
                    children=[
                        html.Div(className="h-1.5 rounded-full bg-primary", style={"width": f"{min(mom, 100)}%"}),
                        html.Span(f"{mom:.1f}", className="font-data-md text-on-surface text-sm"),
                    ]
                ),
            ]
        ))
    return html.Div(
        className="table-scroll-wrapper",
        tabIndex="0",
        **{"aria-label": "12-Condition Signals Table"},
        children=[
            html.Div(
                className="glass-panel rounded-2xl overflow-hidden",
                style={"minWidth": "700px"},
                children=[header] + rows,
            )
        ]
    )


def build_history_section():
    if not os.path.exists(HISTORY_FILE):
        return html.Div("No signal history yet. Signals will be auto-logged when they appear.",
                        className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")
    try:
        hist = pd.read_csv(HISTORY_FILE)
    except Exception:
        hist = pd.DataFrame()

    stats = html.Div(
        className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4",
        children=[
            metric_tile("Total Signals Logged", f"{len(hist):,}"),
            metric_tile("Unique Stocks", f"{hist['Symbol'].nunique():,}" if "Symbol" in hist.columns else "0"),
            metric_tile("Date Range", f"{hist['Date'].min()} → {hist['Date'].max()}" if "Date" in hist.columns and not hist.empty else "-"),
        ]
    )

    rows = []
    for _, r in hist.tail(50).iloc[::-1].iterrows():
        rows.append(html.Div(
            className="grid grid-cols-6 gap-2 px-4 py-2.5 items-center hover:bg-white/5 transition-colors border-b border-outline-variant/40 font-data-md text-sm",
            children=[
                html.Div(str(r.get("Date", "")), className="text-on-surface-variant"),
                html.Div(str(r.get("Symbol", "")), className="text-on-surface font-semibold"),
                html.Div(str(r.get("Exchange", "")), className="text-on-surface-variant"),
                html.Div(f"₹{float(r.get('Price', 0)):,.2f}", className="text-on-surface"),
                html.Div(f"{float(r.get('Delivery_Percent', 0)):.1f}%", className="text-primary"),
                html.Div(f"{float(r.get('Momentum_Score', 0)):.1f}", className="text-secondary"),
            ]
        ))
    header = html.Div(
        className="grid grid-cols-6 gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant",
        children=[html.Div("Date"), html.Div("Symbol"), html.Div("Exch"), html.Div("Price"), html.Div("Delivery"), html.Div("Momentum")]
    )
    table = html.Div(
        className="table-scroll-wrapper",
        tabIndex="0",
        **{"aria-label": "Signal History Table"},
        children=[
            html.Div(
                className="glass-panel rounded-2xl overflow-hidden", 
                style={"minWidth": "600px"},
                children=[header] + rows
            )
        ]
    )
    return html.Div([stats, table])


def layout():
    mtime = os.path.getmtime(LIVE_FILE) if os.path.exists(LIVE_FILE) else 0
    df, signals = load_signal_data(mtime)

    if df.empty:
        return html.Div("No data available. Run auto_update_smart.py first.",
                        className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")

    exch_counts = df["EXCHANGE"].value_counts() if "EXCHANGE" in df.columns else {}
    nse_count = exch_counts.get("NSE", 0)
    bse_count = exch_counts.get("BSE", 0)
    latest_date = pd.to_datetime(df["DATE"], errors="coerce").max()
    as_of = latest_date.strftime("%d %b %Y") if pd.notna(latest_date) else "—"

    return html.Div(
        className="flex flex-col w-full px-[24px] py-[24px] max-w-[1600px] mx-auto gap-6",
        children=[
            html.Header(
                children=[
                    html.H1("Signals", className="font-display-lg text-[36px] text-on-surface tracking-tight"),
                    html.P("12-Condition Progressive Spiker scanner with momentum scoring.",
                           className="font-body-md text-on-surface-variant"),
                ]
            ),
            html.Section(
                className="grid grid-cols-2 md:grid-cols-4 gap-4",
                children=[
                    metric_tile("Total Stocks", f"{len(df):,}", "text-secondary"),
                    metric_tile("NSE", f"{nse_count:,}"),
                    metric_tile("BSE", f"{bse_count:,}"),
                    metric_tile("Data as of", as_of, "text-secondary"),
                ]
            ),
            html.Section(
                children=[
                    html.Div(
                        className="flex items-baseline justify-between mb-3",
                        children=[
                            html.H3("12-Condition Signals", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant"),
                            html.Span(f"{len(signals)} passing", className="font-label-sm text-primary font-bold uppercase tracking-wider"),
                        ]
                    ),
                    build_signals_table(signals),
                ]
            ),
            html.Section(
                children=[
                    html.H3("Signal History", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-3"),
                    build_history_section(),
                ]
            ),
        ]
    )
