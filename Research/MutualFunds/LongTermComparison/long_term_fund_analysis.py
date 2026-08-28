from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FOLDER = Path(__file__).resolve().parent
PPFCF_PATH = ROOT / "Data" / "MutualFunds" / "PPFCF_DIRECT_GROWTH" / "PPFCF_DIRECT_GROWTH_1D.csv"
TRI_ENDPOINT = "https://www.niftyindices.com/BackPage/getTotalReturnIndexString"
SOURCE_PAGE = "https://www.niftyindices.com/reports/historical-data"
START_DATE = pd.Timestamp("2013-05-28")
END_DATE = pd.Timestamp("2026-08-24")
MONTHLY_SIP = 8_000.0
SIP_DAY = 5


@dataclass(frozen=True)
class IndexDefinition:
    Key: str
    RequestName: str
    DisplayName: str


INDICES = (
    IndexDefinition("MIDCAP150_TRI", "NIFTY MIDCAP 150", "Nifty Midcap 150"),
    IndexDefinition("SMALLCAP250_TRI", "NIFTY SMALLCAP 250", "Nifty Smallcap 250"),
)

CRISIS_WINDOWS = (
    ("2015-16 correction", "2015-03-03", "2016-02-29"),
    ("2018-19 mid-small bear", "2018-01-01", "2019-08-30"),
    ("Covid crash", "2020-02-19", "2020-03-23"),
    ("2021-22 tightening", "2021-10-18", "2022-06-20"),
    ("2024-25 correction", "2024-09-27", "2025-04-07"),
    ("2026 geopolitical shock", "2026-01-01", "2026-03-30"),
)


def BuildDateChunks(
    start: pd.Timestamp,
    end: pd.Timestamp,
    maximum_days: int = 364,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if start > end:
        raise ValueError("start cannot be after end")
    chunks = []
    cursor = start.normalize()
    end = end.normalize()
    while cursor <= end:
        chunk_end = min(cursor + pd.Timedelta(days=maximum_days), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + pd.Timedelta(days=1)
    return chunks


def ParseTriPayload(payload_text: str, definition: IndexDefinition) -> pd.DataFrame:
    try:
        payload = json.loads(payload_text)
        if isinstance(payload, dict) and "d" in payload:
            payload = json.loads(payload["d"]) if isinstance(payload["d"], str) else payload["d"]
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"NSE Indices returned invalid JSON for {definition.RequestName}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"NSE Indices returned no TRI rows for {definition.RequestName}")

    frame = pd.DataFrame(payload)
    required = {"Index Name", "Date", "TotalReturnsIndex"}
    if not required.issubset(frame.columns):
        raise ValueError(f"NSE TRI payload is missing columns: {required - set(frame.columns)}")
    identities = frame["Index Name"].astype(str).str.upper().str.strip().unique().tolist()
    if identities != [definition.RequestName]:
        raise ValueError(
            f"NSE TRI identity mismatch for {definition.RequestName}: received {identities}"
        )

    result = pd.DataFrame(
        {
            "Date": pd.to_datetime(frame["Date"], format="%d %b %Y", errors="coerce"),
            definition.Key: pd.to_numeric(frame["TotalReturnsIndex"], errors="coerce"),
        }
    ).dropna()
    result = result.sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True)
    if result.empty or (result[definition.Key] <= 0).any():
        raise ValueError(f"NSE TRI quality check failed for {definition.RequestName}")
    return result


def FetchTriChunk(
    definition: IndexDefinition,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    timeout: int = 45,
    retries: int = 4,
) -> pd.DataFrame:
    cinfo = (
        "{'name':'"
        + definition.RequestName
        + "','startDate':'"
        + start.strftime("%d-%b-%Y")
        + "','endDate':'"
        + end.strftime("%d-%b-%Y")
        + "','indexName':'"
        + definition.DisplayName
        + "'}"
    )
    body = json.dumps({"cinfo": cinfo}).encode("utf-8")
    request = Request(
        TRI_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": SOURCE_PAGE,
            "Origin": "https://www.niftyindices.com",
            "User-Agent": "Mozilla/5.0 Chrome/149.0.0.0 FyersResearch/1.0",
        },
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=timeout) as response:
                if getattr(response, "status", 200) != 200:
                    raise ValueError(f"Unexpected HTTP status {response.status}")
                return ParseTriPayload(response.read().decode("utf-8-sig"), definition)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(
        f"Unable to fetch {definition.RequestName} TRI for {start.date()} to {end.date()}: "
        f"{last_error}"
    ) from last_error


def FetchTriHistory(definition: IndexDefinition) -> pd.DataFrame:
    parts = []
    for start, end in BuildDateChunks(START_DATE, END_DATE):
        parts.append(FetchTriChunk(definition, start, end))
        time.sleep(0.25)
    frame = pd.concat(parts, ignore_index=True)
    frame = frame.sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True)
    if frame["Date"].min() > START_DATE + pd.Timedelta(days=7):
        raise ValueError(f"{definition.RequestName} starts unexpectedly late")
    if frame["Date"].max() < END_DATE:
        raise ValueError(f"{definition.RequestName} is stale: {frame['Date'].max().date()}")
    if len(frame) < 3_000:
        raise ValueError(f"{definition.RequestName} has only {len(frame)} rows")

    folder = ROOT / "Data" / definition.Key
    folder.mkdir(parents=True, exist_ok=True)
    frame.assign(Source="NSE_INDICES_TRI").to_csv(
        folder / f"{definition.Key}_1D.csv",
        index=False,
    )
    return frame


def LoadAlignedData() -> pd.DataFrame:
    ppfcf = pd.read_csv(PPFCF_PATH, parse_dates=["Date"])[["Date", "NAV"]]
    ppfcf = ppfcf.rename(columns={"NAV": "PPFCF"}).sort_values("Date")
    frames = [ppfcf]
    for definition in INDICES:
        frames.append(FetchTriHistory(definition))

    aligned = frames[0]
    for frame in frames[1:]:
        aligned = aligned.merge(frame, on="Date", how="inner")
    aligned = (
        aligned[aligned["Date"].between(START_DATE, END_DATE)]
        .sort_values("Date")
        .reset_index(drop=True)
    )
    expected = {"Date", "PPFCF", "MIDCAP150_TRI", "SMALLCAP250_TRI"}
    if set(aligned.columns) != expected or len(aligned) < 3_000:
        raise ValueError("Aligned long-term dataset failed coverage checks")
    return aligned


def DrawdownDetails(series: pd.Series) -> dict:
    running_peak = series.cummax()
    drawdown = series / running_peak - 1
    trough_date = drawdown.idxmin()
    peak_date = series.loc[:trough_date].idxmax()
    peak_value = series.loc[peak_date]
    recovered = series.loc[trough_date:]
    recovered = recovered[recovered >= peak_value]
    recovery_date = recovered.index[0] if not recovered.empty else pd.NaT
    return {
        "MaxDrawdownPct": drawdown.min() * 100,
        "DrawdownPeak": peak_date,
        "DrawdownTrough": trough_date,
        "RecoveryDate": recovery_date,
        "RecoveryCalendarDays": (
            (recovery_date - peak_date).days if pd.notna(recovery_date) else np.nan
        ),
    }


def CalendarReturns(series: pd.Series) -> pd.Series:
    annual = series.resample("YE").last().pct_change() * 100
    annual.index = annual.index.year
    return annual.dropna()


def RollingReturns(series: pd.Series, months: int) -> pd.Series:
    monthly = series.resample("ME").last()
    return ((monthly / monthly.shift(months)) ** (12 / months) - 1).dropna() * 100


def TrailingCagr(series: pd.Series, years: int) -> float:
    end_date = series.index[-1]
    target = end_date - pd.DateOffset(years=years)
    eligible = series[series.index >= target]
    if eligible.empty:
        return np.nan
    actual_years = (end_date - eligible.index[0]).days / 365.25
    if actual_years <= 0:
        return np.nan
    return ((series.iloc[-1] / eligible.iloc[0]) ** (1 / actual_years) - 1) * 100


def AssetMetrics(name: str, series: pd.Series) -> dict:
    series = series.dropna().sort_index()
    years = (series.index[-1] - series.index[0]).days / 365.25
    daily_returns = series.pct_change().dropna()
    annual = CalendarReturns(series)
    complete_annual = (
        annual[annual.index < series.index[-1].year] if series.index[-1].month < 12 else annual
    )
    rolling3 = RollingReturns(series, 36)
    rolling5 = RollingReturns(series, 60)
    return {
        "Asset": name,
        "Start": series.index[0],
        "End": series.index[-1],
        "Years": years,
        "CAGR_Pct": ((series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1) * 100,
        "ValueOfRs100k": 100_000 * series.iloc[-1] / series.iloc[0],
        "Trailing3YCAGR_Pct": TrailingCagr(series, 3),
        "Trailing5YCAGR_Pct": TrailingCagr(series, 5),
        "Trailing10YCAGR_Pct": TrailingCagr(series, 10),
        "AnnualVolatilityPct": daily_returns.std() * np.sqrt(252) * 100,
        **DrawdownDetails(series),
        "CompletedCalendarYears": len(complete_annual),
        "BestCalendarYearPct": complete_annual.max(),
        "WorstCalendarYearPct": complete_annual.min(),
        "PositiveCalendarYearsPct": (complete_annual > 0).mean() * 100,
        "Rolling3YMedianPct": rolling3.median(),
        "Rolling3YWorstPct": rolling3.min(),
        "Rolling3YPositivePct": (rolling3 > 0).mean() * 100,
        "Rolling5YMedianPct": rolling5.median(),
        "Rolling5YWorstPct": rolling5.min(),
        "Rolling5YPositivePct": (rolling5 > 0).mean() * 100,
    }


def CalculateXirr(cashflows: list[tuple[pd.Timestamp, float]]) -> float:
    ordered = sorted(cashflows, key=lambda item: item[0])
    base_date = ordered[0][0]

    def Xnpv(rate: float) -> float:
        return sum(
            value / ((1 + rate) ** ((date - base_date).days / 365.0)) for date, value in ordered
        )

    try:
        return brentq(Xnpv, -0.9999, 100.0) * 100
    except ValueError:
        return np.nan


def SimulateSip(
    levels: pd.DataFrame,
    weights: dict[str, float],
    monthly_amount: float = MONTHLY_SIP,
) -> dict:
    if not np.isclose(sum(weights.values()), 1.0):
        raise ValueError("SIP weights must sum to one")
    units = dict.fromkeys(weights, 0.0)
    cashflows = []
    contributions = 0.0
    months = pd.period_range(
        start=levels["Date"].min().to_period("M"),
        end=levels["Date"].max().to_period("M"),
        freq="M",
    )
    purchases = 0
    for month in months:
        due = pd.Timestamp(month.year, month.month, min(SIP_DAY, month.days_in_month))
        if due < levels["Date"].min():
            continue
        eligible = levels[(levels["Date"].dt.to_period("M") == month) & (levels["Date"] >= due)]
        if eligible.empty:
            continue
        row = eligible.iloc[0]
        for asset, weight in weights.items():
            units[asset] += monthly_amount * weight / row[asset]
        cashflows.append((due, -monthly_amount))
        contributions += monthly_amount
        purchases += 1

    final = levels.iloc[-1]
    current_value = sum(units[asset] * final[asset] for asset in weights)
    cashflows.append((final["Date"], current_value))
    return {
        "MonthlySIP": monthly_amount,
        "Installments": purchases,
        "Invested": contributions,
        "CurrentValue": current_value,
        "Gain": current_value - contributions,
        "ReturnOnContributionsPct": (current_value / contributions - 1) * 100,
        "XIRR_Pct": CalculateXirr(cashflows),
    }


def RebalancedPortfolio(levels: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    if not np.isclose(sum(weights.values()), 1.0):
        raise ValueError("Portfolio weights must sum to one")
    assets = list(weights)
    indexed = levels.set_index("Date")[assets]
    holdings = None
    values = []
    prior_year = None
    for date, row in indexed.iterrows():
        value = 1.0 if holdings is None else sum(holdings[a] * row[a] for a in assets)
        if holdings is None or date.year != prior_year:
            holdings = {a: value * weights[a] / row[a] for a in assets}
        value = sum(holdings[a] * row[a] for a in assets)
        values.append(value)
        prior_year = date.year
    return pd.Series(values, index=indexed.index)


def CrisisPerformance(aligned: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, start, end in CRISIS_WINDOWS:
        subset = aligned[aligned["Date"].between(start, end)].set_index("Date")
        if subset.empty:
            continue
        for asset in ("PPFCF", "MIDCAP150_TRI", "SMALLCAP250_TRI"):
            series = subset[asset]
            rows.append(
                {
                    "Window": label,
                    "Asset": asset,
                    "Start": series.index[0],
                    "End": series.index[-1],
                    "PeriodReturnPct": (series.iloc[-1] / series.iloc[0] - 1) * 100,
                    "WindowMaxDrawdownPct": (series / series.cummax() - 1).min() * 100,
                }
            )
    return pd.DataFrame(rows)


def RunAnalysis() -> dict:
    aligned = LoadAlignedData()
    indexed = aligned.set_index("Date")
    assets = ["PPFCF", "MIDCAP150_TRI", "SMALLCAP250_TRI"]

    metrics = pd.DataFrame([AssetMetrics(asset, indexed[asset]) for asset in assets])
    calendar = pd.DataFrame({asset: CalendarReturns(indexed[asset]) for asset in assets})
    correlation = indexed[assets].pct_change().corr()
    crises = CrisisPerformance(aligned)

    mixes = {
        "PPFCF_100": {"PPFCF": 1.0},
        "MIDCAP150_100": {"MIDCAP150_TRI": 1.0},
        "SMALLCAP250_100": {"SMALLCAP250_TRI": 1.0},
        "PPFCF50_Midcap50": {
            "PPFCF": 0.50,
            "MIDCAP150_TRI": 0.50,
        },
        "Core60_Mid20_Small20": {
            "PPFCF": 0.60,
            "MIDCAP150_TRI": 0.20,
            "SMALLCAP250_TRI": 0.20,
        },
        "Equal_Thirds": {
            "PPFCF": 1 / 3,
            "MIDCAP150_TRI": 1 / 3,
            "SMALLCAP250_TRI": 1 / 3,
        },
    }
    portfolio_rows = []
    sip_rows = []
    for name, weights in mixes.items():
        series = RebalancedPortfolio(aligned, weights)
        portfolio_rows.append({"Portfolio": name, **AssetMetrics(name, series)})
        sip_rows.append({"Portfolio": name, **SimulateSip(aligned, weights)})
    portfolios = pd.DataFrame(portfolio_rows)
    sip = pd.DataFrame(sip_rows)

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(OUTPUT_FOLDER / "long_term_aligned_levels.csv", index=False)
    metrics.to_csv(OUTPUT_FOLDER / "long_term_asset_metrics.csv", index=False)
    calendar.to_csv(OUTPUT_FOLDER / "long_term_calendar_returns.csv")
    correlation.to_csv(OUTPUT_FOLDER / "long_term_correlation.csv")
    crises.to_csv(OUTPUT_FOLDER / "long_term_crisis_performance.csv", index=False)
    portfolios.to_csv(OUTPUT_FOLDER / "long_term_portfolio_metrics.csv", index=False)
    sip.to_csv(OUTPUT_FOLDER / "long_term_sip_comparison.csv", index=False)
    return {
        "aligned": aligned,
        "metrics": metrics,
        "calendar": calendar,
        "correlation": correlation,
        "crises": crises,
        "portfolios": portfolios,
        "sip": sip,
    }


if __name__ == "__main__":
    result = RunAnalysis()
    print("Asset metrics")
    print(result["metrics"].to_string(index=False))
    print("\nPortfolio metrics")
    print(result["portfolios"].to_string(index=False))
    print("\nSIP comparison")
    print(result["sip"].to_string(index=False))
