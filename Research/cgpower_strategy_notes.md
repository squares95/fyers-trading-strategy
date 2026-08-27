# CGPOWER 5-Min Strategy Research Notes

Source: `Data/CGPOWER/CGPOWER_5MIN.csv`

Rows used: 36,375 regular-session candles across 485 complete trading days.
Excluded: special/partial sessions with non-standard bar counts.
Backtest assumption: signal on candle close, entry at next 5-minute candle open, stop/target checked intrabar, same-bar stop and target resolved conservatively as stop first, no overnight carry, 5 bps cost per side.

Executable strategy module: `Strategies/G01/Core.py`
Robustness checker: `Research/cgpower_strategy_robustness.py`

## Best Tradeable Idea

Use a VWAP + EMA trend-pullback continuation model, one earliest signal per day.

### Long Leg

- Signal window: bar 8 to bar 59, approximately 09:55 to 14:10 signal close.
- Trend: close above intraday VWAP.
- EMA regime: EMA21 greater than EMA55.
- Strength: ADX >= 22.
- Volume: current volume >= 20-day average volume for the same intraday bar.
- Momentum: RSI14 between 50 and 75.
- Pullback: candle low touches EMA21 or VWAP.
- Recovery trigger: candle closes above EMA21 and above previous close.
- Entry: next candle open.
- Stop: entry - 1.3 * ATR14.
- Target: entry + 2.0R.

### Short Leg

- Signal window: bar 8 to bar 49, approximately 09:55 to 13:20 signal close.
- Trend: close below intraday VWAP.
- EMA regime: EMA13 less than EMA34.
- Strength: ADX >= 22.
- Volume: current volume >= 20-day average volume for the same intraday bar.
- Momentum: RSI14 between 28 and 55.
- Pullback: candle high touches EMA13 or VWAP.
- Recovery trigger: candle closes below EMA13 and below previous close.
- Entry: next candle open.
- Stop: entry + 1.3 * ATR14.
- Target: entry - 2.0R.

If both legs signal on the same day, take only the first valid signal by entry time.

## Backtest Summary

Baseline friction: 5 bps per side, 10 bps round trip.

| Period | Trades | Net return | Avg/trade | Win rate | Profit factor | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full sample | 190 | 29.50% | 13.93 bps | 50.00% | 1.515 | -4.30% |
| Train to 2025-09-16 | 122 | 15.95% | 12.46 bps | 50.00% | 1.444 | -4.30% |
| Validation after 2025-09-16 | 68 | 11.69% | 16.55 bps | 50.00% | 1.656 | -2.37% |

Cost stress:

| Cost per side | Net return | Profit factor | Max DD |
|---:|---:|---:|---:|
| 0 bps | 56.55% | 2.084 | -2.47% |
| 3 bps | 39.71% | 1.716 | -3.22% |
| 5 bps | 29.50% | 1.515 | -4.30% |
| 8 bps | 15.56% | 1.263 | -6.46% |
| 10 bps | 7.11% | 1.122 | -7.95% |
| 12 bps | -0.73% | 0.998 | -10.59% |

## Robustness Checks

The final rule was retested separately from the broad parameter search through `Strategies/G01/Core.py`; it reproduced 190 trades, 29.50% net return, and 1.515 profit factor.

| Check | Result |
|---|---:|
| Long leg | 95 trades, 11.23% net, PF 1.420 |
| Short leg | 95 trades, 16.43% net, PF 1.612 |
| Positive quarters | 7 of 9 |
| Positive months | 16 of 24 |
| Bootstrap probability net positive | 99.24% |
| Bootstrap probability PF > 1 | 99.36% |
| Same-day/same-direction random-entry net percentile | 91.8th |
| Same-day/same-direction random-entry PF percentile | 89.7th |
| Pullback variants profitable in train and validation | 377 of 2,592 |
| Strong pullback PF cluster | 11 variants |

## Research Takeaways

- CGPOWER has enough intraday movement: median day range was 2.83%, 75th percentile was 3.89%, and 90th percentile was 5.38%.
- Plain opening-range breakouts were not reliable by themselves. Breakout-to-close continuation was close to a coin flip, even with volume and ADX filters.
- VWAP reversion was consistently poor in this dataset.
- The stable edge came from trend-pullback continuation: wait for VWAP/EMA regime, demand ADX strength, require same-bar relative volume, then enter only after a pullback recovery.
- The strategy is friction-sensitive. It should not be traded if realized all-in cost plus slippage is consistently above about 10 bps per side.
- The random-entry control is important: random entries on the same dates and same long/short side were often mildly profitable because CGPOWER was volatile, but the selected trigger still ranked around the 90th percentile, meaning the timing rule added measurable edge beyond regime selection.
- Fundamental analysis was not included because the supplied file contains only intraday OHLCV and technical columns. Treat this as a technical/price-action strategy, not a fundamental model.
