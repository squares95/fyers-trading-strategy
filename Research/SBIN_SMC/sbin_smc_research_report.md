# SBIN SMC Strategy Research

## Data Split
- Research window: 2025-08-17 to 2026-08-17 (12 months)
- Training: 2025-08-17 to 2026-04-17 (exclusive end, 8 months)
- Out-of-sample test: 2026-04-17 to 2026-08-17 (4 months)
- Bank Nifty VWAP filter source: C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data\BANKNIFTY\BANKNIFTY_1MIN.csv

## Selected Variant
- Selected from training only: opening_15m__market_1m_mss__bank_vwap

## Mechanical Rules
- Detect a bullish sweep when price trades below the selected liquidity level and closes back above it; bearish is the mirror image.
- Liquidity level is either previous-day high/low or the opening 09:15-09:30 range high/low.
- Setup window is 09:30-11:30 IST. Entry must happen by 12:00 IST.
- A 5-minute displacement candle must follow the sweep within six 5-minute bars and must include a 5m or same-window 1m FVG.
- The 5m order block is the last opposite-color candle before displacement.
- Direct OB entry uses a limit order at the midpoint of the 5m order block, valid for 40 minutes.
- 1m MSS entry uses a market entry on a 1m close beyond the prior five 1m candles, with a same-candle 1m FVG.
- Stop goes beyond the swept extreme and order-block edge, plus Rs 0.05 buffer. Trade is skipped if stop exceeds 0.8% of entry price.
- Target is exactly 2R. If neither stop nor target hits, exit at 15:15 IST.
- Once price reaches +1R, stop is moved to breakeven. This was added from training-set failure analysis because many losers first reached about +1R, then reversed.
- Higher timeframe bias comes from 15m and 1h structure breaks. A trade is blocked only if both HTFs point against it.

## Selected Variant Metrics
- Training: trades=15, win_rate=46.67%, decisive_win_rate=77.78%, PF=6.770833333333346, expectancy=0.769R, max_drawdown=-1.00R, breakevens=6
- Test: trades=4, win_rate=0.00%, decisive_win_rate=0.00%, PF=0.0, expectancy=-1.000R, max_drawdown=-3.00R, breakevens=0

## All Variant Summary
| variant | set_name | available | trades | win_rate | decisive_win_rate | profit_factor | expectancy_r | max_drawdown_r | breakevens | losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| previous_day__direct_5m_ob__no_bank_filter | train | True | 6 | 33.3333 | 40 | 1.3333 | 0.1667 | -2 | 1 | 3 |
| previous_day__direct_5m_ob__no_bank_filter | test | True | 6 | 16.6667 | 25 | 0.6667 | -0.1667 | -3 | 2 | 3 |
| previous_day__direct_5m_ob__bank_vwap | train | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| previous_day__direct_5m_ob__bank_vwap | test | True | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| previous_day__market_1m_mss__no_bank_filter | train | True | 6 | 16.6667 | 100 | inf | 0.3333 | 0 | 5 | 0 |
| previous_day__market_1m_mss__no_bank_filter | test | True | 7 | 14.2857 | 25 | 0.6667 | -0.1429 | -3 | 3 | 3 |
| previous_day__market_1m_mss__bank_vwap | train | True | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| previous_day__market_1m_mss__bank_vwap | test | True | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| opening_15m__direct_5m_ob__no_bank_filter | train | True | 21 | 33.3333 | 43.75 | 1.5556 | 0.2381 | -4 | 5 | 9 |
| opening_15m__direct_5m_ob__no_bank_filter | test | True | 20 | 15 | 20 | 0.5 | -0.3 | -10 | 5 | 12 |
| opening_15m__direct_5m_ob__bank_vwap | train | True | 7 | 42.8571 | 50 | 2 | 0.4286 | -2 | 1 | 3 |
| opening_15m__direct_5m_ob__bank_vwap | test | True | 5 | 20 | 20 | 0.5 | -0.4 | -3 | 0 | 4 |
| opening_15m__market_1m_mss__no_bank_filter | train | True | 38 | 39.4737 | 62.5 | 2.9976 | 0.4731 | -2 | 14 | 9 |
| opening_15m__market_1m_mss__no_bank_filter | test | True | 26 | 34.6154 | 52.9412 | 2.0522 | 0.3238 | -2 | 9 | 8 |
| opening_15m__market_1m_mss__bank_vwap | train | True | 15 | 46.6667 | 77.7778 | 6.7708 | 0.7694 | -1 | 6 | 2 |
| opening_15m__market_1m_mss__bank_vwap | test | True | 4 | 0 | 0 | 0 | -1 | -3 | 0 | 4 |

## Losing Trade Breakdown
| failure_reason | count | avg_mfe_r | avg_minutes_held |
| --- | --- | --- | --- |
| SMC trap: sweep kept running with almost no follow-through | 3 | 0.0473 | 13.6667 |
| Opening-range whipsaw after liquidity grab | 2 | 0.6632 | 45 |
| Fast continuation through the swept level | 1 | 0.3692 | 18 |
