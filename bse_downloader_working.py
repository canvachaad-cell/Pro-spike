import requests
import pandas as pd
import zipfile
import io
import os
import glob
from datetime import datetime
from config import Config
import warnings
warnings.filterwarnings('ignore')

from schema_contracts import validate

def ensure_cols(df, col_defaults):
    """Helper to ensure required columns exist in a dataframe."""
    for col, default_val in col_defaults.items():
        if col not in df.columns:
            df[col] = default_val
    return df

def normalize_bse_delivery(df_deliv, out_date=None):
    """Standardize BSE delivery column names"""
    df_deliv.columns = df_deliv.columns.str.strip()
    ren = {
        "SCRIP CODE": "SYMBOL",
        "SECURITY_CODE": "SYMBOL",
        "SCRIP_CODE": "SYMBOL",
        "DELV. PER.": "DELIV_PER",
        "DELIV. PER.": "DELIV_PER",
        "DELIVERY QTY": "DELIV_QTY",
        "DELIV ": "DELIV_QTY",
        " DELIV_QTY": "DELIV_QTY",
        " DELIV_PER": "DELIV_PER",
    }
    df_deliv.rename(columns=ren, inplace=True)
    df_deliv = ensure_cols(df_deliv, {"DELIV_PER": 0, "DELIV_QTY": 0, "SYMBOL": ""})
    df_deliv["DELIV_QTY"] = pd.to_numeric(df_deliv["DELIV_QTY"], errors="coerce").fillna(0)
    df_deliv["DELIV_PER"] = pd.to_numeric(df_deliv["DELIV_PER"], errors="coerce").fillna(0)
    
    if out_date:
        df_deliv["DATE"] = out_date
        return df_deliv[["DATE", "SYMBOL", "DELIV_QTY", "DELIV_PER"]].copy()
    return df_deliv

def merge_bse_bhav_delivery(bhav_all, deliv_all):
    """
    Merge BSE bhavcopy with BSE delivery data.
    bhav_all: normalized BSE bhav (has FinInstrmId, ISIN, SYMBOL, DATE, CLOSE, etc.)
    deliv_all: BSE delivery (has DATE, SYMBOL (numeric code), DELIV_QTY, DELIV_PER)
    """
    if bhav_all.empty:
        return bhav_all
    if deliv_all.empty:
        return ensure_cols(bhav_all, {"DELIV_PER": 0, "DELIV_QTY": 0})

    out = bhav_all.copy()
    deliv_all = deliv_all.copy()

    # Standardize delivery column names
    deliv_all = normalize_bse_delivery(deliv_all)

    # Normalize DATE on both sides
    for df in [out, deliv_all]:
        if "DATE" in df.columns:
            if df["DATE"].dtype in ['int64', 'int32']:
                # Try DDMMYYYY first, fallback to YYYYMMDD
                df["DATE"] = pd.to_datetime(df["DATE"].astype(str), format="%d%m%Y", errors="coerce").fillna(
                    pd.to_datetime(df["DATE"].astype(str), format="%Y%m%d", errors="coerce")
                )
            else:
                df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

    # BSE join: bhav.FinInstrmId = delivery.SYMBOL (numeric code)
    if "FinInstrmId" in out.columns and "SYMBOL" in deliv_all.columns:
        deliv_all = deliv_all.rename(columns={"SYMBOL": "FinInstrmId"})

    # Coerce join key to string
    key = "FinInstrmId"
    if key not in out.columns or key not in deliv_all.columns:
        return ensure_cols(out, {"DELIV_PER": 0, "DELIV_QTY": 0})

    out[key] = out[key].astype(str)
    deliv_all[key] = deliv_all[key].astype(str)

    cols_keep = [c for c in [key, "DATE", "DELIV_PER", "DELIV_QTY"] if c in deliv_all.columns]
    out = out.merge(
        deliv_all[cols_keep],
        on=[key, "DATE"],
        how="left",
        suffixes=("", "_del")
    )

    # Consolidate delivery columns
    if "DELIV_PER_del" in out.columns:
        out["DELIV_PER"] = out["DELIV_PER"].fillna(out["DELIV_PER_del"])
        out.drop(columns=["DELIV_PER_del"], inplace=True)
    if "DELIV_QTY_del" in out.columns:
        out["DELIV_QTY"] = out["DELIV_QTY"].fillna(out["DELIV_QTY_del"])
        out.drop(columns=["DELIV_QTY_del"], inplace=True)

    out = ensure_cols(out, {"DELIV_PER": 0, "DELIV_QTY": 0})
    out["DELIV_PER"] = pd.to_numeric(out["DELIV_PER"], errors="coerce").fillna(0)
    out["DELIV_QTY"] = pd.to_numeric(out["DELIV_QTY"], errors="coerce").fillna(0)

    return out

class BSEDownloaderWorking:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*'
        })
    
    def download_bse_bhav_new_format(self, date):
        date_str = date.strftime('%Y%m%d')
        url = f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{date_str}_F_0000.CSV"
    
        try:
            r = self.session.get(url, timeout=30, verify=False)
            if r.status_code == 200:
                df = pd.read_csv(io.StringIO(r.text))
                return df, True
        except Exception as e:
            # Handle exception or log error
            pass
        return None, False


    
    def download_bse_delivery(self, date):
        """BSE Delivery ZIP: SCBSEALLDDMM.zip"""
        date_str = date.strftime('%Y%m%d')
        y = date.year
        ddmm = date.strftime("%d%m")
        url = f"https://www.bseindia.com/BSEDATA/gross/{y}/SCBSEALL{ddmm}.zip"
        
        try:
            r = self.session.get(url, timeout=20, verify=False)
            if r.status_code == 200:
                zip_path = f"data/temp_bse_del_{ddmm}.zip"
                with open(zip_path, "wb") as f:
                    f.write(r.content)
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall("data/")
                
                txts = glob.glob(f"data/SCBSEALL{ddmm}.TXT")
                if txts:
                    df = pd.read_csv(txts[0], delimiter="|", on_bad_lines="skip")
                    df = normalize_bse_delivery(df, out_date=date_str)
                    
                    # cleanup
                    if os.path.exists(zip_path): os.remove(zip_path)
                    for t in txts:
                        if os.path.exists(t): os.remove(t)
                        
                    # Phase 4 wiring: Validate schema strictly
                    df["DATE"] = df["DATE"].astype("int64") # Ensure type is int64 per schema
                    df = validate("bse_delivery", df)
                        
                    return df, True
        except Exception as e:
            print(f"BSE Delivery download failed for {date.strftime('%Y-%m-%d')}: {e}")
        return None, False
    
    def download_bse_bhav(self, date=None):
        """Download BSE Bhav Copy using working formats"""
        if date is None:
            date = datetime.now()
        
        print(f"\n📅 {date.strftime('%d %b %Y')}")
        
        # Try new format
        print(f"  Trying BSE Bhav (new format)...", end=" ")
        df_bhav, ok_bhav = self.download_bse_bhav_new_format(date)
        
        if ok_bhav and df_bhav is not None and len(df_bhav) > 0:
            print(f"✅ ({len(df_bhav)} records)")
            
            # Save bhav
            out_dir = Config.BSE_RAW_DIR
            os.makedirs(out_dir, exist_ok=True)
            out_file = os.path.join(out_dir, f"bse_bhav_{date.strftime('%Y%m%d')}.csv")
            df_bhav.to_csv(out_file, index=False)
            
            return df_bhav, True, {
                "rows": len(df_bhav), 
                "date": date.strftime('%Y-%m-%d'),
                "columns": list(df_bhav.columns)[:5]
            }
        else:
            print("❌")
            return None, False, "BSE bhav not available"

# Test it
if __name__ == "__main__":
    from datetime import timedelta
    
    downloader = BSEDownloaderWorking()
    
    print("=" * 70)
    print("BSE DOWNLOADER - Using Working URL Formats")
    print("=" * 70)
    
    # Try last 10 days
    for days_back in range(1, 11):
        test_date = datetime.now() - timedelta(days=days_back)
        if test_date.weekday() >= 5:
            continue
        
        df, success, meta = downloader.download_bse_bhav(test_date)
        
        if success:
            print(f"\n🎉 SUCCESS!")
            print(f"   Records: {meta['rows']}")
            print(f"   Sample columns: {meta['columns']}")
            break
    else:
        print("\n❌ Could not download BSE data from any recent date")
