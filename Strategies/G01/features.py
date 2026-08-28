"""
Feature Engineering Module.

This module takes raw price data and calculates all the technical indicators
needed for the strategy. Think of it as the "preparation" step before
running the strategy.

Beginner Note:
    Raw price data isn't enough to make trading decisions.
    We need to calculate indicators like:
        - Moving averages (EMA)
        - Momentum (RSI)
        - Volatility (ATR)
        - Trend strength (ADX)

    This module does all that in one go.
"""

import numpy as np
import pandas as pd

from .config import DEFAULT_DATA_PATH
from .data import load_regular_session
from .indicators import atr, ema, prev_close, rsi

# ============================================================================
# FEATURE CALCULATION
# ============================================================================


def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all technical indicators for the strategy.

    This function adds the following columns to the DataFrame:
        - vwap: Volume-Weighted Average Price
        - ema13, ema21, ema34, ema55: Exponential Moving Averages
        - rsi14: Relative Strength Index
        - atr14: Average True Range
        - adx_for_signal: Directional Movement Index (for trend strength)
        - vol_avg20_samebar: Average volume for this bar
        - vol_ratio20: Volume ratio (current / average)
        - prev_close: Previous bar's close

    Args:
        df: DataFrame from load_regular_session() with columns:
            Open, High, Low, Close, Volume, ADX

    Returns:
        Same DataFrame with all features added

    Example:
        >>> df = load_regular_session()
        >>> df = calculate_features(df)
        >>> print(df[['Close', 'vwap', 'ema21', 'rsi14', 'atr14']].head())

    Why each indicator?
        - vwap: Fair price measure, used for direction
        - ema13/21/34/55: Trend detection
        - rsi14: Momentum/overbought-oversold
        - atr14: Volatility for stops
        - adx: Trend strength confirmation
        - vol_ratio20: Volume confirmation
        - prev_close: Price momentum
    """
    df = df.copy()

    # --- VWAP (Volume-Weighted Average Price) ---
    # VWAP = Running sum of (Price × Volume) / Running sum of Volume
    # This gives us the "average price weighted by volume"
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    df["vwap"] = (typical * df["Volume"]).groupby(df["date"]).cumsum() / df["Volume"].groupby(
        df["date"]
    ).cumsum()

    # --- EMAs (Exponential Moving Averages) ---
    # EMA gives more weight to recent prices
    for span in (13, 21, 34, 55):
        df[f"ema{span}"] = ema(df["Close"], span)

    # --- RSI (Relative Strength Index) ---
    df["rsi14"] = rsi(df["Close"], 14)

    # --- ATR (Average True Range) ---
    df["atr14"] = atr(df, 14)

    # --- ADX for signals ---
    # ADX might already be in the CSV, if not use NaN
    df["adx_for_signal"] = df["ADX"] if "ADX" in df.columns else np.nan

    # --- Volume analysis ---
    # Compare today's volume to average volume at the SAME bar of day
    df["vol_avg20_samebar"] = df.groupby("bar_no")["Volume"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=5).mean()
    )
    df["vol_ratio20"] = df["Volume"] / df["vol_avg20_samebar"]

    # --- Previous close ---
    df["prev_close"] = prev_close(df["Close"])

    return df


# ============================================================================
# DATA PREPARATION PIPELINE
# ============================================================================


def prepare_features(path=DEFAULT_DATA_PATH) -> pd.DataFrame:
    """
    Complete pipeline: Load data → Calculate features.

    This is the main entry point. One function does everything:
    1. Load clean 5-min data
    2. Calculate all technical indicators
    3. Return ready-to-use DataFrame

    Args:
        path: Path to CSV file (default: CGPOWER 5-min data)

    Returns:
        DataFrame with all features ready for signal generation

    Example:
        >>> df = prepare_features()
        >>> print(f"Ready: {len(df)} bars with features")
        >>> print(df.columns.tolist())
        ['Datetime', 'Open', 'High', 'Low', 'Close', 'Volume', 'ADX',
         'date', 'time', 'bar_no', 'vwap', 'ema13', 'ema21', 'ema34',
         'ema55', 'rsi14', 'atr14', 'adx_for_signal',
         'vol_avg20_samebar', 'vol_ratio20', 'prev_close']

    Note:
        This is what most other modules call before generating signals
        or running backtests.
    """
    df = load_regular_session(path)
    df = calculate_features(df)
    return df


# ============================================================================
# FEATURE DESCRIPTIONS
# ============================================================================

FEATURE_DESCRIPTIONS = {
    "vwap": "Volume-Weighted Average Price. Fair value considering volume.",
    "ema13": "13-period EMA. Fast trend line.",
    "ema21": "21-period EMA. Medium-term trend.",
    "ema34": "34-period EMA. Slower trend.",
    "ema55": "55-period EMA. Long-term trend.",
    "rsi14": "Relative Strength Index. Momentum 0-100.",
    "atr14": "Average True Range. Volatility measure.",
    "adx_for_signal": "Average Directional Index. Trend strength 0-100.",
    "vol_ratio20": "Volume ratio vs same-bar average. >1 means above average.",
    "prev_close": "Previous bar's close. For momentum detection.",
}
"""
Dictionary of feature descriptions.

Use this for documentation or dynamic labeling.
"""
