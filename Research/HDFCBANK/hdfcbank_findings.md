# HDFCBANK session research

Coverage: 2024-06-26 to 2026-08-14, 529 complete sessions. Discovery ends 2025-06-30; holdout begins 2025-07-01.

## Cross-asset rule transfer

                     Rule    Sample  Trades WinRate ProfitFactor Expectancy MaxDrawdown
  CG_frozen_opening_drive Discovery      55   38.2%         0.62    -0.146%      -8.21%
  CG_frozen_opening_drive   Holdout      51   60.8%         1.37     0.093%      -4.07%
CG_frozen_liquidity_sweep Discovery      57   42.1%         0.47    -0.105%      -6.16%
CG_frozen_liquidity_sweep   Holdout      65   50.8%         0.67    -0.064%      -4.52%
            CG_frozen_ORB Discovery     116   37.1%         0.68    -0.108%     -13.49%
            CG_frozen_ORB   Holdout     117   46.2%         0.76    -0.077%     -12.85%

## HDFCBANK-specific discovery and holdout

Opening drive:
                      Sample  Trades  WinRate  ProfitFactor  Expectancy  MaxDrawdown
Discovery_through_2025-06-30      36 0.444444      1.038836    0.000120    -0.025120
     Holdout_from_2025-07-01      29 0.448276      0.458371   -0.001936    -0.071789

Liquidity sweep:
                      Sample  Trades  WinRate  ProfitFactor  Expectancy  MaxDrawdown
Discovery_through_2025-06-30      57 0.403509      0.811694   -0.000510    -0.046898
     Holdout_from_2025-07-01      59 0.338983      0.650597   -0.001016    -0.087583

Opening-range breakout:
                      Sample  Trades  WinRate  ProfitFactor  Expectancy  MaxDrawdown
Discovery_through_2025-06-30     109 0.449541      0.740946   -0.000787    -0.104889
     Holdout_from_2025-07-01     101 0.465347      0.687720   -0.001016    -0.112330

## NIFTY relationship comparison

  Symbol  Sessions  GapCorrelation  First15Correlation  DailyCorrelation  GapDirectionMatch  First15DirectionMatch  DailyDirectionMatch  MedianAbsFirst30  MedianOpening30VolumeShare  MedianAbsClosing30  BothOpeningSidesBroken
HDFCBANK       529        0.772099            0.468759          0.700808           0.761364               0.670455             0.746212          0.003824                    0.145263            0.001550                0.287335
 CGPOWER      1282        0.730958            0.254406          0.433921           0.660985               0.585227             0.642045          0.007339                    0.141716            0.003209                0.297972

## Premarket permission filters

                          Variant Period  Trades  WinRate  ProfitFactor  Expectancy
              agreement_only_0930    All     172 0.447674      0.653462   -0.001374
              agreement_only_0930   2024      43 0.395349      0.431704   -0.002663
              agreement_only_0930   2025      68 0.411765      0.403437   -0.002350
              agreement_only_0930   2026      61 0.524590      1.178935    0.000623
     plus_cg_first15_confirmation    All      71 0.422535      0.727058   -0.001114
     plus_cg_first15_confirmation   2024      18 0.277778      0.307670   -0.003742
     plus_cg_first15_confirmation   2025      27 0.370370      0.390868   -0.002665
     plus_cg_first15_confirmation   2026      26 0.576923      1.810283    0.002316
plus_first15_and_range_acceptance    All      45 0.400000      0.561822   -0.001611
plus_first15_and_range_acceptance   2024      12 0.250000      0.519061   -0.001825
plus_first15_and_range_acceptance   2025      18 0.333333      0.383561   -0.002468
plus_first15_and_range_acceptance   2026      15 0.600000      0.870968   -0.000412
   plus_range_acceptance_and_rvol    All      23 0.521739      0.778016   -0.000692
   plus_range_acceptance_and_rvol   2024       4 0.250000      0.695069   -0.001231
   plus_range_acceptance_and_rvol   2025      11 0.454545      0.422955   -0.002249
   plus_range_acceptance_and_rvol   2026       8 0.750000      2.085324    0.001719

No result should be promoted unless the holdout remains profitable after costs and the mental losing replays remain tolerable.
