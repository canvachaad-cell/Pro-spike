import pandas as pd
import logging
from config import Config

logger = logging.getLogger("progressive_screener")
class ProgressiveSpiker:
    def __init__(self, df):
        self.df = df
    
    def get_signals(self):
        """Filter stocks passing all 12 conditions"""
        df = self.df.copy()
        
        required = ["SYMBOL", "CLOSE", "DELIV_PER", "DELIVERY_TURNOVER", "ATW"]
        if not all(col in df.columns for col in required):
            return pd.DataFrame()
            
        # Ensure DATE is datetime and filter out old/delisted records
        if "DATE" in df.columns:
            df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
            max_dt = df["DATE"].max()
            if pd.notna(max_dt):
                df = df[df["DATE"] == max_dt]

        
        # Filter out bad data
        df = df[df["CLOSE"] > 0]
        df = df[df["DELIV_PER"] > 0]
        df = df[df["DELIVERY_TURNOVER"] > 0]
        df = df[df["ATW"] > 0]
        
        # Get baseline thresholds from config
        deliv_min = Config.PROGRESSIVE_SPIKE.get("delivery_pct_min", 50)
        turnover_min = Config.PROGRESSIVE_SPIKE.get("delivery_turnover_min", 5000000)
        atw_min = Config.PROGRESSIVE_SPIKE.get("atw_min", 25000)

        # Baseline 3 conditions (STRICT)
        df = df[df["DELIV_PER"] >= deliv_min]
        df = df[df["DELIVERY_TURNOVER"] >= turnover_min]
        df = df[df["ATW"] >= atw_min]
        
        # Progressive 9 conditions (if columns exist)
        if all(col in df.columns for col in ["DELIV_PER_1W", "DELIV_PER_1M", "DELIV_PER_3M"]):
            df = df[(df["DELIV_PER"] > df["DELIV_PER_1W"]) & 
                    (df["DELIV_PER_1W"] > df["DELIV_PER_1M"]) & 
                    (df["DELIV_PER_1M"] > df["DELIV_PER_3M"])]
        
        if all(col in df.columns for col in ["DELIVERY_TURNOVER_1W", "DELIVERY_TURNOVER_1M", "DELIVERY_TURNOVER_3M"]):
            df = df[(df["DELIVERY_TURNOVER"] > df["DELIVERY_TURNOVER_1W"]) & 
                    (df["DELIVERY_TURNOVER_1W"] > df["DELIVERY_TURNOVER_1M"]) & 
                    (df["DELIVERY_TURNOVER_1M"] > df["DELIVERY_TURNOVER_3M"])]
        
        if all(col in df.columns for col in ["ATW_1W", "ATW_1M", "ATW_3M"]):
            df = df[(df["ATW"] > df["ATW_1W"]) & 
                    (df["ATW_1W"] > df["ATW_1M"]) & 
                    (df["ATW_1M"] > df["ATW_3M"])]
        
        return df.reset_index(drop=True)
