from __future__ import annotations

import json
import math
import textwrap
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "Data"
OUTPUT_DIR = ROOT / "Research" / "SBIN_Personality"
CHART_DIR = OUTPUT_DIR / "charts"
SYMBOL = "SBIN"

RESEARCH_MONTHS = 12
TEST_MONTHS = 3
MIN_TRAIN_TRADES = 22
MIN_TEST_TRADES = 8
TARGET_WIN_RATE = 55.0
TARGET_PROFIT_FACTOR = 1.5
MIN_RR = 1.5
ENTRY_START = time(9, 30)
LAST_ENTRY = time(14, 15)
FORCED_EXIT = time(15, 15)
TICK_BUFFER = 0.05
CONTINUATION_THRESHOLD = 0.0002
GAP_THRESHOLD = 0.002


@dataclass(frozen=True)
class StrategyVariant:
    setup: str
    boundary: str
    entry_end: str
    rr: float
    stop_atr: float
    vol_mult: float
    vwap_filter: bool
    ema_filter: bool
    macro_filter: str
    atr_band: float = 1.2

    @property
    def label(self) -> str:
        return (
            f"{self.setup}|{self.boundary}|end={self.entry_end}|rr={self.rr}|"
            f"atr={self.stop_atr}|vol={self.vol_mult}|vwap={int(self.vwap_filter)}|"
            f"ema={int(self.ema_filter)}|macro={self.macro_filter}|band={self.atr_band}"
        )


@dataclass
class Trade:
    variant: str
    set_name: str
    date: str
    setup: str
    direction: str
    entry_time: str
    entry_price: float
    stop_price: float
    target_price: float
    exit_time: str
    exit_price: float
    outcome: str
    r_multiple: float
    pnl_per_share: float
    risk_per_share: float
    minutes_held: float
    signal_time: str
    boundary: str
    rr: float
    macro_alignment: str


def load_candles(symbol: str, timeframe: str) -> pd.DataFrame:
    path = DATA_ROOT / symbol / f"{symbol}_{timeframe}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing candle file: {path}")

    df = pd.read_csv(path, parse_dates=["Datetime"])
    columns = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    df = df[columns].copy()
    for column in columns[1:]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=columns).drop_duplicates(subset=["Datetime"])
    df = df.sort_values("Datetime").reset_index(drop=True)
    df["Date"] = df["Datetime"].dt.date
    df["Time"] = df["Datetime"].dt.time
    return df


def add_true_range(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["Close"].shift(1)
    tr = pd.concat(
        [
            out["High"] - out["Low"],
            (out["High"] - prev_close).abs(),
            (out["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["TR"] = tr
    out["ATR"] = tr.rolling(window, min_periods=1).mean()
    out["TR_bps"] = out["TR"] / out["Close"] * 10000
    out["Body_bps"] = (out["Close"] - out["Open"]).abs() / out["Open"] * 10000
    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = add_true_range(df)
    typical = (out["High"] + out["Low"] + out["Close"]) / 3
    pv = typical * out["Volume"]
    out["VWAP"] = pv.groupby(out["Date"]).cumsum() / out["Volume"].groupby(out["Date"]).cumsum()
    for span in (9, 20, 21, 50):
        out[f"EMA{span}"] = out["Close"].ewm(span=span, adjust=False, min_periods=span).mean()
    out["VolMA20"] = out.groupby("Date")["Volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )
    out["RollingHigh12"] = out.groupby("Date")["High"].transform(
        lambda s: s.rolling(12, min_periods=6).max().shift(1)
    )
    out["RollingLow12"] = out.groupby("Date")["Low"].transform(
        lambda s: s.rolling(12, min_periods=6).min().shift(1)
    )
    return out


def session_bucket(ts: time) -> str:
    if ts < time(10, 0):
        return "09:15-10:00"
    if ts < time(11, 0):
        return "10:00-11:00"
    if ts < time(12, 0):
        return "11:00-12:00"
    if ts < time(13, 0):
        return "12:00-13:00"
    if ts < time(14, 0):
        return "13:00-14:00"
    if ts < time(15, 0):
        return "14:00-15:00"
    return "15:00-15:30"


def daily_levels(df5: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df5.groupby("Date")
        .agg(
            DayOpen=("Open", "first"),
            DayHigh=("High", "max"),
            DayLow=("Low", "min"),
            DayClose=("Close", "last"),
            DayVolume=("Volume", "sum"),
        )
        .reset_index()
    )
    daily["PrevHigh"] = daily["DayHigh"].shift(1)
    daily["PrevLow"] = daily["DayLow"].shift(1)
    daily["PrevClose"] = daily["DayClose"].shift(1)
    return daily


def opening_range(df: pd.DataFrame, end_time: time, prefix: str) -> pd.DataFrame:
    mask = (df["Time"] >= time(9, 15)) & (df["Time"] < end_time)
    out = (
        df.loc[mask]
        .groupby("Date")
        .agg(**{f"{prefix}High": ("High", "max"), f"{prefix}Low": ("Low", "min")})
        .reset_index()
    )
    out[f"{prefix}Range"] = out[f"{prefix}High"] - out[f"{prefix}Low"]
    return out


def macro_trends(df1d: pd.DataFrame, df1w: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = df1d.copy()
    weekly = df1w.copy()
    for frame in (daily, weekly):
        frame["EMA20"] = frame["Close"].ewm(span=20, adjust=False, min_periods=10).mean()
        frame["EMA50"] = frame["Close"].ewm(span=50, adjust=False, min_periods=15).mean()
        frame["Trend"] = np.where(
            frame["EMA20"] > frame["EMA50"], 1, np.where(frame["EMA20"] < frame["EMA50"], -1, 0)
        )
        frame["AvailableAt"] = frame["Datetime"] + pd.Timedelta(days=1)
    return (
        daily[["AvailableAt", "Trend"]]
        .rename(columns={"Trend": "DailyTrend"})
        .sort_values("AvailableAt"),
        weekly[["AvailableAt", "Trend"]]
        .rename(columns={"Trend": "WeeklyTrend"})
        .sort_values("AvailableAt"),
    )


def attach_macro(df5: pd.DataFrame, df1d: pd.DataFrame, df1w: pd.DataFrame) -> pd.DataFrame:
    daily_trend, weekly_trend = macro_trends(df1d, df1w)
    out = df5.sort_values("Datetime").copy()
    out = pd.merge_asof(
        out, daily_trend, left_on="Datetime", right_on="AvailableAt", direction="backward"
    )
    out = out.drop(columns=["AvailableAt"])
    out = pd.merge_asof(
        out, weekly_trend, left_on="Datetime", right_on="AvailableAt", direction="backward"
    )
    out = out.drop(columns=["AvailableAt"])
    out["DailyTrend"] = out["DailyTrend"].fillna(0).astype(int)
    out["WeeklyTrend"] = out["WeeklyTrend"].fillna(0).astype(int)
    return out


def last_complete_session_date(df: pd.DataFrame) -> date:
    sessions = (
        df.groupby("Date")
        .agg(first_time=("Time", "min"), last_time=("Time", "max"), bars=("Datetime", "size"))
        .reset_index()
    )
    complete = sessions[
        (sessions["first_time"] <= time(9, 15))
        & (sessions["last_time"] >= time(15, 25))
        & (sessions["bars"] >= 60)
    ]
    if complete.empty:
        raise ValueError("No complete trading sessions found in 5MIN data.")
    return max(complete["Date"])


def research_window(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    end = pd.Timestamp(last_complete_session_date(df))
    start = end - pd.DateOffset(months=RESEARCH_MONTHS)
    test_start = end - pd.DateOffset(months=TEST_MONTHS)
    return pd.Timestamp(start), pd.Timestamp(test_start), pd.Timestamp(end)


def filter_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return df[(df["Datetime"] >= start) & (df["Datetime"] < end + pd.Timedelta(days=1))].copy()


def time_of_day_profile(df1: pd.DataFrame, df5: pd.DataFrame) -> pd.DataFrame:
    one = df1.copy()
    five = df5.copy()
    one["Bucket"] = one["Time"].map(session_bucket)
    five["Bucket"] = five["Time"].map(session_bucket)
    p = (
        one.groupby("Bucket")
        .agg(
            one_min_bars=("Datetime", "size"),
            avg_1m_tr_bps=("TR_bps", "mean"),
            median_1m_tr_bps=("TR_bps", "median"),
            avg_1m_volume=("Volume", "mean"),
            total_volume=("Volume", "sum"),
        )
        .reset_index()
    )
    p5 = (
        five.groupby("Bucket")
        .agg(
            avg_5m_tr_bps=("TR_bps", "mean"),
            median_5m_tr_bps=("TR_bps", "median"),
            avg_5m_volume=("Volume", "mean"),
        )
        .reset_index()
    )
    out = p.merge(p5, on="Bucket", how="left")
    out["velocity_score"] = (
        out["avg_1m_tr_bps"].rank(pct=True) * 0.5
        + out["avg_1m_volume"].rank(pct=True) * 0.3
        + out["avg_5m_tr_bps"].rank(pct=True) * 0.2
    )
    out["personality"] = np.where(
        out["velocity_score"] >= out["velocity_score"].quantile(0.7),
        "high-velocity",
        np.where(
            out["velocity_score"] <= out["velocity_score"].quantile(0.3), "dead/noisy", "normal"
        ),
    )
    order = [
        "09:15-10:00",
        "10:00-11:00",
        "11:00-12:00",
        "12:00-13:00",
        "13:00-14:00",
        "14:00-15:00",
        "15:00-15:30",
    ]
    out["Bucket"] = pd.Categorical(out["Bucket"], categories=order, ordered=True)
    return out.sort_values("Bucket").reset_index(drop=True)


def noise_signal_profile(df1: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df1.sort_values(["Date", "Datetime"]).copy()
    df["Direction"] = np.sign(df["Close"] - df["Open"])
    df["Next3Close"] = df.groupby("Date")["Close"].shift(-3)
    df["Next3Ret"] = df["Next3Close"] / df["Close"] - 1
    df["MoveClass"] = "noise"
    eligible = (df["Direction"] != 0) & df["Next3Close"].notna()
    signed_follow = df["Direction"] * df["Next3Ret"]
    df.loc[eligible & (signed_follow > CONTINUATION_THRESHOLD), "MoveClass"] = "continuation"
    df.loc[eligible & (signed_follow < -CONTINUATION_THRESHOLD), "MoveClass"] = "mean_reversion"
    df = df[eligible].copy()
    df["Bucket"] = df["Time"].map(session_bucket)
    total = len(df)
    overall = (
        df["MoveClass"]
        .value_counts(normalize=True)
        .mul(100)
        .rename_axis("class")
        .reset_index(name="percent")
    )
    overall["bars"] = df["MoveClass"].value_counts().reindex(overall["class"]).to_numpy()
    counts = df.groupby(["Bucket", "MoveClass"]).size().reset_index(name="bars")
    bucket_totals = df.groupby("Bucket").size().rename("eligible_bars").reset_index()
    by_bucket = counts.merge(bucket_totals, on="Bucket", how="left")
    by_bucket["percent"] = by_bucket["bars"] / by_bucket["eligible_bars"] * 100
    by_bucket["total_eligible_bars"] = total
    return overall, by_bucket


def opening_range_stats(df1: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for current_date, day in df1.groupby("Date", sort=True):
        first_15 = day[(day["Time"] >= time(9, 15)) & (day["Time"] < time(9, 30))]
        rest = day[(day["Time"] >= time(9, 30)) & (day["Time"] <= time(15, 29))]
        if first_15.empty or rest.empty:
            continue
        high = float(first_15["High"].max())
        low = float(first_15["Low"].min())
        or_range = max(high - low, 0.01)
        high_breaks = rest[rest["High"] > high]
        low_breaks = rest[rest["Low"] < low]
        high_broken = not high_breaks.empty
        low_broken = not low_breaks.empty
        first_side = "none"
        first_time = ""
        true_breakout = False
        fake_breakout = False
        if high_broken or low_broken:
            high_time = (
                pd.Timestamp(high_breaks.iloc[0]["Datetime"]) if high_broken else pd.Timestamp.max
            )
            low_time = (
                pd.Timestamp(low_breaks.iloc[0]["Datetime"]) if low_broken else pd.Timestamp.max
            )
            if high_time < low_time:
                first_side = "up"
                first_time = str(high_time)
                after = rest[rest["Datetime"] >= high_time]
                mfe = after["High"].max() - high
                true_breakout = mfe >= 0.75 * or_range and float(day.iloc[-1]["Close"]) > high
                fake_breakout = (not true_breakout) or (after["Low"].min() < low)
            else:
                first_side = "down"
                first_time = str(low_time)
                after = rest[rest["Datetime"] >= low_time]
                mfe = low - after["Low"].min()
                true_breakout = mfe >= 0.75 * or_range and float(day.iloc[-1]["Close"]) < low
                fake_breakout = (not true_breakout) or (after["High"].max() > high)
        rows.append(
            {
                "date": str(current_date),
                "or_high": high,
                "or_low": low,
                "or_range": or_range,
                "high_broken": high_broken,
                "low_broken": low_broken,
                "both_sides_broken": high_broken and low_broken,
                "first_break_side": first_side,
                "first_break_time": first_time,
                "true_breakout": true_breakout,
                "fake_breakout": fake_breakout,
            }
        )
    daily = pd.DataFrame(rows)
    summary = pd.DataFrame(
        [
            {"metric": "days", "value": len(daily)},
            {"metric": "or_high_broken_pct", "value": daily["high_broken"].mean() * 100},
            {"metric": "or_low_broken_pct", "value": daily["low_broken"].mean() * 100},
            {
                "metric": "either_side_broken_pct",
                "value": (daily["high_broken"] | daily["low_broken"]).mean() * 100,
            },
            {"metric": "both_sides_broken_pct", "value": daily["both_sides_broken"].mean() * 100},
            {
                "metric": "true_breakout_after_first_break_pct",
                "value": daily.loc[daily["first_break_side"] != "none", "true_breakout"].mean()
                * 100,
            },
            {
                "metric": "fake_breakout_after_first_break_pct",
                "value": daily.loc[daily["first_break_side"] != "none", "fake_breakout"].mean()
                * 100,
            },
        ]
    )
    return daily, summary


def gap_resolution_stats(
    df1: pd.DataFrame, levels: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    first_rows = df1.groupby("Date").first().reset_index()[["Date", "Datetime", "Open"]]
    merged = first_rows.merge(levels[["Date", "PrevClose"]], on="Date", how="left")
    for _, row in merged.dropna(subset=["PrevClose"]).iterrows():
        current_date = row["Date"]
        day = df1[df1["Date"] == current_date]
        first_60 = day[(day["Time"] >= time(9, 15)) & (day["Time"] < time(10, 15))]
        if first_60.empty:
            continue
        gap_pct = float(row["Open"] / row["PrevClose"] - 1)
        if abs(gap_pct) < GAP_THRESHOLD:
            continue
        direction = "gap_up" if gap_pct > 0 else "gap_down"
        filled = (
            bool(first_60["Low"].le(row["PrevClose"]).any())
            if gap_pct > 0
            else bool(first_60["High"].ge(row["PrevClose"]).any())
        )
        rows.append(
            {
                "date": str(current_date),
                "open": float(row["Open"]),
                "prev_close": float(row["PrevClose"]),
                "gap_pct": gap_pct * 100,
                "direction": direction,
                "filled_first_60m": filled,
            }
        )
    detail = pd.DataFrame(rows)
    if detail.empty:
        summary = pd.DataFrame(columns=["direction", "gaps", "fill_rate_pct", "avg_gap_pct"])
    else:
        summary = (
            detail.groupby("direction")
            .agg(
                gaps=("date", "size"),
                fill_rate_pct=("filled_first_60m", lambda s: s.mean() * 100),
                avg_gap_pct=("gap_pct", "mean"),
            )
            .reset_index()
        )
    return detail, summary


def simulate_trade(
    df1_day: pd.DataFrame,
    entry_time: pd.Timestamp,
    direction: int,
    entry_price: float,
    stop: float,
    target: float,
    risk: float,
    forced_exit_time: time = FORCED_EXIT,
) -> dict | None:
    end_ts = pd.Timestamp.combine(entry_time.date(), forced_exit_time)
    path = df1_day[(df1_day["Datetime"] >= entry_time) & (df1_day["Datetime"] <= end_ts)]
    if path.empty:
        return None
    exit_ts = pd.Timestamp(path.iloc[-1]["Datetime"])
    exit_price = float(path.iloc[-1]["Close"])
    outcome = "time_exit"
    for _, bar in path.iterrows():
        ts = pd.Timestamp(bar["Datetime"])
        if direction == 1:
            stop_hit = bar["Low"] <= stop
            target_hit = bar["High"] >= target
        else:
            stop_hit = bar["High"] >= stop
            target_hit = bar["Low"] <= target
        if stop_hit and target_hit:
            exit_ts, exit_price, outcome = ts, stop, "stop"
            break
        if stop_hit:
            exit_ts, exit_price, outcome = ts, stop, "stop"
            break
        if target_hit:
            exit_ts, exit_price, outcome = ts, target, "target"
            break
    pnl = (exit_price - entry_price) * direction
    return {
        "exit_time": exit_ts,
        "exit_price": float(exit_price),
        "outcome": outcome,
        "pnl_per_share": float(pnl),
        "r_multiple": float(pnl / risk),
        "minutes_held": float((exit_ts - entry_time).total_seconds() / 60),
    }


def next_5m_entry(
    day5: pd.DataFrame, signal_time: pd.Timestamp
) -> tuple[pd.Timestamp, float] | None:
    future = day5[day5["Datetime"] > signal_time]
    if future.empty:
        return None
    row = future.iloc[0]
    if row["Time"] > LAST_ENTRY:
        return None
    return pd.Timestamp(row["Datetime"]), float(row["Open"])


def macro_allows(row: pd.Series, direction: int, mode: str) -> bool:
    if mode == "none":
        return True
    if mode == "daily":
        return int(row["DailyTrend"]) == direction
    if mode == "daily_weekly":
        return int(row["DailyTrend"]) == direction and int(row["WeeklyTrend"]) == direction
    if mode == "not_both_against":
        return not (int(row["DailyTrend"]) == -direction and int(row["WeeklyTrend"]) == -direction)
    raise ValueError(f"Unknown macro filter: {mode}")


def macro_alignment(row: pd.Series, direction: int) -> str:
    daily = int(row["DailyTrend"])
    weekly = int(row["WeeklyTrend"])
    if daily == direction and weekly == direction:
        return "aligned_1d_1w"
    if daily == -direction and weekly == -direction:
        return "opposed_1d_1w"
    return "mixed_or_neutral"


def base_filters(row: pd.Series, direction: int, variant: StrategyVariant) -> bool:
    if row["Time"] < ENTRY_START or row["Time"] > time.fromisoformat(variant.entry_end):
        return False
    if pd.notna(row["VolMA20"]) and row["Volume"] < row["VolMA20"] * variant.vol_mult:
        return False
    if variant.vwap_filter:
        if direction == 1 and not row["Close"] > row["VWAP"]:
            return False
        if direction == -1 and not row["Close"] < row["VWAP"]:
            return False
    if variant.ema_filter:
        if direction == 1 and not (row["EMA9"] > row["EMA21"] > row["EMA50"]):
            return False
        if direction == -1 and not (row["EMA9"] < row["EMA21"] < row["EMA50"]):
            return False
    if not macro_allows(row, direction, variant.macro_filter):
        return False
    return True


def boundary_values(row: pd.Series, boundary: str) -> tuple[float, float, float] | None:
    if boundary == "or15":
        high, low, rng = row["OR15High"], row["OR15Low"], row["OR15Range"]
    elif boundary == "or30":
        high, low, rng = row["OR30High"], row["OR30Low"], row["OR30Range"]
    elif boundary == "prev_day":
        high, low, rng = row["PrevHigh"], row["PrevLow"], row["PrevHigh"] - row["PrevLow"]
    else:
        raise ValueError(f"Unknown boundary: {boundary}")
    if pd.isna(high) or pd.isna(low) or high <= low:
        return None
    return float(high), float(low), max(float(rng), 0.01)


def signal_direction(
    row: pd.Series, previous_row: pd.Series | None, variant: StrategyVariant
) -> int | None:
    bounds = boundary_values(row, variant.boundary)
    if bounds is None:
        return None
    high, low, rng = bounds
    buffer = max(0.05, 0.02 * rng)

    if variant.setup == "breakout_close":
        if row["Close"] > high + buffer:
            return 1
        if row["Close"] < low - buffer:
            return -1
    elif variant.setup == "breakout_retest":
        if row["Close"] > high and row["Low"] <= high + buffer:
            return 1
        if row["Close"] < low and row["High"] >= low - buffer:
            return -1
    elif variant.setup == "fakeout_reversion":
        if row["High"] > high + buffer and row["Close"] < high:
            return -1
        if row["Low"] < low - buffer and row["Close"] > low:
            return 1
    elif variant.setup == "vwap_pullback":
        if row["Low"] <= row["VWAP"] and row["Close"] > row["EMA9"] and row["EMA9"] > row["EMA21"]:
            return 1
        if row["High"] >= row["VWAP"] and row["Close"] < row["EMA9"] and row["EMA9"] < row["EMA21"]:
            return -1
    elif variant.setup == "vwap_atr_reversion":
        upper = row["VWAP"] + variant.atr_band * row["ATR"]
        lower = row["VWAP"] - variant.atr_band * row["ATR"]
        if row["High"] > upper and row["Close"] < upper:
            return -1
        if row["Low"] < lower and row["Close"] > lower:
            return 1
    elif variant.setup == "ema_structure_break":
        if (
            pd.notna(row["RollingHigh12"])
            and row["Close"] > row["RollingHigh12"]
            and row["EMA20"] > row["EMA50"]
        ):
            return 1
        if (
            pd.notna(row["RollingLow12"])
            and row["Close"] < row["RollingLow12"]
            and row["EMA20"] < row["EMA50"]
        ):
            return -1
    else:
        raise ValueError(f"Unknown setup: {variant.setup}")
    return None


def build_stop_target(
    row: pd.Series, direction: int, entry_price: float, variant: StrategyVariant
) -> tuple[float, float, float] | None:
    atr_risk = max(float(row["ATR"]) * variant.stop_atr, 0.20)
    recent_risk = (
        abs(entry_price - (float(row["Low"]) if direction == 1 else float(row["High"])))
        + TICK_BUFFER
    )
    risk = max(atr_risk, recent_risk)
    if risk <= 0:
        return None
    stop = entry_price - direction * risk
    target = entry_price + direction * variant.rr * risk
    return float(stop), float(target), float(risk)


def generate_trades(
    df1: pd.DataFrame,
    df5: pd.DataFrame,
    variant: StrategyVariant,
    start: pd.Timestamp,
    test_start: pd.Timestamp,
    end: pd.Timestamp,
    df1_by_day: dict[date, pd.DataFrame] | None = None,
) -> list[Trade]:
    trades: list[Trade] = []
    if df1_by_day is None:
        df1_by_day = {d: part.reset_index(drop=True) for d, part in df1.groupby("Date")}
    for current_date, day5_raw in df5.groupby("Date", sort=True):
        day_ts = pd.Timestamp(current_date)
        if day_ts < start or day_ts > end:
            continue
        day1 = df1_by_day.get(current_date)
        if day1 is None or day1.empty:
            continue
        day5 = day5_raw.reset_index(drop=True)
        previous_row = None
        for _, row in day5.iterrows():
            row_time = row["Time"]
            if row_time < ENTRY_START or row_time > time.fromisoformat(variant.entry_end):
                previous_row = row
                continue
            direction = signal_direction(row, previous_row, variant)
            previous_row = row
            if direction is None:
                continue
            if not base_filters(row, direction, variant):
                continue
            entry = next_5m_entry(day5, pd.Timestamp(row["Datetime"]))
            if entry is None:
                continue
            entry_time, entry_price = entry
            risk_plan = build_stop_target(row, direction, entry_price, variant)
            if risk_plan is None:
                continue
            stop, target, risk = risk_plan
            result = simulate_trade(day1, entry_time, direction, entry_price, stop, target, risk)
            if result is None:
                continue
            set_name = "test" if pd.Timestamp(current_date) >= test_start else "train"
            trades.append(
                Trade(
                    variant=variant.label,
                    set_name=set_name,
                    date=str(current_date),
                    setup=variant.setup,
                    direction="LONG" if direction == 1 else "SHORT",
                    entry_time=str(entry_time),
                    entry_price=entry_price,
                    stop_price=stop,
                    target_price=target,
                    exit_time=str(result["exit_time"]),
                    exit_price=float(result["exit_price"]),
                    outcome=str(result["outcome"]),
                    r_multiple=float(result["r_multiple"]),
                    pnl_per_share=float(result["pnl_per_share"]),
                    risk_per_share=risk,
                    minutes_held=float(result["minutes_held"]),
                    signal_time=str(row["Datetime"]),
                    boundary=variant.boundary,
                    rr=variant.rr,
                    macro_alignment=macro_alignment(row, direction),
                )
            )
            break
    return trades


def candidate_variants() -> list[StrategyVariant]:
    variants: list[StrategyVariant] = []
    trend_filters = [
        (False, False, "none"),
        (True, True, "not_both_against"),
    ]

    for setup in ("breakout_close", "breakout_retest"):
        for boundary in ("or15", "or30"):
            for entry_end in ("10:30", "11:30"):
                for rr in (1.5, 2.0):
                    for stop_atr in (1.0,):
                        for vol_mult in (0.8, 1.2):
                            for vwap_filter, ema_filter, macro_filter in trend_filters:
                                variants.append(
                                    StrategyVariant(
                                        setup,
                                        boundary,
                                        entry_end,
                                        rr,
                                        stop_atr,
                                        vol_mult,
                                        vwap_filter,
                                        ema_filter,
                                        macro_filter,
                                    )
                                )

    for boundary in ("or15", "or30"):
        for entry_end in ("10:30", "11:30"):
            for rr in (1.5,):
                for stop_atr in (1.0,):
                    for vol_mult in (0.8,):
                        for macro_filter in ("none", "not_both_against"):
                            variants.append(
                                StrategyVariant(
                                    "fakeout_reversion",
                                    boundary,
                                    entry_end,
                                    rr,
                                    stop_atr,
                                    vol_mult,
                                    False,
                                    False,
                                    macro_filter,
                                )
                            )

    for setup in ("vwap_pullback", "ema_structure_break"):
        for entry_end in ("11:30", "14:15"):
            for rr in (1.5, 2.0):
                for stop_atr in (1.0,):
                    for vol_mult in (0.8, 1.2):
                        for macro_filter in ("none", "not_both_against"):
                            if setup == "vwap_pullback":
                                variants.append(
                                    StrategyVariant(
                                        setup,
                                        "or15",
                                        entry_end,
                                        rr,
                                        stop_atr,
                                        vol_mult,
                                        False,
                                        False,
                                        macro_filter,
                                    )
                                )
                            else:
                                for vwap_filter in (False, True):
                                    variants.append(
                                        StrategyVariant(
                                            setup,
                                            "or15",
                                            entry_end,
                                            rr,
                                            stop_atr,
                                            vol_mult,
                                            vwap_filter,
                                            False,
                                            macro_filter,
                                        )
                                    )

    for entry_end in ("10:30", "11:30"):
        for rr in (1.5,):
            for stop_atr in (1.0,):
                for vol_mult in (0.8,):
                    for macro_filter in ("none",):
                        for atr_band in (1.0, 1.4):
                            variants.append(
                                StrategyVariant(
                                    "vwap_atr_reversion",
                                    "or15",
                                    entry_end,
                                    rr,
                                    stop_atr,
                                    vol_mult,
                                    False,
                                    False,
                                    macro_filter,
                                    atr_band,
                                )
                            )
    return variants


def metrics(trades: Iterable[Trade]) -> dict:
    rows = [asdict(t) for t in trades]
    if not rows:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "max_drawdown_r": 0.0,
            "avg_trade_duration_min": 0.0,
            "avg_r": 0.0,
            "gross_profit_r": 0.0,
            "gross_loss_r": 0.0,
        }
    df = pd.DataFrame(rows)
    r = df["r_multiple"].astype(float)
    wins = r > 0
    losses = r < 0
    gross_profit = r[wins].sum()
    gross_loss = -r[losses].sum()
    equity = r.cumsum()
    drawdown = equity - equity.cummax()
    pf = (
        math.inf
        if gross_loss == 0 and gross_profit > 0
        else (gross_profit / gross_loss if gross_loss else 0.0)
    )
    return {
        "trades": len(df),
        "win_rate": float(wins.mean() * 100),
        "profit_factor": float(pf) if math.isfinite(pf) else "inf",
        "expectancy_r": float(r.mean()),
        "max_drawdown_r": float(drawdown.min()),
        "avg_trade_duration_min": float(df["minutes_held"].mean()),
        "avg_r": float(r.mean()),
        "gross_profit_r": float(gross_profit),
        "gross_loss_r": float(gross_loss),
    }


def summarize_variants(all_trades: list[Trade]) -> pd.DataFrame:
    rows = []
    variants = sorted({trade.variant for trade in all_trades})
    for variant in variants:
        for set_name in ("train", "test"):
            subset = [t for t in all_trades if t.variant == variant and t.set_name == set_name]
            row = metrics(subset)
            row.update({"variant": variant, "set_name": set_name})
            first = next((t for t in subset), None)
            if first:
                row.update({"setup": first.setup, "boundary": first.boundary, "rr": first.rr})
            else:
                parts = dict(part.split("=", 1) for part in variant.split("|") if "=" in part)
                row.update(
                    {
                        "setup": variant.split("|")[0],
                        "boundary": variant.split("|")[1],
                        "rr": float(parts.get("rr", MIN_RR)),
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


def select_best(summary: pd.DataFrame) -> str | None:
    train = summary[
        (summary["set_name"] == "train") & (summary["trades"] >= MIN_TRAIN_TRADES)
    ].copy()
    if train.empty:
        train = summary[(summary["set_name"] == "train") & (summary["trades"] > 0)].copy()
    if train.empty:
        return None
    train["passes_targets"] = (
        (train["win_rate"] >= 55)
        & (pd.to_numeric(train["profit_factor"].replace("inf", 999), errors="coerce") >= 1.5)
        & (train["expectancy_r"] > 0)
    )
    train["pf_rank"] = pd.to_numeric(
        train["profit_factor"].replace("inf", 999), errors="coerce"
    ).fillna(0)
    train = train.sort_values(
        ["passes_targets", "pf_rank", "expectancy_r", "win_rate", "trades", "max_drawdown_r"],
        ascending=[False, False, False, False, False, False],
    )
    return str(train.iloc[0]["variant"])


def profit_factor_value(value: object) -> float:
    if value == "inf":
        return 999.0
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])


def row_passes_targets(row: dict | pd.Series, min_trades: int) -> bool:
    return (
        int(row["trades"]) >= min_trades
        and float(row["win_rate"]) >= TARGET_WIN_RATE
        and profit_factor_value(row["profit_factor"]) >= TARGET_PROFIT_FACTOR
        and float(row["expectancy_r"]) > 0
    )


def strategy_validation_status(train: dict, test: dict) -> dict:
    train_pass = row_passes_targets(train, MIN_TRAIN_TRADES)
    test_pass = row_passes_targets(test, MIN_TEST_TRADES)
    if train_pass and test_pass:
        status = "validated"
        message = "Promotable research candidate: both discovery and out-of-sample windows passed the target thresholds."
    elif not train_pass:
        status = "rejected_train_failed"
        message = (
            "Rejected: the best discovery candidate did not meet the minimum training thresholds."
        )
    else:
        status = "rejected_oos_failed"
        message = "Rejected: the discovery candidate failed the untouched out-of-sample validation window."
    return {
        "status": status,
        "train_pass": train_pass,
        "test_pass": test_pass,
        "message": message,
    }


def htf_dominance(
    df1: pd.DataFrame, df5: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    variant = StrategyVariant(
        setup="ema_structure_break",
        boundary="or15",
        entry_end="14:15",
        rr=1.5,
        stop_atr=1.0,
        vol_mult=1.0,
        vwap_filter=False,
        ema_filter=False,
        macro_filter="none",
    )
    df1_by_day = {d: part.reset_index(drop=True) for d, part in df1.groupby("Date")}
    trades = generate_trades(df1, df5, variant, start, end + pd.Timedelta(days=1), end, df1_by_day)
    rows = []
    for alignment, subset in (
        pd.DataFrame([asdict(t) for t in trades]).groupby("macro_alignment") if trades else []
    ):
        r = subset["r_multiple"].astype(float)
        rows.append(
            {
                "macro_alignment": alignment,
                "trend_setup_trades": len(subset),
                "win_rate_pct": (r > 0).mean() * 100,
                "profit_factor": (
                    (r[r > 0].sum() / -r[r < 0].sum())
                    if (r < 0).any()
                    else ("inf" if (r > 0).any() else 0)
                ),
                "expectancy_r": r.mean(),
            }
        )
    return pd.DataFrame(rows)


def save_chart_time_of_day(profile: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt
    import seaborn as sns

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    use_chart_theme(sns, plt)
    fig, ax1 = plt.subplots(figsize=(10, 5.2))
    plot = profile.copy()
    sns.barplot(
        data=plot,
        x="Bucket",
        y="avg_1m_volume",
        ax=ax1,
        color="#A3BEFA",
        edgecolor="#2E4780",
        linewidth=1.0,
    )
    ax1.set_ylabel("Avg 1m volume")
    ax1.set_xlabel("")
    ax1.tick_params(axis="x", labelrotation=35)
    ax2 = ax1.twinx()
    ax2.grid(False)
    ax2.plot(
        plot["Bucket"].astype(str),
        plot["avg_1m_tr_bps"],
        color="#CC6F47",
        marker="o",
        linewidth=1.0,
        label="Avg 1m TR bps",
    )
    ax2.set_ylabel("Avg 1m true range, bps")
    add_chart_header(
        fig,
        ax1,
        "SBIN volatility and volume cluster near the open",
        "Average 1-minute volume and true range by session bucket, last 12 months",
    )
    path = CHART_DIR / "time_of_day_velocity.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def save_chart_strategy(summary: pd.DataFrame, selected: str) -> Path:
    import matplotlib.pyplot as plt
    import seaborn as sns

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    use_chart_theme(sns, plt)
    selected_summary = summary[summary["variant"] == selected].copy()
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    plot = selected_summary[["set_name", "win_rate", "profit_factor", "expectancy_r"]].copy()
    plot["profit_factor"] = pd.to_numeric(
        plot["profit_factor"].replace("inf", 999), errors="coerce"
    )
    long = plot.melt(
        id_vars="set_name",
        value_vars=["win_rate", "profit_factor", "expectancy_r"],
        var_name="metric",
        value_name="value",
    )
    sns.barplot(
        data=long,
        x="metric",
        y="value",
        hue="set_name",
        ax=ax,
        palette={"train": "#A3BEFA", "test": "#F0986E"},
        edgecolor="#1F2430",
        linewidth=1.0,
    )
    ax.set_xlabel("")
    ax.set_ylabel("Value")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), frameon=False, ncol=2, borderaxespad=0)
    add_chart_header(
        fig,
        ax,
        "Selected strategy validation check",
        "Win rate is percent; Profit Factor and expectancy are unit metrics for the selected variant",
    )
    path = CHART_DIR / "selected_strategy_metrics.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def use_chart_theme(sns, plt) -> None:
    sns.set_theme(
        style="whitegrid",
        rc={
            "figure.facecolor": "#FCFCFD",
            "axes.facecolor": "#FFFFFF",
            "axes.edgecolor": "#D7DBE7",
            "axes.labelcolor": "#1F2430",
            "grid.color": "#E6E8F0",
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.sans-serif": ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial", "sans-serif"],
        },
    )


def add_chart_header(fig, ax, title: str, subtitle: str) -> None:
    ax.set_title("")
    fig.subplots_adjust(top=0.78)
    left = ax.get_position().x0
    fig.text(
        left,
        0.985,
        textwrap.fill(title, 78),
        ha="left",
        va="top",
        fontsize=13,
        fontweight="semibold",
        color="#1F2430",
    )
    fig.text(
        left, 0.925, textwrap.fill(subtitle, 112), ha="left", va="top", fontsize=9, color="#6F768A"
    )
    try:
        import seaborn as sns

        sns.despine(ax=ax)
    except Exception:
        pass


def html_escape(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df.empty:
        return "_No rows._"
    view = df.head(max_rows).copy() if max_rows else df.copy()

    def fmt(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.4f}".rstrip("0").rstrip(".")
        return str(value).replace("|", "\\|")

    cols = list(view.columns)
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    rows = ["| " + " | ".join(fmt(row[col]) for col in cols) + " |" for _, row in view.iterrows()]
    return "\n".join([header, separator, *rows])


def df_to_html_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "<p><em>No rows.</em></p>"
    view = df.head(max_rows).copy()
    headers = "".join(f"<th>{html_escape(col)}</th>" for col in view.columns)
    body = []
    for _, row in view.iterrows():
        cells = "".join(
            f"<td>{html_escape(round(val, 4) if isinstance(val, float) else val)}</td>"
            for val in row
        )
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_report(
    metadata: dict,
    tod: pd.DataFrame,
    noise_overall: pd.DataFrame,
    opening_summary: pd.DataFrame,
    gap_summary: pd.DataFrame,
    htf: pd.DataFrame,
    strategy_summary: pd.DataFrame,
    selected_variant: str,
    charts: dict[str, Path],
) -> tuple[str, str]:
    selected = strategy_summary[strategy_summary["variant"] == selected_variant].copy()
    train = selected[selected["set_name"] == "train"].iloc[0].to_dict()
    test = selected[selected["set_name"] == "test"].iloc[0].to_dict()
    validation = strategy_validation_status(train, test)

    high_velocity = ", ".join(tod.loc[tod["personality"] == "high-velocity", "Bucket"].astype(str))
    dead = ", ".join(tod.loc[tod["personality"] == "dead/noisy", "Bucket"].astype(str))
    continuation = (
        float(noise_overall.loc[noise_overall["class"] == "continuation", "percent"].iloc[0])
        if "continuation" in set(noise_overall["class"])
        else 0
    )
    mean_rev = (
        float(noise_overall.loc[noise_overall["class"] == "mean_reversion", "percent"].iloc[0])
        if "mean_reversion" in set(noise_overall["class"])
        else 0
    )
    personality = "trend-following" if continuation > mean_rev else "mean-reverting"
    if charts.get("time_of_day") and charts.get("strategy"):
        visual_evidence_html = f"""
    <p>The first chart compares average 1-minute volume with average 1-minute true range by session bucket. It identifies the windows where SBIN offers movement and liquidity together, which matters more than volatility alone.</p>
    <img src="{charts['time_of_day'].relative_to(OUTPUT_DIR).as_posix()}" alt="Time of day volatility and volume chart">
    <p>The second chart compares in-sample and out-of-sample metrics for the selected strategy. The important check is not just whether the discovery period looks good, but whether the final three months remain profitable without tuning.</p>
    <img src="{charts['strategy'].relative_to(OUTPUT_DIR).as_posix()}" alt="Selected strategy metrics chart">
"""
    else:
        visual_evidence_html = f"""
    <p>Chart rendering was skipped because the local Python runtime did not have a plotting backend available. The same evidence is preserved below as audit tables.</p>
    <h3>Time-of-day velocity table</h3>{df_to_html_table(tod)}
    <h3>Selected strategy metrics</h3>{df_to_html_table(selected[['set_name','trades','win_rate','profit_factor','expectancy_r','max_drawdown_r','avg_trade_duration_min']])}
"""

    md = f"""# SBIN Personality And Strategy Discovery Report

## Executive Summary

- SBIN's intraday personality is **{personality} on 1-minute follow-through**, with continuation at {continuation:.1f}% versus mean reversion at {mean_rev:.1f}% under the 3-minute follow-through definition.
- High-velocity windows are **{high_velocity or 'not clearly separated'}**. Dead/noisy windows are **{dead or 'not clearly separated'}**.
- **No production-ready strategy was promoted from this run.** {validation['message']}
- Best discovery candidate: `{selected_variant}`.
- In-sample: {int(train['trades'])} trades, {train['win_rate']:.2f}% win rate, PF {train['profit_factor']}, expectancy {train['expectancy_r']:.3f}R, max DD {train['max_drawdown_r']:.2f}R.
- Out-of-sample: {int(test['trades'])} trades, {test['win_rate']:.2f}% win rate, PF {test['profit_factor']}, expectancy {test['expectancy_r']:.3f}R, max DD {test['max_drawdown_r']:.2f}R.

## Personality Profile

### Time-Of-Day Volatility

{markdown_table(tod)}

### Noise Vs Signal

{markdown_table(noise_overall)}

### Opening Range Statistics

{markdown_table(opening_summary)}

### Gap Resolution

{markdown_table(gap_summary) if not gap_summary.empty else 'No qualifying gaps above threshold.'}

### Higher-Timeframe Dominance

{markdown_table(htf) if not htf.empty else 'No qualifying 5-minute trend setups found.'}

## Mechanical Strategy Decision

**Decision: do not promote this SBIN candidate to paper/live trading yet.**

Rejected candidate: `{selected_variant}`.

- Entry uses the setup, boundary, time, VWAP, EMA, volume, and macro filters encoded in the variant string.
- Entry price is next 5-minute candle open after the signal candle.
- Stop uses the larger of recent signal-candle adverse excursion and ATR-multiple risk.
- Target is fixed at the variant's R multiple. Minimum tested reward/risk is {MIN_RR}:1.
- Same-minute stop/target conflict resolves conservatively as stop first.
- Exit at {FORCED_EXIT.strftime('%H:%M')} if neither stop nor target is hit.

The rule above is preserved for audit and future refinement, but it is not a validated trading system because it did not clear the target thresholds.

## Comparative Backtest Summary

{markdown_table(selected[['set_name','trades','win_rate','profit_factor','expectancy_r','max_drawdown_r','avg_trade_duration_min']])}

## Scope And Caveats

- Data source: local FYERS CSV files for SBIN.
- Research window: {metadata['research_start']} to {metadata['research_end']}.
- Discovery window: {metadata['train_start']} to {metadata['train_end_exclusive']} exclusive.
- Out-of-sample window: {metadata['test_start']} to {metadata['research_end']}.
- Partial current sessions are excluded; the research end date is the last complete trading session found in the 5-minute file.
- Metrics are historical simulation results, not live execution proof.
- Brokerage, taxes, slippage, queue position, and whole-share sizing are not included in the headline R metrics.
"""

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SBIN Personality And Strategy Discovery Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #FCFCFD; color: #1F2430; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 36px 28px 64px; }}
    h1 {{ font-size: 30px; margin: 0 0 8px; }}
    h2 {{ margin-top: 34px; border-top: 1px solid #E6E8F0; padding-top: 22px; }}
    h3 {{ margin-top: 24px; }}
    p, li {{ line-height: 1.55; }}
    .summary {{ background: #FFFFFF; border: 1px solid #E6E8F0; padding: 18px 22px; border-radius: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .metric {{ background: #FFFFFF; border: 1px solid #E6E8F0; padding: 14px 16px; border-radius: 8px; }}
    .metric strong {{ display: block; font-size: 22px; margin-top: 6px; }}
    img {{ max-width: 100%; border: 1px solid #E6E8F0; border-radius: 8px; background: white; }}
    table {{ border-collapse: collapse; width: 100%; background: white; margin: 12px 0 18px; font-size: 13px; }}
    th, td {{ border: 1px solid #E6E8F0; padding: 8px 10px; text-align: left; }}
    th {{ background: #F4F5F7; }}
    code {{ background: #F4F5F7; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>SBIN Personality And Strategy Discovery Report</h1>
  <section class="summary">
    <h2>Executive Summary</h2>
    <ul>
      <li>SBIN is <strong>{html_escape(personality)}</strong> on 1-minute follow-through: continuation {continuation:.1f}% vs mean reversion {mean_rev:.1f}%.</li>
      <li>High-velocity windows: <strong>{html_escape(high_velocity or 'not clearly separated')}</strong>. Dead/noisy windows: <strong>{html_escape(dead or 'not clearly separated')}</strong>.</li>
      <li><strong>No production-ready strategy was promoted.</strong> {html_escape(validation['message'])}</li>
      <li>Best discovery candidate: <code>{html_escape(selected_variant)}</code>.</li>
      <li>OOS result: {int(test['trades'])} trades, {test['win_rate']:.2f}% win rate, PF {test['profit_factor']}, expectancy {test['expectancy_r']:.3f}R, max DD {test['max_drawdown_r']:.2f}R.</li>
    </ul>
  </section>
  <section>
    <h2>Key Findings With Visual Evidence</h2>
    {visual_evidence_html}
  </section>
  <section>
    <h2>Scope, Data, And Metric Definitions</h2>
    <p>Research window: {metadata['research_start']} to {metadata['research_end']}. Discovery: {metadata['train_start']} to {metadata['train_end_exclusive']} exclusive. OOS: {metadata['test_start']} to {metadata['research_end']}.</p>
    <p>Continuation and mean reversion are measured on eligible 1-minute bars using the signed move over the next three minutes. Profit Factor is gross positive R divided by absolute gross negative R.</p>
  </section>
  <section>
    <h2>SBIN Personality Profile</h2>
    <h3>Time-of-day profile</h3>{df_to_html_table(tod)}
    <h3>Noise vs signal</h3>{df_to_html_table(noise_overall)}
    <h3>Opening range statistics</h3>{df_to_html_table(opening_summary)}
    <h3>Gap resolution</h3>{df_to_html_table(gap_summary)}
    <h3>Higher-timeframe dominance</h3>{df_to_html_table(htf)}
  </section>
  <section>
    <h2>Mechanical Strategy Decision</h2>
    <p><strong>Decision: do not promote this SBIN candidate to paper/live trading yet.</strong></p>
    <p>Rejected candidate preserved for audit: <code>{html_escape(selected_variant)}</code>.</p>
    <ul>
      <li>Signal is evaluated on closed 5-minute candles.</li>
      <li>Entry is next 5-minute candle open after the signal.</li>
      <li>Stop uses the larger of signal-candle adverse excursion and ATR-multiple risk.</li>
      <li>Target is fixed by the variant R multiple, with minimum tested R:R of {MIN_RR}:1.</li>
      <li>Exit at {FORCED_EXIT.strftime('%H:%M')} if neither stop nor target is hit.</li>
    </ul>
    <p>The rule above is not a validated trading system because it did not clear the target thresholds.</p>
  </section>
  <section>
    <h2>Comparative Backtest Summary</h2>
    {df_to_html_table(selected[['set_name','trades','win_rate','profit_factor','expectancy_r','max_drawdown_r','avg_trade_duration_min']])}
  </section>
  <section>
    <h2>Limitations And Next Steps</h2>
    <ul>
      <li>Headline R metrics exclude brokerage, taxes, slippage, partial fills, queue position, leverage, and whole-share sizing.</li>
      <li>This is a single-symbol discovery result. Validate on additional bank/large-cap names before promoting to live paper trading.</li>
      <li>If Bank Nifty data is added, rerun with sector-index regime and VWAP filters.</li>
    </ul>
  </section>
</main>
</body>
</html>"""
    return md, html


def run_research() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    df1 = add_indicators(load_candles(SYMBOL, "1MIN"))
    df5 = add_indicators(load_candles(SYMBOL, "5MIN"))
    df15 = load_candles(SYMBOL, "15MIN")
    df1d = load_candles(SYMBOL, "1D")
    df1w = load_candles(SYMBOL, "1W")

    start, test_start, end = research_window(df5)
    df1 = filter_window(df1, start, end)
    df5 = filter_window(df5, start, end)
    levels = daily_levels(df5)
    or15 = opening_range(df1, time(9, 30), "OR15")
    or30 = opening_range(df1, time(9, 45), "OR30")
    df5 = df5.merge(levels[["Date", "PrevHigh", "PrevLow", "PrevClose"]], on="Date", how="left")
    df5 = df5.merge(or15, on="Date", how="left").merge(or30, on="Date", how="left")
    df5 = attach_macro(df5, df1d, df1w)

    tod = time_of_day_profile(df1, df5)
    noise_overall, noise_by_bucket = noise_signal_profile(df1)
    or_daily, or_summary = opening_range_stats(df1)
    gap_detail, gap_summary = gap_resolution_stats(df1, levels)
    htf = htf_dominance(df1, df5, start, end)

    all_trades: list[Trade] = []
    df1_by_day = {d: part.reset_index(drop=True) for d, part in df1.groupby("Date")}
    for variant in candidate_variants():
        all_trades.extend(generate_trades(df1, df5, variant, start, test_start, end, df1_by_day))
    summary = summarize_variants(all_trades)
    selected = select_best(summary)
    if not selected:
        raise RuntimeError("No strategy variants produced trades.")

    trades_df = pd.DataFrame([asdict(t) for t in all_trades])
    charts: dict[str, Path] = {}
    try:
        charts = {
            "time_of_day": save_chart_time_of_day(tod),
            "strategy": save_chart_strategy(summary, selected),
        }
    except ModuleNotFoundError:
        charts = {}
    metadata = {
        "symbol": SYMBOL,
        "available_start": str(load_candles(SYMBOL, "5MIN")["Datetime"].min()),
        "available_end": str(load_candles(SYMBOL, "5MIN")["Datetime"].max()),
        "research_start": str(start.date()),
        "train_start": str(start.date()),
        "train_end_exclusive": str(test_start.date()),
        "test_start": str(test_start.date()),
        "research_end": str(end.date()),
        "selected_variant": selected,
        "strategy_validation": strategy_validation_status(
            summary[(summary["variant"] == selected) & (summary["set_name"] == "train")]
            .iloc[0]
            .to_dict(),
            summary[(summary["variant"] == selected) & (summary["set_name"] == "test")]
            .iloc[0]
            .to_dict(),
        ),
        "target_thresholds": {
            "min_train_trades": MIN_TRAIN_TRADES,
            "min_test_trades": MIN_TEST_TRADES,
            "min_win_rate_pct": TARGET_WIN_RATE,
            "min_profit_factor": TARGET_PROFIT_FACTOR,
            "min_rr": MIN_RR,
        },
        "partial_sessions_excluded": True,
        "candidate_variants_tested": len(candidate_variants()),
        "output_dir": str(OUTPUT_DIR),
    }
    md, html = build_report(
        metadata, tod, noise_overall, or_summary, gap_summary, htf, summary, selected, charts
    )

    outputs = {
        "metadata": OUTPUT_DIR / "metadata.json",
        "report_md": OUTPUT_DIR / "sbin_personality_strategy_report.md",
        "report_html": OUTPUT_DIR / "report.html",
        "time_of_day_profile": OUTPUT_DIR / "time_of_day_profile.csv",
        "noise_overall": OUTPUT_DIR / "noise_signal_overall.csv",
        "noise_by_bucket": OUTPUT_DIR / "noise_signal_by_bucket.csv",
        "opening_range_daily": OUTPUT_DIR / "opening_range_daily.csv",
        "opening_range_summary": OUTPUT_DIR / "opening_range_summary.csv",
        "gap_detail": OUTPUT_DIR / "gap_detail.csv",
        "gap_summary": OUTPUT_DIR / "gap_summary.csv",
        "htf_dominance": OUTPUT_DIR / "htf_dominance.csv",
        "strategy_summary": OUTPUT_DIR / "strategy_summary.csv",
        "strategy_trades": OUTPUT_DIR / "strategy_trades.csv",
    }
    outputs["metadata"].write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    outputs["report_md"].write_text(md, encoding="utf-8")
    outputs["report_html"].write_text(html, encoding="utf-8")
    tod.to_csv(outputs["time_of_day_profile"], index=False)
    noise_overall.to_csv(outputs["noise_overall"], index=False)
    noise_by_bucket.to_csv(outputs["noise_by_bucket"], index=False)
    or_daily.to_csv(outputs["opening_range_daily"], index=False)
    or_summary.to_csv(outputs["opening_range_summary"], index=False)
    gap_detail.to_csv(outputs["gap_detail"], index=False)
    gap_summary.to_csv(outputs["gap_summary"], index=False)
    htf.to_csv(outputs["htf_dominance"], index=False)
    summary.to_csv(outputs["strategy_summary"], index=False)
    trades_df.to_csv(outputs["strategy_trades"], index=False)

    return {
        "metadata": metadata,
        "time_of_day": tod,
        "noise": noise_overall,
        "opening_range": or_summary,
        "gap_summary": gap_summary,
        "htf": htf,
        "summary": summary,
        "trades": trades_df,
        "outputs": {k: str(v) for k, v in outputs.items()},
    }


if __name__ == "__main__":
    result = run_research()
    metadata = result["metadata"]
    selected = metadata["selected_variant"]
    selected_summary = result["summary"][result["summary"]["variant"] == selected]
    print(f"SBIN personality research complete: {metadata['output_dir']}")
    print(f"Selected variant: {selected}")
    print(
        selected_summary[
            [
                "set_name",
                "trades",
                "win_rate",
                "profit_factor",
                "expectancy_r",
                "max_drawdown_r",
                "avg_trade_duration_min",
            ]
        ].to_string(index=False)
    )
