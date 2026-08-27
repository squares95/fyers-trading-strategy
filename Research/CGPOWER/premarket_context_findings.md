# CGPOWER pre-market context test

## Reel verdict

- **Previous Nasdaq and Dow direction helps predict CGPOWER's opening gap, not its post-open direction.** Both green produced a CG gap-up on 77.3% of sessions, but only 43.1% had a green first 15 minutes. Both red still produced a gap-up on 56.6% of sessions.
- **NIFTY/GIFT-style indication is closer to the actual opening price.** When NIFTY ultimately opened above +0.2%, CGPOWER gapped up 88.2% of the time; below -0.2%, the CG gap-up rate fell to 27.5%. This uses actual NIFTY opening gap as a proxy, not archived 09:00 GIFT quotes.
- **India VIX is a range switch, not a direction switch.** Above 15, CGPOWER's median absolute day was 1.57% and median range 3.70%; at or below 15, they were 1.10% and 2.85%.
- **Breadth cannot be used as described at 09:00.** NSE normal trading has not begun. The pre-open session is order collection and equilibrium-price discovery; use advances/declines only after the cash market has had time to trade.
- **The full permission rule failed.** US and NIFTY agreement plus CG's first-15-minute confirmation did not create a stable 09:30-to-close edge after 10 bps costs.

## Practical 09:00 process

1. Record previous Nasdaq and Dow return as `global risk`, not a buy/sell command.
2. Record previous India VIX close: above 15 means expect wider stops and smaller position size, not a known direction.
3. Record live GIFT Nifty and NSE's indicative pre-open NIFTY/CGPOWER equilibrium near 09:08. We need to start storing these point-in-time snapshots for a true historical test.
4. At 09:15, compare CGPOWER's actual gap with NIFTY. A large disagreement signals company-specific information.
5. At 09:30, use opening-range structure. Do not trade merely because the external cues were green or red.
6. Add market breadth after roughly 09:20, when advances/declines reflect actual trades.

The mental replay chart deliberately contains three strongest wins and three strongest losses from the same fixed confirmation rule. It shows why a morning checklist can describe context without reliably timing an entry.
