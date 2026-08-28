"""Rank liquid stocks on stable intraday behavior without opening the final holdout."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from Research.CGPOWER import cgpower_session_microstructure as sm

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SYMBOLS = (
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "RELIANCE",
    "INFY",
    "LT",
    "TCS",
    "BEL",
    "BHARTIARTL",
    "M&M",
    "TITAN",
    "HCLTECH",
    "BAJFINANCE",
)
BANK_SYMBOLS = {"HDFCBANK", "ICICIBANK", "SBIN"}
PREVIOUSLY_EXAMINED = {"HDFCBANK", "SBIN"}
FINAL_HOLDOUT_SESSIONS = 60
SCREENER_AS_OF = "2026-08-18"
SCREENER_CONTEXT = {
    "HDFCBANK": "Bank; evaluated separately from ROCE screen",
    "ICICIBANK": "Bank; evaluated separately from ROCE screen",
    "SBIN": "Bank; evaluated separately from ROCE screen",
    "RELIANCE": "Liquid large-cap control",
    "INFY": "Passed large-cap growth and ROCE screen",
    "LT": "Liquid industrial control",
    "TCS": "Passed large-cap growth and ROCE screen",
    "BEL": "Passed large-cap growth and ROCE screen",
    "BHARTIARTL": "Passed large-cap growth and ROCE screen",
    "M&M": "Passed large-cap growth and ROCE screen",
    "TITAN": "Passed large-cap growth and ROCE screen",
    "HCLTECH": "Passed large-cap growth and ROCE screen",
    "BAJFINANCE": "High-beta liquid financial control",
}


def CandlePath(symbol: str) -> Path:
    return ROOT / "Data" / symbol / f"{symbol}_1MIN.csv"


def LoadValidMinutes(symbol: str) -> pd.DataFrame:
    path = CandlePath(symbol)
    if not path.exists():
        raise FileNotFoundError(f"Missing 1MIN data for {symbol}: {path}")
    return sm.valid_sessions(sm.load_minutes(path))


def CommonTradingDates(data: dict[str, pd.DataFrame]) -> list[pd.Timestamp]:
    date_sets = [set(frame["Date"].unique()) for frame in data.values()]
    common = sorted(set.intersection(*date_sets))
    if len(common) <= FINAL_HOLDOUT_SESSIONS + 80:
        raise ValueError(f"Only {len(common)} common full sessions; more history is required")
    return [pd.Timestamp(value) for value in common]


def ResearchBoundaries(common_dates: list[pd.Timestamp]) -> dict[str, pd.Timestamp]:
    sealed_start_index = len(common_dates) - FINAL_HOLDOUT_SESSIONS
    selection_dates = common_dates[:sealed_start_index]
    development_end_index = max(79, int(len(selection_dates) * 0.70) - 1)
    if development_end_index >= len(selection_dates) - 20:
        raise ValueError("Not enough validation sessions before the sealed holdout")
    return {
        "common_start": common_dates[0],
        "development_end": selection_dates[development_end_index],
        "validation_start": selection_dates[development_end_index + 1],
        "selection_end": selection_dates[-1],
        "sealed_start": common_dates[sealed_start_index],
        "common_end": common_dates[-1],
    }


def MetricRows(
    family: str,
    development: pd.DataFrame,
    validation: pd.DataFrame,
    parameters: dict[str, object],
) -> list[dict[str, object]]:
    return [
        {
            "Family": family,
            "Sample": "Development",
            **parameters,
            **sm.metrics(development),
        },
        {
            "Family": family,
            "Sample": "Validation",
            **parameters,
            **sm.metrics(validation),
        },
    ]


def FrozenStrategyResults(
    daily: pd.DataFrame,
    minutes: pd.DataFrame,
    boundaries: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    dev_end = boundaries["development_end"]
    val_start = boundaries["validation_start"]
    selection_end = boundaries["selection_end"]
    discovery = daily[daily.index <= dev_end]
    rvol_cutoff = float(discovery["opening15_rvol20"].median())
    if not np.isfinite(rvol_cutoff):
        rvol_cutoff = 0.0

    rows: list[dict[str, object]] = []
    opening_rule = sm.Rule("opening_drive", 0.15, 0.70, 0.50, 2.0)
    rows.extend(
        MetricRows(
            "opening_drive",
            sm.evaluate_rule(opening_rule, daily, minutes, rvol_cutoff, end=dev_end),
            sm.evaluate_rule(
                opening_rule,
                daily,
                minutes,
                rvol_cutoff,
                start=val_start,
                end=selection_end,
            ),
            {"Parameters": json.dumps({"target_r": 2.0, "rvol": "dev_median"})},
        )
    )

    benchmark_aligned = daily[
        (np.sign(daily["r15"]) == np.sign(daily["nifty_r15"]))
        & (daily["nifty_r15"].abs() >= 0.0005)
    ]
    rows.extend(
        MetricRows(
            "benchmark_aligned_opening",
            sm.evaluate_rule(opening_rule, benchmark_aligned, minutes, rvol_cutoff, end=dev_end),
            sm.evaluate_rule(
                opening_rule,
                benchmark_aligned,
                minutes,
                rvol_cutoff,
                start=val_start,
                end=selection_end,
            ),
            {
                "Parameters": json.dumps(
                    {"target_r": 2.0, "rvol": "dev_median", "benchmark_15m": "same_direction_5bp"}
                )
            },
        )
    )

    rows.extend(
        MetricRows(
            "opening_range_breakout",
            sm.evaluate_orb_rule(
                daily,
                minutes,
                "11:30",
                "opposite_boundary",
                1.5,
                0.0,
                0.70,
                False,
                end=dev_end,
            ),
            sm.evaluate_orb_rule(
                daily,
                minutes,
                "11:30",
                "opposite_boundary",
                1.5,
                0.0,
                0.70,
                False,
                start=val_start,
                end=selection_end,
            ),
            {"Parameters": json.dumps({"target_r": 1.5, "latest": "11:30"})},
        )
    )

    rows.extend(
        MetricRows(
            "two_sided_liquidity_sweep",
            sm.evaluate_sweep_rule(
                daily,
                minutes,
                "14:30",
                "midpoint",
                1.0,
                0.0,
                end=dev_end,
            ),
            sm.evaluate_sweep_rule(
                daily,
                minutes,
                "14:30",
                "midpoint",
                1.0,
                0.0,
                start=val_start,
                end=selection_end,
            ),
            {"Parameters": json.dumps({"target_r": 1.0, "latest": "14:30"})},
        )
    )
    return pd.DataFrame(rows)


def BestFrozenFamily(results: pd.DataFrame) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for family, group in results.groupby("Family", sort=False):
        development = group[group["Sample"] == "Development"].iloc[0]
        validation = group[group["Sample"] == "Validation"].iloc[0]
        floor_pf = min(
            float(np.nan_to_num(development["ProfitFactor"], nan=0.0, posinf=3.0)),
            float(np.nan_to_num(validation["ProfitFactor"], nan=0.0, posinf=3.0)),
        )
        both_positive = bool(development["Expectancy"] > 0 and validation["Expectancy"] > 0)
        min_trades = int(min(development["Trades"], validation["Trades"]))
        candidates.append(
            {
                "BestFamily": family,
                "StrategyFloorPF": floor_pf,
                "StrategyBothPositive": both_positive,
                "DevelopmentTrades": int(development["Trades"]),
                "ValidationTrades": int(validation["Trades"]),
                "DevelopmentWinRate": float(development["WinRate"]),
                "ValidationWinRate": float(validation["WinRate"]),
                "DevelopmentPF": float(development["ProfitFactor"]),
                "ValidationPF": float(validation["ProfitFactor"]),
                "DevelopmentExpectancy": float(development["Expectancy"]),
                "ValidationExpectancy": float(validation["Expectancy"]),
                "DevelopmentMaxDrawdown": float(development["MaxDrawdown"]),
                "ValidationMaxDrawdown": float(validation["MaxDrawdown"]),
                "FamilySelectionScore": (2.0 if both_positive else 0.0)
                + min(floor_pf, 3.0)
                + min(min_trades, 30) / 100,
            }
        )
    return max(candidates, key=lambda row: row["FamilySelectionScore"])


def UnitScore(value: float, low: float, high: float) -> float:
    if not np.isfinite(value) or high <= low:
        return 0.0
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def ReliabilityScore(row: dict[str, object]) -> float:
    benchmark = 0.65 * UnitScore(float(row["BenchmarkCorrelation"]), 0.30, 0.80)
    benchmark += 0.35 * UnitScore(float(row["BenchmarkDirectionMatch"]), 0.55, 0.80)
    acceptance = UnitScore(float(row["OneSidedAcceptance"]), 0.50, 0.75)
    low_noise = UnitScore(0.45 - float(row["TwoSidedBreakRate"]), 0.0, 0.30)
    range_quality = UnitScore(float(row["MedianIntradayRange"]), 0.010, 0.030)
    strategy = UnitScore(float(row["StrategyFloorPF"]), 0.70, 1.50)
    if not bool(row["StrategyBothPositive"]):
        strategy *= 0.35
    return round(
        100
        * (
            0.20 * benchmark
            + 0.15 * acceptance
            + 0.10 * low_noise
            + 0.15 * range_quality
            + 0.40 * strategy
        ),
        2,
    )


def BehaviorSummary(
    symbol: str,
    daily: pd.DataFrame,
    best: dict[str, object],
    boundaries: dict[str, pd.Timestamp],
) -> dict[str, object]:
    selection = daily.loc[: boundaries["selection_end"]].dropna(subset=["nifty_daily_return"])
    matched = selection.dropna(subset=["nifty_daily_return", "nifty_r15"])
    one_sided = selection[selection["break_type"].isin(["high_only", "low_only"])]
    accepted = ((one_sided["break_type"] == "high_only") & one_sided["close_above_or"]) | (
        (one_sided["break_type"] == "low_only") & one_sided["close_below_or"]
    )
    directional_open = selection[selection["r15_atr"].abs() >= 0.15]
    row: dict[str, object] = {
        "Symbol": symbol,
        "Benchmark": "BANKNIFTY" if symbol in BANK_SYMBOLS else "NIFTY",
        "SessionsUsed": len(selection),
        "PreviouslyExamined": symbol in PREVIOUSLY_EXAMINED,
        "ScreenerContext": SCREENER_CONTEXT[symbol],
        "BenchmarkCorrelation": matched["daily_return"].corr(matched["nifty_daily_return"]),
        "BenchmarkDirectionMatch": (
            np.sign(matched["daily_return"]) == np.sign(matched["nifty_daily_return"])
        ).mean(),
        "Opening15DirectionMatch": (
            np.sign(matched["r15"]) == np.sign(matched["nifty_r15"])
        ).mean(),
        "MedianIntradayRange": (selection["High"] / selection["Low"] - 1).median(),
        "MedianAbsFirst30": selection["r30"].abs().median(),
        "MedianTurnoverCr": (selection["Close"] * selection["Volume"]).median() / 10_000_000,
        "OneSidedAcceptance": accepted.mean(),
        "TwoSidedBreakRate": selection["break_type"]
        .isin(["high_then_low", "low_then_high"])
        .mean(),
        "DirectionalOpenContinuation": (
            np.sign(directional_open["r15"]) == np.sign(directional_open["r_after15"])
        ).mean(),
        "ExtremeGapCount": int((selection["gap"].abs() > 0.15).sum()),
        **best,
    }
    row["SelectionGate"] = bool(
        row["StrategyBothPositive"]
        and row["StrategyFloorPF"] >= 1.05
        and row["DevelopmentTrades"] >= 15
        and row["ValidationTrades"] >= 10
        and row["MedianIntradayRange"] >= 0.012
        and row["MedianTurnoverCr"] >= 100
    )
    row["ReliabilityScore"] = ReliabilityScore(row)
    return row


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    loaded = {symbol: LoadValidMinutes(symbol) for symbol in (*SYMBOLS, "NIFTY", "BANKNIFTY")}
    common_dates = CommonTradingDates(loaded)
    boundaries = ResearchBoundaries(common_dates)
    common_set = set(common_dates)
    loaded = {
        symbol: frame[frame["Date"].isin(common_set)].copy() for symbol, frame in loaded.items()
    }

    summaries: list[dict[str, object]] = []
    all_strategy_rows: list[pd.DataFrame] = []
    for symbol in SYMBOLS:
        benchmark = "BANKNIFTY" if symbol in BANK_SYMBOLS else "NIFTY"
        sm._SESSION_CACHE.clear()
        daily = sm.add_nifty_features(sm.build_daily_features(loaded[symbol]), loaded[benchmark])
        results = FrozenStrategyResults(daily, loaded[symbol], boundaries)
        results.insert(0, "Symbol", symbol)
        all_strategy_rows.append(results)
        best = BestFrozenFamily(results)
        summaries.append(BehaviorSummary(symbol, daily, best, boundaries))
        print(
            f"Screened {symbol}: score={summaries[-1]['ReliabilityScore']:.2f} family={best['BestFamily']}"
        )

    summary = pd.DataFrame(summaries).sort_values(
        ["SelectionGate", "ReliabilityScore"], ascending=[False, False]
    )
    strategy_results = pd.concat(all_strategy_rows, ignore_index=True)
    fresh = summary[~summary["PreviouslyExamined"]]
    finalists = fresh.head(2)["Symbol"].tolist()

    summary.to_csv(OUT / "reliability_screen_summary.csv", index=False)
    strategy_results.to_csv(OUT / "frozen_strategy_results.csv", index=False)
    pd.DataFrame([boundaries]).to_csv(OUT / "research_boundaries.csv", index=False)
    report = f"""# Intraday reliability universe screen

Screener context date: {SCREENER_AS_OF}. Costs: {sm.COST_RATE:.2%} round trip. All fills use the next available minute and conservative same-bar stop handling.

Common full-session range: {boundaries['common_start'].date()} to {boundaries['common_end'].date()}.
Development ends: {boundaries['development_end'].date()}.
Validation: {boundaries['validation_start'].date()} to {boundaries['selection_end'].date()}.
The final {FINAL_HOLDOUT_SESSIONS} sessions beginning {boundaries['sealed_start'].date()} remain sealed.

Provisional finalists selected without reading the sealed holdout: {', '.join(finalists)}.

{summary.to_string(index=False)}
"""
    (OUT / "reliability_screen_report.md").write_text(report, encoding="utf-8")
    print("\nPROVISIONAL RANKING")
    print(
        summary[
            [
                "Symbol",
                "ReliabilityScore",
                "SelectionGate",
                "BestFamily",
                "DevelopmentPF",
                "ValidationPF",
                "MedianIntradayRange",
                "BenchmarkDirectionMatch",
            ]
        ].to_string(index=False)
    )
    print("PROVISIONAL FINALISTS", ", ".join(finalists))


if __name__ == "__main__":
    main()
