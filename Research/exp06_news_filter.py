"""
Experiment 6: News/Sentiment Integration (Regime Crisis Filter)

Goal: Add real-world volatility awareness to SUPER GOLD portfolio.
Skip days that look like news-driven chaos (gap days, crash days).

We don't have a free news API, so we use:
1. Gap filter: skip days where any portfolio stock opens >2% from prev close
2. Crash filter: skip if previous day Nifty/BANKNIFTY dropped >2%
3. Combined filter: skip if either condition triggers

Hypothesis: Avoiding chaos days improves Sharpe and reduces drawdown
without sacrificing much upside.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

# Use absolute paths based on this file's location so the script works
# regardless of CWD (e.g., when run as `python Research/exp06_news_filter.py`)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "Data"


# Portfolio from Exp 4/5 (locked)
PORTFOLIO_STOCKS = [
    "CGPOWER", "DRREDDY", "INDUSINDBK", "BHEL",
    "HCLTECH", "TITAN", "M&M",
]

# Index for market-level crash filter
INDEX_SYMBOL = "BANKNIFTY"


def load_daily_ohlc(symbol: str) -> pd.DataFrame:
    """Load daily OHLC from 1D CSV. Uses absolute path."""
    path = DATA_DIR / symbol / f"{symbol}_1D.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Datetime"])
    df = df.sort_values("Datetime").reset_index(drop=True)
    df["date"] = df["Datetime"].dt.date.astype(str)
    return df


def compute_gap_filter(stocks: list[str], gap_threshold: float = 0.02) -> set:
    """
    Return set of dates where ANY portfolio stock gapped >threshold from prev close.
    These are "stock-specific chaos days" we want to skip.
    """
    chaos_dates = set()
    for sym in stocks:
        df = load_daily_ohlc(sym)
        if df.empty or len(df) < 5:
            continue
        df["prev_close"] = df["Close"].shift(1)
        df["gap_pct"] = (df["Open"] - df["prev_close"]) / df["prev_close"]
        gaps = df[df["gap_pct"].abs() > gap_threshold]
        chaos_dates.update(gaps["date"].astype(str).tolist())
    return chaos_dates


def compute_crash_filter(index_sym: str, crash_threshold: float = -0.02) -> set:
    """
    Return set of dates where the index had a >2% DOWN day the previous session.
    Trading today after a crash tends to be whipsaw.
    """
    df = load_daily_ohlc(index_sym)
    if df.empty or len(df) < 5:
        return set()
    df["prev_close"] = df["Close"].shift(1)
    df["prev_day_return"] = (df["Close"] - df["prev_close"]) / df["prev_close"]
    crash = df[df["prev_day_return"] < crash_threshold]
    return set(crash["date"].astype(str).tolist())


def compute_range_filter(stocks: list[str], range_threshold: float = 0.04) -> set:
    """
    Skip days where any stock had >4% intraday range the previous day
    (sign of volatility shock).
    """
    chaos_dates = set()
    for sym in stocks:
        df = load_daily_ohlc(sym)
        if df.empty or len(df) < 5:
            continue
        df["prev_range"] = ((df["High"] - df["Low"]) / df["Open"]).shift(1)
        wide = df[df["prev_range"] > range_threshold]
        chaos_dates.update(wide["date"].astype(str).tolist())
    return chaos_dates


def run_gold_with_filter(symbol: str, blocked_dates: set) -> pd.DataFrame:
    """Run SUPER GOLD on a stock, blocking signals on filtered dates."""
    try:
        from Strategies.G01.features import prepare_features
        from Strategies.G01.signals import generate_signals
        from Strategies.G01.backtest import backtest
        from Strategies.G01.regime_filter import daily_regime_table
        from Strategies.G01.strength_scorer import signal_strength_table
        from Strategies.G01.Gold import get_super_gold_config

        data_path = DATA_DIR / symbol / f"{symbol}_5MIN.csv"
        if not data_path.exists():
            return pd.DataFrame()

        config = get_super_gold_config()
        df = prepare_features(data_path)
        signals = generate_signals(df, config)
        if len(signals) == 0:
            return pd.DataFrame()

        regime = daily_regime_table(df)
        tradeable = set(regime.loc[regime["regime_tradeable"], "date"])
        signals = signals[signals["date"].isin(tradeable)].copy()
        if len(signals) == 0:
            return pd.DataFrame()

        # Apply news/crisis filter
        signals = signals[~signals["date"].isin(blocked_dates)].copy()
        if len(signals) == 0:
            return pd.DataFrame()

        strength = signal_strength_table(df, signals, config)
        signals = signals.merge(
            strength[['date', 'direction', 'signal_strength', 'strength_trigger_component']],
            on=['date', 'direction'], how='left'
        )
        signals = signals[
            (signals['signal_strength'] >= 45) &
            (signals['strength_trigger_component'] >= 0.15)
        ].copy()
        if len(signals) == 0:
            return pd.DataFrame()

        trades = backtest(df, signals, config)
        trades['symbol'] = symbol
        return trades
    except Exception as e:
        return pd.DataFrame()


def calc_metrics(trades_df: pd.DataFrame) -> dict:
    if len(trades_df) == 0:
        return {"total_trades": 0, "net_return_pct": 0, "profit_factor": 0,
                "win_rate_pct": 0, "max_drawdown_pct": 0}
    net = trades_df['net_return'] * 100
    wins = trades_df[trades_df['net_return'] > 0]
    losses = trades_df[trades_df['net_return'] <= 0]
    gross_p = wins['net_return'].sum() * 100 if len(wins) else 0
    gross_l = abs(losses['net_return'].sum() * 100) if len(losses) else 0
    pf = gross_p / gross_l if gross_l > 0 else float('inf')
    cum = trades_df.sort_values('entry_time')['net_return'].cumsum() * 100
    dd = (cum - cum.cummax()).min()
    return {
        "total_trades": int(len(trades_df)),
        "net_return_pct": round(net.sum(), 2),
        "profit_factor": round(pf, 3),
        "win_rate_pct": round((trades_df['net_return'] > 0).mean() * 100, 1),
        "max_drawdown_pct": round(dd, 2),
        "avg_trade_pct": round(net.mean(), 3),
    }


def run_scenario(name: str, blocked_dates: set) -> dict:
    print(f"\n--- Scenario: {name} ({len(blocked_dates)} dates blocked) ---")
    all_trades = []
    for sym in PORTFOLIO_STOCKS:
        t = run_gold_with_filter(sym, blocked_dates)
        if len(t) > 0:
            all_trades.append(t)
            print(f"  {sym}: {len(t)} trades")
    if not all_trades:
        return {"scenario": name, "blocked_days": len(blocked_dates), "metrics": {}}
    combined = pd.concat(all_trades, ignore_index=True)
    metrics = calc_metrics(combined)
    metrics['scenario'] = name
    metrics['blocked_days'] = len(blocked_dates)
    print(f"  NET: {metrics['net_return_pct']:+.2f}%  |  PF: {metrics['profit_factor']}  |  "
          f"DD: {metrics['max_drawdown_pct']}%  |  Trades: {metrics['total_trades']}")
    return metrics


def main():
    print("="*70)
    print("EXPERIMENT 6: NEWS/SENTIMENT REGIME FILTER")
    print("="*70)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Portfolio: {PORTFOLIO_STOCKS}")
    print(f"Index for crash filter: {INDEX_SYMBOL}\n")

    # 0. Verify data presence
    print("Checking data files...")
    missing = []
    for sym in PORTFOLIO_STOCKS + [INDEX_SYMBOL]:
        daily = DATA_DIR / sym / f"{sym}_1D.csv"
        minute = DATA_DIR / sym / f"{sym}_5MIN.csv"
        if not daily.exists() and not minute.exists():
            missing.append(sym)
    if missing:
        print(f"\n[!] MISSING DATA for: {missing}")
        print(f"    Data dir: {DATA_DIR}")
        print("    Data files are gitignored. Upload them OR run Fyers download:")
        print()
        for sym in missing:
            print(f"    python Main.py   # with SYMBOLS=['{sym}'] ACTION='download'")
        print()
        return
    print("  All data files present\n")

    # 1. Build filter sets
    print("Building filter sets from daily candles...")
    gap_dates = compute_gap_filter(PORTFOLIO_STOCKS, gap_threshold=0.02)
    crash_dates = compute_crash_filter(INDEX_SYMBOL, crash_threshold=-0.02)
    range_dates = compute_range_filter(PORTFOLIO_STOCKS, range_threshold=0.04)

    print(f"  Gap>2% dates:      {len(gap_dates)} unique days")
    print(f"  Crash>2% dates:    {len(crash_dates)} unique days")
    print(f"  Range>4% dates:    {len(range_dates)} unique days")

    # 2. Run baseline (no filter)
    baseline = run_scenario("BASELINE (no filter)", set())

    # 3. Run each filter individually
    gap_only = run_scenario("GAP>2% filter", gap_dates)
    crash_only = run_scenario("CRASH>-2% filter", crash_dates)
    range_only = run_scenario("RANGE>4% filter", range_dates)

    # 4. Combined filter
    combined_dates = gap_dates | crash_dates | range_dates
    combined = run_scenario("COMBINED (gap|crash|range)", combined_dates)

    # 5. Stricter combined
    strict_dates = (gap_dates & crash_dates) | range_dates
    strict = run_scenario("STRICT (gap&crash | range)", strict_dates)

    # 6. Summary comparison
    print("\n" + "="*70)
    print("SCENARIO COMPARISON")
    print("="*70)
    print(f"{'Scenario':<35} {'Trades':>7} {'Net%':>8} {'PF':>7} {'DD%':>7}")
    print("-"*70)
    for r in [baseline, gap_only, crash_only, range_only, combined, strict]:
        m = r.get('metrics', r)
        if not m or m.get('total_trades', 0) == 0:
            continue
        print(f"{m.get('scenario','?'):<35} {m['total_trades']:>7} "
              f"{m['net_return_pct']:>+7.2f}% {m['profit_factor']:>7.3f} {m['max_drawdown_pct']:>7.2f}")

    # 7. Save results
    output_dir = Path("Research/GroqAnalysis")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {
        "experiment": "exp06_news_filter",
        "timestamp": ts,
        "filter_stats": {
            "gap_dates": len(gap_dates),
            "crash_dates": len(crash_dates),
            "range_dates": len(range_dates),
            "combined": len(combined_dates),
            "strict": len(strict_dates),
        },
        "scenarios": {
            "baseline": baseline.get('metrics', baseline),
            "gap_only": gap_only.get('metrics', gap_only),
            "crash_only": crash_only.get('metrics', crash_only),
            "range_only": range_only.get('metrics', range_only),
            "combined": combined.get('metrics', combined),
            "strict": strict.get('metrics', strict),
        }
    }
    with open(output_dir / f"exp06_{ts}.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[Saved] Research/GroqAnalysis/exp06_{ts}.json")

    # 8. Recommendation
    print("\n" + "="*70)
    print("RECOMMENDATION")
    print("="*70)
    base_net = baseline.get('metrics', baseline).get('net_return_pct', 0)
    base_dd = baseline.get('metrics', baseline).get('max_drawdown_pct', 0)
    print(f"Baseline: {base_net:+.2f}% net, {base_dd}% DD")
    for r in [gap_only, crash_only, range_only, combined, strict]:
        m = r.get('metrics', r)
        if not m or m.get('total_trades', 0) == 0:
            continue
        name = m.get('scenario', '?')
        net = m['net_return_pct']
        dd = m['max_drawdown_pct']
        verdict = ""
        if net > base_net and dd > base_dd:
            verdict = "  ** WINNER (better both) **"
        elif dd > base_dd * 1.1 and net > base_net * 0.9:
            verdict = "  * Improved DD, slight net trade-off *"
        print(f"  {name}: {net:+.2f}% net, {dd}% DD{verdict}")


if __name__ == "__main__":
    main()
