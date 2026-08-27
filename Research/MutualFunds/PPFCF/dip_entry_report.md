# PPFCF Dip Entry Research

Historical simulation only. Signals use published NAV information and execute at the next available NAV.

## Research Design

- Development: through 2021-12-31
- Validation: 2022-01-01 through 2024-08-23
- Final untouched period: 2024-08-24 onward
- Selected rule: None passed the promotion gate
- Selected monthly deployment: None passed the promotion gate

## Recent Context

- Return: 6.10%
- Maximum drawdown: -10.98%
- Daily correlation with NIFTY 50: 0.873

## Selected Rule Results

No rule passed.

## Monthly Deployment Results

No monthly timing strategy passed.

## Recent Market-Shock Diagnostics

Descriptive only: recent NIFTY coverage is insufficient for independent rule validation.

```text
              Rule  Signals FirstEntry  LastEntry  FellFurtherWithin5DaysPct  MedianWorstNext5Pct  MedianForward20Pct  PositiveForward20Pct  MedianLift20Pct  MedianForward60Pct  PositiveForward60Pct  MedianLift60Pct
     NiftyDayDown1       24 2024-09-09 2026-06-24                  75.000000            -0.354674            0.655033             58.333333         0.259290            2.046398             59.090909         1.289964
   NiftyDayDown1.5        9 2024-10-04 2026-07-09                  55.555556            -0.249364            0.800056             55.555556         0.404313            2.573122             62.500000         1.816688
     NiftyDayDown2        3 2024-10-04 2026-03-20                  66.666667            -1.203356            4.205680             66.666667         3.809937            2.676362            100.000000         1.919929
    Nifty5DayDown3        8 2024-10-07 2026-05-14                  50.000000            -0.121994            1.484404             62.500000         1.088662            2.601627             75.000000         1.845193
    Nifty5DayDown4        4 2024-10-07 2026-03-09                  25.000000             0.413267            0.434964             75.000000         0.039221            0.832876             50.000000         0.076442
    Nifty5DayDown5        3 2024-10-08 2026-03-16                  33.333333             0.319558            3.089475            100.000000         2.693732            1.509057            100.000000         0.752623
 NiftyDay1_FundDD3        7 2024-10-23 2026-03-20                  57.142857            -0.249364            0.647588             71.428571         0.251845           -0.883354             42.857143        -1.639788
Nifty5Day3_FundDD5        3 2025-03-03 2026-03-16                  66.666667            -0.249364            3.089475            100.000000         2.693732            8.554970            100.000000         7.798536
```