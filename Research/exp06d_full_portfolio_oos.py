"""
Exp 6D: Full SUPER GOLD portfolio OOS validation with 2.5% gap filter.

Uses ALL 7 portfolio stocks (no slim-bundle restriction).
Reads from Data/{SYMBOL}/ directly — works on local machine with full data.
Can also work in codespace if all 7 stocks' 1D+5MIN are present.

Tests 2.5% gap (the validated best) on OOS 2025-01-01 onwards.
Also tests baseline for comparison.

Output: Research/GroqAnalysis/exp06d_<timestamp>.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exp06_news_filter import (
    compute_gap_filter,
    compute_crash_filter,
    calc_metrics,
    resolve_data_path,
    SLIM_DIR,
)

# FULL portfolio (all 7 from SUPER GOLD)
FULL_PORTFOLIO = [
    "CGPOWER", "DRREDDY", "INDUSINDBK", "BHEL",
    "HCLTECH", "TITAN", "M&M",
]
INDEX_SYMBOL = "BANKNIFTY"
OOS_START = "2025-01-01"

# We import run_gold_with_filter from exp06 — it uses resolve_data_path,
# which tries slim first, then full Data/. So on local this finds full data.
from exp06_news_filter import run_gold_with_filter

OUT_DIR = Path(__file__).resolve().parent.parent / "Research" / "GroqAnalysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_scenario_full(symbols: list[str], blocked: set, label: str) -> dict:
    print(f"\n--- {label} ---")
    all_trades = []
    for sym in symbols:
        # Use resolve_data_path (prefers slim bundle, falls back to full Data/)
        path_1d = resolve_data_path(sym, "1D")
        path_5m = resolve_data_path(sym, "5MIN")
        if not path_1d.exists() or not path_5m.exists():
            print(f"  [SKIP] {sym}: missing {path_1d.name} or {path_5m.name}")
            continue
        t = run_gold_with_filter(sym, blocked)
        if len(t) > 0:
            # Filter to OOS by entry_time
            import pandas as pd
            t = t[pd.to_datetime(t["entry_time"] if "entry_time" in t.columns else t.get("signal_time")) >= OOS_START].copy()
            if len(t) > 0:
                t["symbol"] = sym
                all_trades.append(t)
                print(f"  {sym}: {len(t)} trades (OOS)")
    if not all_trades:
        return {
            "scenario": label,
            "blocked_days": len(blocked),
            "total_trades": 0,
            "net_return_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
        }
    combined = __import__("pandas").concat(all_trades, ignore_index=True)
    metrics = calc_metrics(combined)
    metrics["scenario"] = label
    metrics["blocked_days"] = len(blocked)
    metrics["portfolio_size"] = len(symbols)
    print(
        f"  NET: {metrics['net_return_pct']:+.2f}%  |  "
        f"PF: {metrics['profit_factor']:.3f}  |  "
        f"DD: {metrics['max_drawdown_pct']:.2f}%  |  "
        f"Trades: {metrics['total_trades']}"
    )
    return metrics


def main() -> None:
    print("=" * 70)
    print("EXP 6D: FULL PORTFOLIO OOS WITH 2.5% GAP FILTER")
    print("=" * 70)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Portfolio (7 stocks): {FULL_PORTFOLIO}")
    print(f"Index: {INDEX_SYMBOL}")
    print(f"OOS start: {OOS_START}")
    print(f"Filter: 2.5% gap (validated best from Exp 6B/6C)\n")

    # Check which stocks have full data (slim bundle or full)
    print("Checking full data availability (slim or full path)...")
    available = []
    for sym in FULL_PORTFOLIO + [INDEX_SYMBOL]:
        p1 = resolve_data_path(sym, "1D")
        p5 = resolve_data_path(sym, "5MIN")
        has = p1.exists() and p5.exists()
        source = "slim" if str(SLIM_DIR) in str(p1) else "full"
        print(f"  {'[OK]' if has else '[MS]'} {sym}: 1D={p1.name} ({source}), 5MIN={p5.name} ({source})")
        if has:
            available.append(sym)
    if INDEX_SYMBOL not in available:
        print(f"\n⚠ Index {INDEX_SYMBOL} missing — crash filter will be empty.")
    if len(available) < len(FULL_PORTFOLIO):
        missing = [s for s in FULL_PORTFOLIO if s not in available]
        print(f"\n⚠ Missing portfolio stocks: {missing}")
        print("  Either download them or add to Data/_slim/ and run again.")
    print()

    # Use available stocks for the test
    test_stocks = [s for s in FULL_PORTFOLIO if s in available]
    if not test_stocks:
        print("[!] No portfolio stocks available — aborting.")
        return
    print(f"Testing with available stocks: {test_stocks}\n")

    # 1. Baseline (no filter) on available stocks
    baseline = run_scenario_full(test_stocks, set(), "BASELINE_OOS")

    # 2. 2.5% gap filter on available stocks
    gap_dates = compute_gap_filter(test_stocks, gap_threshold=0.025)
    filtered = run_scenario_full(test_stocks, gap_dates, "Gap > 2.5% (OOS)")

    # 3. Recommendation
    print()
    print("=" * 70)
    print("RECOMMENDATION — FULL PORTFOLIO")
    print("=" * 70)
    if filtered["net_return_pct"] > baseline["net_return_pct"]:
        print(f"✓ FILTER IMPROVES OOS NET: {baseline['net_return_pct']:+.2f}% → {filtered['net_return_pct']:+.2f}%")
    else:
        print(f"✗ FILTER DECREASES OOS NET: {baseline['net_return_pct']:+.2f}% → {filtered['net_return_pct']:+.2f}%")
    print(f"  Baseline:  {baseline['net_return_pct']:+.2f}% net, PF {baseline['profit_factor']:.3f}, DD {baseline['max_drawdown_pct']:.2f}%")
    print(f"  Filtered:  {filtered['net_return_pct']:+.2f}% net, PF {filtered['profit_factor']:.3f}, DD {filtered['max_drawdown_pct']:.2f}%")

    # Save
    out_path = OUT_DIR / f"exp06d_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(
        json.dumps(
            {
                "experiment": "exp06d_full_portfolio_oos_2_5pct",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "portfolio_full": FULL_PORTFOLIO,
                "portfolio_tested": test_stocks,
                "filter": "gap > 2.5%",
                "oos_start": OOS_START,
                "baseline": baseline,
                "filtered": filtered,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[Saved] {out_path}")


if __name__ == "__main__":
    main()
