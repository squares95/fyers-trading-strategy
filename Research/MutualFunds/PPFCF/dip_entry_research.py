from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
NAV_PATH = ROOT / "Data" / "MutualFunds" / "PPFCF_DIRECT_GROWTH" / "PPFCF_DIRECT_GROWTH_1D.csv"
NIFTY_PATH = ROOT / "Data" / "NIFTY" / "NIFTY_1D.csv"
OUTPUT_FOLDER = Path(__file__).resolve().parent

DEVELOPMENT_END = pd.Timestamp("2021-12-31")
VALIDATION_END = pd.Timestamp("2024-08-23")
FINAL_START = pd.Timestamp("2024-08-24")
FORWARD_HORIZONS = (20, 60, 120, 252)
SIGNAL_COOLDOWN_DAYS = 10
MONTHLY_CONTRIBUTION = 10_000.0


@dataclass(frozen=True)
class Period:
    Name: str
    Start: pd.Timestamp
    End: pd.Timestamp


PERIODS = (
    Period("Development", pd.Timestamp.min, DEVELOPMENT_END),
    Period("Validation", DEVELOPMENT_END + pd.Timedelta(days=1), VALIDATION_END),
    Period("FinalOOS", FINAL_START, pd.Timestamp.max),
)


def LoadData() -> tuple[pd.DataFrame, pd.DataFrame]:
    nav = pd.read_csv(NAV_PATH, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    if nav.empty or nav["Date"].duplicated().any() or (nav["NAV"] <= 0).any():
        raise ValueError("NAV source failed basic quality checks")

    nifty = pd.read_csv(NIFTY_PATH, parse_dates=["Datetime"])
    nifty = nifty.rename(columns={"Datetime": "Date", "Close": "NiftyClose"})
    nifty["Date"] = nifty["Date"].dt.normalize()
    nifty = nifty[["Date", "NiftyClose"]].sort_values("Date").drop_duplicates("Date")
    return AddFeatures(nav), nifty


def AddFeatures(nav: pd.DataFrame) -> pd.DataFrame:
    result = nav.copy()
    result["Return1"] = result["NAV"].pct_change()
    result["Return3"] = result["NAV"].pct_change(3)
    result["Return5"] = result["NAV"].pct_change(5)
    result["Peak20"] = result["NAV"].rolling(20, min_periods=1).max()
    result["Peak60"] = result["NAV"].rolling(60, min_periods=1).max()
    result["Drawdown20"] = result["NAV"] / result["Peak20"] - 1
    result["Drawdown60"] = result["NAV"] / result["Peak60"] - 1
    result["DrawdownATH"] = result["NAV"] / result["NAV"].cummax() - 1
    result["MA20Deviation"] = result["NAV"] / result["NAV"].rolling(20).mean() - 1

    delta = result["NAV"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    result["RSI14"] = 100 - (100 / (1 + gain / loss))
    return result


def BuildRules(nav: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "DailyDrop_0.75": nav["Return1"] <= -0.0075,
        "DailyDrop_1.00": nav["Return1"] <= -0.0100,
        "DailyDrop_1.25": nav["Return1"] <= -0.0125,
        "DailyDrop_1.50": nav["Return1"] <= -0.0150,
        "ThreeDayDrop_1.50": nav["Return3"] <= -0.0150,
        "ThreeDayDrop_2.00": nav["Return3"] <= -0.0200,
        "ThreeDayDrop_2.50": nav["Return3"] <= -0.0250,
        "FiveDayDrop_2.00": nav["Return5"] <= -0.0200,
        "FiveDayDrop_2.50": nav["Return5"] <= -0.0250,
        "FiveDayDrop_3.00": nav["Return5"] <= -0.0300,
        "TwentyDayDD_2": nav["Drawdown20"] <= -0.02,
        "TwentyDayDD_3": nav["Drawdown20"] <= -0.03,
        "TwentyDayDD_4": nav["Drawdown20"] <= -0.04,
        "SixtyDayDD_4": nav["Drawdown60"] <= -0.04,
        "SixtyDayDD_5": nav["Drawdown60"] <= -0.05,
        "RSI_30": nav["RSI14"] <= 30,
        "RSI_35": nav["RSI14"] <= 35,
        "RSI_40": nav["RSI14"] <= 40,
        "DD3_RSI35": (nav["Drawdown20"] <= -0.03) & (nav["RSI14"] <= 35),
        "Drop5_2_RSI35": (nav["Return5"] <= -0.02) & (nav["RSI14"] <= 35),
        "Daily1_DD2": (nav["Return1"] <= -0.01) & (nav["Drawdown20"] <= -0.02),
        "Drop3_2_DD3": (nav["Return3"] <= -0.02) & (nav["Drawdown20"] <= -0.03),
    }


def SelectSignalIndices(
    nav: pd.DataFrame,
    signal: pd.Series,
    period: Period,
    cooldown: int = SIGNAL_COOLDOWN_DAYS,
) -> list[int]:
    candidates = nav.index[
        signal.fillna(False)
        & nav["Date"].between(period.Start, period.End)
    ].tolist()
    selected = []
    last_index = -10_000
    for index in candidates:
        if index <= last_index + cooldown:
            continue
        if index + 1 >= len(nav) or nav.at[index + 1, "Date"] > period.End:
            continue
        selected.append(index)
        last_index = index
    return selected


def BaselineForwardReturns(nav: pd.DataFrame, period: Period, horizon: int) -> pd.Series:
    eligible = nav[
        nav["Date"].between(period.Start, period.End)
        & nav["Date"].shift(-horizon).le(period.End)
    ].index
    return nav.loc[eligible + horizon, "NAV"].to_numpy() / nav.loc[eligible, "NAV"].to_numpy() - 1


def EvaluateSignals(nav: pd.DataFrame, rules: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for rule_name, signal in rules.items():
        for period in PERIODS:
            indices = SelectSignalIndices(nav, signal, period)
            row = {"Rule": rule_name, "Period": period.Name, "Signals": len(indices)}
            for horizon in FORWARD_HORIZONS:
                returns = []
                for signal_index in indices:
                    entry_index = signal_index + 1
                    exit_index = entry_index + horizon
                    if exit_index >= len(nav) or nav.at[exit_index, "Date"] > period.End:
                        continue
                    returns.append(nav.at[exit_index, "NAV"] / nav.at[entry_index, "NAV"] - 1)

                baseline = BaselineForwardReturns(nav, period, horizon)
                returns_array = np.asarray(returns, dtype=float)
                row[f"Count{horizon}"] = len(returns_array)
                row[f"Mean{horizon}Pct"] = np.mean(returns_array) * 100 if len(returns_array) else np.nan
                row[f"Median{horizon}Pct"] = np.median(returns_array) * 100 if len(returns_array) else np.nan
                row[f"Positive{horizon}Pct"] = np.mean(returns_array > 0) * 100 if len(returns_array) else np.nan
                row[f"BaselineMedian{horizon}Pct"] = np.median(baseline) * 100 if len(baseline) else np.nan
                row[f"MedianLift{horizon}Pct"] = (
                    row[f"Median{horizon}Pct"] - row[f"BaselineMedian{horizon}Pct"]
                    if len(returns_array) and len(baseline)
                    else np.nan
                )
            rows.append(row)
    return pd.DataFrame(rows)


def SelectResearchRule(signal_summary: pd.DataFrame) -> tuple[str | None, pd.DataFrame]:
    development = signal_summary[signal_summary["Period"] == "Development"].set_index("Rule")
    validation = signal_summary[signal_summary["Period"] == "Validation"].set_index("Rule")
    candidates = development.join(validation, lsuffix="_Dev", rsuffix="_Val")
    candidates["Pass"] = (
        (candidates["Count60_Dev"] >= 12)
        & (candidates["Count60_Val"] >= 5)
        & (candidates["MedianLift60Pct_Dev"] > 0)
        & (candidates["MedianLift60Pct_Val"] > 0)
        & (candidates["MedianLift120Pct_Dev"] > 0)
        & (candidates["MedianLift120Pct_Val"] > 0)
    )
    candidates["Score"] = (
        candidates["MedianLift60Pct_Dev"]
        + candidates["MedianLift60Pct_Val"]
        + candidates["MedianLift120Pct_Dev"]
        + candidates["MedianLift120Pct_Val"]
    )
    passing = candidates[candidates["Pass"]].sort_values("Score", ascending=False)
    selected = passing.index[0] if not passing.empty else None
    return selected, candidates.reset_index().sort_values(["Pass", "Score"], ascending=[False, False])


def MonthlyInvestmentResult(
    nav: pd.DataFrame,
    signal: pd.Series,
    period: Period,
    *,
    wait_days: int,
    core_fraction: float,
) -> dict:
    subset = nav[nav["Date"].between(period.Start, period.End)]
    if subset.empty:
        return {}

    units = 0.0
    contributions = 0.0
    delays = []
    signal_buys = 0
    for _, month in subset.groupby(subset["Date"].dt.to_period("M")):
        month_indices = month.index.tolist()
        first_index = month_indices[0]
        last_index = month_indices[-1]
        core_amount = MONTHLY_CONTRIBUTION * core_fraction
        reserve_amount = MONTHLY_CONTRIBUTION - core_amount

        if core_amount:
            units += core_amount / nav.at[first_index, "NAV"]
        contributions += MONTHLY_CONTRIBUTION

        if reserve_amount <= 0:
            delays.append(0)
            continue

        signal_window = month_indices[: max(1, min(wait_days, len(month_indices)))]
        signal_candidates = [i for i in signal_window if bool(signal.fillna(False).at[i]) and i + 1 <= last_index]
        if signal_candidates:
            buy_index = signal_candidates[0] + 1
            signal_buys += 1
        else:
            buy_index = month_indices[min(wait_days, len(month_indices) - 1)]
        delays.append(buy_index - first_index)
        units += reserve_amount / nav.at[buy_index, "NAV"]

    final_nav = subset.iloc[-1]["NAV"]
    return {
        "Months": subset["Date"].dt.to_period("M").nunique(),
        "Contributed": contributions,
        "FinalValue": units * final_nav,
        "GainPct": (units * final_nav / contributions - 1) * 100,
        "Units": units,
        "WeightedAverageNAV": contributions / units,
        "AverageDelayDays": np.mean(delays),
        "SignalBuys": signal_buys,
    }


def EvaluateMonthlyStrategies(
    nav: pd.DataFrame,
    rules: dict[str, pd.Series],
) -> pd.DataFrame:
    rows = []
    configurations = [("ImmediateSIP", "Immediate", pd.Series(True, index=nav.index), 0, 1.0)]
    for rule_name, signal in rules.items():
        for wait_days in (5, 10, 15, 20):
            configurations.extend(
                [
                    (f"WaitAll_{wait_days}", rule_name, signal, wait_days, 0.0),
                    (f"Core50_Dip50_{wait_days}", rule_name, signal, wait_days, 0.50),
                    (f"Core75_Dip25_{wait_days}", rule_name, signal, wait_days, 0.75),
                ]
            )

    for period in PERIODS:
        baseline_units = None
        period_rows = []
        for name, rule_name, signal, wait_days, core_fraction in configurations:
            result = MonthlyInvestmentResult(
                nav,
                signal,
                period,
                wait_days=wait_days,
                core_fraction=core_fraction,
            )
            if not result:
                continue
            row = {
                "Strategy": name,
                "Rule": rule_name,
                "Period": period.Name,
                "WaitDays": wait_days,
                "CoreFraction": core_fraction,
                **result,
            }
            if name == "ImmediateSIP":
                baseline_units = result["Units"]
            period_rows.append(row)
        for row in period_rows:
            row["UnitLiftVsImmediatePct"] = (
                (row["Units"] / baseline_units - 1) * 100 if baseline_units else np.nan
            )
            rows.append(row)
    return pd.DataFrame(rows)


def SelectMonthlyStrategy(monthly: pd.DataFrame) -> tuple[dict | None, pd.DataFrame]:
    keys = ["Strategy", "Rule", "WaitDays", "CoreFraction"]
    development = monthly[monthly["Period"] == "Development"].set_index(keys)
    validation = monthly[monthly["Period"] == "Validation"].set_index(keys)
    candidates = development.join(validation, lsuffix="_Dev", rsuffix="_Val").reset_index()
    candidates = candidates[candidates["Strategy"] != "ImmediateSIP"].copy()
    candidates["Pass"] = (
        (candidates["UnitLiftVsImmediatePct_Dev"] > 0)
        & (candidates["UnitLiftVsImmediatePct_Val"] > 0)
        & (candidates["SignalBuys_Dev"] >= 5)
        & (candidates["SignalBuys_Val"] >= 2)
    )
    candidates["Score"] = (
        candidates["UnitLiftVsImmediatePct_Dev"]
        + candidates["UnitLiftVsImmediatePct_Val"]
    )
    candidates = candidates.sort_values(["Pass", "Score"], ascending=[False, False])
    passing = candidates[candidates["Pass"]]
    if passing.empty:
        return None, candidates
    selected = passing.iloc[0]
    return {key: selected[key] for key in keys}, candidates


def RecentMarketContext(nav: pd.DataFrame, nifty: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    recent = nav[nav["Date"] >= FINAL_START].copy()
    nifty = nifty.copy()
    nifty["NiftyReturn1"] = nifty["NiftyClose"].pct_change()
    nifty["NiftyReturn5"] = nifty["NiftyClose"].pct_change(5)
    aligned = recent.merge(nifty, on="Date", how="left")

    clusters = []
    last_index = -10_000
    for index in aligned.sort_values("Return1").index:
        original_index = aligned.index.get_loc(index)
        if any(abs(original_index - prior) <= 5 for prior in clusters):
            continue
        clusters.append(original_index)
        if len(clusters) == 15:
            break
    events = aligned.iloc[sorted(clusters)].copy()

    for horizon in (20, 60, 120):
        values = []
        recovery = []
        for _, row in events.iterrows():
            nav_index = nav.index[nav["Date"] == row["Date"]][0]
            entry_index = nav_index + 1
            exit_index = entry_index + horizon
            values.append(
                (nav.at[exit_index, "NAV"] / nav.at[entry_index, "NAV"] - 1) * 100
                if exit_index < len(nav)
                else np.nan
            )
            prior_nav = nav.at[nav_index - 1, "NAV"] if nav_index > 0 else nav.at[nav_index, "NAV"]
            later = nav.loc[nav_index + 1 :]
            recovered = later[later["NAV"] >= prior_nav]
            recovery.append(
                int(recovered.index[0] - nav_index) if not recovered.empty else np.nan
            )
        events[f"Forward{horizon}Pct"] = values
        if horizon == 20:
            events["RecoveryNavDays"] = recovery

    correlation_rows = aligned.dropna(subset=["Return1", "NiftyReturn1"])
    context = {
        "RecentStart": recent["Date"].min().date(),
        "RecentEnd": recent["Date"].max().date(),
        "RecentRows": len(recent),
        "RecentReturnPct": (recent.iloc[-1]["NAV"] / recent.iloc[0]["NAV"] - 1) * 100,
        "RecentMaxDrawdownPct": (recent["NAV"] / recent["NAV"].cummax() - 1).min() * 100,
        "NiftyNavDailyCorrelation": correlation_rows["Return1"].corr(correlation_rows["NiftyReturn1"]),
    }
    columns = [
        "Date",
        "NAV",
        "Return1",
        "Return5",
        "Drawdown20",
        "DrawdownATH",
        "RSI14",
        "NiftyReturn1",
        "NiftyReturn5",
        "Forward20Pct",
        "Forward60Pct",
        "Forward120Pct",
        "RecoveryNavDays",
    ]
    return events[columns].sort_values("Date"), context


def MarketShockDiagnostics(nav: pd.DataFrame, nifty: pd.DataFrame) -> pd.DataFrame:
    """Describe recent broad-market selloffs without using them for rule selection."""
    market = nifty.copy()
    market["NiftyReturn1"] = market["NiftyClose"].pct_change()
    market["NiftyReturn5"] = market["NiftyClose"].pct_change(5)

    aligned = nav.merge(market, on="Date", how="left")
    start = max(FINAL_START, market["Date"].min())
    rules = {
        "NiftyDayDown1": aligned["NiftyReturn1"] <= -0.01,
        "NiftyDayDown1.5": aligned["NiftyReturn1"] <= -0.015,
        "NiftyDayDown2": aligned["NiftyReturn1"] <= -0.02,
        "Nifty5DayDown3": aligned["NiftyReturn5"] <= -0.03,
        "Nifty5DayDown4": aligned["NiftyReturn5"] <= -0.04,
        "Nifty5DayDown5": aligned["NiftyReturn5"] <= -0.05,
        "NiftyDay1_FundDD3": (
            (aligned["NiftyReturn1"] <= -0.01)
            & (aligned["Drawdown20"] <= -0.03)
        ),
        "Nifty5Day3_FundDD5": (
            (aligned["NiftyReturn5"] <= -0.03)
            & (aligned["Drawdown20"] <= -0.05)
        ),
    }
    period = Period("RecentDescriptive", start, min(nav["Date"].max(), market["Date"].max()))
    baseline = aligned[
        aligned["Date"].between(period.Start, period.End)
        & aligned["NiftyClose"].notna()
    ]
    rows = []
    for name, signal in rules.items():
        indices = SelectSignalIndices(aligned, signal, period)
        observations = []
        for signal_index in indices:
            entry_index = signal_index + 1
            if entry_index >= len(aligned):
                continue
            entry_nav = aligned.at[entry_index, "NAV"]
            row = {
                "EntryDate": aligned.at[entry_index, "Date"],
                "Forward5Pct": np.nan,
                "WorstNext5Pct": np.nan,
                "Forward20Pct": np.nan,
                "Forward60Pct": np.nan,
            }
            five_end = min(entry_index + 5, len(aligned) - 1)
            if five_end > entry_index:
                next_five = aligned.loc[entry_index + 1 : five_end, "NAV"]
                row["Forward5Pct"] = (aligned.at[five_end, "NAV"] / entry_nav - 1) * 100
                row["WorstNext5Pct"] = (next_five.min() / entry_nav - 1) * 100
            for horizon in (20, 60):
                exit_index = entry_index + horizon
                if exit_index < len(aligned) and aligned.at[exit_index, "Date"] <= period.End:
                    row[f"Forward{horizon}Pct"] = (
                        aligned.at[exit_index, "NAV"] / entry_nav - 1
                    ) * 100
            observations.append(row)

        sample = pd.DataFrame(
            observations,
            columns=[
                "EntryDate",
                "Forward5Pct",
                "WorstNext5Pct",
                "Forward20Pct",
                "Forward60Pct",
            ],
        )
        baseline_20 = []
        baseline_60 = []
        for index in baseline.index:
            entry_index = index + 1
            if entry_index >= len(aligned):
                continue
            for horizon, target in ((20, baseline_20), (60, baseline_60)):
                exit_index = entry_index + horizon
                if exit_index < len(aligned) and aligned.at[exit_index, "Date"] <= period.End:
                    target.append(
                        (aligned.at[exit_index, "NAV"] / aligned.at[entry_index, "NAV"] - 1) * 100
                    )

        rows.append(
            {
                "Rule": name,
                "Signals": len(sample),
                "FirstEntry": sample["EntryDate"].min() if not sample.empty else pd.NaT,
                "LastEntry": sample["EntryDate"].max() if not sample.empty else pd.NaT,
                "FellFurtherWithin5DaysPct": (
                    (sample["WorstNext5Pct"] < 0).mean() * 100 if not sample.empty else np.nan
                ),
                "MedianWorstNext5Pct": (
                    sample["WorstNext5Pct"].median() if not sample.empty else np.nan
                ),
                "MedianForward20Pct": (
                    sample["Forward20Pct"].median() if not sample.empty else np.nan
                ),
                "PositiveForward20Pct": (
                    (sample["Forward20Pct"].dropna() > 0).mean() * 100
                    if not sample["Forward20Pct"].dropna().empty
                    else np.nan
                ),
                "MedianLift20Pct": (
                    sample["Forward20Pct"].median() - np.median(baseline_20)
                    if not sample.empty and baseline_20
                    else np.nan
                ),
                "MedianForward60Pct": (
                    sample["Forward60Pct"].median() if not sample.empty else np.nan
                ),
                "PositiveForward60Pct": (
                    (sample["Forward60Pct"].dropna() > 0).mean() * 100
                    if not sample["Forward60Pct"].dropna().empty
                    else np.nan
                ),
                "MedianLift60Pct": (
                    sample["Forward60Pct"].median() - np.median(baseline_60)
                    if not sample.empty and baseline_60
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def CalendarDiagnostics(nav: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    recent = nav[nav["Date"] >= FINAL_START].copy()
    recent["Weekday"] = recent["Date"].dt.day_name()
    weekday = recent.groupby("Weekday", observed=True)["Return1"].agg(["count", "mean", "median"])
    weekday["mean"] *= 100
    weekday["median"] *= 100
    weekday = weekday.reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])

    lows = recent.loc[recent.groupby(recent["Date"].dt.to_period("M"))["NAV"].idxmin(), ["Date", "NAV"]]
    lows["DayOfMonth"] = lows["Date"].dt.day
    lows["MonthSegment"] = pd.cut(
        lows["DayOfMonth"],
        bins=[0, 7, 15, 23, 31],
        labels=["1-7", "8-15", "16-23", "24-end"],
    )
    segments = lows.groupby("MonthSegment", observed=True).size().rename("Months").reset_index()
    segments["FrequencyPct"] = segments["Months"] / len(lows) * 100
    return weekday.reset_index(), segments


def WriteReport(
    signal_summary: pd.DataFrame,
    candidate_selection: pd.DataFrame,
    selected_rule: str | None,
    monthly: pd.DataFrame,
    monthly_selection: pd.DataFrame,
    selected_monthly: dict | None,
    events: pd.DataFrame,
    context: dict,
    weekday: pd.DataFrame,
    month_segments: pd.DataFrame,
    market_shocks: pd.DataFrame,
) -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    signal_summary.to_csv(OUTPUT_FOLDER / "dip_signal_summary.csv", index=False)
    candidate_selection.to_csv(OUTPUT_FOLDER / "dip_rule_selection.csv", index=False)
    monthly.to_csv(OUTPUT_FOLDER / "monthly_investment_summary.csv", index=False)
    monthly_selection.to_csv(OUTPUT_FOLDER / "monthly_strategy_selection.csv", index=False)
    events.to_csv(OUTPUT_FOLDER / "recent_dip_events.csv", index=False)
    weekday.to_csv(OUTPUT_FOLDER / "weekday_diagnostics.csv", index=False)
    month_segments.to_csv(OUTPUT_FOLDER / "monthly_low_segments.csv", index=False)
    market_shocks.to_csv(OUTPUT_FOLDER / "market_shock_diagnostics.csv", index=False)

    selected_rows = signal_summary[signal_summary["Rule"] == selected_rule] if selected_rule else pd.DataFrame()
    if selected_monthly:
        selected_monthly_rows = monthly[
            (monthly["Strategy"] == selected_monthly["Strategy"])
            & (monthly["Rule"] == selected_monthly["Rule"])
            & (monthly["WaitDays"] == selected_monthly["WaitDays"])
            & (monthly["CoreFraction"] == selected_monthly["CoreFraction"])
        ]
    else:
        selected_monthly_rows = pd.DataFrame()

    def FrameBlock(frame: pd.DataFrame, empty_message: str) -> str:
        if frame.empty:
            return empty_message
        return "```text\n" + frame.to_string(index=False) + "\n```"

    report = [
        "# PPFCF Dip Entry Research",
        "",
        "Historical simulation only. Signals use published NAV information and execute at the next available NAV.",
        "",
        "## Research Design",
        "",
        f"- Development: through {DEVELOPMENT_END.date()}",
        f"- Validation: 2022-01-01 through {VALIDATION_END.date()}",
        f"- Final untouched period: {FINAL_START.date()} onward",
        f"- Selected rule: {selected_rule or 'None passed the promotion gate'}",
        f"- Selected monthly deployment: {selected_monthly or 'None passed the promotion gate'}",
        "",
        "## Recent Context",
        "",
        f"- Return: {context['RecentReturnPct']:.2f}%",
        f"- Maximum drawdown: {context['RecentMaxDrawdownPct']:.2f}%",
        f"- Daily correlation with NIFTY 50: {context['NiftyNavDailyCorrelation']:.3f}",
        "",
        "## Selected Rule Results",
        "",
        FrameBlock(selected_rows, "No rule passed."),
        "",
        "## Monthly Deployment Results",
        "",
        FrameBlock(selected_monthly_rows, "No monthly timing strategy passed."),
        "",
        "## Recent Market-Shock Diagnostics",
        "",
        "Descriptive only: recent NIFTY coverage is insufficient for independent rule validation.",
        "",
        FrameBlock(market_shocks, "No recent market-shock observations were available."),
    ]
    (OUTPUT_FOLDER / "dip_entry_report.md").write_text("\n".join(report), encoding="utf-8")


def RunResearch() -> dict:
    nav, nifty = LoadData()
    rules = BuildRules(nav)
    signal_summary = EvaluateSignals(nav, rules)
    selected_rule, candidate_selection = SelectResearchRule(signal_summary)
    monthly = EvaluateMonthlyStrategies(nav, rules)
    selected_monthly, monthly_selection = SelectMonthlyStrategy(monthly)
    events, context = RecentMarketContext(nav, nifty)
    weekday, month_segments = CalendarDiagnostics(nav)
    market_shocks = MarketShockDiagnostics(nav, nifty)
    WriteReport(
        signal_summary,
        candidate_selection,
        selected_rule,
        monthly,
        monthly_selection,
        selected_monthly,
        events,
        context,
        weekday,
        month_segments,
        market_shocks,
    )
    return {
        "selected_rule": selected_rule,
        "selected_monthly": selected_monthly,
        "context": context,
        "report": OUTPUT_FOLDER / "dip_entry_report.md",
    }


if __name__ == "__main__":
    result = RunResearch()
    print(f"Selected rule: {result['selected_rule']}")
    print(f"Selected monthly strategy: {result['selected_monthly']}")
    print(f"Report: {result['report']}")
