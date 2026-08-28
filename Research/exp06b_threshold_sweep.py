"""
Exp 6B: Gap threshold sweep for SUPER GOLD

Tests 6 different gap thresholds to find the optimal one:
- 1.0%, 1.5%, 2.0%, 2.5%, 3.0%, 4.0%

Same 3-stock subset (CGPOWER, HDFCBANK, SUZLON) as Exp 6A.
Reuses exp06 logic via import.

Output: Research/GroqAnalysis/exp06b_<timestamp>.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import helpers from Exp 6A
from exp06_news_filter import (
    INDEX_SYMBOL,
    PORTFOLIO_STOCKS,
    SLIM_DIR,
    compute_gap_filter,
    resolve_data_path,
    run_scenario,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "Research" / "GroqAnalysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Thresholds to test
GAP_THRESHOLDS = [0.010, 0.015, 0.020, 0.025, 0.030, 0.040]


def main() -> None:
    print("=" * 70)
    print("EXPERIMENT 6B: GAP THRESHOLD SWEEP")
    print("=" * 70)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Portfolio: {PORTFOLIO_STOCKS}")
    print(f"Index: {INDEX_SYMBOL}")
    print(f"Thresholds: {[f'{t:.1%}' for t in GAP_THRESHOLDS]}\n")

    # 0. Verify data
    print("Checking data files...")
    print(f"  Slim bundle: {SLIM_DIR} ({'present' if SLIM_DIR.exists() else 'NOT FOUND'})")
    missing = []
    for sym in PORTFOLIO_STOCKS + [INDEX_SYMBOL]:
        daily = resolve_data_path(sym, "1D")
        minute = resolve_data_path(sym, "5MIN")
        if not daily.exists() and not minute.exists():
            missing.append(sym)
        else:
            source = "slim" if str(SLIM_DIR) in str(daily) else "full"
            print(f"  [OK] {sym}: {daily.name} ({source})")
    if missing:
        print(f"\n[!] MISSING: {missing}")
        return
    print("  All data files present\n")

    # 1. Baseline
    print("=" * 70)
    print("BASELINE (no filter)")
    print("=" * 70)
    baseline = run_scenario("BASELINE", set())
    print(
        f"  NET: {baseline['net_return_pct']:+.2f}%  |  "
        f"PF: {baseline['profit_factor']:.3f}  |  "
        f"DD: {baseline['max_drawdown_pct']:.2f}%  |  "
        f"Trades: {baseline['total_trades']}"
    )

    # 2. Threshold sweep
    print()
    sweep_results = []
    for thresh in GAP_THRESHOLDS:
        gap_dates = compute_gap_filter(PORTFOLIO_STOCKS, gap_threshold=thresh)
        scenario_name = f"Gap > {thresh:.1%}"
        result = run_scenario(scenario_name, gap_dates)
        sweep_results.append(
            {
                "threshold": thresh,
                "blocked_dates": len(gap_dates),
                "net_pct": result["net_return_pct"],
                "profit_factor": result["profit_factor"],
                "max_drawdown_pct": result["max_drawdown_pct"],
                "win_rate_pct": result.get("win_rate_pct", 0),
                "trades": result["total_trades"],
                "avg_trade_pct": result.get("avg_trade_pct", 0),
            }
        )

    # 3. Summary
    print()
    print("=" * 70)
    print("GAP THRESHOLD SWEEP — SUMMARY")
    print("=" * 70)
    print(f"{'Threshold':<12} {'Blocked':<8} {'Net%':<10} {'PF':<8} {'DD%':<8} {'Trades':<8}")
    print("-" * 70)
    print(
        f"{'BASELINE':<12} {0:<8} "
        f"{baseline['net_return_pct']:>+9.2f} "
        f"{baseline['profit_factor']:<8.3f} "
        f"{baseline['max_drawdown_pct']:<8.2f} "
        f"{baseline['total_trades']:<8}"
    )
    for r in sweep_results:
        marker = (
            "  <-- BEST NET" if r["net_pct"] == max(s["net_pct"] for s in sweep_results) else ""
        )
        print(
            f"{r['threshold']:.1%}      {r['blocked_dates']:<8} "
            f"{r['net_pct']:>+9.2f} "
            f"{r['profit_factor']:<8.3f} "
            f"{r['max_drawdown_pct']:<8.2f} "
            f"{r['trades']:<8}{marker}"
        )

    # 4. Recommendation
    best_net = max(sweep_results, key=lambda s: s["net_pct"])
    best_pf = max(sweep_results, key=lambda s: s["profit_factor"])
    best_dd = max(sweep_results, key=lambda s: s["max_drawdown_pct"])  # least negative
    print()
    print("=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    print(
        f"BEST NET:     {best_net['threshold']:.1%} → {best_net['net_pct']:+.2f}% net, "
        f"PF {best_net['profit_factor']:.3f}, DD {best_net['max_drawdown_pct']:.2f}%"
    )
    print(
        f"BEST PF:      {best_pf['threshold']:.1%} → {best_pf['profit_factor']:.3f} PF, "
        f"{best_pf['net_pct']:+.2f}% net"
    )
    print(
        f"LOWEST DD:    {best_dd['threshold']:.1%} → {best_dd['max_drawdown_pct']:.2f}% DD, "
        f"{best_dd['net_pct']:+.2f}% net"
    )

    # Save
    out_path = OUT_DIR / f"exp06b_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(
        json.dumps(
            {
                "experiment": "exp06b_gap_threshold_sweep",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "portfolio": PORTFOLIO_STOCKS,
                "thresholds_tested": GAP_THRESHOLDS,
                "baseline": baseline,
                "sweep": sweep_results,
                "best_net": best_net,
                "best_pf": best_pf,
                "best_dd": best_dd,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[Saved] {out_path}")


if __name__ == "__main__":
    main()
