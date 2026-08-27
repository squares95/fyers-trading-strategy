from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Strategies.G01.Core import (
    BARS_PER_DAY,
    DEFAULT_DATA_PATH,
    StrategyConfig,
    backtest,
    generate_signals,
    prepare_features,
    summarize_trades,
)


OUTPUT_DIR = Path(__file__).resolve().parent
RNG_SEED = 20260601


def equity_stats(returns: pd.Series | np.ndarray) -> dict[str, float | int]:
    ret = pd.Series(returns, dtype=float).dropna()
    if ret.empty:
        return {
            "trades": 0,
            "net_pct": 0.0,
            "avg_bps": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
        }
    equity = (1 + ret).cumprod()
    dd = equity / equity.cummax() - 1
    gp = ret[ret > 0].sum()
    gl = -ret[ret < 0].sum()
    return {
        "trades": int(len(ret)),
        "net_pct": round(float((equity.iloc[-1] - 1) * 100), 2),
        "avg_bps": round(float(ret.mean() * 10000), 2),
        "win_rate_pct": round(float((ret > 0).mean() * 100), 2),
        "profit_factor": round(float(gp / gl), 3) if gl > 0 else 999.0,
        "max_dd_pct": round(float(dd.min() * 100), 2),
    }


def add_periods(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"])
    out["date_dt"] = pd.to_datetime(out["date"])
    out["month"] = out["entry_time"].dt.to_period("M").astype(str)
    out["quarter"] = out["entry_time"].dt.to_period("Q").astype(str)
    return out


def grouped_stats(trades: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for key, grp in trades.groupby(group_col, sort=True):
        stats = equity_stats(grp["net_return"])
        stats[group_col] = key
        stats["longs"] = int((grp["direction"] == 1).sum())
        stats["shorts"] = int((grp["direction"] == -1).sum())
        rows.append(stats)
    return pd.DataFrame(rows)


def simulate_one(
    df: pd.DataFrame,
    signal_idx: int,
    direction: int,
    config: StrategyConfig,
) -> float:
    entry_idx = signal_idx + 1
    day_end_idx = (signal_idx // BARS_PER_DAY) * BARS_PER_DAY + (BARS_PER_DAY - 1)
    entry = float(df.at[entry_idx, "Open"])
    stop_distance = config.stop_atr_multiple * float(df.at[signal_idx, "atr14"])
    stop = entry - direction * stop_distance
    target = entry + direction * config.target_r * stop_distance
    exit_price = float(df.at[day_end_idx, "Close"])

    for pos in range(entry_idx, day_end_idx + 1):
        high = float(df.at[pos, "High"])
        low = float(df.at[pos, "Low"])
        if direction == 1:
            stop_hit = low <= stop
            target_hit = high >= target
        else:
            stop_hit = high >= stop
            target_hit = low <= target
        if stop_hit and target_hit:
            exit_price = stop
            break
        if stop_hit:
            exit_price = stop
            break
        if target_hit:
            exit_price = target
            break

    gross = direction * (exit_price / entry - 1)
    return float(gross - 2 * config.cost_bps_per_side / 10000)


def random_entry_control(
    df: pd.DataFrame,
    trades: pd.DataFrame,
    config: StrategyConfig,
    simulations: int = 1000,
) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED)
    date_to_day_start = df.groupby("date").head(1).set_index("date").index
    date_first_idx = {date: int(grp.index[0]) for date, grp in df.groupby("date", sort=False)}

    choices: list[tuple[str, int, np.ndarray]] = []
    for row in trades.itertuples(index=False):
        start = date_first_idx[row.date]
        if int(row.direction) == 1:
            bars = np.arange(config.long_first_bar, config.long_last_signal_bar_exclusive)
        else:
            bars = np.arange(config.short_first_bar, config.short_last_signal_bar_exclusive)
        indices = start + bars
        indices = indices[np.isfinite(df.loc[indices, "atr14"].to_numpy(float))]
        choices.append((row.date, int(row.direction), indices))

    random_returns = []
    for sim in range(simulations):
        returns = [
            simulate_one(df, int(rng.choice(indices)), direction, config)
            for _, direction, indices in choices
            if len(indices) > 0
        ]
        stats = equity_stats(returns)
        stats["simulation"] = sim
        random_returns.append(stats)
    return pd.DataFrame(random_returns)


def bootstrap_trade_returns(
    trades: pd.DataFrame,
    simulations: int = 5000,
) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED + 11)
    returns = trades["net_return"].to_numpy(float)
    n = len(returns)
    rows = []
    for sim in range(simulations):
        sample = rng.choice(returns, size=n, replace=True)
        stats = equity_stats(sample)
        stats["simulation"] = sim
        rows.append(stats)
    return pd.DataFrame(rows)


def shuffled_drawdown(trades: pd.DataFrame, simulations: int = 5000) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED + 29)
    returns = trades["net_return"].to_numpy(float)
    rows = []
    for sim in range(simulations):
        sample = rng.permutation(returns)
        stats = equity_stats(sample)
        rows.append(
            {
                "simulation": sim,
                "max_dd_pct": stats["max_dd_pct"],
                "net_pct": stats["net_pct"],
            }
        )
    return pd.DataFrame(rows)


def neighborhood_summary() -> dict[str, float | int]:
    all_path = OUTPUT_DIR / "cgpower_strategy_all_results.csv"
    if not all_path.exists():
        return {"available": 0}
    rows = pd.read_csv(all_path)
    pullbacks = rows[rows["strategy"].eq("vwap_ema_pullback")]
    robust = pullbacks[
        (pullbacks["train_pf"] >= 1.4)
        & (pullbacks["test_pf"] >= 1.4)
        & (pullbacks["train_trades"] >= 50)
        & (pullbacks["test_trades"] >= 25)
    ]
    both_profitable = pullbacks[
        (pullbacks["train_net_pct"] > 0)
        & (pullbacks["test_net_pct"] > 0)
        & (pullbacks["train_trades"] >= 50)
        & (pullbacks["test_trades"] >= 25)
    ]
    return {
        "available": 1,
        "pullback_candidates": int(len(pullbacks)),
        "pullback_train_and_test_profitable": int(len(both_profitable)),
        "pullback_robust_pf_cluster": int(len(robust)),
        "best_robust_pf_avg_bps": round(float(robust["all_avg_bps"].max()), 2)
        if not robust.empty
        else 0.0,
    }


def percentile_summary(series: pd.Series) -> dict[str, float]:
    q = series.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "p05": round(float(q.loc[0.05]), 2),
        "p25": round(float(q.loc[0.25]), 2),
        "p50": round(float(q.loc[0.50]), 2),
        "p75": round(float(q.loc[0.75]), 2),
        "p95": round(float(q.loc[0.95]), 2),
    }


def main() -> None:
    config = StrategyConfig()
    df = prepare_features(DEFAULT_DATA_PATH)
    signals = generate_signals(df, config)
    trades = add_periods(backtest(df, signals, config))

    dates = sorted(df["date"].unique())
    train_end = dates[int(len(dates) * 0.65) - 1]
    train = trades[trades["date"] <= train_end]
    validation = trades[trades["date"] > train_end]

    side_stats = grouped_stats(trades, "direction")
    quarter_stats = grouped_stats(trades, "quarter")
    month_stats = grouped_stats(trades, "month")
    random_control = random_entry_control(df, trades, config)
    bootstrap = bootstrap_trade_returns(trades)
    dd_shuffle = shuffled_drawdown(trades)

    actual = summarize_trades(trades)
    actual_net = actual["net_pct"]
    actual_pf = actual["profit_factor"]

    summary = {
        "strategy": "CGPOWER VWAP/EMA trend-pullback combo, first signal per day",
        "data_path": str(DEFAULT_DATA_PATH),
        "train_end_date": train_end,
        "baseline": actual,
        "train": summarize_trades(train),
        "validation": summarize_trades(validation),
        "long_leg": summarize_trades(trades[trades["direction"] == 1]),
        "short_leg": summarize_trades(trades[trades["direction"] == -1]),
        "quarters_positive": int((quarter_stats["net_pct"] > 0).sum()),
        "quarters_total": int(len(quarter_stats)),
        "months_positive": int((month_stats["net_pct"] > 0).sum()),
        "months_total": int(len(month_stats)),
        "random_entry_control": {
            "simulations": int(len(random_control)),
            "net_pct_percentiles": percentile_summary(random_control["net_pct"]),
            "profit_factor_percentiles": percentile_summary(random_control["profit_factor"]),
            "actual_net_pct_rank_pct": round(float((random_control["net_pct"] < actual_net).mean() * 100), 2),
            "actual_pf_rank_pct": round(float((random_control["profit_factor"] < actual_pf).mean() * 100), 2),
        },
        "bootstrap_actual_returns": {
            "simulations": int(len(bootstrap)),
            "net_pct_percentiles": percentile_summary(bootstrap["net_pct"]),
            "profit_factor_percentiles": percentile_summary(bootstrap["profit_factor"]),
            "probability_net_positive_pct": round(float((bootstrap["net_pct"] > 0).mean() * 100), 2),
            "probability_pf_above_1_pct": round(float((bootstrap["profit_factor"] > 1).mean() * 100), 2),
        },
        "shuffled_trade_order_drawdown": {
            "simulations": int(len(dd_shuffle)),
            "max_dd_pct_percentiles": percentile_summary(dd_shuffle["max_dd_pct"]),
        },
        "parameter_neighborhood": neighborhood_summary(),
    }

    side_stats.to_csv(OUTPUT_DIR / "cgpower_strategy_robustness_by_side.csv", index=False)
    quarter_stats.to_csv(OUTPUT_DIR / "cgpower_strategy_robustness_by_quarter.csv", index=False)
    month_stats.to_csv(OUTPUT_DIR / "cgpower_strategy_robustness_by_month.csv", index=False)
    random_control.to_csv(OUTPUT_DIR / "cgpower_strategy_random_entry_control.csv", index=False)
    (OUTPUT_DIR / "cgpower_strategy_robustness_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
