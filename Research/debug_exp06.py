"""Debug Exp 6 - find out why 0 trades and 0 dates."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Test 1: can we load daily data?
print("=== Test 1: load_daily_ohlc ===")
from exp06_news_filter import load_daily_ohlc, PORTFOLIO_STOCKS, INDEX_SYMBOL

for sym in PORTFOLIO_STOCKS + [INDEX_SYMBOL]:
    df = load_daily_ohlc(sym)
    if df.empty:
        print(f"  {sym}: EMPTY")
    else:
        print(f"  {sym}: {len(df)} rows, cols={list(df.columns)}")
        print(f"    first: {df.iloc[0].to_dict()}")
        break  # just one example

# Test 2: strategy import
print("\n=== Test 2: strategy imports ===")
try:
    from Strategies.G01.features import prepare_features
    from Strategies.G01.signals import generate_signals
    from Strategies.G01.backtest import backtest
    from Strategies.G01.regime_filter import daily_regime_table
    from Strategies.G01.strength_scorer import signal_strength_table
    from Strategies.G01.Gold import get_super_gold_config
    print("  All imports OK")
except Exception as e:
    print(f"  IMPORT FAIL: {type(e).__name__}: {e}")

# Test 3: run on CGPOWER with full traceback
print("\n=== Test 3: CGPOWER full run ===")
try:
    config = get_super_gold_config()
    print(f"  Config: {config}")
    data_path = Path(f"Data/CGPOWER/CGPOWER_5MIN.csv")
    print(f"  Data path: {data_path}, exists={data_path.exists()}")
    df = prepare_features(data_path)
    print(f"  Features: {len(df)} rows, {df.columns.tolist()[:5]}...")
    signals = generate_signals(df, config)
    print(f"  Signals: {len(signals)}")
    if len(signals) > 0:
        print(f"    sample: {signals.iloc[0].to_dict()}")
except Exception as e:
    import traceback
    traceback.print_exc()
