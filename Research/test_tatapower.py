"""Test SUPER GOLD on newly downloaded stocks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Strategies.G01 import Gold
from Strategies.G01.Core import prepare_features, generate_signals, backtest


def test_stock(symbol):
    try:
        path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
        if not path.exists():
            return None

        df = prepare_features(path)
        days = df["date"].nunique()
        regime = Gold.daily_regime_table(df)
        tradeable = set(regime.loc[regime["regime_tradeable"], "date"])

        signals = generate_signals(df, Gold.SUPER_GOLD_CONFIG)
        signals = signals[signals["date"].isin(tradeable)].copy()

        if len(signals) < 3:
            return {
                "symbol": symbol,
                "days": days,
                "signals": len(signals),
                "note": "too_few_signals",
            }

        strength = Gold.signal_strength_table(df, signals, Gold.SUPER_GOLD_CONFIG)
        trades = backtest(df, signals, Gold.SUPER_GOLD_CONFIG)
        trades = Gold.attach_signal_strength(trades, strength)

        results = {}
        for min_str in [30, 35, 40, 45, 50]:
            filtered = trades[trades["signal_strength"] >= min_str]
            if len(filtered) >= 3:
                stats = Gold.equity_stats(filtered)
                results[min_str] = stats

        # Find best
        best_thresh = None
        best_stats = None
        for thresh, stats in results.items():
            if stats and stats["net_pct"] > 0:
                if best_stats is None or stats["net_pct"] > best_stats["net_pct"]:
                    best_stats = stats
                    best_thresh = thresh

        return {
            "symbol": symbol,
            "days": days,
            "signals": len(signals),
            "tradeable_days": len(tradeable),
            "best_threshold": best_thresh,
            "best_stats": best_stats,
            "all_results": results,
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def main():
    print("=" * 80)
    print("TESTING SUPER GOLD ON NEW STOCKS")
    print("=" * 80)

    # Test on all stocks we have
    data_path = Path("Data")
    symbols = []
    for folder in data_path.iterdir():
        if folder.is_dir() and (folder / f"{folder.name}_5MIN.csv").exists():
            symbols.append(folder.name)

    print(f"\nFound {len(symbols)} stocks with 5-min data")
    print(f"Stocks: {symbols}\n")

    profitable = []
    for symbol in sorted(symbols):
        result = test_stock(symbol)
        if result is None:
            continue

        if "error" in result:
            print(f"  {symbol:15s} | ERROR: {result['error']}")
        elif "note" in result:
            print(f"  {symbol:15s} | {result.get('signals', 0)} signals - {result['note']}")
        elif result.get("best_stats"):
            stats = result["best_stats"]
            profitable.append({
                "symbol": symbol,
                "days": result["days"],
                "signals": result["signals"],
                "trades": stats["trades"],
                "net_pct": stats["net_pct"],
                "win_rate": stats["win_rate_pct"],
                "pf": stats["profit_factor"],
                "max_dd": stats["max_dd_pct"],
                "threshold": result["best_threshold"],
            })
            print(f"  {symbol:15s} | {result['days']:4d} days | {result['signals']:3d} signals | "
                  f"{stats['trades']:3d} trades | net={stats['net_pct']:6.2f}% | "
                  f"win={stats['win_rate_pct']:5.1f}% | pf={stats['profit_factor']:.2f} | "
                  f"dd={stats['max_dd_pct']:6.2f}% | str>={result['best_threshold']}")

    # Summary
    print("\n" + "=" * 80)
    print("PROFITABLE STOCKS (Sorted by Net Return)")
    print("=" * 80)

    if profitable:
        profitable.sort(key=lambda x: x["net_pct"], reverse=True)
        for p in profitable:
            print(f"  {p['symbol']:15s} | net={p['net_pct']:6.2f}% | pf={p['pf']:.2f} | "
                  f"dd={p['max_dd']:6.2f}% | {p['trades']} trades")

        total = sum(p["net_pct"] for p in profitable)
        print(f"\nTotal net if traded all: {total:.2f}%")
        print(f"Average per stock: {total/len(profitable):.2f}%")
    else:
        print("No profitable stocks found with these parameters")


if __name__ == "__main__":
    main()
