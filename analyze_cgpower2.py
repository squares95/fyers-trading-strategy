import pandas as pd

df = pd.read_csv(r'C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data\CGPOWER\CGPOWER_1MIN.csv', parse_dates=['Datetime'])

print("=" * 60)
print("DETAILED CGPOWER DATA QUALITY ANALYSIS")
print("=" * 60)

# 1. Check for intra-day gaps (gaps during trading hours)
df['minute_diff'] = df['Datetime'].diff().dt.total_seconds() / 60
df['date'] = df['Datetime'].dt.date
df['time'] = df['Datetime'].dt.time

# Intra-day gaps: gap > 1 min AND same date
intra_day_gaps = df[(df['minute_diff'] > 1) & (df['date'] == df['Datetime'].shift().dt.date)]
print(f"\n1. INTRA-DAY GAPS (same-day gaps > 1 minute):")
print(f"   Count: {len(intra_day_gaps)}")
if len(intra_day_gaps) > 0:
    print(intra_day_gaps[['Datetime', 'minute_diff', 'Open', 'High', 'Low', 'Close', 'Volume']].head(20).to_string())

# 2. OHLC integrity issues
print(f"\n2. OHLC INTEGRITY ISSUES:")
ohlc_issues = df[(df['High'] < df['Low']) | (df['High'] < df['Open']) | (df['High'] < df['Close']) |
                  (df['Low'] > df['Open']) | (df['Low'] > df['Close']) |
                  (df['Open'] > df['Close'])]
print(f"   Count: {len(ohlc_issues)}")
if len(ohlc_issues) > 0:
    print(ohlc_issues[['Datetime', 'Open', 'High', 'Low', 'Close', 'Volume']].to_string())

# 3. Zero volume bars
print(f"\n3. ZERO VOLUME BARS:")
zero_vol = df[df['Volume'] == 0]
print(f"   Count: {len(zero_vol)}")
if len(zero_vol) > 0:
    # Check if they're clustered at end of day
    zero_vol['time_str'] = zero_vol['Datetime'].dt.strftime('%H:%M')
    time_counts = zero_vol['time_str'].value_counts().sort_index()
    print(f"   Time distribution (top 15):")
    print(time_counts.head(15).to_string())

# 4. Days with wrong bar counts
print(f"\n4. DAYS WITH WRONG BAR COUNTS:")
daily_counts = df.groupby(df['Datetime'].dt.date).size()
wrong_days = daily_counts[daily_counts != 375]
print(f"   Count: {len(wrong_days)}")
print(wrong_days.to_string())

# 5. Check if zero-vol bars are at market close buffer
print(f"\n5. ZERO VOLUME AT END OF DAY (15:25-15:29):")
end_of_day_zero = zero_vol[zero_vol['time_str'].isin(['15:25', '15:26', '15:27', '15:28', '15:29'])]
print(f"   Count: {len(end_of_day_zero)}")

# 6. Check price continuity
print(f"\n6. PRICE CONTINUITY CHECK:")
df['price_change'] = df['Close'].diff()
large_moves = df[df['price_change'].abs() > 50]
print(f"   Price moves > 50 in one minute: {len(large_moves)}")
if len(large_moves) > 0:
    print(large_moves[['Datetime', 'Close', 'price_change']].head(10).to_string())

# 7. Check for NaN/missing values
print(f"\n7. MISSING VALUES:")
for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
    nan_count = df[col].isna().sum()
    print(f"   {col}: {nan_count}")

# 8. Check EMA9/ADX/ATR indicator coverage
print(f"\n8. INDICATOR COVERAGE:")
for col in ['EMA9', 'EMA21', 'ADX', 'ATR']:
    null_count = df[col].isna().sum()
    print(f"   {col}: {null_count} nulls")

# 9. Check if 15:25-15:29 bars are legit
print(f"\n9. BUFFER ZONE (15:25-15:29) ANALYSIS:")
buffer = df[df['time_str'].isin(['15:25', '15:26', '15:27', '15:28', '15:29'])]
print(f"   Total buffer bars: {len(buffer)}")
print(f"   Zero volume in buffer: {(buffer['Volume'] == 0).sum()}")
print(f"   Non-zero volume in buffer: {(buffer['Volume'] > 0).sum()}")
if (buffer['Volume'] > 0).sum() > 0:
    print("   Non-zero buffer bars:")
    print(buffer[buffer['Volume'] > 0][['Datetime', 'Open', 'High', 'Low', 'Close', 'Volume']].head(10).to_string())

print("\n" + "=" * 60)