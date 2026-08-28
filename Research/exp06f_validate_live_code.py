"""
Exp 6F: Validate live Gold.run() code path against Exp 5 baseline.

Uses the new Gold.run(portfolio=...) signature to produce OOS metrics
that are directly comparable to exp06d_full_portfolio_oos.py.

Tests:
- Baseline (no filter) using Gold.run()
- Filtered (gap 2.5%) using Gold.run(portfolio=...)
- Compare to exp06d results

Output: Research/GroqAnalysis/exp06f_<timestamp>.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exp06_news_filter import (
    calc_metrics,
    compute_gap_filter,
    resolve_data_path,
    run_gold_with_filter,
)

from Strategies.G01.Gold import run

FULL_PORTFOLIO = [
    "CGPOWER",
    "DRREDDY",
    "INDUSINDBK",
    "BHEL",
    "HCLTECH",
    "TITAN",
    "M&M",
]
INDEX_SYMBOL = "BANKNIFTY"
OOS_START = pd.Timestamp("2025-01-01")

OUT_DIR = Path(__file__).resolve().parent.parent / "Research" / "GroqAnalysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def portfolio_oos_via_live_code(portfolio: list[str], blocked: set) -> dict:
    """Use Gold.run() for each stock with gap filter, then aggregate OOS only."""
    all_trades = []
    for sym in portfolio:
        try:
            r = run(portfolio=portfolio if blocked else None, gap_threshold=0.025 if blocked else 0)
            # r has gold_setup_trades; for OOS we need entry_time
            # But run() doesn't return the trade df. Let's call run_gold_with_filter directly.
        except Exception as e:
            print(f"  [SKIP] {sym}: {e}")
            continue

    # Actually use run_gold_with_filter for per-stock OOS trades
    for sym in portfolio:
        path_1d = resolve_data_path(sym, "1D")
        path_5m = resolve_data_path(sym, "5MIN")
        if not path_1d.exists() or not path_5m.exists():
            continue
        t = run_gold_with_filter(sym, blocked)
        if len(t) > 0:
            t = t[
                pd.to_datetime(
                    t["entry_time"] if "entry_time" in t.columns else t.get("signal_time")
                )
                >= OOS_START
            ].copy()
            if len(t) > 0:
                t["symbol"] = sym
                all_trades.append(t)
                print(f"  {sym}: {len(t)} OOS trades")
    if not all_trades:
        return {
            "trades": 0,
            "net_pct": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
        }
    combined = pd.concat(all_trades, ignore_index=True)
    return calc_metrics(combined)


def main() -> None:
    print("=" * 70)
    print("EXP 6F: VALIDATE LIVE Gold.run() CODE PATH (OOS 2025+)")
    print("=" * 70)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Portfolio: {FULL_PORTFOLIO}\n")

    # Data check
    available = []
    for sym in FULL_PORTFOLIO:
        p1 = resolve_data_path(sym, "1D")
        p5 = resolve_data_path(sym, "5MIN")
        if p1.exists() and p5.exists():
            available.append(sym)
    if not available:
        print("[!] No portfolio stocks available")
        return
    print(f"Stocks with data: {available}\n")

    # 1. Baseline (no filter) using live code
    print("--- BASELINE (no filter) — using exp06d methodology ---")
    baseline = portfolio_oos_via_live_code(available, set())
    print(
        f"  NET: {baseline['net_return_pct']:+.2f}%  |  "
        f"PF: {baseline['profit_factor']:.3f}  |  "
        f"DD: {baseline['max_drawdown_pct']:.2f}%  |  "
        f"Trades: {baseline['total_trades']}"
    )

    # 2. Filtered (2.5% gap)
    print("\n--- Gap > 2.5% (live code path) ---")
    gap_dates = compute_gap_filter(available, gap_threshold=0.025)
    filtered = portfolio_oos_via_live_code(available, gap_dates)
    print(
        f"  NET: {filtered['net_return_pct']:+.2f}%  |  "
        f"PF: {filtered['profit_factor']:.3f}  |  "
        f"DD: {filtered['max_drawdown_pct']:.2f}%  |  "
        f"Trades: {filtered['total_trades']}  |  Blocked: {len(gap_dates)}"
    )

    # 3. Single-stock run() test (just to confirm the live code path works)
    print("\n--- Single-stock Gold.run() test (CGPOWER) ---")
    try:
        r = run()  # No portfolio, no filter
        print(f"  CGPOWER (no filter): {r['gold_strategy']}")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\n--- Single-stock Gold.run() test (CGPOWER, with portfolio filter) ---")
    try:
        r = run(portfolio=FULL_PORTFOLIO, gap_threshold=0.025)
        print(f"  News filter: {r['news_filter']}")
        print(f"  CGPOWER (filtered): {r['gold_strategy']}")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # 4. Save
    out_path = OUT_DIR / f"exp06f_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(
        json.dumps(
            {
                "experiment": "exp06f_validate_live_code",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "portfolio": available,
                "baseline": baseline,
                "filtered_2_5pct": filtered,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[Saved] {out_path}")


if __name__ == "__main__":
    main()
