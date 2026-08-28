"""
Data Loading Module.

This module handles reading CSV files and preparing the raw data.
It's the "gatekeeper" that makes sure we have clean, valid data
to work with.

Beginner Note:
    Before you can run any trading strategy, you need data.
    This module reads price data from CSV files and:
    1. Filters out junk (non-trading hours, bad days)
    2. Adds basic info (date, time, bar numbers)
    3. Returns clean data ready for analysis
"""

import pandas as pd

from .config import BARS_PER_DAY, DEFAULT_DATA_PATH, MARKET_CLOSE, MARKET_OPEN

# ============================================================================
# DATA LOADING
# ============================================================================


def load_regular_session(path=DEFAULT_DATA_PATH) -> pd.DataFrame:
    """
    Load price data and keep only regular trading hours.

    This function:
    1. Reads the CSV file
    2. Sorts by time
    3. Adds date and time columns
    4. Filters to regular session only (9:15 AM - 3:25 PM)
    5. Keeps only complete trading days (75 bars)
    6. Adds bar number (0-74) within each day

    Args:
        path: Path to CSV file (default: CGPOWER 5-min data)

    Returns:
        DataFrame with columns: Datetime, Open, High, Low, Close, Volume, ADX, date, time, bar_no

    Example:
        >>> df = load_regular_session("Data/CGPOWER/CGPOWER_5MIN.csv")
        >>> print(f"Loaded {len(df)} bars across {df['date'].nunique()} days")

    Why filter to regular session?
        - Pre-market and post-market have different behavior
        - Lower liquidity outside regular hours
        - Can skew indicator calculations

    Why require exactly 75 bars per day?
        - Incomplete days (holidays, early closes) can distort indicators
        - VWAP and EMAs assume consistent data
        - Cleaner backtests = more reliable results
    """
    # Read CSV
    raw = pd.read_csv(path, parse_dates=["Datetime"])

    # Sort by time (oldest first)
    raw = raw.sort_values("Datetime").reset_index(drop=True)

    # Extract date and time as separate columns
    raw["date"] = raw["Datetime"].dt.date.astype(str)  # "2024-06-11"
    raw["time"] = raw["Datetime"].dt.strftime("%H:%M")  # "09:15"

    # Filter to regular trading hours only
    regular = raw[(raw["time"] >= MARKET_OPEN) & (raw["time"] <= MARKET_CLOSE)].copy()

    # Find days with exactly 75 bars (complete trading days)
    day_counts = regular.groupby("date").size()
    complete_days = day_counts[day_counts == BARS_PER_DAY].index

    # Keep only complete days
    df = regular[regular["date"].isin(complete_days)].copy().reset_index(drop=True)

    # Add bar number within each day (0 = first bar, 74 = last bar)
    df["bar_no"] = df.groupby("date").cumcount()

    return df


def load_data_for_strategy(path=DEFAULT_DATA_PATH) -> pd.DataFrame:
    """
    Convenience function: load data with basic validation.

    Same as load_regular_session but with extra checks for common issues.

    Args:
        path: Path to CSV file

    Returns:
        Clean DataFrame ready for feature engineering

    Raises:
        FileNotFoundError: If CSV doesn't exist
        ValueError: If data is empty or has wrong format
    """
    df = load_regular_session(path)

    # Validation
    required_columns = ["Datetime", "Open", "High", "Low", "Close", "Volume", "ADX"]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if df.empty:
        raise ValueError(f"No data found in {path}")

    return df


# ============================================================================
# DATA SUMMARY
# ============================================================================


def get_data_summary(df: pd.DataFrame) -> dict:
    """
    Get a quick summary of loaded data.

    Args:
        df: DataFrame from load_regular_session

    Returns:
        Dictionary with data statistics

    Example:
        >>> df = load_regular_session()
        >>> summary = get_data_summary(df)
        >>> print(f"Date range: {summary['start_date']} to {summary['end_date']}")
        >>> print(f"Total bars: {summary['total_bars']}")
        >>> print(f"Trading days: {summary['trading_days']}")
    """
    return {
        "total_bars": len(df),
        "trading_days": int(df["date"].nunique()),
        "start_date": str(df["Datetime"].min()),
        "end_date": str(df["Datetime"].max()),
        "start_price": float(df.iloc[0]["Close"]),
        "end_price": float(df.iloc[-1]["Close"]),
        "avg_volume": int(df["Volume"].mean()),
    }
