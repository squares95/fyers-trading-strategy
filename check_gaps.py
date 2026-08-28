import os

import pandas as pd

data_dir = r"C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data"

symbol = "BANKNIFTY"
fpath = os.path.join(data_dir, symbol, f"{symbol}_1MIN.csv")
df = pd.read_csv(fpath, parse_dates=["Datetime"])
print(f"Checking {symbol} data quality:")
print(f"  Total rows: {len(df)}")
print(f"  Date range: {df['Datetime'].min()} to {df['Datetime'].max()}")
print(f"  Unique dates: {df['Datetime'].dt.date.nunique()}")

# Check minute differences
df["minute_diff"] = df["Datetime"].diff().dt.total_seconds() / 60
gaps = df[df["minute_diff"] > 1]
print(f"  Gaps > 1 minute: {len(gaps)}")
if len(gaps) > 0:
    print(f"    First gap: {gaps.iloc[0]['Datetime']} (+{gaps.iloc[0]['minute_diff']} min)")

# Check trading hours compliance
df["time"] = df["Datetime"].dt.time
outside_hours = df[
    (df["time"] < pd.Timestamp("09:15").time()) | (df["time"] > pd.Timestamp("15:30").time())
]
print(f"  Outside 09:15-15:30: {len(outside_hours)} rows")

# Check volume
zero_vol = (df["Volume"] == 0).sum()
print(f"  Zero volume bars: {zero_vol}")

# Check OHLC logic
ohlc_bad = df[
    (df["High"] < df["Low"])
    | (df["High"] < df["Open"])
    | (df["High"] < df["Close"])
    | (df["Low"] > df["Open"])
    | (df["Low"] > df["Close"])
]
print(f"  OHLC logic violations: {len(ohlc_bad)}")
