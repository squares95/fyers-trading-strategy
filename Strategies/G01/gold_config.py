"""
Gold Strategy Configuration Module.

This module contains the "Gold" version of the strategy - an enhanced
configuration that's more selective and profitable than the base.

Beginner Note:
    The "Gold" version is a better-tuned configuration of the base strategy:
    - Stricter entry conditions
    - Better stop/target ratios
    - Regime filter (only trade good days)
    - Signal strength scoring (only take A+ setups)

    It's the difference between "trading every day" and "trading the BEST
    opportunities".
"""

from pathlib import Path

# Path setup
ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "Data" / "CGPOWER" / "CGPOWER_5MIN.csv"
OUTPUT_DIR = ROOT / "Research" / "G01"

# Training cutoff for backtest validation
TRAIN_CUTOFF = "2025-01-01"
"""
Train on data before this date, validate on data after.
Used to prevent overfitting.
"""


# ============================================================================
# GOLD STRATEGY CONFIGURATION
# ============================================================================


def get_gold_config():
    """
    Get the Gold strategy configuration (from base StrategyConfig).

    These parameters are optimized based on extensive backtesting.
    The Gold config is stricter than the default, which means:
    - Fewer signals (higher quality)
    - Better win rate
    - Lower drawdown
    - Higher profit factor

    Returns:
        StrategyConfig object with Gold parameters
    """
    from .config import StrategyConfig

    return StrategyConfig(
        # Stricter ADX requirement (26 vs 22)
        adx_min=26.0,
        # Higher volume requirement (1.2 vs 1.0)
        volume_ratio_min=1.2,
        # Stop and target
        stop_atr_multiple=1.3,
        target_r=2.0,
        # RSI ranges (similar to base)
        long_rsi_min=50.0,
        long_rsi_max=75.0,
        short_rsi_min=28.0,
        short_rsi_max=55.0,
        # Time windows
        long_first_bar=8,
        long_last_signal_bar_exclusive=60,
        short_first_bar=8,
        short_last_signal_bar_exclusive=45,  # Shorts exit earlier
        # Cost
        cost_bps_per_side=5.0,
    )


def get_super_gold_config():
    """
    Get the SUPER GOLD configuration (wildly optimized).

    Based on wild_experiments_gold.py results, this config:
    - Uses 1:3 risk-reward ratio (stop=1.3, target=3.9)
    - Requires ADX >= 32 (only strong trends)
    - Requires volume >= 2.0 (high participation)
    - Achieves 47.93% net return with 1.664 PF on CGPOWER

    Returns:
        StrategyConfig object with Super Gold parameters
    """
    from .config import StrategyConfig

    return StrategyConfig(
        # Best from experiments: st=1.3, t=3.9
        stop_atr_multiple=1.3,
        target_r=3.9,  # 1:3 ratio
        # High ADX for best PF (1.704)
        adx_min=32.0,
        # High volume for best PF (1.834)
        volume_ratio_min=2.0,
        # Standard RSI ranges
        long_rsi_min=50.0,
        long_rsi_max=75.0,
        short_rsi_min=28.0,
        short_rsi_max=55.0,
        # Time windows
        long_first_bar=8,
        long_last_signal_bar_exclusive=60,
        short_first_bar=8,
        short_last_signal_bar_exclusive=45,
        # Cost
        cost_bps_per_side=5.0,
    )


def get_shorts_only_config():
    """
    Get the SHORTS-ONLY configuration (best PF with low DD).

    This config disables longs and only trades shorts:
    - PF: 1.724
    - Max DD: -4.09%
    - Win rate: 51.8%

    Great for risk-averse traders.

    Returns:
        StrategyConfig object with shorts-only parameters
    """
    from .config import StrategyConfig

    return StrategyConfig(
        # Disables longs by setting RSI range to invalid
        long_rsi_min=100,
        long_rsi_max=0,
        # Shorts use normal parameters
        short_rsi_min=28.0,
        short_rsi_max=55.0,
        # Standard other parameters
        adx_min=26.0,
        volume_ratio_min=1.2,
        stop_atr_multiple=1.3,
        target_r=2.0,
        # Time windows
        long_first_bar=8,
        long_last_signal_bar_exclusive=60,
        short_first_bar=8,
        short_last_signal_bar_exclusive=45,
        # Cost
        cost_bps_per_side=5.0,
    )
