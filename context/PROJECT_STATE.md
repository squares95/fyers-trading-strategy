# Project State - Final Locked Strategy (Aug 28, 2026)

## Status: PAPER TRADING READY

**Latest commit**: `ad34641`
**Strategy**: SUPER GOLD Portfolio + 2.5% Gap Filter
**Validation**: OOS 2025+ confirmed: +48.0% net, PF 2.872, DD -4.44%, 105 trades

---

## What's Locked

### Portfolio (7 stocks, 100% capital allocation)
- CGPOWER: 40%
- DRREDDY: 25%
- INDUSINDBK: 15%
- BHEL: 10%
- HCLTECH: 5%
- TITAN: 5%
- M&M: 5%

### Strategy Parameters
- **Entry**: VWAP-EMA pullback, EMA 13/34, ADX >= 32, vol ratio >= 2.0
- **Stop**: 1.3x ATR
- **Target**: 3.9R (1:3 risk/reward)
- **Regime filter**: turnover > 1B, range > 2% daily
- **Strength filter**: score >= 45, trigger >= 0.15
- **NEWS FILTER (Exp 6)**: skip day if any portfolio stock gapped > 2.5%

### Files
- `Strategies/G01/Gold.py` — main orchestrator (`run(portfolio=..., gap_threshold=...)`)
- `Strategies/G01/Core.py` — base strategy (signals + backtest)
- `Strategies/G01/news_filter.py` — gap/crash filter (NEW)
- `Strategies/G01/regime_filter.py` — daily tradeability check
- `Strategies/G01/strength_scorer.py` — signal quality scoring
- `Paper/GoldPaperTrader.py` — live paper trading (honors filter)
- `Strategies/G01/config.py` — has `gap_threshold: float = 0.025`

---

## What's Done

### Experiments (1-6)
- **Exp 1-5**: SUPER GOLD portfolio validated, +22.8% OOS net
- **Exp 6A-6F**: 2.5% gap filter validated on full 7-stock OOS
  - Net: +48.0% (vs +48.56% baseline — equal)
  - PF: 2.872 (vs 2.359 — +22%)
  - DD: -4.44% (vs -5.76% — -23%)
  - Trades: 105 (vs 132 — -20%)

### Dev Setup
- ruff + black + pre-commit installed
- 357 ruff issues auto-fixed
- 91 files reformatted
- Strategy regression test PASSED (same numbers after auto-fixes)

### Auto-Approval
- `.claude/settings.local.json` — 70+ commands whitelisted
- Dangerous ops blocked (rm -rf /, format, sudo)
- LOCAL ONLY (gitignored, never pushed)

---

## What's Next

1. **Paper trade during market hours** (9:15 AM - 3:30 PM IST)
2. Monitor live vs backtest for 2-4 weeks
3. If consistent → live trading with small capital
4. Consider adding 2-3 more NSE stocks if diversification needed

### Quick Start (Codespace)
```bash
cd /workspaces/fyers-trading-strategy
git pull
python Paper/GoldPaperTrader.py --symbols CGPOWER DRREDDY INDUSINDBK BHEL HCLTECH TITAN M&M
```

### Quick Start (Local)
```powershell
cd c:\Users\Tapan\IDirect\my-python-project\src\Fyers
py Paper/GoldPaperTrader.py --symbols CGPOWER DRREDDY INDUSINDBK BHEL HCLTECH TITAN M&M
```

---

## Data
- **Slim bundle** (`Data/_slim/`): 7 stocks, 1D+5MIN+1W, 34.4 MB
- **Full data** (`Data/{SYMBOL}/`): gitignored, ~500 MB
- **Codespace**: has slim bundle (pushed to repo)
- **Local**: has full data

---

## Memory Locations
- `C:\Users\Tapan\.claude\projects\...\memory\MEMORY.md` — index
- `current-focus.md` — active task
- `project-overview.md` — strategy summary
- `exp06-gap-filter.md` — Exp 6 details
- `dev-setup.md` — ruff/black/pre-commit
- `session-continuation-guide.md` — how to resume

---

## User Preferences (Recurring)
- Short, classy, crisp responses — no code in chat
- Read files directly, don't show code changes
- Be wild, try different combos/parameters
- Factor in real-world volatility
- Lead mission autonomously
- Always update memory/context as we go
