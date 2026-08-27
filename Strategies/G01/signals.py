"""
Signal Generation Module.

This module takes price data with indicators and generates trade signals.
It identifies where entries would occur and calculates entry prices,
stops, and targets.

Beginner Note:
    This is the "brain" of the strategy. It:
    1. Looks at each bar and asks "Should I enter here?"
    2. Applies the rules from signal_rules.py
    3. Resolves entry on the NEXT bar (not same bar)
    4. Calculates stop loss and profit target

    Think of it as the "scanner" that finds all potential trades.
"""

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .signal_rules import long_entry_condition, short_entry_condition, select_first_signal_per_day


# ============================================================================
# SIGNAL GENERATION
# ============================================================================

def generate_signals(df: pd.DataFrame, config: StrategyConfig = StrategyConfig()) -> pd.DataFrame:
    """
    Generate trading signals from price data.

    This function:
    1. Applies long and short entry conditions
    2. Selects first signal per day (no double entries)
    3. Resolves entry price on next bar's open
    4. Calculates stop loss and profit target
    5. Returns a clean DataFrame of actionable signals

    Args:
        df: DataFrame with features (from prepare_features)
        config: Strategy parameters

    Returns:
        DataFrame with columns:
            - date: Trading date
            - direction: 1 (long) or -1 (short)
            - Datetime: When signal triggered
            - signal_index: Bar index of signal
            - entry_index: Bar index of entry (signal + 1)
            - entry_time: Entry bar timestamp
            - entry: Entry price (next bar open)
            - atr14: ATR at signal time
            - stop_distance: Distance to stop
            - stop: Stop loss price
            - target: Profit target price

    Example:
        >>> df = prepare_features()
        >>> signals = generate_signals(df, StrategyConfig())
        >>> print(f"Generated {len(signals)} signals")
        >>> print(signals[['date', 'direction', 'entry', 'stop', 'target']].head())

    Note:
        This function uses "next bar open" for entry, which is realistic
        for a trading system. You can't always get the signal bar's close.
    """
    # Step 1: Get long and short entry masks
    long_mask = long_entry_condition(df, config)
    short_mask = short_entry_condition(df, config)

    # Step 2: Select first signal per day
    signal_df = select_first_signal_per_day(df, long_mask, short_mask)

    if signal_df.empty:
        return signal_df

    # Step 3: Build index lookup for fast access
    # This lets us find bar index from (date, Datetime) quickly
    index_lookup = df.reset_index().set_index(["date", "Datetime"])["index"]

    # Step 4: Map signals to bar indices
    signal_indexes = []
    for row in signal_df.itertuples(index=False):
        signal_idx = int(index_lookup.loc[(row.date, row.Datetime)])
        signal_indexes.append(signal_idx)

    signal_df["signal_index"] = signal_indexes

    # Step 5: Entry is the bar AFTER the signal
    signal_df["entry_index"] = signal_df["signal_index"] + 1

    # Remove signals where entry would be beyond data
    signal_df = signal_df[signal_df["entry_index"] < len(df)].copy()

    if signal_df.empty:
        return signal_df

    # Step 6: Get entry time and price (next bar's open)
    entry_times = []
    entries = []
    for row in signal_df.itertuples(index=False):
        entry_idx = int(row.entry_index)
        entry_times.append(df.loc[entry_idx, "Datetime"])
        entries.append(float(df.loc[entry_idx, "Open"]))

    signal_df["entry_time"] = entry_times
    signal_df["entry"] = entries

    # Step 7: Get ATR and calculate stop/target
    signal_df["atr14"] = df.loc[signal_df["signal_index"].values, "atr14"].values
    signal_df["stop_distance"] = config.stop_atr_multiple * signal_df["atr14"]

    # Long: stop below entry. Short: stop above entry
    signal_df["stop"] = signal_df["entry"] - signal_df["direction"] * signal_df["stop_distance"]

    # Target is always in the profitable direction
    signal_df["target"] = signal_df["entry"] + signal_df["direction"] * config.target_r * signal_df["stop_distance"]

    return signal_df.reset_index(drop=True)


# ============================================================================
# SIGNAL STATISTICS
# ============================================================================

def get_signal_stats(signals: pd.DataFrame) -> dict:
    """
    Get statistics about generated signals.

    Args:
        signals: DataFrame from generate_signals()

    Returns:
        Dictionary with signal statistics

    Example:
        >>> signals = generate_signals(df, config)
        >>> stats = get_signal_stats(signals)
        >>> print(f"Total signals: {stats['total']}")
        >>> print(f"Longs: {stats['longs']}, Shorts: {stats['shorts']}")
    """
    if signals.empty:
        return {"total": 0, "longs": 0, "shorts": 0}

    return {
        "total": int(len(signals)),
        "longs": int((signals["direction"] == 1).sum()),
        "shorts": int((signals["direction"] == -1).sum()),
        "avg_entry_price": float(signals["entry"].mean()),
        "avg_atr": float(signals["atr14"].mean()),
    }
