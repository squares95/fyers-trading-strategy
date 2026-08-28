"""
Experiment 5: Out-of-Sample Validation
Tests if SUPER GOLD works on RECENT data only (2025-2026).
This is the critical test for whether the strategy will work in LIVE trading.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


# Portfolio of winners
PORTFOLIO_STOCKS = ["CGPOWER", "BHEL", "DRREDDY", "INDUSINDBK", "M&M", "HCLTECH", "TITAN"]

# Out-of-sample cutoffs
OOS_CUTOFFS = [
    ("2025-01-01", "OOS: 2025-2026 only"),
    ("2024-01-01", "OOS: 2024-2026 only"),
    ("2023-06-01", "OOS: Last 3 years"),
]


def run_gold_filtered(symbol: str, start_date: str = None) -> pd.DataFrame:
    """Run Gold strategy, optionally filter to recent data only."""
    try:
        from Strategies.G01.backtest import backtest
        from Strategies.G01.features import prepare_features
        from Strategies.G01.Gold import get_super_gold_config
        from Strategies.G01.regime_filter import daily_regime_table
        from Strategies.G01.signals import generate_signals
        from Strategies.G01.strength_scorer import signal_strength_table

        data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
        if not data_path.exists():
            return pd.DataFrame()

        config = get_super_gold_config()
        df = prepare_features(data_path)

        if start_date:
            df = df[df["Datetime"] >= pd.Timestamp(start_date)].copy()

        if len(df) == 0:
            return pd.DataFrame()

        signals = generate_signals(df, config)
        if len(signals) == 0:
            return pd.DataFrame()

        regime = daily_regime_table(df)
        tradeable = set(regime.loc[regime["regime_tradeable"], "date"])
        signals = signals[signals["date"].isin(tradeable)].copy()

        if len(signals) == 0:
            return pd.DataFrame()

        strength = signal_strength_table(df, signals, config)
        signals = signals.merge(
            strength[["date", "direction", "signal_strength", "strength_trigger_component"]],
            on=["date", "direction"],
            how="left",
        )
        signals = signals[
            (signals["signal_strength"] >= 45) & (signals["strength_trigger_component"] >= 0.15)
        ].copy()

        if len(signals) == 0:
            return pd.DataFrame()

        trades = backtest(df, signals, config)
        trades["symbol"] = symbol
        return trades

    except Exception:
        return pd.DataFrame()


def calculate_metrics(trades: pd.DataFrame) -> dict:
    """Calculate metrics for a trade set."""
    if len(trades) == 0:
        return {"error": "No trades"}

    total_return = (trades["net_return"].sum()) * 100
    win_trades = trades[trades["net_return"] > 0]
    loss_trades = trades[trades["net_return"] <= 0]

    gross_profit = win_trades["net_return"].sum() * 100
    gross_loss = abs(loss_trades["net_return"].sum()) * 100
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    win_rate = len(win_trades) / len(trades) * 100

    # Max DD
    sorted_trades = trades.sort_values("entry_time")
    cumulative = (sorted_trades["net_return"].cumsum()) * 100
    peak = cumulative.cummax()
    max_dd = (cumulative - peak).min()

    # Monthly
    monthly = (
        sorted_trades.groupby(pd.to_datetime(sorted_trades["entry_time"]).dt.to_period("M"))[
            "net_return"
        ].sum()
        * 100
    )

    return {
        "trades": len(trades),
        "net_return_pct": round(total_return, 2),
        "profit_factor": round(profit_factor, 3),
        "win_rate_pct": round(win_rate, 1),
        "max_dd_pct": round(max_dd, 2),
        "months": len(monthly),
        "profitable_months": int((monthly > 0).sum()),
        "monthly_avg": round(float(monthly.mean()), 3) if len(monthly) > 0 else 0,
    }


def main():
    print("=" * 60)
    print("EXPERIMENT 5: Out-of-Sample Validation")
    print("=" * 60)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Portfolio: {PORTFOLIO_STOCKS}\n")

    # Test on full period and out-of-sample periods
    results = {}

    # Full period
    print("=" * 60)
    print("FULL PERIOD (in-sample)")
    print("=" * 60)
    all_trades_list = []
    for sym in PORTFOLIO_STOCKS:
        print(f"  {sym}...", end=" ")
        trades = run_gold_filtered(sym)
        if len(trades) == 0:
            print("[-] No trades")
        else:
            net = trades["net_return"].sum() * 100
            print(f"[OK] {len(trades)} trades, Net: {net:+.1f}%")
            all_trades_list.append(trades)

    all_trades = (
        pd.concat(all_trades_list, ignore_index=True) if all_trades_list else pd.DataFrame()
    )
    full_metrics = calculate_metrics(all_trades)
    results["FULL_PERIOD"] = full_metrics

    # Out-of-sample tests
    for cutoff, label in OOS_CUTOFFS:
        print("\n" + "=" * 60)
        print(label)
        print("=" * 60)
        oos_trades_list = []
        for sym in PORTFOLIO_STOCKS:
            print(f"  {sym}...", end=" ")
            trades = run_gold_filtered(sym, start_date=cutoff)
            if len(trades) == 0:
                print("[-] No trades")
            else:
                net = trades["net_return"].sum() * 100
                print(f"[OK] {len(trades)} trades, Net: {net:+.1f}%")
                oos_trades_list.append(trades)

        oos_trades = (
            pd.concat(oos_trades_list, ignore_index=True) if oos_trades_list else pd.DataFrame()
        )
        oos_metrics = calculate_metrics(oos_trades)
        results[label] = oos_metrics

    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"{'Period':<30} {'Trades':>8} {'Net%':>8} {'PF':>6} {'DD%':>8} {'WR%':>6}")
    print("-" * 60)

    for period, m in results.items():
        if "error" in m:
            print(f"{period:<30} {'N/A':>8}")
        else:
            print(
                f"{period:<30} {m['trades']:>8} {m['net_return_pct']:>+8.1f} "
                f"{m['profit_factor']:>6.2f} {m['max_dd_pct']:>8.2f} {m['win_rate_pct']:>6.1f}"
            )

    # Save
    output_dir = Path("Research/GroqAnalysis")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(output_dir / f"exp05_oos_{ts}.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n[Saved] Research/GroqAnalysis/exp05_oos_{ts}.json")

    return results


if __name__ == "__main__":
    main()
