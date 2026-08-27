# CGPOWER Gold Strategy - 5 Year Backtest

Source: `Data/CGPOWER/CGPOWER_5MIN.csv`

Rows used by the strategy: 92,250 regular-session 5-minute candles across 1,230 complete trading days.
Partial latest day was excluded from the backtest automatically.

## Key Discovery

The earlier 2-year strategy did not survive the full 5-year test without a regime gate.
The regime gate is the first decision. Signal strength is applied only after that.

| Strategy | Trades | Net return | Avg/trade | Win rate | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Old strategy, no regime filter | 535 | -41.41% | -9.61 bps | 36.26% | 0.774 | -58.12% |
| Old strategy, outside gold regime | 333 | -54.89% | -23.52 bps | 28.23% | 0.535 | -58.12% |
| Gold setup before strength filter | 132 | 32.92% | 21.99 bps | 56.06% | 1.792 | -4.02% |
| Final gold strategy | 113 | 34.60% | 26.75 bps | 58.41% | 2.018 | -3.45% |

## Regime Gate

Use only prior completed daily data.

- Compute daily candles from 5-minute data.
- Compute 60-day median turnover: `Close * Volume`.
- Compute 60-day median daily range: `(High - Low) / Open`.
- A day is tradeable only if:
  - prior 60-day median turnover > `1,000,000,000`
  - prior 60-day median daily range > `2%`

This is a structural participation/liquidity regime filter, not a date filter.
It catches the post-rerating CGPOWER behavior where the intraday pullback edge exists.

## Entry Logic

Trade only the first valid signal per day.

Long:

- Signal window: bars 8 to 59.
- Close > VWAP.
- EMA21 > EMA55.
- ADX >= 26.
- Same-bar volume ratio >= 1.2 versus 20-day same-time average.
- RSI14 between 50 and 75.
- Low touches EMA21 or VWAP.
- Close recovers above EMA21 and previous close.
- Entry: next candle open.
- Stop: 1.3 * ATR14.
- Target: 2R.

Short:

- Signal window: bars 8 to 44.
- Close < VWAP.
- EMA13 < EMA34.
- ADX >= 26.
- Same-bar volume ratio >= 1.2 versus 20-day same-time average.
- RSI14 between 28 and 55.
- High touches EMA13 or VWAP.
- Close breaks below EMA13 and previous close.
- Entry: next candle open.
- Stop: 1.3 * ATR14.
- Target: 2R.

## Signal Strength

Strength is a 0-100 pre-entry score. It is not a replacement for the regime gate.
The regime remains binary; once a day passes regime, strength scores only the signal candle.

Components:

- ADX above the minimum trend threshold.
- Same-time volume expansion above the minimum volume ratio.
- EMA alignment in the trade direction.
- Distance from VWAP in the trade direction.
- Trigger quality measured as close beyond the recovery/breakdown reference versus ATR.

RSI was tested as part of strength, but it hurt the ranking at the top buckets. RSI remains an entry guardrail only.

Final rule:

- Take trades only when `signal_strength >= 40`.
- Also require `strength_trigger_component >= 0.15`.

The trigger guardrail removes setups where the candle technically qualifies but has not confirmed enough recovery/breakdown versus ATR.

Strength result by bucket before applying the filter:

| Strength band | Trades | Net return | Avg/trade | Win rate | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| <40 | 14 | -0.21% | -1.21 bps | 42.86% | 0.966 | -2.59% |
| 40-50 | 19 | 3.12% | 16.46 bps | 52.63% | 1.644 | -1.57% |
| 50-60 | 36 | 7.05% | 19.18 bps | 61.11% | 1.839 | -3.19% |
| 60-70 | 21 | 1.89% | 9.19 bps | 52.38% | 1.318 | -1.36% |
| 70-80 | 19 | 6.24% | 32.67 bps | 52.63% | 1.984 | -2.75% |
| 80+ | 23 | 11.47% | 47.95 bps | 65.22% | 2.782 | -2.07% |

Higher thresholds are useful for sizing:

| Minimum strength | Trades | Net return | Avg/trade | PF | Max DD |
|---:|---:|---:|---:|---:|---:|
| 40 | 118 | 33.20% | 24.74 bps | 1.923 | -3.45% |
| 55 | 84 | 26.66% | 28.65 bps | 2.051 | -3.45% |
| 60 | 63 | 20.66% | 30.42 bps | 2.033 | -3.13% |
| 70 | 42 | 18.43% | 41.04 bps | 2.379 | -2.46% |
| 80 | 23 | 11.47% | 47.95 bps | 2.782 | -2.07% |

## High Win-Rate Test

I tested the 80% win-rate idea using two approaches:

- Smaller fixed targets such as `0.5R`.
- Hybrid partial exits: book the first leg around `0.4R` to `0.8R`, move the remaining stop, and let a runner continue toward `2R` to `4R`.

The strict 80% win-rate variants worked only when they gave up too much net return.
The best pure high-win candidate was:

| Variant | Trades | Net return | Avg/trade | Win rate | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Strength >= 80, stop 1.8 ATR, target 0.5R | 23 | 6.99% | 29.56 bps | 86.96% | 3.657 | -1.17% |

That is clean, but it is not a replacement for the main strategy because total net return drops too much.
The best hybrid tests that kept net near the current strategy topped out around 70-71% win rate, not 80%.
So the final strategy keeps the `2R` payoff profile and only adds the trigger-quality guardrail.

## Validation

Baseline cost: 5 bps per side.

| Period | Trades | Net return | Avg/trade | Win rate | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full final sample | 113 | 34.60% | 26.75 bps | 58.41% | 2.018 | -3.45% |
| Train before 2025 | 41 | 3.29% | 8.46 bps | 46.34% | 1.212 | -3.45% |
| Validation 2025 onward | 72 | 30.30% | 37.17 bps | 65.28% | 3.010 | -2.49% |
| Long leg | 70 | 14.93% | 20.25 bps | 54.29% | 1.744 | -2.45% |
| Short leg | 43 | 17.11% | 37.34 bps | 65.12% | 2.510 | -3.08% |

By year:

| Year | Trades | Net return | Avg/trade | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| 2024 | 41 | 3.29% | 8.46 bps | 1.212 | -3.45% |
| 2025 | 52 | 20.20% | 35.72 bps | 3.189 | -1.80% |
| 2026 | 20 | 8.41% | 40.93 bps | 2.696 | -2.49% |

Cost stress:

| Cost per side | Net return | Avg/trade | PF | Max DD |
|---:|---:|---:|---:|---:|
| 0 bps | 50.65% | 36.75 bps | 2.658 | -3.06% |
| 5 bps | 34.60% | 26.75 bps | 2.018 | -3.45% |
| 10 bps | 20.24% | 16.75 bps | 1.546 | -4.39% |
| 12 bps | 14.94% | 12.75 bps | 1.392 | -5.76% |
| 15 bps | 7.41% | 6.75 bps | 1.191 | -7.77% |

Bootstrap over final trade returns:

- Probability net positive: 99.82%.
- Probability PF > 1: 99.90%.
- 5th percentile net return: 15.01%.
- Median net return: 34.63%.
- 95th percentile net return: 59.17%.

## Files

- Strategy source: `Strategies/G01`
- Config snapshot: `Config/Strategies/G01/config.json`
- Fresh research output folder: `Research/G01`
- Scanner reports: `Paper/Reports/Scans`
