# Data Quality Findings — Option A Complete

**Date**: 2026-08-26
**Scope**: All 1-MIN data files in `Data/`

## Summary Verdict: ✅ Data is clean and usable for research

### Coverage by Symbol

| Symbol | Bars | Days | Date Range | Complete | After-Hours | OHLC Viol. |
|--------|------|------|------------|----------|-------------|------------|
| CGPOWER | 481,915 | 1,291 | 2021-06-03 → 2026-08-14 | 96% | 240 | 3 |
| SUZLON | 481,990 | 1,291 | 2021-06-03 → 2026-08-14 | 99% | 241 | 2 |
| HDFCBANK | 198,496 | 531 | 2024-06-26 → 2026-08-14 | 99.6% | 60 | 0 |
| NIFTY | 198,871 | 532 | 2024-06-26 → 2026-08-17 | 99.6% | 60 | 0 |
| BANKNIFTY | 185,371 | 496 | 2024-08-19 → 2026-08-17 | 99.6% | 60 | 0 |
| SBIN | 185,746 | 497 | 2024-08-16 → 2026-08-17 | 99.6% | 60 | 0 |
| ICICIBANK | 185,371 | 496 | 2024-08-19 → 2026-08-17 | 99.6% | 60 | 0 |
| BHARTIARTL | 185,371 | 496 | 2024-08-19 → 2026-08-17 | 99.6% | 60 | 0 |
| M&M | 185,371 | 496 | 2024-08-19 → 2026-08-17 | 99.6% | 60 | 0 |
| LT | 185,371 | 496 | 2024-08-19 → 2026-08-17 | 99.6% | 60 | 0 |
| RELIANCE | 101,311 | 271 | 2025-07-14 → 2026-08-17 | 99.6% | 0 | 0 |
| TCS | 101,311 | 271 | 2025-07-14 → 2026-08-17 | 99.6% | 0 | 0 |
| INFY | 101,311 | 271 | 2025-07-14 → 2026-08-17 | 99.6% | 0 | 0 |
| BAJFINANCE | 101,311 | 271 | 2025-07-14 → 2026-08-17 | 99.6% | 0 | 0 |
| BEL | 101,311 | 271 | 2025-07-14 → 2026-08-17 | 99.6% | 0 | 0 |
| HCLTECH | 101,311 | 271 | 2025-07-14 → 2026-08-17 | 99.6% | 0 | 0 |
| TITAN | 101,311 | 271 | 2025-07-14 → 2026-08-17 | 99.6% | 0 | 0 |
| MIDCAP150_TRI | — | — | Daily only | — | — | — |
| SMALLCAP250_TRI | — | — | Daily only | — | — | — |
| HDFCSML250 | — | — | Daily only | — | — | — |
| MIDCAPIETF | — | — | Daily only | — | — | — |

### Issues Found

1. **After-hours bars (240 across CGPOWER, similar across symbols)**: Bars from 18:00-19:14 on ~5 specific dates
   - 2021-11-04, 2022-10-24, 2023-11-12, 2024-03-02, 2024-05-18, 2024-11-01, 2025-10-21
   - **Fix**: Filter to 09:15-15:30 only. Drop 0.05% of data.

2. **OHLC violations**: Only 5 across all symbols
   - CGPOWER: 2023-12-28, 2024-01-18, 2024-01-25 (all opening bars)
   - SUZLON: 2 opening bars
   - **Fix**: Filter first bar of day or replace with previous close

3. **Intra-day gaps**: 81 small gaps (1-2 min), 2 medium (91 min)
   - **Fix**: Materialize from 1-MIN to higher TFs handles this

4. **Zero-volume bars**: 2,948 in CGPOWER (spread across day)
   - **Fix**: No special handling needed; real market phenomenon

### Quality by Year (CGPOWER)

| Year | Bars | Days |
|------|------|------|
| 2021 | 54,359 | 146 |
| 2022 | 92,663 | 248 |
| 2023 | 91,937 | 246 |
| 2024 | 92,520 | 249 |
| 2025 | 93,061 | 249 |
| 2026 | 57,375 | 153 (partial) |

### Filtering Recipe for Research

```python
# Standard filter for any research backtest
df = pd.read_csv(csv_path, parse_dates=['Datetime'])
df = df[(df['Datetime'].dt.time >= pd.Timestamp('09:15').time()) &
        (df['Datetime'].dt.time <= pd.Timestamp('15:30').time())]
df = df.drop_duplicates(subset='Datetime', keep='last')
```

### Conclusion

Data is **research-grade**. No major cleaning required beyond the time filter.
All 1-MIN data is suitable for backtesting once filtered to market hours.
CGPOWER and SUZLON are the longest-history symbols (ideal for walk-forward).
