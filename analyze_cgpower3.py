import pandas as pd

df = pd.read_csv(r'C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data\CGPOWER\CGPOWER_1MIN.csv', parse_dates=['Datetime'])

print("=" * 60)
print("REVISED CGPOWER DATA QUALITY ANALYSIS (FIXED LOGIC)")
print("=" * 60)

# 1. CORRECT OHLC integrity: only flag genuine violations
# High should be >= max(Open, Close, Low), Low should be <= min(Open, Close, High)
df['max_ocl'] = df[['Open', 'Close', 'Low']].max(axis=1)
df['min_och'] = df[['Open', 'Close', 'High']].min(axis=1)
ohlc_real_issues = df[(df['High'] < df['max_ocl']) | (df['Low'] > df['min_och'])]
print(f"\n1. REAL OHLC INTEGRITY ISSUES (High<max(O,C,L) or Low>min(O,C,H)):")
print(f"   Count: {len(ohlc_real_issues)}")
if len(ohlc_real_issues) > 0:
    print(ohlc_real_issues[['Datetime', 'Open', 'High', 'Low', 'Close', 'Volume']].head(20).to_string())

# 2. Intra-day gaps (genuinely missing minutes)
df['minute_diff'] = df['Datetime'].diff().dt.total_seconds() / 60
df['date'] = df['Datetime'].dt.date
intra_gaps = df[(df['minute_diff'] > 1) & (df['date'] == df['Datetime'].shift().dt.date)]
print(f"\n2. INTRA-DAY GAPS:")
print(f"   Count: {len(intra_gaps)}")
print(f"   Most common gap sizes:")
print(intra_gaps['minute_diff'].value_counts().head().to_string())

# 3. Zero volume bars by time of day
df['time_str'] = df['Datetime'].dt.strftime('%H:%M')
zero_vol = df[df['Volume'] == 0]
print(f"\n3. ZERO VOLUME BARS:")
print(f"   Count: {len(zero_vol)}")
# Check the timing pattern
time_dist = zero_vol['time_str'].value_counts().sort_index()
print(f"   Time distribution:")
print(time_dist.to_string())

# 4. Days with wrong bar counts
daily_counts = df.groupby(df['Datetime'].dt.date).size()
print(f"\n4. DAYS WITH WRONG BAR COUNTS:")
print(f"   Total unique days: {len(daily_counts)}")
print(f"   Days with 375 bars: {(daily_counts == 375).sum()}")
print(f"   Days with < 375 bars: {(daily_counts < 375).sum()}")
print(f"   Days with > 375 bars: {(daily_counts > 375).sum()}")
print(f"   Distribution:")
print(daily_counts.value_counts().sort_index().to_string())

# 5. Buffer zone (15:25-15:29) - check if market closes at 15:30 but data goes to 15:29
buffer = df[df['time_str'].isin(['15:25', '15:26', '15:27', '15:28', '15:29'])]
print(f"\n5. BUFFER ZONE (15:25-15:29):")
print(f"   Total bars: {len(buffer)}")
print(f"   Per day avg: {len(buffer) / len(daily_counts):.2f}")
print(f"   Zero volume: {(buffer['Volume'] == 0).sum()}")
print(f"   With non-zero volume: {(buffer['Volume'] > 0).sum()}")

# 6. Check for missing values
print(f"\n6. NULL VALUES:")
for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'EMA9', 'EMA21', 'ADX', 'ATR']:
    print(f"   {col}: {df[col].isna().sum()}")

# 7. Big price moves (potential data errors)
df['price_change'] = df['Close'].diff()
big_moves = df[df['price_change'].abs() > 20]  # CGPOWER ~600, 20=3% move is large
print(f"\n7. BIG PRICE MOVES (>20 rupees in 1 min):")
print(f"   Count: {len(big_moves)}")
if len(big_moves) > 0:
    print(big_moves[['Datetime', 'Close', 'price_change']].head(10).to_string())

# 8. Date range coverage by year
df['year'] = df['Datetime'].dt.year
yearly = df.groupby('year').agg({'Datetime': ['count', 'min', 'max'], 'date': 'nunique'})
yearly.columns = ['total_bars', 'first', 'last', 'unique_days']
print(f"\n8. YEARLY COVERAGE:")
print(yearly.to_string())

# 9. Check market hours consistency
# Indian market: 09:15 to 15:30 (with last bar at 15:29 or 15:30)
print(f"\n9. MARKET HOURS ANALYSIS:")
first_bar_time = df['Datetime'].dt.time.min()
last_bar_time = df['Datetime'].dt.time.max()
print(f"   First bar time: {first_bar_time}")
print(f"   Last bar time: {last_bar_time}")

# 10. Volume statistics
print(f"\n10. VOLUME STATISTICS:")
print(f"   Mean: {df['Volume'].mean():.0f}")
print(f"   Median: {df['Volume'].median():.0f}")
print(f"   Min: {df['Volume'].min()}")
print(f"   Max: {df['Volume'].max()}")
print(f"   Std: {df['Volume'].std():.0f}")

# 11. Check for zero/very-low volume sessions (illiquid days)
daily_vol = df.groupby(df['Datetime'].dt.date)['Volume'].sum()
low_vol_days = daily_vol[daily_vol < 10000]
print(f"\n11. LOW VOLUME DAYS (total volume < 10,000):")
print(f"   Count: {len(low_vol_days)}")
if len(low_vol_days) > 0:
    print(f"   Examples: {list(low_vol_days.head(5).index)}")

# 12. Final: check 15:25 to 15:29 is correct buffer (5 extra minutes after 15:25 close)
# Indian market closes 15:30, last regular candle should be 15:29
print(f"\n12. LAST BAR OF DAY VERIFICATION:")
last_bars = df.groupby(df['Datetime'].dt.date).tail(1)
print(f"   Last bar times distribution:")
print(last_bars['time_str'].value_counts().sort_index().to_string())

print("\n" + "=" * 60)