import os
from functools import lru_cache

import dash
import pandas as pd
from dash import Input, Output, State, dcc, html

dash.register_page(__name__, path='/notifications', name='Alerts', title='Pro Spike - Alerts')

ALERTS_LOG = os.path.join("data", "alerts_log.csv")

ENGINE_LABELS = {
    "ALPHA_MARKUPS": "Alpha Markups",
    "FLEXGATE": "FlexGate",
    "FLEXGATE2": "FlexGate 2.0",
    "CORNER": "Corner Spike",
}

# Ledger STATUS badge map — verbatim from dash_pages/win_rate.py:74-80
STATUS_BADGES = {
    "ACTIVE": "bg-primary/10 text-primary border-primary/30",
    "HIT_TP": "bg-primary/10 text-primary border-primary/30",
    "HIT_SL": "bg-error/10 text-error border-error/30",
    "MOMENTUM_LOST": "bg-secondary/10 text-secondary border-secondary/30",
    "SUSPENDED": "bg-white/10 text-on-surface-variant border-outline-variant/30",
    "APPROACHING": "bg-secondary/10 text-secondary border-secondary/30",
    "NEW_ENTRY": "bg-primary/10 text-primary border-primary/30",
    "REACTIVATED": "bg-primary/10 text-primary border-primary/30",
}

TYPE_TO_STATUS = {
    "EXIT_TP": "HIT_TP",
    "EXIT_SL": "HIT_SL",
    "EXIT_MOMENTUM": "MOMENTUM_LOST",
    "EXIT_SUSPENDED": "SUSPENDED",
    "APPROACHING_SL": "APPROACHING",
    "APPROACHING_TP": "APPROACHING",
    "NEW_ENTRY": "NEW_ENTRY",
    "REACTIVATED": "REACTIVATED",
}

TYPE_ICON = {
    "EXIT_TP": "trending_up",
    "EXIT_SL": "trending_down",
    "EXIT_MOMENTUM": "hourglass_empty",
    "EXIT_SUSPENDED": "pause_circle",
    "APPROACHING_SL": "visibility",
    "APPROACHING_TP": "visibility",
    "NEW_ENTRY": "new_releases",
    "REACTIVATED": "restart_alt",
}

FILTERS = [
    ("ALL", "All"),
    ("EXITS", "Exits"),
    ("EXIT_TP", "TP"),
    ("EXIT_SL", "SL"),
    ("EXIT_MOMENTUM", "Momentum"),
    ("NEW_ENTRY", "New Entries"),
]


@lru_cache(maxsize=16)
def _read_csv(path, mtime):
    """Cached CSV reader keyed on file mtime so renders stay cheap."""
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def load_alerts():
    if not os.path.exists(ALERTS_LOG):
        return None
    try:
        return _read_csv(ALERTS_LOG, os.path.getmtime(ALERTS_LOG))
    except OSError:
        return None


def _fmt_inr(v):
    try:
        f = float(v)
        if pd.isna(f):
            return "-"
        return f"₹{f:,.2f}"
    except (TypeError, ValueError):
        return "-"


def stat_tile(label, value, accent="text-on-surface"):
    return html.Div(
        className="glass-panel rounded-2xl p-5 flex flex-col justify-between",
        children=[
            html.Div(label, className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase tracking-widest"),
            html.Div(str(value), className=f"font-headline-md text-[24px] font-semibold {accent} mt-2"),
        ]
    )


def empty_state(msg):
    return html.Div(msg, className="p-6 font-body-md text-outline text-center glass-panel rounded-xl")


def alert_row(r):
    etype = str(r.get("event_type", ""))
    status = TYPE_TO_STATUS.get(etype, etype)
    badge = STATUS_BADGES.get(status, "bg-white/10 text-on-surface-variant border-outline-variant/30")
    icon = TYPE_ICON.get(etype, "notifications")
    pnl = r.get("pnl_pct")
    try:
        pnl_f = float(pnl)
        pnl_txt = f"{pnl_f:+.2f}%"
    except (TypeError, ValueError):
        pnl_f = 0.0
        pnl_txt = "-"

    lag = r.get("lag_days")
    try:
        lag_i = int(lag)
        lag_txt = f"{lag_i}d" if lag_i > 0 else "same day"
    except (TypeError, ValueError):
        lag_txt = "-"

    return html.Div(
        className="grid grid-cols-8 gap-2 px-4 py-2.5 items-center hover:bg-white/5 transition-colors border-b border-outline-variant/40 font-data-md text-sm",
        children=[
            html.Div(str(r.get("detected_at", ""))[:16], className="text-xs text-on-surface-variant"),
            html.Div(
                className="flex items-center gap-2",
                children=[
                    html.Span(icon, className="material-symbols-outlined text-[16px] text-on-surface-variant"),
                    html.Span(str(r.get("symbol", "")), className="text-on-surface font-semibold"),
                ]
            ),
            html.Div(ENGINE_LABELS.get(str(r.get("engine", "")), str(r.get("engine", ""))),
                     className="text-xs text-on-surface-variant"),
            html.Span(status, className=f"text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border w-fit {badge}"),
            html.Div(_fmt_inr(r.get("entry_price")), className="text-on-surface"),
            html.Div(_fmt_inr(r.get("exit_price")), className="text-on-surface"),
            html.Div(pnl_txt, className="text-primary" if pnl_f >= 0 else "text-error"),
            html.Div(lag_txt, className="text-xs text-on-surface-variant"),
        ]
    )


def table_head():
    cols = ["Detected", "Symbol", "Engine", "Status", "Entry", "Exit", "PnL", "Lag"]
    return html.Div(
        className="grid grid-cols-8 gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant",
        children=[html.Div(c) for c in cols],
    )


def build_table(df, flt):
    if df is None or df.empty:
        return empty_state("No alerts recorded yet. Run calculate_active_signals.py or "
                           "python alert_engine.py to generate events.")

    df = df.copy()
    df["detected_at"] = df["detected_at"].astype(str)
    df = df.sort_values("detected_at", ascending=False)

    if flt == "EXITS":
        sel = df[df["event_type"].astype(str).str.startswith("EXIT")]
    elif flt in ("EXIT_TP", "EXIT_SL", "EXIT_MOMENTUM"):
        sel = df[df["event_type"].astype(str) == flt]
    elif flt == "NEW_ENTRY":
        sel = df[df["event_type"].astype(str).isin(["NEW_ENTRY", "REACTIVATED"])]
    else:
        sel = df

    if sel.empty:
        return empty_state("No alerts match this filter.")

    rows = [alert_row(r) for _, r in sel.head(300).iterrows()]
    return html.Div(
        className="table-scroll-wrapper",
        tabIndex="0",
        **{"aria-label": "Ledger alert history table"},
        children=[
            html.Div(
                className="glass-panel rounded-2xl overflow-hidden",
                style={"minWidth": "900px"},
                children=[table_head()] + rows,
            )
        ],
    )


def chip_class(active: bool) -> str:
    base = "px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors cursor-pointer "
    if active:
        return base + "bg-primary/15 border-primary/40 text-primary"
    return base + "bg-white/5 border-white/5 text-on-surface-variant hover:bg-white/10 hover:text-white"


def chip(label, value, active):
    return html.Button(label, id=f"alert-chip-{value}", n_clicks=0, className=chip_class(active))


def layout():
    df = load_alerts()
    total = 0 if df is None or df.empty else len(df)

    def _count(prefix):
        if df is None or df.empty:
            return 0
        return int(df["event_type"].astype(str).str.startswith(prefix).sum())

    tp = _count("EXIT_TP")
    sl = _count("EXIT_SL")
    mo = _count("EXIT_MOMENTUM")

    return html.Div(
        className="flex flex-col gap-lg",
        children=[
            dcc.Store(id="alerts-last-visit", storage_type="local"),
            dcc.Store(id="alerts-filter", data="ALL"),

            html.Div(
                className="flex flex-col gap-xs",
                children=[
                    html.H2("Alerts", className="font-headline-md text-on-surface"),
                    html.P("Ledger exit events: take-profit, stop-loss, momentum loss, "
                           "suspensions and new entries.",
                           className="font-body-md text-on-surface-variant"),
                ]
            ),

            html.Div(id="alerts-unread-banner"),

            html.Div(
                className="grid grid-cols-2 md:grid-cols-4 gap-4",
                children=[
                    stat_tile("TP Exits", tp, "text-primary"),
                    stat_tile("SL Exits", sl, "text-error"),
                    stat_tile("Momentum Lost", mo, "text-secondary"),
                    stat_tile("Total Events", total),
                ]
            ),

            html.Div(
                className="flex flex-wrap gap-2 items-center justify-between",
                children=[
                    html.Div(
                        className="flex flex-wrap gap-2",
                        children=[chip(lbl, val, val == "ALL") for val, lbl in FILTERS]
                    ),
                    html.Button("Mark all read", id="alerts-mark-read", n_clicks=0,
                                className="px-3 py-1.5 rounded-full text-xs font-semibold "
                                          "bg-white/5 border border-white/10 text-on-surface-variant "
                                          "hover:bg-white/10 hover:text-white transition-colors cursor-pointer"),
                ]
            ),

            html.Div(id="alerts-table", children=build_table(df, "ALL")),
        ]
    )


@dash.callback(
    Output("alerts-filter", "data"),
    [Output(f"alert-chip-{value}", "className") for value, _ in FILTERS],
    [Input(f"alert-chip-{value}", "n_clicks") for value, _ in FILTERS],
    prevent_initial_call=True,
)
def _set_filter(*_clicks):
    triggered = dash.ctx.triggered_id
    if not triggered:
        raise dash.exceptions.PreventUpdate
    selected_value = triggered.replace("alert-chip-", "")
    
    classes = [chip_class(val == selected_value) for val, _ in FILTERS]
    return (selected_value, *classes)


@dash.callback(
    Output("alerts-table", "children"),
    Input("alerts-filter", "data"),
)
def _render_table(flt):
    return build_table(load_alerts(), flt or "ALL")


@dash.callback(
    Output("alerts-last-visit", "data"),
    Output("alerts-unread-banner", "children"),
    Input("alerts-mark-read", "n_clicks"),
    State("alerts-last-visit", "data"),
    prevent_initial_call=True,
)
def _mark_read(n_clicks, last_visit):
    import datetime as _dt
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if n_clicks:
        return now, html.Div("All alerts marked as read.",
                             className="glass-panel rounded-xl p-3 font-body-md text-primary")
    raise dash.exceptions.PreventUpdate


@dash.callback(
    Output("alerts-unread-banner", "children", allow_duplicate=True),
    Input("alerts-last-visit", "data"),
    prevent_initial_call='initial_duplicate',
)
def _unread_banner(last_visit):
    df = load_alerts()
    if df is None or df.empty:
        return None

    df = df.copy()
    df["detected_at"] = df["detected_at"].astype(str)

    if not last_visit:
        # First ever visit: everything is new. Set the cursor to now going forward.
        unread = len(df)
        msg = ("This is your first visit — subscribe on the Alerts page bookmark. "
               f"{unread} historical event(s) on record.")
    else:
        unread = int((df["detected_at"] > str(last_visit)).sum())
        msg = f"{unread} alert(s) since your last visit."

    if unread == 0:
        return None
    return html.Div(
        className="glass-panel rounded-xl p-4 flex items-center gap-3 border-l-4 border-error",
        children=[
            html.Span("notifications_active", className="material-symbols-outlined text-error"),
            html.Span(msg, className="font-body-md text-on-surface"),
        ]
    )
