import pandas as pd

# Analyze CGPOWER 1MIN data
df = pd.read_csv(
    r"C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data\CGPOWER\CGPOWER_1MIN.csv",
    parse_dates=["Datetime"],
)

print("=" * 60)
print("CGPOWER 1MIN DATA QUALITY ANALYSIS")
print("=" * 60)

print("\n1. BASIC STATISTICS")
print(f"   Total rows: {len(df)}")
print(f"   Date range: {df['Datetime'].min()} to {df['Datetime'].max()}")
print(f"   Unique dates: {df['Datetime'].dt.date.nunique()}")
print(f"   Avg bars per day: {len(df) // df['Datetime'].dt.date.nunique()}")

print("\n2. FIRST 5 TIMESTAMPS")
print(df.head(5)[["Datetime", "Open", "High", "Low", "Close", "Volume"]].to_string())

print("\n3. LAST 5 TIMESTAMPS")
print(df.tail(5)[["Datetime", "Open", "High", "Low", "Close", "Volume"]].to_string())

print("\n4. CHECKING FOR DUPLICATES")
dup_count = df["Datetime"].duplicated().sum()
print(f"   Duplicate timestamps: {dup_count}")

print("\n5. CHECKING FOR TIMESTAMP GAPS")
df["minute_diff"] = df["Datetime"].diff().dt.total_seconds() / 60
gaps = df[df["minute_diff"] > 1]
print(f"   Gaps > 1 minute: {len(gaps)}")
if len(gaps) > 0:
    print(gaps[["Datetime", "minute_diff"]].head(10).to_string())

print("\n6. TRADING SESSION BOUNDARY CHECKS")
df["time"] = df["Datetime"].dt.time
early = df[df["time"] < pd.Timestamp("09:15").time()]
late = df[df["time"] > pd.Timestamp("15:30").time()]
print(f"   Rows before 09:15: {len(early)}")
print(f"   Rows after 15:30: {len(late)}")

print("\n7. DATA INtegrity CHECKS")
ohlc_issues = df[
    (df["High"] < df["Low"])
    | (df["High"] < df["Open"])
    | (df["High"] < df["Close"])
    | (df["Low"] > df["Open"])
    | (df["Low"] > df["Close"])
]
print(f"   OHLC integrity issues: {len(ohlc_issues)}")

print("\n8. VOLUME CHECKS")
zero_vol = (df["Volume"] == 0).sum()
print(f"   Zero volume bars: {zero_vol}")

# Check if any date has exactly 375 bars
daily_counts = df.groupby(df["Datetime"].dt.date).size()
full_days = (daily_counts == 375).sum()
print("\n9. COMPLETE TRADING DAYS (375 bars):")
print(f"   Days with exactly 375 bars: {full_days}")
print(f"   Days with < 375 bars: {(daily_counts < 375).sum()}")
print(f"   Days with > 375 bars: {(daily_counts > 375).sum()}")

print("\n10. SAMPLE DAILY COUNTS (last 20 days)")
print(daily_counts.tail(20).to_string())

print("\n" + "=" * 60)
