import sys
sys.path.insert(0, "/opt/markethq")
import pandas as pd
import yfinance as yf

# Test data availability for different symbols/timeframes
symbols = ["THYAO.IS", "XU100.IS", "GARAN.IS", "AKBNK.IS", "SAHOL.IS", "BIST01.IS", "DOAS.IS"]
timeframes = ["15m", "1h", "4h"]

for sym in symbols:
    for tf in timeframes:
        try:
            ticker = yf.Ticker(sym)
            if tf == "15m":
                df = ticker.history(period="60d", interval="15m")
            elif tf == "1h":
                df = ticker.history(period="60d", interval="60m")
            elif tf == "4h":
                df = ticker.history(period="60d", interval="240m")
            else:
                df = pd.DataFrame()
            
            if df.empty:
                print(f"{sym} {tf}: EMPTY")
            else:
                # Check for NaN
                nulls = df[["Open", "High", "Low", "Close", "Volume"]].isnull().sum().sum()
                print(f"{sym} {tf}: {len(df)} bars, nulls={nulls}, range={df.index.min()} → {df.index.max()}")
        except Exception as e:
            print(f"{sym} {tf}: ERROR - {e}")