import pandas as pd

df = pd.read_csv(
    r"C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data\CGPOWER\CGPOWER_1MIN.csv",
    parse_dates=["Datetime"],
)

print("=" * 60)
print("ANOMALY DEEP DIVE")
print("=" * 60)

# 1. Last bar anomalies
df["date"] = df["Datetime"].dt.date
df["time_str"] = df["Datetime"].dt.strftime("%H:%M:%S")
last_bars = df.groupby("date").tail(1)
abnormal = last_bars[~last_bars["time_str"].isin(["15:29:00", "15:30:00"])]
print("\n1. ABNORMAL LAST BARS (not 15:29 or 15:30):")
print(abnormal[["Datetime", "Open", "High", "Low", "Close", "Volume"]].to_string())

# 2. Investigate 2024-06-04 (4 big moves)
print("\n2. 2024-06-04 DETAIL (4 big moves):")
day = df[df["date"] == pd.Timestamp("2024-06-04").date()]
print(day[["Datetime", "Open", "High", "Low", "Close", "Volume"]].head(30).to_string())

# 3. Check 15:30+ bars (after-hours)
after_hours = df[df["Datetime"].dt.time > pd.Timestamp("15:30:00").time()]
print("\n3. AFTER-HOURS BARS (> 15:30):")
print(f"   Count: {len(after_hours)}")
print(after_hours[["Datetime", "Open", "High", "Low", "Close", "Volume"]].head(20).to_string())

# 4. Investigate 2024-01-18 OHLC violation
print("\n4. 2024-01-18 OPENING (OHLC violation):")
day = df[df["date"] == pd.Timestamp("2024-01-18").date()]
print(day.head(10)[["Datetime", "Open", "High", "Low", "Close", "Volume"]].to_string())

# 5. Check for 91-min gaps
df["minute_diff"] = df["Datetime"].diff().dt.total_seconds() / 60
big_gaps = df[df["minute_diff"] >= 10]
print("\n5. BIG INTRA-DAY GAPS (>= 10 minutes):")
print(big_gaps[["Datetime", "minute_diff"]].to_string())

# 6. Check if 15:29 is the last bar consistently
print("\n6. LAST BAR ANALYSIS:")
print(f"   Days ending at 15:29: {(last_bars['time_str'] == '15:29:00').sum()}")
print(f"   Days ending at 15:30: {(last_bars['time_str'] == '15:30:00').sum()}")
print(
    f"   Other times: {len(last_bars) - (last_bars['time_str'] == '15:29:00').sum() - (last_bars['time_str'] == '15:30:00').sum()}"
)

# 7. The 15:25 to 15:29 buffer zone: are these zero-volume or have legitimate activity?
buffer = df[df["time_str"].between("15:25:00", "15:29:00", inclusive="both")]
print("\n7. BUFFER ZONE (15:25-15:29) VOLUME:")
print(f"   Mean: {buffer['Volume'].mean():.0f}")
print(f"   Zero count: {(buffer['Volume'] == 0).sum()}")
print(f"   Non-zero count: {(buffer['Volume'] > 0).sum()}")
print(f"   Median: {buffer['Volume'].median():.0f}")

# 8. Check if there's a regular 5-min market close
print("\n8. VOLUME PROFILE BY MINUTE (last 10 min of day):")
last_10 = df[df["time_str"].between("15:20:00", "15:29:00", inclusive="both")]
profile = last_10.groupby("time_str")["Volume"].agg(["mean", "median", "count"])
print(profile.to_string())

# 9. Check what dates have zero volume at start (09:15)
print("\n9. ZERO VOLUME AT MARKET OPEN (09:15):")
open_zero = df[(df["time_str"] == "09:15:00") & (df["Volume"] == 0)]
print(f"   Count: {len(open_zero)}")

# 10. Pre-market detection
print("\n10. PRE-MARKET BARS (< 09:15):")
pre_market = df[df["Datetime"].dt.time < pd.Timestamp("09:15:00").time()]
print(f"   Count: {len(pre_market)}")
if len(pre_market) > 0:
    print(pre_market[["Datetime", "Open", "High", "Low", "Close", "Volume"]].to_string())

# 11. Validate the "after-hours" data
print("\n11. ALL TIMES OBSERVED (last 5 of day samples):")
sample_dates = df["date"].drop_duplicates().sample(5, random_state=42)
for d in sample_dates:
    day_data = df[df["date"] == d]
    if len(day_data) > 0:
        print(f"\n   {d}:")
        print(day_data.tail(5)[["Datetime", "Open", "High", "Low", "Close", "Volume"]].to_string())

# 12. Check volume=0 days
print("\n12. ZERO VOLUME PER DAY (entire day):")
daily_vol_sum = df.groupby("date")["Volume"].sum()
zero_days = daily_vol_sum[daily_vol_sum == 0]
print(f"   Days with 0 total volume: {len(zero_days)}")

# 13. Verify timezone (no timezone column, but is it naive IST?)
print("\n13. TIMEZONE CHECK:")
print(f"   Datetime dtype: {df['Datetime'].dtype}")
print(f"   First 3 raw values: {df['Datetime'].head(3).tolist()}")

print("\n" + "=" * 60)
