"""
Exp 6C: Out-of-sample validation of gap filter thresholds.

Tests the top 3 gap thresholds (1.5%, 2.0%, 2.5%) on the OOS period only:
- Train: 2021-01-01 to 2024-12-31
- Test (OOS): 2025-01-01 to today

Same 3-stock subset (CGPOWER, HDFCBANK, SUZLON) as Exp 6A/6B.
Uses exp06's run_scenario + entry_time filtering for OOS split.

Output: Research/GroqAnalysis/exp06c_<timestamp>.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exp06_news_filter import (
    PORTFOLIO_STOCKS,
    INDEX_SYMBOL,
    compute_gap_filter,
    run_gold_with_filter,
    calc_metrics,
    resolve_data_path,
    SLIM_DIR,
    DATA_DIR,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "Research" / "GroqAnalysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OOS_START = pd.Timestamp("2025-01-01")
TOP_THRESHOLDS = [0.015, 0.020, 0.025]


def run_scenario_filtered(name: str, blocked_dates: set, oos_only: bool = True) -> dict:
    """Run scenario, optionally filter to OOS only by entry_time."""
    print(f"\n--- Scenario: {name} ({len(blocked_dates)} dates blocked) ---")
    all_trades = []
    for sym in PORTFOLIO_STOCKS:
        t = run_gold_with_filter(sym, blocked_dates)
        if len(t) > 0 and oos_only and "entry_time" in t.columns:
            t = t[pd.to_datetime(t["entry_time"]) >= OOS_START].copy()
        if len(t) > 0:
            t["symbol"] = sym
            all_trades.append(t)
            print(f"  {sym}: {len(t)} trades (OOS)")
    if not all_trades:
        return {
            "scenario": name,
            "blocked_days": len(blocked_dates),
            "total_trades": 0,
            "net_return_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
        }
    combined = pd.concat(all_trades, ignore_index=True)
    metrics = calc_metrics(combined)
    metrics["scenario"] = name
    metrics["blocked_days"] = len(blocked_dates)
    print(
        f"  NET: {metrics['net_return_pct']:+.2f}%  |  "
        f"PF: {metrics['profit_factor']:.3f}  |  "
        f"DD: {metrics['max_drawdown_pct']:.2f}%  |  "
        f"Trades: {metrics['total_trades']}"
    )
    return metrics


def main() -> None:
    print("=" * 70)
    print("EXPERIMENT 6C: OOS VALIDATION (2025-01-01 onwards)")
    print("=" * 70)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Portfolio: {PORTFOLIO_STOCKS}")
    print(f"Index: {INDEX_SYMBOL}")
    print(f"OOS start: {OOS_START.date()}")
    print(f"Thresholds: {[f'{t:.1%}' for t in TOP_THRESHOLDS]}\n")

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

    # 1. Baseline OOS
    print("=" * 70)
    print("BASELINE (no filter) — OOS only")
    print("=" * 70)
    baseline = run_scenario_filtered("BASELINE_OOS", set(), oos_only=True)

    # 2. Threshold sweep OOS
    print()
    print("=" * 70)
    print("THRESHOLD SWEEP — OOS only")
    print("=" * 70)
    sweep_results = []
    for thresh in TOP_THRESHOLDS:
        gap_dates = compute_gap_filter(PORTFOLIO_STOCKS, gap_threshold=thresh)
        result = run_scenario_filtered(f"Gap > {thresh:.1%} (OOS)", gap_dates, oos_only=True)
        sweep_results.append(
            {
                "threshold": thresh,
                "blocked_dates": len(gap_dates),
                "net_pct": result["net_return_pct"],
                "profit_factor": result["profit_factor"],
                "max_drawdown_pct": result["max_drawdown_pct"],
                "win_rate_pct": result.get("win_rate_pct", 0),
                "trades": result["total_trades"],
            }
        )

    # 3. Summary
    print()
    print("=" * 70)
    print("OOS VALIDATION — SUMMARY")
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
        marker = "  <-- BEST NET" if r["net_pct"] == max(s["net_pct"] for s in sweep_results) else ""
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
    print("RECOMMENDATION (OOS 2025+)")
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

    # Sanity check: did the filter beat baseline OOS?
    baseline_net = baseline["net_return_pct"]
    print()
    if best_net["net_pct"] > baseline_net:
        print(
            f"✓ Gap filter IMPROVED OOS net: "
            f"{baseline_net:+.2f}% → {best_net['net_pct']:+.2f}% "
            f"(+{best_net['net_pct'] - baseline_net:.2f}%)"
        )
    else:
        print(
            f"✗ Gap filter did NOT improve OOS net: "
            f"{baseline_net:+.2f}% → {best_net['net_pct']:+.2f}% "
            f"({best_net['net_pct'] - baseline_net:+.2f}%)"
        )

    # Save
    out_path = OUT_DIR / f"exp06c_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(
        json.dumps(
            {
                "experiment": "exp06c_oos_validation",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "portfolio": PORTFOLIO_STOCKS,
                "oos_start": OOS_START.isoformat(),
                "thresholds_tested": TOP_THRESHOLDS,
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
