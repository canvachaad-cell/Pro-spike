import dash
from dash import Dash, html, dcc, Input, Output, State
from dash_iconify import DashIconify
import os
import gzip

# --- Zero-dependency WSGI Gzip Middleware for High-Speed Mobile Delivery ---
class GzipMiddleware:
    def __init__(self, wsgi_app, compress_level=6, min_size=500):
        self.wsgi_app = wsgi_app
        self.compress_level = compress_level
        self.min_size = min_size

    def __call__(self, environ, start_response):
        if "gzip" not in environ.get("HTTP_ACCEPT_ENCODING", "").lower():
            return self.wsgi_app(environ, start_response)

        status_code = []
        headers_list = []

        def custom_start(status, headers, exc_info=None):
            status_code.append(status)
            headers_list.extend(headers)
            return lambda _: None

        app_iter = self.wsgi_app(environ, custom_start)
        content_type = ""
        for k, v in headers_list:
            if k.lower() == "content-type":
                content_type = v.lower()
                break

        compressable = any(t in content_type for t in ["text/", "application/javascript", "application/json", "image/svg+xml"])
        body = b"".join(app_iter)
        if hasattr(app_iter, "close"):
            app_iter.close()

        if compressable and len(body) >= self.min_size:
            gz_body = gzip.compress(body, compresslevel=self.compress_level)
            new_h = [(k, v) for k, v in headers_list if k.lower() not in ("content-length", "content-encoding")]
            new_h.extend([("Content-Encoding", "gzip"), ("Content-Length", str(len(gz_body))), ("Vary", "Accept-Encoding")])
            start_response(status_code[0], new_h)
            return [gz_body]

        start_response(status_code[0], headers_list)
        return [body]

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
        <meta name="description" content="Pro-spike: quantitative trading dashboard for NSE/BSE institutional accumulation, delivery volume signals, and portfolio analytics.">
        {%metas%}
        <title>{%title%}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link rel="canonical" href="https://prospike.com">
        <meta property="og:description" content="Pro-spike: quantitative trading dashboard for NSE/BSE institutional accumulation, delivery volume signals, and portfolio analytics.">
        <meta property="og:title" content="Pro Spike">
        <meta property="og:type" content="website">
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
server.wsgi_app = GzipMiddleware(server.wsgi_app)


@server.route('/robots.txt')
def serve_robots():
    return (
        "User-agent: *\nAllow: /\nSitemap: https://prospike.com/sitemap.xml\n",
        200,
        {'Content-Type': 'text/plain; charset=utf-8'}
    )


@server.route('/llms.txt')
def serve_llms_txt():
    content = (
        "# Pro Spike Quantitative Trading Platform\n\n"
        "> Real-time institutional footprint tracking, Wyckoffian volume surges, and quantitative momentum signals for the Indian stock market.\n\n"
        "## Core Platform Modules\n"
        "- [Dashboard](http://127.0.0.1:8050/): High-level market overview and 12-condition breakout signals.\n"
        "- [Institutional Signals](http://127.0.0.1:8050/institutional-signals): SBIA Alpha, FlexGate, FlexGate 2.0, and Corner Spike scanners.\n"
        "- [Winner Archetypes](http://127.0.0.1:8050/winner-archetypes): Top 30 historical multi-bagger archetype classification.\n"
        "- [Momentum Score](http://127.0.0.1:8050/momentum): 3-component momentum percentile rankings.\n"
        "- [Watchlist](http://127.0.0.1:8050/watchlist): Active high-conviction institutional positions.\n"
    )
    return content, 200, {'Content-Type': 'text/markdown; charset=utf-8'}


@server.route('/.well-known/ai-catalog.json')
def serve_ai_catalog():
    import json
    catalog = json.dumps({
        "specVersion": "1.0",
        "name": "Pro Spike",
        "description": "Indian stock market quantitative signals and analytics",
        "entries": [
            {
                "name": "Market Dashboard",
                "description": "High-level market overview and 12-condition breakout signals",
                "url": "http://127.0.0.1:8050/"
            },
            {
                "name": "Institutional Signals",
                "description": "SBIA Alpha, FlexGate, FlexGate 2.0, and Corner Spike scanners",
                "url": "http://127.0.0.1:8050/institutional-signals"
            }
        ]
    })
    return catalog, 200, {'Content-Type': 'application/json; charset=utf-8'}


def get_icon(icon_name):
    return DashIconify(icon=icon_name, width=18, height=18)

sidebar_header = html.Div(
    className="flex items-center justify-between mb-xl px-xs",
    children=[
        html.Div(
            id="sidebar-title-container",
            children=[
                html.Div("Pro Spike", className="font-headline-sm text-headline-sm text-primary", style={"margin": 0}),
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

NAV_LINKS = [
    {"name": "Dashboard", "icon": "leaderboard", "path": "/"},
    {"name": "Winner Archetypes", "icon": "emoji_events", "path": "/winner-archetypes"},
    {"name": "Institutional Signals", "icon": "shield", "path": "/institutional-signals"},
    {"name": "Signals", "icon": "bolt", "path": "/signals"},
    {"name": "Momentum Score", "icon": "speed", "path": "/momentum"},
    {"name": "Watchlist", "icon": "bookmark", "path": "/watchlist"},
    {"name": "Win Rate", "icon": "monitoring", "path": "/win-rate"},
    {"name": "Verify Conditions", "icon": "check_circle", "path": "/verify-conditions"},
    {"name": "Data Health", "icon": "health_and_safety", "path": "/data-health"}
]

MOBILE_PRIMARY_LINKS = [
    {"id": "nav-btn-dashboard", "name": "Dashboard", "icon": "leaderboard", "path": "/"},
    {"id": "nav-btn-inst-signals", "name": "Inst.", "icon": "shield", "path": "/institutional-signals"},
    {"id": "nav-btn-momentum", "name": "Momentum", "icon": "speed", "path": "/momentum"},
    {"id": "nav-btn-archetypes", "name": "Archetypes", "icon": "emoji_events", "path": "/winner-archetypes"},
]


def build_mobile_nav(pathname="/"):
    links = []
    for item in MOBILE_PRIMARY_LINKS:
        is_active = (pathname == item["path"])
        cls = "mobile-nav-item active" if is_active else "mobile-nav-item"
        links.append(
            dcc.Link(
                id=item["id"],
                className=cls,
                href=item["path"],
                children=[
                    html.Span(item["icon"], className="material-symbols-outlined nav-icon"),
                    html.Span(item["name"])
                ]
            )
        )
    links.append(
        html.Div(
            id="mobile-nav-more",
            role="button",
            tabIndex="0",
            className="mobile-nav-item cursor-pointer",
            children=[
                html.Span("more_horiz", className="material-symbols-outlined nav-icon"),
                html.Span("More")
            ]
        )
    )
    return links


mobile_bottom_nav = html.Nav(
    id="mobile-bottom-nav",
    className="mobile-bottom-nav",
    children=build_mobile_nav("/")
)

mobile_top_header = html.Header(
    className="flex md:hidden justify-between items-center px-4 sticky top-0 z-40 bg-surface/90 backdrop-blur-xl h-14 border-b border-white/5",
    children=[
        dcc.Link(
            href="/",
            className="flex items-center gap-2 no-underline text-on-surface",
            children=[
                html.Span("emoji_events", className="material-symbols-outlined text-primary text-xl"),
                html.Div("Pro Spike", className="font-headline-sm text-base font-bold text-primary tracking-tight"),
                html.Span("LIVE", className="text-[9px] font-mono font-bold bg-primary/10 text-primary border border-primary/30 px-1.5 py-0.5 rounded"),
            ]
        ),
        html.Button(
            id="mobile-drawer-toggle",
            title="Open all navigation pages",
            **{"aria-label": "Open all navigation pages"},
            className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/10 active:scale-95 text-on-surface-variant transition-colors border border-white/10",
            children=[DashIconify(icon="material-symbols:menu", width=22, height=22, id="mobile-drawer-icon")]
        )
    ]
)

mobile_drawer = html.Div(
    id="mobile-menu-drawer",
    className="p-5 flex flex-col gap-3",
    children=[
        html.Div(
            className="flex items-center justify-between pb-3 border-b border-white/10",
            children=[
                html.Div(
                    className="flex items-center gap-2",
                    children=[
                        html.Span("menu_book", className="material-symbols-outlined text-primary text-base"),
                        html.Span("All Platform Modules", className="font-headline-sm text-sm font-bold text-on-surface uppercase tracking-wider"),
                    ]
                ),
                html.Button(
                    id="mobile-drawer-close",
                    title="Close navigation",
                    **{"aria-label": "Close navigation"},
                    className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5 text-on-surface-variant hover:text-white",
                    children=[DashIconify(icon="material-symbols:close", width=18, height=18)]
                )
            ]
        ),
        html.Div(
            id="mobile-drawer-links",
            className="grid grid-cols-2 gap-2 max-h-[60vh] overflow-y-auto py-1",
        )
    ]
)

top_navbar = html.Header(
    style={"width": "100%", "flexShrink": "0"},
    className="hidden md:flex justify-between items-center px-4 md:px-margin-desktop sticky top-0 z-50 bg-surface/80 backdrop-blur-xl h-16 border-b border-outline-variant shadow-sm",
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
        html.Div(id="mobile-drawer-backdrop", **{"aria-hidden": "true"}),
        mobile_drawer,

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
        # Mobile Floating Vikram Button (FAB)
        html.Div(
            id="mobile-vikram-fab",
            role="button",
            tabIndex="0",
            **{"aria-label": "Open Vikram AI"},
            className="md:hidden fixed bottom-20 right-4 z-[210] flex items-center justify-center w-[52px] h-[52px] rounded-2xl bg-surface/80 backdrop-blur-3xl shadow-[0_8px_32px_rgba(90,240,179,0.25)] border border-primary/40 cursor-pointer active:scale-95 transition-all",
            children=[
                html.Span("smart_toy", className="material-symbols-outlined text-primary text-[28px]")
            ]
        ),
        # Vikram backdrop - dims the page and intercepts taps while the panel is open (BUG-032)
        html.Div(
            id="vikram-backdrop",
            **{"aria-hidden": "true"},
        ),
        # Vikram AI Analyst slide-in panel (right sheet desktop / bottom sheet mobile)
        html.Aside(
            id="vikram-panel",
            className="fixed top-0 right-0 h-[100dvh] w-full md:w-[400px] z-[999] flex flex-col bg-surface-container-low/95 backdrop-blur-2xl border-l border-white/10 shadow-[0_0_60px_rgba(0,0,0,0.6)] max-md:top-auto max-md:bottom-0 max-md:left-0 max-md:h-[75dvh] max-md:rounded-t-2xl max-md:border-x-0 max-md:border-t",
            style={"transform": "translateX(100%)", "transition": "transform 0.3s ease", "pointerEvents": "none"},
            children=[
                # Drag handle - mobile bottom-sheet affordance (hidden on md+)
                html.Div(className="md:hidden w-10 h-1 rounded-full bg-white/20 mx-auto mt-2 flex-shrink-0"),
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
                    className="flex gap-2 p-3 border-t border-outline-variant max-md:pb-[calc(0.75rem+env(safe-area-inset-bottom))]",
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
                mobile_top_header,
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
    Output("mobile-bottom-nav", "children"),
    Input("url", "pathname"),
    Input("sidebar-state", "data")
)
def update_nav(pathname, state):
    collapsed = state.get("collapsed", False) if state else False
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

    mobile_items = build_mobile_nav(pathname or "/")
    return items_html, mobile_items


@app.callback(
    Output("mobile-drawer-backdrop", "className"),
    Output("mobile-drawer-links", "children"),
    Input("mobile-drawer-toggle", "n_clicks"),
    Input("mobile-nav-more", "n_clicks"),
    Input("mobile-drawer-close", "n_clicks"),
    Input("mobile-drawer-backdrop", "n_clicks"),
    Input("url", "pathname"),
    State("mobile-drawer-backdrop", "className"),
    prevent_initial_call=True
)
def toggle_mobile_drawer(toggle_clicks, more_clicks, close_clicks, backdrop_clicks, pathname, current_cls):
    triggered = dash.ctx.triggered_id
    if not triggered:
        raise dash.exceptions.PreventUpdate

    if triggered in ("mobile-drawer-close", "mobile-drawer-backdrop", "url"):
        return "", dash.no_update

    if triggered in ("mobile-drawer-toggle", "mobile-nav-more"):
        clicks = more_clicks if triggered == "mobile-nav-more" else toggle_clicks
        if not clicks:
            raise dash.exceptions.PreventUpdate

        drawer_items = []
        for item in NAV_LINKS:
            is_active = (pathname == item["path"])
            item_cls = (
                "flex items-center gap-2.5 p-3 rounded-xl border text-xs font-semibold transition-all "
                + (
                    "bg-primary/15 border-primary/40 text-primary shadow-[0_0_12px_rgba(90,240,179,0.2)]"
                    if is_active
                    else "bg-white/5 border-white/5 text-on-surface-variant hover:bg-white/10 hover:text-white"
                )
            )
            drawer_items.append(
                dcc.Link(
                    href=item["path"],
                    className=item_cls,
                    children=[
                        html.Span(item["icon"], className="material-symbols-outlined text-[18px] flex-shrink-0"),
                        html.Span(item["name"], className="truncate")
                    ]
                )
            )

        is_open = "open" in (current_cls or "")
        new_cls = "" if is_open else "open"
        return new_cls, drawer_items

    raise dash.exceptions.PreventUpdate

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
