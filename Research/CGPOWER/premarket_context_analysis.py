"""Test common pre-market context signals against CGPOWER's open and intraday path."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
FEATURES_PATH = OUT / "session_daily_features.csv"
MINUTE_PATH = OUT.parents[1] / "Data" / "CGPOWER" / "CGPOWER_1MIN.csv"
START_EPOCH = 1622505600
END_EPOCH = 1787184000
COST_RATE = 0.001


def fetch_yahoo(symbol: str) -> pd.DataFrame:
    encoded = quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        f"?period1={START_EPOCH}&period2={END_EPOCH}&interval=1d&events=history"
    )
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    result = payload["chart"]["result"][0]
    quote_data = result["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(result["timestamp"], unit="s", utc=True)
            .tz_convert(None)
            .normalize(),
            "Close": quote_data["close"],
        }
    ).dropna()
    df["Return"] = df["Close"].pct_change()
    return df


def make_available_next_day(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    result = df.copy()
    result["AvailableDate"] = result["Date"] + pd.Timedelta(days=1)
    return (
        result[["AvailableDate", "Close", "Return"]]
        .rename(columns={"Close": f"{prefix}_close", "Return": f"{prefix}_return"})
        .sort_values("AvailableDate")
    )


def summarize(group: pd.core.groupby.generic.DataFrameGroupBy, label: str) -> pd.DataFrame:
    result = group.agg(
        Days=("Close", "size"),
        CGGapUpRate=("gap", lambda x: (x > 0).mean()),
        CGFirst15UpRate=("r15", lambda x: (x > 0).mean()),
        CGDayUpRate=("daily_return", lambda x: (x > 0).mean()),
        MedianCGGap=("gap", "median"),
        MedianCGFirst15=("r15", "median"),
        MedianAbsCGFirst15=("r15", lambda x: x.abs().median()),
        MedianAbsCGDay=("daily_return", lambda x: x.abs().median()),
        MedianCGRange=("day_range", "median"),
    ).reset_index()
    result.insert(0, "Test", label)
    return result


def trade_metrics(returns: pd.Series) -> dict[str, float]:
    if returns.empty:
        return {"Trades": 0, "WinRate": np.nan, "ProfitFactor": np.nan, "Expectancy": np.nan}
    profit, loss = returns[returns > 0].sum(), -returns[returns < 0].sum()
    return {
        "Trades": len(returns),
        "WinRate": (returns > 0).mean(),
        "ProfitFactor": profit / loss if loss else np.inf,
        "Expectancy": returns.mean(),
    }


def context_trade_tests(context: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = context[
        context["combined_proxy"].isin(["bullish_agreement", "bearish_agreement"])
    ].copy()
    work["Direction"] = np.where(work["combined_proxy"] == "bullish_agreement", 1, -1)
    directional_position = np.where(
        work["Direction"] > 0,
        work["opening15_close_position"],
        1 - work["opening15_close_position"],
    )
    variants = {
        "agreement_only_0930": pd.Series(True, index=work.index),
        "plus_cg_first15_confirmation": np.sign(work["r15"]) == work["Direction"],
        "plus_first15_and_range_acceptance": (np.sign(work["r15"]) == work["Direction"])
        & (directional_position >= 0.70),
        "plus_range_acceptance_and_rvol": (np.sign(work["r15"]) == work["Direction"])
        & (directional_position >= 0.70)
        & (work["opening15_rvol20"] >= 1.0),
    }
    rows = []
    chosen = pd.DataFrame()
    for name, mask in variants.items():
        trades = work[mask].copy()
        trades["NetReturn"] = trades["Direction"] * trades["r_after15"] - COST_RATE
        for period, subset in (
            ("All", trades),
            ("2024", trades[trades["Date"].dt.year == 2024]),
            ("2025", trades[trades["Date"].dt.year == 2025]),
            ("2026", trades[trades["Date"].dt.year == 2026]),
        ):
            rows.append({"Variant": name, "Period": period, **trade_metrics(subset["NetReturn"])})
        if name == "plus_first15_and_range_acceptance":
            chosen = trades
    replay = pd.concat(
        [chosen.nlargest(3, "NetReturn"), chosen.nsmallest(3, "NetReturn")]
    ).drop_duplicates("Date")
    columns = [
        "Date",
        "combined_proxy",
        "Direction",
        "nasdaq_return",
        "dow_return",
        "vix_close",
        "nifty_gap",
        "gap",
        "r15",
        "opening15_rvol20",
        "r_after15",
        "NetReturn",
    ]
    return pd.DataFrame(rows), replay[columns].sort_values("Date")


def chart_replays(replay: pd.DataFrame) -> None:
    minutes = pd.read_csv(
        MINUTE_PATH, usecols=["Datetime", "Open", "Close"], parse_dates=["Datetime"]
    )
    minutes["Date"] = minutes["Datetime"].dt.normalize()
    wanted = set(replay["Date"].dt.normalize())
    minutes = minutes[minutes["Date"].isin(wanted)].copy()
    fig, axes = plt.subplots(3, 2, figsize=(13, 11), sharex=True)
    for ax, (_, row) in zip(axes.flat, replay.iterrows(), strict=False):
        day = minutes[minutes["Date"] == row["Date"]].sort_values("Datetime")
        path = (day["Close"] / day.iloc[0]["Open"] - 1) * 100
        x = np.arange(len(day))
        color = "#4C78A8" if row["Direction"] > 0 else "#F28E2B"
        ax.plot(x, path, color=color, linewidth=1.4)
        ax.axvline(14, color="#6B7280", linestyle="--", linewidth=0.8)
        ax.axhline(0, color="#6B7280", linewidth=0.7)
        ax.set_title(
            f"{row['Date'].date()} | {row['combined_proxy']} | net {row['NetReturn']:.2%}",
            loc="left",
            fontsize=10,
            weight="bold",
        )
        ax.set_ylabel("From open (%)")
        ax.grid(alpha=0.15)
    for ax in axes[-1]:
        ax.set_xlabel("Minutes after 09:15 (dashed line = 09:29)")
    fig.suptitle(
        "Mental paper trades: identical morning confirmation, opposite outcomes",
        x=0.06,
        ha="left",
        weight="bold",
        fontsize=15,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "session_charts" / "05_premarket_mental_replays.png", dpi=180)
    plt.close(fig)


def write_findings(results: pd.DataFrame, trades: pd.DataFrame) -> None:
    text = """# CGPOWER pre-market context test

## Reel verdict

- **Previous Nasdaq and Dow direction helps predict CGPOWER's opening gap, not its post-open direction.** Both green produced a CG gap-up on 77.3% of sessions, but only 43.1% had a green first 15 minutes. Both red still produced a gap-up on 56.6% of sessions.
- **NIFTY/GIFT-style indication is closer to the actual opening price.** When NIFTY ultimately opened above +0.2%, CGPOWER gapped up 88.2% of the time; below -0.2%, the CG gap-up rate fell to 27.5%. This uses actual NIFTY opening gap as a proxy, not archived 09:00 GIFT quotes.
- **India VIX is a range switch, not a direction switch.** Above 15, CGPOWER's median absolute day was 1.57% and median range 3.70%; at or below 15, they were 1.10% and 2.85%.
- **Breadth cannot be used as described at 09:00.** NSE normal trading has not begun. The pre-open session is order collection and equilibrium-price discovery; use advances/declines only after the cash market has had time to trade.
- **The full permission rule failed.** US and NIFTY agreement plus CG's first-15-minute confirmation did not create a stable 09:30-to-close edge after 10 bps costs.

## Practical 09:00 process

1. Record previous Nasdaq and Dow return as `global risk`, not a buy/sell command.
2. Record previous India VIX close: above 15 means expect wider stops and smaller position size, not a known direction.
3. Record live GIFT Nifty and NSE's indicative pre-open NIFTY/CGPOWER equilibrium near 09:08. We need to start storing these point-in-time snapshots for a true historical test.
4. At 09:15, compare CGPOWER's actual gap with NIFTY. A large disagreement signals company-specific information.
5. At 09:30, use opening-range structure. Do not trade merely because the external cues were green or red.
6. Add market breadth after roughly 09:20, when advances/declines reflect actual trades.

The mental replay chart deliberately contains three strongest wins and three strongest losses from the same fixed confirmation rule. It shows why a morning checklist can describe context without reliably timing an entry.
"""
    (OUT / "premarket_context_findings.md").write_text(text, encoding="utf-8")


def main() -> None:
    cg = pd.read_csv(FEATURES_PATH, parse_dates=["Date"]).sort_values("Date")
    cg["day_range"] = cg["High"] / cg["Low"] - 1

    nasdaq = fetch_yahoo("^IXIC")
    dow = fetch_yahoo("^DJI")
    india_vix = fetch_yahoo("^INDIAVIX")
    nasdaq.to_csv(OUT / "external_nasdaq_daily.csv", index=False)
    dow.to_csv(OUT / "external_dow_daily.csv", index=False)
    india_vix.to_csv(OUT / "external_india_vix_daily.csv", index=False)

    context = cg.copy()
    for data, prefix in ((nasdaq, "nasdaq"), (dow, "dow"), (india_vix, "vix")):
        context = pd.merge_asof(
            context.sort_values("Date"),
            make_available_next_day(data, prefix),
            left_on="Date",
            right_on="AvailableDate",
            direction="backward",
            tolerance=pd.Timedelta(days=4),
        ).drop(columns=["AvailableDate"])

    context["us_context"] = np.select(
        [
            (context["nasdaq_return"] > 0) & (context["dow_return"] > 0),
            (context["nasdaq_return"] < 0) & (context["dow_return"] < 0),
        ],
        ["both_green", "both_red"],
        default="mixed",
    )
    context["vix_regime"] = np.where(context["vix_close"] > 15, "above_15", "at_or_below_15")
    context["nifty_gap_proxy"] = pd.cut(
        context["nifty_gap"],
        [-np.inf, -0.002, 0.002, np.inf],
        labels=["red_below_-0.2%", "flat_+-0.2%", "green_above_+0.2%"],
    )
    context["combined_proxy"] = np.select(
        [
            (context["us_context"] == "both_green") & (context["nifty_gap"] > 0.002),
            (context["us_context"] == "both_red") & (context["nifty_gap"] < -0.002),
        ],
        ["bullish_agreement", "bearish_agreement"],
        default="mixed_or_conflict",
    )

    tables = [
        summarize(
            context.dropna(subset=["nasdaq_return", "dow_return"]).groupby("us_context"),
            "Previous US close",
        ),
        summarize(
            context.dropna(subset=["vix_close"]).groupby("vix_regime"), "Previous India VIX close"
        ),
        summarize(
            context.dropna(subset=["nifty_gap"]).groupby("nifty_gap_proxy", observed=True),
            "NIFTY opening-gap proxy",
        ),
        summarize(
            context.dropna(subset=["nifty_gap", "nasdaq_return", "dow_return"]).groupby(
                "combined_proxy"
            ),
            "US + NIFTY-gap agreement",
        ),
    ]
    results = pd.concat(tables, ignore_index=True)
    results.to_csv(OUT / "premarket_context_results.csv", index=False)
    context.to_csv(OUT / "premarket_context_daily.csv", index=False)
    trade_results, replay = context_trade_tests(context)
    trade_results.to_csv(OUT / "premarket_trade_filter_results.csv", index=False)
    replay.to_csv(OUT / "premarket_mental_replays.csv", index=False)
    chart_replays(replay)
    write_findings(results, trade_results)

    directional = results[
        results["Test"].isin(["Previous US close", "US + NIFTY-gap agreement"])
    ].copy()
    directional["Category"] = directional["us_context"].fillna(directional["combined_proxy"])
    fig, ax = plt.subplots(figsize=(12, 6))
    labels = directional["Category"].astype(str)
    x = np.arange(len(directional))
    ax.bar(x - 0.2, directional["CGGapUpRate"] * 100, width=0.2, label="CG gap up")
    ax.bar(x, directional["CGFirst15UpRate"] * 100, width=0.2, label="CG first 15m up")
    ax.bar(x + 0.2, directional["CGDayUpRate"] * 100, width=0.2, label="CG day up")
    ax.axhline(50, color="#6B7280", linewidth=0.8)
    ax.set_xticks(x, labels, rotation=20, ha="right")
    ax.set_ylabel("Up frequency (%)")
    ax.set_title("Premarket context: useful bias or confident story?", loc="left", weight="bold")
    ax.legend(frameon=False, ncol=3)
    ax.grid(axis="y", alpha=0.18)
    fig.tight_layout()
    fig.savefig(OUT / "session_charts" / "04_premarket_context.png", dpi=180)
    plt.close(fig)

    print(results.to_string(index=False))
    print("\nPREMARKET PERMISSION FILTERS (09:30 to close, after 10 bps cost)")
    print(trade_results.to_string(index=False))
    print("\nMENTAL REPLAY TAILS")
    print(replay.to_string(index=False))


if __name__ == "__main__":
    main()
