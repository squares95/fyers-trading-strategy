"""
Backtest Engine Module.

This module simulates trade execution and calculates P&L.
It's like a "fake broker" that pretends to execute trades based on
historical price data.

Beginner Note:
    A backtester answers the question: "If I had taken these trades
    in the past, how much money would I have made?"

    It walks through time, bar by bar, and:
    1. Checks if we should enter a trade (based on signals)
    2. Tracks the open position
    3. Checks if we should exit (stop loss, target, end of day)
    4. Calculates profit/loss
"""

import numpy as np
import pandas as pd

from .config import BARS_PER_DAY, StrategyConfig


# ============================================================================
# TRADE SIMULATION
# ============================================================================

def simulate_single_trade(
    df: pd.DataFrame,
    signal_index: int,
    entry_index: int,
    direction: int,
    entry: float,
    stop: float,
    target: float,
    stop_distance: float,
    cost_bps_per_side: float,
) -> dict:
    """
    Simulate a single trade from entry to exit.

    This function walks forward from the entry bar and checks each bar
    to see if the stop or target was hit.

    Exit Priority (checked in this order):
        1. Both stop and target hit same bar → Stop (worst case, conservative)
        2. Stop hit → Exit at stop price
        3. Target hit → Exit at target price
        4. End of day → Exit at close price (default fallback)

    Args:
        df: DataFrame with price data
        signal_index: Bar index where signal was generated
        entry_index: Bar index where we enter (next bar after signal)
        direction: 1 for long, -1 for short
        entry: Entry price
        stop: Stop loss price
        target: Target price
        stop_distance: Distance to stop (for R-multiple calculation)
        cost_bps_per_side: Transaction cost in basis points

    Returns:
        Dictionary with trade details (exit price, P&L, reason, etc.)

    Example:
        >>> trade = simulate_single_trade(
        ...     df, signal_idx=100, entry_idx=101, direction=1,
        ...     entry=100, stop=95, target=110, stop_distance=5,
        ...     cost_bps_per_side=5
        ... )
    """
    # Calculate last bar of the day
    day_end_idx = (signal_index // BARS_PER_DAY) * BARS_PER_DAY + (BARS_PER_DAY - 1)

    # Default: exit at end of day at close price
    exit_price = float(df.at[day_end_idx, "Close"])
    exit_idx = day_end_idx
    exit_reason = "eod"

    # Walk through bars from entry to end of day
    for pos in range(entry_index, day_end_idx + 1):
        high = float(df.at[pos, "High"])
        low = float(df.at[pos, "Low"])

        # Check if stop or target was hit this bar
        if direction == 1:  # Long position
            stop_hit = low <= stop
            target_hit = high >= target
        else:  # Short position
            stop_hit = high >= stop
            target_hit = low <= target

        # Both hit same bar? Exit at stop (conservative)
        if stop_hit and target_hit:
            exit_price = stop
            exit_idx = pos
            exit_reason = "stop_same_bar"
            break

        # Stop hit
        if stop_hit:
            exit_price = stop
            exit_idx = pos
            exit_reason = "stop"
            break

        # Target hit
        if target_hit:
            exit_price = target
            exit_idx = pos
            exit_reason = "target"
            break

    # Calculate returns
    gross_return = direction * (exit_price / entry - 1)
    net_return = gross_return - (2 * cost_bps_per_side / 10000)  # 2 = entry + exit

    # Calculate R-multiple (how many "R" units did we make/lose)
    r_multiple = direction * (exit_price - entry) / stop_distance

    return {
        "direction": direction,
        "signal_index": signal_index,
        "entry_index": entry_index,
        "entry_time": df.at[entry_index, "Datetime"],
        "exit_time": df.at[exit_idx, "Datetime"],
        "entry": entry,
        "exit": exit_price,
        "stop": stop,
        "target": target,
        "stop_distance": stop_distance,
        "gross_return": gross_return,
        "net_return": net_return,
        "r_multiple": r_multiple,
        "exit_reason": exit_reason,
    }


# ============================================================================
# BACKTEST ORCHESTRATOR
# ============================================================================

def backtest(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    config: StrategyConfig = StrategyConfig(),
) -> pd.DataFrame:
    """
    Run backtest simulation on all signals.

    This is the main entry point. It takes a list of signals and
    simulates each trade, returning a DataFrame of all trades.

    Args:
        df: DataFrame with price data and indicators
        signals: DataFrame of signals (from generate_signals)
                 Must have columns: date, Datetime, direction, signal_index,
                 entry_index, entry, stop, target, stop_distance
        config: Strategy configuration (for cost_bps_per_side)

    Returns:
        DataFrame with one row per trade

    Example:
        >>> signals = generate_signals(df, config)
        >>> trades = backtest(df, signals, config)
        >>> # trades has columns: date, direction, entry, exit, net_return, etc.

    Performance:
        Each trade takes ~0.5ms to simulate.
        1000 trades = 0.5 seconds.
    """
    rows: list[dict] = []

    for signal in signals.itertuples(index=False):
        signal_idx = int(signal.signal_index)
        entry_idx = int(signal.entry_index)

        # Skip signals too close to end of day (no time to trade)
        if signal_idx % BARS_PER_DAY >= BARS_PER_DAY - 2:
            continue

        # Simulate this trade
        trade = simulate_single_trade(
            df=df,
            signal_index=signal_idx,
            entry_index=entry_idx,
            direction=int(signal.direction),
            entry=float(signal.entry),
            stop=float(signal.stop),
            target=float(signal.target),
            stop_distance=float(signal.stop_distance),
            cost_bps_per_side=config.cost_bps_per_side,
        )

        # Add date from signal
        trade["date"] = signal.date
        trade["signal_time"] = signal.Datetime

        rows.append(trade)

    return pd.DataFrame(rows)


# ============================================================================
# PERFORMANCE METRICS
# ============================================================================

def calculate_performance_metrics(trades: pd.DataFrame) -> dict:
    """
    Calculate key performance metrics from backtest results.

    Metrics calculated:
        - Net return: Total profit/loss as percentage
        - Win rate: Percentage of profitable trades
        - Profit factor: Gross profit / Gross loss
        - Max drawdown: Largest peak-to-trough decline
        - Average R: Average R-multiple per trade

    Args:
        trades: DataFrame from backtest()

    Returns:
        Dictionary of performance metrics

    Example:
        >>> trades = backtest(df, signals, config)
        >>> metrics = calculate_performance_metrics(trades)
        >>> print(f"Win rate: {metrics['win_rate_pct']}%")
        >>> print(f"Profit factor: {metrics['profit_factor']}")
    """
    if trades.empty:
        return {
            "trades": 0,
            "net_pct": 0.0,
            "avg_bps": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
            "avg_r": 0.0,
        }

    returns = trades["net_return"].astype(float)

    # Calculate equity curve
    equity = (1 + returns).cumprod()

    # Calculate drawdown
    drawdown = equity / equity.cummax() - 1

    # Gross profit and loss
    gross_profit = returns[returns > 0].sum()
    gross_loss = -returns[returns < 0].sum()

    return {
        "trades": int(len(trades)),
        "net_pct": round(float((equity.iloc[-1] - 1) * 100), 2),
        "avg_bps": round(float(returns.mean() * 10000), 2),
        "win_rate_pct": round(float((returns > 0).mean() * 100), 2),
        "profit_factor": round(float(gross_profit / gross_loss), 3) if gross_loss > 0 else np.inf,
        "max_dd_pct": round(float(drawdown.min() * 100), 2),
        "avg_r": round(float(trades["r_multiple"].mean()), 3),
    }
