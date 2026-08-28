# config.py

CONFIG = {
    "initial_capital": 100000,  # Starting money
    "sl_atr": 1.0,  # Stop-loss = 1x ATR
    "tp_atr": 3.0,  # Take-profit = 2x ATR
    "adx_threshold": 30,  # Only trade when ADX > this
    "position_size_pct": 0.1,  # Risk 10% of capital per trade
    "atr_period": 14,  # For ATR calculation if needed
    "verbose": False,
    "volatility_window": 20,
    "min_atr_factor": 1.0,
    "hours": ["14-15"],  # Print trades as they happen
}
