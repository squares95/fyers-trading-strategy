"""
Technical Indicators Module.

This module contains pure mathematical functions for calculating technical indicators.
No trading logic, no data loading - just the math!

Beginner Note:
    Think of these like basic math operations. Each function takes some data,
    does a calculation, and returns the result. These are the "ingredients"
    that other parts of the system use to make decisions.
"""

import numpy as np
import pandas as pd

# ============================================================================
# EXPONENTIAL MOVING AVERAGE (EMA)
# ============================================================================


def ema(series: pd.Series, span: int) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA).

    EMA is like a regular moving average, but it gives more weight to recent prices.
    This makes it more responsive to new information than a simple average.

    Think of it like: recent prices matter more than old prices.

    Args:
        series: Price data (usually Close prices)
        span: Number of periods for the EMA
              - span=12 is common for "fast" EMA
              - span=26 is common for "slow" EMA

    Returns:
        Series with EMA values, same length as input

    Example:
        >>> close_prices = pd.Series([100, 102, 101, 103, 105])
        >>> ema20 = ema(close_prices, 20)

    Why this matters:
        When short EMA crosses above long EMA, it might signal an uptrend.
        When short EMA crosses below long EMA, it might signal a downtrend.
    """
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


# ============================================================================
# RELATIVE STRENGTH INDEX (RSI)
# ============================================================================


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI).

    RSI measures how fast prices are changing and whether they're overbought or oversold.

    The Magic Numbers:
        - RSI > 70: Stock might be "overbought" (too expensive, could drop)
        - RSI < 30: Stock might be "oversold" (too cheap, could bounce)
        - RSI = 50: Neutral (no strong momentum either way)

    Args:
        close: Closing prices
        period: Lookback period (default: 14, popularized by Wilder)

    Returns:
        Series with RSI values from 0 to 100

    Example:
        >>> close_prices = pd.Series([100, 102, 101, 103, 105, 107, 106, 108])
        >>> rsi14 = rsi(close_prices, 14)

    How it works:
        1. Calculate price changes (up or down)
        2. Separate gains (positive changes) from losses (negative changes)
        3. Calculate average gain and average loss
        4. RS = Average Gain / Average Loss
        5. RSI = 100 - (100 / (1 + RS))

    Beginner Note:
        RSI is a "momentum oscillator" - it measures the SPEED of price changes,
        not the direction. High RSI means prices rose quickly recently.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)  # Only positive changes (losses become 0)
    loss = -delta.clip(upper=0)  # Only negative changes (gains become 0)

    # Calculate exponential moving averages of gains and losses
    # Using Wilder's smoothing method (alpha = 1/period)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    # Relative Strength = Average Gain / Average Loss
    rs = avg_gain / avg_loss.replace(0, np.nan)  # Avoid division by zero

    # RSI formula: 100 - (100 / (1 + RS))
    return 100 - (100 / (1 + rs))


# ============================================================================
# TRUE RANGE (TR)
# ============================================================================


def true_range(df: pd.DataFrame) -> pd.Series:
    """
    Calculate True Range - the measure of a bar's overall range.

    True Range is more accurate than simply using High - Low because it accounts
    for gaps and overnight moves.

    For each bar, True Range is the MAXIMUM of:
        1. High - Low (the bar's own range)
        2. |High - Previous Close| (gap up from yesterday)
        3. |Low - Previous Close| (gap down from yesterday)

    Args:
        df: DataFrame with columns 'High', 'Low', 'Close'

    Returns:
        Series with True Range values

    Example:
        >>> df = pd.DataFrame({
        ...     'High': [105, 107, 106],
        ...     'Low': [98, 100, 99],
        ...     'Close': [103, 104, 102]
        ... })
        >>> tr = true_range(df)

    Why this matters:
        True Range is the foundation for ATR. It tells us how much a stock
        typically moves in a given period.
    """
    prev_close = df["Close"].shift(1)

    return pd.concat(
        [
            df["High"] - df["Low"],  # Bar's own range
            (df["High"] - prev_close).abs(),  # Gap from yesterday's close (up)
            (df["Low"] - prev_close).abs(),  # Gap from yesterday's close (down)
        ],
        axis=1,
    ).max(axis=1)


# ============================================================================
# AVERAGE TRUE RANGE (ATR)
# ============================================================================


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (ATR).

    ATR is simply an EMA of True Range. It smooths out the volatility
    measurement to give us a single number representing typical movement.

    Think of ATR as "average volatility" - how much does this stock
    typically move in a period?

    Args:
        df: DataFrame with columns 'High', 'Low', 'Close'
        period: Lookback period (default: 14)

    Returns:
        Series with ATR values

    Example:
        >>> df = pd.DataFrame({
        ...     'High': [105, 107, 106, 108, 110],
        ...     'Low': [98, 100, 99, 102, 104],
        ...     'Close': [103, 104, 102, 106, 107]
        ... })
        >>> atr14 = atr(df, 14)

    Trading Uses:
        - Stop Loss: Set stop at entry ± (1.5 × ATR)
        - Position Sizing: Risk $100 / (1.5 × ATR) = number of shares
        - Strategy Filtering: Only trade when ATR > minimum threshold

    Beginner Note:
        A stock with ATR of 5 moves more than a stock with ATR of 2.
        You might set stops at 1.5× ATR for both, but in dollar terms
        the higher-volatility stock gets a wider stop.
    """
    return true_range(df).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


# ============================================================================
# VOLUME-BASED INDICATORS
# ============================================================================


def volume_ratio(volume: pd.Series, bar_no: pd.Series, lookback: int = 20) -> pd.Series:
    """
    Calculate volume ratio compared to same-bar historical average.

    This compares today's volume to the average volume for this SAME bar number
    over the past 'lookback' days.

    Example: Today's 10th bar (10:15 AM) volume vs the average 10th bar volume
    over the past 20 days.

    Why same-bar comparison?
        Volume has patterns. There's usually a rush at open, a lull mid-day,
        and activity at close. Comparing same-bar volumes removes these
        patterns and shows if today is truly unusual.

    Args:
        volume: Volume series
        bar_no: Bar number within the day (0-74 for 5-min bars)
        lookback: Number of days to average (default: 20)

    Returns:
        Series with volume ratios (>1 = above average, <1 = below average)

    Example:
        >>> vol_ratio = volume_ratio(df['Volume'], df['bar_no'], 20)
        >>> # vol_ratio = 1.5 means 50% more volume than typical for this bar
    """
    # Calculate average volume for each bar number
    vol_avg = volume.groupby(bar_no).transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=5).mean()
    )
    return volume / vol_avg


# ============================================================================
# SIMPLE PRICE MOVEMENTS
# ============================================================================


def prev_close(close: pd.Series) -> pd.Series:
    """
    Get previous bar's close price.

    Simple but useful for detecting price changes between bars.

    Args:
        close: Closing prices

    Returns:
        Series with previous close (first value will be NaN)

    Example:
        >>> close = pd.Series([100, 102, 101, 103])
        >>> prev_close(close)
        0      NaN
        1    100.0
        2    102.0
        3    101.0
    """
    return close.shift(1)
