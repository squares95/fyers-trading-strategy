import pandas as pd
import os

def check_symbol_quality(symbol):
    data_dir = r'C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data'
    fpath = os.path.join(data_dir, symbol, f'{symbol}_1MIN.csv')
    if not os.path.exists(fpath):
        return None
    df = pd.read_csv(fpath, parse_dates=['Datetime'])
    print(f"\n=== {symbol} ===")
    print(f"Rows: {len(df):,}")
    print(f"Date range: {df['Datetime'].min()} to {df['Datetime'].max()}")
    print(f"Unique dates: {df['Datetime'].dt.date.nunique()}")

    # Basic stats
    df['date'] = df['Datetime'].dt.date
    df['time'] = df['Datetime'].dt.time
    daily_counts = df.groupby('date').size()
    print(f"Avg bars/day: {daily_counts.mean():.1f} (std {daily_counts.std():.1f})")
    print(f"Days with exactly 375 bars: {(daily_counts == 375).sum()}")
    print(f"Days with <375 bars: {(daily_counts < 375).sum()}")
    print(f"Days with >375 bars: {(daily_counts > 375).sum()}")

    # Duplicates
    dup = df['Datetime'].duplicated().sum()
    print(f"Duplicate timestamps: {dup}")

    # Gaps >1 minute (intra-day and inter-day)
    df['minute_diff'] = df['Datetime'].diff().dt.total_seconds() / 60
    gaps = df[df['minute_diff'] > 1]
    print(f"Gaps >1 minute: {len(gaps)}")
    if len(gaps) > 0:
        # Show first few gaps with context
        for idx in gaps.index[:5]:
            prev = df.loc[idx-1, 'Datetime'] if idx>0 else None
            curr = df.loc[idx, 'Datetime']
            print(f"  Gap: {prev} -> {curr} (+{df.loc[idx, 'minute_diff']:.1f} min)")

    # Trading session boundaries
    market_open = pd.Timestamp('09:15:00').time()
    market_close = pd.Timestamp('15:25:00').time()
    # Allow buffer until 15:29 for last candle
    outside_regular = df[(df['time'] < market_open) | (df['time'] > pd.Timestamp('15:29:00').time())]
    print(f"Outside 09:15-15:29: {len(outside_regular)} rows")
    if len(outside_regular) > 0:
        # Show distribution of outside times
        outside_times = outside_regular['time'].value_counts().head(10)
        print("  Top outside times:")
        for t, cnt in outside_times.items():
            print(f"    {t}: {cnt}")

    # OHLC validity: High >= Low, High >= Open, High >= Close, Low <= Open, Low <= Close
    ohlc_ok = (df['High'] >= df['Low']) & (df['High'] >= df['Open']) & (df['High'] >= df['Close']) & \
              (df['Low'] <= df['Open']) & (df['Low'] <= df['Close'])
    ohlc_bad = (~ohlc_ok).sum()
    print(f"OHLC violations: {ohlc_bad}")
    if ohlc_bad > 0:
        bad = df[~ohlc_ok]
        print("  Sample violations:")
        print(bad[['Datetime','Open','High','Low','Close']].head())

    # Volume zero
    zero_vol = (df['Volume'] == 0).sum()
    print(f"Zero volume bars: {zero_vol}")
    if zero_vol > 0:
        # Check if they are mostly at end of day (buffer)
        zero_times = df[df['Volume']==0]['time'].value_counts().head(10)
        print("  Zero volume times (top):")
        for t, cnt in zero_times.items():
            print(f"    {t}: {cnt}")

    # Indicator columns presence (EMA9, EMA21, ADX, ATR) - check nulls
    ind_cols = ['EMA9','EMA21','ADX','ATR']
    for col in ind_cols:
        if col in df.columns:
            nulls = df[col].isna().sum()
            print(f"{col} nulls: {nulls}")
        else:
            print(f"{col} column missing")

    return {
        'symbol': symbol,
        'rows': len(df),
        'date_range': (df['Datetime'].min(), df['Datetime'].max()),
        'dup': dup,
        'gaps_gt1': len(gaps),
        'outside_regular': len(outside_regular),
        'ohlc_bad': ohlc_bad,
        'zero_vol': zero_vol,
        'daily_counts_stats': (daily_counts.mean(), daily_counts.std(), (daily_counts==375).sum())
    }

# Check key symbols
symbols = ['CGPOWER', 'HDFCBANK', 'BANKNIFTY', 'NIFTY', 'RELIANCE', 'TCS', 'INFY', 'LT', 'SBIN']
results = {}
for sym in symbols:
    res = check_symbol_quality(sym)
    if res:
        results[sym] = res

print("\n\n=== SUMMARY ===")
for sym, r in results.items():
    print(f"{sym:10} | rows:{r['rows']:8,} | dup:{r['dup']:4} | gaps>1:{r['gaps_gt1']:4} | ohlc_bad:{r['ohlc_bad']:6} | zero_vol:{r['zero_vol']:6} | outside:{r['outside_regular']:4}")