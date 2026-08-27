from __future__ import annotations

import argparse
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import brentq


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PPFCF_PATH = (
    ROOT
    / "Data"
    / "MutualFunds"
    / "PPFCF_DIRECT_GROWTH"
    / "PPFCF_DIRECT_GROWTH_1D.csv"
)
OUTPUT_FOLDER = Path(__file__).resolve().parent
ETF_URLS = {
    "HDFCSML250": "https://www.equitypandit.com/historical-data/HDFCSML250",
    "MIDCAPIETF": "https://www.equitypandit.com/historical-data/midcapietf",
}
ETF_NAMES = {
    "HDFCSML250": "HDFC Nifty Smallcap 250 ETF",
    "MIDCAPIETF": "ICICI Prudential Nifty Midcap 150 ETF",
}
VALUATION_DATE = pd.Timestamp("2026-08-24")
MONTHS = 18
DEFAULT_SIP_DAY = 5


@dataclass(frozen=True)
class SipResult:
    Name: str
    MonthlyContribution: float
    Contributions: float
    Units: float
    Cash: float
    CurrentPrice: float
    CurrentValue: float
    Gain: float
    ReturnPct: float
    XirrPct: float
    WholeUnits: bool
    Transactions: pd.DataFrame


def FetchText(url: str) -> str:
    from MutualFunds import FetchUrlText

    return FetchUrlText(url)


def ParseEtfHistory(html: str, symbol: str) -> pd.DataFrame:
    if symbol.upper() not in html.upper():
        raise ValueError(f"ETF page identity check failed for {symbol}")
    tables = pd.read_html(StringIO(html))
    if len(tables) != 1:
        raise ValueError(f"Expected one historical table for {symbol}, found {len(tables)}")

    frame = tables[0].copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(-1)
    required = {"Date", "Price", "Open", "High", "Low", "Volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Historical table for {symbol} is missing columns: {required - set(frame.columns)}")

    frame = frame.rename(columns={"Price": "Close"})
    frame["Date"] = pd.to_datetime(frame["Date"], format="%d %b %Y", errors="coerce")
    for column in ("Open", "High", "Low", "Close", "Volume"):
        frame[column] = pd.to_numeric(
            frame[column].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )
    frame = frame.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"])
    frame = frame[["Date", "Open", "High", "Low", "Close", "Volume"]]
    frame = frame.sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True)

    if frame.empty or (frame[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError(f"Historical data quality check failed for {symbol}")
    if (frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1)).any():
        raise ValueError(f"Invalid high prices found for {symbol}")
    if (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1)).any():
        raise ValueError(f"Invalid low prices found for {symbol}")
    return frame


def LoadInputs() -> dict[str, pd.DataFrame]:
    ppfcf = pd.read_csv(PPFCF_PATH, parse_dates=["Date"])[["Date", "NAV"]]
    ppfcf = ppfcf.rename(columns={"NAV": "Close"}).sort_values("Date").reset_index(drop=True)
    if ppfcf.empty or ppfcf["Date"].duplicated().any() or (ppfcf["Close"] <= 0).any():
        raise ValueError("PPFCF NAV source failed quality checks")

    inputs = {"PPFCF": ppfcf}
    for symbol, url in ETF_URLS.items():
        frame = ParseEtfHistory(FetchText(url), symbol)
        if frame["Date"].max() < VALUATION_DATE:
            raise ValueError(
                f"{symbol} is stale: latest={frame['Date'].max().date()}, "
                f"required={VALUATION_DATE.date()}"
            )
        inputs[symbol] = frame
        folder = ROOT / "Data" / symbol
        folder.mkdir(parents=True, exist_ok=True)
        frame.assign(Source="EquityPandit").to_csv(folder / f"{symbol}_1D.csv", index=False)
    return inputs


def BuildMonths(valuation_date: pd.Timestamp, count: int = MONTHS) -> pd.PeriodIndex:
    return pd.period_range(end=valuation_date.to_period("M"), periods=count, freq="M")


def FindExecutionRow(frame: pd.DataFrame, month: pd.Period, sip_day: int) -> pd.Series:
    due_date = pd.Timestamp(month.year, month.month, min(sip_day, month.days_in_month))
    eligible = frame[
        (frame["Date"].dt.to_period("M") == month)
        & (frame["Date"] >= due_date)
    ]
    if eligible.empty:
        raise ValueError(f"No price available on or after {due_date.date()} within {month}")
    return eligible.iloc[0]


def CalculateXirr(cashflows: list[tuple[pd.Timestamp, float]]) -> float:
    ordered = sorted(cashflows, key=lambda item: item[0])
    base_date = ordered[0][0]

    def Xnpv(rate: float) -> float:
        return sum(
            value / ((1 + rate) ** ((date - base_date).days / 365.0))
            for date, value in ordered
        )

    try:
        return brentq(Xnpv, -0.9999, 100.0) * 100
    except ValueError:
        return np.nan


def SimulateSip(
    name: str,
    frame: pd.DataFrame,
    monthly_contribution: float,
    *,
    valuation_date: pd.Timestamp = VALUATION_DATE,
    months: int = MONTHS,
    sip_day: int = DEFAULT_SIP_DAY,
    whole_units: bool,
) -> SipResult:
    available = frame[frame["Date"] <= valuation_date].copy()
    if available.empty:
        raise ValueError(f"No valuation data available for {name}")

    units = 0.0
    cash = 0.0
    transactions = []
    cashflows = []
    for month in BuildMonths(valuation_date, months):
        row = FindExecutionRow(available, month, sip_day)
        due_date = pd.Timestamp(month.year, month.month, min(sip_day, month.days_in_month))
        cash += monthly_contribution
        if whole_units:
            bought = float(np.floor(cash / row["Close"]))
        else:
            bought = cash / row["Close"]
        spent = bought * row["Close"]
        cash -= spent
        units += bought
        cashflows.append((due_date, -monthly_contribution))
        transactions.append(
            {
                "Asset": name,
                "DueDate": due_date,
                "ExecutionDate": row["Date"],
                "Price": row["Close"],
                "Contribution": monthly_contribution,
                "UnitsBought": bought,
                "CashAfter": cash,
            }
        )

    current_price = float(available.iloc[-1]["Close"])
    current_value = units * current_price + cash
    contributions = monthly_contribution * months
    gain = current_value - contributions
    cashflows.append((valuation_date, current_value))
    return SipResult(
        Name=name,
        MonthlyContribution=monthly_contribution,
        Contributions=contributions,
        Units=units,
        Cash=cash,
        CurrentPrice=current_price,
        CurrentValue=current_value,
        Gain=gain,
        ReturnPct=gain / contributions * 100,
        XirrPct=CalculateXirr(cashflows),
        WholeUnits=whole_units,
        Transactions=pd.DataFrame(transactions),
    )


def CombinePortfolio(
    name: str,
    results: list[SipResult],
    sip_day: int,
    *,
    months: int = MONTHS,
    valuation_date: pd.Timestamp = VALUATION_DATE,
) -> dict:
    contributions = sum(result.Contributions for result in results)
    current_value = sum(result.CurrentValue for result in results)
    monthly = sum(result.MonthlyContribution for result in results)
    cashflows = []
    for month in BuildMonths(valuation_date, months):
        due_date = pd.Timestamp(month.year, month.month, min(sip_day, month.days_in_month))
        cashflows.append((due_date, -monthly))
    cashflows.append((valuation_date, current_value))
    return {
        "Portfolio": name,
        "MonthlyInvestment": monthly,
        "Installments": months,
        "Invested": contributions,
        "CurrentValue": current_value,
        "Gain": current_value - contributions,
        "ReturnPct": (current_value / contributions - 1) * 100,
        "XirrPct": CalculateXirr(cashflows),
    }


def RunForSipDay(
    inputs: dict[str, pd.DataFrame],
    sip_day: int,
    *,
    months: int = MONTHS,
    valuation_date: pd.Timestamp = VALUATION_DATE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    simulation = {"sip_day": sip_day, "months": months, "valuation_date": valuation_date}
    ppfcf_8000 = SimulateSip(
        "PPFCF", inputs["PPFCF"], 8000, whole_units=False, **simulation
    )
    ppfcf_7800 = SimulateSip(
        "PPFCF", inputs["PPFCF"], 7800, whole_units=False, **simulation
    )
    diversified_2600 = [
        SimulateSip("PPFCF", inputs["PPFCF"], 2600, whole_units=False, **simulation),
        SimulateSip("HDFCSML250", inputs["HDFCSML250"], 2600, whole_units=True, **simulation),
        SimulateSip("MIDCAPIETF", inputs["MIDCAPIETF"], 2600, whole_units=True, **simulation),
    ]
    diversified_equal = [
        SimulateSip("PPFCF", inputs["PPFCF"], 8000 / 3, whole_units=False, **simulation),
        SimulateSip("HDFCSML250", inputs["HDFCSML250"], 8000 / 3, whole_units=True, **simulation),
        SimulateSip("MIDCAPIETF", inputs["MIDCAPIETF"], 8000 / 3, whole_units=True, **simulation),
    ]

    summary = pd.DataFrame(
        [
            CombinePortfolio(
                "PPFCF only - stated Rs8000",
                [ppfcf_8000],
                sip_day,
                months=months,
                valuation_date=valuation_date,
            ),
            CombinePortfolio(
                "PPFCF only - comparable Rs7800",
                [ppfcf_7800],
                sip_day,
                months=months,
                valuation_date=valuation_date,
            ),
            CombinePortfolio(
                "Diversified - stated Rs2600 each",
                diversified_2600,
                sip_day,
                months=months,
                valuation_date=valuation_date,
            ),
            CombinePortfolio(
                "Diversified - equal Rs8000 budget",
                diversified_equal,
                sip_day,
                months=months,
                valuation_date=valuation_date,
            ),
        ]
    )
    sleeve_rows = []
    for label, results in (
        ("Stated Rs2600 each", diversified_2600),
        ("Equal Rs8000 budget", diversified_equal),
    ):
        for result in results:
            sleeve_rows.append(
                {
                    "Portfolio": label,
                    "Asset": result.Name,
                    "MonthlyContribution": result.MonthlyContribution,
                    "Invested": result.Contributions,
                    "CurrentPrice": result.CurrentPrice,
                    "Units": result.Units,
                    "UninvestedCash": result.Cash,
                    "CurrentValue": result.CurrentValue,
                    "Gain": result.Gain,
                    "ReturnPct": result.ReturnPct,
                    "XirrPct": result.XirrPct,
                }
            )
    return summary, pd.DataFrame(sleeve_rows)


def RunAnalysis(*, months: int = MONTHS) -> dict:
    if months <= 0:
        raise ValueError("months must be positive")
    inputs = LoadInputs()
    summary, sleeves = RunForSipDay(inputs, DEFAULT_SIP_DAY, months=months)

    sensitivity_rows = []
    for sip_day in (1, 5, 10, 15):
        day_summary, _ = RunForSipDay(inputs, sip_day, months=months)
        ppfcf = day_summary[day_summary["Portfolio"] == "PPFCF only - stated Rs8000"].iloc[0]
        diversified = day_summary[
            day_summary["Portfolio"] == "Diversified - equal Rs8000 budget"
        ].iloc[0]
        sensitivity_rows.append(
            {
                "SipDay": sip_day,
                "PPFCFValue": ppfcf["CurrentValue"],
                "PPFCFReturnPct": ppfcf["ReturnPct"],
                "DiversifiedValue": diversified["CurrentValue"],
                "DiversifiedReturnPct": diversified["ReturnPct"],
                "DiversifiedMinusPPFCF": diversified["CurrentValue"] - ppfcf["CurrentValue"],
            }
        )
    sensitivity = pd.DataFrame(sensitivity_rows)

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    suffix = "" if months == MONTHS else f"_{months}m"
    summary.to_csv(OUTPUT_FOLDER / f"sip_portfolio_summary{suffix}.csv", index=False)
    sleeves.to_csv(OUTPUT_FOLDER / f"sip_sleeve_summary{suffix}.csv", index=False)
    sensitivity.to_csv(OUTPUT_FOLDER / f"sip_date_sensitivity{suffix}.csv", index=False)
    return {
        "summary": summary,
        "sleeves": sleeves,
        "sensitivity": sensitivity,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare PPFCF with a diversified ETF SIP")
    parser.add_argument("--months", type=int, default=MONTHS)
    args = parser.parse_args()
    result = RunAnalysis(months=args.months)
    print("Portfolio summary")
    print(result["summary"].to_string(index=False))
    print("\nSleeve summary")
    print(result["sleeves"].to_string(index=False))
    print("\nSIP-date sensitivity")
    print(result["sensitivity"].to_string(index=False))
