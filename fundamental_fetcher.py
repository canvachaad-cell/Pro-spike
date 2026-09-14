"""FundamentalFetcher — Layer 1 of the Vikram v3 architecture.

For each screener signal, fetches institutional fundamentals from
screener.in (consolidated, falling back to standalone):
  - market cap, promoter holding, DII/FII quarterly trends
  - pledge % trend (last 4 quarters) + direction
  - OCF/PAT (3yr cumulative)
  - operating leverage (EBIT vs revenue growth, last 4 quarters)
  - interest coverage trend (EBIT/Interest, last 4 vs prior 4 quarters)
  - RoICE (delta EBIT / delta Capital Employed, 3 FYs)

Results are cached in data/fundamental_cache.json with a 24h TTL.
Rate-safe: only invoked for the handful of symbols the screener surfaces.
"""
import json
import os
import re
import threading
import time

import requests
from bs4 import BeautifulSoup
from rpt_fetcher import RPTFetcher

CACHE_PATH = os.path.join("data", "fundamental_cache.json")
CACHE_TTL_SECONDS = 24 * 3600
# screener.in intermittently stalls under load; 6s timeout + stale-cache fallback.
REQUEST_TIMEOUT = 6
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_lock = threading.Lock()


def _num(v):
    try:
        s = str(v).replace(",", "").replace("%", "").strip()
        if s in ("", "-", "--"):
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse_table(table):
    """Screener table -> (headers, {row_label: [values]})."""
    rows = table.select("tr")
    if not rows:
        return None, None
    headers = [c.get_text(strip=True) for c in rows[0].select("th, td")]
    data = {}
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.select("td, th")]
        if not cells:
            continue
        label = re.sub(r"\s*\+$", "", cells[0]).strip()
        vals = [v for v in cells[1:] if v != ""]
        if label:
            data[label] = vals
    return headers, data


QUALITY_KEYS = (
    "market_cap_cr", "price", "quarterly_quarters", "fcf_pat_ratio",
    "roice_pct", "interest_coverage_trend", "op_lev_ratio",
    "promoter_holding", "ocf_3yr_cr",
)


def _quality_count(data):
    """How many substantive fundamentals a fetch produced."""
    if not data or data.get("error"):
        return 0
    return sum(1 for k in QUALITY_KEYS if data.get(k) is not None)


# A result below this is a HOLLOW page (screener occasionally serves a page
# with no financial tables) — must never be cached and must be reported as
# incomplete so the caller falls back to search instead of ⏳-forever.
MIN_QUALITY_KEYS = 3


class FundamentalFetcher:
    def fetch(self, symbol):
        """Return a fundamentals dict for SYMBOL (cached, 24h TTL).

        Resilience layers:
        1. Hollow pages (< MIN_QUALITY_KEYS substantive values) are treated
           as failures — never cached, retried once.
        2. If consolidated URL yields a hollow page, the standalone URL is
           tried before giving up (consolidated pages are sometimes hollow
           for companies with sparse consolidated reporting).
        3. Hard failures (timeout/5xx/network) retry once.
        4. If everything fails, serve a STALE cache entry (any age) marked
           data_stale=True — a slightly old number beats a ⏳ empty scorecard.
        Cache reads also purge/ignore hollow historical entries.
        """
        symbol = str(symbol).upper().strip()
        cached = self._load_cache(symbol)
        if cached is not None:
            if _quality_count(cached) >= MIN_QUALITY_KEYS:
                return cached
            # Hollow cache entry (old bug) — purge and refetch
            self._purge_cache(symbol)
        data = self._fetch_live(symbol)
        if _quality_count(data) < MIN_QUALITY_KEYS:
            # hollow consolidated page -> try standalone
            standalone = self._fetch_live(symbol, standalone=True)
            if _quality_count(standalone) > _quality_count(data):
                data = standalone
        if _quality_count(data) < MIN_QUALITY_KEYS:
            stale = self._load_cache(symbol, allow_stale=True)
            if stale is not None and _quality_count(stale) >= MIN_QUALITY_KEYS:
                stale = dict(stale)
                stale["data_stale"] = True
                return stale
            if stale is not None:
                # hollow stale entry — purge so it never shadows future fetches
                self._purge_cache(symbol)
            if "error" not in data:
                data = dict(data)
                data["error"] = "incomplete data from screener.in (financial tables missing from page)"
            return data
        if "error" not in data:
            revenue_cr = data.get("revenue_ttm_cr")
            rpt_info = RPTFetcher().fetch_rpt_data(symbol, revenue_cr=revenue_cr)
            data["rpt_status"] = rpt_info.get("status", "NOT_FOUND")
            data["rpt_pct"] = rpt_info.get("rpt_pct")
            data["rpt_amount_cr"] = rpt_info.get("rpt_amount_cr")
            self._save_cache(symbol, data)
        return data

    # ---- cache -----------------------------------------------------------

    def _purge_cache(self, symbol):
        try:
            with _lock:
                if not os.path.exists(CACHE_PATH):
                    return
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                if symbol in cache:
                    del cache[symbol]
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=1)
        except Exception:
            pass

    def _load_cache(self, symbol, allow_stale=False):
        try:
            with _lock:
                if not os.path.exists(CACHE_PATH):
                    return None
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            entry = cache.get(symbol)
            if not entry:
                return None
            if not allow_stale and time.time() - entry.get("ts", 0) > CACHE_TTL_SECONDS:
                return None
            return entry.get("data")
        except Exception:
            return None

    def _save_cache(self, symbol, data):
        try:
            with _lock:
                cache = {}
                if os.path.exists(CACHE_PATH):
                    try:
                        with open(CACHE_PATH, "r", encoding="utf-8") as f:
                            cache = json.load(f)
                    except Exception:
                        cache = {}
                cache[symbol] = {"ts": time.time(), "data": data}
                os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=1)
        except Exception:
            pass
    # ---- live fetch ------------------------------------------------------

    def _fetch_live(self, symbol, standalone=False):
        if standalone:
            url = f"https://www.screener.in/company/{symbol}/"
        else:
            url = f"https://www.screener.in/company/{symbol}/consolidated/"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
            if not standalone and r.status_code == 404:
                url = f"https://www.screener.in/company/{symbol}/"
                r = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
        except Exception:
            return {"symbol": symbol, "error": "network error / timeout"}

        if r.status_code == 404:
            # Fallback: BSE-only stocks often use 6-digit codes instead of symbols on Screener
            try:
                sr = requests.get("https://www.screener.in/api/company/search/", params={"q": symbol}, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
                if sr.status_code == 200 and sr.json():
                    url_path = sr.json()[0].get("url", "")
                    if url_path:
                        url = f"https://www.screener.in{url_path}"
                        if "consolidated" not in url:
                            r = requests.get(url + "consolidated/", headers=_HEADERS, timeout=REQUEST_TIMEOUT)
                            if r.status_code == 404:
                                r = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
                        else:
                            r = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
                        url = r.url if getattr(r, 'url', None) else url
            except Exception:
                pass

        if r.status_code == 404:
            return {"symbol": symbol, "error": "not found on screener.in (BSE-only listings may lack a page)"}
        if r.status_code != 200:
            return {"symbol": symbol, "error": f"HTTP {r.status_code}"}

        try:
            soup = BeautifulSoup(r.text, "html.parser")
            out = {"symbol": symbol, "url": url}
            h1 = soup.select_one("h1")
            if h1:
                out["name"] = h1.get_text(strip=True)

            # top ratios: market cap / price
            ratios = {}
            for li in soup.select("ul#top-ratios li"):
                n = li.select_one(".name")
                v = li.select_one(".value")
                if n and v:
                    ratios[n.get_text(strip=True)] = v.get_text(" ", strip=True)
            m = re.search(r"([\d,]+)", ratios.get("Market Cap", ""))
            if m:
                out["market_cap_cr"] = float(m.group(1).replace(",", ""))
            m = re.search(r"([\d,]+(?:\.\d+)?)", ratios.get("Current Price", ""))
            if m:
                out["price"] = float(m.group(1).replace(",", ""))

            tables = soup.select("table")
            parsed = []
            for t in tables:
                headers, data = _parse_table(t)
                if headers and data:
                    parsed.append((headers, data))

            # Table lookup with financial-sector label fallbacks: banks/NBFCs
            # use 'Revenue'/'Financing Profit' instead of 'Sales'/'Operating
            # Profit'. Each key set is a list of acceptable alternatives.
            pl_q = self._find_table_multi(parsed, [["Sales", "Revenue"], ["Operating Profit", "Financing Profit"]], quarters=True)
            pl_a = self._find_table_multi(parsed, [["Sales", "Revenue"], ["Net Profit", "Financing Profit"]], quarters=False)
            qh, qdata = pl_q if pl_q else (None, {})
            ah, adata = pl_a if pl_a else (None, {})
            bh, bdata = self._find_table(parsed, ("Equity Capital", "Borrowing"), quarters=False)
            ch, cdata = self._find_table(parsed, ("Cash from Operating Activity",), quarters=False)
            sh, sdata = self._find_table(parsed, ("Promoters", "DIIs"), quarters=True)

            self._extract_shareholding(out, sh, sdata)
            self._extract_pledge(out, parsed, r.text)
            self._extract_quarterly(out, qh, qdata)
            self._extract_annual(out, ah, adata, bh, bdata, ch, cdata)
            # Financial-sector marker: screener's P&L uses 'Revenue'/'Financing
            # Profit' labels for banks/NBFCs/brokers. OCF for such companies is
            # structurally negative (loan disbursements are operating outflows),
            # so FCF/PAT vetoes don't apply.
            if ah and any("Financing Profit" in k for k in adata.keys()):
                out["sector_type"] = "financial"
            self._derive_free_float(out)
            return out
        except Exception as e:
            return {"symbol": symbol, "error": f"parse error: {e}"}

    @staticmethod
    def _find_table(parsed, row_keys, quarters):
        for headers, data in parsed:
            if all(any(k in lab for lab in data) for k in row_keys):
                is_q = bool(re.search(r"(Jun|Sep|Dec)\s*20\d\d", " ".join(headers)))
                if quarters == is_q:
                    return headers, data
        return None, {}

    @staticmethod
    def _find_table_multi(parsed, key_alternatives, quarters):
        """Like _find_table but each key position accepts several labels.

        key_alternatives = [["Sales", "Revenue"], ["Operating Profit",
        "Financing Profit"]] — a table matches if EVERY position has at
        least one of its alternatives present as a row-label substring.
        """
        for headers, data in parsed:
            pos_ok = [
                any(alt in lab for lab in data for alt in alts)
                for alts in key_alternatives
            ]
            if all(pos_ok):
                is_q = bool(re.search(r"(Jun|Sep|Dec)\s*20\d\d", " ".join(headers)))
                if quarters == is_q:
                    return headers, data
        return None, {}

    @staticmethod
    def _series(headers, values):
        """Align a values list against headers; returns {label: value}."""
        # values align to headers[1:] positionally after empty cells dropped
        out = {}
        for h, v in zip(headers[1:], values):
            m = re.search(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\d{4}|\d{4})", h.replace(" ", " "))
            if m:
                out[m.group(1).replace(" ", "")] = _num(v)
        return out

    def _extract_shareholding(self, out, headers, data):
        if not headers:
            return
        quarters = [h for h in headers if re.search(r"(Sep|Dec|Mar|Jun)\s*20\d\d", h)]
        for row_key, key in (("Promoters", "promoter"), ("DIIs", "dii"), ("FIIs", "fii")):
            for k, vals in data.items():
                if k == row_key:
                    pairs = [f"{q.split()[0]} {q.split()[-1]}: {v}" for q, v in zip(quarters, vals)]
                    out[f"{key}_trend"] = " -> ".join(pairs)
                    nums = [_num(v) for v in vals if str(v).endswith("%")]
                    if nums:
                        out[f"{key}_holding"] = nums[-1]
                    break

    def _extract_pledge(self, out, parsed, page_text):
        """Pledge % for the last 4 quarters (table when present, else text)."""
        pledge_vals = []
        for headers, data in parsed:
            for k, vals in data.items():
                if re.search(r"pledge", k, re.I):
                    for v in vals:
                        n = _num(v)
                        if n is not None:
                            pledge_vals.append(n)
        if not pledge_vals:
            m = re.search(r"pledged?[^\n]{0,60}?([\d.]+)\s*%", page_text, re.I)
            if m:
                pledge_vals = [_num(m.group(1))]
        if pledge_vals:
            pledge_vals = pledge_vals[-4:]
            out["pledge_trend"] = pledge_vals
            last, prior = pledge_vals[-1], (pledge_vals[-2] if len(pledge_vals) > 1 else None)
            if prior is None or abs(last - prior) < 0.5:
                out["pledge_direction"] = "flat"
            else:
                out["pledge_direction"] = "rising" if last > prior else "falling"
        else:
            out["pledge_trend"] = [0.0]
            out["pledge_direction"] = "flat"
            out["pledge_note"] = "no pledge table/mention on screener page (treated as 0%)"

    def _extract_quarterly(self, out, headers, data):
        """Operating leverage + interest coverage from the quarterly P&L.

        Financial-sector companies (banks, NBFCs, brokers) use 'Revenue+' and
        'Financing Profit' labels instead of 'Sales'/'Operating Profit' on
        screener — both label sets are handled.
        """
        if not headers:
            return
        def row(labels):
            for lab in labels:
                for k, vals in data.items():
                    if k == lab:
                        return vals
            return []
        sales = [_num(v) for v in row(["Sales", "Revenue"])]
        ebit = [_num(v) for v in row(["Operating Profit", "Financing Profit"])]
        interest = [_num(v) for v in row(["Interest"])]
        out["quarterly_quarters"] = len(sales)
        
        # Calculate TTM Revenue for RPT percentage calculations
        if len(sales) >= 4:
            out["revenue_ttm_cr"] = sum(x for x in sales[-4:] if x is not None)
            
        # Operating leverage: full YoY when >= 8 quarters; last-4 vs oldest
        # quarter approximation for 5-7 (new IPOs); skip below 5.
        if len(sales) >= 5 and len(ebit) >= 5:
            if len(sales) >= 8 and len(ebit) >= 8:
                s_last = sum(x for x in sales[-4:] if x is not None)
                s_prev = sum(x for x in sales[-8:-4] if x is not None)
                e_last = sum(x for x in ebit[-4:] if x is not None)
                e_prev = sum(x for x in ebit[-8:-4] if x is not None)
            else:
                s_prev = sales[0] if sales[0] is not None else None
                e_prev = ebit[0] if ebit[0] is not None else None
                s_last = sum(x for x in sales[-4:] if x is not None)
                e_last = sum(x for x in ebit[-4:] if x is not None)
                out["op_lev_data_note"] = f"limited_history_{len(sales)}q"
            if s_prev and s_prev > 0:
                out["revenue_4q_growth"] = (s_last - s_prev) / s_prev
            if e_prev and e_prev > 0:
                out["ebit_4q_growth"] = (e_last - e_prev) / e_prev
            rg, eg = out.get("revenue_4q_growth"), out.get("ebit_4q_growth")
            if rg is not None and eg is not None and rg > 0:
                out["op_lev_ratio"] = eg / rg
                out["op_lev_inflecting"] = bool(eg > 0 and eg / rg >= 2.0)
        # interest coverage: EBIT/Interest, last 4 vs prior 4 (or halves)
        cov = []
        for e, i in zip(ebit, interest):
            if e is not None and i is not None and i > 0:
                cov.append(e / i)
        if len(cov) >= 5:
            if len(cov) >= 8:
                last4, prev4 = cov[-4:], cov[-8:-4]
                lm, pm = sum(last4) / 4, sum(prev4) / 4
            else:
                mid = len(cov) // 2
                lm = sum(cov[mid:]) / len(cov[mid:])
                pm = sum(cov[:mid]) / len(cov[:mid])
                out["interest_coverage_data_note"] = f"limited_history_{len(cov)}q"
            if abs(lm - pm) / (abs(pm) if pm else 1) < 0.05:
                out["interest_coverage_trend"] = "stable"
            else:
                out["interest_coverage_trend"] = "improving" if lm > pm else "deteriorating"
            out["interest_coverage_recent"] = round(lm, 2)

    def _extract_annual(self, out, ah, adata, bh, bdata, ch, cdata):
        # OCF/PAT: 3yr cumulative from the cash-flow + P&L annual tables.
        # Financial-sector P&L rows use 'Net Profit +' etc. — both handled.
        def _row(df_data, labels):
            for lab in labels:
                vals = df_data.get(lab)
                if vals:
                    return vals
            return []
        ocf = self._series(ch, _row(cdata, ["Cash from Operating Activity"])) if ch else {}
        npf = self._series(ah, _row(adata, ["Net Profit", "Net Profit +", "Financing Profit"])) if ah else {}
        years = sorted(set(ocf) & set(npf))[-3:]
        if years:
            o = [ocf[y] for y in years]
            n = [npf[y] for y in years]
            out["ocf_3yr_cr"] = [round(v, 1) if v is not None else None for v in o]
            out["pat_3yr_cr"] = [round(v, 1) if v is not None else None for v in n]
            o_sum = sum(v for v in o if v is not None)
            n_sum = sum(v for v in n if v is not None)
            if n_sum and abs(n_sum) > 0:
                out["fcf_pat_ratio"] = round(o_sum / n_sum, 2)

        # RoICE: delta EBIT / delta Capital Employed over 3 FYs
        ebit_a = self._series(ah, _row(adata, ["Operating Profit", "Financing Profit"])) if ah else {}
        eq = self._series(bh, _row(bdata, ["Equity Capital"])) if bh else {}
        res = self._series(bh, _row(bdata, ["Reserves"])) if bh else {}
        bor = self._series(bh, _row(bdata, ["Borrowing", "Borrowings"])) if bh else {}
        ce = {}
        for y in set(eq) & set(res) & set(bor):
            if eq[y] is not None and res[y] is not None and bor[y] is not None:
                ce[y] = eq[y] + res[y] + bor[y]
        yrs = sorted(set(ebit_a) & set(ce))
        if len(yrs) >= 4:
            d_ebit = ebit_a[yrs[-1]] - ebit_a[yrs[-4]]
            d_ce = ce[yrs[-1]] - ce[yrs[-4]]
            if d_ce and d_ce > 0 and d_ebit is not None:
                out["roice_pct"] = round(d_ebit / d_ce * 100, 1)
        # borrowings snapshot for context
        if bor:
            y = sorted(bor)[-1]
            if bor[y] is not None:
                out["borrowings_cr"] = round(bor[y], 0)

    @staticmethod
    def _derive_free_float(out):
        mcap = out.get("market_cap_cr")
        promo = out.get("promoter_holding")
        if mcap is not None and promo is not None:
            out["free_float_cr"] = round(mcap * (1 - promo / 100.0))
