"""Test NIFTY-aligned HDFCBANK VWAP pullbacks and VWAP fades without lookahead."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from Research.CGPOWER.cgpower_session_microstructure import metrics, simulate_trade_detail


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CHARTS = OUT / "session_charts"
HDFC_PATH = ROOT / "Data" / "HDFCBANK" / "HDFCBANK_1MIN.csv"
NIFTY_PATH = ROOT / "Data" / "NIFTY" / "NIFTY_1MIN.csv"
DISCOVERY_END = pd.Timestamp("2025-06-30")
HOLDOUT_START = pd.Timestamp("2025-07-01")


def load_aligned() -> dict[pd.Timestamp, pd.DataFrame]:
    cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    hdfc = pd.read_csv(HDFC_PATH, usecols=cols, parse_dates=["Datetime"]).rename(
        columns={column: f"H_{column}" for column in cols if column != "Datetime"})
    nifty = pd.read_csv(NIFTY_PATH, usecols=cols, parse_dates=["Datetime"]).rename(
        columns={column: f"N_{column}" for column in cols if column != "Datetime"})
    data = hdfc.merge(nifty, on="Datetime", how="inner").sort_values("Datetime")
    data = data[data["Datetime"].dt.strftime("%H:%M").between("09:15", "15:29")].copy()
    data["Date"] = data["Datetime"].dt.normalize()
    data["Time"] = data["Datetime"].dt.strftime("%H:%M")
    sessions = {}
    for date, day in data.groupby("Date", sort=True):
        if len(day) < 365 or not {"09:15", "09:45", "15:14"}.issubset(set(day["Time"])):
            continue
        day = day.reset_index(drop=True).copy()
        h_typical = (day["H_High"] + day["H_Low"] + day["H_Close"]) / 3
        day["H_VWAP"] = (h_typical * day["H_Volume"]).cumsum() / day["H_Volume"].cumsum().replace(0, np.nan)
        n_typical = (day["N_High"] + day["N_Low"] + day["N_Close"]) / 3
        day["N_TWAP"] = n_typical.expanding().mean()
        day["N_EMA9"] = day["N_Close"].ewm(span=9, adjust=False).mean()
        day["N_EMA21"] = day["N_Close"].ewm(span=21, adjust=False).mean()
        day["H_EMA9"] = day["H_Close"].ewm(span=9, adjust=False).mean()
        day["H_R5"] = day["H_Close"].pct_change(5)
        day["H_R15"] = day["H_Close"].pct_change(15)
        day["N_FromOpen"] = day["N_Close"] / day.iloc[0]["N_Open"] - 1
        day["H_FromOpen"] = day["H_Close"] / day.iloc[0]["H_Open"] - 1
        day["H_VWAPDist"] = day["H_Close"] / day["H_VWAP"] - 1
        sessions[date] = day
    return sessions


def simulate(day: pd.DataFrame, signal_idx: int, direction: int, stop_lookback: int,
             target_r: float | None, target_vwap: bool = False) -> dict | None:
    if signal_idx + 1 >= len(day):
        return None
    entry_idx = signal_idx + 1
    entry_time = str(day.loc[entry_idx, "Time"])
    if entry_time > "14:30":
        return None
    entry = float(day.loc[entry_idx, "H_Open"])
    history = day.iloc[max(0, signal_idx - stop_lookback + 1):signal_idx + 1]
    stop = float(history["H_Low"].min()) if direction > 0 else float(history["H_High"].max())
    risk = direction * (entry - stop)
    if risk <= 0 or risk / entry > 0.008:
        return None
    if target_vwap:
        target = float(day.loc[signal_idx, "H_VWAP"])
        reward = direction * (target - entry)
        if reward / risk < 1.2:
            return None
    else:
        target = entry + direction * float(target_r) * risk
    trade_day = day.rename(columns={
        "H_Open": "Open", "H_High": "High", "H_Low": "Low", "H_Close": "Close",
    })
    result = simulate_trade_detail(trade_day, direction, entry_time, "15:14", stop, target)
    return {"SignalTime": str(day.loc[signal_idx, "Time"]), "Direction": direction,
            "NiftyFromOpen": day.loc[signal_idx, "N_FromOpen"],
            "HDFCVWAPDistance": day.loc[signal_idx, "H_VWAPDist"], **result}


def trend_pullback(sessions: dict[pd.Timestamp, pd.DataFrame], variant: str,
                   stop_lookback: int, target_r: float,
                   start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> pd.DataFrame:
    rows = []
    for date, day in sessions.items():
        if start is not None and date < start or end is not None and date > end:
            continue
        previous = day.shift(1)
        long_cross = (previous["H_Close"] <= previous["H_VWAP"]) & (day["H_Close"] > day["H_VWAP"])
        short_cross = (previous["H_Close"] >= previous["H_VWAP"]) & (day["H_Close"] < day["H_VWAP"])
        n_long = (day["N_Close"] > day["N_TWAP"]) & (day["N_EMA9"] > day["N_EMA21"])
        n_short = (day["N_Close"] < day["N_TWAP"]) & (day["N_EMA9"] < day["N_EMA21"])
        if "nifty_10bp" in variant:
            n_long &= day["N_FromOpen"] > 0.001
            n_short &= day["N_FromOpen"] < -0.001
        if "hdfc_5m" in variant:
            n_long &= day["H_R5"] > 0
            n_short &= day["H_R5"] < 0
        if "hdfc_15m" in variant:
            n_long &= day["H_R15"] > 0
            n_short &= day["H_R15"] < 0
        eligible_time = day["Time"].between("09:45", "13:30")
        candidates = day.index[eligible_time & ((long_cross & n_long) | (short_cross & n_short))]
        for idx in candidates:
            direction = 1 if long_cross.loc[idx] and n_long.loc[idx] else -1
            result = simulate(day, int(idx), direction, stop_lookback, target_r)
            if result is not None:
                rows.append({"Date": date, "Family": "trend_pullback", "Variant": variant, **result})
                break
    return pd.DataFrame(rows)


def vwap_fade(sessions: dict[pd.Timestamp, pd.DataFrame], deviation: float,
              stop_lookback: int, nifty_tolerance: float,
              start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> pd.DataFrame:
    rows = []
    for date, day in sessions.items():
        if start is not None and date < start or end is not None and date > end:
            continue
        previous = day.shift(1)
        long_reversal = (previous["H_Close"] <= previous["H_EMA9"]) & (day["H_Close"] > day["H_EMA9"]) & (day["H_VWAPDist"] <= -deviation)
        short_reversal = (previous["H_Close"] >= previous["H_EMA9"]) & (day["H_Close"] < day["H_EMA9"]) & (day["H_VWAPDist"] >= deviation)
        n_not_bearish = day["N_Close"] / day["N_TWAP"] - 1 >= -nifty_tolerance
        n_not_bullish = day["N_Close"] / day["N_TWAP"] - 1 <= nifty_tolerance
        eligible = day["Time"].between("09:45", "13:30")
        candidates = day.index[eligible & ((long_reversal & n_not_bearish) | (short_reversal & n_not_bullish))]
        for idx in candidates:
            direction = 1 if long_reversal.loc[idx] and n_not_bearish.loc[idx] else -1
            result = simulate(day, int(idx), direction, stop_lookback, None, target_vwap=True)
            if result is not None:
                rows.append({"Date": date, "Family": "vwap_fade",
                             "Variant": f"dev={deviation:.4f}|tol={nifty_tolerance:.4f}", **result})
                break
    return pd.DataFrame(rows)


def evaluate_grid(sessions: dict[pd.Timestamp, pd.DataFrame]) -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame]:
    rows = []
    specs = []
    for variant in ("base", "nifty_10bp", "hdfc_5m", "nifty_10bp_hdfc_5m", "nifty_10bp_hdfc_15m"):
        for stop in (10, 20):
            for target in (1.5, 2.0):
                trades = trend_pullback(sessions, variant, stop, target, end=DISCOVERY_END)
                spec = {"Family": "trend_pullback", "Variant": variant, "StopLookback": stop,
                        "TargetR": target, "Deviation": np.nan, "NiftyTolerance": np.nan}
                rows.append({**spec, **metrics(trades)})
                specs.append((spec, trades))
    for deviation in (0.003, 0.005):
        for stop in (10, 20):
            for tolerance in (0.001, 0.002):
                trades = vwap_fade(sessions, deviation, stop, tolerance, end=DISCOVERY_END)
                spec = {"Family": "vwap_fade", "Variant": "fade", "StopLookback": stop,
                        "TargetR": np.nan, "Deviation": deviation, "NiftyTolerance": tolerance}
                rows.append({**spec, **metrics(trades)})
                specs.append((spec, trades))
    grid = pd.DataFrame(rows)
    eligible = grid[(grid["Trades"] >= 20) & (grid["Expectancy"] > 0)].copy()
    if eligible.empty:
        eligible = grid[grid["Trades"] >= 10].copy()
    eligible["Score"] = eligible["ProfitFactor"].clip(upper=3) * np.sqrt(eligible["Trades"]) * (1 + eligible["Expectancy"] * 100)
    best = eligible.sort_values(["Score", "ProfitFactor"], ascending=False).iloc[0].to_dict()
    if best["Family"] == "trend_pullback":
        discovery = trend_pullback(sessions, str(best["Variant"]), int(best["StopLookback"]), float(best["TargetR"]), end=DISCOVERY_END)
        holdout = trend_pullback(sessions, str(best["Variant"]), int(best["StopLookback"]), float(best["TargetR"]), start=HOLDOUT_START)
    else:
        discovery = vwap_fade(sessions, float(best["Deviation"]), int(best["StopLookback"]), float(best["NiftyTolerance"]), end=DISCOVERY_END)
        holdout = vwap_fade(sessions, float(best["Deviation"]), int(best["StopLookback"]), float(best["NiftyTolerance"]), start=HOLDOUT_START)
    return grid, best, discovery, holdout


def passes_research_gate(summary: pd.DataFrame) -> bool:
    """Require a real edge in both untouched samples before promotion."""
    if set(summary["Sample"]) != {"Discovery", "Holdout"}:
        return False
    return bool(
        (summary["Trades"] >= 20).all()
        and (summary["ProfitFactor"] > 1.0).all()
        and (summary["Expectancy"] > 0).all()
    )


def yearly_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if trades.empty:
        return pd.DataFrame()
    for year, group in trades.groupby(trades["Date"].dt.year):
        rows.append({"Year": int(year), **metrics(group)})
    return pd.DataFrame(rows)


def chart_results(discovery: pd.DataFrame, holdout: pd.DataFrame, replay: pd.DataFrame,
                  sessions: dict[pd.Timestamp, pd.DataFrame]) -> None:
    combined = pd.concat([discovery.assign(Sample="Discovery"), holdout.assign(Sample="Holdout")])
    equity = (1 + combined["NetReturn"]).cumprod()
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(combined["Date"], equity, color="#195B8A")
    ax.axvline(HOLDOUT_START, color="#F28E2B", linestyle="--", label="Holdout begins")
    ax.set_title("HDFCBANK index-aligned candidate equity", loc="left", weight="bold")
    ax.set_ylabel("Growth of 1.0 unit")
    ax.legend(frameon=False)
    ax.grid(alpha=0.18)
    fig.tight_layout()
    fig.savefig(CHARTS / "06_index_aligned_equity.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(3, 2, figsize=(13, 11), sharex=True)
    for ax, (_, trade) in zip(axes.flat, replay.iterrows()):
        day = sessions[trade["Date"]]
        path = (day["H_Close"] / day.iloc[0]["H_Open"] - 1) * 100
        ax.plot(np.arange(len(day)), path, color="#195B8A" if trade["Direction"] > 0 else "#F28E2B")
        signal_idx = day.index[day["Time"] == trade["SignalTime"]][0]
        ax.axvline(signal_idx, color="#6B7280", linestyle="--")
        ax.axhline(0, color="#6B7280", linewidth=0.7)
        ax.set_title(f"{trade['Date'].date()} | net {trade['NetReturn']:.2%} | {trade['ExitReason']}", loc="left", weight="bold", fontsize=10)
        ax.grid(alpha=0.15)
    fig.suptitle("HDFCBANK candidate mental paper trades: best and worst holdout days", x=0.06, ha="left", weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(CHARTS / "07_index_aligned_replays.png", dpi=180)
    plt.close(fig)


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    sessions = load_aligned()
    grid, best, discovery, holdout = evaluate_grid(sessions)
    summary = pd.DataFrame([
        {"Sample": "Discovery", **metrics(discovery)},
        {"Sample": "Holdout", **metrics(holdout)},
    ])
    qualified = passes_research_gate(summary)
    all_trades = pd.concat([discovery.assign(Sample="Discovery"), holdout.assign(Sample="Holdout")])
    yearly = yearly_metrics(all_trades)
    replay = pd.concat([holdout.nlargest(3, "NetReturn"), holdout.nsmallest(3, "NetReturn")]).drop_duplicates("Date").sort_values("Date")

    grid.to_csv(OUT / "index_aligned_grid_discovery.csv", index=False)
    summary.to_csv(OUT / "index_aligned_train_holdout.csv", index=False)
    all_trades.to_csv(OUT / "index_aligned_trades.csv", index=False)
    yearly.to_csv(OUT / "index_aligned_yearly.csv", index=False)
    replay.to_csv(OUT / "index_aligned_mental_replays.csv", index=False)
    chart_results(discovery, holdout, replay, sessions)

    report = f"""# HDFCBANK index-aligned strategy experiment

NIFTY cash-index volume is zero, so this study uses expanding intraday average price (TWAP) and EMA direction for NIFTY. HDFCBANK uses true VWAP.

Best diagnostic candidate from the discovery grid (not automatically tradable):\n{best}

{summary.to_string(index=False)}

Research gate: {'PASS' if qualified else 'FAIL'}. A pass requires at least 20 trades, Profit Factor above 1.0, and positive expectancy in both discovery and untouched holdout data.

Yearly:\n{yearly.to_string(index=False)}

The candidate is acceptable only if its holdout remains profitable after 10 bps costs and does not depend on one small group of trades.
"""
    (OUT / "index_aligned_findings.md").write_text(report, encoding="utf-8")
    print("BEST DIAGNOSTIC CANDIDATE", best)
    print(summary.to_string(index=False))
    print("RESEARCH GATE", "PASS" if qualified else "FAIL")
    print(yearly.to_string(index=False))


if __name__ == "__main__":
    main()
