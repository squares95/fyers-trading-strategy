"""
Signal Rules Module.

This module defines the conditions for entry signals (long and short).
It's the "decision maker" that looks at indicator values and decides
when to enter a trade.

Beginner Note:
    This is where the strategy logic lives. Each function here answers
    a specific question:
        - "Should I go long here?"  -> long_entry_condition()
        - "Should I go short here?" -> short_entry_condition()

    The conditions use technical indicators (from indicators.py) to make
    these decisions. Think of these as the "rules of the game".
"""

import pandas as pd

from .indicators import prev_close
from .config import StrategyConfig


# ============================================================================
# LONG ENTRY CONDITIONS
# ============================================================================

def long_entry_condition(
    df: pd.DataFrame,
    config: StrategyConfig,
    bar_column: str = "bar_no",
) -> pd.Series:
    """
    Determine where long entry conditions are met.

    Returns a boolean Series (True = go long at this bar, False = don't).

    LONG ENTRY RULES (all must be true):
        1. Time window: Bar must be in trading hours
           - bar_no >= long_first_bar (8 = 9:50 AM, not too early)
           - bar_no < long_last_signal_bar_exclusive (60 = 14:15 PM, not too late)

        2. Trend is up:
           - Close > VWAP (price above average price)
           - EMA(21) > EMA(55) (short-term trend > long-term trend)

        3. Strong trend:
           - ADX >= adx_min (default 22, higher = stronger trend)

        4. Volume confirmation:
           - Volume ratio >= volume_ratio_min (default 1.0, 1.5 = 50% above avg)

        5. Not overbought:
           - RSI between long_rsi_min (50) and long_rsi_max (75)

        6. Pullback happened:
           - Low touched EMA(21) or VWAP (price pulled back to support)

        7. Recovery confirmed:
           - Close > EMA(21) (back above the EMA after pullback)
           - Close > Previous Close (price rising)

    Args:
        df: DataFrame with all indicators calculated
        config: Strategy parameters (from config.py)

    Returns:
        Boolean Series (True where long entry conditions are met)

    Example:
        >>> long_signals = long_entry_condition(df, StrategyConfig())
        >>> first_long = df[long_signals].iloc[0]  # First long signal

    Strategy Philosophy:
        "Buy the dip in an uptrend" - we want to enter when:
        - Overall trend is up (EMAs, VWAP)
        - There was a pullback (touched EMA or VWAP)
        - The dip is ending (price recovering)
        - Momentum is strong (ADX, volume)
        - Not at extremes (RSI between 50-75)
    """
    return (
        # Time window - only enter during main trading hours
        (df[bar_column] >= config.long_first_bar) &
        (df[bar_column] < config.long_last_signal_bar_exclusive) &

        # Trend direction
        (df["Close"] > df["vwap"]) &         # Price above average
        (df["ema21"] > df["ema55"]) &        # Short EMA > Long EMA

        # Trend strength
        (df["adx_for_signal"] >= config.adx_min) &

        # Volume confirmation
        (df["vol_ratio20"] >= config.volume_ratio_min) &

        # RSI range (not overbought, not oversold)
        (df["rsi14"].between(config.long_rsi_min, config.long_rsi_max)) &

        # Pullback happened
        ((df["Low"] <= df["ema21"]) | (df["Low"] <= df["vwap"])) &

        # Recovery
        (df["Close"] > df["ema21"]) &
        (df["Close"] > prev_close(df["Close"]))
    )


# ============================================================================
# SHORT ENTRY CONDITIONS
# ============================================================================

def short_entry_condition(
    df: pd.DataFrame,
    config: StrategyConfig,
    bar_column: str = "bar_no",
) -> pd.Series:
    """
    Determine where short entry conditions are met.

    Returns a boolean Series (True = go short at this bar, False = don't).

    SHORT ENTRY RULES (all must be true):
        1. Time window: Bar must be in trading hours
           - bar_no >= short_first_bar (8 = 9:50 AM)
           - bar_no < short_last_signal_bar_exclusive (45 = 13:00 PM)
           - Note: Shorts exit earlier than longs!

        2. Trend is down:
           - Close < VWAP (price below average)
           - EMA(13) < EMA(34) (short-term trend < long-term trend)

        3. Strong trend:
           - ADX >= adx_min (default 22)

        4. Volume confirmation:
           - Volume ratio >= volume_ratio_min

        5. Not oversold:
           - RSI between short_rsi_min (28) and short_rsi_max (55)

        6. Bounce happened:
           - High touched EMA(13) or VWAP (price bounced to resistance)

        7. Decline confirmed:
           - Close < EMA(13)
           - Close < Previous Close

    Args:
        df: DataFrame with all indicators calculated
        config: Strategy parameters (from config.py)

    Returns:
        Boolean Series (True where short entry conditions are met)

    Example:
        >>> short_signals = short_entry_condition(df, StrategyConfig())
        >>> first_short = df[short_signals].iloc[0]  # First short signal

    Strategy Philosophy:
        "Sell the rally in a downtrend" - we want to enter when:
        - Overall trend is down (EMAs, VWAP)
        - There was a bounce (touched EMA or VWAP)
        - The bounce is ending (price declining)
        - Momentum is strong (ADX, volume)
        - Not at extremes (RSI between 28-55)

    Why shorts use different EMAs (13/34) vs longs (21/55):
        Shorts need faster signal because:
        1. They have more risk (losses can be unlimited)
        2. Bear moves can be sharper and shorter
        3. Faster EMAs catch the reversal quicker
    """
    return (
        # Time window
        (df[bar_column] >= config.short_first_bar) &
        (df[bar_column] < config.short_last_signal_bar_exclusive) &

        # Trend direction
        (df["Close"] < df["vwap"]) &
        (df["ema13"] < df["ema34"]) &

        # Trend strength
        (df["adx_for_signal"] >= config.adx_min) &

        # Volume confirmation
        (df["vol_ratio20"] >= config.volume_ratio_min) &

        # RSI range
        (df["rsi14"].between(config.short_rsi_min, config.short_rsi_max)) &

        # Bounce happened
        ((df["High"] >= df["ema13"]) | (df["High"] >= df["vwap"])) &

        # Decline
        (df["Close"] < df["ema13"]) &
        (df["Close"] < prev_close(df["Close"]))
    )


# ============================================================================
# SIGNAL SELECTION (One per day)
# ============================================================================

def select_first_signal_per_day(
    df: pd.DataFrame,
    long_mask: pd.Series,
    short_mask: pd.Series,
) -> pd.DataFrame:
    """
    Select the first valid signal for each trading day.

    This is important because:
        1. Taking multiple signals per day often leads to overtrading
        2. The first signal usually has the best risk/reward
        3. Avoids "stacking" correlated entries

    If both long and short signals trigger on the same day, we keep
    only the FIRST one (chronologically).

    Args:
        df: Full DataFrame with Datetime, date columns
        long_mask: Boolean series for long entry conditions
        short_mask: Boolean series for short entry conditions

    Returns:
        DataFrame with one row per day containing the first signal

    Example:
        >>> long_mask = long_entry_condition(df, config)
        >>> short_mask = short_entry_condition(df, config)
        >>> daily_signals = select_first_signal_per_day(df, long_mask, short_mask)
        >>> # Result: one signal per day (the earliest one)
    """
    # Combine long and short signals
    signal_rows = pd.concat(
        [
            df.loc[long_mask, ["Datetime", "date", "bar_no"]].assign(direction=1),   # 1 = long
            df.loc[short_mask, ["Datetime", "date", "bar_no"]].assign(direction=-1),  # -1 = short
        ],
        axis=0,
    )

    # Sort by date, then time (earliest first), then direction (longs before shorts)
    signal_rows = signal_rows.sort_values(
        ["date", "Datetime", "direction"],
        ascending=[True, True, False]  # direction=False means -1 comes before 1
    )

    # Keep only the first signal per day
    return signal_rows.groupby("date", as_index=False).first()
