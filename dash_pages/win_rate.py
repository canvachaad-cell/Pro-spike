import dash
from dash import html
import pandas as pd
import os
from dash_iconify import DashIconify
from watchlist_manager import WatchlistManager

dash.register_page(__name__, path='/win-rate', name='Win Rate', title='Pro Spike - Win Rate')

SBIA_LEDGER = os.path.join("data", "sbia_ledger.csv")
FG2_LEDGER = os.path.join("data", "flexgate2_ledger.csv")


def stat_tile(label, value, accent="text-on-surface", icon=None):
    return html.Div(
        className="glass-panel rounded-2xl p-5 flex flex-col justify-between",
        children=[
            html.Div(
                className="flex items-center justify-between",
                children=[
                    html.Div(label, className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase tracking-widest"),
                    html.Span(icon, className="material-symbols-outlined text-[18px] text-on-surface-variant") if icon else None,
                ]
            ),
            html.Div(str(value), className=f"font-headline-md text-[24px] font-semibold {accent} mt-2"),
        ]
    )


def pnl_class(v):
    return "text-primary" if v >= 0 else "text-error"


def ledger_summary(path):
    """Closed-trade stats from an engine ledger CSV."""
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if df.empty or "STATUS" not in df.columns:
        return None

    active = int((df["STATUS"] == "ACTIVE").sum())
    closed_mask = df["STATUS"].isin(["HIT_TP", "HIT_SL", "MOMENTUM_LOST"])
    closed = df[closed_mask]
    winners = int((df["STATUS"] == "HIT_TP").sum())
    total_closed = len(closed)
    win_rate = (winners / total_closed * 100) if total_closed else 0.0

    ret = None
    if {"ENTRY_PRICE", "EXIT_PRICE"}.issubset(closed.columns) and total_closed:
        ret = ((closed["EXIT_PRICE"] - closed["ENTRY_PRICE"]) / closed["ENTRY_PRICE"] * 100).mean()

    return {
        "active": active,
        "closed": total_closed,
        "winners": winners,
        "win_rate": win_rate,
        "avg_return": ret,
    }


def ledger_table(path, engine_name):
    if not os.path.exists(path):
        return html.Div(f"No ledger recorded yet for {engine_name}.",
                        className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")
    df = pd.read_csv(path)
    if df.empty:
        return html.Div(f"No ledger recorded yet for {engine_name}.",
                        className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")

    status_badges = {
        "ACTIVE": "bg-primary/10 text-primary border-primary/30",
        "HIT_TP": "bg-primary/10 text-primary border-primary/30",
        "HIT_SL": "bg-error/10 text-error border-error/30",
        "MOMENTUM_LOST": "bg-secondary/10 text-secondary border-secondary/30",
        "SUSPENDED": "bg-white/10 text-on-surface-variant border-outline-variant/30",
    }

    header = html.Div(
        className="grid grid-cols-7 gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant",
        children=[html.Div(c) for c in ["Symbol", "Status", "Entry Date", "Entry", "Stop", "Target", "Exit"]],
    )
    rows = []
    for _, r in df.iloc[::-1].head(100).iterrows():
        status = str(r.get("STATUS", ""))
        badge = status_badges.get(status, "bg-white/10 text-on-surface-variant border-outline-variant/30")
        rows.append(html.Div(
            className="grid grid-cols-7 gap-2 px-4 py-2.5 items-center hover:bg-white/5 transition-colors border-b border-outline-variant/40 font-data-md text-sm",
            children=[
                html.Div(str(r.get("SYMBOL", "")), className="text-on-surface font-semibold"),
                html.Span(status, className=f"text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border w-fit {badge}"),
                html.Div(str(r.get("ENTRY_DATE", "")), className="text-xs text-on-surface-variant"),
                html.Div(f"₹{float(r.get('ENTRY_PRICE', 0) or 0):,.2f}", className="text-on-surface"),
                html.Div(f"₹{float(r.get('STOP_LOSS', 0) or 0):,.2f}" if pd.notna(r.get("STOP_LOSS")) else "-", className="text-error"),
                html.Div(f"₹{float(r.get('TAKE_PROFIT', 0) or 0):,.2f}" if pd.notna(r.get("TAKE_PROFIT")) else "-", className="text-primary"),
                html.Div(f"₹{float(r.get('EXIT_PRICE', 0) or 0):,.2f}" if pd.notna(r.get("EXIT_PRICE")) else "-", className="text-on-surface"),
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


def layout():
    wm = WatchlistManager()
    stats = wm.get_win_rate()

    sbia = ledger_summary(SBIA_LEDGER)
    fg2 = ledger_summary(FG2_LEDGER)

    manual_tiles = [
        stat_tile("Total", stats["total"], "text-secondary", "inventory"),
        stat_tile("Winners", stats["winners"], "text-primary", "trending_up"),
        stat_tile("Win Rate %", f"{stats['win_rate']:.1f}%", "text-secondary", "percent"),
        stat_tile("Avg Return %", f"{stats['avg_return']:+.1f}%", pnl_class(stats["avg_return"]), "balance"),
    ]

    engine_sections = []
    for path, name, summary in [(SBIA_LEDGER, "SBIA Alpha Engine", sbia), (FG2_LEDGER, "FlexGate 2.0 ML Engine", fg2)]:
        if summary is None:
            continue
        avg_ret_str = f"{summary['avg_return']:+.1f}%" if summary["avg_return"] is not None else "-"
        engine_sections.append(html.Section(
            children=[
                html.H3(name, className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-3"),
                html.Div(
                    className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4",
                    children=[
                        stat_tile("Active", summary["active"], "text-secondary"),
                        stat_tile("Closed Trades", summary["closed"]),
                        stat_tile("Winners (Hit TP)", summary["winners"], "text-primary"),
                        stat_tile("Win Rate", f"{summary['win_rate']:.1f}% · avg {avg_ret_str}", "text-secondary"),
                    ]
                ),
                ledger_table(path, name),
            ]
        ))

    return html.Div(
        className="flex flex-col w-full px-[24px] py-[24px] max-w-[1600px] mx-auto gap-6",
        children=[
            html.Header(
                children=[
                    html.H2("Win Rate", className="font-display-lg text-[36px] text-on-surface tracking-tight"),
                    html.P("Performance report: manual watchlist trades and engine ledger outcomes.",
                           className="font-body-md text-on-surface-variant"),
                ]
            ),
            html.Section(
                children=[
                    html.H3("Trading Statistics (Watchlist)", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-3"),
                    html.Div(className="grid grid-cols-2 md:grid-cols-4 gap-4", children=manual_tiles),
                ]
            ),
        ] + engine_sections,
    )
