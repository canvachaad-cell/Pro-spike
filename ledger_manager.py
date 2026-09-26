import pandas as pd
import numpy as np
import yfinance as yf
import os

def check_signal_eligibility(ledger_df, sym, trigger_dt, cooldown_days=14):
    """
    Enforces:
    1. Max 1 Active Trade: No stacking if symbol is already ACTIVE.
    2. Conditional Post-Loss Lockout: Blocks re-entry for 14 calendar days after a LOSS.
    3. Positive Continuation: Freely permits re-entry after a WIN.
    """
    if ledger_df.empty:
        return True, "FIRST_ENTRY"

    sym_trades = ledger_df[ledger_df['SYMBOL'] == sym]
    if sym_trades.empty:
        return True, "FIRST_ENTRY"

    # Rule 1: No stacking while active
    if (sym_trades['STATUS'] == 'ACTIVE').any():
        return False, "ALREADY_ACTIVE"

    # Exact duplicate entry check
    trigger_ts = pd.to_datetime(trigger_dt)
    if (sym_trades['ENTRY_DATE'] == trigger_ts).any():
        return False, "DUPLICATE_ENTRY_DATE"

    # Rule 2: Check most recent closed trade
    closed = sym_trades[sym_trades['STATUS'].isin(['HIT_TP', 'HIT_SL', 'MOMENTUM_LOST'])].copy()
    if closed.empty:
        return True, "CLEARED"

    closed['EXIT_DT'] = pd.to_datetime(closed['EXIT_DATE'], errors='coerce')
    valid_closed = closed[closed['EXIT_DT'].notna() & (closed['EXIT_DT'] <= trigger_ts)]
    if valid_closed.empty:
        valid_closed = closed[closed['EXIT_DT'].notna()]
        if valid_closed.empty:
            return True, "CLEARED"

    last_trade = valid_closed.sort_values('EXIT_DT').iloc[-1]

    # Determine if last trade was a WIN or LOSS
    is_loss = (last_trade['STATUS'] == 'HIT_SL') or (
        last_trade['STATUS'] == 'MOMENTUM_LOST' and
        pd.notna(last_trade.get('EXIT_PRICE')) and
        last_trade['EXIT_PRICE'] < last_trade['ENTRY_PRICE']
    )

    if is_loss and pd.notna(last_trade['EXIT_DT']):
        days_since_exit = (trigger_ts - last_trade['EXIT_DT']).days
        if 0 <= days_since_exit < cooldown_days:
            return False, f"POST_LOSS_LOCKOUT ({days_since_exit}d < {cooldown_days}d)"

    return True, "CLEARED"


def _hydrate_missing_active_watchlist(filtered_wl, active_ledger, latest_prices_df, archive_path=None, is_flexgate=False):
    """
    Guarantees that 100% of open ACTIVE trades from the ledger are present in the active watchlist.
    Synthesizes entries for active trades not triggered today using ledger parameters and live metrics.
    """
    if active_ledger.empty:
        return filtered_wl

    import numpy as np
    filtered_wl = filtered_wl.copy() if filtered_wl is not None else pd.DataFrame()
    if 'DATE_DT' in filtered_wl.columns:
        present_keys = set(zip(filtered_wl['SYMBOL'], pd.to_datetime(filtered_wl['DATE_DT'])))
    elif 'DATE' in filtered_wl.columns:
        present_keys = set(zip(filtered_wl['SYMBOL'], pd.to_datetime(filtered_wl['DATE'], errors='coerce')))
    else:
        present_keys = set()

    missing_active = active_ledger[
        active_ledger.apply(lambda r: (r['SYMBOL'], pd.to_datetime(r['ENTRY_DATE'])) not in present_keys, axis=1)
    ].copy()

    if missing_active.empty:
        # Still ensure live prices are updated
        if not latest_prices_df.empty and {'SYMBOL', 'CLOSE'}.issubset(latest_prices_df.columns):
            live_px_map = latest_prices_df.drop_duplicates('SYMBOL').set_index('SYMBOL')['CLOSE'].to_dict()
            if 'CLOSE' in filtered_wl.columns:
                filtered_wl['CLOSE'] = filtered_wl['SYMBOL'].map(live_px_map).fillna(filtered_wl['CLOSE'])
        if is_flexgate and 'STOP_LOSS' in filtered_wl.columns:
            filtered_wl['CHANDELIER_EXIT'] = filtered_wl['STOP_LOSS']
        return filtered_wl

    arch_df = None
    if archive_path and os.path.exists(archive_path):
        try:
            arch_df = pd.read_csv(archive_path)
            arch_df['DATE_STR'] = pd.to_datetime(arch_df['DATE'], errors='coerce').dt.strftime('%Y-%m-%d')
        except Exception:
            arch_df = None

    syn_rows = []
    for _, a_row in missing_active.iterrows():
        sym = a_row['SYMBOL']
        entry_dt = pd.to_datetime(a_row['ENTRY_DATE'])
        dt_str = entry_dt.strftime('%Y-%m-%d')

        entry_px = a_row.get('ENTRY_PRICE', np.nan)
        sl = a_row.get('STOP_LOSS', np.nan)
        tp = a_row.get('TAKE_PROFIT', np.nan)
        atr = a_row.get('ATR14', np.nan)
        prob = a_row.get('ENTRY_AI_PROB', 60.0) if pd.notna(a_row.get('ENTRY_AI_PROB')) else 60.0

        syn = {
            'DATE': dt_str,
            'DATE_DT': entry_dt,
            'SYMBOL': sym,
            'ENTRY_PRICE': entry_px,
            'ATR14': atr,
            'STOP_LOSS': sl,
            'CHANDELIER_EXIT': sl,
            'TAKE_PROFIT': tp,
            'AI_WIN_PROBABILITY': prob,
            'AI_APPROVED': bool(prob >= 60.0),
            'Whale_Density': a_row.get('ENTRY_WHALE_DENSITY', 0.0),
            'Implied_Trades': a_row.get('ENTRY_IMPLIED_TRADES', 0.0),
            'REC_POS_SIZE_INR': 100000.0,
        }
        if is_flexgate:
            syn['CHANDELIER_EXIT'] = sl
            syn['IS_FLEXGATE_ALERT'] = True

        # Inherit historical screener metrics from archive if present
        if arch_df is not None:
            m_arch = arch_df[(arch_df['SYMBOL'] == sym) & (arch_df['DATE_STR'] == dt_str)]
            if not m_arch.empty:
                arch_row = m_arch.iloc[-1].to_dict()
                for k in ['ISIN', 'EXCHANGE', 'SIS', 'MOMENTUM_RAW', 'FOOTPRINT_RAW', 'STABILITY_RAW', 
                          'MOMENTUM_SCORE', 'FOOTPRINT_SCORE', 'STABILITY_SCORE', 'DELIV_PER', 
                          'DELIVERY_TURNOVER', 'TOTAL_TURNOVER', 'VOLUME', 'VWAP', 'VWAP_1M',
                          'WHALE_DENSITY', 'WHALE_DENSITY_1M', 'ATW', 'EVER_100_DELIV']:
                    if k in arch_row and k not in syn:
                        syn[k] = arch_row[k]

        # Enrich with latest live market metrics
        if not latest_prices_df.empty and 'SYMBOL' in latest_prices_df.columns:
            m_live = latest_prices_df[latest_prices_df['SYMBOL'] == sym]
            if not m_live.empty:
                live_row = m_live.iloc[-1].to_dict()
                syn['CLOSE'] = live_row.get('CLOSE', entry_px)
                if 'EXCHANGE' not in syn or pd.isna(syn.get('EXCHANGE')):
                    syn['EXCHANGE'] = live_row.get('EXCHANGE', 'NSE')
                if 'ISIN' not in syn or pd.isna(syn.get('ISIN')):
                    syn['ISIN'] = live_row.get('ISIN', '')
                if 'Whale_Density' not in syn or syn['Whale_Density'] == 0:
                    syn['Whale_Density'] = live_row.get('WHALE_DENSITY', syn.get('Whale_Density', 0.0))
            else:
                syn['CLOSE'] = entry_px
        else:
            syn['CLOSE'] = entry_px

        syn_rows.append(syn)

    if syn_rows:
        syn_df = pd.DataFrame(syn_rows)
        filtered_wl = pd.concat([filtered_wl, syn_df], ignore_index=True)

    # Refresh live CLOSE prices across all active rows
    if not latest_prices_df.empty and {'SYMBOL', 'CLOSE'}.issubset(latest_prices_df.columns):
        live_px_map = latest_prices_df.drop_duplicates('SYMBOL').set_index('SYMBOL')['CLOSE'].to_dict()
        if 'CLOSE' in filtered_wl.columns:
            filtered_wl['CLOSE'] = filtered_wl['SYMBOL'].map(live_px_map).fillna(filtered_wl['CLOSE'])

    if is_flexgate and 'STOP_LOSS' in filtered_wl.columns:
        filtered_wl['CHANDELIER_EXIT'] = filtered_wl['STOP_LOSS']

    return filtered_wl


def update_sbia_ledger(alpha_watchlist, latest_prices_df, ledger_path="data/sbia_ledger.csv"):
    """
    Updates the permanent trade ledger for SBIA Alpha signals.
    Calculates STATIC Stop Loss and Take Profit based on the Entry Date.
    Classifies trades into ACTIVE, HIT_TP, HIT_SL, MOMENTUM_LOST, SUSPENDED.
    """
    if alpha_watchlist.empty:
        return alpha_watchlist, pd.DataFrame()

    # 1. Load existing ledger
    if os.path.exists(ledger_path):
        ledger_df = pd.read_csv(ledger_path)
    else:
        ledger_df = pd.DataFrame(columns=[
            'ENTRY_DATE', 'SYMBOL', 'ENTRY_PRICE', 'ATR14', 'STOP_LOSS', 'TAKE_PROFIT', 
            'ENTRY_AI_PROB', 'ENTRY_WHALE_DENSITY', 'ENTRY_IMPLIED_TRADES',
            'STATUS', 'EXIT_DATE', 'EXIT_PRICE'
        ])
        
    ledger_df['ENTRY_DATE'] = pd.to_datetime(ledger_df['ENTRY_DATE'])
    if 'EXIT_DATE' in ledger_df.columns:
        ledger_df['EXIT_DATE'] = pd.to_datetime(ledger_df['EXIT_DATE'], errors='coerce')
        
    # 2. Identify NEW signals from alpha_watchlist
    alpha_watchlist = alpha_watchlist.copy()
    alpha_watchlist['DATE_DT'] = pd.to_datetime(alpha_watchlist['DATE'])
    
    new_signals = []
    for _, row in alpha_watchlist.iterrows():
        sym = row['SYMBOL']
        dt = row['DATE_DT']
        
        eligible, reason = check_signal_eligibility(ledger_df, sym, dt, cooldown_days=14)
        if eligible:
            new_signals.append(row)
        else:
            print(f"[RE-ENTRY GATE] SBIA candidate {sym} on {dt.strftime('%Y-%m-%d')} skipped: {reason}")
            
    # Gather ALL symbols we need data for: New signals + existing ACTIVE signals
    active_symbols = ledger_df[ledger_df['STATUS'] == 'ACTIVE']['SYMBOL'].unique().tolist()
    new_syms = [row['SYMBOL'] for row in new_signals]
    all_needed_symbols = list(set(active_symbols + new_syms))
    
    symbol_to_yf = {}
    if not latest_prices_df.empty and 'EXCHANGE' in latest_prices_df.columns:
        exch_map = latest_prices_df.drop_duplicates('SYMBOL').set_index('SYMBOL')['EXCHANGE'].to_dict()
    else:
        exch_map = {}

    data = None
    if all_needed_symbols:
        for s in all_needed_symbols:
            exch = exch_map.get(s, 'NSE')
            suffix = ".BO" if exch == "BSE" else ".NS"
            symbol_to_yf[s] = f"{s}{suffix}"
            
        yf_symbols = list(set(symbol_to_yf.values()))
        print(f"Fetching historical path data for {len(yf_symbols)} symbols...")
        data = yf.download(yf_symbols, period="6mo", progress=False, group_by="ticker")
        
    # 3. Process new signals
    if new_signals:
        new_df = pd.DataFrame(new_signals)
        print(f"Adding {len(new_df)} new signals to the trade ledger...")
        new_records = []
        for _, row in new_df.iterrows():
            sym = row['SYMBOL']
            dt = row['DATE_DT']
            try:
                if len(all_needed_symbols) == 1:
                    ticker_df = data
                else:
                    yf_sym = symbol_to_yf.get(sym, f"{sym}.NS")
                    if yf_sym not in data.columns.levels[0] if isinstance(data.columns, pd.MultiIndex) else data.columns:
                        raise KeyError(yf_sym)
                    ticker_df = data[yf_sym]
                    
                hist_up_to_dt = ticker_df[ticker_df.index.tz_localize(None) <= dt].copy()
                hist_up_to_dt = hist_up_to_dt.dropna(subset=['Close'])
                
                if len(hist_up_to_dt) > 0:
                    high_low = hist_up_to_dt['High'] - hist_up_to_dt['Low']
                    high_close = np.abs(hist_up_to_dt['High'] - hist_up_to_dt['Close'].shift())
                    low_close = np.abs(hist_up_to_dt['Low'] - hist_up_to_dt['Close'].shift())
                    ranges = pd.concat([high_low, high_close, low_close], axis=1)
                    true_range = np.max(ranges, axis=1)
                    
                    window = min(14, len(hist_up_to_dt))
                    atr14 = true_range.rolling(window).mean().iloc[-1]
                    entry_price = hist_up_to_dt['Close'].iloc[-1]
                    
                    if pd.notna(atr14) and atr14 > 0:
                        sl = entry_price - (2.0 * atr14)
                        tp = entry_price + (4.0 * atr14)
                    else:
                        sl = np.nan
                        tp = np.nan
                        
                    new_records.append({
                        'ENTRY_DATE': dt,
                        'SYMBOL': sym,
                        'ENTRY_PRICE': entry_price,
                        'ATR14': atr14,
                        'STOP_LOSS': sl,
                        'TAKE_PROFIT': tp,
                        'ENTRY_AI_PROB': row.get('AI_WIN_PROBABILITY', np.nan),
                        'ENTRY_WHALE_DENSITY': row.get('Whale_Density', np.nan),
                        'ENTRY_IMPLIED_TRADES': row.get('Implied_Trades', np.nan),
                        'STATUS': 'ACTIVE',
                        'EXIT_DATE': pd.NaT,
                        'EXIT_PRICE': np.nan
                    })
            except Exception as e:
                print(f"Failed to initialize ledger for {sym} on {dt}: {e}")
                
        if new_records:
            ledger_df = pd.concat([ledger_df, pd.DataFrame(new_records)], ignore_index=True)
            
    # 4. Update status of ACTIVE trades by walking the historical price path
    latest_date = pd.to_datetime(latest_prices_df['DATE'].max()) if 'DATE' in latest_prices_df.columns else pd.Timestamp.now().normalize()
    watchlist_keys = set(zip(alpha_watchlist['SYMBOL'], alpha_watchlist['DATE_DT']))
    
    for idx, row in ledger_df.iterrows():
        if row['STATUS'] == 'ACTIVE':
            sym = row['SYMBOL']
            entry_dt = row['ENTRY_DATE']
            
            if pd.isna(row['STOP_LOSS']):
                ledger_df.at[idx, 'STATUS'] = 'SUSPENDED'
                ledger_df.at[idx, 'EXIT_DATE'] = latest_date
                ledger_df.at[idx, 'EXIT_PRICE'] = row['ENTRY_PRICE']
                continue

            if sym in ['JBCHEPHARM']:
                ledger_df.at[idx, 'STATUS'] = 'SUSPENDED'
                ledger_df.at[idx, 'EXIT_DATE'] = latest_date
                ledger_df.at[idx, 'EXIT_PRICE'] = row['ENTRY_PRICE']
                continue

            # Historical Path Check
            if data is not None:
                yf_sym = symbol_to_yf.get(sym, f"{sym}.NS")
                if len(yf_symbols) == 1:
                    ticker_df = data
                else:
                    ticker_df = data[yf_sym]
                    
                # Path must strictly evaluate days AFTER entry date to avoid Day-0 morning low lookback leakage
                path_df = ticker_df[ticker_df.index.tz_localize(None) > entry_dt].copy()
                path_df = path_df.dropna(subset=['Close'])
                
                hit = False
                for p_date, p_row in path_df.iterrows():
                    # Check if High crossed TP
                    if pd.notna(row['TAKE_PROFIT']) and p_row['High'] >= row['TAKE_PROFIT']:
                        ledger_df.at[idx, 'STATUS'] = 'HIT_TP'
                        ledger_df.at[idx, 'EXIT_DATE'] = p_date.tz_localize(None)
                        ledger_df.at[idx, 'EXIT_PRICE'] = row['TAKE_PROFIT']
                        hit = True
                        break
                    
                    # Check if Low crossed SL
                    if pd.notna(row['STOP_LOSS']) and p_row['Low'] <= row['STOP_LOSS']:
                        ledger_df.at[idx, 'STATUS'] = 'HIT_SL'
                        ledger_df.at[idx, 'EXIT_DATE'] = p_date.tz_localize(None)
                        ledger_df.at[idx, 'EXIT_PRICE'] = row['STOP_LOSS']
                        hit = True
                        break
                        
                if hit:
                    continue
            
            # If we didn't hit SL or TP along the path, check momentum loss
            if (sym, entry_dt) not in watchlist_keys:
                days_held = (latest_date - entry_dt).days
                if days_held >= 10:
                    ledger_df.at[idx, 'STATUS'] = 'MOMENTUM_LOST'
                    ledger_df.at[idx, 'EXIT_DATE'] = latest_date
                    ledger_df.at[idx, 'EXIT_PRICE'] = path_df['Close'].iloc[-1] if data is not None and len(path_df) > 0 else row['ENTRY_PRICE']
                
    # 5. Filter alpha_watchlist
    active_ledger = ledger_df[ledger_df['STATUS'] == 'ACTIVE'].copy()
    active_keys = set(zip(active_ledger['SYMBOL'], pd.to_datetime(active_ledger['ENTRY_DATE'])))
    
    filtered_alpha = alpha_watchlist[
        alpha_watchlist.apply(lambda row: (row['SYMBOL'], row['DATE_DT']) in active_keys, axis=1)
    ].copy()
    
    cols_to_drop = [c for c in ['STOP_LOSS', 'TAKE_PROFIT', 'ENTRY_PRICE', 'ATR14'] if c in filtered_alpha.columns]
    if cols_to_drop:
        filtered_alpha = filtered_alpha.drop(columns=cols_to_drop)
        
    active_ledger_subset = active_ledger[['SYMBOL', 'ENTRY_DATE', 'ENTRY_PRICE', 'ATR14', 'STOP_LOSS', 'TAKE_PROFIT']]
    active_ledger_subset = active_ledger_subset.rename(columns={'ENTRY_DATE': 'DATE_DT'})
    active_ledger_subset['DATE_DT'] = pd.to_datetime(active_ledger_subset['DATE_DT'])
    
    filtered_alpha = pd.merge(filtered_alpha, active_ledger_subset, on=['SYMBOL', 'DATE_DT'], how='left')

    # Hydrate any open active positions from ledger missing from filtered_alpha
    filtered_alpha = _hydrate_missing_active_watchlist(
        filtered_alpha, active_ledger, latest_prices_df, archive_path="data/survivors_archive.csv", is_flexgate=False
    )
    
    ledger_df['ENTRY_DATE'] = ledger_df['ENTRY_DATE'].dt.strftime('%Y-%m-%d')
    if 'EXIT_DATE' in ledger_df.columns:
        ledger_df['EXIT_DATE'] = ledger_df['EXIT_DATE'].dt.strftime('%Y-%m-%d')
    
    ledger_df.to_csv(ledger_path, index=False)
    print(f"Ledger updated and saved to {ledger_path}")
    
    if 'DATE_DT' in filtered_alpha.columns:
        filtered_alpha = filtered_alpha.sort_values(by='DATE_DT', ascending=False)
        filtered_alpha = filtered_alpha.drop(columns=['DATE_DT'])
        
    return filtered_alpha, ledger_df


def update_flexgate_ledger(flex_watchlist, latest_prices_df, ledger_path):
    """
    Updates the permanent trade ledger for FlexGate engines.
    Uses CHANDELIER_EXIT for the Stop Loss (Static at Entry Day). No Take Profit.
    """
    if flex_watchlist.empty:
        import pandas as pd
        return flex_watchlist, pd.DataFrame()

    import os
    import pandas as pd
    import numpy as np
    import yfinance as yf
    
    if os.path.exists(ledger_path):
        ledger_df = pd.read_csv(ledger_path)
    else:
        ledger_df = pd.DataFrame(columns=[
            'ENTRY_DATE', 'SYMBOL', 'ENTRY_PRICE', 'ATR14', 'STOP_LOSS', 'TAKE_PROFIT', 
            'ENTRY_AI_PROB', 'ENTRY_WHALE_DENSITY', 'ENTRY_IMPLIED_TRADES',
            'STATUS', 'EXIT_DATE', 'EXIT_PRICE'
        ])
        
    ledger_df['ENTRY_DATE'] = pd.to_datetime(ledger_df['ENTRY_DATE'])
    if 'EXIT_DATE' in ledger_df.columns:
        ledger_df['EXIT_DATE'] = pd.to_datetime(ledger_df['EXIT_DATE'], errors='coerce')
        
    flex_watchlist = flex_watchlist.copy()
    flex_watchlist['DATE_DT'] = pd.to_datetime(flex_watchlist['DATE'])
    
    new_signals = []
    for _, row in flex_watchlist.iterrows():
        sym = row['SYMBOL']
        dt = row['DATE_DT']
        
        eligible, reason = check_signal_eligibility(ledger_df, sym, dt, cooldown_days=14)
        if eligible:
            new_signals.append(row)
        else:
            print(f"[RE-ENTRY GATE] FlexGate candidate {sym} on {dt.strftime('%Y-%m-%d')} skipped: {reason}")
            
    active_symbols = ledger_df[ledger_df['STATUS'] == 'ACTIVE']['SYMBOL'].unique().tolist()
    new_syms = [row['SYMBOL'] for row in new_signals]
    all_needed_symbols = list(set(active_symbols + new_syms))
    
    symbol_to_yf = {}
    if not latest_prices_df.empty and 'EXCHANGE' in latest_prices_df.columns:
        exch_map = latest_prices_df.drop_duplicates('SYMBOL').set_index('SYMBOL')['EXCHANGE'].to_dict()
    else:
        exch_map = {}

    data = None
    yf_symbols = []
    if all_needed_symbols:
        for s in all_needed_symbols:
            exch = exch_map.get(s, 'NSE')
            suffix = ".BO" if exch == "BSE" else ".NS"
            symbol_to_yf[s] = f"{s}{suffix}"
            
        yf_symbols = list(set(symbol_to_yf.values()))
        data = yf.download(yf_symbols, period="6mo", progress=False, group_by="ticker")
        
    if new_signals:
        new_df = pd.DataFrame(new_signals)
        print(f"Adding {len(new_df)} new FlexGate signals to {ledger_path}...")
        new_records = []
        for _, row in new_df.iterrows():
            sym = row['SYMBOL']
            dt = row['DATE_DT']
            try:
                yf_sym = symbol_to_yf.get(sym, f"{sym}.NS")
                if isinstance(data.columns, pd.MultiIndex):
                    if yf_sym in (data.columns.levels[0] if hasattr(data.columns, 'levels') else []):
                        ticker_df = data[yf_sym]
                    elif yf_sym in (data.columns.levels[1] if hasattr(data.columns, 'levels') and len(data.columns.levels) > 1 else []):
                        ticker_df = data.xs(yf_sym, level=1, axis=1)
                    elif hasattr(data.columns, 'levels') and len(data.columns.levels[0]) == 1:
                        ticker_df = data[data.columns.levels[0][0]]
                    else:
                        raise KeyError(yf_sym)
                else:
                    ticker_df = data
                    
                hist_up_to_dt = ticker_df[ticker_df.index.tz_localize(None) <= dt].copy()
                hist_up_to_dt = hist_up_to_dt.dropna(subset=['Close'])
                
                if len(hist_up_to_dt) > 0:
                    entry_price = hist_up_to_dt['Close'].iloc[-1]
                    
                    ch_exit = row.get('CHANDELIER_EXIT', np.nan)
                    atr14 = row.get('ATR14', np.nan)
                    if pd.isna(ch_exit) and pd.notna(atr14):
                         ch_exit = entry_price - (3.0 * atr14)
                    
                    sl = ch_exit
                    tp = np.nan
                        
                    new_records.append({
                        'ENTRY_DATE': dt,
                        'SYMBOL': sym,
                        'ENTRY_PRICE': entry_price,
                        'ATR14': atr14,
                        'STOP_LOSS': sl,
                        'TAKE_PROFIT': tp,
                        'ENTRY_AI_PROB': row.get('AI_WIN_PROBABILITY', np.nan),
                        'ENTRY_WHALE_DENSITY': row.get('Whale_Density', np.nan),
                        'ENTRY_IMPLIED_TRADES': row.get('Implied_Trades', np.nan),
                        'STATUS': 'ACTIVE',
                        'EXIT_DATE': pd.NaT,
                        'EXIT_PRICE': np.nan
                    })
            except Exception as e:
                print(f"Failed to initialize flex ledger for {sym} on {dt}: {e}")
                
        if new_records:
            ledger_df = pd.concat([ledger_df, pd.DataFrame(new_records)], ignore_index=True)
            
    latest_date = pd.to_datetime(latest_prices_df['DATE'].max()) if 'DATE' in latest_prices_df.columns else pd.Timestamp.now().normalize()
    watchlist_keys = set(zip(flex_watchlist['SYMBOL'], flex_watchlist['DATE_DT']))
    
    for idx, row in ledger_df.iterrows():
        if row['STATUS'] == 'ACTIVE':
            sym = row['SYMBOL']
            entry_dt = row['ENTRY_DATE']
            
            if pd.isna(row['STOP_LOSS']):
                ledger_df.at[idx, 'STATUS'] = 'SUSPENDED'
                ledger_df.at[idx, 'EXIT_DATE'] = latest_date
                ledger_df.at[idx, 'EXIT_PRICE'] = row['ENTRY_PRICE']
                continue

            if data is not None:
                yf_sym = symbol_to_yf.get(sym, f"{sym}.NS")
                ticker_df = None
                if isinstance(data.columns, pd.MultiIndex):
                    if yf_sym in (data.columns.levels[0] if hasattr(data.columns, 'levels') else []):
                        ticker_df = data[yf_sym]
                    elif yf_sym in (data.columns.levels[1] if hasattr(data.columns, 'levels') and len(data.columns.levels) > 1 else []):
                        ticker_df = data.xs(yf_sym, level=1, axis=1)
                    elif hasattr(data.columns, 'levels') and len(data.columns.levels[0]) == 1:
                        ticker_df = data[data.columns.levels[0][0]]
                else:
                    ticker_df = data
                    
                if ticker_df is not None:
                    # Path must strictly evaluate days AFTER entry date to avoid Day-0 morning low lookback leakage
                    path_df = ticker_df[ticker_df.index.tz_localize(None) > entry_dt].copy()
                    path_df = path_df.dropna(subset=['Close'])
                    
                    # Dynamic Chandelier Exit Trailing Logic
                    # Start current_stop_loss at the true entry stop loss so replayed ratchets start from day 0 without time-travel paradox
                    initial_sl = row['ENTRY_PRICE'] - (3.0 * row['ATR14']) if (pd.notna(row.get('ATR14')) and row.get('ATR14') > 0) else row['STOP_LOSS']
                    current_stop_loss = initial_sl
                    highest_high = row['ENTRY_PRICE'] # Start highest_high at entry price
                    
                    hit = False
                    for p_date, p_row in path_df.iterrows():
                        # 1. Update Highest High
                        if pd.notna(p_row['High']) and p_row['High'] > highest_high:
                            highest_high = p_row['High']
                            
                        # 2. Calculate New Dynamic Stop Loss (3 ATRs below highest high)
                        if pd.notna(row['ATR14']):
                            new_sl = highest_high - (3.0 * row['ATR14'])
                            # 3. Ratchet Logic: Only move SL up, never down
                            if pd.isna(current_stop_loss) or new_sl > current_stop_loss:
                                current_stop_loss = new_sl
                                
                        # 4. Check for Stop Loss Hit
                        if pd.notna(current_stop_loss) and p_row['Low'] <= current_stop_loss:
                            # In trailing stop engines, an exit in profit above entry is taking profit (HIT_TP)
                            if current_stop_loss > row['ENTRY_PRICE']:
                                ledger_df.at[idx, 'STATUS'] = 'HIT_TP'
                            else:
                                ledger_df.at[idx, 'STATUS'] = 'HIT_SL'
                            ledger_df.at[idx, 'EXIT_DATE'] = p_date.tz_localize(None)
                            ledger_df.at[idx, 'EXIT_PRICE'] = current_stop_loss
                            hit = True
                            break
                            
                    if hit:
                        continue
                        
                    # 5. If trade is still active, save the tightest stop loss back to ledger
                    if not hit and pd.notna(current_stop_loss):
                        ledger_df.at[idx, 'STOP_LOSS'] = current_stop_loss
                        
    active_ledger = ledger_df[ledger_df['STATUS'] == 'ACTIVE'].copy()
    active_keys = set(zip(active_ledger['SYMBOL'], pd.to_datetime(active_ledger['ENTRY_DATE'])))
    
    filtered_flex = flex_watchlist[
        flex_watchlist.apply(lambda r: (r['SYMBOL'], r['DATE_DT']) in active_keys, axis=1)
    ].copy()
    
    cols_to_drop = [c for c in ['STOP_LOSS', 'TAKE_PROFIT', 'ENTRY_PRICE', 'ATR14'] if c in filtered_flex.columns]
    if cols_to_drop:
        filtered_flex = filtered_flex.drop(columns=cols_to_drop)
        
    active_ledger_subset = active_ledger[['SYMBOL', 'ENTRY_DATE', 'ENTRY_PRICE', 'ATR14', 'STOP_LOSS', 'TAKE_PROFIT']]
    active_ledger_subset = active_ledger_subset.rename(columns={'ENTRY_DATE': 'DATE_DT'})
    active_ledger_subset['DATE_DT'] = pd.to_datetime(active_ledger_subset['DATE_DT'])
    
    filtered_flex = pd.merge(filtered_flex, active_ledger_subset, on=['SYMBOL', 'DATE_DT'], how='left')

    # Hydrate any open active positions from ledger missing from filtered_flex
    filtered_flex = _hydrate_missing_active_watchlist(
        filtered_flex, active_ledger, latest_prices_df, archive_path="data/flexgate_archive.csv", is_flexgate=True
    )
    
    ledger_df['ENTRY_DATE'] = ledger_df['ENTRY_DATE'].dt.strftime('%Y-%m-%d')
    if 'EXIT_DATE' in ledger_df.columns:
        ledger_df['EXIT_DATE'] = ledger_df['EXIT_DATE'].dt.strftime('%Y-%m-%d')
    
    ledger_df.to_csv(ledger_path, index=False)
    
    if 'DATE_DT' in filtered_flex.columns:
        filtered_flex = filtered_flex.sort_values(by='DATE_DT', ascending=False)
        filtered_flex = filtered_flex.drop(columns=['DATE_DT'])
        
    return filtered_flex, ledger_df
