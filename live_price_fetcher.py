"""
Live Price Fetcher & SL/TP Proximity Engine for Pro-Spike.

Features:
- Fetches real-time market prices (CMP / LTP) for all open active positions
  across SBIA Alpha, FlexGate, FlexGate 2.0, and Corner Spike engines.
- Proper BSE (.BO) vs NSE (.NS) exchange routing to eliminate 404/delisted errors.
- Concurrent multi-threaded fetching with ThreadPoolExecutor (< 4 sec runtime).
- 60-second local JSON disk cache (data/live_quotes_cache.json) to prevent API rate limits.
- Computes precise real-time SL/TP proximity percentages and urgency tiers:
    * BREACHED_SL: CMP <= Stop Loss
    * NEAR_SL: 0 < Distance to SL <= 3.0%
    * NEAR_TP: 0 <= Distance to TP <= 3.0%
    * HIT_TP: CMP >= Take Profit
    * HEALTHY: Comfortable buffer above SL
- Read-only invariant: Never mutates raw strategy ledgers.
"""

import os
import time
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pandas as pd
import yfinance as yf

CACHE_FILE = os.path.join("data", "live_quotes_cache.json")
CLOUD_FILE = os.path.join("data", "dashboard_cloud.csv")
LIVE_FILE = os.path.join("data", "combined_dashboard_live.csv")

LEDGER_FILES = [
    ("SBIA Alpha", os.path.join("data", "sbia_ledger.csv")),
    ("FlexGate", os.path.join("data", "flexgate_ledger.csv")),
    ("FlexGate 2.0", os.path.join("data", "flexgate2_ledger.csv")),
    ("Corner Spike", os.path.join("data", "corner_engine_ledger.csv")),
]


def get_active_symbols() -> list[str]:
    """Return sorted list of all unique symbols currently ACTIVE across all 4 strategy ledgers."""
    active_syms = set()
    for _, path in LEDGER_FILES:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                if "STATUS" in df.columns and "SYMBOL" in df.columns:
                    act = df[df["STATUS"] == "ACTIVE"]["SYMBOL"].dropna().str.strip().str.upper()
                    active_syms.update(act.tolist())
            except Exception:
                pass
    return sorted(list(active_syms))


def get_exchange_map() -> dict[str, str]:
    """Build mapping of SYMBOL -> 'NSE' | 'BSE' using cloud and live files."""
    exch_map = {}
    for p in (CLOUD_FILE, LIVE_FILE):
        if os.path.exists(p):
            try:
                df = pd.read_csv(p)
                if {"SYMBOL", "EXCHANGE"}.issubset(df.columns):
                    for _, r in df.dropna(subset=["SYMBOL", "EXCHANGE"]).iterrows():
                        s = str(r["SYMBOL"]).strip().upper()
                        e = str(r["EXCHANGE"]).strip().upper()
                        if s and e and s not in exch_map:
                            exch_map[s] = e
            except Exception:
                pass
    return exch_map


def _fetch_single_quote(symbol: str, exch: str) -> tuple[str, float | None]:
    """Fetch live CMP for a single symbol with primary/secondary exchange fallback."""
    primary_suffix = ".BO" if exch == "BSE" else ".NS"
    alt_suffix = ".NS" if primary_suffix == ".BO" else ".BO"

    # Try primary exchange
    try:
        tk = yf.Ticker(symbol + primary_suffix)
        price = tk.fast_info.get("last_price")
        if price and price > 0:
            return symbol, float(price)
    except Exception:
        pass

    # Fallback to alternate exchange
    try:
        tk = yf.Ticker(symbol + alt_suffix)
        price = tk.fast_info.get("last_price")
        if price and price > 0:
            return symbol, float(price)
    except Exception:
        pass

    return symbol, None


def get_live_quotes(
    symbols: list[str] | None = None,
    force_refresh: bool = False,
    ttl_seconds: int = 60,
    max_workers: int = 10,
) -> dict[str, dict]:
    """Fetch live quotes for active symbols.

    Returns a dict keyed by SYMBOL containing:
      {'cmp': float, 'exchange': str, 'timestamp': float, 'time_str': str, 'source': str}
    """
    if symbols is None:
        symbols = get_active_symbols()

    if not symbols:
        return {}

    now_ts = time.time()

    # 1. Check local cache first
    cached_data = {}
    if os.path.exists(CACHE_FILE) and not force_refresh:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                cache_ts = raw.get("timestamp", 0)
                if (now_ts - cache_ts) < ttl_seconds:
                    cached_quotes = raw.get("quotes", {})
                    # If all requested symbols exist in cache, return immediately
                    if all(s in cached_quotes for s in symbols):
                        return cached_quotes
                    cached_data = cached_quotes
        except Exception:
            cached_data = {}

    exch_map = get_exchange_map()

    # 2. Parallel network fetch for missing or expired symbols
    symbols_to_fetch = [s for s in symbols if force_refresh or (s not in cached_data)]
    new_quotes = dict(cached_data)

    if symbols_to_fetch:
        tasks = [(s, exch_map.get(s, "NSE")) for s in symbols_to_fetch]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(lambda args: _fetch_single_quote(*args), tasks)
            for sym, px in results:
                if px is not None and px > 0:
                    new_quotes[sym] = {
                        "cmp": round(px, 2),
                        "exchange": exch_map.get(sym, "NSE"),
                        "timestamp": now_ts,
                        "time_str": datetime.now().strftime("%I:%M:%S %p"),
                        "source": "live_yfinance",
                    }

    # 3. Fallback for any unresolvable tickers to dashboard_cloud.csv EOD close
    eod_prices = {}
    if os.path.exists(CLOUD_FILE):
        try:
            cdf = pd.read_csv(CLOUD_FILE)
            if {"SYMBOL", "CLOSE"}.issubset(cdf.columns):
                eod_prices = cdf.drop_duplicates("SYMBOL").set_index("SYMBOL")["CLOSE"].to_dict()
        except Exception:
            pass

    for s in symbols:
        if s not in new_quotes or new_quotes[s].get("cmp") is None:
            fallback_px = eod_prices.get(s, 0.0)
            new_quotes[s] = {
                "cmp": round(float(fallback_px), 2) if fallback_px else None,
                "exchange": exch_map.get(s, "NSE"),
                "timestamp": now_ts,
                "time_str": datetime.now().strftime("%I:%M:%S %p"),
                "source": "eod_fallback",
            }

    # 4. Save to cache
    try:
        payload = {
            "timestamp": now_ts,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "quotes": new_quotes,
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass

    return new_quotes


def compute_trade_proximity(
    symbol: str,
    entry_price: float | None,
    stop_loss: float | None,
    take_profit: float | None = None,
    chandelier_exit: float | None = None,
    cmp: float | None = None,
) -> dict:
    """Calculate exact real-time SL / TP proximity and urgency classification.

    Parameters:
      symbol: Stock ticker
      entry_price: Original trade entry price
      stop_loss: Hard initial stop loss price
      take_profit: Optional fixed take-profit target
      chandelier_exit: Optional dynamic trailing stop level
      cmp: Optional pre-fetched CMP (fetched automatically if None)

    Returns:
      Dict with cmp, pnl_pct, sl_dist_pct, tp_dist_pct, urgency, badge_text, badge_color
    """
    if cmp is None or cmp <= 0:
        quotes = get_live_quotes([symbol])
        q = quotes.get(symbol, {})
        cmp = q.get("cmp")

    effective_sl = None
    if chandelier_exit is not None and pd.notna(chandelier_exit) and float(chandelier_exit) > 0:
        effective_sl = float(chandelier_exit)
    elif stop_loss is not None and pd.notna(stop_loss) and float(stop_loss) > 0:
        effective_sl = float(stop_loss)

    tp = float(take_profit) if (take_profit is not None and pd.notna(take_profit) and float(take_profit) > 0) else None
    entry = float(entry_price) if (entry_price is not None and pd.notna(entry_price) and float(entry_price) > 0) else None

    # Calculate PnL %
    pnl_pct = ((cmp - entry) / entry * 100) if (cmp and entry) else None

    # Calculate Distance to SL
    sl_dist_pct = None
    if cmp and effective_sl:
        sl_dist_pct = (cmp - effective_sl) / cmp * 100

    # Calculate Distance to TP
    tp_dist_pct = None
    if cmp and tp:
        tp_dist_pct = (tp - cmp) / cmp * 100

    # Determine Urgency
    if cmp and effective_sl and cmp <= effective_sl:
        urgency = "BREACHED_SL"
        badge_text = f"🚨 BELOW SL ({effective_sl:.2f})"
        badge_bg = "rgba(239, 68, 68, 0.20)"
        badge_fg = "#f87171"
    elif sl_dist_pct is not None and 0.0 < sl_dist_pct <= 3.0:
        urgency = "NEAR_SL"
        badge_text = f"⚠️ {sl_dist_pct:.1f}% to SL"
        badge_bg = "rgba(245, 158, 11, 0.20)"
        badge_fg = "#fbbf24"
    elif tp and cmp and cmp >= tp:
        urgency = "HIT_TP"
        badge_text = f"🚀 HIT TARGET ({tp:.2f})"
        badge_bg = "rgba(16, 185, 129, 0.20)"
        badge_fg = "#34d399"
    elif tp_dist_pct is not None and 0.0 <= tp_dist_pct <= 3.0:
        urgency = "NEAR_TP"
        badge_text = f"🎯 {tp_dist_pct:.1f}% to TP"
        badge_bg = "rgba(56, 189, 248, 0.20)"
        badge_fg = "#38bdf8"
    elif sl_dist_pct is not None:
        urgency = "HEALTHY"
        badge_text = f"🛡️ {sl_dist_pct:.1f}% buffer"
        badge_bg = "rgba(148, 163, 184, 0.12)"
        badge_fg = "#94a3b8"
    else:
        urgency = "UNKNOWN"
        badge_text = "—"
        badge_bg = "transparent"
        badge_fg = "#64748b"

    return {
        "cmp": cmp,
        "entry_price": entry,
        "effective_sl": effective_sl,
        "take_profit": tp,
        "pnl_pct": pnl_pct,
        "sl_dist_pct": sl_dist_pct,
        "tp_dist_pct": tp_dist_pct,
        "urgency": urgency,
        "badge_text": badge_text,
        "badge_bg": badge_bg,
        "badge_fg": badge_fg,
    }


def get_portfolio_proximity_summary(force_refresh: bool = False) -> dict:
    """Analyze all active trades across all 4 strategy ledgers and build portfolio radar data."""
    active_syms = get_active_symbols()
    quotes = get_live_quotes(active_syms, force_refresh=force_refresh)

    trades = []
    near_sl = []
    near_tp = []
    breached_sl = []
    healthy = []

    last_time = "Just now"

    for engine, path in LEDGER_FILES:
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
            if "STATUS" not in df.columns or "SYMBOL" not in df.columns:
                continue
            act = df[df["STATUS"] == "ACTIVE"].copy()
            for _, r in act.iterrows():
                sym = str(r["SYMBOL"]).strip().upper()
                q = quotes.get(sym, {})
                cmp_val = q.get("cmp")
                if q.get("time_str"):
                    last_time = q["time_str"]

                prox = compute_trade_proximity(
                    symbol=sym,
                    entry_price=r.get("ENTRY_PRICE"),
                    stop_loss=r.get("STOP_LOSS"),
                    take_profit=r.get("TAKE_PROFIT"),
                    chandelier_exit=r.get("CHANDELIER_EXIT"),
                    cmp=cmp_val,
                )

                item = {
                    "engine": engine,
                    "symbol": sym,
                    "entry_date": str(r.get("ENTRY_DATE", "-")),
                    "entry_price": prox["entry_price"],
                    "cmp": prox["cmp"],
                    "effective_sl": prox["effective_sl"],
                    "take_profit": prox["take_profit"],
                    "pnl_pct": prox["pnl_pct"],
                    "sl_dist_pct": prox["sl_dist_pct"],
                    "tp_dist_pct": prox["tp_dist_pct"],
                    "urgency": prox["urgency"],
                    "badge_text": prox["badge_text"],
                    "badge_bg": prox["badge_bg"],
                    "badge_fg": prox["badge_fg"],
                    "source": q.get("source", "eod"),
                }
                trades.append(item)

                if prox["urgency"] == "BREACHED_SL":
                    breached_sl.append(item)
                elif prox["urgency"] == "NEAR_SL":
                    near_sl.append(item)
                elif prox["urgency"] == "NEAR_TP":
                    near_tp.append(item)
                elif prox["urgency"] == "HEALTHY":
                    healthy.append(item)
        except Exception:
            pass

    return {
        "total_active": len(trades),
        "unique_symbols": len(active_syms),
        "near_sl": sorted(near_sl, key=lambda x: x["sl_dist_pct"] if x["sl_dist_pct"] is not None else 999),
        "near_tp": sorted(near_tp, key=lambda x: x["tp_dist_pct"] if x["tp_dist_pct"] is not None else 999),
        "breached_sl": breached_sl,
        "healthy_count": len(healthy),
        "last_updated": last_time,
        "quotes": quotes,
    }


if __name__ == "__main__":
    print("Testing live price fetcher & proximity analysis...")
    summary = get_portfolio_proximity_summary(force_refresh=True)
    print(f"Total Active Positions: {summary['total_active']} ({summary['unique_symbols']} unique symbols)")
    print(f"Last Updated: {summary['last_updated']}")
    print(f"Breached SL: {len(summary['breached_sl'])}")
    print(f"Near SL (<3%): {len(summary['near_sl'])}")
    for item in summary["near_sl"]:
        txt = item['badge_text'].encode('ascii', errors='replace').decode('ascii')
        print(f"  [{item['engine']}] {item['symbol']}: CMP {item['cmp']} vs SL {item['effective_sl']} -> {txt}")
    print(f"Near TP (<3%): {len(summary['near_tp'])}")
    for item in summary["near_tp"]:
        txt = item['badge_text'].encode('ascii', errors='replace').decode('ascii')
        print(f"  [{item['engine']}] {item['symbol']}: CMP {item['cmp']} vs TP {item['take_profit']} -> {txt}")
    print(f"Healthy: {summary['healthy_count']}")

