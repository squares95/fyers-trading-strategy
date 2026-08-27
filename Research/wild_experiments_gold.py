"""
Wild Strategy Experiments WITH Gold enhancements.

This tests different parameters when using:
- Regime filter (daily tradeability check)
- Strength scoring (quality filter)
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
from Strategies.G01 import Gold
from Strategies.G01.Core import prepare_features, generate_signals, backtest, StrategyConfig


def run_gold_experiment(
    df: pd.DataFrame,
    config: StrategyConfig,
    regime_table: pd.DataFrame,
    min_strength: float = Gold.MIN_SIGNAL_STRENGTH,
    min_trigger: float = Gold.MIN_TRIGGER_COMPONENT,
    name: str = "",
) -> dict:
    """Run experiment WITH Gold enhancements."""
    try:
        tradeable_dates = set(regime_table.loc[regime_table['regime_tradeable'], 'date'])

        signals = generate_signals(df, config)
        signals = signals[signals['date'].isin(tradeable_dates)].copy()

        if len(signals) == 0:
            return {"name": name, "trades": 0, "net_pct": 0, "skip": "no_signals"}

        strength = Gold.signal_strength_table(df, signals, config)
        trades = backtest(df, signals, config)

        # Attach strength and filter
        trades_with_strength = Gold.attach_signal_strength(trades, strength)
        filtered = trades_with_strength[
            (trades_with_strength['signal_strength'] >= min_strength) &
            (trades_with_strength['strength_trigger_component'] >= min_trigger)
        ]

        if len(filtered) == 0:
            return {"name": name, "trades": 0, "net_pct": 0, "skip": "no_filtered"}

        stats = Gold.equity_stats(filtered)
        stats["name"] = name
        stats["signals"] = len(signals)
        stats["filtered_trades"] = len(filtered)
        return stats
    except Exception as e:
        return {"name": name, "error": str(e)}


def main():
    print("=" * 100)
    print("WILD STRATEGY EXPERIMENTS WITH GOLD ENHANCEMENTS")
    print("=" * 100)

    # Load data
    path = ROOT / "Data" / "CGPOWER" / "CGPOWER_5MIN.csv"
    df = prepare_features(path)
    regime = Gold.daily_regime_table(df)
    print(f"Loaded {len(df)} bars from {df['date'].nunique()} days")
    print(f"Tradeable days: {regime['regime_tradeable'].sum()} / {len(regime)}\n")

    all_results = []

    # ===== EXPERIMENT 1: Stop/Target Ratios =====
    print("=" * 100)
    print("EXP 1: Stop/Target Ratios")
    print("=" * 100)

    stop_targets = [
        (1.0, 1.5), (1.0, 2.0), (1.3, 2.0), (1.5, 2.0), (1.5, 2.5),
        (1.5, 3.0), (2.0, 2.0), (2.0, 3.0), (2.0, 4.0), (2.5, 5.0),
        (1.0, 3.0), (1.0, 4.0), (1.0, 5.0), (1.2, 2.4), (1.3, 3.9),
    ]

    for stop, target in stop_targets:
        config = StrategyConfig(
            stop_atr_multiple=stop, target_r=target,
            adx_min=26.0, volume_ratio_min=1.2,
            long_rsi_min=50.0, long_rsi_max=75.0,
            short_rsi_min=28.0, short_rsi_max=55.0,
        )
        result = run_gold_experiment(df, config, regime, name=f"st{stop}_t{target}")
        if "error" not in result and "skip" not in result:
            print(f"  st={stop} t={target:4.1f} | trades={result['trades']:3d} | "
                  f"net={result['net_pct']:6.2f}% | win={result['win_rate_pct']:5.1f}% | "
                  f"pf={result['profit_factor']:.3f} | dd={result['max_dd_pct']:6.2f}%")
            all_results.append(result)

    # ===== EXPERIMENT 2: Strength Thresholds =====
    print("\n" + "=" * 100)
    print("EXP 2: Strength Thresholds")
    print("=" * 100)

    strength_combos = [
        (30, 0.10), (35, 0.10), (40, 0.10), (45, 0.10), (50, 0.10),
        (40, 0.15), (40, 0.20), (40, 0.25), (40, 0.30),
        (50, 0.15), (50, 0.20), (50, 0.25),
        (45, 0.15), (45, 0.20),
        (35, 0.15), (35, 0.20),
        (55, 0.15), (55, 0.20),
        (60, 0.15), (60, 0.20),
    ]

    for min_str, min_trig in strength_combos:
        result = run_gold_experiment(
            df, Gold.GOLD_CONFIG, regime,
            min_strength=min_str, min_trigger=min_trig,
            name=f"str{min_str}_tr{min_trig}"
        )
        if "error" not in result and "skip" not in result:
            print(f"  strength>={min_str} trigger>={min_trig} | trades={result['trades']:3d} | "
                  f"net={result['net_pct']:6.2f}% | win={result['win_rate_pct']:5.1f}% | "
                  f"pf={result['profit_factor']:.3f} | dd={result['max_dd_pct']:6.2f}%")
            all_results.append(result)

    # ===== EXPERIMENT 3: ADX Thresholds =====
    print("\n" + "=" * 100)
    print("EXP 3: ADX Thresholds")
    print("=" * 100)

    for adx in [20, 22, 24, 26, 28, 30, 32, 35, 40]:
        config = StrategyConfig(adx_min=adx, volume_ratio_min=1.2)
        result = run_gold_experiment(df, config, regime, name=f"adx{adx}")
        if "error" not in result and "skip" not in result:
            print(f"  adx>={adx} | trades={result['trades']:3d} | "
                  f"net={result['net_pct']:6.2f}% | win={result['win_rate_pct']:5.1f}% | "
                  f"pf={result['profit_factor']:.3f} | dd={result['max_dd_pct']:6.2f}%")
            all_results.append(result)

    # ===== EXPERIMENT 4: Volume Thresholds =====
    print("\n" + "=" * 100)
    print("EXP 4: Volume Thresholds")
    print("=" * 100)

    for vol in [0.8, 1.0, 1.2, 1.4, 1.5, 1.8, 2.0, 2.5]:
        config = StrategyConfig(volume_ratio_min=vol, adx_min=26.0)
        result = run_gold_experiment(df, config, regime, name=f"vol{vol}")
        if "error" not in result and "skip" not in result:
            print(f"  vol>={vol} | trades={result['trades']:3d} | "
                  f"net={result['net_pct']:6.2f}% | win={result['win_rate_pct']:5.1f}% | "
                  f"pf={result['profit_factor']:.3f} | dd={result['max_dd_pct']:6.2f}%")
            all_results.append(result)

    # ===== EXPERIMENT 5: Regime Relaxation =====
    print("\n" + "=" * 100)
    print("EXP 5: Regime Relaxation (Different Thresholds)")
    print("=" * 100)

    # This would require modifying regime_filter.py, so we skip for now
    print("  (Regime modification requires code change - skipped for now)")

    # ===== EXPERIMENT 6: Just Longs vs Just Shorts =====
    print("\n" + "=" * 100)
    print("EXP 6: Longs Only vs Shorts Only")
    print("=" * 100)

    # Longs only
    config_long = StrategyConfig(
        adx_min=26.0, volume_ratio_min=1.2,
        short_rsi_min=100, short_rsi_max=0,  # Effectively disable shorts
    )
    result_long = run_gold_experiment(df, config_long, regime, name="longs_only")

    # Shorts only
    config_short = StrategyConfig(
        adx_min=26.0, volume_ratio_min=1.2,
        long_rsi_min=100, long_rsi_max=0,  # Effectively disable longs
    )
    result_short = run_gold_experiment(df, config_short, regime, name="shorts_only")

    for name, result in [("Longs Only", result_long), ("Shorts Only", result_short)]:
        if "error" not in result and "skip" not in result:
            print(f"  {name:12s} | trades={result['trades']:3d} | "
                  f"net={result['net_pct']:6.2f}% | win={result['win_rate_pct']:5.1f}% | "
                  f"pf={result['profit_factor']:.3f} | dd={result['max_dd_pct']:6.2f}%")
            all_results.append(result)

    # Save results
    print("\n" + "=" * 100)
    print("SAVING RESULTS")
    print("=" * 100)

    results_df = pd.DataFrame(all_results)
    output_path = ROOT / "Research" / "wild_experiments_gold_results.csv"
    results_df.to_csv(output_path, index=False)
    print(f"Saved {len(all_results)} experiments to: {output_path}")

    # Top 10
    print("\n" + "=" * 100)
    print("TOP 10 BY NET RETURN:")
    print("=" * 100)
    top = results_df.nlargest(10, "net_pct")
    for _, r in top.iterrows():
        print(f"  {r['name']:20s} | trades={r['trades']:3d} | "
              f"net={r['net_pct']:6.2f}% | win={r['win_rate_pct']:5.1f}% | "
              f"pf={r['profit_factor']:.3f} | dd={r['max_dd_pct']:6.2f}%")

    # Top by PF
    print("\n" + "=" * 100)
    print("TOP 10 BY PROFIT FACTOR (min 30 trades):")
    print("=" * 100)
    top_pf = results_df[results_df["trades"] >= 30].nlargest(10, "profit_factor")
    for _, r in top_pf.iterrows():
        print(f"  {r['name']:20s} | trades={r['trades']:3d} | "
              f"net={r['net_pct']:6.2f}% | win={r['win_rate_pct']:5.1f}% | "
              f"pf={r['profit_factor']:.3f} | dd={r['max_dd_pct']:6.2f}%")


if __name__ == "__main__":
    main()
