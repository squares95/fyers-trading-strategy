# SBIN Personality And Strategy Discovery Report

## Executive Summary

- SBIN's intraday personality is **mean-reverting on 1-minute follow-through**, with continuation at 35.5% versus mean reversion at 39.0% under the 3-minute follow-through definition.
- High-velocity windows are **09:15-10:00, 15:00-15:30**. Dead/noisy windows are **12:00-13:00, 13:00-14:00**.
- **No production-ready strategy was promoted from this run.** Rejected: the best discovery candidate did not meet the minimum training thresholds.
- Best discovery candidate: `breakout_retest|or30|end=10:30|rr=1.5|atr=1.0|vol=0.8|vwap=1|ema=1|macro=not_both_against|band=1.2`.
- In-sample: 51 trades, 50.98% win rate, PF 1.5359183673469499, expectancy 0.263R, max DD -8.00R.
- Out-of-sample: 11 trades, 36.36% win rate, PF 0.7155388471177906, expectancy -0.181R, max DD -4.99R.

## Personality Profile

### Time-Of-Day Volatility

| Bucket | one_min_bars | avg_1m_tr_bps | median_1m_tr_bps | avg_1m_volume | total_volume | avg_5m_tr_bps | median_5m_tr_bps | avg_5m_volume | velocity_score | personality |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:15-10:00 | 11115 | 12.7428 | 9.5111 | 42974.0265 | 477656305 | 31.5588 | 22.8124 | 214870.1327 | 0.9571 | high-velocity |
| 10:00-11:00 | 14820 | 7.8949 | 6.8145 | 27777.6028 | 411664073 | 18.2247 | 15.9268 | 138888.0138 | 0.6714 | normal |
| 11:00-12:00 | 14820 | 6.9824 | 6.0961 | 24754.1536 | 366856557 | 15.7146 | 13.635 | 123770.7682 | 0.3571 | normal |
| 12:00-13:00 | 14820 | 6.9389 | 5.7872 | 24026.219 | 356068565 | 15.3764 | 12.9748 | 120131.0948 | 0.1714 | dead/noisy |
| 13:00-14:00 | 14835 | 7.0047 | 6.0613 | 24257.7084 | 359863104 | 15.3402 | 13.0419 | 121288.542 | 0.3286 | dead/noisy |
| 14:00-15:00 | 14866 | 7.6047 | 6.3967 | 33425.1899 | 496898873 | 16.6445 | 14.0911 | 167080.9929 | 0.6143 | normal |
| 15:00-15:30 | 7410 | 8.4668 | 7.2502 | 78837.3101 | 584184468 | 18.406 | 15.2354 | 394186.5506 | 0.9 | high-velocity |

### Noise Vs Signal

| class | percent | bars |
| --- | --- | --- |
| mean_reversion | 39.0012 | 32816 |
| continuation | 35.5273 | 29893 |
| noise | 25.4715 | 21432 |

### Opening Range Statistics

| metric | value |
| --- | --- |
| days | 247 |
| or_high_broken_pct | 68.8259 |
| or_low_broken_pct | 70.4453 |
| either_side_broken_pct | 99.1903 |
| both_sides_broken_pct | 40.081 |
| true_breakout_after_first_break_pct | 35.5102 |
| fake_breakout_after_first_break_pct | 69.3878 |

### Gap Resolution

| direction | gaps | fill_rate_pct | avg_gap_pct |
| --- | --- | --- | --- |
| gap_down | 49 | 46.9388 | -0.7543 |
| gap_up | 90 | 37.7778 | 0.7549 |

### Higher-Timeframe Dominance

| macro_alignment | trend_setup_trades | win_rate_pct | profit_factor | expectancy_r |
| --- | --- | --- | --- | --- |
| aligned_1d_1w | 77 | 42.8571 | 1.0353 | 0.0195 |
| mixed_or_neutral | 84 | 42.8571 | 1.0768 | 0.0439 |
| opposed_1d_1w | 62 | 40.3226 | 1.0378 | 0.022 |

## Mechanical Strategy Decision

**Decision: do not promote this SBIN candidate to paper/live trading yet.**

Rejected candidate: `breakout_retest|or30|end=10:30|rr=1.5|atr=1.0|vol=0.8|vwap=1|ema=1|macro=not_both_against|band=1.2`.

- Entry uses the setup, boundary, time, VWAP, EMA, volume, and macro filters encoded in the variant string.
- Entry price is next 5-minute candle open after the signal candle.
- Stop uses the larger of recent signal-candle adverse excursion and ATR-multiple risk.
- Target is fixed at the variant's R multiple. Minimum tested reward/risk is 1.5:1.
- Same-minute stop/target conflict resolves conservatively as stop first.
- Exit at 15:15 if neither stop nor target is hit.

The rule above is preserved for audit and future refinement, but it is not a validated trading system because it did not clear the target thresholds.

## Comparative Backtest Summary

| set_name | trades | win_rate | profit_factor | expectancy_r | max_drawdown_r | avg_trade_duration_min |
| --- | --- | --- | --- | --- | --- | --- |
| train | 51 | 50.9804 | 1.5359 | 0.2627 | -8 | 35.1765 |
| test | 11 | 36.3636 | 0.7155 | -0.181 | -4.9912 | 73.5455 |

## Scope And Caveats

- Data source: local FYERS CSV files for SBIN.
- Research window: 2025-06-19 to 2026-06-19.
- Discovery window: 2025-06-19 to 2026-03-19 exclusive.
- Out-of-sample window: 2026-03-19 to 2026-06-19.
- Partial current sessions are excluded; the research end date is the last complete trading session found in the 5-minute file.
- Metrics are historical simulation results, not live execution proof.
- Brokerage, taxes, slippage, queue position, and whole-share sizing are not included in the headline R metrics.
