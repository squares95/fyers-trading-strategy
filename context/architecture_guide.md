# G01 Strategy - Code Architecture Guide

## Overview
This document shows the complete code architecture after refactoring.
Think of it as a "map" to navigate the codebase.

## New File Structure (Modular Design)

```
Strategies/G01/
├── __init__.py              # Package entry point
├── Core.py                  # Main orchestrator (thin, re-exports)
├── Gold.py                  # Gold strategy orchestrator (thin, re-exports)
│
├── config.py                # ⭐ All settings & parameters
├── indicators.py            # ⭐ Technical indicator math (EMA, RSI, ATR)
├── data.py                  # ⭐ Load CSV & filter to trading hours
├── features.py              # ⭐ Calculate all features from raw data
│
├── signal_rules.py          # ⭐ When to enter (long/short conditions)
├── signals.py               # ⭐ Generate complete signals with entry/stop/target
│
├── backtest.py              # ⭐ Simulate trades (entry → exit)
├── stats.py                 # ⭐ Performance metrics & analysis
│
├── regime_filter.py         # ⭐ Daily tradeability check (Gold feature)
├── strength_scorer.py       # ⭐ Signal quality scoring (Gold feature)
├── gold_config.py           # ⭐ Gold strategy parameters
│
└── Strategy.py              # High-level strategy interface
```

## Data Flow Diagram

```
┌─────────────┐
│  CSV File   │  (CGPOWER_5MIN.csv)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   data.py   │  load_regular_session()
│             │  - Filter trading hours
│             │  - Remove incomplete days
│             │  - Add bar numbers
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ features.py │  prepare_features()
│             │  - VWAP
│             │  - EMAs (13, 21, 34, 55)
│             │  - RSI (14)
│             │  - ATR (14)
│             │  - ADX, volume ratio
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ signal_rules.py │  long_entry_condition() + short_entry_condition()
│                 │  - Check all conditions
│                 │  - Return True/False masks
└──────┬──────────┘
       │
       ▼
┌─────────────┐
│ signals.py  │  generate_signals()
│             │  - Apply conditions
│             │  - Select first signal per day
│             │  - Calculate entry/stop/target
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ backtest.py │  backtest()
│             │  - Simulate each trade
│             │  - Check stop/target/EOD
│             │  - Calculate P&L
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  stats.py   │  summarize_trades()
│             │  - Net return
│             │  - Win rate
│             │  - Profit factor
│             │  - Drawdown
└─────────────┘
```

## Gold Strategy Flow (Enhanced)

```
Base Strategy + Gold Enhancements:

Base flow... (as above)
        +
        │
        ▼
┌──────────────────┐
│ regime_filter.py │  daily_regime_table()
│                  │  - Check turnover > 1B
│                  │  - Check range > 2%
│                  │  - Only trade good days
└────────┬─────────┘
         │
         ▼
┌─────────────────────┐
│ strength_scorer.py  │  signal_strength_table()
│                     │  - Score 0-100
│                     │  - 5 components
│                     │  - Filter < 40
└────────┬────────────┘
         │
         ▼
┌─────────────────┐
│    backtest.py  │  Run backtest
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Gold.py     │  run() - Generate all reports
└─────────────────┘
```

## Module Responsibilities (One-liner)

| Module | What it does | When to edit |
|--------|-------------|--------------|
| `config.py` | All strategy parameters | When tuning the strategy |
| `indicators.py` | Pure math indicators (EMA, RSI, ATR) | When adding new indicators |
| `data.py` | Load CSV files | When changing data sources |
| `features.py` | Calculate features from data | When adding new features |
| `signal_rules.py` | Entry conditions (long/short) | When changing strategy logic |
| `signals.py` | Generate complete signals | When changing signal format |
| `backtest.py` | Simulate trades | When changing execution rules |
| `stats.py` | Performance metrics | When adding new metrics |
| `regime_filter.py` | Daily tradeability | When changing regime rules |
| `strength_scorer.py` | Signal quality scoring | When changing scoring |
| `gold_config.py` | Gold parameters | When tuning Gold config |
| `Core.py` | Public API for base strategy | Rarely (re-exports only) |
| `Gold.py` | Public API for Gold strategy | Rarely (re-exports only) |

## Common Tasks & Where to Look

### "I want to change the stop loss"
→ Edit `config.py` → `stop_atr_multiple`

### "I want to add a new indicator"
→ Add function to `indicators.py`
→ Use it in `features.py`

### "I want to change entry conditions"
→ Edit `signal_rules.py` → `long_entry_condition()` or `short_entry_condition()`

### "I want to see performance stats"
→ Use `stats.py` → `summarize_trades()`

### "I want to backtest with different config"
→ Create new `StrategyConfig()` with different parameters

### "I want to add a new strength component"
→ Edit `strength_scorer.py` → `signal_strength_table()`

## Backwards Compatibility

✅ All existing imports still work:
```python
# These all still work (re-exported from Core.py)
from Strategies.G01.Core import (
    StrategyConfig, prepare_features, generate_signals,
    backtest, summarize_trades, run_strategy
)

# These all still work (re-exported from Gold.py)
from Strategies.G01.Gold import (
    GOLD_CONFIG, run, daily_regime_table, signal_strength_table
)
```

## Testing

Quick smoke test:
```python
from Strategies.G01 import Core
df, signals, trades = Core.run_strategy()
print(f"Trades: {len(trades)}")
```

Quick Gold test:
```python
from Strategies.G01 import Gold
results = Gold.run()
print(results['gold_strategy'])
```

## Benefits of This Structure

1. **Beginner-friendly**: Each file has one clear purpose
2. **Easy to find**: Module names describe what they do
3. **Easy to test**: Test each module in isolation
4. **Easy to extend**: Add new features without breaking existing code
5. **Well-documented**: Every function has detailed docstrings
6. **Type-safe**: Full type hints throughout
7. **Backwards compatible**: Existing imports still work

## Next Steps

- [ ] Add unit tests for each module
- [ ] Apply same pattern to GoldPaperTrader.py
- [ ] Create visualization tools
- [ ] Add multi-symbol support
- [ ] Build web dashboard for monitoring
