# Current Session State

**Last updated**: 2026-08-28

---

## 🎯 Active Goal

Enhance SUPER GOLD portfolio strategy by adding **market news / sentiment** overlay
before going to paper trading. User wants real-world volatility awareness.

**End state**: A "Market-Ready" strategy that combines:
- Technical signals (SUPER GOLD: VWAP-EMA pullback + regime + strength)
- Macro/news regime (avoid trading on crash days, news-driven chaos)

---

## ✅ Completed (Recent Wins)

| Exp | Result | Status |
|-----|--------|--------|
| 1 | Power sector deep dive | Done — base strategy loses, filters needed |
| 2 | 26-stock Gold screen | 8 winners, 9 losers |
| 3 | New candidates | DRREDDY +6.7%, INDUSINDBK +4.2% |
| 4 | **Portfolio: +65.1% net, PF 2.18, DD -5.76%** | Done |
| 5 | **OOS 2025-2026: +22.8% net, PF 2.10** | Validated |

---

## 🏆 Locked Strategy (SUPER GOLD Portfolio)

### Portfolio (Trade These 7)
| Stock | Allocation | Sector | Notes |
|-------|-----------|--------|-------|
| CGPOWER | 40% | Power | Best individual (+40.4%) |
| DRREDDY | 25% | Pharma | New winner |
| INDUSINDBK | 15% | Banking | New winner |
| BHEL | 10% | Power | Solid |
| HCLTECH | 5% | IT | Diversifier |
| TITAN | 5% | Consumer | Diversifier |
| M&M | 5% | Auto | Diversifier |

### Strategy Parameters
- VWAP-EMA Pullback (long/short)
- EMA 13/21/34 alignment
- ADX >= 32
- Volume ratio >= 2.0
- Stop: 1.3x ATR
- Target: 3.9R (1:3 risk/reward)
- Regime filter: turnover > 1B, range > 2%
- Strength filter: score >= 45, trigger >= 0.15

---

## 🔄 In Progress: Exp 6 — News/Sentiment Integration

### Hypothesis
Strategy is profitable on average but may bleed on:
- Crash days (news-driven)
- Event-driven volatility (results, budget, Fed-like events)
- Sector-wide news shocks

### Design Ideas (TBD)
1. **VIX filter** — Skip trading when India VIX > X
2. **FII/DII flow filter** — Strong FII selling = defensive mode
3. **News event blackout** — Skip 1-2 days around known events
4. **Sentiment score** — Daily news score 0-100, only trade > 50
5. **Gap filter** — No trading after overnight gap > 2%

### Data Sources (Free/Accessible)
- NSE India VIX (daily)
- NSE FII/DII activity (daily)
- MoneyControl / Economic Times news scraping
- Twitter/X finance (rate-limited)
- Google News RSS

### Success Criteria
- OOS performance must NOT degrade vs. Exp 5 (+22.8%)
- Ideally improve on drawdown (-5.09% baseline)
- Reduce losing days / tail risk

---

## 🚧 Blockers / Open Questions

- Free news API access? (NewsAPI has limits)
- Real-time vs daily news granularity?
- Backtest period: how to test news filter without lookahead bias?

---

## 📋 Next Actions

1. [ ] Decide on macro filter(s) — VIX? FII? Both?
2. [ ] Build data fetcher for VIX + FII/DII (NSE website scrape or NSEpy)
3. [ ] Design filter rule (e.g., skip when VIX > 20)
4. [ ] Re-run backtest with filter on 2021-2026
5. [ ] Re-validate on 2025-2026 OOS
6. [ ] If better → integrate into SUPER GOLD config
7. [ ] If not → document why and move to paper trade

---

## 🧠 User Preferences (Recurring)

- **Short, classy, crisp responses** — no code in chat
- **No code changes shown in output** — read files directly
- **Be wild, try diff combos/parameters** — iterate
- **Factor in real-world volatility** — think live, not just backtest
- **Lead the mission autonomously** — come back when strategy is ready

---

## 📂 Key Files Reference

- `Research/exp01-05_*.py` — Completed experiments
- `Research/exp06_news_filter.py` — TO BE CREATED
- `Strategies/G01/Gold.py` — SUPER GOLD config lives here
- `Strategies/G01/regime_filter.py` — Add macro filter here
- `Data/{SYMBOL}/{SYMBOL}_5MIN.csv` — 5-min price data
- `Config/groq_config.json` — Groq API (offload analysis)
- `context/experiment_log.md` — Master log
- `context/architecture_guide.md` — Code map

---

## 💾 Session Hygiene

- Update this file after each major decision
- Archive old sections to `archive/session_*.md` when this file grows > 200 lines
- Commit context/ folder after each experiment
