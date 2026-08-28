"""
Gold Strategy Module - Main Orchestrator.

This is the main entry point for the Gold (enhanced) strategy.
It re-exports all Gold-specific components and provides the complete
pipeline.

Beginner Note:
    The Gold strategy is the "pro" version of the base strategy.
    It adds:
    1. Daily regime filter (only trade good days)
    2. Signal strength scoring (only take strong signals)
    3. Optimized parameters (better than default)

    Think of it as the difference between a regular car and a sports car.
    Same basic idea, but better tuned and more selective.

Modules used:
    - regime_filter.py: Daily tradeability check
    - strength_scorer.py: Signal quality scoring
    - gold_config.py: Gold-specific parameters
    - backtest.py: Trade simulation
    - stats.py: Performance analysis
"""

import json

import numpy as np
import pandas as pd

from .backtest import backtest

# Re-export from base modules
# Re-export from gold_config
from .gold_config import (
    DATA_PATH,
    OUTPUT_DIR,
    TRAIN_CUTOFF,
    get_gold_config,
    get_shorts_only_config,
    get_super_gold_config,
)

# News/sentiment filter (Exp 6 — validated 2.5% gap filter)
from .news_filter import (
    compute_portfolio_gap_dates,
)

# Re-export from regime_filter
from .regime_filter import (
    REGIME_RANGE_MIN,
    REGIME_TURNOVER_MIN,
    daily_regime_table,
    filter_signals_by_regime,
    get_tradeable_dates,
)
from .stats import (
    analyze_by_direction,
    analyze_by_period,
    analyze_exit_reasons,
    summarize_trades,
)

# Re-export from strength_scorer
from .strength_scorer import (
    MIN_SIGNAL_STRENGTH,
    MIN_TRIGGER_COMPONENT,
    SIGNAL_STRENGTH_SCALES,
    SIGNAL_STRENGTH_WEIGHTS,
    STRENGTH_LABELS,
    attach_signal_strength,
    filter_by_strength,
    signal_strength_table,
)

# ============================================================================
# GOLD CONFIG INSTANCE
# ============================================================================

GOLD_CONFIG = get_gold_config()
"""
Gold strategy configuration (singleton).
Use this for all Gold strategy operations.
"""

SUPER_GOLD_CONFIG = get_super_gold_config()
"""
Super Gold configuration (wildly optimized).
Best net return (47.93%) with high PF (1.664).
"""

SHORTS_ONLY_CONFIG = get_shorts_only_config()
"""
Shorts-only configuration.
Best risk-adjusted returns: PF 1.724, DD -4.09%.
"""


# ============================================================================
# EQUITY STATISTICS (Gold-specific)
# ============================================================================


def equity_stats(trades: pd.DataFrame) -> dict:
    """
    Calculate equity curve statistics for Gold strategy.

    This is the main performance reporting function.
    Returns comprehensive statistics about the trading period.

    Args:
        trades: DataFrame from backtest() with net_return column

    Returns:
        Dictionary with:
            - trades: Number of trades
            - net_pct: Net return as percentage
            - avg_bps: Average return in basis points
            - win_rate_pct: Percentage of winners
            - profit_factor: Gross profit / Gross loss
            - max_dd_pct: Maximum drawdown

    Example:
        >>> trades = backtest(df, signals, GOLD_CONFIG)
        >>> stats = equity_stats(trades)
        >>> print(f"Net: {stats['net_pct']}%, Win rate: {stats['win_rate_pct']}%")
    """
    if trades.empty:
        return {
            "trades": 0,
            "net_pct": 0.0,
            "avg_bps": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
        }

    returns = trades["net_return"].astype(float)
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1
    gross_profit = returns[returns > 0].sum()
    gross_loss = -returns[returns < 0].sum()

    return {
        "trades": len(returns),
        "net_pct": round(float((equity.iloc[-1] - 1) * 100), 2),
        "avg_bps": round(float(returns.mean() * 10000), 2),
        "win_rate_pct": round(float((returns > 0).mean() * 100), 2),
        "profit_factor": round(float(gross_profit / gross_loss), 3) if gross_loss > 0 else 999.0,
        "max_dd_pct": round(float(drawdown.min() * 100), 2),
    }


# ============================================================================
# PERIOD ANALYSIS
# ============================================================================


def add_period_columns(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Add year, month, quarter columns to trades.

    Useful for analyzing performance over time.

    Args:
        trades: DataFrame from backtest()

    Returns:
        DataFrame with added columns: year, month, quarter
    """
    if trades.empty:
        return trades.copy()

    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"])
    out["exit_time"] = pd.to_datetime(out["exit_time"])
    out["year"] = out["entry_time"].dt.year
    out["month"] = out["entry_time"].dt.to_period("M").astype(str)
    out["quarter"] = out["entry_time"].dt.to_period("Q").astype(str)
    return out


def grouped_stats(trades: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """
    Calculate statistics grouped by a column (e.g., year, month, direction).

    Args:
        trades: DataFrame from backtest()
        group_col: Column to group by (e.g., "year", "month", "quarter")

    Returns:
        DataFrame with stats per group

    Example:
        >>> trades = backtest(df, signals, GOLD_CONFIG)
        >>> by_year = grouped_stats(trades, "year")
        >>> print(by_year)
    """
    rows = []
    for key, group in trades.groupby(group_col, sort=True):
        row = equity_stats(group)
        row[group_col] = key
        row["longs"] = int((group["direction"] == 1).sum())
        row["shorts"] = int((group["direction"] == -1).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def strength_band_stats(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate statistics for each strength band.

    Shows how performance varies by signal strength.

    Args:
        trades: DataFrame with strength_band column

    Returns:
        DataFrame with stats per strength band

    Example:
        >>> trades = backtest(df, signals)
        >>> trades = attach_signal_strength(trades, signals_scored)
        >>> band_stats = strength_band_stats(trades)
    """
    rows = []
    for band in STRENGTH_LABELS:
        group = trades[trades["strength_band"] == band]
        row = equity_stats(group)
        row["strength_band"] = band
        row["avg_strength"] = (
            round(float(group["signal_strength"].mean()), 2) if not group.empty else 0.0
        )
        row["longs"] = int((group["direction"] == 1).sum()) if not group.empty else 0
        row["shorts"] = int((group["direction"] == -1).sum()) if not group.empty else 0
        rows.append(row)
    return pd.DataFrame(rows)


# ============================================================================
# COST & BOOTSTRAP ANALYSIS
# ============================================================================


def cost_stress(trades: pd.DataFrame, costs: list = None) -> list:
    """
    Test strategy profitability at different cost levels.

    Args:
        trades: DataFrame from backtest()
        costs: List of cost values in bps (default: [0, 3, 5, 8, 10, 12, 15])

    Returns:
        List of dictionaries with stats per cost level

    Example:
        >>> trades = backtest(df, signals, GOLD_CONFIG)
        >>> stress = cost_stress(trades)
        >>> for result in stress:
        ...     print(f"Cost {result['cost_bps_per_side']}bps: {result['net_pct']}%")
    """
    if costs is None:
        costs = [0, 3, 5, 8, 10, 12, 15]

    rows = []
    gross = trades["gross_return"].astype(float)
    for cost in costs:
        adjusted = trades.copy()
        adjusted["net_return"] = gross - 2 * cost / 10000
        stats = equity_stats(adjusted)
        stats["cost_bps_per_side"] = cost
        rows.append(stats)
    return rows


def bootstrap_returns(trades: pd.DataFrame, simulations: int = 5000) -> dict:
    """
    Monte Carlo simulation to test strategy robustness.

    Randomly resamples trades (with replacement) to see how the
    strategy would have performed in different "lucky" or "unlucky" sequences.

    Args:
        trades: DataFrame from backtest()
        simulations: Number of bootstrap simulations (default: 5000)

    Returns:
        Dictionary with:
            - simulations: Number of runs
            - prob_net_positive_pct: % of sims with net > 0
            - prob_pf_above_1_pct: % of sims with profit factor > 1
            - net_pct_p05/p50/p95: 5th, 50th, 95th percentile net returns
            - pf_p05/p50/p95: 5th, 50th, 95th percentile profit factors

    Example:
        >>> trades = backtest(df, signals, GOLD_CONFIG)
        >>> bootstrap = bootstrap_returns(trades)
        >>> print(f"Probability positive: {bootstrap['prob_net_positive_pct']}%")
    """
    rng = np.random.default_rng(20260601)  # Fixed seed for reproducibility
    returns = trades["net_return"].to_numpy(float)

    if len(returns) == 0:
        return {"simulations": 0}

    net_pcts = []
    pfs = []
    for _ in range(simulations):
        # Resample with replacement
        sample = rng.choice(returns, size=len(returns), replace=True)
        sample_trades = pd.DataFrame({"net_return": sample})
        stats = equity_stats(sample_trades)
        net_pcts.append(stats["net_pct"])
        pfs.append(stats["profit_factor"])

    net_s = pd.Series(net_pcts)
    pf_s = pd.Series(pfs)

    return {
        "simulations": simulations,
        "prob_net_positive_pct": round(float((net_s > 0).mean() * 100), 2),
        "prob_pf_above_1_pct": round(float((pf_s > 1).mean() * 100), 2),
        "net_pct_p05": round(float(net_s.quantile(0.05)), 2),
        "net_pct_p50": round(float(net_s.quantile(0.50)), 2),
        "net_pct_p95": round(float(net_s.quantile(0.95)), 2),
        "pf_p05": round(float(pf_s.quantile(0.05)), 3),
        "pf_p50": round(float(pf_s.quantile(0.50)), 3),
        "pf_p95": round(float(pf_s.quantile(0.95)), 3),
    }


def strength_threshold_stats(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Test different strength thresholds for trade filtering.

    Args:
        trades: DataFrame with signal_strength column

    Returns:
        DataFrame with stats for each threshold and segment (all/train/validation)
    """
    thresholds = [0, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]
    rows = []

    for threshold in thresholds:
        filtered = trades[trades["signal_strength"] >= threshold]
        segments = {
            "all": filtered,
            "train_before_2025": filtered[filtered["entry_time"] < pd.Timestamp(TRAIN_CUTOFF)],
            "validation_2025_onward": filtered[
                filtered["entry_time"] >= pd.Timestamp(TRAIN_CUTOFF)
            ],
        }
        for segment, group in segments.items():
            row = equity_stats(group)
            row["threshold"] = threshold
            row["segment"] = segment
            rows.append(row)

    return pd.DataFrame(rows)


# ============================================================================
# COMPLETE GOLD PIPELINE
# ============================================================================


def run(portfolio: list[str] | None = None, gap_threshold: float | None = None) -> dict:
    """
    Run the complete Gold strategy pipeline and generate all reports.

    This is the main "do everything" function. It:
    1. Loads and prepares data
    2. Generates signals with Gold config
    3. Applies regime filter
    4. Applies news/sentiment gap filter (if portfolio provided)
    5. Scores signal strength
    6. Filters by strength
    7. Runs backtest
    8. Calculates all statistics
    9. Saves all results to CSV/JSON files

    Args:
        portfolio: Optional list of stock symbols. If provided, applies the
            validated 2.5% gap filter (skip days where any portfolio stock
            gapped > gap_threshold from prev close). If None, no news filter.
        gap_threshold: Gap % threshold (default: GOLD_CONFIG.gap_threshold = 0.025).
            Set higher (e.g. 0.05) to filter only extreme gaps.

    Returns:
        Dictionary with comprehensive results and statistics

    Example:
        >>> from Gold import run
        >>> results = run()  # Single stock, no news filter
        >>> results = run(portfolio=['CGPOWER', 'DRREDDY', 'INDUSINDBK'])  # Portfolio with filter
    """
    from .features import prepare_features
    from .signals import generate_signals

    if gap_threshold is None:
        gap_threshold = GOLD_CONFIG.gap_threshold

    # Step 1: Prepare data with features
    df = prepare_features(DATA_PATH)

    # Step 2: Calculate regime and get tradeable dates
    regime = daily_regime_table(df)
    tradeable_dates = set(regime.loc[regime["regime_tradeable"], "date"])

    # Step 2b: News/sentiment filter — skip chaos days (Exp 6)
    news_blocked_dates = set()
    if portfolio is not None and gap_threshold > 0:
        # Build portfolio daily data for gap detection
        portfolio_daily = {}
        for sym in portfolio:
            try:
                sym_path = DATA_PATH.parent.parent / sym / f"{sym}_5MIN.csv"
                if sym_path.exists():
                    sym_df = prepare_features(sym_path)
                    sym_daily = daily_regime_table(sym_df)
                    portfolio_daily[sym] = sym_daily
            except Exception:
                pass
        if portfolio_daily:
            news_blocked_dates = compute_portfolio_gap_dates(
                portfolio_daily, threshold=gap_threshold
            )

    # Step 3: Generate signals with Gold config
    old_signals = generate_signals(df)  # Base config (for comparison)
    old_trades = add_period_columns(backtest(df, old_signals))

    gold_signals = generate_signals(df, GOLD_CONFIG)
    gold_signals = gold_signals[gold_signals["date"].isin(tradeable_dates)].copy()
    if news_blocked_dates:
        gold_signals = gold_signals[~gold_signals["date"].isin(news_blocked_dates)].copy()

    # Step 4: Score strength
    gold_strength_signals = signal_strength_table(df, gold_signals, GOLD_CONFIG)

    # Step 5: Run backtest
    gold_setup_trades = add_period_columns(backtest(df, gold_signals, GOLD_CONFIG))
    gold_setup_trades = attach_signal_strength(gold_setup_trades, gold_strength_signals)

    # Step 6: Filter by strength
    gold_trades = gold_setup_trades[
        (gold_setup_trades["signal_strength"] >= MIN_SIGNAL_STRENGTH)
        & (gold_setup_trades["strength_trigger_component"] >= MIN_TRIGGER_COMPONENT)
    ].copy()

    # Step 7: Analyze results
    off_regime_trades = old_trades[~old_trades["date"].isin(tradeable_dates)].copy()
    train = gold_trades[gold_trades["entry_time"] < pd.Timestamp(TRAIN_CUTOFF)]
    validation = gold_trades[gold_trades["entry_time"] >= pd.Timestamp(TRAIN_CUTOFF)]

    # Build summary
    summary = {
        "data_path": str(DATA_PATH),
        "data_rows_used": len(df),
        "complete_trading_days_used": int(df["date"].nunique()),
        "date_range": [str(df["Datetime"].min()), str(df["Datetime"].max())],
        "regime_rule": {
            "turnover_med60_prev_gt": REGIME_TURNOVER_MIN,
            "range_med60_prev_gt": REGIME_RANGE_MIN,
            "tradeable_days": len(tradeable_dates),
        },
        "news_filter": {
            "enabled": bool(news_blocked_dates),
            "portfolio": portfolio or [],
            "gap_threshold": gap_threshold,
            "blocked_days": len(news_blocked_dates),
        },
        "old_strategy_unfiltered": equity_stats(old_trades),
        "old_strategy_off_regime": equity_stats(off_regime_trades),
        "gold_setup_before_strength_filter": equity_stats(gold_setup_trades),
        "gold_strategy": equity_stats(gold_trades),
        "gold_train_before_2025": equity_stats(train),
        "gold_validation_2025_onward": equity_stats(validation),
        "gold_long_leg": equity_stats(gold_trades[gold_trades["direction"] == 1]),
        "gold_short_leg": equity_stats(gold_trades[gold_trades["direction"] == -1]),
        "cost_stress": cost_stress(gold_trades, [0, 3, 5, 8, 10, 12, 15]),
        "bootstrap": bootstrap_returns(gold_trades),
        "signal_strength_rule": {
            "minimum_to_trade": MIN_SIGNAL_STRENGTH,
            "minimum_trigger_component": MIN_TRIGGER_COMPONENT,
            "weights": SIGNAL_STRENGTH_WEIGHTS,
            "scales": SIGNAL_STRENGTH_SCALES,
        },
        "strength_by_band": strength_band_stats(gold_setup_trades).to_dict("records"),
        "strength_thresholds": strength_threshold_stats(gold_setup_trades).to_dict("records"),
        "config": GOLD_CONFIG.__dict__,
    }

    # Step 8: Save outputs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "_newsfiltered" if news_blocked_dates else ""
    gold_setup_trades.to_csv(
        OUTPUT_DIR / f"cgpower_gold_strategy_all_setup_trades{suffix}.csv", index=False
    )
    gold_trades.to_csv(OUTPUT_DIR / f"cgpower_gold_strategy_trades{suffix}.csv", index=False)
    gold_strength_signals.to_csv(
        OUTPUT_DIR / f"cgpower_gold_strategy_signals_with_strength{suffix}.csv", index=False
    )
    regime.to_csv(OUTPUT_DIR / f"cgpower_gold_strategy_daily_regime{suffix}.csv", index=False)
    grouped_stats(gold_trades, "year").to_csv(
        OUTPUT_DIR / f"cgpower_gold_strategy_by_year{suffix}.csv", index=False
    )
    grouped_stats(gold_trades, "month").to_csv(
        OUTPUT_DIR / f"cgpower_gold_strategy_by_month{suffix}.csv", index=False
    )
    grouped_stats(gold_trades, "quarter").to_csv(
        OUTPUT_DIR / f"cgpower_gold_strategy_by_quarter{suffix}.csv", index=False
    )
    strength_band_stats(gold_setup_trades).to_csv(
        OUTPUT_DIR / f"cgpower_gold_strategy_strength_by_band{suffix}.csv", index=False
    )
    strength_threshold_stats(gold_setup_trades).to_csv(
        OUTPUT_DIR / f"cgpower_gold_strategy_strength_thresholds{suffix}.csv", index=False
    )
    (OUTPUT_DIR / f"cgpower_gold_strategy_summary{suffix}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    return summary


# ============================================================================
# PUBLIC API
# ============================================================================

__all__ = [
    # Config
    "GOLD_CONFIG",
    "SUPER_GOLD_CONFIG",
    "SHORTS_ONLY_CONFIG",
    "TRAIN_CUTOFF",
    "DATA_PATH",
    "OUTPUT_DIR",
    # Regime
    "daily_regime_table",
    "get_tradeable_dates",
    "filter_signals_by_regime",
    "REGIME_TURNOVER_MIN",
    "REGIME_RANGE_MIN",
    # Strength
    "signal_strength_table",
    "filter_by_strength",
    "attach_signal_strength",
    "MIN_SIGNAL_STRENGTH",
    "MIN_TRIGGER_COMPONENT",
    # Stats
    "equity_stats",
    "add_period_columns",
    "grouped_stats",
    "strength_band_stats",
    "strength_threshold_stats",
    "cost_stress",
    "bootstrap_returns",
    "summarize_trades",
    "analyze_by_direction",
    "analyze_by_period",
    "analyze_exit_reasons",
    # Pipeline
    "run",
    "backtest",
]


# ============================================================================
# COMMAND-LINE INTERFACE
# ============================================================================

if __name__ == "__main__":
    """
    Run the complete Gold strategy when executed directly:
        python Gold.py
    """
    print(json.dumps(run(), indent=2))
