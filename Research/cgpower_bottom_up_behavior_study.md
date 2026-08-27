# CGPOWER Bottom-Up Price Behavior Study

Data used: `Data/CGPOWER/CGPOWER_5MIN.csv`

Period studied: 2021-06-02 to 2026-05-29, using 1,230 complete trading days.

## First Observation

CGPOWER is not behaving like a normal large-cap mean-reversion stock. From the first usable close to the last usable close in the dataset, CGPOWER gained about 984%, while HDFCBANK was roughly flat over the same local dataset.

That matters because the current strategy is not a generic EMA/VWAP strategy. It is a high-participation, rerating-stock strategy.

## Bottom-Up Move Clusters

The cleanest bullish CGPOWER weeks were not isolated random days. They clustered around phases where the company story was being repriced.

| Window | Weekly return | Up days | Avg volume ratio | Weekly close position | Read |
|---|---:|---:|---:|---:|---|
| 2021-09-20 to 2021-09-24 | 21.36% | 4/5 | 2.21x | 1.00 | Turnaround rerating |
| 2021-10-18 to 2021-10-22 | 22.55% | 5/5 | 2.11x | 0.97 | Q2 FY22 result confirmation |
| 2023-01-09 to 2023-01-13 | 14.82% | 4/5 | 5.01x | 1.00 | Pre-result / growth anticipation |
| 2024-03-18 to 2024-03-22 | 14.39% | 4/5 | 3.92x | 0.82 | Semiconductor narrative follow-through |
| 2024-05-13 to 2024-05-17 | 12.94% | 4/5 | 2.07x | 0.84 | Q4 FY24 digestion |
| 2024-10-07 to 2024-10-11 | 18.12% | 5/5 | 2.20x | 0.87 | Pre-Q2 FY25 run-up |
| 2025-05-12 to 2025-05-16 | 14.25% | 5/5 | 1.18x | 0.90 | Q4 FY25 order-book digestion |
| 2026-02-01 to 2026-02-06 | 15.05% | 6/6 | 1.75x | 0.98 | Q3 FY26 / order-flow digestion |

Weekly close position means where the week closed within its own high-low range. A value near 1.0 means the stock closed near the weekly high.

## Event Overlay

| Event | Event date | Pre 20D | Post 20D | Interpretation |
|---|---:|---:|---:|---|
| Q1 FY22 turnaround results | 2021-08-02 | -3.55% | 8.77% | First confirmation of operational recovery |
| Q2 FY22 all-round turnaround results | 2021-10-21 | 38.20% | 11.07% | Strong result confirmed an existing rerating |
| Q1 FY23 strong growth results | 2022-07-28 | 15.20% | 0.45% | Good result, but less follow-through after pre-run |
| Q3 FY23 board/result anticipation | 2023-01-09 | 2.76% | 9.31% | Fresh anticipation worked |
| Q4 FY23 strong FY23 results | 2023-05-08 | 7.38% | 21.79% | Result became a continuation catalyst |
| Semiconductor unit approval/JV | 2024-02-29 | -1.62% | 15.69% | New narrative opened a fresh rerating leg |
| Q4 FY24 results | 2024-05-06 | 8.28% | 14.83% | Result digestion continued upward |
| Q2 FY25 order backlog/expansion | 2024-10-21 | 5.89% | -10.24% | Pre-run had already priced in optimism |
| Q4 FY25 order book jump | 2025-05-06 | -4.39% | 13.78% | Positive result after correction worked well |
| US data center order reaction | 2026-01-19 | -11.15% | 16.91% | New order news after selloff created a rebound setup |
| Q3 FY26 results | 2026-01-27 | -18.26% | 34.47% | Result/order digestion after heavy correction |

This is the main pattern: positive events work best when they confirm a fresh or recovering story, not when they arrive after a crowded pre-result run-up.

## Fundamental Context

The strongest price regimes were aligned with fundamental acceleration or narrative expansion:

- FY22 turnaround: Q2 FY22 standalone sales grew 139% YoY, PBT moved to Rs 137 crore from a loss of Rs 40 crore, and management called out all-round improvement in performance.
- FY23 growth confirmation: Q4 FY23 sales grew 28% YoY and FY23 PBT grew 89% YoY.
- FY24/FY25 continuation: Q1 FY25 sales and PBT were among the highest recent quarterly levels, and Q3 FY25 order intake grew 61% YoY with order backlog at Rs 8,952 crore.
- Semiconductor narrative: In February 2024, CG Power announced a semiconductor unit with Renesas and Stars Microelectronics in Sanand.
- FY25 order-book visibility: Q4 FY25 order backlog was reported around Rs 9,909 crore standalone / Rs 10,631 crore in broader reporting, sharply higher YoY.
- FY26 order narrative: January 2026 brought a roughly Rs 900 crore US data-center transformer order, followed by strong Q3 FY26 commentary.

## Market Regime Overlay

CGPOWER's best moves happened when company-specific strength overpowered or aligned with market conditions:

- 2021: Broad India risk appetite was strong; Nifty/Sensex ended the year sharply positive. CGPOWER's turnaround was rewarded aggressively.
- 2022: Global inflation, rate hikes, and the Russia-Ukraine shock created risk-off periods. CGPOWER still produced tactical rallies, but bearish weeks were sharper and more frequent.
- 2024: Election volatility hit the market in June, but CGPOWER's semiconductor and order-book narrative supported post-event recoveries.
- Late 2024 to early 2025: Small/mid-cap correction punished crowded names. This explains why some good-looking result windows, especially October 2024, failed after a pre-run.
- 2025/2026: CGPOWER rallied best after prior correction plus fresh order/result confirmation.

## HDFCBANK Contrast

HDFCBANK had 350 raw signals under the same technical entry rules, but only 14 after the CGPOWER regime gate and only 11 final trades. Final result was -1.18% with PF 0.639.

The contrast is important:

- HDFCBANK did not have the same multi-year rerating profile.
- HDFCBANK's post-merger period was dominated by balance-sheet normalization, deposit growth, credit-deposit ratio, and NIM concerns.
- The same intraday momentum-pullback logic is not naturally suited to a large private bank unless the bank is in a fresh, strong catalyst regime.

## Trading Implications

The best strategy filter is not just technical. It should ask:

1. Is the company in an earnings/order-book/narrative acceleration phase?
2. Is the stock already in high-participation mode?
3. Has the latest event created a fresh repricing, or was it already priced in?
4. Is the broader market supportive or at least not in a heavy small/mid-cap derating?

For CGPOWER-like names, bullish trades should be prioritized after:

- Strong result or order-book confirmation.
- Recent correction or consolidation before the event.
- Weekly close near highs on high volume.
- First or second intraday pullback after the event confirmation.

Avoid chasing when:

- The stock already rallied 20-35% into the result.
- The result/event week closes far off the high.
- Broader small/mid-cap regime is derating.
- Volume spike is a one-day exhaustion event rather than multi-day participation.

## Strategy Upgrade Ideas

1. Add a stock-selection layer:
   - 60-day median turnover rising.
   - Weekly close above rising 10-week and 30-week trend.
   - At least one recent clean impulse week.
   - Company has a live catalyst: result acceleration, order-book expansion, capacity expansion, or sector/narrative rerating.

2. Add an event digestion mode:
   - Do not buy the event candle blindly.
   - Wait for 5-minute pullback to VWAP/EMA support after event confirmation.
   - Prefer the first 1-10 trading days after a positive event if there was no large pre-run.

3. Add a pre-run penalty:
   - If pre-20-day return is already very high, reduce size or wait.
   - October 2024 is the warning case: strong pre-run, then poor post-result follow-through.

4. Keep HDFCBANK out of this strategy unless it enters a separate bank-specific regime.

## Sources

- CG Power Q2 FY22 press release: https://www.cgglobal.com/admin/uploads/Press_Release_dated_21_10_2021.pdf
- CG Power Q4 FY23 press release: https://www.murugappa.com/uploads/CG_Power_Press_Release_Q4_FY_2022_23_May_09_2023_1c58d09f01.pdf
- CG Power semiconductor disclosure: https://www.cgglobal.com/admin/uploads/Reg_30_Disclosure_Release_PIB.pdf
- CG Power Q1 FY25 press release: https://www.cgglobal.com/admin/uploads/SEDisclosure_PressRelease_Q1_FY2024_25.pdf
- CG Power Q3 FY25 press release: https://www.cgglobal.com/admin/uploads/SEDisclosure_PressRelease6.pdf
- CG Power Q4 FY25 press release: https://www.murugappa.com/uploads/CG_Power_releases_Q4_FY_2024_25_results_May_08_2025_026cd875f2.pdf
- CG Power US data-center order: https://www.murugappa.com/media/0xrj5sf1/press-release-cg-power-receives-900-crore-order-from-tallgrass-for-transformers.pdf
- HDFC Bank merger completion: https://www.hdfc.bank.in/press-release/2023/q2/hdfc-ltd-to-merge-into-hdfc-bank-effective-july-1-2023
- 2021 Indian market risk appetite: https://economictimes.indiatimes.com/markets/stocks/news/sensex-nifty50-end-2021-with-a-bang-as-risk-appetite-returns/articleshow/88614837.cms
- 2024 election market selloff: https://indianexpress.com/article/business/market/sensex-nifty-plunge-6-after-election-trends-suggest-weaker-mandate-for-bjp-led-nda-9371625/lite/
- 2025 small/mid-cap correction context: https://www.fortuneindia.com/investing/small-mid-cap-indices-correct-12-in-2025-heres-why/120362
