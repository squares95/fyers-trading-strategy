"""
Signal Strength Scorer Module.

This module calculates a "strength score" (0-100) for each signal.
The score tells us how confident we should be in the trade.

Beginner Note:
    Not all signals are equal. Some signals are "A+" trades:
    - Strong trend
    - High volume
    - Clear pullback
    - Good location relative to VWAP

    Others are "C-" trades that might work but are weaker.

    This module calculates a score (0-100) for each signal so we
    can filter for the BEST opportunities only.
"""

import numpy as np
import pandas as pd

from .config import StrategyConfig

# ============================================================================
# SCORING CONFIGURATION
# ============================================================================

# Weights for each component (must sum to 1.0)
# - adx: Trend strength (higher ADX = stronger trend)
# - volume: Participation (higher volume = more conviction)
# - ema_alignment: Trend clarity (how well EMAs are aligned)
# - vwap_distance: Location quality (optimal distance from VWAP)
# - trigger_quality: Pullback quality (clear pullback that recovers)
SIGNAL_STRENGTH_WEIGHTS = {
    "adx": 0.22,
    "volume": 0.28,
    "ema_alignment": 0.18,
    "vwap_distance": 0.12,
    "trigger_quality": 0.20,
}

# How much each component can contribute (scales)
SIGNAL_STRENGTH_SCALES = {
    "adx_points_above_min": 18.0,
    "volume_ratio_above_min": 1.5,
    "ema_alignment_pct": 0.010,
    "vwap_distance_pct": 0.006,
    "trigger_atr_fraction": 0.35,
}

# Score thresholds
MIN_SIGNAL_STRENGTH = 40.0  # Minimum overall score to take a trade

MIN_TRIGGER_COMPONENT = 0.15  # Minimum trigger quality component (0-1)

# Bands for categorizing strength
STRENGTH_BINS = [0.0, 40.0, 50.0, 60.0, 70.0, 80.0, 100.0001]
STRENGTH_LABELS = ["<40", "40-50", "50-60", "60-70", "70-80", "80+"]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def clip01(values):
    """
    Clip values to range [0, 1].

    Used to normalize scoring components to a consistent range.

    Args:
        values: Numpy array or similar

    Returns:
        Array with values clipped to [0, 1]
    """
    return np.clip(np.asarray(values, dtype=float), 0.0, 1.0)


# ============================================================================
# MAIN SCORING FUNCTION
# ============================================================================


def signal_strength_table(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    config: StrategyConfig = None,
) -> pd.DataFrame:
    """
    Calculate signal strength scores (0-100) for each signal.

    This function calculates 5 components, each normalized to [0, 1]:
        1. ADX strength (trend strength)
        2. Volume strength (participation)
        3. EMA alignment (trend clarity)
        4. VWAP distance (location)
        5. Trigger quality (pullback quality)

    Then combines them using weights to get final score 0-100.

    Args:
        df: DataFrame with features (from prepare_features)
        signals: DataFrame of signals (from generate_signals)
        config: Strategy parameters (optional)

    Returns:
        Input signals DataFrame with added columns:
            - strength_adx_component: 0-1
            - strength_volume_component: 0-1
            - strength_ema_component: 0-1
            - strength_vwap_component: 0-1
            - strength_trigger_component: 0-1
            - signal_strength: 0-100 (final score)
            - strength_band: "<40", "40-50", "50-60", "60-70", "70-80", "80+"

    Example:
        >>> df = prepare_features()
        >>> signals = generate_signals(df)
        >>> signals_scored = signal_strength_table(df, signals)
        >>> print(signals_scored[['date', 'signal_strength', 'strength_band']])

    Scoring Philosophy:
        - We want CONSISTENT good setups, not lucky ones
        - Multiple weak factors don't make a strong signal
        - Each component is necessary, not just nice-to-have
    """
    if config is None:
        config = StrategyConfig()

    if signals.empty:
        # Return empty DataFrame with all expected columns
        out = signals.copy()
        for col in [
            "strength_adx_component",
            "strength_volume_component",
            "strength_ema_component",
            "strength_vwap_component",
            "strength_trigger_component",
            "signal_strength",
            "strength_band",
        ]:
            out[col] = []
        return out

    out = signals.copy()

    # Get the signal bars (the bar where the signal triggered)
    rows = df.iloc[out["signal_index"].astype(int).to_numpy()].reset_index(drop=True)
    direction = out["direction"].astype(int).reset_index(drop=True).to_numpy()
    atr_values = rows["atr14"].astype(float).to_numpy()
    atr_values = np.where(atr_values > 0, atr_values, np.nan)

    # Component 1: ADX strength
    # Higher ADX above minimum = better
    adx_component = clip01(
        (rows["adx_for_signal"].astype(float).to_numpy() - config.adx_min)
        / SIGNAL_STRENGTH_SCALES["adx_points_above_min"]
    )

    # Component 2: Volume strength
    # Higher volume ratio above minimum = better
    volume_component = clip01(
        (rows["vol_ratio20"].astype(float).to_numpy() - config.volume_ratio_min)
        / SIGNAL_STRENGTH_SCALES["volume_ratio_above_min"]
    )

    # Component 3: EMA alignment
    # For longs: EMA21 / EMA55 - 1 (positive = bullish)
    # For shorts: EMA34 / EMA13 - 1 (positive = bearish)
    ema_long = (
        rows["ema21"].astype(float).to_numpy() / rows["ema55"].astype(float).to_numpy() - 1.0
    ) / SIGNAL_STRENGTH_SCALES["ema_alignment_pct"]
    ema_short = (
        rows["ema34"].astype(float).to_numpy() / rows["ema13"].astype(float).to_numpy() - 1.0
    ) / SIGNAL_STRENGTH_SCALES["ema_alignment_pct"]
    ema_component = clip01(np.where(direction == 1, ema_long, ema_short))

    # Component 4: VWAP distance
    # How far price is from VWAP (in the trade direction)
    vwap_long = (
        rows["Close"].astype(float).to_numpy() / rows["vwap"].astype(float).to_numpy() - 1.0
    ) / SIGNAL_STRENGTH_SCALES["vwap_distance_pct"]
    vwap_short = (
        rows["vwap"].astype(float).to_numpy() / rows["Close"].astype(float).to_numpy() - 1.0
    ) / SIGNAL_STRENGTH_SCALES["vwap_distance_pct"]
    vwap_component = clip01(np.where(direction == 1, vwap_long, vwap_short))

    # Component 5: Trigger quality (pullback depth)
    # How deep was the pullback relative to ATR?
    # Deeper pullback = better quality (more obvious support/resistance)
    trigger_long = (
        rows["Close"].astype(float).to_numpy()
        - np.maximum(
            rows["ema21"].astype(float).to_numpy(), rows["prev_close"].astype(float).to_numpy()
        )
    ) / atr_values
    trigger_short = (
        np.minimum(
            rows["ema13"].astype(float).to_numpy(), rows["prev_close"].astype(float).to_numpy()
        )
        - rows["Close"].astype(float).to_numpy()
    ) / atr_values
    trigger_component = clip01(
        np.where(direction == 1, trigger_long, trigger_short)
        / SIGNAL_STRENGTH_SCALES["trigger_atr_fraction"]
    )

    # Calculate final weighted score (0-100)
    score = 100 * (
        SIGNAL_STRENGTH_WEIGHTS["adx"] * adx_component
        + SIGNAL_STRENGTH_WEIGHTS["volume"] * volume_component
        + SIGNAL_STRENGTH_WEIGHTS["ema_alignment"] * ema_component
        + SIGNAL_STRENGTH_WEIGHTS["vwap_distance"] * vwap_component
        + SIGNAL_STRENGTH_WEIGHTS["trigger_quality"] * trigger_component
    )
    score = np.nan_to_num(score, nan=0.0, posinf=100.0, neginf=0.0)
    score = np.clip(score, 0.0, 100.0)

    # Add all component scores to output
    out["strength_adx_component"] = np.round(adx_component, 4)
    out["strength_volume_component"] = np.round(volume_component, 4)
    out["strength_ema_component"] = np.round(ema_component, 4)
    out["strength_vwap_component"] = np.round(vwap_component, 4)
    out["strength_trigger_component"] = np.round(trigger_component, 4)
    out["signal_strength"] = np.round(score, 2)

    # Categorize into bands
    out["strength_band"] = pd.cut(
        out["signal_strength"],
        bins=STRENGTH_BINS,
        labels=STRENGTH_LABELS,
        right=False,
        include_lowest=True,
    ).astype(str)

    return out


# ============================================================================
# FILTERING FUNCTIONS
# ============================================================================


def filter_by_strength(
    signals: pd.DataFrame,
    min_strength: float = MIN_SIGNAL_STRENGTH,
    min_trigger: float = MIN_TRIGGER_COMPONENT,
) -> pd.DataFrame:
    """
    Filter signals to only include strong ones.

    Args:
        signals: DataFrame from signal_strength_table()
        min_strength: Minimum overall strength (default: 40)
        min_trigger: Minimum trigger quality (default: 0.15)

    Returns:
        Filtered DataFrame

    Example:
        >>> signals = signal_strength_table(df, signals)
        >>> strong_signals = filter_by_strength(signals, min_strength=50)
    """
    if signals.empty:
        return signals

    return signals[
        (signals["signal_strength"] >= min_strength)
        & (signals["strength_trigger_component"] >= min_trigger)
    ].copy()


def attach_signal_strength(trades: pd.DataFrame, strength_signals: pd.DataFrame) -> pd.DataFrame:
    """
    Attach strength scores to trade results.

    This joins the strength data with the backtest results so you
    can see the strength of each traded signal.

    Args:
        trades: DataFrame from backtest()
        strength_signals: DataFrame from signal_strength_table()

    Returns:
        Trades DataFrame with strength columns added

    Example:
        >>> signals = signal_strength_table(df, signals)
        >>> trades = backtest(df, signals)
        >>> trades_with_strength = attach_signal_strength(trades, signals)
    """
    strength_cols = [
        "date",
        "signal_strength",
        "strength_band",
        "strength_adx_component",
        "strength_volume_component",
        "strength_ema_component",
        "strength_vwap_component",
        "strength_trigger_component",
    ]

    if trades.empty:
        out = trades.copy()
        for col in strength_cols:
            if col not in out.columns:
                out[col] = []
        return out

    return trades.merge(strength_signals[strength_cols], on="date", how="left")
