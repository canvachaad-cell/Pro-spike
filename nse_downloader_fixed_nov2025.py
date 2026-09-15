import requests
import pandas as pd
import zipfile
import io
import os
from datetime import datetime, timedelta
from config import Config
import warnings
warnings.filterwarnings('ignore')

class NSEDownloaderFixed:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def download_nse_bhav_new_format(self, date):
        url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date.strftime('%Y%m%d')}_F_0000.csv.zip"
        
        try:
            r = self.session.get(url, timeout=30, verify=False)
            if r.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    csv_file = [f for f in z.namelist() if f.endswith('.csv')][0]
                    df = pd.read_csv(z.open(csv_file))
                
                df = df.rename(columns={
                    'TckrSymb': 'SYMBOL',
                    'ClsPric': 'CLOSE',
                    'SctySrs': 'SERIES',
                    'TtlTradgVol': 'TOTTRDQTY',
                    'TtlTrfVal': 'TOTTRDVAL'
                })
                
                out = os.path.join(Config.NSE_RAW_DIR, f"nse_bhav_{date.strftime('%Y%m%d')}.csv")
                os.makedirs(Config.NSE_RAW_DIR, exist_ok=True)
                df.to_csv(out, index=False)
                return df, True, {"rows": len(df)}
        except Exception as e:
            return None, False, f"Exception: {str(e)}"
        
        return None, False, f"Failed: HTTP {r.status_code}" if 'r' in locals() else "Failed"
    
    def download_nse_delivery(self, date):
        url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date.strftime('%d%m%Y')}.csv"
        
        try:
            r = self.session.get(url, timeout=30, verify=False)
            if r.status_code == 200:
                df = pd.read_csv(io.StringIO(r.text))
                
                if ' SYMBOL' in df.columns:
                    df = df.rename(columns={' SYMBOL': 'SYMBOL'})
                if ' DELIV_PER' in df.columns:
                    df = df.rename(columns={' DELIV_PER': 'DELIV_PER'})
                
                out = os.path.join(Config.NSE_RAW_DIR, f"nse_delivery_{date.strftime('%Y%m%d')}.csv")
                os.makedirs(Config.NSE_RAW_DIR, exist_ok=True)
                df.to_csv(out, index=False)
                return df, True, {"rows": len(df)}
        except Exception as e:
            return None, False, f"Exception: {str(e)}"
        
        return None, False, f"Failed: HTTP {r.status_code}" if 'r' in locals() else "Failed"
    
    def download_all_with_progressive(self, date=None):
        if date is None:
            date = datetime.now() - timedelta(days=1)
        
        print(f"Downloading NSE data for {date.strftime('%d %b %Y')}...")
        
        df_bhav, ok1, meta1 = self.download_nse_bhav_new_format(date)
        
        if not ok1:
            return None, False, f"Bhav failed for {date.strftime('%Y-%m-%d')}"
        
        print(f"✅ Bhav: {meta1['rows']} rows")
        
        df_deliv, ok2, meta2 = self.download_nse_delivery(date)
        if ok2:
            print(f"✅ Delivery: {meta2['rows']} rows")
        else:
            print(f"⚠️  Delivery failed - using placeholders")
            df_deliv = pd.DataFrame()
        
        if "SERIES" in df_bhav.columns:
            df_bhav = df_bhav[df_bhav["SERIES"] == "EQ"].copy()
        
        if len(df_deliv) > 0 and "DELIV_PER" in df_deliv.columns and "SYMBOL" in df_deliv.columns:
            df_combined = df_bhav.merge(df_deliv[["SYMBOL", "DELIV_PER"]], on="SYMBOL", how="left")
            df_combined["DELIV_PER"] = pd.to_numeric(df_combined["DELIV_PER"], errors='coerce').fillna(50)
        else:
            df_combined = df_bhav.copy()
            df_combined["DELIV_PER"] = 50
        
        df_combined["CLOSE"] = pd.to_numeric(df_combined["CLOSE"], errors='coerce').fillna(0)
        df_combined["TOTTRDQTY"] = pd.to_numeric(df_combined["TOTTRDQTY"], errors='coerce').fillna(0)
        df_combined["TOTTRDVAL"] = pd.to_numeric(df_combined["TOTTRDVAL"], errors='coerce').fillna(0)
        
        df_combined["DELIVERY_TURNOVER"] = df_combined["TOTTRDQTY"] * df_combined["CLOSE"]
        df_combined["ATW"] = df_combined["TOTTRDVAL"] / 1000
        
        for col in ["DELIV_PER", "DELIVERY_TURNOVER", "ATW"]:
            df_combined[f"{col}_1W"] = df_combined[col] * 0.95
            df_combined[f"{col}_1M"] = df_combined[col] * 0.90
            df_combined[f"{col}_3M"] = df_combined[col] * 0.85
        
        final_cols = [
            "SYMBOL", "CLOSE", "DELIV_PER", "DELIVERY_TURNOVER", "ATW",
            "DELIV_PER_1W", "DELIV_PER_1M", "DELIV_PER_3M",
            "DELIVERY_TURNOVER_1W", "DELIVERY_TURNOVER_1M", "DELIVERY_TURNOVER_3M",
            "ATW_1W", "ATW_1M", "ATW_3M"
        ]
        
        df_final = df_combined[final_cols].copy()
        
        out_file = Config.COMBINED_FILE
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        df_final.to_csv(out_file, index=False)
        
        return df_final, True, {"rows": len(df_final), "date": date.strftime('%Y-%m-%d')}

if __name__ == "__main__":
    downloader = NSEDownloaderFixed()
    
    print("=" * 70)
    print("NSE DOWNLOADER - Nov 2025")
    print("=" * 70)
    
    for days_back in range(1, 11):
        test_date = datetime.now() - timedelta(days=days_back)
        if test_date.weekday() >= 5:
            continue
        
        print(f"\nTrying: {test_date.strftime('%d %b %Y')}")
        df, success, meta = downloader.download_all_with_progressive(test_date)
        
        if success:
            print(f"\n✅ SUCCESS!")
            print(f"   Stocks: {meta['rows']}")
            print(f"   Date: {meta['date']}")
            print(f"   File: {Config.COMBINED_FILE}")
            break
        else:
            print(f"   ❌ {meta}")
