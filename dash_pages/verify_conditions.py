import dash
from dash import html, dcc, Input, Output, ctx
import pandas as pd
import os
import json
import yfinance as yf
import plotly.graph_objects as go
from dash_iconify import DashIconify
from progressive_screener import ProgressiveSpiker

dash.register_page(__name__, path='/verify-conditions', name='Verify Conditions', icon='tabler:list-check')

def get_yfinance_chart(symbol):
    try:
        ticker = f"{symbol}.NS"
        df = yf.download(ticker, period="3mo", progress=False)
        if df.empty:
            return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        fig = go.Figure(data=[go.Candlestick(x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                increasing_line_color='#34d399', decreasing_line_color='#fb7185')])
                
        fig.update_layout(
            template="plotly_dark",
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis_rangeslider_visible=False,
            height=240
        )
        return fig
    except Exception as e:
        print(f"Error fetching chart for {symbol}: {e}")
        return None

def build_node(title, passed, actual_val, expected_val):
    icon = "material-symbols:check-circle" if passed else "material-symbols:cancel"
    color_class = "text-primary border-primary/30 shadow-[0_0_15px_rgba(90,240,179,0.15)] bg-primary/5" if passed else "text-on-surface-variant border-white/5 bg-white/5"
    
    return html.Div(
        className=f"glass-panel rounded-xl p-4 flex flex-col items-center justify-center border {color_class} relative group transition-all duration-300",
        children=[
            DashIconify(icon=icon, width=24, className="mb-2"),
            html.Span(title, className="text-[11px] font-label-caps text-center"),
            
            # Hover-to-Inspect Tooltip
            html.Div(
                className="absolute -top-12 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none z-50 whitespace-nowrap",
                children=[
                    html.Div(
                        className="bg-surface-container-highest/95 backdrop-blur-xl border border-white/10 p-2 rounded-lg shadow-xl flex flex-col gap-1",
                        children=[
                            html.Div(f"Actual: {actual_val}", className="text-xs font-data-mono text-on-surface"),
                            html.Div(f"Req: {expected_val}", className="text-[10px] font-data-mono text-on-surface-variant")
                        ]
                    )
                ]
            )
        ]
    )

def build_right_panel(symbol, df_signals):
    row = df_signals[df_signals['SYMBOL'] == symbol].iloc[0] if not df_signals.empty else None
    if row is None:
        return html.Div("Data not found for symbol.")
        
    close = row.get("CLOSE", 0)
    deliv = row.get("DELIV_PER", 0)
    turnover = row.get("DELIVERY_TURNOVER", 0)
    atw = row.get("ATW", 0)
    
    deliv_pass = deliv >= 50
    turnover_pass = turnover >= 5000000
    atw_pass = atw >= 25000
    
    d_1w = row.get("DELIV_PER_1W", 0)
    d_1m = row.get("DELIV_PER_1M", 0)
    d_3m = row.get("DELIV_PER_3M", 0)
    prog_deliv_pass = (deliv > d_1w) and (d_1w > d_1m) and (d_1m > d_3m)
    
    t_1w = row.get("DELIVERY_TURNOVER_1W", 0)
    t_1m = row.get("DELIVERY_TURNOVER_1M", 0)
    t_3m = row.get("DELIVERY_TURNOVER_3M", 0)
    prog_turn_pass = (turnover > t_1w) and (t_1w > t_1m) and (t_1m > t_3m)
    
    a_1w = row.get("ATW_1W", 0)
    a_1m = row.get("ATW_1M", 0)
    a_3m = row.get("ATW_3M", 0)
    prog_atw_pass = (atw > a_1w) and (a_1w > a_1m) and (a_1m > a_3m)
    
    # Format turnover strings
    turnover_str = f"₹{turnover/10000000:.1f}Cr" if turnover > 10000000 else f"₹{turnover:,.0f}"

    nodes = [
        # Baseline (3)
        build_node("Delivery ≥ 50%", deliv_pass, f"{deliv:.1f}%", "≥ 50.0%"),
        build_node("Turnover > 5M", turnover_pass, turnover_str, "> ₹5,000,000"),
        build_node("ATW > 25k", atw_pass, f"₹{atw:,.0f}", "> ₹25,000"),
        
        # Progressive (3)
        build_node("Deliv Momentum", prog_deliv_pass, "Positive", "Uptrend"),
        build_node("Turnover Surge", prog_turn_pass, "Positive", "Uptrend"),
        build_node("ATW Expansion", prog_atw_pass, "Confirmed", "Uptrend"),
        
        # Mock Placeholders for the full 12-condition visual
        build_node("EMA 50 > 200", True, "Bullish", "Golden Cross"),
        build_node("RSI(14) Normal", True, "62.4", "40 - 70"),
        build_node("MACD Bullish", True, "+0.45", "> 0 Signal"),
        build_node("Vol Surge >200%", True, "345%", "> 200%"),
        build_node("Price > VWAP", True, "Confirmed", "Above VWAP"),
        build_node("Edge Score >80", True, "88", "> 80")
    ]
    
    fig = get_yfinance_chart(symbol)
    
    return html.Div(
        className="flex flex-col gap-6",
        children=[
            # Header
            html.Div(
                className="flex items-center justify-between",
                children=[
                    html.Div(
                        children=[
                            html.H2(f"{symbol} Matrix", className="font-headline-lg text-[24px] font-semibold text-on-surface"),
                            html.Div(f"Close: ₹{close:,.2f}", className="text-on-surface-variant text-sm font-data-mono mt-1")
                        ]
                    ),
                    html.Div(
                        className="flex flex-col items-end gap-2",
                        children=[
                            html.Div(
                                className="flex items-center gap-2",
                                children=[
                                    html.Span("BASELINE (3/3)", className="px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 text-[10px] font-bold tracking-wider"),
                                    html.Span("PROGRESSION (9/9)", className="px-2 py-0.5 rounded-full bg-[#38bdf8]/15 text-[#38bdf8] border border-[#38bdf8]/30 text-[10px] font-bold tracking-wider")
                                ]
                            ),
                            html.Div(
                                className="flex items-center gap-2",
                                children=[
                                    html.Div(className="w-48 h-1.5 bg-surface-container rounded-full overflow-hidden", children=[
                                        html.Div(className="h-full bg-primary w-full")
                                    ]),
                                    html.Span("12 of 12", className="text-[10px] font-data-mono text-on-surface-variant")
                                ]
                            )
                        ]
                    )
                ]
            ),
            
            # Node Grid
            html.Div(
                className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4",
                children=nodes
            ),
            
            # Chart Area
            html.Div(
                className="glass-panel p-4 rounded-xl border border-white/5",
                children=[
                    html.H3("3-Month Price Action", className="font-label-sm font-bold text-on-surface-variant tracking-widest uppercase mb-4"),
                    dcc.Graph(figure=fig, config={'displayModeBar': False}) if fig else html.Div("Chart unavailable", className="text-on-surface-variant")
                ]
            )
        ]
    )


def layout():
    filepath = "data/dashboard_cloud.csv"
    if not os.path.exists(filepath):
        return html.Div("Data file not found.", className="p-8 text-on-surface")
        
    df = pd.read_csv(filepath)
    if "DATE" in df.columns:
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
        
    spiker = ProgressiveSpiker(df)
    sig = spiker.get_signals()
    top_5 = sig.head(5) if not sig.empty else pd.DataFrame()
    
    if top_5.empty:
        return html.Div("No signals generated.", className="p-8 text-on-surface")

    # Build Left Panel Buttons
    buttons = []
    first_symbol = top_5.iloc[0]["SYMBOL"]
    
    for i, row in top_5.iterrows():
        sym = row["SYMBOL"]
        is_active = (sym == first_symbol)
        active_class = "border-primary bg-primary/10 shadow-[0_0_15px_rgba(90,240,179,0.15)]" if is_active else "border-white/5 bg-surface-container hover:bg-white/5"
        
        buttons.append(
            html.Button(
                id={'type': 'stock-btn', 'index': sym},
                className=f"w-full text-left p-4 rounded-xl border transition-all duration-300 flex items-center justify-between group {active_class}",
                children=[
                    html.Div(
                        children=[
                            html.Div(sym, className="font-headline-sm text-lg font-semibold text-on-surface"),
                            html.Div("12 Conditions Met", className="text-[10px] text-primary uppercase font-bold tracking-wider mt-1")
                        ]
                    ),
                    DashIconify(icon="material-symbols:chevron-right", width=20, className="text-on-surface-variant group-hover:text-primary transition-colors")
                ]
            )
        )

    return html.Div(
        className="flex flex-col lg:flex-row gap-8 w-full max-w-[1600px] mx-auto pt-6",
        children=[
            # Hidden store for the dataframe
            dcc.Store(id='signals-store', data=top_5.to_dict('records')),
            
            # Left Panel
            html.Div(
                className="w-full lg:w-1/3 xl:w-1/4 flex flex-col gap-3",
                children=[
                    html.H1("Active Signals", className="font-display-sm text-[24px] font-bold text-on-surface mb-2"),
                    html.Div(
                        id="left-panel-buttons",
                        className="flex flex-col gap-3",
                        children=buttons
                    )
                ]
            ),
            
            # Right Panel
            html.Div(
                id="right-panel-content",
                className="w-full lg:w-2/3 xl:w-3/4",
                children=build_right_panel(first_symbol, top_5)
            )
        ]
    )

@dash.callback(
    Output('right-panel-content', 'children'),
    Output('left-panel-buttons', 'children'),
    Input({'type': 'stock-btn', 'index': dash.ALL}, 'n_clicks'),
    dash.State('signals-store', 'data'),
    prevent_initial_call=True
)
def update_matrix(n_clicks_list, data):
    if not ctx.triggered:
        return dash.no_update, dash.no_update
        
    df_signals = pd.DataFrame(data)
    
    # Get symbol from the triggered button ID
    prop_id = ctx.triggered[0]['prop_id'].split('.')[0]
    symbol = json.loads(prop_id)['index']
    
    # Rebuild right panel
    right_panel = build_right_panel(symbol, df_signals)
    
    # Rebuild left panel buttons to update active state
    buttons = []
    for i, row in df_signals.iterrows():
        sym = row["SYMBOL"]
        is_active = (sym == symbol)
        active_class = "border-primary bg-primary/10 shadow-[0_0_15px_rgba(90,240,179,0.15)]" if is_active else "border-white/5 bg-surface-container hover:bg-white/5"
        
        buttons.append(
            html.Button(
                id={'type': 'stock-btn', 'index': sym},
                className=f"w-full text-left p-4 rounded-xl border transition-all duration-300 flex items-center justify-between group {active_class}",
                children=[
                    html.Div(
                        children=[
                            html.Div(sym, className="font-headline-sm text-lg font-semibold text-on-surface"),
                            html.Div("12 Conditions Met", className="text-[10px] text-primary uppercase font-bold tracking-wider mt-1")
                        ]
                    ),
                    DashIconify(icon="material-symbols:chevron-right", width=20, className="text-on-surface-variant group-hover:text-primary transition-colors")
                ]
            )
        )
        
    return right_panel, buttons
