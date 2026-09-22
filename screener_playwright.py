"""screener_playwright.py — JS-rendered Screener.in fallback fetcher.

Used ONLY when the requests-based FundamentalFetcher._fetch_live() returns a
financially-hollow page (P&L / CF / balance-sheet tables missing because
Screener.in now renders financial columns via JavaScript for some tickers).

Architecture:
  - Launches a single persistent Chromium instance (headless) on first call.
  - Pages are fetched with a 20s hard timeout, waiting for the financial table
    network responses to complete.
  - Returns the same dict shape as FundamentalFetcher._fetch_live() so the
    caller can merge/replace without any schema changes.
  - Thread-safe singleton: uses a module-level lock so multiple callbacks
    don't spin up multiple browsers.

NOT imported at module level — only imported inside the fallback branch
so the requests-only path has zero Playwright overhead.
"""

import re
import threading
import time
from typing import Optional, Dict, Any

_browser_lock = threading.Lock()
_browser = None  # singleton Playwright browser instance
_playwright_obj = None


def _num(v):
    try:
        s = str(v).replace(",", "").replace("%", "").strip()
        if s in ("", "-", "--"):
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _get_browser():
    """Return a singleton Chrome browser, launching it if needed."""
    global _browser, _playwright_obj
    if _browser is not None:
        return _browser
    from playwright.sync_api import sync_playwright
    _playwright_obj = sync_playwright().start()
    _browser = _playwright_obj.chromium.launch(
        channel="chrome",  # use system-installed Chrome, not Playwright's Chromium
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    return _browser


def fetch_with_playwright(symbol: str, bse_code: Optional[str] = None) -> Dict[str, Any]:
    """Fetch financials for SYMBOL from Screener.in using a headless Chrome browser.

    Args:
        symbol: NSE/BSE ticker e.g. 'GGAUTO'
        bse_code: 6-digit BSE code e.g. '531399' (used to build the URL directly)

    Returns:
        dict with keys matching FundamentalFetcher's output, or {'error': ...} on failure.
    """
    from fundamental_fetcher import FundamentalFetcher, _is_financially_hollow, _quality_count
    fetcher = FundamentalFetcher()

    # Candidate URLs to try (standalone first for BSE codes, consolidated first for symbols)
    code = bse_code or symbol
    if bse_code:
        candidate_urls = [
            f"https://www.screener.in/company/{code}/",
            f"https://www.screener.in/company/{code}/consolidated/",
        ]
    else:
        candidate_urls = [
            f"https://www.screener.in/company/{code}/consolidated/",
            f"https://www.screener.in/company/{code}/",
        ]

    best_result = {"symbol": symbol, "error": "playwright fetch failed"}

    try:
        with _browser_lock:
            browser = _get_browser()
            page = browser.new_page()

        try:
            for url in candidate_urls:
                try:
                    page.goto(url, timeout=20000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                    html = page.content()
                    
                    parsed = fetcher._parse_html(html, symbol, url)
                    if _quality_count(parsed) > _quality_count(best_result):
                        best_result = parsed
                    if not _is_financially_hollow(parsed) and _quality_count(parsed) >= 6:
                        # Found complete data, no need to try second URL
                        break
                except Exception as e_page:
                    print(f"[screener_playwright] Error fetching {url}: {e_page}")
        finally:
            page.close()

        return best_result

    except Exception as e:
        return {"symbol": symbol, "error": f"playwright fetch error: {e}"}

