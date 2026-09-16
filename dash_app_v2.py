import dash
from dash import Dash, html, dcc, Input, Output, State
from dash_iconify import DashIconify
import os

app = Dash(
    __name__,
    use_pages=True,
    pages_folder="dash_pages",
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description", "content": "Pro-spike: quantitative trading dashboard for NSE/BSE institutional accumulation, delivery volume signals, and portfolio analytics."}
    ],
    external_scripts=[
        # NOTE: no forms plugin — it forces light-theme form resets (white input
        # backgrounds, default blue/purple focus rings) that fight the dark M3 theme.
        {"src": "https://cdn.tailwindcss.com?plugins=container-queries"}
    ],
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap",
        "https://fonts.googleapis.com/css2?family=Geist:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap"
    ]
)

app.index_string = '''<!DOCTYPE html>
<html lang="en">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>'''

# Expose Flask server for gunicorn (Procfile: gunicorn dash_app_v2:server)
server = app.server


def get_icon(icon_name):
    return DashIconify(icon=icon_name, width=18, height=18)

sidebar_header = html.Div(
    className="flex items-center justify-between mb-xl px-xs",
    children=[
        html.Div(
            id="sidebar-title-container",
            children=[
                html.H1("Pro Spike", className="font-headline-sm text-headline-sm text-primary", style={"margin": 0}),
                html.P("Institutional Grade", className="font-label-caps text-label-caps text-outline whitespace-nowrap", style={"margin": 0})
            ]
        ),
        html.Button(
            id="sidebar-toggle-btn",
            title="Collapse sidebar",
            **{"aria-label": "Collapse sidebar"},
            className="text-on-surface-variant hover:text-primary transition-colors active:scale-95",
            children=[DashIconify(icon="material-symbols:menu-open", width=24, height=24, id="sidebar-toggle-icon")]
        )
    ]
)

sidebar_footer = html.Div(
    className="flex flex-col gap-md mt-auto pt-lg border-t border-outline-variant",
    children=[
        html.Button("Trade Now", id="trade-now-btn", className="w-full bg-primary text-on-primary font-headline-sm text-headline-sm rounded-lg py-sm min-h-[44px] hover:bg-primary-fixed transition-colors shadow-[0_0_15px_rgba(174,198,255,0.2)]"),
        html.A([html.Span("help_outline", className="material-symbols-outlined text-lg"), "Support"], href="#", className="flex items-center gap-md px-sm py-sm rounded-lg font-label-caps text-label-caps text-on-surface-variant hover:text-secondary hover:bg-white/5 transition-all duration-200 ease-in-out min-h-[44px]"),
        html.A([html.Span("logout", className="material-symbols-outlined text-lg"), "Logout"], href="#", className="flex items-center gap-md px-sm py-sm rounded-lg font-label-caps text-label-caps text-on-surface-variant hover:text-secondary hover:bg-white/5 transition-all duration-200 ease-in-out min-h-[44px]"),
    ]
)

sidebar = html.Nav(
    id="sidebar-el",
    className="hidden md:flex flex-col py-lg px-sm gap-xs bg-surface-container-low/80 backdrop-blur-xl h-[calc(100vh-32px)] my-4 ml-4 rounded-2xl sticky left-0 top-4 border border-white/5 shadow-[0_0_40px_rgba(0,0,0,0.5)] z-40",
    children=[
        sidebar_header,
        html.Div(id="sidebar-nav-links", className="flex-1 flex flex-col gap-base"),
        sidebar_footer
    ]
)

mobile_bottom_nav = html.Nav(
    className="mobile-bottom-nav",
    children=[
        dcc.Link(
            className="mobile-nav-item", id="nav-btn-dashboard", href="/",
            children=[html.Span("leaderboard", className="material-symbols-outlined nav-icon"), html.Span("Dashboard")]
        ),
        dcc.Link(
            className="mobile-nav-item", id="nav-btn-signals", href="/signals",
            children=[html.Span("bolt", className="material-symbols-outlined nav-icon"), html.Span("Signals")]
        ),
        dcc.Link(
            className="mobile-nav-item", id="nav-btn-watchlist", href="/watchlist",
            children=[html.Span("bookmark", className="material-symbols-outlined nav-icon"), html.Span("Watchlist")]
        ),
        html.Div(
            id="mobile-vikram-tab",
            role="button",
            tabIndex="0",
            **{"aria-label": "Open Vikram AI"},
            className="mobile-nav-item cursor-pointer",
            children=[html.Span("smart_toy", className="material-symbols-outlined nav-icon"), html.Span("Vikram")]
        ),
        dcc.Link(
            className="mobile-nav-item", id="nav-btn-inst-signals", href="/institutional-signals",
            children=[html.Span("shield", className="material-symbols-outlined nav-icon"), html.Span("Inst. Signals")]
        )
    ]
)

top_navbar = html.Header(
    style={"width": "100%", "flexShrink": "0"},
    className="flex justify-between items-center px-4 md:px-margin-desktop sticky top-0 z-50 bg-surface/80 backdrop-blur-xl h-16 border-b border-outline-variant shadow-sm",
    children=[
        # Search/AI entry point is the floating Vikram bar (bottom center);
        # this spacer keeps the right-hand icons pushed right.
        html.Div(className="flex-1"),
        html.Div(
            className="flex items-center gap-md",
            children=[
                html.Button(
                    title="Notifications",
                    **{"aria-label": "Notifications"},
                    className="w-11 h-11 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors active:scale-95 duration-100 text-on-surface-variant",
                    children=[DashIconify(icon="material-symbols:notifications-outline", width=24, height=24)]
                ),
                html.Button(
                    title="Settings",
                    **{"aria-label": "Settings"},
                    className="w-11 h-11 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors active:scale-95 duration-100 text-on-surface-variant",
                    children=[DashIconify(icon="material-symbols:settings-outline", width=24, height=24)]
                ),
                html.Div(
                    className="relative flex items-center justify-center cursor-pointer group",
                    children=[
                        html.Img(
                            alt="User profile picture",
                            className="w-10 h-10 rounded-full border-2 border-surface-container-high object-cover transition-all duration-300 group-hover:border-primary",
                            src="https://lh3.googleusercontent.com/aida-public/AB6AXuDSPGwdD37lUGqWROw7FbCdpsC09lzG81peku_8eXOQ5lhQIBmGTRWYwMd2ih-sO4Efzsi-FiItAyFEtnl9Trh2C_jDb78r21h1SXAIShk7Lhf_L5OCBwvtTYZlfCl35aBGDb6ivgxsHATQLjcZsap-8TF1B9xjyzM-hWf5k2sygd7Lp6MxuWFHkF78sUWs7RkfRQLWbIgfKgboAJMB09guDKkIWZPI0MuAChf6sK8faa-Axtck-uo4kw"
                        ),
                        html.Div(className="absolute bottom-0 right-0 w-3 h-3 bg-primary rounded-full border-2 border-surface shadow-[0_0_8px_rgba(90,240,179,0.8)]")
                    ]
                )
            ]
        )
    ]
)

app.layout = html.Div(
    id="main-layout",
    className="app-grid bg-background antialiased font-body-md text-on-background",
    children=[
        dcc.Store(id="sidebar-state", data={"collapsed": False}),
        sidebar,
        mobile_bottom_nav,
        # Mobile FAB for Trade Now (hidden on desktop)
        html.Button(
            "Trade",
            id="mobile-trade-fab",
            className="md:hidden fixed bottom-[90px] right-4 z-50 bg-primary text-on-primary font-label-caps text-label-caps rounded-xl px-5 py-3 shadow-[0_4px_20px_rgba(174,198,255,0.4)] hover:bg-primary-fixed active:scale-95 transition-all"
        ),
        # Floating Command Bar — opens the Vikram AI panel
        html.Div(
            id="vikram-trigger",
            role="complementary",
            **{"aria-label": "Open Vikram AI Command Bar"},
            className="hidden md:flex fixed bottom-6 left-1/2 -translate-x-1/2 z-50 items-center gap-3 px-4 py-2.5 rounded-full bg-surface-container-highest/90 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.4)] cursor-pointer hover:bg-surface-container-highest transition-colors",
            children=[
                DashIconify(icon="material-symbols:search", width=20, height=20, className="text-on-surface-variant"),
                html.Span("Ask Vikram — AI Analyst", className="text-on-surface-variant font-body-md text-sm pr-12"),
                html.Div(
                    className="flex items-center gap-1",
                    children=[
                        html.Kbd("⌘", className="px-1.5 py-0.5 rounded bg-white/10 text-on-surface-variant text-xs font-data-mono border border-white/5"),
                        html.Kbd("K", className="px-1.5 py-0.5 rounded bg-white/10 text-on-surface-variant text-xs font-data-mono border border-white/5")
                    ]
                )
            ]
        ),
        # Vikram AI Analyst slide-in panel (right side, hidden by default)
        html.Aside(
            id="vikram-panel",
            className="fixed top-0 right-0 h-[100dvh] w-full md:w-[400px] z-[999] flex flex-col bg-surface-container-low/95 backdrop-blur-2xl border-l border-white/10 shadow-[0_0_60px_rgba(0,0,0,0.6)]",
            style={"transform": "translateX(100%)", "transition": "transform 0.3s ease"},
            children=[
                html.Div(
                    className="flex items-center justify-between px-4 py-3 border-b border-outline-variant",
                    children=[
                        html.Div(
                            children=[
                                html.Div("Vikram", className="font-headline-sm text-headline-sm text-primary"),
                                html.P("AI Analyst — Institutional / Small Cap", className="font-label-caps text-label-caps text-outline whitespace-nowrap")
                            ]
                        ),
                        html.Button(
                            id="vikram-close",
                            title="Close Vikram panel",
                            **{"aria-label": "Close Vikram panel"},
                            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors text-on-surface-variant",
                            children=[DashIconify(icon="material-symbols:close", width=20, height=20)]
                        )
                    ]
                ),
                html.Div(
                    id="vikram-chat",
                    className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3",
                    children=[
                        html.Div(
                            "I'm Vikram — your portfolio-aware analyst. I can see your active positions and today's engine signals. Ask me about a stock from the scanners, your positions, or which mode (institutional / small-cap momentum) applies to a name.",
                            className="self-start max-w-[95%] bg-white/5 border border-outline-variant/60 text-on-surface rounded-xl rounded-bl-sm px-3 py-2 text-sm font-body-md whitespace-pre-wrap leading-relaxed"
                        )
                    ]
                ),
                html.Div(
                    className="flex gap-2 p-3 border-t border-outline-variant",
                    children=[
                        dcc.Input(
                            id="vikram-input",
                            type="text",
                            placeholder="Ask about a stock or your positions...",
                            style={"fontSize": "16px"},
                            className="flex-1 bg-transparent border border-outline-variant rounded-lg px-3 font-data-mono text-sm text-on-surface placeholder:text-outline focus:border-primary focus:ring-0 focus:outline-none outline-none appearance-none min-h-[44px]"
                        ),
                        html.Button(
                            "Ask",
                            id="vikram-send",
                            className="bg-primary text-on-primary font-headline-sm text-headline-sm rounded-lg px-4 hover:bg-primary-fixed transition-colors min-h-[44px] active:scale-95"
                        )
                    ]
                ),
                dcc.Store(id="vikram-history", data=[]),
                dcc.Store(id="vikram-pending", data=None),
            ]
        ),
        html.Main(
            style={"display": "flex", "flexDirection": "column", "minWidth": "0", "overflow": "hidden"},
            children=[
                dcc.Location(id="url", refresh=False),
                top_navbar,
                html.Div(
                    style={"flex": "1", "overflowY": "auto"},
                    tabIndex="0",
                    className="p-margin-mobile md:p-margin-desktop pb-24 page-content-mobile-pad focus:outline-none",
                    children=[
                        html.Div(
                            className="max-w-[1800px] mx-auto w-full",
                            children=[
                                dash.page_container
                            ]
                        )
                    ]
                )
            ]
        )
    ]
)

@app.callback(
    Output("sidebar-nav-links", "children"),
    Input("url", "pathname"),
    Input("sidebar-state", "data")
)
def update_nav(pathname, state):
    collapsed = state.get("collapsed", False) if state else False
    NAV_LINKS = [
        {"name": "Dashboard", "icon": "leaderboard", "path": "/"},
        {"name": "Signals", "icon": "bolt", "path": "/signals"},
        {"name": "Institutional Signals", "icon": "shield", "path": "/institutional-signals"},
        {"name": "Verify Conditions", "icon": "check_circle", "path": "/verify-conditions"},
        {"name": "Watchlist", "icon": "bookmark", "path": "/watchlist"},
        {"name": "Win Rate", "icon": "monitoring", "path": "/win-rate"},
        {"name": "Data Health", "icon": "health_and_safety", "path": "/data-health"}
    ]
    base_class = "flex items-center gap-md px-sm py-md rounded-lg font-label-caps text-label-caps transition-all duration-300 ease-in-out min-h-[44px]"
    active_class = " text-secondary bg-secondary-container/10 border-transparent shadow-[0_0_20px_rgba(174,198,255,0.15)]"
    inactive_class = " text-on-surface-variant hover:text-secondary hover:bg-white/5"

    items_html = []
    for item in NAV_LINKS:
        text_style = {"display": "none"} if collapsed else {}
        is_active = (pathname == item["path"])
        cls = base_class + (active_class if is_active else inactive_class)
        items_html.append(
            dcc.Link(
                className=cls,
                href=item["path"],
                children=[
                    html.Span(item["icon"], className="material-symbols-outlined text-lg"),
                    html.Span(item["name"], style=text_style)
                ]
            )
        )
    return items_html

@app.callback(
    Output("main-layout", "className"),
    Output("sidebar-state", "data"),
    Output("sidebar-toggle-icon", "icon"),
    Output("sidebar-title-container", "style"),
    Input("sidebar-toggle-btn", "n_clicks"),
    State("sidebar-state", "data"),
    prevent_initial_call=True
)
def toggle_sidebar(n_clicks, state):
    collapsed = state.get("collapsed", False)
    new_collapsed = not collapsed
    
    new_class = "app-grid sidebar-collapsed bg-background antialiased font-body-md text-on-background" if new_collapsed else "app-grid bg-background antialiased font-body-md text-on-background"
    new_icon = "material-symbols:menu" if new_collapsed else "material-symbols:menu-open"
    new_title_style = {"display": "none"} if new_collapsed else {}
    
    return new_class, {"collapsed": new_collapsed}, new_icon, new_title_style



# Registers the Vikram AI Analyst chat callbacks (⌘K bar -> slide-in panel).
# Underscore prefix keeps this module out of the Dash pages registry.
import dash_pages._vikram_callback  # noqa: E402, F401

server = app.server

if __name__ == '__main__':
    app.run(debug=os.environ.get("DASH_DEBUG") == "1", host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
