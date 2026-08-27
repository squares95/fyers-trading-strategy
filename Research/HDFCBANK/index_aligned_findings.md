# HDFCBANK index-aligned strategy experiment

NIFTY cash-index volume is zero, so this study uses expanding intraday average price (TWAP) and EMA direction for NIFTY. HDFCBANK uses true VWAP.

Best diagnostic candidate from the discovery grid (not automatically tradable):
{'Family': 'trend_pullback', 'Variant': 'nifty_10bp_hdfc_15m', 'StopLookback': 20, 'TargetR': 2.0, 'Deviation': nan, 'NiftyTolerance': nan, 'Trades': 134, 'WinRate': 0.43283582089552236, 'ProfitFactor': 0.7832614871287297, 'Expectancy': -0.00044499259732980743, 'MaxDrawdown': -0.07255374737755849, 'Score': 8.663436567559348}

   Sample  Trades  WinRate  ProfitFactor  Expectancy  MaxDrawdown
Discovery     134 0.432836      0.783261   -0.000445    -0.072554
  Holdout     148 0.277027      0.396731   -0.001479    -0.196400

Research gate: FAIL. A pass requires at least 20 trades, Profit Factor above 1.0, and positive expectancy in both discovery and untouched holdout data.

Yearly:
 Year  Trades  WinRate  ProfitFactor  Expectancy  MaxDrawdown
 2024      71 0.450704      0.880548   -0.000222    -0.028679
 2025     126 0.309524      0.450602   -0.001313    -0.170573
 2026      85 0.329412      0.525443   -0.001145    -0.094324

The candidate is acceptable only if its holdout remains profitable after 10 bps costs and does not depend on one small group of trades.
