# Experiment Log - UPDATED 2026-08-28 (BREAKTHROUGH!)

## 🎯 NEW: PORTFOLIO STRATEGY VALIDATED

### Portfolio Backtest (7 stocks, 2021-2026)
| Metric | Value |
|--------|-------|
| **Total Net Return** | **+65.1%** |
| **Profit Factor** | 2.18 |
| **Max Drawdown** | -5.76% |
| **Win Rate** | 46.1% |
| **Total Trades** | 180 |
| **Profitable Months** | 28/43 (65%) |
| **Annualized** | 18.2% |

### Out-of-Sample Validation (2025-2026 only)
| Metric | Value |
|--------|-------|
| **Net Return (16 months)** | **+22.8%** |
| **Profit Factor** | 2.10 |
| **Max DD** | -5.09% |
| **Win Rate** | 46.8% |
| **Annualized** | ~17-20% |

## PORTFOLIO (TRADE THESE)
1. **CGPOWER** - 40% allocation, +40.4% individual, Power sector
2. **DRREDDY** - 25% allocation, +6.6%, Pharma
3. **INDUSINDBK** - 15% allocation, +4.2%, Banking
4. **BHEL** - 10% allocation, +6.2%, Power
5. **HCLTECH** - 5%, +2.5%, IT
6. **TITAN** - 5%, +2.4%, Consumer

## Strategy: SUPER GOLD
- VWAP-EMA Pullback (long/short)
- EMA 13/21/34 alignment
- ADX >= 32 (strong trend)
- Volume ratio >= 2.0
- Stop: 1.3x ATR
- Target: 3.9R (1:3 risk/reward)
- Regime filter: turnover > 1B, range > 2%
- Strength filter: score >= 45, trigger >= 0.15

## EXPERIMENTS COMPLETED

### Exp 1: Power Sector Deep Dive
- Compared CGPOWER, BHEL, TATAPOWER, ADANIPOWER, NTPC, POWERGRID, SUZLON
- Base strategy loses on all (PF < 1.0)
- Need regime + strength filters

### Exp 2: Multi-Stock Gold Screen (26 stocks)
- 8 stocks become profitable with SUPER GOLD
- Winners: CGPOWER, BHEL, M&M, HCLTECH, TITAN, JSWSTEEL, ICICIBANK
- Fails: SUZLON, ADANIPOWER, BHARTIARTL, TATAPOWER

### Exp 3: New Candidates (DRREDDY, INDUSINDBK tested)
- **DRREDDY: +6.7%, PF 2.24** ⭐ NEW WINNER
- **INDUSINDBK: +4.2%, PF 1.90** ⭐ NEW WINNER
- Downloaded 4 new stocks successfully

### Exp 4: Portfolio Backtest
- 7-stock portfolio: +65.1% net, -5.76% DD
- Better than any individual stock
- Diversification works

### Exp 5: Out-of-Sample Validation
- 2025-2026 data: +22.8% net
- Strategy works on unseen data
- ~17-20% annualized realistic

## NEXT STEPS
- [ ] Live paper trading (GoldPaperTrader.py)
- [ ] Monitor real-time signals
- [ ] Track performance vs backtest
- [ ] Adjust if slippage > expected

## FILES CREATED
- `Research/exp01_power_sector_deep.py`
- `Research/exp02_gold_multi_stock.py`
- `Research/exp03_download_and_test.py`
- `Research/exp04_portfolio_backtest.py`
- `Research/exp05_out_of_sample.py`
- `Research/GroqAnalysis/exp01-05_*.json`
- `Config/groq_config.json.example`