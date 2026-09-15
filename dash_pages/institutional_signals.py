import dash
from dash import html, dcc, Input, Output
import pandas as pd
import os
from functools import lru_cache

dash.register_page(__name__, path='/institutional-signals', name='Institutional Signals', title='Pro Spike - Institutional Signals')

LEGACY_FILE = os.path.join("data", "legacy_watchlist.csv")
ALPHA_FILE = os.path.join("data", "sbia_alpha_watchlist.csv")
FLEXGATE_FILE = os.path.join("data", "sbia_flexgate_watchlist.csv")
FLEXGATE2_FILE = os.path.join("data", "sbia_flexgate2_watchlist.csv")
SBIA_LEDGER = os.path.join("data", "sbia_ledger.csv")
FLEXGATE_LEDGER = os.path.join("data", "flexgate_ledger.csv")
FLEXGATE2_LEDGER = os.path.join("data", "flexgate2_ledger.csv")
CLOUD_FILE = os.path.join("data", "dashboard_cloud.csv")

# Display caps: keep tab payloads small (Tailwind CDN JIT rescans every DOM
# injection, so huge tables freeze the browser). Most recent rows are kept.
MAX_SIM_ROWS = 40
MAX_COMPLETED_ROWS = 40

TAB_STYLE = {
    "background": "rgba(255,255,255,0.03)",
    "border": "1px solid rgba(255,255,255,0.08)",
    "borderRadius": "12px",
    "padding": "10px 16px",
    "marginRight": "8px",
    "marginBottom": "8px",
    "color": "var(--text-secondary)",
    "fontWeight": "600",
    "fontSize": "13px",
    "letterSpacing": "0.02em",
    "minHeight": "44px",
    "display": "flex",
    "alignItems": "center",
}
TAB_STYLE_SELECTED = {
    **TAB_STYLE,
    "background": "rgba(255,255,255,0.06)",
    "borderColor": "rgba(90,240,179,0.4)",
    "color": "var(--text-primary)",
}


@lru_cache(maxsize=16)
def _read_csv(path, mtime):
    """Cached CSV reader keyed on file mtime so renders stay cheap."""
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def load_csv(path):
    if not os.path.exists(path):
        return None
    try:
        return _read_csv(path, os.path.getmtime(path))
    except OSError:
        return None


def _empty_panel(msg):
    return html.Div(msg, className="glass-panel rounded-xl p-6 font-body-md text-outline text-center")


def _f(v, template, pre=""):
    try:
        if v is None or pd.isna(v):
            return "-"
        return pre + template.format(float(v))
    except (TypeError, ValueError):
        return "-"


def _section_header(text, accent="#5af0b3", size="15px"):
    return html.Div(
        text,
        className="font-label-caps uppercase tracking-widest font-bold text-on-surface-variant mt-6 mb-3",
        style={"borderLeft": f"3px solid {accent}", "paddingLeft": "10px", "fontSize": size},
    )


def _template(columns, wide=None):
    """Grid track template: per-column overrides (by column name) for wide content."""
    wide = wide or {}
    return " ".join(wide.get(c, "minmax(0, 1fr)") for c in columns)


def _grid_table(columns, rows, min_width=760, wide=None):
    style = {"gridTemplateColumns": _template(columns, wide)}
    
    header_cells = []
    for i, c in enumerate(columns):
        if i == 0:
            header_cells.append(html.Div(c, className="sticky left-0 z-30 bg-[#0a0a0a] pr-2 border-r border-white/10 -ml-4 pl-4 py-3 -my-3"))
        else:
            header_cells.append(html.Div(c))
            
    header = html.Div(
        className="grid gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant break-words sticky top-0 z-20 bg-[#0a0a0a]",
        style=style,
        children=header_cells,
    )
    inner_wrapper = html.Div(
        style={"minWidth": f"{min_width}px"},
        children=[header] + rows,
    )
    return html.Div(
        className="glass-panel rounded-2xl overflow-x-auto",
        tabIndex="0",
        **{"aria-label": "Data table"},
        children=[inner_wrapper],
    )


def _grid_row(cells, tpl, row_class=""):
    style = {"gridTemplateColumns": tpl}
    if cells:
        cells[0] = html.Div(cells[0], className="sticky left-0 z-10 bg-[#0a0a0a] pr-2 border-r border-white/10 -ml-4 pl-4 py-3 -my-3")
    return html.Div(
        className=f"grid gap-2 px-4 py-3 items-center font-data-md text-sm border-b border-outline-variant/40 hover:bg-white/5 transition-colors break-words {row_class}",
        style=style,
        children=cells,
    )


def _fmt_date(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d %b %Y")


def _sl_tp_str(v, entry, sign_prefix=""):
    try:
        if pd.isna(v):
            return "N/A"
        if pd.notna(entry) and float(entry) > 0:
            pct = (float(v) - float(entry)) / float(entry) * 100
            return f"₹{float(v):.2f} ({sign_prefix}{pct:.1f}%)"
        return f"₹{float(v):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _num(v, default=None):
    try:
        f = float(v)
        return default if pd.isna(f) else f
    except (TypeError, ValueError):
        return default


def _prob_cell(v):
    pct = _num(v)
    if pct is None:
        return html.Div("-", className="text-on-surface-variant")
    bar = "bg-primary" if pct >= 80 else ("bg-secondary" if pct >= 60 else "bg-on-surface-variant")
    txt = "text-primary" if pct >= 80 else ("text-secondary" if pct >= 60 else "text-on-surface-variant")
    return html.Div(
        className="flex items-center gap-2",
        children=[
            html.Div(className=f"h-1.5 rounded-full {bar}", style={"width": f"{min(pct, 100)}%", "minWidth": "4px"}),
            html.Span(f"{pct:.1f}%", className=f"{txt}"),
        ],
    )


def legacy_table():
    df = load_csv(LEGACY_FILE)
    if df is None:
        return _empty_panel("Legacy watchlist not found.")
    if df.empty:
        return _empty_panel("No legacy signals found.")

    is_today = pd.Series([False] * len(df))
    if "DATE" in df.columns:
        date_raw = pd.to_datetime(df["DATE"], errors="coerce")
        df = df.assign(DATE=date_raw.dt.strftime("%d %b %Y"))
        if date_raw.notna().any():
            is_today = date_raw == date_raw.max()

    cols = ["DATE", "SYMBOL", "EXCHANGE", "CLOSE", "AI_SCORE", "SIS", "Whale_Density", "Implied_Trades", "STABILITY_RAW", "TRIGGER_COUNT_30D", "DELIV_PER", "DELIVERY_TURNOVER", "ATW"]
    avail = [c for c in cols if c in df.columns]
    wide = {"DATE": "minmax(115px, 1fr)", "SYMBOL": "minmax(190px, 1.8fr)"}
    tpl = _template(avail, wide)
    fmt = {
        "CLOSE": lambda v: _f(v, "{:.2f}", "₹"),
        "AI_SCORE": lambda v: _f(v, "{:.2f}"),
        "SIS": lambda v: _f(v, "{:.2f}"),
        "Whale_Density": lambda v: _f(v, "{:.2f}"),
        "Implied_Trades": lambda v: _f(v, "{:,.0f}"),
        "STABILITY_RAW": lambda v: _f(v, "{:.2f}"),
        "TRIGGER_COUNT_30D": lambda v: "-" if pd.isna(v) else (f"{int(v)}" if _num(v) is not None else "-"),
        "DELIV_PER": lambda v: _f(v, "{:.2f}%"),
        "DELIVERY_TURNOVER": lambda v: _f(v, "{:,.0f}", "₹"),
        "ATW": lambda v: _f(v, "{:,.0f}", "₹"),
    }

    rows = []
    for i, (_, r) in enumerate(df.reset_index(drop=True).iterrows()):
        sym = str(r.get("SYMBOL", ""))
        if i < len(is_today) and bool(is_today.iloc[i]):
            sym = f"🆕 {sym}"
        if "REPEAT_FLAG" in df.columns and "TRIGGER_COUNT_30D" in df.columns:
            tc_raw = _num(r.get("TRIGGER_COUNT_30D"))
            try:
                if bool(r.get("REPEAT_FLAG")) and tc_raw is not None:
                    sym = f"{sym} 🔥({int(tc_raw)})"
            except (TypeError, ValueError):
                pass

        row_class = "bg-[rgba(72,187,120,0.12)]" if (i < len(is_today) and bool(is_today.iloc[i])) else ""
        tc = r.get("TRIGGER_COUNT_30D")
        stab = r.get("STABILITY_RAW")
        try:
            if tc is not None and pd.notna(tc) and float(tc) > 2:
                row_class = "bg-[rgba(255,76,76,0.12)] text-[#ff4c4c]"
            elif tc is not None and pd.notna(tc) and float(tc) == 1 and stab is not None and pd.notna(stab) and float(stab) > 3.16:
                row_class = "bg-[rgba(0,255,204,0.10)] text-[#00ffcc] font-bold"
        except (TypeError, ValueError):
            row_class = row_class

        cells = []
        for c in avail:
            if c == "SYMBOL":
                cells.append(html.Div(sym, className="font-semibold"))
            elif c == "DATE":
                cells.append(html.Div(str(r.get(c, "-")) if pd.notna(r.get(c)) else "-", className="text-on-surface-variant"))
            elif c == "EXCHANGE":
                cells.append(html.Div(str(r.get(c, "-")), className="text-on-surface-variant uppercase text-xs"))
            elif c in fmt:
                cells.append(html.Div(fmt[c](r.get(c)), className="text-on-surface"))
            else:
                raw = r.get(c)
                cells.append(html.Div("-" if raw is None or pd.isna(raw) else str(raw), className="text-on-surface"))
        rows.append(_grid_row(cells, tpl, row_class))

    return _grid_table(avail, rows, min_width=1140, wide=wide)


def alpha_table():
    df = load_csv(ALPHA_FILE)
    if df is None:
        return _empty_panel("Run calculate_active_signals.py to generate the Alpha Watchlist.")
    if df.empty:
        return _empty_panel("⚠️ No stocks passed the Path A ML Gate today.")

    if "DATE" in df.columns:
        df = df.assign(DATE=_fmt_date(df["DATE"]))

    cols = ["DATE", "SYMBOL", "EXCHANGE", "ENTRY_PRICE", "CLOSE", "AI_WIN_PROBABILITY", "SIS", "Whale_Density", "Implied_Trades", "STOP_LOSS", "TAKE_PROFIT", "REC_POS_SIZE_INR", "ATR14"]
    avail = [c for c in cols if c in df.columns]
    wide = {"DATE": "minmax(115px, 1fr)", "SYMBOL": "minmax(170px, 1.6fr)", "STOP_LOSS": "minmax(150px, 1.3fr)", "TAKE_PROFIT": "minmax(150px, 1.3fr)"}
    tpl = _template(avail, wide)

    rows = []
    for _, r in df.iterrows():
        entry = r.get("ENTRY_PRICE")
        cells = []
        for c in avail:
            if c == "SYMBOL":
                cells.append(html.Div(str(r.get(c, "")), className="font-semibold"))
            elif c == "DATE":
                cells.append(html.Div(str(r.get(c, "-")) if pd.notna(r.get(c)) else "-", className="text-on-surface-variant"))
            elif c == "EXCHANGE":
                cells.append(html.Div(str(r.get(c, "-")), className="text-on-surface-variant uppercase text-xs"))
            elif c == "AI_WIN_PROBABILITY":
                cells.append(_prob_cell(r.get(c)))
            elif c == "STOP_LOSS":
                cells.append(html.Div(_sl_tp_str(r.get(c), entry), className="text-error"))
            elif c == "TAKE_PROFIT":
                cells.append(html.Div(_sl_tp_str(r.get(c), entry, "+"), className="text-primary"))
            elif c in ("ENTRY_PRICE", "CLOSE", "ATR14"):
                cells.append(html.Div(_f(r.get(c), "{:.2f}", "₹"), className="text-on-surface"))
            elif c == "REC_POS_SIZE_INR":
                cells.append(html.Div(_f(r.get(c), "{:,.0f}", "₹"), className="text-on-surface"))
            elif c in ("SIS", "Whale_Density"):
                cells.append(html.Div(_f(r.get(c), "{:.2f}"), className="text-on-surface"))
            elif c == "Implied_Trades":
                cells.append(html.Div(_f(r.get(c), "{:,.0f}"), className="text-on-surface"))
            else:
                raw = r.get(c)
                cells.append(html.Div("-" if raw is None or pd.isna(raw) else str(raw), className="text-on-surface"))
        rows.append(_grid_row(cells, tpl))

    return _grid_table(avail, rows, min_width=1280, wide=wide)


_STATUS_BADGE = {
    "HIT_TP": "text-[#2ecc71] font-semibold",
    "HIT_SL": "text-[#e74c3c] font-semibold",
    "SUSPENDED": "text-[#f39c12]",
    "MOMENTUM_LOST": "text-[#95a5a6]",
}


def completed_trades():
    df = load_csv(SBIA_LEDGER)
    if df is None or "STATUS" not in df.columns:
        return None
    completed = df[df["STATUS"] != "ACTIVE"].copy()
    if completed.empty:
        return html.Div("No completed trades recorded yet.", className="p-4 font-body-md text-outline text-center")

    if "ENTRY_DATE" in completed.columns:
        completed = completed.sort_values("ENTRY_DATE", ascending=False)
    total_completed = len(completed)
    if total_completed > MAX_COMPLETED_ROWS:
        completed = completed.head(MAX_COMPLETED_ROWS)

    if "ENTRY_DATE" in completed.columns:
        completed["ENTRY_DATE"] = _fmt_date(completed["ENTRY_DATE"])
    if "EXIT_DATE" in completed.columns:
        completed["EXIT_DATE"] = _fmt_date(completed["EXIT_DATE"])

    cols = ["ENTRY_DATE", "SYMBOL", "STATUS", "ENTRY_AI_PROB", "ENTRY_WHALE_DENSITY", "ENTRY_PRICE", "EXIT_PRICE", "EXIT_DATE", "STOP_LOSS", "TAKE_PROFIT"]
    avail = [c for c in cols if c in completed.columns]
    wide = {"ENTRY_DATE": "minmax(115px, 1fr)", "SYMBOL": "minmax(165px, 1.5fr)", "EXIT_PRICE": "minmax(150px, 1.3fr)", "STOP_LOSS": "minmax(145px, 1.25fr)", "TAKE_PROFIT": "minmax(145px, 1.25fr)"}
    tpl = _template(avail, wide)

    rows = []
    for _, r in completed.iterrows():
        entry = r.get("ENTRY_PRICE")
        cells = []
        for c in avail:
            if c == "SYMBOL":
                cells.append(html.Div(str(r.get(c, "")), className="font-semibold"))
            elif c == "STATUS":
                badge = _STATUS_BADGE.get(str(r.get(c, "")), "text-on-surface-variant")
                cells.append(html.Div(str(r.get(c, "-")), className=f"{badge}"))
            elif c in ("ENTRY_DATE", "EXIT_DATE"):
                cells.append(html.Div(str(r.get(c, "-")) if pd.notna(r.get(c)) else "-", className="text-on-surface-variant"))
            elif c == "ENTRY_AI_PROB":
                cells.append(html.Div(_f(r.get(c), "{:.1f}%"), className="text-on-surface"))
            elif c == "ENTRY_WHALE_DENSITY":
                cells.append(html.Div(_f(r.get(c), "{:.2f}"), className="text-on-surface"))
            elif c == "ENTRY_PRICE":
                cells.append(html.Div(_f(r.get(c), "{:.2f}", "₹"), className="text-on-surface"))
            elif c == "EXIT_PRICE":
                exit_n = _num(r.get(c))
                entry_n = _num(entry)
                if exit_n is None:
                    cells.append(html.Div("N/A", className="text-on-surface-variant"))
                else:
                    if entry_n is not None and entry_n > 0:
                        sign = "+" if exit_n >= entry_n else ""
                        s = f"₹{exit_n:.2f} ({sign}{(exit_n - entry_n) / entry_n * 100:.1f}%)"
                    else:
                        s = f"₹{exit_n:.2f}"
                    color = "text-primary" if (entry_n is not None and exit_n >= entry_n) else "text-error"
                    cells.append(html.Div(s, className=f"{color}"))
            elif c == "STOP_LOSS":
                cells.append(html.Div(_sl_tp_str(r.get(c), entry), className="text-error"))
            elif c == "TAKE_PROFIT":
                cells.append(html.Div(_sl_tp_str(r.get(c), entry, "+"), className="text-primary"))
            else:
                raw = r.get(c)
                cells.append(html.Div("-" if raw is None or pd.isna(raw) else str(raw), className="text-on-surface"))
        rows.append(_grid_row(cells, tpl))

    completed_footer = []
    if total_completed > MAX_COMPLETED_ROWS:
        completed_footer.append(
            html.Div(
                f"Showing {MAX_COMPLETED_ROWS} most recent of {total_completed} completed trades.",
                className="px-4 py-2 font-label-caps text-[10px] text-outline uppercase tracking-wider",
            )
        )

    return html.Details(
        className="glass-panel rounded-2xl mt-4 overflow-x-auto",
        tabIndex="0",
        **{"aria-label": "Completed trades data table"},
        children=[
            html.Summary("🕰️ Historical / Completed Trades", className="px-4 py-3 font-label-caps text-on-surface-variant uppercase tracking-wider text-xs cursor-pointer select-none"),
            html.Div(
                style={"minWidth": "1150px"},
                children=[
                    html.Div(
                        className="grid gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant break-words",
                        style={"gridTemplateColumns": tpl},
                        children=[html.Div(c) for c in avail],
                    )
                ] + rows + completed_footer,
            ),
        ],
    )


def flexgate_table(path, missing_msg, empty_msg):
    df = load_csv(path)
    if df is None:
        return _empty_panel(missing_msg)
    if df.empty:
        return _empty_panel(empty_msg)

    if "DATE" in df.columns:
        df = df.assign(DATE=_fmt_date(df["DATE"]))

    has_ai = ("AI_WIN_PROBABILITY" in df.columns) and ("AI_APPROVED" in df.columns)
    cols = ["DATE", "SYMBOL", "EXCHANGE", "CLOSE", "AI_STATUS", "SIS", "Whale_Density", "Implied_Trades", "CHANDELIER_EXIT", "REC_POS_SIZE_INR", "ATR14"]
    avail = [c for c in cols if c in df.columns or c == "AI_STATUS"]
    if not has_ai:
        avail = [c for c in avail if c != "AI_STATUS"]
    wide = {"DATE": "minmax(115px, 1fr)", "SYMBOL": "minmax(170px, 1.5fr)"}
    tpl = _template(avail, wide)

    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in avail:
            if c == "SYMBOL":
                cells.append(html.Div(str(r.get(c, "")), className="font-semibold"))
            elif c == "DATE":
                cells.append(html.Div(str(r.get(c, "-")) if pd.notna(r.get(c)) else "-", className="text-on-surface-variant"))
            elif c == "EXCHANGE":
                cells.append(html.Div(str(r.get(c, "-")), className="text-on-surface-variant uppercase text-xs"))
            elif c == "AI_STATUS":
                prob = _num(r.get("AI_WIN_PROBABILITY"))
                approved = bool(r.get("AI_APPROVED"))
                if prob is None:
                    cells.append(html.Div("-", className="text-on-surface-variant"))
                elif approved:
                    cells.append(html.Div(f"✅ {prob:.1f}%", className="text-[#2ecc71] font-semibold bg-[rgba(46,204,113,0.10)] px-2 py-0.5 rounded-full w-fit text-xs"))
                else:
                    cells.append(html.Div(f"❌ {prob:.1f}%", className="text-[#e74c3c] italic bg-[rgba(231,76,60,0.08)] px-2 py-0.5 rounded-full w-fit text-xs"))
            elif c in ("CLOSE", "ATR14", "CHANDELIER_EXIT"):
                cells.append(html.Div(_f(r.get(c), "{:.2f}", "₹"), className="text-on-surface"))
            elif c == "REC_POS_SIZE_INR":
                cells.append(html.Div(_f(r.get(c), "{:,.0f}", "₹"), className="text-on-surface"))
            elif c in ("SIS", "Whale_Density"):
                cells.append(html.Div(_f(r.get(c), "{:.2f}"), className="text-on-surface"))
            elif c == "Implied_Trades":
                cells.append(html.Div(_f(r.get(c), "{:,.0f}"), className="text-on-surface"))
            else:
                raw = r.get(c)
                cells.append(html.Div("-" if raw is None or pd.isna(raw) else str(raw), className="text-on-surface"))
        rows.append(_grid_row(cells, tpl))

    return _grid_table(avail, rows, min_width=1080, wide=wide)


def _sim_tile(title, accent, stat_a_label, stat_a_value, stat_b_label, stat_b_value, stat_b_class=""):
    return html.Div(
        className="glass-panel rounded-2xl p-5",
        style={"borderTop": f"3px solid {accent}"},
        children=[
            html.Div(title, className="font-label-sm text-[10px] font-bold uppercase tracking-widest mb-3", style={"color": accent}),
            html.Div(
                className="flex justify-between items-end gap-4",
                children=[
                    html.Div(
                        children=[
                            html.Div(stat_a_label, className="font-body-md text-[11px] text-on-surface-variant font-semibold mb-1"),
                            html.Div(stat_a_value, className="font-headline-md text-[24px] font-semibold text-on-surface tracking-tight"),
                        ]
                    ),
                    html.Div(
                        className="text-right",
                        children=[
                            html.Div(stat_b_label, className="font-body-md text-[11px] text-on-surface-variant font-semibold mb-1"),
                            html.Div(stat_b_value, className=f"text-[18px] font-semibold font-data-md {stat_b_class}"),
                        ]
                    ),
                ],
            ),
        ],
    )


def velocity_simulation(ledger_csv, risk_pct, ai_threshold=None, title="₹10L Velocity Simulation Status"):
    """Port of dashboard_full.py render_velocity_simulation — arithmetic verbatim."""
    capital = 1000000.0
    risk_per_trade = capital * risk_pct
    sim_records = []
    total_realized = 0.0
    total_unrealized = 0.0
    wins = 0
    losses = 0
    total_allocated = 0.0
    active_trades_count = 0
    current_equity = capital
    win_rate = 0.0

    ledger_full = load_csv(ledger_csv)
    if ledger_full is not None:
        if ai_threshold is not None and "ENTRY_AI_PROB" in ledger_full.columns:
            ledger_full = ledger_full[ledger_full["ENTRY_AI_PROB"] >= ai_threshold]
        if len(ledger_full) > 0:
            latest_prices = {}
            live = load_csv(CLOUD_FILE)
            if live is not None and {"SYMBOL", "CLOSE"}.issubset(live.columns):
                try:
                    latest_prices = live.drop_duplicates(subset=["SYMBOL"]).set_index("SYMBOL")["CLOSE"].to_dict()
                except Exception:
                    latest_prices = {}

            for _, row in ledger_full.iterrows():
                sym = row.get("SYMBOL", "")
                entry = row.get("ENTRY_PRICE")
                sl = row.get("STOP_LOSS")
                status = row.get("STATUS", "")
                entry = _num(entry, float("nan"))
                sl = _num(sl, float("nan"))

                if pd.isna(entry) or pd.isna(sl) or entry <= sl:
                    invested = capital * 0.10
                    shares = invested / entry if entry > 0 else 0
                else:
                    sl_dist = entry - sl
                    shares = risk_per_trade / sl_dist
                    invested = shares * entry
                    if invested > capital * 0.10:
                        invested = capital * 0.10
                        shares = invested / entry

                r_pnl = 0.0
                u_pnl = 0.0
                current_value = invested
                if status != "ACTIVE":
                    exit_px = _num(row.get("EXIT_PRICE", entry), entry)
                    r_pnl = shares * (exit_px - entry)
                    total_realized += r_pnl
                    current_value = invested + r_pnl
                    if status in ("HIT_TP", "MOMENTUM_LOST") and r_pnl > 0:
                        wins += 1
                    elif status == "HIT_SL" or r_pnl < 0:
                        losses += 1
                else:
                    current_px = _num(latest_prices.get(sym, entry), entry)
                    u_pnl = shares * (current_px - entry)
                    total_unrealized += u_pnl
                    current_value = invested + u_pnl
                    total_allocated += invested
                    active_trades_count += 1

                sim_records.append({
                    "DATE": row.get("ENTRY_DATE", ""),
                    "SYMBOL": sym,
                    "STATUS": status,
                    "INVESTED": invested,
                    "CURR_VALUE": current_value,
                    "REALIZED_PNL": r_pnl,
                    "UNREALIZED_PNL": u_pnl,
                    "TOTAL_PNL": r_pnl + u_pnl,
                    "PNL_%": ((r_pnl + u_pnl) / invested * 100) if invested > 0 else 0,
                })

            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            current_equity = capital + total_realized + total_unrealized

    realized_class = "text-[#00E5FF]" if total_realized >= 0 else "text-[#F50057]"
    unrealized_class = "text-[#00E5FF]" if total_unrealized >= 0 else "text-[#F50057]"

    tiles = html.Div(
        className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4",
        children=[
            _sim_tile(
                "Portfolio Health", "#00E5FF",
                "Current Value", f"₹{current_equity:,.0f}",
                "Realized PnL", f"{'+' if total_realized >= 0 else ''}₹{total_realized:,.0f}",
                realized_class,
            ),
            _sim_tile(
                "Live Exposure", "#FFB300",
                "Active Trades", f"{active_trades_count}",
                "Allocated Cap", f"₹{total_allocated:,.0f}",
                "text-[#FFB300]",
            ),
            _sim_tile(
                "System Efficiency", "#F50057",
                "Strategy Win Rate", f"{win_rate:.1f}%",
                "Unrealized MTM", f"{'+' if total_unrealized >= 0 else ''}₹{total_unrealized:,.0f}",
                unrealized_class,
            ),
        ],
    )

    ledger_section = []
    if sim_records:
        sim_df = pd.DataFrame(sim_records)
        sim_df = sim_df.sort_values(by="DATE", ascending=False)
        sim_cols = ["DATE", "SYMBOL", "STATUS", "INVESTED", "CURR_VALUE", "REALIZED_PNL", "UNREALIZED_PNL", "TOTAL_PNL", "PNL_%"]
        sim_wide = {"DATE": "minmax(115px, 1fr)", "SYMBOL": "minmax(160px, 1.4fr)"}
        sim_tpl = _template(sim_cols, sim_wide)
        sim_status_class = {
            "ACTIVE": "text-[#f1c40f] font-semibold",
            "HIT_TP": "text-[#2ecc71] font-semibold",
            "HIT_SL": "text-[#e74c3c] font-semibold",
        }
        rows = []
        for _, r in sim_df.head(MAX_SIM_ROWS).iterrows():
            cells = []
            for c in sim_cols:
                v = r.get(c)
                if c in ("DATE", "SYMBOL"):
                    cells.append(html.Div("-" if v is None or pd.isna(v) else str(v), className="text-on-surface" if c == "SYMBOL" else "text-on-surface-variant"))
                elif c == "STATUS":
                    cells.append(html.Div("-" if v is None or pd.isna(v) else str(v), className=sim_status_class.get(str(v), "text-[#95a5a6]")))
                elif c in ("INVESTED", "CURR_VALUE"):
                    cells.append(html.Div(_f(v, "{:,.0f}", "₹"), className="text-on-surface"))
                elif c == "PNL_%":
                    n = _num(v)
                    cls = "text-[#2ecc71]" if (n is not None and n > 0) else ("text-[#e74c3c]" if (n is not None and n < 0) else "text-[#95a5a6]")
                    cells.append(html.Div(_f(v, "{:+.1f}%"), className=cls))
                else:
                    n = _num(v)
                    cls = "text-[#2ecc71]" if (n is not None and n > 0) else ("text-[#e74c3c]" if (n is not None and n < 0) else "text-[#95a5a6]")
                    cells.append(html.Div(f"{'+' if (n is not None and n >= 0) else ''}₹{n:,.0f}" if n is not None else "-", className=cls))
            rows.append(_grid_row(cells, sim_tpl))

        if len(sim_df) > MAX_SIM_ROWS:
            rows.append(
                html.Div(
                    f"Showing {MAX_SIM_ROWS} most recent of {len(sim_df)} simulated trades.",
                    className="px-4 py-2 font-label-caps text-[10px] text-outline uppercase tracking-wider",
                )
            )

        ledger_section.append(
            html.Details(
                className="glass-panel rounded-2xl mt-4 overflow-x-auto",
                tabIndex="0",
                **{"aria-label": "Simulation ledger data table"},
                children=[
                    html.Summary("📝 View Trade-by-Trade Simulation Ledger", className="px-4 py-3 font-label-caps text-on-surface-variant uppercase tracking-wider text-xs cursor-pointer select-none"),
                    html.Div(
                        style={"minWidth": "950px"},
                        children=[
                            html.Div(
                                className="grid gap-2 px-4 py-3 font-label-caps text-[10px] text-on-surface-variant uppercase tracking-wider border-b border-outline-variant break-words",
                                style={"gridTemplateColumns": sim_tpl},
                                children=[html.Div(c) for c in sim_cols],
                            )
                        ] + rows,
                    ),
                ],
            )
        )

    return html.Div(
        children=[
            html.Div(title, className="font-label-sm text-[10px] font-bold text-on-surface-variant uppercase tracking-widest mt-6 mb-1"),
            tiles,
        ] + ledger_section
    )


def _tab_legacy():
    return [
        _section_header("🔬 Phase 1: Institutional Screener (Raw ATW Unverified)"),
        legacy_table(),
    ]


def _tab_alpha():
    return [
        _section_header("Path A: Alpha Markups", "#FFB300"),
        alpha_table(),
        _section_header("Trade Execution Log", "#F50057"),
        completed_trades() or html.Div("No completed trades recorded yet.", className="p-4 font-body-md text-outline text-center"),
        velocity_simulation(SBIA_LEDGER, risk_pct=0.003),
    ]


def _tab_flexgate():
    return [
        html.Div(
            className="glass-panel rounded-2xl p-4 mt-6 mb-2 font-body-md",
            style={"borderLeft": "3px solid #8ea2ff"},
            children=[
                html.Div("🔭 Path B: Base-Loading (FlexGate)", className="font-headline-sm text-[#8ea2ff] font-semibold mb-1"),
                html.P("These signals survived the ICT Box anomalies (exactly 2 alerts in 10 days). Trend-Following Notice: No Fixed Profit Target. Use the Chandelier Exit.", className="text-on-surface-variant text-sm mb-0"),
            ],
        ),
        flexgate_table(FLEXGATE_FILE, "Run calculate_active_signals.py to generate the FlexGate Watchlist.", "⚠️ No stocks passed the strict FlexGate logic today."),
        velocity_simulation(FLEXGATE_LEDGER, risk_pct=0.002, ai_threshold=65.0, title="₹10L FlexGate Simulation Status"),
    ]


def _tab_flexgate2():
    return [
        html.Div(
            className="glass-panel rounded-2xl p-4 mt-6 mb-2 font-body-md",
            style={"borderLeft": "3px solid #e74c3c"},
            children=[
                html.Div("🤖 FlexGate 2.0 (ML Engine)", className="font-headline-sm text-[#ffb4ab] font-semibold mb-1"),
                html.P("These signals survived the ML Heuristic Bouncer (ATR > 3.5%) and scored ≥ 60% on the Random Forest engine.", className="text-on-surface-variant text-sm mb-0"),
            ],
        ),
        flexgate_table(FLEXGATE2_FILE, "Run flexgate_2_scanner.py to generate the FlexGate 2.0 Watchlist.", "⚠️ No stocks passed the strict FlexGate 2.0 ML logic today."),
        velocity_simulation(FLEXGATE2_LEDGER, risk_pct=0.002, ai_threshold=60.0, title="₹10L FlexGate 2.0 Simulation Status"),
    ]


TAB_BUILDERS = {
    "legacy": _tab_legacy,
    "alpha": _tab_alpha,
    "flexgate": _tab_flexgate,
    "flexgate2": _tab_flexgate2,
}


@dash.callback(
    Output("engine-tab-content", "children"),
    Input("engine-tabs", "value"),
    prevent_initial_call=True,
)
def render_engine_tab(tab_value):
    builder = TAB_BUILDERS.get(tab_value)
    if builder is None:
        return html.Div("Unknown engine tab.", className="glass-panel rounded-xl p-6 font-body-md text-outline text-center")
    return builder()


def layout():
    return html.Div(
        className="px-4 md:px-6 pt-6 pb-32 w-full flex flex-col gap-4",
        children=[
            html.Section(
                className="flex flex-col gap-1",
                children=[
                    html.H1("Institutional Signals", className="font-display-lg text-headline-lg md:text-[36px] text-on-surface tracking-tight"),
                    html.P("Multi-Strategy Execution Engine — high-conviction data signals for professional trading.", className="font-body-md text-on-surface-variant"),
                ],
            ),
            html.Div(
                className="glass-panel rounded-2xl p-4 font-body-md text-on-surface-variant",
                children=[
                    "This dual-engine system isolates distinct institutional profiles: ",
                    html.Strong("High-Velocity Alpha Markups (Path A)", className="text-on-surface"),
                    " and ",
                    html.Strong("Quiet Base-Loading Breakouts (Path B)", className="text-on-surface"),
                    ".",
                ],
            ),
            html.Div(
                className="w-full overflow-x-auto hide-scrollbar touch-pan-x mb-2",
                children=[
                    dcc.Tabs(
                        id="engine-tabs",
                        value="legacy",
                        parent_className="w-full min-w-max flex",
                        parent_style={"borderBottom": "none", "backgroundColor": "transparent"},
                        children=[
                            dcc.Tab(label="🔬 Legacy Screener", value="legacy", style=TAB_STYLE, selected_style=TAB_STYLE_SELECTED),
                            dcc.Tab(label="🏆 SBIA Alpha Engine (High-Velocity)", value="alpha", style=TAB_STYLE, selected_style=TAB_STYLE_SELECTED),
                            dcc.Tab(label="🔭 SBIA FlexGate Engine (Base-Loading)", value="flexgate", style=TAB_STYLE, selected_style=TAB_STYLE_SELECTED),
                            dcc.Tab(label="🤖 FlexGate 2.0 (ML Engine)", value="flexgate2", style=TAB_STYLE, selected_style=TAB_STYLE_SELECTED),
                        ],
                    )
                ]
            ),
            html.Div(id="engine-tab-content", children=_tab_legacy()),
        ],
    )
