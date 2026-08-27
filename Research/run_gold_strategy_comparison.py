from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Strategies.G01 import Core as base
from Strategies.G01 import Gold as gold


DATA_DIR = ROOT / "Data"
OUTPUT_DIR = ROOT / "Research"


def strategy_stats_for_symbol(symbol: str) -> tuple[dict[str, object], pd.DataFrame]:
    path = DATA_DIR / symbol / f"{symbol}_5MIN.csv"
    df = base.prepare_features(path)
    regime = gold.daily_regime_table(df)
    tradeable_dates = set(regime.loc[regime["regime_tradeable"], "date"])

    all_signals = base.generate_signals(df, gold.GOLD_CONFIG)
    all_trades = gold.add_period_columns(base.backtest(df, all_signals, gold.GOLD_CONFIG))

    regime_signals = all_signals[all_signals["date"].isin(tradeable_dates)].copy()
    strength_signals = gold.signal_strength_table(df, regime_signals, gold.GOLD_CONFIG)
    setup_trades = gold.add_period_columns(base.backtest(df, regime_signals, gold.GOLD_CONFIG))
    setup_trades = gold.attach_signal_strength(setup_trades, strength_signals)
    final_trades = setup_trades[
        (setup_trades["signal_strength"] >= gold.MIN_SIGNAL_STRENGTH)
        & (setup_trades["strength_trigger_component"] >= gold.MIN_TRIGGER_COMPONENT)
    ].copy()

    stats = {
        "symbol": symbol,
        "data_path": str(path),
        "rows_used": int(len(df)),
        "complete_days": int(df["date"].nunique()),
        "date_start": str(df["Datetime"].min()),
        "date_end": str(df["Datetime"].max()),
        "regime_tradeable_days": int(len(tradeable_dates)),
        "signals_before_regime": int(len(all_signals)),
        "signals_after_regime": int(len(regime_signals)),
        "unfiltered_trades": gold.equity_stats(all_trades),
        "setup_before_strength_filter": gold.equity_stats(setup_trades),
        "final_strategy": gold.equity_stats(final_trades),
        "train_before_2025": gold.equity_stats(
            final_trades[final_trades["entry_time"] < gold.TRAIN_CUTOFF]
        ),
        "validation_2025_onward": gold.equity_stats(
            final_trades[final_trades["entry_time"] >= gold.TRAIN_CUTOFF]
        ),
        "long_leg": gold.equity_stats(final_trades[final_trades["direction"] == 1]),
        "short_leg": gold.equity_stats(final_trades[final_trades["direction"] == -1]),
    }
    return stats, final_trades


def flatten_stats(stats: dict[str, object]) -> dict[str, object]:
    row = {
        "symbol": stats["symbol"],
        "rows_used": stats["rows_used"],
        "complete_days": stats["complete_days"],
        "date_start": stats["date_start"],
        "date_end": stats["date_end"],
        "regime_tradeable_days": stats["regime_tradeable_days"],
        "signals_before_regime": stats["signals_before_regime"],
        "signals_after_regime": stats["signals_after_regime"],
    }
    for prefix in [
        "unfiltered_trades",
        "setup_before_strength_filter",
        "final_strategy",
        "train_before_2025",
        "validation_2025_onward",
        "long_leg",
        "short_leg",
    ]:
        for key, value in stats[prefix].items():
            row[f"{prefix}_{key}"] = value
    return row


def run(symbols: list[str]) -> dict[str, object]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    stats_rows = []
    details = {}
    for symbol in symbols:
        stats, trades = strategy_stats_for_symbol(symbol)
        stats_rows.append(flatten_stats(stats))
        details[symbol] = stats
        trades.to_csv(OUTPUT_DIR / f"{symbol}_gold_strategy_trades.csv", index=False)

    comparison = pd.DataFrame(stats_rows)
    comparison.to_csv(OUTPUT_DIR / "gold_strategy_symbol_comparison.csv", index=False)
    (OUTPUT_DIR / "gold_strategy_symbol_comparison.json").write_text(
        json.dumps(details, indent=2), encoding="utf-8"
    )
    return details


if __name__ == "__main__":
    print(json.dumps(run(["CGPOWER", "HDFCBANK"]), indent=2))
