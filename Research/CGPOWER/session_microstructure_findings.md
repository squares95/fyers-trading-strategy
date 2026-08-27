# CGPOWER opening and closing microstructure

Coverage: 2021-06-03 to 2026-08-14, 1,282 complete sessions. Discovery sample: 881 sessions through 2024. Holdout: 401 sessions from 2025 onward. Costs: 10 bps round trip.

## Session anatomy

- The median first 30 minutes contain **14.2% of daily volume** and move **0.73%** in absolute terms.
- The median final 30 minutes contain **16.7% of daily volume** and move **0.32%** in absolute terms.
- Both sides of the first 15-minute range are broken on **29.8%** of sessions. Those sessions are two-sided discovery/noise, not clean trend days.
- The first 15 minutes are useful only when normalized by the prior 20-day ATR, confirmed by close location inside the opening range, and supported by opening volume.
- The final hour is more often a liquidity/positioning phase than a fresh-information phase. Strong moves into 14:29 do not automatically continue.

## Frozen opening-drive rule

- At 09:30, trade in the first-15-minute direction only when `abs(first15 return) >= 0.15 x prior ATR20`.
- The 09:29 close must finish in the directional top/bottom 30% of the opening range.
- First-15-minute volume must exceed **0.99x** the prior 20-session median for that same window (the training 50% quantile).
- Stop at the opposite opening-range boundary; reject risk above 1.2%; target 2.0R; otherwise exit 15:14.

           Sample  Trades WinRate ProfitFactor Expectancy MaxDrawdown
  Train_2021_2024      29   44.8%         1.13     0.068%      -6.01%
Holdout_2025_2026      26   42.3%         0.73    -0.142%      -9.83%

This is a deliberately frozen holdout check, not a production recommendation. If holdout performance is weak, the correct conclusion is that opening structure explains price action but does not yet provide a stable standalone edge.

## Opening-range liquidity sweep test

The data's stronger structural clue is sequence, not raw first-15-minute direction: a low sweep followed by a high break tends to finish bullish, while a high sweep followed by a low break tends to finish bearish. The training-selected mechanical test waits for the second boundary to break, enters on the next minute, uses a **midpoint** stop, a **1.0R** target, and accepts signals through **14:30**. Its opening RVOL filter is `none`.

           Sample  Trades WinRate ProfitFactor Expectancy MaxDrawdown
  Train_2021_2024     140   49.3%         0.70    -0.114%     -16.87%
Holdout_2025_2026     106   53.8%         0.93    -0.020%      -3.94%

## Mental paper-trade replay set

These holdout examples were selected only after the rule was frozen: the three best and three worst outcomes. Replaying both tails prevents a persuasive chart from hiding how the setup actually fails.

      Date  Direction     BreakType SignalTime EntryTime  EntryPrice    Stop  Target ExitTime  ExitPrice ExitReason NetReturn
2025-03-27          1 low_then_high      11:38     11:39      640.35 634.100 646.600    14:05    634.100       stop   -1.076%
2025-05-09          1 low_then_high      14:12     14:13      605.25 598.450 612.050    14:49    612.050     target    1.024%
2025-08-04         -1 high_then_low      10:48     10:49      647.60 653.500 641.700    11:33    653.500       stop   -1.011%
2026-01-21          1 low_then_high      12:43     12:44      573.00 567.425 578.575    13:50    567.425       stop   -1.073%
2026-02-01         -1 high_then_low      12:27     12:28      584.65 591.575 577.725    12:28    577.725     target    1.084%
2026-04-02          1 low_then_high      13:41     13:42      673.55 665.500 681.600    15:06    681.600     target    1.095%

## First opening-range break test

The earlier entry trades the first opening-range break by **11:30**, only when the 09:29 close is in the directional top/bottom **30%**. It uses a **opposite_boundary** stop, **1.5R** target, RVOL filter `none`, and gap-alignment requirement `False`.

           Sample  Trades WinRate ProfitFactor Expectancy MaxDrawdown
  Train_2021_2024      69   53.6%         1.29     0.129%      -7.62%
Holdout_2025_2026      82   40.2%         0.73    -0.148%     -14.97%

Its holdout replay tails are stored separately so the entry can be visually audited without choosing only attractive examples.

## Evidence files

- `minute_of_day_profile.csv`
- `opening_strength_outcomes.csv`
- `opening_range_outcomes.csv`
- `closing_strength_outcomes.csv`
- `opening_rule_grid_train.csv`
- `opening_rule_train_holdout.csv`
- `liquidity_sweep_grid_train.csv`
- `liquidity_sweep_train_holdout.csv`
- `mental_papertrade_replays.csv`
- `opening_range_breakout_grid_train.csv`
- `opening_range_breakout_train_holdout.csv`
- `opening_range_breakout_replays.csv`
- `session_charts/`
