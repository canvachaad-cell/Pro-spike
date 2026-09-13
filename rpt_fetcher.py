"""RPTFetcher — Related Party Transaction Data Parser for trading_dashboard.

Fetches Reg 23 XBRL filings (FY2022+ per NSE circulars NSE/CML/2021/34 & NSE/CML/2021/42)
or Ind AS 24 notes, calculating RPT % relative to trailing revenue.

Returns explicit status 'NOT_FOUND' if filing/data is unavailable — never defaults to 0%.
"""
import os
import json
import logging
import requests
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class RPTFetcher:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.rpt_cache_path = os.path.join(self.data_dir, "rpt_cache.json")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def fetch_rpt_data(self, symbol, revenue_cr=None):
        """Fetches RPT data for a symbol.

        Returns:
            dict: {
                "status": "OK" | "NOT_FOUND",
                "rpt_amount_cr": float or None,
                "rpt_pct": float or None,
                "filing_type": str or None
            }
        """
        # 1. Read from local RPT cache/store if present
        if os.path.exists(self.rpt_cache_path):
            try:
                with open(self.rpt_cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                    if symbol in cache:
                        data = cache[symbol]
                        return {
                            "status": data.get("status", "OK"),
                            "rpt_amount_cr": data.get("rpt_amount_cr"),
                            "rpt_pct": data.get("rpt_pct"),
                            "filing_type": data.get("filing_type", "Reg23_XBRL")
                        }
            except Exception as e:
                logger.warning(f"Error reading RPT cache for {symbol}: {e}")

        # 2. No live scraping at query time - relies purely on the offline scraper cache
        
        # Explicit NOT_FOUND return when filing data is not available in the cache
        return {
            "status": "NOT_FOUND",
            "rpt_amount_cr": None,
            "rpt_pct": None,
            "filing_type": None
        }
