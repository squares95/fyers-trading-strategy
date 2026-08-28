"""
Performance Statistics Module.

This module calculates statistics and metrics from backtest results.
It's the "report card" that shows how the strategy performed.

Beginner Note:
    After running a backtest, you need to know:
    - How much did I make?
    - What percentage of trades were winners?
    - What's the worst drawdown?
    - Is this strategy actually profitable?

    This module answers all those questions.
"""

import numpy as np
import pandas as pd

# ============================================================================
# MAIN STATISTICS
# ============================================================================


def summarize_trades(trades: pd.DataFrame) -> dict:
    """
    Calculate performance summary statistics from backtest results.

    This is the main "report card" function. It calculates all the
    key metrics in one go.

    Metrics:
        - trades: Number of trades
        - net_pct: Net return as percentage
        - avg_bps: Average return in basis points (1 bp = 0.01%)
        - win_rate_pct: Percentage of profitable trades
        - profit_factor: Gross profit / Gross loss (>1 = profitable)
        - max_dd_pct: Maximum drawdown as percentage

    Args:
        trades: DataFrame from backtest() with column "net_return"

    Returns:
        Dictionary of performance metrics

    Example:
        >>> trades = backtest(df, signals, config)
        >>> stats = summarize_trades(trades)
        >>> print(f"Trades: {stats['trades']}")
        >>> print(f"Net return: {stats['net_pct']}%")
        >>> print(f"Win rate: {stats['win_rate_pct']}%")
        >>> print(f"Profit factor: {stats['profit_factor']}")
        >>> print(f"Max drawdown: {stats['max_dd_pct']}%")
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

    # Calculate equity curve (compound returns)
    equity = (1 + returns).cumprod()

    # Calculate drawdown (peak-to-trough decline)
    drawdown = equity / equity.cummax() - 1

    # Gross profit and loss
    gross_profit = returns[returns > 0].sum()
    gross_loss = -returns[returns < 0].sum()

    return {
        "trades": len(trades),
        "net_pct": round(float((equity.iloc[-1] - 1) * 100), 2),
        "avg_bps": round(float(returns.mean() * 10000), 2),
        "win_rate_pct": round(float((returns > 0).mean() * 100), 2),
        "profit_factor": round(float(gross_profit / gross_loss), 3) if gross_loss > 0 else np.inf,
        "max_dd_pct": round(float(drawdown.min() * 100), 2),
    }


# ============================================================================
# DETAILED ANALYSIS
# ============================================================================


def analyze_by_direction(trades: pd.DataFrame) -> dict:
    """
    Analyze performance separately for longs and shorts.

    Args:
        trades: DataFrame from backtest() with column "direction"

    Returns:
        Dictionary with separate stats for longs and shorts

    Example:
        >>> trades = backtest(df, signals, config)
        >>> analysis = analyze_by_direction(trades)
        >>> print(f"Longs: {analysis['longs']['net_pct']}%")
        >>> print(f"Shorts: {analysis['shorts']['net_pct']}%")
    """
    if trades.empty or "direction" not in trades.columns:
        return {"longs": {}, "shorts": {}}

    longs = trades[trades["direction"] == 1]
    shorts = trades[trades["direction"] == -1]

    return {
        "longs": summarize_trades(longs),
        "shorts": summarize_trades(shorts),
    }


def analyze_by_period(trades: pd.DataFrame, period: str = "month") -> pd.DataFrame:
    """
    Analyze performance by time period (month, quarter, year).

    Args:
        trades: DataFrame from backtest()
        period: "month", "quarter", or "year"

    Returns:
        DataFrame with performance stats per period

    Example:
        >>> trades = backtest(df, signals, config)
        >>> monthly = analyze_by_period(trades, "month")
        >>> print(monthly)
    """
    if trades.empty or "entry_time" not in trades.columns:
        return pd.DataFrame()

    df = trades.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"])

    if period == "month":
        df["period"] = df["entry_time"].dt.to_period("M").astype(str)
    elif period == "quarter":
        df["period"] = df["entry_time"].dt.to_period("Q").astype(str)
    elif period == "year":
        df["period"] = df["entry_time"].dt.year
    else:
        raise ValueError(f"period must be 'month', 'quarter', or 'year', got '{period}'")

    rows = []
    for period_value, group in df.groupby("period", sort=True):
        stats = summarize_trades(group)
        stats["period"] = period_value
        rows.append(stats)

    return pd.DataFrame(rows)


def analyze_exit_reasons(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze which exit reasons are most common and their performance.

    Args:
        trades: DataFrame from backtest() with column "exit_reason"

    Returns:
        DataFrame with stats per exit reason

    Example:
        >>> trades = backtest(df, signals, config)
        >>> exit_analysis = analyze_exit_reasons(trades)
        >>> print(exit_analysis)
    """
    if trades.empty or "exit_reason" not in trades.columns:
        return pd.DataFrame()

    rows = []
    for reason, group in trades.groupby("exit_reason", sort=True):
        stats = summarize_trades(group)
        stats["exit_reason"] = reason
        rows.append(stats)

    return pd.DataFrame(rows)
