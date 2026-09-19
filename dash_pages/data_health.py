import dash
from dash import html
import pandas as pd
import os
import json
from functools import lru_cache

dash.register_page(__name__, path='/data-health', name='Data Health', title='Pro Spike - Data Health')

STATUS_FILE = os.path.join("data", "data_status.json")
LIVE_FILE = os.path.join("data", "combined_dashboard_live.csv")
MERGE_STATS_FILE = os.path.join("data", "debug_bse_row_counts.csv")


@lru_cache(maxsize=8)
def load_health_data(status_mtime, live_mtime, merge_mtime):
    status = {}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            status = json.load(f)
    except Exception:
        pass

    total_count, nse_count, bse_count, as_of = 0, 0, 0, None
    try:
        df = pd.read_csv(LIVE_FILE, usecols=["EXCHANGE", "DATE"])
        total_count = len(df)
        exch = df["EXCHANGE"].value_counts()
        nse_count = int(exch.get("NSE", 0))
        bse_count = int(exch.get("BSE", 0))
        as_of = pd.to_datetime(df["DATE"], errors="coerce").max()
    except Exception:
        pass

    merge_stats = None
    try:
        mdf = pd.read_csv(MERGE_STATS_FILE)
        if not mdf.empty:
            merge_stats = mdf.iloc[-1].to_dict()
    except Exception:
        pass

    return status, total_count, nse_count, bse_count, as_of, merge_stats


def feed_card(label, icon, date_str):
    synced = bool(date_str) and str(date_str) != "Missing"
    icon_color = "text-primary" if synced else "text-error"
    badge = (
        "bg-primary/10 text-primary border-primary/30" if synced
        else "bg-error/10 text-error border-error/30"
    )
    status_text = "Synced" if synced else "Missing"
    return html.Div(
        className="glass-panel rounded-2xl p-5 flex items-center gap-4",
        children=[
            html.Span(icon, className=f"material-symbols-outlined text-[28px] {icon_color}"),
            html.Div(
                className="flex flex-col gap-1 flex-1",
                children=[
                    html.Div(label, className="font-label-sm text-[11px] font-bold text-on-surface-variant uppercase tracking-widest"),
                    html.Div(str(date_str) if synced else "Missing", className="font-headline-md text-[20px] font-semibold text-on-surface"),
                ]
            ),
            html.Span(status_text, className=f"text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border {badge}"),
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
    status_mtime = os.path.getmtime(STATUS_FILE) if os.path.exists(STATUS_FILE) else 0
    live_mtime = os.path.getmtime(LIVE_FILE) if os.path.exists(LIVE_FILE) else 0
    merge_mtime = os.path.getmtime(MERGE_STATS_FILE) if os.path.exists(MERGE_STATS_FILE) else 0
    status, total_count, nse_count, bse_count, as_of, merge_stats = load_health_data(status_mtime, live_mtime, merge_mtime)

    as_of_str = as_of.strftime("%d %b %Y") if as_of is not None and pd.notna(as_of) else "—"
    last_run = status.get("last_run", "Unknown")

    merge_tiles = []
    if merge_stats is not None:
        merge_tiles = [
            stat_tile("Total BSE Rows", f"{float(merge_stats.get('total_bse_rows', 0)):,.0f}"),
            stat_tile("Zero Delivery", f"{float(merge_stats.get('zero_delivery', 0)):,.0f}", "text-error" if float(merge_stats.get('zero_delivery', 0)) > 5000 else "text-primary"),
            stat_tile("Partial Delivery", f"{float(merge_stats.get('partial_delivery', 0)):,.0f}"),
            stat_tile("Full Delivery (T2T)", f"{float(merge_stats.get('full_delivery', 0)):,.0f}"),
        ]

    return html.Div(
        className="flex flex-col w-full px-[24px] py-[24px] max-w-[1600px] mx-auto gap-6",
        children=[
            html.Header(
                children=[
                    html.H1("Data Health", className="font-display-lg text-[36px] text-on-surface tracking-tight"),
                    html.P(f"Feed freshness and sync status. Background sync last ran: {last_run}.",
                           className="font-body-md text-on-surface-variant"),
                ]
            ),
            html.Section(
                className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4",
                children=[
                    feed_card("NSE Bhavcopy", "candlestick_chart", status.get("nse_bhav_date", "Missing")),
                    feed_card("NSE Delivery", "inventory_2", status.get("nse_deliv_date", "Missing")),
                    feed_card("BSE Bhavcopy", "account_balance", status.get("bse_bhav_date", "Missing")),
                    feed_card("BSE Delivery", "local_shipping", status.get("bse_deliv_date", "Missing")),
                ]
            ),
            html.Section(
                children=[
                    html.H3("Universe", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-3"),
                    html.Div(
                        className="grid grid-cols-2 md:grid-cols-4 gap-4",
                        children=[
                            stat_tile("Total Universe", f"{total_count:,}", "text-secondary"),
                            stat_tile("NSE Stocks", f"{nse_count:,}"),
                            stat_tile("BSE Stocks", f"{bse_count:,}"),
                            stat_tile("Data as of", as_of_str, "text-secondary"),
                        ]
                    ),
                ]
            ),
            html.Section(
                children=[
                    html.H3("BSE Delivery Merge", className="font-headline-lg text-[20px] font-semibold text-on-surface-variant mb-1"),
                    html.P("Latest bhavcopy/delivery merge composition (from debug_bse_row_counts.csv).",
                           className="font-body-md text-sm text-on-surface-variant mb-3"),
                    html.Div(
                        className="grid grid-cols-2 md:grid-cols-4 gap-4",
                        children=merge_tiles or [html.Div("No merge stats recorded yet.", className="p-4 font-body-md text-outline glass-panel rounded-xl")],
                    ),
                ]
            ),
        ]
    )
