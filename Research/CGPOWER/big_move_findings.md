# CGPOWER big-move attribution

Data checked: 2021-06-03 to 2026-08-14, 1,287 trading sessions. NIFTY-relative attribution begins only when local NIFTY data starts (2024-06-26).

## What the chart says

- **Fresh information is traded during the session.** The cleanest positive repricing days have a modest gap, strong open-to-close progress, high relative volume, and a close near the day's high. The 22-Nov-2023 OSAT application and 28-Jan-2026 Q3 result are the clearest examples.
- **A large gap is not automatically momentum.** 03-Jun-2024 and 03-Feb-2026 delivered most of their gain before the open, then made little or negative progress intraday. Chasing those opens paid a very different price from owning before the information.
- **Bad news has two distinct shapes.** Margin disappointment on 06-May-2025 became persistent intraday distribution; the global shock on 07-Apr-2025 opened sharply lower but recovered during the session. Direction alone is insufficient: gap size, VWAP acceptance, and broad-market confirmation matter.
- **The business changed structurally after FY24.** Semiconductor optionality, transformer capacity expansion, data-centre orders, and a rapidly growing backlog created repeated company-specific repricing. Industrial-margin pressure and working-capital consumption explain why strong order growth did not remove downside shocks.
- **The existing G01 result must be treated as regime-dependent.** Its stronger 2025-26 historical performance should not be assumed to describe 2021-24 or a future valuation-compression regime.

## The moves that matter

- **22-Nov-2023, OSAT application:** +20.41%, almost entirely created after the open, on 11.79x normal volume. This was genuine intraday price discovery, but it gave back 3.76% over the next five sessions.
- **29-Feb-2024, Cabinet OSAT approval:** +4.94%, followed by another +4.64% over five sessions. Unlike the first OSAT spike, this repricing developed into a broader rerating.
- **29-Jan-2025 and 28-Jan-2026, earnings/capex:** +7.68% and +8.67%; both were mostly intraday, high-volume, company-specific moves. The FY25 reaction faded over five sessions, while the FY26 reaction extended another 13.39%, showing that the same chart shape can have different forward outcomes.
- **06-May-2025, margin disappointment:** -6.22%, with -6.58% from open to close. Price sold off late and persistently, yet recovered 9.30% over five sessions; bad event-day momentum was not automatically a swing short.
- **07-Apr-2025, tariff panic:** -10.49% opening gap but +3.77% open-to-close recovery. This was broad risk liquidation, not the same microstructure as company-specific distribution.
- **03-Jul-2026, procurement-policy shock:** -6.58% despite NIFTY rising 0.43%, on 7.14x normal volume. That is a clean sector/company-policy shock and the opposite of a market-beta move.

## Event path summary

| Path type | Events | MedianEventReturn | MedianPost5 | MedianPost20 |
| --- | --- | --- | --- | --- |
| intraday_accumulation | 6.0 | 7.08 | -0.9 | -1.36 |
| intraday_distribution | 1.0 | -6.22 | 9.3 | 13.78 |
| negative_expansion | 2.0 | -7.17 | 3.19 | 4.88 |
| negative_gap_recovery | 1.0 | -7.12 | 10.89 | 12.86 |
| ordinary | 2.0 | 0.45 | 6.41 | 10.61 |
| positive_expansion | 2.0 | 4.76 | -1.32 | 11.87 |

## Trading implications to validate, not assumptions

1. Use an event-session classifier before the normal momentum rules: overnight gap, relative volume, NIFTY-relative return, first-30-minute VWAP acceptance, and close location.
2. Continue positive moves only after price accepts above VWAP and the opening range; avoid gap-only opens that fail to extend.
3. For negative gaps, distinguish company-specific distribution from market-wide panic. A recovery above VWAP after a broad-market shock is not the same setup as a margin-led breakdown.
4. Train any new rule through 2024 and freeze it before testing 2025-Aug-2026. These observations explain history; they are not yet a tradable edge.

## Files

- `big_move_days.csv`: largest up/down sessions with gap, intraday, volume, timing, and NIFTY-relative fields.
- `big_move_weeks.csv`: largest weekly expansions and contractions.
- `event_move_windows.csv`: sourced events mapped to the next trading session and forward returns.
- `material_events.csv`: source ledger.
- `charts/`: visual evidence.
