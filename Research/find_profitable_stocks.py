"""
Find Profitable Stocks - Screen all available stocks for SUPER GOLD strategy.

This script:
1. Analyzes volatility, trend, and volume characteristics of all stocks
2. Ranks them by similarity to CGPOWER (our best performer)
3. Tests SUPER GOLD on the most promising candidates
4. Outputs a ranked list of stocks that work with the strategy
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import numpy as np

from Strategies.G01 import Gold
from Strategies.G01.Core import prepare_features, generate_signals, backtest


def analyze_stock_characteristics(symbol: str) -> dict:
    """Analyze a stock's characteristics for strategy suitability."""
    try:
        path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
        if not path.exists():
            return None

        df = prepare_features(path)

        if len(df) < 1000:
            return None

        # Calculate characteristics
        regime = Gold.daily_regime_table(df)
        tradeable_days = regime['regime_tradeable'].sum()
        total_days = len(regime)

        # Volatility metrics (from daily data)
        daily = df.groupby('date').agg({
            'High': 'max',
            'Low': 'min',
            'Open': 'first',
            'Close': 'last',
            'Volume': 'sum'
        })
        daily['range_pct'] = (daily['High'] - daily['Low']) / daily['Open']
        daily['atr_proxy'] = daily['range_pct'] * daily['Close'] / 100
        daily['price_level'] = daily['Close'].iloc[-1] if len(daily) > 0 else 0

        # Trend metrics
        daily['daily_return'] = daily['Close'].pct_change()
        daily['trend_days'] = (daily['daily_return'].abs() > daily['daily_return'].std()).sum()

        # Volume metrics
        avg_volume = daily['Volume'].mean()
        volume_std = daily['Volume'].std()
        avg_turnover = (daily['Close'] * daily['Volume']).mean()

        # ATR metrics
        atr_pct = df['atr14'].mean() / df['Close'].mean() * 100 if 'atr14' in df.columns else 0

        return {
            'symbol': symbol,
            'total_days': total_days,
            'tradeable_days': tradeable_days,
            'tradeable_pct': tradeable_days / total_days * 100 if total_days > 0 else 0,
            'avg_range_pct': daily['range_pct'].mean() * 100,
            'median_range_pct': daily['range_pct'].median() * 100,
            'atr_pct': atr_pct,
            'avg_volume': avg_volume,
            'avg_turnover': avg_turnover,
            'turnover_1b_pct': (daily['Close'] * daily['Volume'] > 1e9).mean() * 100,
            'price_level': daily['price_level'].iloc[-1] if len(daily) > 0 else 0,
            'total_bars': len(df),
        }
    except Exception as e:
        return {'symbol': symbol, 'error': str(e)}


def test_super_gold(symbol: str) -> dict:
    """Test SUPER GOLD config on a stock."""
    try:
        path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
        if not path.exists():
            return None

        df = prepare_features(path)
        regime = Gold.daily_regime_table(df)
        tradeable = set(regime.loc[regime['regime_tradeable'], 'date'])

        # Test with SUPER GOLD config
        from Strategies.G01.Gold import SUPER_GOLD_CONFIG

        signals = generate_signals(df, SUPER_GOLD_CONFIG)
        signals = signals[signals['date'].isin(tradeable)].copy()

        if len(signals) < 5:
            return {'symbol': symbol, 'signals': len(signals), 'note': 'too_few_signals'}

        strength = Gold.signal_strength_table(df, signals, SUPER_GOLD_CONFIG)
        trades = backtest(df, signals, SUPER_GOLD_CONFIG)
        trades = Gold.attach_signal_strength(trades, strength)

        # Try different strength thresholds
        results = {}
        for min_str in [30, 35, 40, 45, 50]:
            filtered = trades[trades['signal_strength'] >= min_str]
            if len(filtered) >= 5:
                stats = Gold.equity_stats(filtered)
                results[min_str] = stats
            else:
                results[min_str] = None

        # Find best threshold
        best_result = None
        best_threshold = None
        for thresh, stats in results.items():
            if stats and stats['net_pct'] > 0 and stats['profit_factor'] > 1.0:
                if best_result is None or stats['net_pct'] > best_result['net_pct']:
                    best_result = stats
                    best_threshold = thresh

        return {
            'symbol': symbol,
            'signals': len(signals),
            'best_threshold': best_threshold,
            'best_stats': best_result,
            'all_results': results,
        }
    except Exception as e:
        return {'symbol': symbol, 'error': str(e)}


def main():
    print("=" * 100)
    print("FIND PROFITABLE STOCKS FOR SUPER GOLD STRATEGY")
    print("=" * 100)

    # Step 1: Analyze all stocks
    print("\n[STEP 1] Analyzing stock characteristics...")
    symbols = [
        'CGPOWER', 'HDFCBANK', 'SUZLON', 'SBIN', 'RELIANCE', 'INFY', 'TCS',
        'BEL', 'LT', 'ICICIBANK', 'NIFTY', 'BANKNIFTY', 'TITAN', 'HCLTECH',
        'BAJFINANCE', 'BHARTIARTL', 'M&M'
    ]

    characteristics = []
    for symbol in symbols:
        result = analyze_stock_characteristics(symbol)
        if result:
            characteristics.append(result)
        print(f"  Analyzed: {symbol}")

    char_df = pd.DataFrame(characteristics)
    char_df = char_df.sort_values('avg_range_pct', ascending=False)

    print("\n" + "=" * 100)
    print("STOCK CHARACTERISTICS (ranked by volatility)")
    print("=" * 100)
    print(char_df[['symbol', 'avg_range_pct', 'median_range_pct', 'atr_pct',
                   'turnover_1b_pct', 'tradeable_pct', 'price_level']].to_string(index=False))

    # Step 2: Test SUPER GOLD on all stocks
    print("\n" + "=" * 100)
    print("[STEP 2] Testing SUPER GOLD on all stocks...")
    print("=" * 100)

    test_results = []
    for symbol in symbols:
        result = test_super_gold(symbol)
        if result and 'best_stats' in result and result['best_stats']:
            test_results.append({
                'symbol': symbol,
                'trades': result['best_stats']['trades'],
                'net_pct': result['best_stats']['net_pct'],
                'win_rate': result['best_stats']['win_rate_pct'],
                'pf': result['best_stats']['profit_factor'],
                'max_dd': result['best_stats']['max_dd_pct'],
                'best_threshold': result['best_threshold'],
                'signals': result['signals'],
            })
        elif result and 'note' not in result:
            test_results.append({
                'symbol': symbol,
                'error': result.get('error', 'unknown'),
            })
        print(f"  Tested: {symbol}")

    test_df = pd.DataFrame(test_results)
    if 'net_pct' in test_df.columns:
        test_df = test_df.sort_values('net_pct', ascending=False)

        print("\n" + "=" * 100)
        print("TEST RESULTS (ranked by net return)")
        print("=" * 100)

        # Successful results
        successful = test_df[test_df['net_pct'] > 0].sort_values('net_pct', ascending=False)
        if len(successful) > 0:
            print("\n✅ PROFITABLE STOCKS:")
            for _, r in successful.iterrows():
                trades_val = int(r['trades']) if pd.notna(r['trades']) else 0
                threshold_val = int(r['best_threshold']) if pd.notna(r['best_threshold']) else 0
                print(f"  {r['symbol']:12s} | {trades_val:3d} trades | "
                      f"net={r['net_pct']:6.2f}% | win={r['win_rate']:5.1f}% | "
                      f"pf={r['pf']:.2f} | dd={r['max_dd']:6.2f}% | "
                      f"str>={threshold_val:.0f}")

        # Failed results
        failed = test_df[test_df['net_pct'] <= 0].sort_values('net_pct', ascending=False)
        if len(failed) > 0:
            print("\n❌ UNPROFITABLE STOCKS:")
            for _, r in failed.iterrows():
                trades_val = int(r['trades']) if pd.notna(r['trades']) else 0
                print(f"  {r['symbol']:12s} | {trades_val:3d} trades | "
                      f"net={r['net_pct']:6.2f}% | pf={r['pf']:.2f}")

        # Save results
        output_path = Path("Research") / "profitable_stocks_results.csv"
        test_df.to_csv(output_path, index=False)
        print(f"\nResults saved to: {output_path}")

        # Step 3: Summary
        print("\n" + "=" * 100)
        print("SUMMARY")
        print("=" * 100)
        profitable = len(successful)
        total = len(test_df[test_df['net_pct'].notna()])
        print(f"Profitable: {profitable} / {total} stocks ({profitable/total*100:.1f}%)")

        if len(successful) > 0:
            best = successful.iloc[0]
            print(f"\n🏆 BEST STOCK: {best['symbol']}")
            print(f"   Net Return: {best['net_pct']:.2f}%")
            print(f"   Profit Factor: {best['pf']:.2f}")
            print(f"   Max Drawdown: {best['max_dd']:.2f}%")
            print(f"   Win Rate: {best['win_rate']:.1f}%")
            print(f"   Trades: {best['trades']}")

    else:
        print("No successful tests")
        print(test_df)


if __name__ == "__main__":
    main()
