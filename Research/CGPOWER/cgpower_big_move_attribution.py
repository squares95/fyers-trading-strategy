"""Reproducible CGPOWER big-move attribution from local one-minute candles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CHARTS = OUT / "charts"
CG_PATH = ROOT / "Data" / "CGPOWER" / "CGPOWER_1MIN.csv"
NIFTY_PATH = ROOT / "Data" / "NIFTY" / "NIFTY_1MIN.csv"
SESSION_START = "09:15"
SESSION_END = "15:29"


@dataclass(frozen=True)
class Event:
    announcement_date: str
    reaction_date: str
    label: str
    category: str
    direction: str
    source_url: str


EVENTS = [
    Event("2023-11-22", "2023-11-22", "OSAT application disclosed", "Semiconductor", "Positive",
          "https://www.businesstoday.in/markets/company-stock/story/cg-power-shares-rise-record-high-outsourced-semiconductor-assembly-and-test-406670-2023-11-22"),
    Event("2024-02-29", "2024-02-29", "Cabinet approves Rs 7,600cr OSAT unit", "Semiconductor", "Positive",
          "https://www.cgglobal.com/admin/uploads/Reg_30_Disclosure_Release_PIB.pdf"),
    Event("2024-03-13", "2024-03-13", "Sanand OSAT foundation ceremony", "Semiconductor", "Positive",
          "https://www.cgglobal.com/admin/uploads/Press_Release_13032024.pdf"),
    Event("2024-06-04", "2024-06-04", "Indian election-result risk shock", "Macro", "Negative",
          "https://www.nseindia.com/market-data/live-equity-market"),
    Event("2024-07-04", "2024-07-05", "G.G. Tronics acquisition announced", "Railway/KAVACH", "Positive",
          "https://www.cgglobal.com/admin/uploads/Annual_Report-FY_2024-25.pdf"),
    Event("2025-01-28", "2025-01-29", "Q3 FY25 results and transformer capex", "Earnings/Capex", "Positive",
          "https://economictimes.indiatimes.com/markets/stocks/news/cg-power-shares-rally-over-8-as-q3-earnings-beat-estimates-capex-plans-boost-sentiment/articleshow/117673838.cms"),
    Event("2025-04-07", "2025-04-07", "Global tariff-driven risk-off gap", "Macro", "Negative",
          "https://www.nseindia.com/market-data/live-equity-market"),
    Event("2025-05-06", "2025-05-06", "Q4 FY25 industrial-margin disappointment", "Earnings", "Negative",
          "https://www.business-standard.com/markets/news/cg-power-tanks-8-on-heavy-volumes-post-q4-results-check-details-125050600834_1.html"),
    Event("2025-08-28", "2025-08-29", "Sanand OSAT facility launch", "Semiconductor", "Positive",
          "https://nsearchives.nseindia.com/corporate/CGPOWER_28082025173125_Disclosure_Press_Release_28_08_2025.pdf"),
    Event("2026-01-17", "2026-01-19", "Rs 900cr US data-centre transformer order", "Order win", "Positive",
          "https://www.cgglobal.com/cg-in-the-news"),
    Event("2026-01-27", "2026-01-28", "Q3 FY26 results: growth and backlog", "Earnings", "Positive",
          "https://nsearchives.nseindia.com/corporate/CGPOWER_27012026145448_SEDisclosure_PressRelease.pdf"),
    Event("2026-05-06", "2026-05-06", "Q4 FY26 results and record backlog", "Earnings", "Mixed",
          "https://nsearchives.nseindia.com/corporate/CGPOWER_06052026144003_SEDisclosure_PressRelease.pdf"),
    Event("2026-05-27", "2026-05-27", "Broad power-equipment sector rally", "Sector", "Positive",
          "https://www.angelone.in/news/stocks/power-stocks-rally-as-bse-power-index-hits-record-high-bhel-cg-power-and-siemens-energy-surge"),
    Event("2026-07-03", "2026-07-03", "Power-equipment procurement policy shock", "Sector policy", "Negative",
          "https://www.livemint.com/market/stock-market-news/why-did-cg-power-hitachi-energy-apar-industries-and-other-capital-goods-stocks-crash-up-to-10-today-explained-11783070141221.html"),
]


def load_candles(path: Path) -> pd.DataFrame:
    required = {"Datetime", "Open", "High", "Low", "Close", "Volume"}
    df = pd.read_csv(path, usecols=list(required), parse_dates=["Datetime"])
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
    df = df.sort_values("Datetime").drop_duplicates("Datetime", keep="last")
    if not df["Datetime"].is_monotonic_increasing:
        raise ValueError(f"{path.name} timestamps are not chronological")
    df = df[df["Datetime"].dt.strftime("%H:%M").between(SESSION_START, SESSION_END)].copy()
    df["Date"] = df["Datetime"].dt.normalize()
    return df


def aggregate_daily(minutes: pd.DataFrame) -> pd.DataFrame:
    grouped = minutes.groupby("Date", sort=True)
    daily = grouped.agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
        Close=("Close", "last"), Volume=("Volume", "sum"), Bars=("Close", "size"),
    )
    daily["PrevClose"] = daily["Close"].shift()
    daily["return_pct"] = (daily["Close"] / daily["PrevClose"] - 1) * 100
    daily["gap_pct"] = (daily["Open"] / daily["PrevClose"] - 1) * 100
    daily["intraday_pct"] = (daily["Close"] / daily["Open"] - 1) * 100
    daily["range_pct"] = (daily["High"] / daily["Low"] - 1) * 100
    span = (daily["High"] - daily["Low"]).replace(0, np.nan)
    daily["close_position"] = (daily["Close"] - daily["Low"]) / span
    daily["volume_ratio20"] = daily["Volume"] / daily["Volume"].shift().rolling(20).median()
    daily["pre5_pct"] = (daily["PrevClose"] / daily["Close"].shift(6) - 1) * 100
    daily["pre20_pct"] = (daily["PrevClose"] / daily["Close"].shift(21) - 1) * 100
    for horizon in (1, 5, 20):
        daily[f"post{horizon}_pct"] = (daily["Close"].shift(-horizon) / daily["Close"] - 1) * 100
    return daily


def intraday_profiles(minutes: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for date, day in minutes.groupby("Date", sort=True):
        day = day.sort_values("Datetime").copy()
        if len(day) < 300:
            continue
        start = day.iloc[0]
        first15 = day.iloc[min(14, len(day) - 1)]
        first60 = day.iloc[min(59, len(day) - 1)]
        rolling15 = day["Close"].pct_change(15) * 100
        first30_volume_share = day.iloc[:30]["Volume"].sum() / max(day["Volume"].sum(), 1)
        rows.append({
            "Date": date,
            "first15_pct": (first15["Close"] / start["Open"] - 1) * 100,
            "first60_pct": (first60["Close"] / start["Open"] - 1) * 100,
            "first30_volume_share": first30_volume_share,
            "high_time": day.loc[day["High"].idxmax(), "Datetime"].strftime("%H:%M"),
            "low_time": day.loc[day["Low"].idxmin(), "Datetime"].strftime("%H:%M"),
            "max_15m_up_pct": rolling15.max(),
            "max_15m_up_time": day.loc[rolling15.idxmax(), "Datetime"].strftime("%H:%M") if rolling15.notna().any() else None,
            "max_15m_down_pct": rolling15.min(),
            "max_15m_down_time": day.loc[rolling15.idxmin(), "Datetime"].strftime("%H:%M") if rolling15.notna().any() else None,
        })
    profile = pd.DataFrame(rows).set_index("Date")
    return daily.join(profile, how="left")


def classify_path(row: pd.Series) -> str:
    gap, intra, close_pos, rvol = row["gap_pct"], row["intraday_pct"], row["close_position"], row["volume_ratio20"]
    if pd.isna(gap):
        return "insufficient_history"
    if gap >= 3 and intra <= -1:
        return "positive_gap_fade"
    if gap <= -3 and intra >= 1:
        return "negative_gap_recovery"
    if gap >= 3 and abs(intra) < 1:
        return "positive_gap_repricing"
    if gap <= -3 and abs(intra) < 1:
        return "negative_gap_repricing"
    if intra >= 3 and close_pos >= 0.75 and rvol >= 2:
        return "intraday_accumulation"
    if intra <= -3 and close_pos <= 0.25 and rvol >= 2:
        return "intraday_distribution"
    if row["return_pct"] >= 4:
        return "positive_expansion"
    if row["return_pct"] <= -4:
        return "negative_expansion"
    return "ordinary"


def add_benchmark(cg: pd.DataFrame, nifty: pd.DataFrame) -> pd.DataFrame:
    result = cg.join(nifty[["return_pct"]].rename(columns={"return_pct": "nifty_return_pct"}), how="left")
    result["abnormal_vs_nifty_pct"] = result["return_pct"] - result["nifty_return_pct"]
    return result


def top_moves(daily: pd.DataFrame, count: int = 20) -> pd.DataFrame:
    chosen = pd.concat([daily.nlargest(count, "return_pct"), daily.nsmallest(count, "return_pct")])
    chosen = chosen[~chosen.index.duplicated()].sort_values("return_pct", ascending=False).copy()
    chosen.index.name = "Date"
    return chosen


def weekly_moves(daily: pd.DataFrame) -> pd.DataFrame:
    weekly = daily.resample("W-FRI").agg(Open=("Open", "first"), High=("High", "max"),
                                          Low=("Low", "min"), Close=("Close", "last"),
                                          Volume=("Volume", "sum"))
    weekly["return_pct"] = weekly["Close"].pct_change() * 100
    weekly["range_pct"] = (weekly["High"] / weekly["Low"] - 1) * 100
    selected = pd.concat([weekly.nlargest(15, "return_pct"), weekly.nsmallest(15, "return_pct")])
    return selected[~selected.index.duplicated()].sort_values("return_pct", ascending=False)


def event_windows(events: list[Event], daily: pd.DataFrame) -> pd.DataFrame:
    trading_days = daily.index
    records = []
    for event in events:
        announced = pd.Timestamp(event.announcement_date)
        intended_reaction = pd.Timestamp(event.reaction_date)
        pos = trading_days.searchsorted(intended_reaction)
        if pos >= len(trading_days):
            continue
        trade_date = trading_days[pos]
        row = daily.loc[trade_date]
        records.append({
            **event.__dict__, "trading_date": trade_date,
            "days_to_market": int((trade_date - announced).days),
            "pre5_pct": row["pre5_pct"], "pre20_pct": row["pre20_pct"],
            "event_return_pct": row["return_pct"], "gap_pct": row["gap_pct"],
            "intraday_pct": row["intraday_pct"], "range_pct": row["range_pct"],
            "volume_ratio20": row["volume_ratio20"], "close_position": row["close_position"],
            "nifty_return_pct": row.get("nifty_return_pct", np.nan),
            "abnormal_vs_nifty_pct": row.get("abnormal_vs_nifty_pct", np.nan),
            "post1_pct": row["post1_pct"], "post5_pct": row["post5_pct"],
            "post20_pct": row["post20_pct"], "path_type": row["path_type"],
        })
    return pd.DataFrame(records)


def chart_price_events(daily: pd.DataFrame, events: pd.DataFrame) -> None:
    view = daily.loc["2023-01-01":]
    fig, ax = plt.subplots(figsize=(14, 6.5))
    ax.plot(view.index, view["Close"], color="#195B8A", linewidth=1.6)
    selected_labels = {
        "OSAT application disclosed", "Cabinet approves Rs 7,600cr OSAT unit",
        "Indian election-result risk shock", "G.G. Tronics acquisition announced",
        "Q4 FY25 industrial-margin disappointment",
        "Q3 FY26 results: growth and backlog", "Power-equipment procurement policy shock",
    }
    annotate = events[events["label"].isin(selected_labels)].sort_values("trading_date").reset_index(drop=True)
    offsets = [(8, 35), (8, -55), (8, -55), (8, 35), (8, -55), (8, 35), (8, 35), (8, -55)]
    for (_, row), offset in zip(annotate.iterrows(), offsets):
        date = row["trading_date"]
        y = daily.loc[date, "Close"]
        ax.annotate(row["label"], xy=(date, y), xytext=offset, textcoords="offset points",
                    fontsize=7.5, arrowprops={"arrowstyle": "-", "color": "#6B7280", "lw": 0.7},
                    bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "#D1D5DB", "alpha": 0.9})
    ax.set_title("CGPOWER: material events on the price chart", loc="left", fontsize=15, weight="bold")
    ax.set_ylabel("Close price (Rs)")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(CHARTS / "01_price_and_events.png", dpi=180)
    plt.close(fig)


def chart_move_decomposition(moves: pd.DataFrame) -> None:
    display = pd.concat([moves.nlargest(10, "return_pct"), moves.nsmallest(10, "return_pct")]).sort_values("return_pct")
    labels = display.index.strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.barh(labels, display["gap_pct"], color="#4C78A8", label="Overnight gap")
    ax.barh(labels, display["intraday_pct"], left=display["gap_pct"], color="#F28E2B", label="09:15 to close")
    ax.axvline(0, color="#374151", linewidth=0.8)
    ax.set_title("Largest CGPOWER sessions: gap versus intraday move", loc="left", fontsize=14, weight="bold")
    ax.set_xlabel("Return contribution (%)")
    ax.legend(frameon=False, ncol=2, loc="lower right")
    ax.grid(axis="x", alpha=0.18)
    fig.tight_layout()
    fig.savefig(CHARTS / "02_gap_vs_intraday.png", dpi=180)
    plt.close(fig)


def chart_event_windows(events: pd.DataFrame) -> None:
    display = events.sort_values("event_return_pct").copy()
    y = np.arange(len(display))
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.barh(y - 0.22, display["event_return_pct"], height=0.42, color="#4C78A8", label="Event session")
    ax.barh(y + 0.22, display["post5_pct"], height=0.42, color="#F28E2B", label="Next 5 sessions")
    ax.set_yticks(y, display["label"])
    ax.axvline(0, color="#374151", linewidth=0.8)
    ax.set_title("Announcement reaction and five-session follow-through", loc="left", fontsize=14, weight="bold")
    ax.set_xlabel("Return (%)")
    ax.legend(frameon=False)
    ax.grid(axis="x", alpha=0.18)
    fig.tight_layout()
    fig.savefig(CHARTS / "03_event_reaction_followthrough.png", dpi=180)
    plt.close(fig)


def chart_intraday_paths(minutes: pd.DataFrame) -> None:
    dates = ["2023-11-22", "2023-11-24", "2024-06-04", "2025-04-07",
             "2025-05-06", "2026-01-28", "2026-07-03", "2026-08-04"]
    fig, axes = plt.subplots(4, 2, figsize=(13, 13), sharex=True)
    for ax, date_text in zip(axes.flat, dates):
        date = pd.Timestamp(date_text)
        day = minutes[minutes["Date"] == date].copy()
        if day.empty:
            ax.set_visible(False)
            continue
        normalized = (day["Close"] / day.iloc[0]["Open"] - 1) * 100
        x = (day["Datetime"] - day.iloc[0]["Datetime"]).dt.total_seconds() / 60
        ax.plot(x, normalized, color="#195B8A", linewidth=1.4)
        ax.fill_between(x, 0, normalized, where=normalized >= 0, color="#59A14F", alpha=0.18)
        ax.fill_between(x, 0, normalized, where=normalized < 0, color="#E15759", alpha=0.15)
        ax.axhline(0, color="#6B7280", linewidth=0.7)
        ax.set_title(date_text, loc="left", fontsize=10, weight="bold")
        ax.set_ylabel("From open (%)")
        ax.grid(alpha=0.15)
    for ax in axes[-1]:
        ax.set_xlabel("Minutes after 09:15")
    fig.suptitle("Intraday anatomy of representative CGPOWER shock sessions", x=0.06, ha="left", fontsize=15, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(CHARTS / "04_intraday_shock_paths.png", dpi=180)
    plt.close(fig)


def write_findings(daily: pd.DataFrame, events: pd.DataFrame) -> None:
    event_follow = events.groupby("path_type").agg(
        Events=("label", "size"), MedianEventReturn=("event_return_pct", "median"),
        MedianPost5=("post5_pct", "median"), MedianPost20=("post20_pct", "median"),
    ).round(2)
    headers = ["Path type", *event_follow.columns]
    table_rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for index, row in event_follow.iterrows():
        values = [str(index), *[str(value) for value in row.tolist()]]
        table_rows.append("| " + " | ".join(values) + " |")
    event_table = "\n".join(table_rows)
    text = f"""# CGPOWER big-move attribution

Data checked: {daily.index.min().date()} to {daily.index.max().date()}, {len(daily):,} trading sessions. NIFTY-relative attribution begins only when local NIFTY data starts (2024-06-26).

## What the chart says

- **Fresh information is traded during the session.** The cleanest positive repricing days have a modest gap, strong open-to-close progress, high relative volume, and a close near the day's high. The 22-Nov-2023 OSAT application and 28-Jan-2026 Q3 result are the clearest examples.
- **A large gap is not automatically momentum.** 03-Jun-2024 and 03-Feb-2026 delivered most of their gain before the open, then made little or negative progress intraday. Chasing those opens paid a very different price from owning before the information.
- **Bad news has two distinct shapes.** Margin disappointment on 06-May-2025 became persistent intraday distribution; the global shock on 07-Apr-2025 opened sharply lower but recovered during the session. Direction alone is insufficient: gap size, VWAP acceptance, and broad-market confirmation matter.
- **The business changed structurally after FY24.** Semiconductor optionality, transformer capacity expansion, data-centre orders, and a rapidly growing backlog created repeated company-specific repricing. Industrial-margin pressure and working-capital consumption explain why strong order growth did not remove downside shocks.
- **The existing G01 result must be treated as regime-dependent.** Its stronger 2025-26 historical performance should not be assumed to describe 2021-24 or a future valuation-compression regime.

## The moves that matter

- **22-Nov-2023, OSAT application:** +20.41%, almost entirely created after the open, on 11.79x normal volume. This was genuine intraday price discovery, but it gave back 3.76% over the next five sessions.
- **29-Feb-2024, Cabinet OSAT approval:** +4.94%, followed by another +4.64% over five sessions. Unlike the first OSAT spike, this repricing developed into a broader rerating.
- **29-Jan-2025 and 28-Jan-2026, earnings/capex:** +7.68% and +8.67%; both were mostly intraday, high-volume, company-specific moves. The FY25 reaction faded over five sessions, while the FY26 reaction extended another 13.39%, showing that the same chart shape can have different forward outcomes.
- **06-May-2025, margin disappointment:** -6.22%, with -6.58% from open to close. Price sold off late and persistently, yet recovered 9.30% over five sessions; bad event-day momentum was not automatically a swing short.
- **07-Apr-2025, tariff panic:** -10.49% opening gap but +3.77% open-to-close recovery. This was broad risk liquidation, not the same microstructure as company-specific distribution.
- **03-Jul-2026, procurement-policy shock:** -6.58% despite NIFTY rising 0.43%, on 7.14x normal volume. That is a clean sector/company-policy shock and the opposite of a market-beta move.

## Event path summary

{event_table}

## Trading implications to validate, not assumptions

1. Use an event-session classifier before the normal momentum rules: overnight gap, relative volume, NIFTY-relative return, first-30-minute VWAP acceptance, and close location.
2. Continue positive moves only after price accepts above VWAP and the opening range; avoid gap-only opens that fail to extend.
3. For negative gaps, distinguish company-specific distribution from market-wide panic. A recovery above VWAP after a broad-market shock is not the same setup as a margin-led breakdown.
4. Train any new rule through 2024 and freeze it before testing 2025-Aug-2026. These observations explain history; they are not yet a tradable edge.

## Files

- `big_move_days.csv`: largest up/down sessions with gap, intraday, volume, timing, and NIFTY-relative fields.
- `big_move_weeks.csv`: largest weekly expansions and contractions.
- `event_move_windows.csv`: sourced events mapped to the next trading session and forward returns.
- `material_events.csv`: source ledger.
- `charts/`: visual evidence.
"""
    (OUT / "big_move_findings.md").write_text(text, encoding="utf-8")


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    cg_minutes = load_candles(CG_PATH)
    nifty_minutes = load_candles(NIFTY_PATH)
    cg_daily = intraday_profiles(cg_minutes, aggregate_daily(cg_minutes))
    nifty_daily = aggregate_daily(nifty_minutes)
    cg_daily = add_benchmark(cg_daily, nifty_daily)
    cg_daily["path_type"] = cg_daily.apply(classify_path, axis=1)

    moves = top_moves(cg_daily)
    weeks = weekly_moves(cg_daily)
    events = event_windows(EVENTS, cg_daily)
    material = pd.DataFrame([event.__dict__ for event in EVENTS])

    moves.to_csv(OUT / "big_move_days.csv", float_format="%.4f")
    weeks.to_csv(OUT / "big_move_weeks.csv", float_format="%.4f")
    events.to_csv(OUT / "event_move_windows.csv", index=False, float_format="%.4f")
    material.to_csv(OUT / "material_events.csv", index=False)

    chart_price_events(cg_daily, events)
    chart_move_decomposition(moves)
    chart_event_windows(events)
    chart_intraday_paths(cg_minutes)
    write_findings(cg_daily, events)

    coverage = f"{cg_daily.index.min().date()}..{cg_daily.index.max().date()}"
    print(f"CGPOWER attribution complete: {len(cg_daily)} sessions ({coverage}), {len(events)} events, {len(moves)} big-move days.")


if __name__ == "__main__":
    main()
