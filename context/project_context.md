# Fyers Trading System - Project Context

## Purpose
A complete automated trading system for Indian equities that can **download**, **analyze**, **backtest**, and **papertrade** using Fyers API data.

## End Goal
Design a profitable trading strategy/setup to make substantial returns with controlled risk.

## Project Architecture

### 1. Data Layer
- **Data/Fyers**: Downloaded market data organized by symbol and timeframe (1MIN, 5MIN, 15MIN, 1D, 1W)
- **Download.py**: Fyers API integration for downloading historical data, resampling, adding technical indicators
- **TickData/**: Real-time tick-level data storage (JSONL format)

### 2. Strategy Layer (Strategies/G01)
- **Core.py**: Base strategy with signal generation and backtesting
  - EMA 13/21/34/55, RSI 14, ADX, VWAP, volume ratio calculations
  - Signal conditions for long/short entries
  - Stop-loss (1.3x ATR), target (2:1 R:R), EOD exit rules
- **Gold.py**: Enhanced strategy with:
  - Daily regime filtering (requires turnover > 1B and range > 2%)
  - Signal strength scoring (0-100 scale with 5 components)
  - Minimum thresholds: strength >= 40, trigger component >= 0.15

### 3. Research Layer
- **Research/cgpower_strategy_research.py**: Family search across 4 strategy types:
  1. Opening Range Breakout (OR-based)
  2. Donchian Breakout (momentum)
  3. VWAP-EMA Pullback (trend continuation)
  4. VWAP Reversion (mean reversion)
- Optimized with train/test split (65% train, 35% test)

### 4. Paper Trading
- **Paper/GoldPaperTrader.py**: Live paper trading engine
  - Manages real-time positions with stop/target/EOD exits
  - Tracks state in gold_paper_state.json
  - Logs trades, events, and generates Excel reports
  - Configurable: balance, leverage, brokerage, slippage

### 5. Live Tick Pipeline
- **LiveTick/**: Real-time data streaming from Fyers websockets
  - Candle building from ticks
  - CSV storage for persistence
  - Session management

## Current Strategy Performance (Gold Strategy on CGPOWER)
**Data**: 5-min candles, 2021-06 → 2026-05, 1230 trading days, 505 regime-tradeable days

### Overall Results (113 trades):
| Metric | Value |
|--------|-------|
| Net Return | +34.6% |
| Avg Trade | +26.75 bps |
| Win Rate | 58.41% |
| Profit Factor | 2.018 |
| Max Drawdown | -3.45% |
| Cost Stress (5bps): | +34.6% (viable) |
| Cost Stress (10bps): | +20.24% |
| Cost Stress (15bps): | +7.41% |

### Bootstrap Analysis (5000 simulations):
- 99.82% probability of net positive
- Median net: +34.63%, PF: 2.02
- P5 worst case: +15.01% net, 1.41 PF

### Signal Strength Breakdown:
| Band | Trades | Net % | Win % | PF |
|------|--------|-------|-------|-----|
| <40 | 14 | -0.21 | 42.86 | 0.966 |
| 40-50 | 19 | +3.12 | 52.63 | 1.644 |
| 50-60 | 36 | +7.05 | 61.11 | 1.839 |
| 60-70 | 21 | +1.89 | 52.38 | 1.318 |
| 70-80 | 19 | +6.24 | 52.63 | 1.984 |
| 80+ | 23 | +11.47 | 65.22 | 2.782 |

### Long vs Short:
- **Shorts**: 43 trades, +17.11% net, 65.12% win rate, PF 2.51
- **Longs**: 70 trades, +14.93% net, 54.29% win rate, PF 1.744

### Validation (Post-2025):
- 72 trades, +30.3% net, 65.28% win rate, PF 3.01

## Key Strategy Logic
**Setup**: VWAP-EMA Pullback (Long)
- ema13 > ema34 (bullish alignment)
- Price touches ema13 or VWAP (pullback)
- Price recovers above ema13
- ADX >= 22 (trend strength)
- RSI 50-75 (not overextended)
- Volume ratio >= 1.0 (participation)
- Entry: next bar open (1:1 R:R target at 1.6R)

## Available Symbols
- CGPOWER (primary research subject)
- HDFCBANK (secondary symbol with data)

## Next Steps
- Review research results to refine strategy parameters
- Consider expanding to more symbols for diversification
- Implement portfolio-level risk management
- Validate strategy robustness across different market conditions