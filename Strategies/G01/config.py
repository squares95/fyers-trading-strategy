"""
Configuration Module.

This module contains all the "knobs" you can tune for the strategy.
Having these in one place makes it easy to experiment and backtest
different parameter values.

Beginner Note:
    Think of this like the "settings" or "preferences" of the strategy.
    All the magic numbers are here, so you can change them without
    touching the trading logic.
"""

from dataclasses import dataclass
from pathlib import Path


# ============================================================================
# TRADING SESSION CONSTANTS
# ============================================================================

# These define what counts as "regular trading hours"
# Anything outside this is pre-market, post-market, or off-hours

MARKET_OPEN = "09:15"
"""
First bar of regular trading session.
Format: "HH:MM" in 24-hour format (IST).
"""

MARKET_CLOSE = "15:25"
"""
Last bar of regular trading session.
We use 15:25 instead of 15:30 to leave time for orderly exits.
Format: "HH:MM" in 24-hour format (IST).
"""

BARS_PER_DAY = 75
"""
Expected number of 5-minute bars per trading day.

Calculation:
    9:15 AM to 3:25 PM = 6 hours 10 minutes = 370 minutes
    370 minutes / 5 minutes per bar = 74 bars

We use 75 to have a small buffer for edge cases.
"""

# Path to project root (two levels up from this file)
ROOT = Path(__file__).resolve().parents[2]

# Default data path
DEFAULT_DATA_PATH = ROOT / "Data" / "CGPOWER" / "CGPOWER_5MIN.csv"


# ============================================================================
# STRATEGY CONFIGURATION DATACLASS
# ============================================================================

@dataclass(frozen=True)
class StrategyConfig:
    """
    All tunable parameters for the trading strategy.

    Using frozen=True makes this a "read-only" dataclass.
    This prevents accidental changes during backtesting which
    could lead to inconsistent results.

    Think of each field as a "knob" you can tune to optimize
    the strategy. Default values are starting points, not gospel!
    """

    # --- Transaction Costs ---
    cost_bps_per_side: float = 5.0
    """
    Cost per trade in basis points (bps).

    1 bp = 0.01%
    5 bps = 0.05%

    Components:
        - Brokerage: ~3 bps
        - Exchange fees: ~1.5 bps
        - STT, GST, stamp duty: ~0.5 bps

    Note: This is charged TWICE per trade (once for entry, once for exit).
    """

    # --- Stop Loss and Target ---
    stop_atr_multiple: float = 1.3
    """
    Stop loss distance in ATR multiples.

    Stop distance = entry_price - (1.3 × ATR)

    Examples:
        - ATR = 5.0, Stop distance = 6.5
        - ATR = 10.0, Stop distance = 13.0

    Higher values = wider stops = fewer stop-outs but bigger losses
    """

    target_r: float = 2.0
    """
    Target profit in terms of stop distance.

    Target = entry_price + (2.0 × stop_distance)

    Examples:
        - If stop distance = 6.5, target = entry + 13.0
        - 2.0R means: if we risk 1 unit, we expect to make 2 units

    This is a 2:1 risk-reward ratio.
    Higher values = bigger winners but lower win rate
    """

    # --- Trend Strength ---
    adx_min: float = 22.0
    """
    Minimum ADX value for valid signals.

    ADX measures TREND STRENGTH (not direction).

    ADX Values:
        - < 20: Weak trend / ranging market
        - 20-40: Moderate trend
        - 40-60: Strong trend
        - > 60: Very strong trend

    Higher values = stricter filtering = fewer but better signals
    """

    # --- Volume Confirmation ---
    volume_ratio_min: float = 1.0
    """
    Minimum volume ratio for valid signals.

    Volume ratio = Today's volume / Average volume for this bar

    Examples:
        - 1.0 = Average volume (minimum)
        - 1.5 = 50% above average (strong)
        - 2.0 = Double average (very strong)

    Higher values = stricter filtering = only trade high-volume days
    """

    # --- RSI Filters ---
    long_rsi_min: float = 50.0
    """
    Minimum RSI for long signals.

    RSI ranges 0-100:
        - > 70: Overbought (too high)
        - 50: Neutral
        - < 30: Oversold (too low)

    We want RSI between 50-75 for longs (not too extended)
    """

    long_rsi_max: float = 75.0
    """
    Maximum RSI for long signals.
    Prevents entering when stock is already overbought.
    """

    short_rsi_min: float = 28.0
    """
    Minimum RSI for short signals.

    For shorts, we invert the logic:
        - RSI < 30 is oversold (not good for shorts)
        - RSI > 70 is overbought (good for shorts)

    short_rsi_min = 28 is close to oversold territory
    """

    short_rsi_max: float = 55.0
    """
    Maximum RSI for short signals.

    Keeps us from shorting stocks that are too extended already.
    """

    # --- Time Windows ---
    long_first_bar: int = 8
    """
    First bar number for long signals (0-indexed).

    Bar 8 = 9:15 + (8 × 5 min) = 9:55 AM

    Reason: Skip the chaotic opening period.
    """

    long_last_signal_bar_exclusive: int = 60
    """
    Last bar number for long signals (exclusive).

    Bar 60 = 9:15 + (60 × 5 min) = 2:15 PM

    Reason: Leave time for trade to work out before close.
    """

    short_first_bar: int = 8
    """
    First bar number for short signals.

    Same as longs - skip opening chaos.
    """

    short_last_signal_bar_exclusive: int = 50
    """
    Last bar number for short signals (exclusive).

    Bar 50 = 9:15 + (50 × 5 min) = 1:25 PM

    Note: Shorts exit earlier than longs (50 vs 60).

    Why? Because:
        1. Short squeezes can be violent
        2. Overnight gap-ups can cause big losses
        3. Less time for the trade to work = less risk
    """

    # --- Gap Filter (Exp 6 — News/Sentiment Regime) ---
    gap_threshold: float = 0.025
    """
    Skip signals on days where any portfolio stock gapped more than this %.

    Validated in Exp 6A-6E (Aug 2026): 2.5% gap filter improves risk-adjusted
    returns on full 7-stock OOS portfolio:
        - Net: +48.0% (essentially equal to +48.56% baseline)
        - PF: 2.872 vs 2.359 (+22% better)
        - DD: -4.44% vs -5.76% (23% shallower)
        - Trades: 105 vs 132 (-20% overtrading)

    Why it works: gap days (overnight news shocks) produce whipsaw intraday
    moves that hurt technical-signal strategies. Skipping them removes the
    chaos while preserving the actual trend edge.

    Set to 1.0 (or higher) to disable the filter effectively.
    Set to 0.025 for the validated 2.5% threshold.
    """


# ============================================================================
# DEFAULT CONFIGURATION
# ============================================================================

# A "default" config object you can use for quick testing
# This makes it easy to pass to functions without specifying every parameter
DEFAULT_CONFIG = StrategyConfig()
