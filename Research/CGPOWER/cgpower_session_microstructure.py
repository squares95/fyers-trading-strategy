"""Study what moves CGPOWER around the open and close using one-minute candles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CHARTS = OUT / "session_charts"
CG_PATH = ROOT / "Data" / "CGPOWER" / "CGPOWER_1MIN.csv"
NIFTY_PATH = ROOT / "Data" / "NIFTY" / "NIFTY_1MIN.csv"
TRAIN_END = pd.Timestamp("2024-12-31")
HOLDOUT_START = pd.Timestamp("2025-01-01")
COST_RATE = 0.001  # 5 bps per side.


BOUNDARIES = {
    "c5": "09:19", "c15": "09:29", "c30": "09:44", "c60": "10:14",
    "c1430": "14:29", "c1500": "14:59", "c1515": "15:14", "close": "15:29",
}

_SESSION_CACHE: dict[int, dict[pd.Timestamp, pd.DataFrame]] = {}


@dataclass(frozen=True)
class Rule:
    name: str
    strength_atr: float
    position_min: float
    volume_quantile: float
    target_r: float


def load_minutes(path: Path) -> pd.DataFrame:
    cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    df = pd.read_csv(path, usecols=cols, parse_dates=["Datetime"])
    df = df.sort_values("Datetime").drop_duplicates("Datetime", keep="last")
    df = df[df["Datetime"].dt.strftime("%H:%M").between("09:15", "15:29")].copy()
    df["Date"] = df["Datetime"].dt.normalize()
    df["Time"] = df["Datetime"].dt.strftime("%H:%M")
    return df


def valid_sessions(minutes: pd.DataFrame) -> pd.DataFrame:
    required_times = {"09:15", *BOUNDARIES.values()}
    valid = []
    for date, day in minutes.groupby("Date", sort=True):
        times = set(day["Time"])
        if len(day) >= 365 and required_times.issubset(times):
            valid.append(date)
    return minutes[minutes["Date"].isin(valid)].copy()


def _at(day: pd.DataFrame, clock: str, column: str = "Close") -> float:
    return float(day.loc[day["Time"] == clock, column].iloc[-1])


def _window(day: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return day[day["Time"].between(start, end)]


def session_map(minutes: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    key = id(minutes)
    if key not in _SESSION_CACHE:
        _SESSION_CACHE[key] = {
            date: day.sort_values("Datetime").reset_index(drop=True)
            for date, day in minutes.groupby("Date", sort=False)
        }
    return _SESSION_CACHE[key]


def build_daily_features(minutes: pd.DataFrame) -> pd.DataFrame:
    records = []
    for date, day in minutes.groupby("Date", sort=True):
        day = day.sort_values("Datetime").copy()
        open_price = float(day.iloc[0]["Open"])
        total_volume = max(float(day["Volume"].sum()), 1.0)
        typical = (day["High"] + day["Low"] + day["Close"]) / 3
        day["CumVWAP"] = (typical * day["Volume"]).cumsum() / day["Volume"].cumsum().replace(0, np.nan)
        opening15 = _window(day, "09:15", "09:29")
        opening30 = _window(day, "09:15", "09:44")
        final60 = _window(day, "14:30", "15:29")
        final30 = _window(day, "15:00", "15:29")
        final15 = _window(day, "15:15", "15:29")
        after_open = _window(day, "09:30", "15:29")
        or_high, or_low = float(opening15["High"].max()), float(opening15["Low"].min())
        high_breaks = after_open.index[after_open["High"] > or_high].tolist()
        low_breaks = after_open.index[after_open["Low"] < or_low].tolist()
        first_high_time = day.loc[high_breaks[0], "Time"] if high_breaks else None
        first_low_time = day.loc[low_breaks[0], "Time"] if low_breaks else None
        if high_breaks and low_breaks:
            break_type = "high_then_low" if high_breaks[0] < low_breaks[0] else "low_then_high"
        elif high_breaks:
            break_type = "high_only"
        elif low_breaks:
            break_type = "low_only"
        else:
            break_type = "neither"
        c = {key: _at(day, clock) for key, clock in BOUNDARIES.items()}
        open15_span = max(or_high - or_low, 1e-12)
        day_span = max(float(day["High"].max() - day["Low"].min()), 1e-12)
        records.append({
            "Date": date, "Open": open_price, "High": day["High"].max(), "Low": day["Low"].min(),
            "Close": c["close"], "Volume": total_volume, "Bars": len(day),
            "r5": c["c5"] / open_price - 1, "r15": c["c15"] / open_price - 1,
            "r30": c["c30"] / open_price - 1, "r60": c["c60"] / open_price - 1,
            "r_after15": c["close"] / c["c15"] - 1,
            "r_mid": c["c1430"] / c["c60"] - 1,
            "r_to1430": c["c1430"] / open_price - 1,
            "r_close60": c["close"] / c["c1430"] - 1,
            "r_close30": c["close"] / c["c1500"] - 1,
            "r_close15": c["close"] / c["c1515"] - 1,
            "opening15_volume_share": opening15["Volume"].sum() / total_volume,
            "opening15_volume": opening15["Volume"].sum(),
            "opening30_volume_share": opening30["Volume"].sum() / total_volume,
            "closing60_volume_share": final60["Volume"].sum() / total_volume,
            "closing30_volume_share": final30["Volume"].sum() / total_volume,
            "closing15_volume_share": final15["Volume"].sum() / total_volume,
            "opening15_close_position": (c["c15"] - or_low) / open15_span,
            "day_close_position": (c["close"] - day["Low"].min()) / day_span,
            "position_1430": (c["c1430"] - day.loc[day["Time"] <= "14:29", "Low"].min()) /
                             max(day.loc[day["Time"] <= "14:29", "High"].max() - day.loc[day["Time"] <= "14:29", "Low"].min(), 1e-12),
            "vwap_0929": _at(day, "09:29", "CumVWAP"), "vwap_1429": _at(day, "14:29", "CumVWAP"),
            "vwap_close": _at(day, "15:29", "CumVWAP"),
            "opening_range_pct": (or_high / or_low - 1), "opening_range_share": open15_span / day_span,
            "or_high": or_high, "or_low": or_low, "break_type": break_type,
            "first_high_break": first_high_time, "first_low_break": first_low_time,
            "close_above_or": c["close"] > or_high, "close_below_or": c["close"] < or_low,
        })
    daily = pd.DataFrame(records).set_index("Date").sort_index()
    daily["PrevClose"] = daily["Close"].shift()
    daily["gap"] = daily["Open"] / daily["PrevClose"] - 1
    daily["daily_return"] = daily["Close"] / daily["PrevClose"] - 1
    true_range = pd.concat([
        daily["High"] - daily["Low"],
        (daily["High"] - daily["PrevClose"]).abs(),
        (daily["Low"] - daily["PrevClose"]).abs(),
    ], axis=1).max(axis=1)
    daily["atr20_pct"] = (true_range / daily["PrevClose"]).shift().rolling(20).mean()
    daily["r15_atr"] = daily["r15"] / daily["atr20_pct"]
    daily["r_to1430_atr"] = daily["r_to1430"] / daily["atr20_pct"]
    daily["ema20"] = daily["Close"].ewm(span=20, adjust=False).mean()
    daily["ema50"] = daily["Close"].ewm(span=50, adjust=False).mean()
    daily["trend_regime"] = np.where((daily["Close"] > daily["ema50"]) & (daily["ema20"] > daily["ema50"]), "uptrend",
                              np.where((daily["Close"] < daily["ema50"]) & (daily["ema20"] < daily["ema50"]), "downtrend", "mixed"))
    daily["prior_trend_regime"] = pd.Series(daily["trend_regime"], index=daily.index).shift()
    daily["next_gap"] = daily["Open"].shift(-1) / daily["Close"] - 1
    daily["opening15_rvol20"] = daily["opening15_volume"] / daily["opening15_volume"].shift().rolling(20).median()
    return daily


def add_nifty_features(cg: pd.DataFrame, nifty_minutes: pd.DataFrame) -> pd.DataFrame:
    nifty = build_daily_features(valid_sessions(nifty_minutes))
    fields = ["gap", "r15", "r_to1430", "r_close60", "daily_return"]
    renamed = nifty[fields].rename(columns={field: f"nifty_{field}" for field in fields})
    result = cg.join(renamed, how="left")
    result["r15_relative_nifty"] = result["r15"] - result["nifty_r15"]
    result["close60_relative_nifty"] = result["r_close60"] - result["nifty_r_close60"]
    return result


def minute_profile(minutes: pd.DataFrame) -> pd.DataFrame:
    data = minutes.copy()
    data["minute_return"] = data.groupby("Date")["Close"].pct_change()
    data["volume_share"] = data["Volume"] / data.groupby("Date")["Volume"].transform("sum")
    profile = data.groupby("Time").agg(
        mean_abs_return=("minute_return", lambda x: x.abs().mean()),
        median_abs_return=("minute_return", lambda x: x.abs().median()),
        mean_volume_share=("volume_share", "mean"),
        median_volume_share=("volume_share", "median"),
    )
    return profile


def conditional_tables(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = daily.dropna(subset=["atr20_pct"]).copy()
    work["opening_strength"] = pd.cut(work["r15_atr"],
        [-np.inf, -0.35, -0.15, 0.15, 0.35, np.inf],
        labels=["strong_down", "moderate_down", "flat", "moderate_up", "strong_up"])
    opening = work.groupby("opening_strength", observed=True).agg(
        Days=("Close", "size"), MedianFirst15=("r15", "median"),
        MedianRestOfDay=("r_after15", "median"),
        ContinueRate=("r_after15", lambda x: np.nan),
        MedianClosePosition=("day_close_position", "median"),
    )
    for label in opening.index:
        subset = work[work["opening_strength"] == label]
        direction = np.sign(subset["r15"])
        opening.loc[label, "ContinueRate"] = (np.sign(subset["r_after15"]) == direction).mean()

    breakouts = work.groupby("break_type").agg(
        Days=("Close", "size"), MedianDayReturn=("daily_return", "median"),
        MedianClosePosition=("day_close_position", "median"),
        CloseAboveOR=("close_above_or", "mean"), CloseBelowOR=("close_below_or", "mean"),
    ).sort_values("Days", ascending=False)

    work["preclose_strength"] = pd.cut(work["r_to1430_atr"],
        [-np.inf, -0.5, -0.2, 0.2, 0.5, np.inf],
        labels=["strong_down", "moderate_down", "flat", "moderate_up", "strong_up"])
    closing = work.groupby("preclose_strength", observed=True).agg(
        Days=("Close", "size"), MedianTo1430=("r_to1430", "median"),
        MedianFinalHour=("r_close60", "median"), MedianFinal30=("r_close30", "median"),
        MedianNextGap=("next_gap", "median"),
    )
    for label in closing.index:
        subset = work[work["preclose_strength"] == label]
        direction = np.sign(subset["r_to1430"])
        closing.loc[label, "FinalHourContinueRate"] = (np.sign(subset["r_close60"]) == direction).mean()
    return opening, breakouts, closing


def simulate_trade(day: pd.DataFrame, direction: int, entry_time: str, exit_time: str,
                   stop: float, target: float) -> float:
    return simulate_trade_detail(day, direction, entry_time, exit_time, stop, target)["NetReturn"]


def simulate_trade_detail(day: pd.DataFrame, direction: int, entry_time: str, exit_time: str,
                          stop: float, target: float) -> dict[str, float | str]:
    future = day[day["Time"].between(entry_time, exit_time)].sort_values("Datetime")
    if future.empty:
        return {"NetReturn": np.nan}
    entry = float(future.iloc[0]["Open"])
    exit_price = float(future.iloc[-1]["Close"])
    actual_exit_time = str(future.iloc[-1]["Time"])
    exit_reason = "time"
    for _, bar in future.iterrows():
        if direction > 0:
            stop_hit, target_hit = bar["Low"] <= stop, bar["High"] >= target
        else:
            stop_hit, target_hit = bar["High"] >= stop, bar["Low"] <= target
        if stop_hit:
            exit_price = stop
            actual_exit_time = str(bar["Time"])
            exit_reason = "stop"
            break
        if target_hit:
            exit_price = target
            actual_exit_time = str(bar["Time"])
            exit_reason = "target"
            break
    gross = direction * (exit_price / entry - 1)
    return {
        "EntryTime": entry_time, "EntryPrice": entry, "Stop": stop, "Target": target,
        "ExitTime": actual_exit_time, "ExitPrice": exit_price, "ExitReason": exit_reason,
        "GrossReturn": gross, "NetReturn": gross - COST_RATE,
    }


def evaluate_rule(rule: Rule, daily: pd.DataFrame, minutes: pd.DataFrame, volume_cutoff: float,
                  start: pd.Timestamp | None = None, end: pd.Timestamp | None = None,
                  max_risk_pct: float = 0.012) -> pd.DataFrame:
    eligible = daily.copy()
    if start is not None:
        eligible = eligible[eligible.index >= start]
    if end is not None:
        eligible = eligible[eligible.index <= end]
    rows = []
    sessions = session_map(minutes)
    for date, row in eligible.iterrows():
        if pd.isna(row["r15_atr"]) or abs(row["r15_atr"]) < rule.strength_atr:
            continue
        direction = 1 if row["r15_atr"] > 0 else -1
        directional_position = row["opening15_close_position"] if direction > 0 else 1 - row["opening15_close_position"]
        if directional_position < rule.position_min or row["opening15_rvol20"] < volume_cutoff:
            continue
        day = sessions[date]
        entry = float(day.loc[day["Time"] == "09:30", "Open"].iloc[0])
        stop = row["or_low"] if direction > 0 else row["or_high"]
        risk = direction * (entry - stop)
        if risk <= 0 or risk / entry > max_risk_pct:
            continue
        target = entry + direction * rule.target_r * risk
        net = simulate_trade(day, direction, "09:30", "15:14", stop, target)
        rows.append({"Date": date, "Direction": direction, "NetReturn": net})
    return pd.DataFrame(rows)


def metrics(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {"Trades": 0, "WinRate": np.nan, "ProfitFactor": np.nan, "Expectancy": np.nan, "MaxDrawdown": np.nan}
    r = trades["NetReturn"]
    gross_profit, gross_loss = r[r > 0].sum(), -r[r < 0].sum()
    equity = (1 + r).cumprod()
    drawdown = equity / equity.cummax() - 1
    return {
        "Trades": len(r), "WinRate": (r > 0).mean(),
        "ProfitFactor": gross_profit / gross_loss if gross_loss > 0 else np.inf,
        "Expectancy": r.mean(), "MaxDrawdown": drawdown.min(),
    }


def discover_opening_rule(daily: pd.DataFrame, minutes: pd.DataFrame) -> tuple[pd.DataFrame, Rule, float]:
    train = daily[daily.index <= TRAIN_END].dropna(subset=["r15_atr"])
    quantiles = {q: train["opening15_rvol20"].quantile(q) for q in (0.25, 0.50, 0.75)}
    results = []
    for strength in (0.15, 0.25, 0.35, 0.50):
        for position in (0.70, 0.80, 0.90):
            for volume_q, cutoff in quantiles.items():
                for target_r in (1.5, 2.0):
                    rule = Rule("opening_drive", strength, position, volume_q, target_r)
                    trades = evaluate_rule(rule, daily, minutes, cutoff, end=TRAIN_END)
                    result = {**rule.__dict__, "volume_cutoff": cutoff, **metrics(trades)}
                    results.append(result)
    grid = pd.DataFrame(results)
    robust = grid[(grid["Trades"] >= 30) & (grid["Expectancy"] > 0)].copy()
    if robust.empty:
        robust = grid[grid["Trades"] >= 20].copy()
    robust["score"] = robust["ProfitFactor"].clip(upper=4) * np.sqrt(robust["Trades"]) * (1 + robust["Expectancy"] * 100)
    best = robust.sort_values(["score", "ProfitFactor"], ascending=False).iloc[0]
    rule = Rule("opening_drive", best["strength_atr"], best["position_min"], best["volume_quantile"], best["target_r"])
    return grid, rule, float(best["volume_cutoff"])


def strategy_summary(rule: Rule, cutoff: float, daily: pd.DataFrame, minutes: pd.DataFrame) -> pd.DataFrame:
    train_trades = evaluate_rule(rule, daily, minutes, cutoff, end=TRAIN_END)
    holdout_trades = evaluate_rule(rule, daily, minutes, cutoff, start=HOLDOUT_START)
    rows = []
    for sample, trades in ((f"Discovery_through_{TRAIN_END.date()}", train_trades),
                           (f"Holdout_from_{HOLDOUT_START.date()}", holdout_trades)):
        row = {"Sample": sample, **metrics(trades)}
        rows.append(row)
    return pd.DataFrame(rows)


def evaluate_sweep_rule(daily: pd.DataFrame, minutes: pd.DataFrame, latest_signal: str,
                        stop_mode: str, target_r: float, rvol_cutoff: float,
                        start: pd.Timestamp | None = None, end: pd.Timestamp | None = None,
                        max_risk_pct: float = 0.012) -> pd.DataFrame:
    eligible = daily.copy()
    if start is not None:
        eligible = eligible[eligible.index >= start]
    if end is not None:
        eligible = eligible[eligible.index <= end]
    eligible = eligible[eligible["break_type"].isin(["low_then_high", "high_then_low"])]
    rows = []
    sessions = session_map(minutes)
    for date, row in eligible.iterrows():
        if pd.isna(row["opening15_rvol20"]) or row["opening15_rvol20"] < rvol_cutoff:
            continue
        day = sessions[date]
        after = day[(day["Time"] >= "09:30") & (day["Time"] <= latest_signal)]
        high_hits = after.index[after["High"] > row["or_high"]].tolist()
        low_hits = after.index[after["Low"] < row["or_low"]].tolist()
        if not high_hits or not low_hits or high_hits[0] == low_hits[0]:
            continue
        direction = 1 if low_hits[0] < high_hits[0] else -1
        signal_idx = high_hits[0] if direction > 0 else low_hits[0]
        if signal_idx + 1 >= len(day) or day.loc[signal_idx + 1, "Time"] > "15:14":
            continue
        entry_time = str(day.loc[signal_idx + 1, "Time"])
        entry = float(day.loc[signal_idx + 1, "Open"])
        midpoint = (row["or_high"] + row["or_low"]) / 2
        if stop_mode == "midpoint":
            stop = midpoint
        else:
            stop = row["or_low"] if direction > 0 else row["or_high"]
        risk = direction * (entry - stop)
        if risk <= 0 or risk / entry > max_risk_pct:
            continue
        target = entry + direction * target_r * risk
        trade = simulate_trade_detail(day, direction, entry_time, "15:14", stop, target)
        rows.append({
            "Date": date, "Direction": direction, "BreakType": row["break_type"],
            "SignalTime": str(day.loc[signal_idx, "Time"]), "Opening15Return": row["r15"],
            "Opening15RVOL": row["opening15_rvol20"], "Gap": row["gap"],
            "NiftyDayReturn": row.get("nifty_daily_return", np.nan), **trade,
        })
    return pd.DataFrame(rows)


def discover_sweep_rule(daily: pd.DataFrame, minutes: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | str]]:
    train = daily[daily.index <= TRAIN_END]
    rvol_levels = {
        "none": 0.0,
        "median": float(train["opening15_rvol20"].median()),
        "upper_quartile": float(train["opening15_rvol20"].quantile(0.75)),
    }
    rows = []
    for latest in ("11:30", "13:30", "14:30"):
        for stop_mode in ("midpoint", "opposite_boundary"):
            for target_r in (1.0, 1.5, 2.0):
                for rvol_name, cutoff in rvol_levels.items():
                    trades = evaluate_sweep_rule(daily, minutes, latest, stop_mode, target_r, cutoff, end=TRAIN_END)
                    rows.append({"latest_signal": latest, "stop_mode": stop_mode, "target_r": target_r,
                                 "rvol_filter": rvol_name, "rvol_cutoff": cutoff, **metrics(trades)})
    grid = pd.DataFrame(rows)
    candidates = grid[(grid["Trades"] >= 40) & (grid["Expectancy"] > 0)].copy()
    if candidates.empty:
        candidates = grid[grid["Trades"] >= 30].copy()
    candidates["score"] = candidates["ProfitFactor"].clip(upper=3) * np.sqrt(candidates["Trades"]) * (1 + candidates["Expectancy"] * 100)
    best = candidates.sort_values(["score", "ProfitFactor"], ascending=False).iloc[0]
    return grid, best.to_dict()


def sweep_summary(best: dict[str, float | str], daily: pd.DataFrame, minutes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    kwargs = dict(latest_signal=str(best["latest_signal"]), stop_mode=str(best["stop_mode"]),
                  target_r=float(best["target_r"]), rvol_cutoff=float(best["rvol_cutoff"]))
    train = evaluate_sweep_rule(daily, minutes, **kwargs, end=TRAIN_END)
    holdout = evaluate_sweep_rule(daily, minutes, **kwargs, start=HOLDOUT_START)
    summary = pd.DataFrame([
        {"Sample": f"Discovery_through_{TRAIN_END.date()}", **metrics(train)},
        {"Sample": f"Holdout_from_{HOLDOUT_START.date()}", **metrics(holdout)},
    ])
    replay = pd.concat([holdout.nlargest(3, "NetReturn"), holdout.nsmallest(3, "NetReturn")]).drop_duplicates("Date")
    return summary, replay.sort_values("Date")


def evaluate_orb_rule(daily: pd.DataFrame, minutes: pd.DataFrame, latest_signal: str,
                      stop_mode: str, target_r: float, rvol_cutoff: float,
                      position_min: float, require_gap_alignment: bool,
                      start: pd.Timestamp | None = None, end: pd.Timestamp | None = None,
                      max_risk_pct: float = 0.012) -> pd.DataFrame:
    eligible = daily.copy()
    if start is not None:
        eligible = eligible[eligible.index >= start]
    if end is not None:
        eligible = eligible[eligible.index <= end]
    rows = []
    sessions = session_map(minutes)
    for date, row in eligible.iterrows():
        if pd.isna(row["opening15_rvol20"]) or row["opening15_rvol20"] < rvol_cutoff:
            continue
        day = sessions[date]
        after = day[(day["Time"] >= "09:30") & (day["Time"] <= latest_signal)]
        high_hits = after.index[after["High"] > row["or_high"]].tolist()
        low_hits = after.index[after["Low"] < row["or_low"]].tolist()
        first_high = high_hits[0] if high_hits else np.inf
        first_low = low_hits[0] if low_hits else np.inf
        if first_high == first_low or (np.isinf(first_high) and np.isinf(first_low)):
            continue
        direction = 1 if first_high < first_low else -1
        signal_idx = int(min(first_high, first_low))
        directional_position = row["opening15_close_position"] if direction > 0 else 1 - row["opening15_close_position"]
        if directional_position < position_min:
            continue
        if require_gap_alignment and np.sign(row["gap"]) != direction:
            continue
        if signal_idx + 1 >= len(day) or day.loc[signal_idx + 1, "Time"] > "15:14":
            continue
        entry_time = str(day.loc[signal_idx + 1, "Time"])
        entry = float(day.loc[signal_idx + 1, "Open"])
        midpoint = (row["or_high"] + row["or_low"]) / 2
        stop = midpoint if stop_mode == "midpoint" else (row["or_low"] if direction > 0 else row["or_high"])
        risk = direction * (entry - stop)
        if risk <= 0 or risk / entry > max_risk_pct:
            continue
        target = entry + direction * target_r * risk
        trade = simulate_trade_detail(day, direction, entry_time, "15:14", stop, target)
        rows.append({
            "Date": date, "Direction": direction, "SignalTime": str(day.loc[signal_idx, "Time"]),
            "Opening15Return": row["r15"], "Opening15RVOL": row["opening15_rvol20"],
            "Gap": row["gap"], "NiftyDayReturn": row.get("nifty_daily_return", np.nan), **trade,
        })
    return pd.DataFrame(rows)


def discover_orb_rule(daily: pd.DataFrame, minutes: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | str | bool]]:
    train = daily[daily.index <= TRAIN_END]
    rvol_levels = {"none": 0.0, "median": float(train["opening15_rvol20"].median())}
    rows = []
    for latest in ("10:00", "11:30"):
        for stop_mode in ("midpoint", "opposite_boundary"):
            for target_r in (1.0, 1.5):
                for rvol_name, cutoff in rvol_levels.items():
                    for position_min in (0.70,):
                        for gap_alignment in (False, True):
                            trades = evaluate_orb_rule(daily, minutes, latest, stop_mode, target_r, cutoff,
                                                       position_min, gap_alignment, end=TRAIN_END)
                            rows.append({"latest_signal": latest, "stop_mode": stop_mode, "target_r": target_r,
                                         "rvol_filter": rvol_name, "rvol_cutoff": cutoff,
                                         "position_min": position_min, "gap_alignment": gap_alignment,
                                         **metrics(trades)})
    grid = pd.DataFrame(rows)
    candidates = grid[(grid["Trades"] >= 40) & (grid["Expectancy"] > 0)].copy()
    if candidates.empty:
        candidates = grid[grid["Trades"] >= 30].copy()
    candidates["score"] = candidates["ProfitFactor"].clip(upper=3) * np.sqrt(candidates["Trades"]) * (1 + candidates["Expectancy"] * 100)
    return grid, candidates.sort_values(["score", "ProfitFactor"], ascending=False).iloc[0].to_dict()


def orb_summary(best: dict[str, float | str | bool], daily: pd.DataFrame, minutes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    kwargs = dict(latest_signal=str(best["latest_signal"]), stop_mode=str(best["stop_mode"]),
                  target_r=float(best["target_r"]), rvol_cutoff=float(best["rvol_cutoff"]),
                  position_min=float(best["position_min"]), require_gap_alignment=bool(best["gap_alignment"]))
    train = evaluate_orb_rule(daily, minutes, **kwargs, end=TRAIN_END)
    holdout = evaluate_orb_rule(daily, minutes, **kwargs, start=HOLDOUT_START)
    summary = pd.DataFrame([
        {"Sample": f"Discovery_through_{TRAIN_END.date()}", **metrics(train)},
        {"Sample": f"Holdout_from_{HOLDOUT_START.date()}", **metrics(holdout)},
    ])
    replay = pd.concat([holdout.nlargest(3, "NetReturn"), holdout.nsmallest(3, "NetReturn")]).drop_duplicates("Date")
    return summary, replay.sort_values("Date")


def chart_activity(profile: pd.DataFrame, symbol: str = "CGPOWER") -> None:
    x = np.arange(len(profile))
    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax1.plot(x, profile["mean_abs_return"] * 100, color="#195B8A", label="Mean absolute 1m return")
    ax1.set_ylabel("Mean absolute 1m return (%)", color="#195B8A")
    ax2 = ax1.twinx()
    ax2.plot(x, profile["mean_volume_share"] * 100, color="#F28E2B", label="Mean volume share")
    ax2.set_ylabel("Share of daily volume per minute (%)", color="#F28E2B")
    ticks = [0, 45, 105, 165, 225, 285, 345, len(profile) - 1]
    ax1.set_xticks(ticks, [profile.index[i] for i in ticks])
    ax1.axvspan(0, 29, color="#4C78A8", alpha=0.08)
    ax1.axvspan(len(profile) - 60, len(profile) - 1, color="#F28E2B", alpha=0.08)
    ax1.set_title(f"{symbol} intraday activity: the open dominates volatility, the close regains volume", loc="left", weight="bold")
    ax1.grid(axis="y", alpha=0.18)
    fig.tight_layout()
    fig.savefig(CHARTS / "01_intraday_activity_curve.png", dpi=180)
    plt.close(fig)


def chart_conditionals(opening: pd.DataFrame, closing: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    axes[0].bar(opening.index.astype(str), opening["ContinueRate"] * 100, color="#4C78A8")
    axes[0].axhline(50, color="#6B7280", linewidth=0.8)
    axes[0].set_title("Does the first 15-minute direction continue?", loc="left", weight="bold")
    axes[0].set_ylabel("Same-direction rest-of-day rate (%)")
    axes[0].tick_params(axis="x", rotation=25)
    axes[1].bar(closing.index.astype(str), closing["FinalHourContinueRate"] * 100, color="#F28E2B")
    axes[1].axhline(50, color="#6B7280", linewidth=0.8)
    axes[1].set_title("Does the move through 14:29 continue?", loc="left", weight="bold")
    axes[1].set_ylabel("Same-direction final-hour rate (%)")
    axes[1].tick_params(axis="x", rotation=25)
    for ax in axes:
        ax.grid(axis="y", alpha=0.18)
    fig.tight_layout()
    fig.savefig(CHARTS / "02_open_close_continuation.png", dpi=180)
    plt.close(fig)


def chart_breakouts(breakouts: pd.DataFrame) -> None:
    display = breakouts.copy()
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(display))
    ax.bar(x - 0.18, display["CloseAboveOR"] * 100, width=0.36, label="Closes above opening range", color="#4C78A8")
    ax.bar(x + 0.18, display["CloseBelowOR"] * 100, width=0.36, label="Closes below opening range", color="#F28E2B")
    ax.set_xticks(x, display.index)
    ax.set_ylabel("Sessions (%)")
    ax.set_title("Opening-range breaks: one-sided acceptance versus two-sided noise", loc="left", weight="bold")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.18)
    fig.tight_layout()
    fig.savefig(CHARTS / "03_opening_range_outcomes.png", dpi=180)
    plt.close(fig)


def write_report(daily: pd.DataFrame, profile: pd.DataFrame, opening: pd.DataFrame, breakouts: pd.DataFrame,
                 closing: pd.DataFrame, rule: Rule, cutoff: float, strategy: pd.DataFrame,
                 sweep_best: dict[str, float | str], sweep_results: pd.DataFrame,
                 replay: pd.DataFrame, orb_best: dict[str, float | str | bool],
                 orb_results: pd.DataFrame, orb_replay: pd.DataFrame) -> None:
    train_days = (daily.index <= TRAIN_END).sum()
    holdout_days = (daily.index >= HOLDOUT_START).sum()
    first30_vol = daily["opening30_volume_share"].median() * 100
    final30_vol = daily["closing30_volume_share"].median() * 100
    open_abs = daily["r30"].abs().median() * 100
    close_abs = daily["r_close30"].abs().median() * 100
    both = (daily["break_type"].isin(["high_then_low", "low_then_high"])).mean() * 100
    event_text = f"""# CGPOWER opening and closing microstructure

Coverage: {daily.index.min().date()} to {daily.index.max().date()}, {len(daily):,} complete sessions. Discovery sample: {train_days} sessions through 2024. Holdout: {holdout_days} sessions from 2025 onward. Costs: 10 bps round trip.

## Session anatomy

- The median first 30 minutes contain **{first30_vol:.1f}% of daily volume** and move **{open_abs:.2f}%** in absolute terms.
- The median final 30 minutes contain **{final30_vol:.1f}% of daily volume** and move **{close_abs:.2f}%** in absolute terms.
- Both sides of the first 15-minute range are broken on **{both:.1f}%** of sessions. Those sessions are two-sided discovery/noise, not clean trend days.
- The first 15 minutes are useful only when normalized by the prior 20-day ATR, confirmed by close location inside the opening range, and supported by opening volume.
- The final hour is more often a liquidity/positioning phase than a fresh-information phase. Strong moves into 14:29 do not automatically continue.

## Frozen opening-drive rule

- At 09:30, trade in the first-15-minute direction only when `abs(first15 return) >= {rule.strength_atr:.2f} x prior ATR20`.
- The 09:29 close must finish in the directional top/bottom {100 * (1 - rule.position_min):.0f}% of the opening range.
- First-15-minute volume must exceed **{cutoff:.2f}x** the prior 20-session median for that same window (the training {rule.volume_quantile:.0%} quantile).
- Stop at the opposite opening-range boundary; reject risk above 1.2%; target {rule.target_r:.1f}R; otherwise exit 15:14.

{strategy.to_string(index=False, formatters={"WinRate": lambda x: f"{x:.1%}", "ProfitFactor": lambda x: f"{x:.2f}", "Expectancy": lambda x: f"{x:.3%}", "MaxDrawdown": lambda x: f"{x:.2%}"})}

This is a deliberately frozen holdout check, not a production recommendation. If holdout performance is weak, the correct conclusion is that opening structure explains price action but does not yet provide a stable standalone edge.

## Opening-range liquidity sweep test

The data's stronger structural clue is sequence, not raw first-15-minute direction: a low sweep followed by a high break tends to finish bullish, while a high sweep followed by a low break tends to finish bearish. The training-selected mechanical test waits for the second boundary to break, enters on the next minute, uses a **{sweep_best['stop_mode']}** stop, a **{float(sweep_best['target_r']):.1f}R** target, and accepts signals through **{sweep_best['latest_signal']}**. Its opening RVOL filter is `{sweep_best['rvol_filter']}`.

{sweep_results.to_string(index=False, formatters={"WinRate": lambda x: f"{x:.1%}", "ProfitFactor": lambda x: f"{x:.2f}", "Expectancy": lambda x: f"{x:.3%}", "MaxDrawdown": lambda x: f"{x:.2%}"})}

## Mental paper-trade replay set

These holdout examples were selected only after the rule was frozen: the three best and three worst outcomes. Replaying both tails prevents a persuasive chart from hiding how the setup actually fails.

{replay[["Date", "Direction", "BreakType", "SignalTime", "EntryTime", "EntryPrice", "Stop", "Target", "ExitTime", "ExitPrice", "ExitReason", "NetReturn"]].to_string(index=False, formatters={"NetReturn": lambda x: f"{x:.3%}"})}

## First opening-range break test

The earlier entry trades the first opening-range break by **{orb_best['latest_signal']}**, only when the 09:29 close is in the directional top/bottom **{100 * (1 - float(orb_best['position_min'])):.0f}%**. It uses a **{orb_best['stop_mode']}** stop, **{float(orb_best['target_r']):.1f}R** target, RVOL filter `{orb_best['rvol_filter']}`, and gap-alignment requirement `{orb_best['gap_alignment']}`.

{orb_results.to_string(index=False, formatters={"WinRate": lambda x: f"{x:.1%}", "ProfitFactor": lambda x: f"{x:.2f}", "Expectancy": lambda x: f"{x:.3%}", "MaxDrawdown": lambda x: f"{x:.2%}"})}

Its holdout replay tails are stored separately so the entry can be visually audited without choosing only attractive examples.

## Evidence files

- `minute_of_day_profile.csv`
- `opening_strength_outcomes.csv`
- `opening_range_outcomes.csv`
- `closing_strength_outcomes.csv`
- `opening_rule_grid_train.csv`
- `opening_rule_train_holdout.csv`
- `liquidity_sweep_grid_train.csv`
- `liquidity_sweep_train_holdout.csv`
- `mental_papertrade_replays.csv`
- `opening_range_breakout_grid_train.csv`
- `opening_range_breakout_train_holdout.csv`
- `opening_range_breakout_replays.csv`
- `session_charts/`
"""
    (OUT / "session_microstructure_findings.md").write_text(event_text, encoding="utf-8")


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    minutes = valid_sessions(load_minutes(CG_PATH))
    nifty_minutes = load_minutes(NIFTY_PATH)
    daily = add_nifty_features(build_daily_features(minutes), nifty_minutes)
    profile = minute_profile(minutes)
    opening, breakouts, closing = conditional_tables(daily)
    grid, rule, cutoff = discover_opening_rule(daily, minutes)
    strategy = strategy_summary(rule, cutoff, daily, minutes)
    sweep_grid, sweep_best = discover_sweep_rule(daily, minutes)
    sweep_results, replay = sweep_summary(sweep_best, daily, minutes)
    orb_grid, orb_best = discover_orb_rule(daily, minutes)
    orb_results, orb_replay = orb_summary(orb_best, daily, minutes)

    profile.to_csv(OUT / "minute_of_day_profile.csv")
    opening.to_csv(OUT / "opening_strength_outcomes.csv")
    breakouts.to_csv(OUT / "opening_range_outcomes.csv")
    closing.to_csv(OUT / "closing_strength_outcomes.csv")
    grid.to_csv(OUT / "opening_rule_grid_train.csv", index=False)
    strategy.to_csv(OUT / "opening_rule_train_holdout.csv", index=False)
    sweep_grid.to_csv(OUT / "liquidity_sweep_grid_train.csv", index=False)
    sweep_results.to_csv(OUT / "liquidity_sweep_train_holdout.csv", index=False)
    replay.to_csv(OUT / "mental_papertrade_replays.csv", index=False)
    orb_grid.to_csv(OUT / "opening_range_breakout_grid_train.csv", index=False)
    orb_results.to_csv(OUT / "opening_range_breakout_train_holdout.csv", index=False)
    orb_replay.to_csv(OUT / "opening_range_breakout_replays.csv", index=False)
    daily.to_csv(OUT / "session_daily_features.csv")

    chart_activity(profile)
    chart_conditionals(opening, closing)
    chart_breakouts(breakouts)
    write_report(daily, profile, opening, breakouts, closing, rule, cutoff, strategy,
                 sweep_best, sweep_results, replay, orb_best, orb_results, orb_replay)
    print(f"Session study complete: {len(daily)} sessions, rule={rule}, volume_cutoff={cutoff:.4f}")
    print(strategy.to_string(index=False))
    print(f"Liquidity sweep rule: {sweep_best}")
    print(sweep_results.to_string(index=False))
    print(f"Opening-range breakout rule: {orb_best}")
    print(orb_results.to_string(index=False))


if __name__ == "__main__":
    main()
