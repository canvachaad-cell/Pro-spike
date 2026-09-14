import dash
from dash import html, dcc, Input, Output, State, ctx, ALL
import pandas as pd
import os
from functools import lru_cache
from dash_iconify import DashIconify
from watchlist_manager import WatchlistManager

dash.register_page(__name__, path='/watchlist', name='Watchlist', title='Pro Spike - Watchlist')

LIVE_FILE = os.path.join("data", "combined_dashboard_live.csv")


@lru_cache(maxsize=4)
def load_scanner_universe(mtime):
    """Union of symbols from all active scanners, mapped to their source scanner."""
    universe = {}

    master_df = pd.DataFrame()
    if os.path.exists(LIVE_FILE):
        try:
            master_df = pd.read_csv(LIVE_FILE)
        except Exception:
            master_df = pd.DataFrame()

    if not master_df.empty:
        try:
            from progressive_screener import ProgressiveSpiker
            df_filt = master_df[master_df["EVER_100_DELIV"] == False] if "EVER_100_DELIV" in master_df.columns else master_df
            sig_df = ProgressiveSpiker(df_filt).get_signals()
            for sym in sig_df["SYMBOL"].dropna().unique():
                universe[sym] = "12-Condition Scanner"
        except Exception:
            pass

    for path, name in [
        ("data/sbia_alpha_watchlist.csv", "SBIA Alpha Engine"),
        ("data/sbia_flexgate_watchlist.csv", "Legacy FlexGate"),
        ("data/sbia_flexgate2_watchlist.csv", "FlexGate 2.0 ML Engine"),
    ]:
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
            if "AI_APPROVED" in df.columns and name.startswith("FlexGate 2.0"):
                df = df[df["AI_APPROVED"] == True]
            for sym in df["SYMBOL"].dropna().unique():
                if sym not in universe or universe[sym] == "12-Condition Scanner":
                    universe[sym] = name
        except Exception:
            pass

    return master_df, universe


def get_live_watchlist():
    """Load watchlist and refresh current prices from the latest combined data."""
    wm = WatchlistManager()
    if len(wm.active) > 0 and os.path.exists(LIVE_FILE):
        try:
            df = pd.read_csv(LIVE_FILE, usecols=["SYMBOL", "CLOSE"])
            wm.auto_update_prices(df)
            wm = WatchlistManager()
        except Exception:
            pass
    return wm


def pnl_class(pnl):
    return "text-primary" if pnl >= 0 else "text-error"


def build_positions_section(wm):
    if len(wm.active) == 0:
        return html.Div("No active positions — add signals from the scanners above.",
                        className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")

    total_value = float((wm.active["current_price"] * 100).sum())
    total_pl = float(((wm.active["current_price"] - wm.active["entry_price"]) * 100).sum())
    total_pnl_pct = (total_pl / total_value * 100) if total_value else 0.0

    stats = html.Div(
        className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4",
        children=[
            stat_tile("Active Positions", len(wm.active), "text-secondary"),
            stat_tile("Approx Value", f"₹{total_value:,.0f}"),
            stat_tile("Unrealized P&L", f"₹{total_pl:,.0f}", pnl_class(total_pl)),
            stat_tile("Open PnL %", f"{total_pnl_pct:.2f}%", pnl_class(total_pnl_pct)),
        ]
    )

    header = html.Div(
        className="grid grid-cols-9 gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant",
        children=[html.Div(c) for c in ["Symbol", "Strategy", "Entry", "Current", "Target", "Stop", "Entry Date", "PnL %", ""]],
    )

    rows = []
    for _, r in wm.active.iterrows():
        pnl = ((r["current_price"] - r["entry_price"]) / r["entry_price"]) * 100 if r["entry_price"] else 0.0
        rows.append(html.Div(
            className="grid grid-cols-9 gap-2 px-4 py-3 items-center hover:bg-white/5 transition-colors border-b border-outline-variant/40",
            children=[
                html.Div(str(r.get("symbol", "")), className="font-data-md text-on-surface font-semibold"),
                html.Div(str(r.get("strategy", "") or "12-Condition Scanner"), className="text-xs text-on-surface-variant"),
                html.Div(f"₹{float(r.get('entry_price', 0)):,.2f}", className="font-data-md text-sm text-on-surface"),
                html.Div(f"₹{float(r.get('current_price', 0)):,.2f}", className="font-data-md text-sm text-on-surface"),
                html.Div(f"₹{float(r.get('tp', 0)):,.2f}", className="font-data-md text-sm text-primary"),
                html.Div(f"₹{float(r.get('sl', 0)):,.2f}", className="font-data-md text-sm text-error"),
                html.Div(str(r.get("entry_date", "")), className="text-xs text-on-surface-variant"),
                html.Div(f"{pnl:+.2f}%", className=f"font-data-md text-sm font-semibold {pnl_class(pnl)}"),
                html.Button(
                    "Close",
                    id={"type": "close-btn", "index": str(r.get("symbol", ""))},
                    n_clicks=0,
                    className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border border-error/30 bg-error/10 text-error hover:bg-error/20 transition-colors",
                ),
            ]
        ))

    return html.Div([
        stats,
        html.Div(
            className="table-scroll-wrapper",
            children=[
                html.Div(
                    className="glass-panel rounded-2xl overflow-hidden",
                    style={"minWidth": "900px"},
                    children=[header] + rows
                )
            ]
        ),
    ])


def build_closed_section(wm):
    if not os.path.exists(wm.closed_file):
        return html.Div("No closed trades recorded yet.",
                        className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")
    closed = pd.read_csv(wm.closed_file)
    if closed.empty:
        return html.Div("No closed trades recorded yet.",
                        className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")
    if "exit_date" in closed.columns:
        closed = closed.sort_values(by="exit_date", ascending=False)

    header = html.Div(
        className="grid grid-cols-7 gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant",
        children=[html.Div(c) for c in ["Symbol", "Strategy", "Entry Date", "Exit Date", "Entry", "Exit", "Return %"]],
    )
    rows = []
    for _, r in closed.head(100).iterrows():
        ret = float(r.get("return_pct", 0) or 0)
        rows.append(html.Div(
            className="grid grid-cols-7 gap-2 px-4 py-2.5 items-center hover:bg-white/5 transition-colors border-b border-outline-variant/40 font-data-md text-sm",
            children=[
                html.Div(str(r.get("symbol", "")), className="text-on-surface font-semibold"),
                html.Div(str(r.get("strategy", "") or "-"), className="text-xs text-on-surface-variant"),
                html.Div(str(r.get("entry_date", "")), className="text-xs text-on-surface-variant"),
                html.Div(str(r.get("exit_date", "")), className="text-xs text-on-surface-variant"),
                html.Div(f"₹{float(r.get('entry_price', 0)):,.2f}", className="text-on-surface"),
                html.Div(f"₹{float(r.get('exit_price', 0)):,.2f}", className="text-on-surface"),
                html.Div(f"{ret:+.2f}%", className=f"font-semibold {pnl_class(ret)}"),
            ]
        ))
    return html.Div(
        className="table-scroll-wrapper",
        children=[
            html.Div(
                className="glass-panel rounded-2xl overflow-hidden",
                style={"minWidth": "720px"},
                children=[header] + rows
            )
        ]
    )


def stat_tile(label, value, accent="text-on-surface"):
    return html.Div(
        className="glass-panel rounded-2xl p-5 flex flex-col justify-between",
        children=[
            html.Div(label, className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase tracking-widest"),
            html.Div(str(value), className=f"font-headline-md text-[24px] font-semibold {accent} mt-2"),
        ]
    )


def layout():
    mtime = os.path.getmtime(LIVE_FILE) if os.path.exists(LIVE_FILE) else 0
    master_df, universe = load_scanner_universe(mtime)
    wm = get_live_watchlist()

    options = [{"label": f"{sym}  |  {scanner}", "value": sym} for sym, scanner in sorted(universe.items())]

    add_section = html.Section(
        className="glass-panel rounded-2xl p-6",
        children=[
            html.H3("Add Scanner Stock to Watchlist", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-4"),
            html.Div(
                className="flex flex-col md:flex-row gap-4 items-stretch md:items-end",
                children=[
                    html.Div(
                        className="flex-1 flex flex-col gap-1",
                        children=[
                            html.Label("Search for a stock that recently triggered a scanner:", className="font-label-sm text-[11px] font-bold text-on-surface-variant uppercase tracking-widest"),
                            dcc.Dropdown(
                                id="symbol-dropdown",
                                options=options,
                                value=None,
                                placeholder="Type symbol or scanner name...",
                                className="font-data-md",
                            ),
                        ]
                    ),
                    html.Div(
                        className="flex flex-col gap-1",
                        children=[
                            html.Label("Entry Price", className="font-label-sm text-[11px] font-bold text-on-surface-variant uppercase tracking-widest"),
                            dcc.Input(
                                id="entry-price-input",
                                type="number",
                                value=0,
                                step=0.05,
                                className="glass-panel bg-transparent rounded-lg px-3 py-2 font-data-md text-on-surface w-32 focus:ring-0 focus:outline-none outline-none appearance-none",
                            ),
                        ]
                    ),
                    html.Button(
                        [DashIconify(icon="mdi:plus", width=16), html.Span("Add to Watchlist")],
                        id="add-btn",
                        n_clicks=0,
                        className="flex items-center gap-2 bg-primary text-on-primary font-headline-sm rounded-lg px-5 py-2.5 min-h-[44px] hover:bg-primary-fixed transition-colors",
                    ),
                ]
            ),
            html.Div(id="add-status", className="mt-3 font-body-md text-sm"),
        ]
    )

    return html.Div(
        className="flex flex-col w-full px-[24px] py-[24px] max-w-[1600px] mx-auto gap-6",
        children=[
            html.Header(
                children=[
                    html.H2("Watchlist", className="font-display-lg text-[36px] text-on-surface tracking-tight"),
                    html.P("Active position tracking with automatic price updates and PnL.", className="font-body-md text-on-surface-variant"),
                ]
            ),
            add_section,
            html.Div(
                id="watchlist-body",
                children=[
                    html.Section(
                        children=[
                            html.H3("Manage Positions", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-3"),
                            build_positions_section(wm),
                        ]
                    ),
                    html.Section(
                        children=[
                            html.H3("Past Closed Trades", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-3"),
                            build_closed_section(wm),
                        ]
                    ),
                ]
            ),
        ]
    )


@dash.callback(
    Output("entry-price-input", "value"),
    Input("symbol-dropdown", "value"),
    prevent_initial_call=True,
)
def update_entry_price(symbol):
    if not symbol:
        return 0
    mtime = os.path.getmtime(LIVE_FILE) if os.path.exists(LIVE_FILE) else 0
    master_df, _ = load_scanner_universe(mtime)
    if master_df.empty:
        return 0
    match = master_df[master_df["SYMBOL"] == symbol]
    if match.empty:
        return 0
    try:
        return round(float(match.iloc[0]["CLOSE"]), 2)
    except (TypeError, ValueError):
        return 0


@dash.callback(
    Output("watchlist-body", "children"),
    Output("add-status", "children"),
    Input("add-btn", "n_clicks"),
    Input({"type": "close-btn", "index": ALL}, "n_clicks"),
    State("symbol-dropdown", "value"),
    State("entry-price-input", "value"),
    prevent_initial_call=True,
)
def handle_watchlist_actions(add_clicks, close_clicks, symbol, entry_price):
    status = ""
    triggered = ctx.triggered_id

    if triggered == "add-btn" and symbol:
        wm = WatchlistManager()
        mtime = os.path.getmtime(LIVE_FILE) if os.path.exists(LIVE_FILE) else 0
        master_df, universe = load_scanner_universe(mtime)
        delivery_pct = 0.0
        if not master_df.empty:
            match = master_df[master_df["SYMBOL"] == symbol]
            if not match.empty:
                try:
                    delivery_pct = float(match.iloc[0].get("DELIV_PER", 0) or 0)
                except (TypeError, ValueError):
                    delivery_pct = 0.0
        entry = float(entry_price) if entry_price else 0.0
        success, msg = wm.add_stock(
            symbol=symbol,
            entry_price=entry,
            delivery_pct=delivery_pct,
            momentum=0,
            strategy=universe.get(symbol, "Unknown"),
        )
        status = f"✅ {symbol} added to Watchlist! Tracking PnL active." if success else f"⚠️ {msg}"
        symbol = None

    elif isinstance(triggered, dict) and triggered.get("type") == "close-btn":
        close_symbol = triggered.get("index")
        wm = WatchlistManager()
        if len(wm.active) > 0:
            match = wm.active[wm.active["symbol"] == close_symbol]
            exit_price = float(match.iloc[0]["current_price"]) if not match.empty else 0.0
            wm.close_position(close_symbol, exit_price, "manual")
            status = f"✅ Closed position for {close_symbol}"

    wm = get_live_watchlist()
    return (
        [
            html.Section(
                children=[
                    html.H3("Manage Positions", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-3"),
                    build_positions_section(wm),
                ]
            ),
            html.Section(
                children=[
                    html.H3("Past Closed Trades", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-3"),
                    build_closed_section(wm),
                ]
            ),
        ],
        status,
    )
