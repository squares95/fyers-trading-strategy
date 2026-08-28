"""Tune finalists before, and only then evaluate, a sealed 60-session holdout."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from Research.CGPOWER import cgpower_session_microstructure as sm
from Research.Universe.reliability_screen import CommonTradingDates, ResearchBoundaries

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "Finalists"
SYMBOLS = ("BHARTIARTL", "M&M", "LT", "ICICIBANK", "SBIN")
BENCHMARK = {
    "BHARTIARTL": "NIFTY",
    "M&M": "NIFTY",
    "LT": "NIFTY",
    "ICICIBANK": "BANKNIFTY",
    "SBIN": "BANKNIFTY",
}
CLEAN_HOLDOUT = {
    "BHARTIARTL": True,
    "M&M": True,
    "LT": True,
    "ICICIBANK": True,
    "SBIN": False,
}
MAX_RISK_PCT = 0.008
MIN_DEVELOPMENT_TRADES = 25
MIN_VALIDATION_TRADES = 12
MIN_FINAL_TRADES = 8
TOP_SPECS_PER_FAMILY = 5


def CandlePath(symbol: str) -> Path:
    return ROOT / "Data" / symbol / f"{symbol}_1MIN.csv"


def LoadValidMinutes(symbol: str) -> pd.DataFrame:
    return sm.valid_sessions(sm.load_minutes(CandlePath(symbol)))


def JsonParameters(spec: dict[str, object]) -> str:
    return json.dumps(
        {key: value for key, value in spec.items() if key not in {"Family", "SpecId"}},
        sort_keys=True,
    )


def BuildSpecs(daily: pd.DataFrame, development_end: pd.Timestamp) -> list[dict[str, object]]:
    development = daily.loc[:development_end]
    rvol_levels = {
        "none": 0.0,
        "median": float(development["opening15_rvol20"].median()),
        "upper_quartile": float(development["opening15_rvol20"].quantile(0.75)),
    }
    specs: list[dict[str, object]] = []
    spec_id = 0

    for family in ("opening_drive", "benchmark_opening"):
        for strength in (0.15, 0.25, 0.35, 0.50):
            for position in (0.70, 0.80, 0.90):
                for rvol_name, cutoff in rvol_levels.items():
                    for target_r in (1.5, 2.0):
                        specs.append(
                            {
                                "SpecId": spec_id,
                                "Family": family,
                                "strength": strength,
                                "position": position,
                                "rvol_name": rvol_name,
                                "rvol_cutoff": cutoff,
                                "target_r": target_r,
                            }
                        )
                        spec_id += 1

    for latest in ("11:30", "13:30", "14:30"):
        for stop_mode in ("midpoint", "opposite_boundary"):
            for target_r in (1.0, 1.5, 2.0):
                for rvol_name, cutoff in rvol_levels.items():
                    specs.append(
                        {
                            "SpecId": spec_id,
                            "Family": "two_sided_sweep",
                            "latest": latest,
                            "stop_mode": stop_mode,
                            "target_r": target_r,
                            "rvol_name": rvol_name,
                            "rvol_cutoff": cutoff,
                        }
                    )
                    spec_id += 1

    for latest in ("10:00", "11:30"):
        for stop_mode in ("midpoint", "opposite_boundary"):
            for target_r in (1.0, 1.5):
                for rvol_name, cutoff in {"none": 0.0, "median": rvol_levels["median"]}.items():
                    for gap_alignment in (False, True):
                        specs.append(
                            {
                                "SpecId": spec_id,
                                "Family": "opening_range_breakout",
                                "latest": latest,
                                "stop_mode": stop_mode,
                                "target_r": target_r,
                                "rvol_name": rvol_name,
                                "rvol_cutoff": cutoff,
                                "position": 0.70,
                                "gap_alignment": gap_alignment,
                            }
                        )
                        spec_id += 1
    return specs


def EvaluateSpec(
    spec: dict[str, object],
    daily: pd.DataFrame,
    minutes: pd.DataFrame,
    start: pd.Timestamp | None,
    end: pd.Timestamp,
) -> pd.DataFrame:
    family = str(spec["Family"])
    if family in {"opening_drive", "benchmark_opening"}:
        eligible = daily
        if family == "benchmark_opening":
            eligible = daily[
                (np.sign(daily["r15"]) == np.sign(daily["nifty_r15"]))
                & (daily["nifty_r15"].abs() >= 0.0005)
            ]
        rule = sm.Rule(
            family,
            float(spec["strength"]),
            float(spec["position"]),
            0.0,
            float(spec["target_r"]),
        )
        return sm.evaluate_rule(
            rule,
            eligible,
            minutes,
            float(spec["rvol_cutoff"]),
            start=start,
            end=end,
            max_risk_pct=MAX_RISK_PCT,
        )
    if family == "two_sided_sweep":
        return sm.evaluate_sweep_rule(
            daily,
            minutes,
            str(spec["latest"]),
            str(spec["stop_mode"]),
            float(spec["target_r"]),
            float(spec["rvol_cutoff"]),
            start=start,
            end=end,
            max_risk_pct=MAX_RISK_PCT,
        )
    if family == "opening_range_breakout":
        return sm.evaluate_orb_rule(
            daily,
            minutes,
            str(spec["latest"]),
            str(spec["stop_mode"]),
            float(spec["target_r"]),
            float(spec["rvol_cutoff"]),
            float(spec["position"]),
            bool(spec["gap_alignment"]),
            start=start,
            end=end,
            max_risk_pct=MAX_RISK_PCT,
        )
    raise ValueError(f"Unknown family: {family}")


def SafeNumber(value: object, default: float = 0.0) -> float:
    number = float(pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0])
    if np.isnan(number):
        return default
    if np.isposinf(number):
        return 3.0
    return number


def DevelopmentScore(metric: dict[str, float]) -> float:
    if int(metric["Trades"]) < 20:
        return -np.inf
    pf = min(SafeNumber(metric["ProfitFactor"]), 3.0)
    expectancy = SafeNumber(metric["Expectancy"])
    drawdown_penalty = max(0.25, 1 + SafeNumber(metric["MaxDrawdown"]))
    return pf * np.sqrt(int(metric["Trades"])) * max(0.25, 1 + expectancy * 100) * drawdown_penalty


def PassesSelection(development: dict[str, float], validation: dict[str, float]) -> bool:
    return bool(
        int(development["Trades"]) >= MIN_DEVELOPMENT_TRADES
        and int(validation["Trades"]) >= MIN_VALIDATION_TRADES
        and SafeNumber(development["ProfitFactor"]) >= 1.20
        and SafeNumber(validation["ProfitFactor"]) >= 1.15
        and SafeNumber(development["Expectancy"]) > 0
        and SafeNumber(validation["Expectancy"]) > 0
        and SafeNumber(development["MaxDrawdown"], -1.0) > -0.12
        and SafeNumber(validation["MaxDrawdown"], -1.0) > -0.12
    )


def PassesFinal(final: dict[str, float]) -> bool:
    return bool(
        int(final["Trades"]) >= MIN_FINAL_TRADES
        and SafeNumber(final["ProfitFactor"]) >= 1.10
        and SafeNumber(final["Expectancy"]) > 0
        and SafeNumber(final["MaxDrawdown"], -1.0) > -0.10
    )


def PrefixMetrics(prefix: str, metric: dict[str, float]) -> dict[str, float]:
    return {f"{prefix}{key}": value for key, value in metric.items()}


def SelectCandidate(
    specs: list[dict[str, object]],
    daily: pd.DataFrame,
    minutes: pd.DataFrame,
    boundaries: dict[str, pd.Timestamp],
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    development_rows: list[dict[str, object]] = []
    development_trades: dict[int, pd.DataFrame] = {}
    for spec in specs:
        trades = EvaluateSpec(spec, daily, minutes, None, boundaries["development_end"])
        metric = sm.metrics(trades)
        development_trades[int(spec["SpecId"])] = trades
        development_rows.append(
            {
                "SpecId": int(spec["SpecId"]),
                "Family": spec["Family"],
                "Parameters": JsonParameters(spec),
                **metric,
                "DevelopmentScore": DevelopmentScore(metric),
            }
        )
    development_grid = pd.DataFrame(development_rows)

    shortlist_ids: list[int] = []
    for _, family in development_grid.groupby("Family", sort=False):
        eligible = family[family["DevelopmentScore"] > -np.inf]
        shortlist_ids.extend(
            eligible.nlargest(TOP_SPECS_PER_FAMILY, "DevelopmentScore")["SpecId"]
            .astype(int)
            .tolist()
        )

    specs_by_id = {int(spec["SpecId"]): spec for spec in specs}
    validation_rows: list[dict[str, object]] = []
    validation_trades: dict[int, pd.DataFrame] = {}
    for spec_id in shortlist_ids:
        spec = specs_by_id[spec_id]
        development_metric = sm.metrics(development_trades[spec_id])
        trades = EvaluateSpec(
            spec,
            daily,
            minutes,
            boundaries["validation_start"],
            boundaries["selection_end"],
        )
        validation_trades[spec_id] = trades
        validation_metric = sm.metrics(trades)
        floor_pf = min(
            SafeNumber(development_metric["ProfitFactor"]),
            SafeNumber(validation_metric["ProfitFactor"]),
        )
        selection_pass = PassesSelection(development_metric, validation_metric)
        validation_rows.append(
            {
                "SpecId": spec_id,
                "Family": spec["Family"],
                "Parameters": JsonParameters(spec),
                **PrefixMetrics("Development", development_metric),
                **PrefixMetrics("Validation", validation_metric),
                "SelectionPass": selection_pass,
                "SelectionScore": (10.0 if selection_pass else 0.0)
                + min(floor_pf, 3.0)
                + min(int(development_metric["Trades"]), int(validation_metric["Trades"]), 30)
                / 100,
            }
        )
    validation_table = pd.DataFrame(validation_rows).sort_values(
        ["SelectionPass", "SelectionScore"], ascending=[False, False]
    )
    if validation_table.empty:
        raise RuntimeError("No development candidate had enough trades for validation")
    selected_row = validation_table.iloc[0].to_dict()
    selected_id = int(selected_row["SpecId"])
    selected_spec = specs_by_id[selected_id]
    return (
        selected_spec,
        development_grid,
        validation_table,
        pd.concat(
            [
                development_trades[selected_id].assign(Sample="Development"),
                validation_trades[selected_id].assign(Sample="Validation"),
            ],
            ignore_index=True,
        ),
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    needed = set(SYMBOLS) | set(BENCHMARK.values())
    loaded = {symbol: LoadValidMinutes(symbol) for symbol in needed}
    common_dates = CommonTradingDates(loaded)
    boundaries = ResearchBoundaries(common_dates)
    common_set = set(common_dates)
    loaded = {
        symbol: frame[frame["Date"].isin(common_set)].copy() for symbol, frame in loaded.items()
    }

    summaries: list[dict[str, object]] = []
    for symbol in SYMBOLS:
        sm._SESSION_CACHE.clear()
        daily = sm.add_nifty_features(
            sm.build_daily_features(loaded[symbol]),
            loaded[BENCHMARK[symbol]],
        )
        specs = BuildSpecs(daily, boundaries["development_end"])
        selected, development_grid, validation_table, preholdout_trades = SelectCandidate(
            specs,
            daily,
            loaded[symbol],
            boundaries,
        )
        selected_id = int(selected["SpecId"])
        selected_validation = validation_table[validation_table["SpecId"] == selected_id].iloc[0]
        final_trades = EvaluateSpec(
            selected,
            daily,
            loaded[symbol],
            boundaries["sealed_start"],
            boundaries["common_end"],
        )
        final_metric = sm.metrics(final_trades)
        selection_pass = bool(selected_validation["SelectionPass"])
        final_pass = PassesFinal(final_metric)
        clean_holdout = CLEAN_HOLDOUT[symbol]
        promoted = bool(selection_pass and final_pass and clean_holdout)

        development_grid.insert(0, "Symbol", symbol)
        validation_table.insert(0, "Symbol", symbol)
        all_trades = pd.concat(
            [preholdout_trades, final_trades.assign(Sample="FinalHoldout")],
            ignore_index=True,
        )
        all_trades.insert(0, "Symbol", symbol)
        development_grid.to_csv(OUT / f"{symbol}_development_grid.csv", index=False)
        validation_table.to_csv(OUT / f"{symbol}_validation_shortlist.csv", index=False)
        all_trades.to_csv(OUT / f"{symbol}_selected_trades.csv", index=False)

        summary = {
            "Symbol": symbol,
            "Benchmark": BENCHMARK[symbol],
            "CleanHoldout": clean_holdout,
            "Family": selected["Family"],
            "Parameters": JsonParameters(selected),
            "SelectionPass": selection_pass,
            "FinalPass": final_pass,
            "Promoted": promoted,
            **{
                key: selected_validation[key]
                for key in selected_validation.index
                if key.startswith("Development") or key.startswith("Validation")
            },
            **PrefixMetrics("Final", final_metric),
        }
        summaries.append(summary)
        print(
            f"{symbol}: family={selected['Family']} selection={'PASS' if selection_pass else 'FAIL'} "
            f"final={'PASS' if final_pass else 'FAIL'} PF={SafeNumber(final_metric['ProfitFactor']):.2f} "
            f"trades={int(final_metric['Trades'])}"
        )

    result = pd.DataFrame(summaries).sort_values(
        ["Promoted", "FinalPass", "SelectionPass", "FinalProfitFactor"],
        ascending=[False, False, False, False],
    )
    result.to_csv(OUT / "finalist_validation_summary.csv", index=False)
    winners = result[result["Promoted"]]["Symbol"].tolist()
    verdict = winners[0] if winners else "NONE"
    report = f"""# Finalist strategy validation

Common data: {boundaries['common_start'].date()} to {boundaries['common_end'].date()}.
Development ends {boundaries['development_end'].date()}; validation ends {boundaries['selection_end'].date()}.
The final 60 sessions beginning {boundaries['sealed_start'].date()} were opened only after each stock's rule was selected.
Costs are {sm.COST_RATE:.2%} round trip, entries use the next minute, same-bar ambiguity is adverse, and stops above {MAX_RISK_PCT:.2%} are rejected.

Promoted clean-holdout winner: {verdict}.

{result.to_string(index=False)}
"""
    (OUT / "finalist_validation_report.md").write_text(report, encoding="utf-8")
    print("\nFINALIST SUMMARY")
    print(
        result[
            [
                "Symbol",
                "CleanHoldout",
                "Family",
                "SelectionPass",
                "FinalTrades",
                "FinalWinRate",
                "FinalProfitFactor",
                "FinalExpectancy",
                "FinalMaxDrawdown",
                "Promoted",
            ]
        ].to_string(index=False)
    )
    print("PROMOTED WINNER", verdict)


if __name__ == "__main__":
    main()
