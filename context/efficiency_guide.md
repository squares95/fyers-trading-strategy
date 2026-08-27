# Efficiency & Effectiveness Guide for Trading System Development

## Overview
This document outlines strategies and tools to maximize productivity when developing trading systems, managing token usage, and maintaining code quality.

---

## 1. Claude Code Token Efficiency

### Installed Extensions
- **Continue** (VS Code) - AI code assistant with context management
- **Context7** (MCP) - Fetches fresh docs without bloating context

### Token-Saving Best Practices

#### Use Built-in Commands
- `/clear` - Reset conversation when starting fresh tasks
- `/context` - View current token usage
- `/help` - Get Claude Code help

#### Read-First Pattern
Before asking questions:
1. Use `Glob` to find files: `Glob("**/*.py")`
2. Use `Grep` to search: `Grep("pattern", type="py")`
3. Use `Read` with `head_limit` for large files

#### Context Management
- Keep context folder updated: `context/project_context.md`
- Save key facts to memory files for cross-session persistence
- Break complex tasks into multiple focused requests

#### Code Reading Efficiency
```python
# Instead of reading entire file:
Read("file.py", limit=50)  # First 50 lines

# Find specific function:
Grep("def function_name", type="py")  # Then read context around it

# Search across files:
Grep("class.*Strategy", type="py")
```

---

## 2. Code Organization for Novice Coders

### Modular Structure Goals
- One concept per file
- Clear file names describe purpose
- Extensive docstrings explaining WHY
- Type hints for self-documenting code

### File Naming Conventions
```
indicators.py      # Technical indicator calculations
signal_rules.py    # Entry/exit conditions
backtest.py        # Trade simulation
regime_filter.py   # Market condition checks
strength_scorer.py # Signal quality scoring
```

### Documentation Standards
```python
def calculate_rsi(close_prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI).
    
    RSI measures momentum based on recent price changes.
    - Values above 70 = overbought (potential sell)
    - Values below 30 = oversold (potential buy)
    
    Args:
        close_prices: Closing prices for the stock
        period: Lookback period for calculations (default: 14)
    
    Returns:
        Series with RSI values (0-100)
    
    Why this matters:
        RSI helps identify potential reversal points.
        High RSI suggests stock may be due for a pullback.
    """
```

---

## 3. Development Workflow

### Session Start Template
```
1. Read context files:
   - context/project_context.md
   - context/session_continuation.md
   
2. Check memory files for ongoing tasks

3. State current goal clearly

4. Reference specific files by path
```

### Task Breakdown Strategy
Instead of: "Fix all bugs"
Do: "Fix the signal generation bug in Core.py lines 102-115"

### File Change Tracking
```markdown
## Changes Made (Session Date)
- File: Core.py
- Change: Extracted indicators to separate module
- Reason: Improves readability, enables re-use
- Impact: No breaking changes (backwards compatible)
```

---

## 4. Testing & Validation

### Code Before Asking for Help
- [ ] File has no syntax errors
- [ ] Imports are correct
- [ ] Type hints match actual usage
- [ ] Basic functionality tested manually

### Error Reporting Format
When reporting bugs:
```
File: Strategies/G01/Core.py
Line: ~102
Expected: signal should trigger when...
Actual: signal doesn't trigger because...
Error message: (if any)
```

---

## 5. Claude Code Extensions & Tools

### VS Code Extensions
- **Continue** - AI pair programming with context awareness
- **Context7** - Real-time library documentation
- **Python** - Intellisense, debugging, linting
- **Pylance** - Type checking, code navigation

### Claude Code Specific Features
- **MCP Servers** - Connect to external tools (databases, APIs)
- **Hooks** - Automate actions on events
- **Slash Commands** - Custom commands for frequent tasks
- **Workflows** - Chain complex operations

---

## 6. Project-Specific Efficiency Tips

### Trading System Development
- Backtest first, optimize later
- Use bootstrap simulations for robustness
- Test on out-of-sample data before live trading
- Paper trade before real money

### Data Management
- Cache processed data to avoid recalculation
- Use appropriate timeframes for strategy
- Validate data quality before backtesting

### Strategy Development
- Start simple, add complexity only when justified
- Document why each parameter was chosen
- Track performance across different market regimes
- Consider transaction costs from day one

---

## 7. Memory & Context Management

### When to Update Files
| Event | Update |
|-------|--------|
| Session end | context/session_continuation.md |
| New finding | context/strategy_notes.md |
| Project change | memory/project-overview.md |
| Efficiency tip | memory/token-efficiency-tips.md |

### Memory File Format
```markdown
---
name: unique-slug
description: One-line summary
metadata:
  type: user | feedback | project | reference
---

Content here...
```

---

## 8. Next Steps for This Project

### Immediate (Today)
- [ ] Refactor Core.py into modular chunks
- [ ] Refactor Gold.py into modular chunks
- [ ] Add beginner-friendly docstrings

### Short Term (This Week)
- [ ] Apply modularization to Paper/GoldPaperTrader.py
- [ ] Create architecture diagram
- [ ] Add unit tests for key modules

### Long Term
- [ ] Scale strategy to multiple symbols
- [ ] Add real-time monitoring
- [ ] Implement position sizing
- [ ] Build reporting dashboard
