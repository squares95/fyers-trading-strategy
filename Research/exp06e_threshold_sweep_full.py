"""
Exp 6E: Test multiple gap thresholds on full 7-stock portfolio OOS.

Tests 1.0%, 1.5%, 2.0%, 2.5%, 3.0% on the full SUPER GOLD portfolio.
Finds the best balance of net return, profit factor, and max drawdown.

Output: Research/GroqAnalysis/exp06e_<timestamp>.json
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
THRESHOLDS = [0.010, 0.015, 0.020, 0.025, 0.030]

OUT_DIR = Path(__file__).resolve().parent.parent / "Research" / "GroqAnalysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_scenario_full(symbols, blocked, label):
    """Run scenario, return metrics (OOS only)."""
    all_trades = []
    for sym in symbols:
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
    if not all_trades:
        return {
            "scenario": label,
            "blocked_days": len(blocked),
            "total_trades": 0,
            "net_return_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
        }
    combined = pd.concat(all_trades, ignore_index=True)
    metrics = calc_metrics(combined)
    metrics["scenario"] = label
    metrics["blocked_days"] = len(blocked)
    return metrics


def main():
    print("=" * 70)
    print("EXP 6E: GAP THRESHOLD SWEEP — FULL 7-STOCK PORTFOLIO (OOS)")
    print("=" * 70)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Portfolio: {FULL_PORTFOLIO}")
    print(f"Thresholds: {[f'{t:.1%}' for t in THRESHOLDS]}\n")

    # 0. Data check
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

    # 1. Baseline
    print("--- BASELINE (no filter) ---")
    baseline = run_scenario_full(available, set(), "BASELINE")
    print(
        f"  NET: {baseline['net_return_pct']:+.2f}%  |  "
        f"PF: {baseline['profit_factor']:.3f}  |  "
        f"DD: {baseline['max_drawdown_pct']:.2f}%  |  "
        f"Trades: {baseline['total_trades']}"
    )

    # 2. Threshold sweep
    print()
    sweep_results = []
    for thresh in THRESHOLDS:
        gap_dates = compute_gap_filter(available, gap_threshold=thresh)
        result = run_scenario_full(available, gap_dates, f"Gap > {thresh:.1%}")
        sweep_results.append(
            {
                "threshold": thresh,
                "blocked_dates": len(gap_dates),
                "net_pct": result["net_return_pct"],
                "profit_factor": result["profit_factor"],
                "max_drawdown_pct": result["max_drawdown_pct"],
                "trades": result["total_trades"],
            }
        )
        print(
            f"  Gap > {thresh:.1%}: NET {result['net_return_pct']:+.2f}% | "
            f"PF {result['profit_factor']:.3f} | DD {result['max_drawdown_pct']:.2f}% | "
            f"Trades {result['total_trades']} | Blocked {len(gap_dates)}"
        )

    # 3. Summary
    print()
    print("=" * 70)
    print("FULL-PORTFOLIO OOS — SUMMARY")
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
        marker = ""
        if r["net_pct"] == max(s["net_pct"] for s in sweep_results):
            marker = "  <-- BEST NET"
        elif r["profit_factor"] == max(s["profit_factor"] for s in sweep_results):
            marker = "  <-- BEST PF"
        elif r["max_drawdown_pct"] == max(s["max_drawdown_pct"] for s in sweep_results):
            marker = "  <-- BEST DD"
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
    best_dd = max(sweep_results, key=lambda s: s["max_drawdown_pct"])

    print()
    print("=" * 70)
    print("RECOMMENDATION (FULL PORTFOLIO, OOS 2025+)")
    print("=" * 70)
    print(
        f"BEST NET:  {best_net['threshold']:.1%} → {best_net['net_pct']:+.2f}% net, "
        f"PF {best_net['profit_factor']:.3f}, DD {best_net['max_drawdown_pct']:.2f}%"
    )
    print(
        f"BEST PF:   {best_pf['threshold']:.1%} → {best_pf['profit_factor']:.3f} PF, "
        f"{best_pf['net_pct']:+.2f}% net"
    )
    print(
        f"BEST DD:   {best_dd['threshold']:.1%} → {best_dd['max_drawdown_pct']:.2f}% DD, "
        f"{best_dd['net_pct']:+.2f}% net"
    )

    # Composite score: net (0.5) + PF (0.3) + DD (0.2)
    # Normalize each 0-1 by min-max across the sweep + baseline
    all_results = [baseline] + sweep_results
    all_nets = [r.get("net_pct", r.get("net_return_pct", 0)) for r in all_results]
    all_pfs = [r.get("profit_factor", 0) for r in all_results]
    all_dds = [r.get("max_drawdown_pct", 0) for r in all_results]
    # Higher net = better, higher PF = better, less negative DD = better

    def normalize(values, higher_better=True):
        vmin, vmax = min(values), max(values)
        if vmax == vmin:
            return [0.5] * len(values)
        normed = [(v - vmin) / (vmax - vmin) for v in values]
        if not higher_better:
            normed = [1 - n for n in normed]
        return normed

    net_norm = normalize(all_nets, higher_better=True)
    pf_norm = normalize(all_pfs, higher_better=True)
    dd_norm = normalize(all_dds, higher_better=True)  # -5 > -10 so higher is better
    composite = [0.5 * n + 0.3 * p + 0.2 * d for n, p, d in zip(net_norm, pf_norm, dd_norm)]

    print()
    print("=" * 70)
    print("COMPOSITE SCORE (50% net + 30% PF + 20% DD)")
    print("=" * 70)
    scenarios = ["BASELINE"] + [f"{r['threshold']:.1%}" for r in sweep_results]
    for s, c in zip(scenarios, composite):
        marker = "  <-- BEST COMPOSITE" if c == max(composite) else ""
        print(f"  {s:<12} {c:.3f}{marker}")

    best_composite_idx = composite.index(max(composite))
    best_composite = scenarios[best_composite_idx]
    print(f"\n>>> WINNER: {best_composite} <<<")

    # Save
    out_path = OUT_DIR / f"exp06e_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(
        json.dumps(
            {
                "experiment": "exp06e_threshold_sweep_full_portfolio",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "portfolio": available,
                "thresholds_tested": THRESHOLDS,
                "baseline": baseline,
                "sweep": sweep_results,
                "best_net": best_net,
                "best_pf": best_pf,
                "best_dd": best_dd,
                "best_composite": best_composite,
                "composite_scores": dict(zip(scenarios, composite)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[Saved] {out_path}")


if __name__ == "__main__":
    main()
