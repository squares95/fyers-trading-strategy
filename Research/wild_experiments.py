"""
Wild Strategy Experiments - Find the most profitable config.

This script tries MANY different parameter combinations to find what's
actually profitable. We test on CGPOWER (our best-performing stock)
but the goal is to find configs that work across multiple symbols.

Experiments:
1. Different EMA combinations
2. Different time windows
3. Different stop/target ratios
4. Different RSI ranges
5. Different ADX thresholds
6. Different volume requirements
7. Multi-timeframe strategies
8. Volatility-adaptive parameters
"""

from pathlib import Path
import itertools
import json
import time
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
from Strategies.G01 import Core, Gold
from Strategies.G01.Core import (
    prepare_features, generate_signals, backtest, StrategyConfig
)


def run_experiment(
    df: pd.DataFrame,
    config: StrategyConfig,
    name: str,
) -> dict:
    """Run a single backtest experiment and return metrics."""
    try:
        signals = generate_signals(df, config)
        if len(signals) == 0:
            return {"name": name, "trades": 0, "net_pct": 0, "skip": "no_signals"}

        trades = backtest(df, signals, config)
        if len(trades) == 0:
            return {"name": name, "trades": 0, "net_pct": 0, "skip": "no_trades"}

        stats = Gold.equity_stats(trades)
        stats["name"] = name
        stats["win_rate_pct"] = stats.pop("win_rate_pct")
        return stats
    except Exception as e:
        return {"name": name, "error": str(e)}


def experiment_ema_combinations(df: pd.DataFrame) -> list:
    """Try different EMA combinations."""
    results = []

    # Baseline (Gold config)
    results.append(run_experiment(df, Gold.GOLD_CONFIG, "baseline_gold"))

    # Different EMA pairs
    ema_pairs = [
        (5, 13),      # Very fast
        (8, 21),      # Fast
        (13, 34),     # Medium
        (21, 55),     # Slow
        (34, 89),     # Very slow
        (5, 20),      # Classic
        (10, 30),     # Alternative
    ]

    for fast, slow in ema_pairs:
        # Note: We're testing the concept, the actual EMA values are hardcoded in prepare_features
        # So this is more of a conceptual test
        name = f"ema_concept_{fast}_{slow}"
        results.append({"name": name, "note": "EMA values hardcoded in features.py"})

    return results


def experiment_stop_target_ratios(df: pd.DataFrame) -> list:
    """Try different stop and target combinations."""
    results = []

    stop_targets = [
        (1.0, 1.5),   # Tight
        (1.0, 2.0),   # Standard
        (1.3, 2.0),   # Gold default
        (1.5, 2.5),   # Wide
        (1.5, 3.0),   # Wide aggressive
        (2.0, 3.0),   # Very wide
        (0.8, 1.5),   # Very tight
        (1.0, 3.0),   # 1:3 ratio
        (1.5, 4.5),   # 1:3 wide
    ]

    for stop, target in stop_targets:
        config = StrategyConfig(
            stop_atr_multiple=stop,
            target_r=target,
            cost_bps_per_side=5.0,
            adx_min=26.0,
            volume_ratio_min=1.2,
        )
        result = run_experiment(
            df, config, f"stop_{stop}_target_{target}"
        )
        results.append(result)

    return results


def experiment_rsi_ranges(df: pd.DataFrame) -> list:
    """Try different RSI filter ranges."""
    results = []

    rsi_ranges = [
        (40, 80),   # Wider
        (50, 75),   # Default
        (45, 70),   # Tighter long
        (55, 80),   # Higher min
        (40, 70),   # Lower max
        (30, 70),   # Very wide
        (50, 65),   # Tighter
    ]

    for low, high in rsi_ranges:
        config = StrategyConfig(
            long_rsi_min=low,
            long_rsi_max=high,
            short_rsi_min=100 - high,  # Mirror
            short_rsi_max=100 - low,
            cost_bps_per_side=5.0,
            adx_min=26.0,
            volume_ratio_min=1.2,
        )
        result = run_experiment(
            df, config, f"rsi_{low}_{high}"
        )
        results.append(result)

    return results


def experiment_adx_thresholds(df: pd.DataFrame) -> list:
    """Try different ADX thresholds."""
    results = []

    adx_values = [15, 18, 20, 22, 26, 30, 35, 40]

    for adx in adx_values:
        config = StrategyConfig(
            adx_min=adx,
            cost_bps_per_side=5.0,
        )
        result = run_experiment(df, config, f"adx_{adx}")
        results.append(result)

    return results


def experiment_volume_thresholds(df: pd.DataFrame) -> list:
    """Try different volume ratio thresholds."""
    results = []

    vol_values = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5]

    for vol in vol_values:
        config = StrategyConfig(
            volume_ratio_min=vol,
            cost_bps_per_side=5.0,
            adx_min=26.0,
        )
        result = run_experiment(df, config, f"vol_{vol}")
        results.append(result)

    return results


def experiment_time_windows(df: pd.DataFrame) -> list:
    """Try different time windows for entries."""
    results = []

    # (long_first, long_last, short_first, short_last)
    windows = [
        (5, 60, 5, 50),    # Earlier
        (8, 60, 8, 45),    # Default
        (10, 55, 10, 40),  # Later
        (8, 70, 8, 50),    # Wider
        (12, 50, 12, 35),  # Tight
        (5, 50, 5, 35),    # Morning only
        (15, 60, 15, 45),  # Skip first 15 min
        (8, 60, 8, 60),    # Shorts full day
    ]

    for lf, ll, sf, sl in windows:
        config = StrategyConfig(
            long_first_bar=lf,
            long_last_signal_bar_exclusive=ll,
            short_first_bar=sf,
            short_last_signal_bar_exclusive=sl,
            cost_bps_per_side=5.0,
            adx_min=26.0,
            volume_ratio_min=1.2,
        )
        result = run_experiment(
            df, config, f"window_{lf}_{ll}_{sf}_{sl}"
        )
        results.append(result)

    return results


def main():
    """Run all experiments on CGPOWER and find the best config."""
    print("=" * 80)
    print("WILD STRATEGY EXPERIMENTS")
    print("=" * 80)

    # Load data
    path = ROOT / "Data" / "CGPOWER" / "CGPOWER_5MIN.csv"
    df = prepare_features(path)
    print(f"Loaded {len(df)} bars from {df['date'].nunique()} days\n")

    all_results = []

    # Run experiments
    experiments = [
        ("Stop/Target Ratios", experiment_stop_target_ratios),
        ("RSI Ranges", experiment_rsi_ranges),
        ("ADX Thresholds", experiment_adx_thresholds),
        ("Volume Thresholds", experiment_volume_thresholds),
        ("Time Windows", experiment_time_windows),
    ]

    for exp_name, exp_func in experiments:
        print(f"\n{'=' * 80}")
        print(f"EXPERIMENT: {exp_name}")
        print(f"{'=' * 80}")
        start = time.time()
        results = exp_func(df)
        elapsed = time.time() - start

        # Filter and sort by net return
        valid = [r for r in results if "error" not in r and "skip" not in r]
        valid.sort(key=lambda x: x.get("net_pct", 0), reverse=True)

        for r in valid:
            print(f"  {r['name']:30s} | trades={r.get('trades', 0):3d} | "
                  f"net={r.get('net_pct', 0):6.2f}% | "
                  f"win={r.get('win_rate_pct', 0):5.1f}% | "
                  f"pf={r.get('profit_factor', 0):.2f} | "
                  f"dd={r.get('max_dd_pct', 0):6.2f}%")

        print(f"\n  Completed in {elapsed:.1f}s")
        all_results.extend(valid)

    # Save all results
    results_df = pd.DataFrame(all_results)
    output_path = ROOT / "Research" / "wild_experiments_results.csv"
    results_df.to_csv(output_path, index=False)
    print(f"\n{'=' * 80}")
    print(f"Results saved to: {output_path}")
    print(f"Total experiments: {len(all_results)}")

    # Find top 10
    print(f"\n{'=' * 80}")
    print("TOP 10 CONFIGURATIONS BY NET RETURN:")
    print(f"{'=' * 80}")
    top10 = results_df.nlargest(10, "net_pct")
    print(top10[["name", "trades", "net_pct", "win_rate_pct", "profit_factor", "max_dd_pct"]].to_string(index=False))

    # Find top by profit factor
    print(f"\n{'=' * 80}")
    print("TOP 10 BY PROFIT FACTOR (min 30 trades):")
    print(f"{'=' * 80}")
    top_pf = results_df[results_df["trades"] >= 30].nlargest(10, "profit_factor")
    print(top_pf[["name", "trades", "net_pct", "win_rate_pct", "profit_factor", "max_dd_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
