"""
Daily Regime Filter Module.

This module determines if a trading day is "tradeable" based on
market conditions. It's like a "permission to trade" check.

Beginner Note:
    Not every day is good for trading. Some days have:
    - Low volume (choppy, hard to enter/exit)
    - Small price range (no opportunities)

    This module calculates daily metrics and decides if we should
    trade that day. It's the "bouncer at the club" that filters
    out bad trading days.
"""

import pandas as pd

# Regime thresholds
REGIME_TURNOVER_MIN = 1_000_000_000  # 1 billion (1B) - minimum daily turnover
"""
Minimum daily turnover (in rupees) for a day to be tradeable.

Turnover = Close Price × Daily Volume

Why 1B?
    - Ensures enough liquidity for entry/exit
    - Higher turnover = more participants = better fills
    - Avoids illiquid stocks that can move erratically
"""

REGIME_RANGE_MIN = 0.02  # 2% - minimum daily range
"""
Minimum daily range as percentage of open price.

Range = (High - Low) / Open

Why 2%?
    - Ensures enough movement to profit
    - Days with < 2% range are typically "dead" days
    - Provides room for stops and targets
"""


def daily_regime_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate daily regime metrics and identify tradeable days.

    This function aggregates 5-min data into daily metrics and
    determines which days are good for trading.

    Args:
        df: DataFrame with 5-min data (must have date, OHLC, Volume)

    Returns:
        DataFrame with one row per day containing:
            - date: Trading date
            - Open, High, Low, Close, Volume: Daily OHLC
            - turnover: Close × Volume
            - range_pct: (High - Low) / Open
            - turnover_med60_prev: 60-day median turnover (previous day)
            - range_med60_prev: 60-day median range (previous day)
            - regime_tradeable: True if day is tradeable

    Example:
        >>> df = prepare_features()
        >>> regime = daily_regime_table(df)
        >>> tradeable = regime[regime['regime_tradeable']]
        >>> print(f"Tradeable days: {len(tradeable)} / {len(regime)}")

    How it works:
        1. Aggregate 5-min bars into daily bars
        2. Calculate turnover and range
        3. Use ROLLING 60-day median (looking BACK 60 days)
        4. Compare current day to historical median
        5. If both turnover and range are above median → tradeable

    Why use rolling median?
        - Median is more robust to outliers than average
        - 60 days is enough to capture recent market character
        - "shift(1)" means we use data up to YESTERDAY, not including today
          (can't use today's data - we wouldn't know it yet in real-time)
    """
    # Step 1: Aggregate 5-min bars into daily bars
    daily = (
        df.groupby("date")
        .agg(
            Datetime=("Datetime", "last"),
            Open=("Open", "first"),
            High=("High", "max"),
            Low=("Low", "min"),
            Close=("Close", "last"),
            Volume=("Volume", "sum"),
        )
        .reset_index()
    )

    # Step 2: Calculate turnover and range
    daily["turnover"] = daily["Close"] * daily["Volume"]
    daily["range_pct"] = (daily["High"] - daily["Low"]) / daily["Open"]

    # Step 3: Calculate 60-day rolling median (shifted by 1 to avoid look-ahead)
    # min_periods=20 means we need at least 20 days of history
    daily["turnover_med60_prev"] = daily["turnover"].rolling(60, min_periods=20).median().shift(1)
    daily["range_med60_prev"] = daily["range_pct"].rolling(60, min_periods=20).median().shift(1)

    # Step 4: Mark tradeable days
    # A day is tradeable if BOTH conditions are met:
    # - Turnover is above 1 billion
    # - Daily range is above 2%
    daily["regime_tradeable"] = (
        (daily["turnover"] > REGIME_TURNOVER_MIN) &
        (daily["range_pct"] > REGIME_RANGE_MIN)
    )

    return daily


def get_tradeable_dates(df: pd.DataFrame) -> set:
    """
    Get a set of tradeable dates from the data.

    This is a convenience function that returns just the dates
    that pass the regime filter.

    Args:
        df: DataFrame with 5-min data

    Returns:
        Set of date strings that are tradeable

    Example:
        >>> df = prepare_features()
        >>> tradeable = get_tradeable_dates(df)
        >>> signals_filtered = signals[signals['date'].isin(tradeable)]
    """
    regime = daily_regime_table(df)
    return set(regime.loc[regime["regime_tradeable"], "date"])


def filter_signals_by_regime(
    signals: pd.DataFrame,
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Filter signals to only include those on tradeable days.

    Args:
        signals: DataFrame from generate_signals()
        df: DataFrame with 5-min data

    Returns:
        Filtered DataFrame with only tradeable day signals

    Example:
        >>> signals = generate_signals(df)
        >>> signals_filtered = filter_signals_by_regime(signals, df)
    """
    tradeable_dates = get_tradeable_dates(df)
    return signals[signals["date"].isin(tradeable_dates)].copy()
