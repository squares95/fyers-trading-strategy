"""
Core Module - Main Orchestrator.

This is the main entry point for the base trading strategy.
It re-exports all the modular components for easy access.

Beginner Note:
    Think of this as the "menu" or "index" of the strategy.
    All the actual code is in separate modules:
        - config.py: Settings
        - indicators.py: Technical indicators
        - data.py: Data loading
        - features.py: Feature engineering
        - signal_rules.py: Entry conditions
        - signals.py: Signal generation
        - backtest.py: Trade simulation
        - stats.py: Performance metrics

    This file just makes everything available in one place.

Usage:
    >>> from Core import StrategyConfig, prepare_features, generate_signals, backtest
    >>> df = prepare_features()
    >>> signals = generate_signals(df)
    >>> trades = backtest(df, signals)
"""

# Re-export from config
from .config import (
    DEFAULT_DATA_PATH,
    ROOT,
    MARKET_OPEN,
    MARKET_CLOSE,
    BARS_PER_DAY,
    StrategyConfig,
    DEFAULT_CONFIG,
)

# Re-export from indicators
from .indicators import (
    ema,
    rsi,
    true_range,
    atr,
    volume_ratio,
    prev_close,
)

# Re-export from data
from .data import (
    load_regular_session,
    load_data_for_strategy,
    get_data_summary,
)

# Re-export from features
from .features import (
    calculate_features,
    prepare_features,
    FEATURE_DESCRIPTIONS,
)

# Re-export from signal_rules
from .signal_rules import (
    long_entry_condition,
    short_entry_condition,
    select_first_signal_per_day,
)

# Re-export from signals
from .signals import (
    generate_signals,
    get_signal_stats,
)

# Re-export from backtest
from .backtest import (
    backtest,
    simulate_single_trade,
    calculate_performance_metrics,
)

# Re-export from stats
from .stats import (
    summarize_trades,
    analyze_by_direction,
    analyze_by_period,
    analyze_exit_reasons,
)


# ============================================================================
# COMPLETE PIPELINE
# ============================================================================

def run_strategy(path=DEFAULT_DATA_PATH) -> tuple:
    """
    Run the complete strategy pipeline.

    This is the "one-liner" that does everything:
    1. Load data
    2. Calculate features
    3. Generate signals
    4. Run backtest

    Args:
        path: Path to CSV data file

    Returns:
        Tuple of (df, signals, trades)
        - df: DataFrame with features
        - signals: DataFrame of entry signals
        - trades: DataFrame of backtest results

    Example:
        >>> df, signals, trades = run_strategy()
        >>> print(f"Generated {len(signals)} signals")
        >>> print(f"Backtested {len(trades)} trades")
    """
    from .features import prepare_features
    from .signals import generate_signals
    from .backtest import backtest

    df = prepare_features(path)
    signals = generate_signals(df)
    trades = backtest(df, signals)
    return df, signals, trades


# ============================================================================
# PUBLIC API
# ============================================================================

__all__ = [
    # Config
    "DEFAULT_DATA_PATH",
    "ROOT",
    "MARKET_OPEN",
    "MARKET_CLOSE",
    "BARS_PER_DAY",
    "StrategyConfig",
    "DEFAULT_CONFIG",

    # Indicators
    "ema",
    "rsi",
    "true_range",
    "atr",
    "volume_ratio",
    "prev_close",

    # Data
    "load_regular_session",
    "load_data_for_strategy",
    "get_data_summary",

    # Features
    "calculate_features",
    "prepare_features",
    "FEATURE_DESCRIPTIONS",

    # Signal Rules
    "long_entry_condition",
    "short_entry_condition",
    "select_first_signal_per_day",

    # Signals
    "generate_signals",
    "get_signal_stats",

    # Backtest
    "backtest",
    "simulate_single_trade",
    "calculate_performance_metrics",

    # Stats
    "summarize_trades",
    "analyze_by_direction",
    "analyze_by_period",
    "analyze_exit_reasons",

    # Pipeline
    "run_strategy",
]


# ============================================================================
# COMMAND-LINE INTERFACE
# ============================================================================

if __name__ == "__main__":
    """
    Quick smoke test when run directly:
        python Core.py

    This will:
    1. Run the full pipeline
    2. Print summary statistics
    """
    print("Running strategy pipeline...")
    df, signals_df, trades_df = run_strategy()
    print(f"signals={len(signals_df)} trades={len(trades_df)}")
    print(summarize_trades(trades_df))
