# Slim Data Bundle

This is a **23.6 MB** subset of the full `Data/` folder, committed to GitHub
so the codespace has data to work with (full `Data/` is gitignored).

## What's included

For each of these symbols:
- `CGPOWER` (Power)
- `HDFCBANK` (Banking)
- `SUZLON` (Power)
- `NIFTY` (Index)
- `BANKNIFTY` (Index)

We have:
- `1D` (daily candles, ~100 KB each)
- `5MIN` (5-min candles, 3-7 MB each)
- `1W` (weekly, ~10-20 KB each)

## What's NOT included (and why)

- **1MIN** files (15-35 MB each, 3 stocks = ~80 MB) — not needed for our intraday strategy; 5MIN is enough
- **15MIN** files (2-3 MB each) — derivable from 5MIN
- **PDF contract notes** (~440 MB total!) — useless for backtest

## How scripts find this

All research scripts use a `resolve_data_path()` helper that:
1. Tries `Data/_slim/{SYMBOL}_{TIMEFRAME}.csv` first
2. Falls back to `Data/{SYMBOL}/{SYMBOL}_{TIMEFRAME}.csv`

So this works in **both**:
- **Codespace** (slim bundle present, scripts use slim)
- **Local machine** (full Data folder, scripts use full)

## If you need a different stock or timeframe

1. Download locally from Fyers (using `Download.py` or the main pipeline)
2. Copy the CSVs into `Data/_slim/` keeping the naming pattern
3. Commit + push

Only commit files you actually need — every MB matters on slow connections.
