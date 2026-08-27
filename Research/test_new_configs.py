"""Test new Super Gold and Shorts Only configs."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Strategies.G01 import Gold
from Strategies.G01.Core import prepare_features, generate_signals, backtest

print("=" * 80)
print("TESTING NEW CONFIGS")
print("=" * 80)

print("\n=== SUPER GOLD CONFIG ===")
print(Gold.SUPER_GOLD_CONFIG)

print("\n=== SHORTS ONLY CONFIG ===")
print(Gold.SHORTS_ONLY_CONFIG)

# Test on CGPOWER
df = prepare_features('Data/CGPOWER/CGPOWER_5MIN.csv')
regime = Gold.daily_regime_table(df)
tradeable = set(regime.loc[regime['regime_tradeable'], 'date'])

print("\n" + "=" * 80)
print("RESULTS ON CGPOWER")
print("=" * 80)

# Test Super Gold
signals = generate_signals(df, Gold.SUPER_GOLD_CONFIG)
signals = signals[signals['date'].isin(tradeable)].copy()
strength = Gold.signal_strength_table(df, signals, Gold.SUPER_GOLD_CONFIG)
trades = backtest(df, signals, Gold.SUPER_GOLD_CONFIG)
trades_s = Gold.attach_signal_strength(trades, strength)
filtered = trades_s[trades_s['signal_strength'] >= Gold.MIN_SIGNAL_STRENGTH]
sg_stats = Gold.equity_stats(filtered)
print(f"\nSuper Gold: {len(filtered)} trades")
print(f"  Net: {sg_stats['net_pct']:.2f}%")
print(f"  Win: {sg_stats['win_rate_pct']:.1f}%")
print(f"  PF: {sg_stats['profit_factor']:.3f}")
print(f"  Max DD: {sg_stats['max_dd_pct']:.2f}%")

# Test Shorts Only
signals_s = generate_signals(df, Gold.SHORTS_ONLY_CONFIG)
signals_s = signals_s[signals_s['date'].isin(tradeable)].copy()
strength_s = Gold.signal_strength_table(df, signals_s, Gold.SHORTS_ONLY_CONFIG)
trades_s2 = backtest(df, signals_s, Gold.SHORTS_ONLY_CONFIG)
trades_s2 = Gold.attach_signal_strength(trades_s2, strength_s)
filtered_s = trades_s2[trades_s2['signal_strength'] >= Gold.MIN_SIGNAL_STRENGTH]
so_stats = Gold.equity_stats(filtered_s)
print(f"\nShorts Only: {len(filtered_s)} trades")
print(f"  Net: {so_stats['net_pct']:.2f}%")
print(f"  Win: {so_stats['win_rate_pct']:.1f}%")
print(f"  PF: {so_stats['profit_factor']:.3f}")
print(f"  Max DD: {so_stats['max_dd_pct']:.2f}%")

# Test multiple symbols with Super Gold
print("\n" + "=" * 80)
print("SUPER GOLD ON MULTIPLE SYMBOLS")
print("=" * 80)

symbols = ['CGPOWER', 'HDFCBANK', 'SUZLON', 'SBIN', 'RELIANCE', 'INFY', 'TCS', 'BEL', 'LT', 'ICICIBANK']
for symbol in symbols:
    try:
        df = prepare_features(f'Data/{symbol}/{symbol}_5MIN.csv')
        regime = Gold.daily_regime_table(df)
        tradeable = set(regime.loc[regime['regime_tradeable'], 'date'])

        signals = generate_signals(df, Gold.SUPER_GOLD_CONFIG)
        signals = signals[signals['date'].isin(tradeable)].copy()
        if len(signals) == 0:
            print(f"  {symbol:12s} | No signals")
            continue

        strength = Gold.signal_strength_table(df, signals, Gold.SUPER_GOLD_CONFIG)
        trades = backtest(df, signals, Gold.SUPER_GOLD_CONFIG)
        trades = Gold.attach_signal_strength(trades, strength)
        filtered = trades[trades['signal_strength'] >= Gold.MIN_SIGNAL_STRENGTH]

        if len(filtered) == 0:
            print(f"  {symbol:12s} | No trades after filter")
            continue

        stats = Gold.equity_stats(filtered)
        print(f"  {symbol:12s} | {stats['trades']:3d} trades | "
              f"net={stats['net_pct']:6.2f}% | win={stats['win_rate_pct']:5.1f}% | "
              f"pf={stats['profit_factor']:.2f} | dd={stats['max_dd_pct']:6.2f}%")
    except Exception as e:
        print(f"  {symbol:12s} | ERROR: {e}")
