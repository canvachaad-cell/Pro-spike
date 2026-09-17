import os
import time
import json
import re
import pandas as pd
import pdfplumber
import requests
import warnings
from collections import namedtuple
from datetime import datetime, timedelta
import argparse
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fundamental_fetcher import FundamentalFetcher

SCORES_PATH = 'data/fundamental_scores.csv'
FUND_CACHE_PATH = 'data/fundamental_cache.json'
RPT_CACHE_PATH = 'data/rpt_cache.json'
PDF_DIR = 'data/rpt_pdfs'
DELTA_TABLE_PATH = 'data/rpt_delta_table.csv'

# ETF and Fund exclusions
EXCLUDE_TICKERS = {'GROWWLIQID', 'ABSL10BANK', 'DEFENCE', 'CPPLUS', 'GROWW', 'SMCGLOBAL'}

def init_cache():
    if os.path.exists(RPT_CACHE_PATH):
        with open(RPT_CACHE_PATH, 'r') as f:
            return json.load(f)
    return {}

RptResult = namedtuple("RptResult", ["status", "rpt_amount_cr", "rpt_pct", "filing_type", "flags", "unit_source", "rescaled"])

UNIT_TO_CR = {"lakh": 0.01, "crore": 1.0, "million": 0.1, "thousand": 0.00001, "rupees": 0.0000001}
BACKSTOP_ORDER = ("crore", "lakh", "million")

ROUNDING_FIELD_RE = re.compile(
    r"level of rounding.{0,150}?\b(lakhs?|lacs?|crores?|millions?|thousands?)\b"
    r"|rounding\s+(?:off\s+)?(?:to\s+the\s+nearest\s+)?(lakhs?|lacs?|crores?|millions?|thousands?)\b",
    re.IGNORECASE | re.DOTALL,
)
PARENS_UNIT_RE = re.compile(r"\(\s*(?:in\s+)?(?:Rs\.?|₹)\s*(?:in\s+)?(lakhs?|crores?|millions?)\s*\)", re.IGNORECASE)
EMBEDDED_TOTAL_RE = re.compile(r"Total\s+(?:value\s+)?of\s+transactions?\s*.*?([\d,]+\.\d+)", re.IGNORECASE)
EXEMPTION_RE = re.compile(
    r"(?:non-?applicab\w*|shall not apply|not required to (?:submit|disclose)).{0,200}?regulation\s+23"
    r"|regulation\s+23.{0,200}?(?:non-?applicab\w*|shall not apply|not required to (?:submit|disclose))",
    re.IGNORECASE | re.DOTALL,
)
RPT_ANNOUNCEMENT_RE = re.compile(
    r"(?:related\s+party|reg(?:ulation)?\.?\s*23\s*\(9\)|rpt\b)",
    re.IGNORECASE,
)

def generate_date_windows(start_date_str="20230101", end_date_str=None, chunk_days=350):
    """Yields (from_date, to_date) strings in reverse chronological order.
    
    BSE API AnnSubCategoryGetData silently returns 0 results if the date
    span exceeds ~366 days. Chunks <= 350 days ensure 100% API compliance.
    """
    if end_date_str is None:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(end_date_str, "%Y%m%d")
    start_date = datetime.strptime(start_date_str, "%Y%m%d")

    windows = []
    curr_end = end_date
    while curr_end > start_date:
        curr_start = max(start_date, curr_end - timedelta(days=chunk_days))
        windows.append((curr_start.strftime("%Y%m%d"), curr_end.strftime("%Y%m%d")))
        curr_end = curr_start - timedelta(days=1)
    return windows

def _all_text(pdf_path):
    text = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text.append(extracted)
    except Exception:
        pass
    return "\n".join(text)

def resolve_unit(path, raw_value, mcap_cr=None, unit_hint=None):
    full = _all_text(path)
    
    # Priority 1: explicit declaration
    m = ROUNDING_FIELD_RE.search(full)
    m2 = PARENS_UNIT_RE.search(full)
    
    if m or m2 or unit_hint:
        unit = None
        if m:
            unit = m.group(1) or m.group(2)
        if not unit and m2:
            unit = m2.group(1)
        if not unit:
            unit = unit_hint
            
        unit = unit.lower().rstrip("s")
        if unit not in UNIT_TO_CR:
            unit = "rupees" if unit == "rupee" else "crore"
            
        flags = []
        if mcap_cr and raw_value * UNIT_TO_CR.get(unit, 1.0) > 2.0 * mcap_cr:
            flags.append("EXPLICIT_UNIT_SUSPECT")
            
        return raw_value * UNIT_TO_CR.get(unit, 1.0), f"explicit:{unit}", False, flags
        
    # Priority 2: magnitude backstop
    flags = []
    if mcap_cr:
        passing = [u for u in BACKSTOP_ORDER if raw_value * UNIT_TO_CR[u] <= 2.0 * mcap_cr]
        if not passing:
            return raw_value, "UNRESOLVED", False, ["SCALE_IMPOSSIBLE"]
        chosen = passing[0] # Deliberate: largest plausible
        if len(passing) > 1:
            flags.append(f"AMBIGUOUS_SCALE:{'/'.join(passing)}")
        return raw_value * UNIT_TO_CR[chosen], f"backstop:{chosen}", chosen != "crore", flags
        
    # Priority 3: no mcap, no declaration
    return raw_value, "UNIT_UNKNOWN", False, flags

def extract_rpt_v2(pdf_path, market_cap_cr=None):
    full_text = _all_text(pdf_path)
    
    # Stage 0: PREFLIGHT
    if "ytrap detaler" in full_text.lower():
        return RptResult("UNPARSABLE", None, None, None, ["REVERSED_TEXT"], None, False)
        
    # Stage 1 & 2: SEBI standard table & SME fallback
    total_val = 0.0
    found_table = False
    col_aliases = ["Value of transaction during the reporting period", "Amount (Rs.)", "Value of Transaction"]
    unit_hint = None
    active_target_col = None
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if not table:
                    continue

                if active_target_col is None:
                    # Find header in top 5 rows
                    for row_idx, row in enumerate(table[:5]):
                        for col_idx, cell in enumerate(row):
                            if cell:
                                cell_text = str(cell).replace('\n', ' ').strip().lower()
                                if any(alias.lower() in cell_text for alias in col_aliases):
                                    active_target_col = col_idx
                                    if "rs." in cell_text or "rupees" in cell_text:
                                        unit_hint = "rupees"
                                    break
                        if active_target_col is not None:
                            break
                    if active_target_col is not None:
                        found_table = True
                        data_rows = table[3:]
                    else:
                        data_rows = []
                else:
                    # Continuation table on subsequent pages (page 2, 3, etc.)
                    first_cell = str(table[0][0] or '').lower() if len(table) > 0 and len(table[0]) > 0 else ''
                    start_idx = 1 if any(h in first_cell for h in ('sr', 'no', 'name', 'details', 'nature')) else 0
                    data_rows = table[start_idx:]

                for row in data_rows:
                    if len(row) > (active_target_col if active_target_col is not None else 0) and row[active_target_col] is not None:
                        val_str = str(row[active_target_col]).replace(',', '').strip()
                        if val_str.startswith('(') and val_str.endswith(')'):
                            val_str = '-' + val_str[1:-1]
                        val_str = re.sub(r'[^\d\.-]', '', val_str)
                        try:
                            if val_str and val_str not in ('-', '.'):
                                total_val += abs(float(val_str))
                        except ValueError:
                            pass
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        
    # Stage 3: Embedded total regex fallback
    if not found_table:
        m = EMBEDDED_TOTAL_RE.search(full_text)
        if m:
            total_val = float(m.group(1).replace(",", ""))
            found_table = True
            
    if not found_table:
        if EXEMPTION_RE.search(full_text):
            return RptResult("EXEMPT", None, None, "BSE_PDF_EXEMPT", [], None, False)
        return RptResult("UNPARSABLE", None, None, None, ["NO_TABLE"], None, False)
        
    # Stage 4: UNIT RESOLUTION
    resolved_val, resolution_method, rescaled, flags = resolve_unit(pdf_path, total_val, market_cap_cr, unit_hint)
    
    if "UNKNOWN" in resolution_method or "UNRESOLVED" in resolution_method:
        return RptResult("NOT_FOUND", None, None, None, flags, resolution_method, rescaled)
        
    return RptResult("OK", resolved_val, None, "BSE_PDF", flags, resolution_method, rescaled)

def main():
    os.makedirs(PDF_DIR, exist_ok=True)
    df = pd.read_csv(SCORES_PATH)
    if os.path.exists('watchlist/active_watchlist.csv'):
        active_df = pd.read_csv('watchlist/active_watchlist.csv')
        if 'symbol' in active_df.columns:
            active_df['ticker'] = active_df['symbol']
            df = pd.concat([df, active_df], ignore_index=True)
            
    fund_cache = {}
    if os.path.exists(FUND_CACHE_PATH):
        with open(FUND_CACHE_PATH, 'r') as f:
            fund_cache = json.load(f)
        
    rpt_cache = init_cache()
    delta_rows = []
    
    parser = argparse.ArgumentParser(description="BSE RPT Scraper & Delta Generator")
    parser.add_argument("--commit-cache", action="store_true", help="Atomically commit verified delta rows to data/rpt_cache.json")
    parser.add_argument("--ticker", type=str, default=None, help="Optional single ticker to scrape (e.g. PAGEIND)")
    args = parser.parse_args()

    for idx, row in df.iterrows():
        ticker = row.get('ticker')
        if pd.isna(row.get('sector_type')) or pd.isna(row.get('bse_scrip')):
            fd = fund_cache.get(ticker, {}).get('data', {})
            if pd.isna(row.get('sector_type')) and fd.get('sector_type'):
                df.at[idx, 'sector_type'] = fd.get('sector_type')
            
    targets = df[(df['sector_type'] != 'financial') & (~df['ticker'].isin(EXCLUDE_TICKERS)) & (df['bse_scrip'].notna())].copy()
    targets = targets.drop_duplicates(subset=['ticker'])
    
    if args.ticker:
        target_ticker = args.ticker.upper().strip()
        targets = targets[targets['ticker'] == target_ticker]
        print(f"Target pool filtered to single ticker: {target_ticker}")
    else:
        print(f"Target pool size: {len(targets)} unique non-financial corporate tickers.")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://www.bseindia.com',
        'Referer': 'https://www.bseindia.com/'
    }
    
    windows = generate_date_windows("20230101")
    if windows:
        print(f"Generated {len(windows)} reverse-chronological search windows (<=350d each) spanning {windows[-1][0]} to {windows[0][1]}.")
    
    for idx, row in targets.iterrows():
        ticker = row['ticker']
        mcap_cr = row.get('market_cap_cr')
        if pd.isna(mcap_cr) and ticker in fund_cache:
            mcap_cr = fund_cache[ticker].get('data', {}).get('market_cap_cr')
            
        scrip = str(row['bse_scrip']).split('.')[0]
        
        print(f"[{ticker}] Fetching Scrip {scrip} across {len(windows)} windows via API...")
        
        try:
            candidates = []
            for w_from, w_to in windows:
                for pageno in range(1, 6):
                    url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno={pageno}&strCat=-1&strPrevDate={w_from}&strScrip={scrip}&strSearch=P&strToDate={w_to}&strType=C"
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code != 200:
                        break
                        
                    data = r.json()
                    table = data.get('Table', [])
                    if not table:
                        break
                    
                    for item in table:
                        subject = str(item.get('NEWSSUB', ''))
                        headline = str(item.get('HEADLINE', ''))
                        if RPT_ANNOUNCEMENT_RE.search(subject) or RPT_ANNOUNCEMENT_RE.search(headline):
                            pdf_filename = item.get('ATTACHMENTNAME')
                            date_str = item.get('NEWS_DT', item.get('DT_TM', ''))
                            if pdf_filename:
                                candidates.append((date_str, pdf_filename))
                if candidates:
                    break
                            
            pdf_filename = None
            if candidates:
                # NEWS_DT format is proven to be ISO-8601 (e.g. '2024-05-08T20:39:00.957'), so string max is chronologically correct.
                pdf_filename = max(candidates, key=lambda c: c[0])[1]
                    
            new_result = None
            if pdf_filename:
                pdf_path = os.path.join(PDF_DIR, f"{ticker}_rpt.pdf")
                
                if not os.path.exists(pdf_path):
                    pdf_url_live = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{pdf_filename}"
                    pdf_url_his = f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{pdf_filename}"
                    
                    pdf_r = requests.get(pdf_url_live, headers=headers, timeout=10)
                    if pdf_r.status_code == 404:
                        pdf_r = requests.get(pdf_url_his, headers=headers, timeout=10)
                        
                    if pdf_r.status_code == 200:
                        with open(pdf_path, 'wb') as f_pdf:
                            f_pdf.write(pdf_r.content)
                
                if os.path.exists(pdf_path):
                    rpt_obj = extract_rpt_v2(pdf_path, market_cap_cr=mcap_cr)
                    if rpt_obj.status == "OK":
                        fund_data = fund_cache.get(ticker, {}).get('data', {})
                        revenue = fund_data.get('revenue_ttm_cr')
                        if not revenue:
                            fetcher = FundamentalFetcher()
                            live_data = fetcher.fetch(ticker)
                            revenue = live_data.get('revenue_ttm_cr')

                        if revenue and revenue > 0:
                            rpt_pct = round((rpt_obj.rpt_amount_cr / revenue) * 100, 2)
                            new_result = {
                                "status": "OK",
                                "rpt_amount_cr": round(rpt_obj.rpt_amount_cr, 2),
                                "rpt_pct": rpt_pct,
                                "filing_type": "BSE_PDF",
                                "flags": "|".join(rpt_obj.flags),
                                "unit_source": rpt_obj.unit_source,
                                "rescaled": rpt_obj.rescaled
                            }
                        else:
                            new_result = {"status": "NOT_FOUND", "rpt_amount_cr": None, "rpt_pct": None, "filing_type": None, "flags": "NO_REVENUE", "unit_source": None, "rescaled": False}
                    elif rpt_obj.status == "EXEMPT":
                        new_result = {"status": "EXEMPT", "rpt_amount_cr": None, "rpt_pct": None, "filing_type": "BSE_PDF_EXEMPT", "flags": "", "unit_source": None, "rescaled": False}
                    else:
                        new_result = {"status": rpt_obj.status, "rpt_amount_cr": None, "rpt_pct": None, "filing_type": None, "flags": "|".join(rpt_obj.flags), "unit_source": getattr(rpt_obj, 'unit_source', None), "rescaled": getattr(rpt_obj, 'rescaled', False)}
            else:
                new_result = {"status": "NOT_FOUND", "rpt_amount_cr": None, "rpt_pct": None, "filing_type": None, "flags": "NO_FILING", "unit_source": None, "rescaled": False}
                
            old_result = rpt_cache.get(ticker, {})
            delta_rows.append({
                "ticker": ticker,
                "old_status": old_result.get("status", "NOT_FOUND"),
                "old_amount": old_result.get("rpt_amount_cr"),
                "new_status": new_result.get("status") if new_result else "ERROR",
                "new_amount": new_result.get("rpt_amount_cr") if new_result else None,
                "new_pct": new_result.get("rpt_pct") if new_result else None,
                "filing_type": new_result.get("filing_type") if new_result else None,
                "flags": new_result.get("flags", "") if new_result else "",
                "unit_source": new_result.get("unit_source", "") if new_result else "",
                "rescaled": new_result.get("rescaled", False) if new_result else False
            })
            
        except Exception as e:
            print(f"[{ticker}] Error: {e}")
            
        time.sleep(0.5)
            
    print("Done Phase B scraping (API Mode) - V2 Delta Table Generated.")
    
    delta_df = pd.DataFrame(delta_rows)
    delta_df.to_csv(DELTA_TABLE_PATH, index=False)
    print(f"Delta table saved to {DELTA_TABLE_PATH}")

    if args.commit_cache:
        curr_cache = init_cache()
        promoted_count = 0
        for row in delta_rows:
            t = row["ticker"]
            st = row["new_status"]
            if st in ("OK", "EXEMPT"):
                curr_cache[t] = {
                    "status": st,
                    "rpt_amount_cr": row.get("new_amount"),
                    "rpt_pct": row.get("new_pct"),
                    "filing_type": row.get("filing_type"),
                    "flags": row.get("flags", ""),
                    "unit_source": row.get("unit_source", ""),
                    "rescaled": row.get("rescaled", False)
                }
                promoted_count += 1
        temp_cache_path = RPT_CACHE_PATH + ".tmp"
        with open(temp_cache_path, "w", encoding="utf-8") as f:
            json.dump(curr_cache, f, indent=2)
        os.replace(temp_cache_path, RPT_CACHE_PATH)
        print(f"Atomically committed {promoted_count} verified RPT entries to {RPT_CACHE_PATH}")
    else:
        print("Dry-run mode: Cache NOT updated (pass --commit-cache to promote verified entries).")

if __name__ == '__main__':
    main()
