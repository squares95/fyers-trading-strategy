from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "Data"
OUTPUT_DIR = ROOT / "Research" / "SBIN_SMC"
SYMBOL = "SBIN"
MIN_TRAIN_TRADES_FOR_SELECTION = 10
RESEARCH_MONTHS = 12
TEST_MONTHS = 4

MARKET_OPEN = time(9, 15)
SETUP_START = time(9, 30)
SETUP_END = time(11, 30)
LAST_ENTRY_TIME = time(12, 0)
FORCED_EXIT_TIME = time(15, 15)

MAX_STOP_PCT = 0.008
MIN_RR = 2.0
BREAKEVEN_AT_R = 1.0
SWEEP_BREACH_PCT = 0.0002
TICK_BUFFER = 0.05


@dataclass(frozen=True)
class Variant:
    sweep_reference: str
    entry_trigger: str
    banknifty_filter: bool

    @property
    def label(self) -> str:
        suffix = "bank_vwap" if self.banknifty_filter else "no_bank_filter"
        return f"{self.sweep_reference}__{self.entry_trigger}__{suffix}"


@dataclass
class Trade:
    variant: str
    set_name: str
    symbol: str
    date: str
    direction: str
    sweep_reference: str
    entry_trigger: str
    sweep_time: str
    sweep_level: float
    sweep_extreme: float
    confirmation_time: str
    entry_time: str
    entry_price: float
    stop_price: float
    target_price: float
    exit_time: str
    exit_price: float
    outcome: str
    pnl_per_share: float
    r_multiple: float
    risk_per_share: float
    stop_pct: float
    mfe_r: float
    mae_r: float
    minutes_held: float
    bias_15m: int
    bias_1h: int
    fvg_time: str
    fvg_size: float
    order_block_low: float
    order_block_high: float
    failure_reason: str = ""


def load_candles(symbol: str, timeframe: str) -> pd.DataFrame:
    path = DATA_ROOT / symbol / f"{symbol}_{timeframe}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing candle file: {path}")

    df = pd.read_csv(path, parse_dates=["Datetime"])
    keep = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    df = df[keep].copy()
    for column in keep[1:]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=keep).drop_duplicates(subset=["Datetime"])
    df = df.sort_values("Datetime").reset_index(drop=True)
    df["Date"] = df["Datetime"].dt.date
    df["Time"] = df["Datetime"].dt.time
    return df


def add_atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
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
    out["ATR"] = tr.rolling(window=window, min_periods=1).mean()
    return out


def add_fvg_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["BullFVG"] = out["Low"] > out["High"].shift(2)
    out["BearFVG"] = out["High"] < out["Low"].shift(2)
    out["BullFVGSize"] = (out["Low"] - out["High"].shift(2)).clip(lower=0)
    out["BearFVGSize"] = (out["Low"].shift(2) - out["High"]).clip(lower=0)
    return out


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
    return daily


def opening_range(df5: pd.DataFrame) -> pd.DataFrame:
    mask = (df5["Time"] >= MARKET_OPEN) & (df5["Time"] < SETUP_START)
    return (
        df5.loc[mask]
        .groupby("Date")
        .agg(ORHigh=("High", "max"), ORLow=("Low", "min"))
        .reset_index()
    )


def resample_hourly_from_5m(df5: pd.DataFrame) -> pd.DataFrame:
    df = df5.copy()
    session_start = pd.to_datetime(df["Date"].astype(str) + " 09:15:00")
    minutes = ((df["Datetime"] - session_start).dt.total_seconds() // 60).astype(int)
    df["BucketStart"] = session_start + pd.to_timedelta((minutes // 60) * 60, unit="m")
    out = (
        df.groupby(["Date", "BucketStart"], as_index=False)
        .agg(
            Datetime=("BucketStart", "first"),
            Open=("Open", "first"),
            High=("High", "max"),
            Low=("Low", "min"),
            Close=("Close", "last"),
            Volume=("Volume", "sum"),
        )
        .sort_values("Datetime")
        .reset_index(drop=True)
    )
    out["Time"] = out["Datetime"].dt.time
    return out


def add_structure_bias(htf: pd.DataFrame, lookback: int, available_after_minutes: int) -> pd.DataFrame:
    out = htf.copy()
    prior_high = out["High"].rolling(lookback, min_periods=lookback).max().shift(1)
    prior_low = out["Low"].rolling(lookback, min_periods=lookback).min().shift(1)
    event = np.where(out["Close"] > prior_high, 1, np.where(out["Close"] < prior_low, -1, 0))
    out["Bias"] = pd.Series(event, index=out.index).replace(0, np.nan).ffill().fillna(0).astype(int)
    out["AvailableAt"] = out["Datetime"] + pd.to_timedelta(available_after_minutes, unit="m")
    return out[["AvailableAt", "Bias"]].sort_values("AvailableAt")


def attach_bias(df5: pd.DataFrame, df15: pd.DataFrame) -> pd.DataFrame:
    base = df5.sort_values("Datetime").copy()
    bias15 = add_structure_bias(df15, lookback=8, available_after_minutes=15).rename(columns={"Bias": "Bias15"})
    hourly = resample_hourly_from_5m(df5)
    bias60 = add_structure_bias(hourly, lookback=4, available_after_minutes=60).rename(columns={"Bias": "Bias60"})

    base = pd.merge_asof(
        base,
        bias15,
        left_on="Datetime",
        right_on="AvailableAt",
        direction="backward",
    ).drop(columns=["AvailableAt"])
    base = pd.merge_asof(
        base,
        bias60,
        left_on="Datetime",
        right_on="AvailableAt",
        direction="backward",
    ).drop(columns=["AvailableAt"])
    base["Bias15"] = base["Bias15"].fillna(0).astype(int)
    base["Bias60"] = base["Bias60"].fillna(0).astype(int)
    return base


def higher_timeframe_allows(direction: int, row: pd.Series) -> bool:
    # This allows reversals after a liquidity grab but blocks trades where both
    # structural timeframes are already pointing against the entry.
    return not (int(row["Bias15"]) == -direction and int(row["Bias60"]) == -direction)


def find_banknifty_source() -> Path | None:
    candidates = [
        DATA_ROOT / "BANKNIFTY" / "BANKNIFTY_1MIN.csv",
        DATA_ROOT / "NIFTYBANK" / "NIFTYBANK_1MIN.csv",
        DATA_ROOT / "NIFTY_BANK" / "NIFTY_BANK_1MIN.csv",
    ]
    return next((path for path in candidates if path.exists()), None)


def load_banknifty_vwap() -> pd.DataFrame | None:
    path = find_banknifty_source()
    if path is None:
        return None

    df = pd.read_csv(path, parse_dates=["Datetime"])
    df = df[["Datetime", "High", "Low", "Close", "Volume"]].dropna().sort_values("Datetime")
    df["Date"] = df["Datetime"].dt.date
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    pv = typical * df["Volume"]
    df["VWAP"] = pv.groupby(df["Date"]).cumsum() / df["Volume"].groupby(df["Date"]).cumsum()
    return df[["Datetime", "Close", "VWAP"]].rename(columns={"Close": "BankNiftyClose"})


def bank_filter_allows(
    bank_vwap: pd.DataFrame | None,
    direction: int,
    timestamp: pd.Timestamp,
) -> bool:
    if bank_vwap is None:
        return False

    row = pd.merge_asof(
        pd.DataFrame({"Datetime": [timestamp]}),
        bank_vwap,
        on="Datetime",
        direction="backward",
    ).iloc[0]
    if pd.isna(row["VWAP"]):
        return False
    if direction == 1:
        return row["BankNiftyClose"] > row["VWAP"]
    return row["BankNiftyClose"] < row["VWAP"]


def detect_sweep(row: pd.Series, variant: Variant) -> tuple[int, float] | None:
    if variant.sweep_reference == "previous_day":
        high_level = row["PrevHigh"]
        low_level = row["PrevLow"]
    elif variant.sweep_reference == "opening_15m":
        high_level = row["ORHigh"]
        low_level = row["ORLow"]
    else:
        raise ValueError(f"Unknown sweep reference: {variant.sweep_reference}")

    if pd.isna(high_level) or pd.isna(low_level):
        return None

    long_breach = (low_level - row["Low"]) / low_level if low_level else 0
    short_breach = (row["High"] - high_level) / high_level if high_level else 0
    swept_low = row["Low"] < low_level and row["Close"] > low_level and long_breach >= SWEEP_BREACH_PCT
    swept_high = row["High"] > high_level and row["Close"] < high_level and short_breach >= SWEEP_BREACH_PCT

    if swept_low and swept_high:
        return None
    if swept_low:
        return 1, float(low_level)
    if swept_high:
        return -1, float(high_level)
    return None


def find_order_block(df5_day: pd.DataFrame, start_idx: int, end_idx: int, direction: int) -> tuple[int, float, float] | None:
    left = max(0, start_idx - 4)
    for idx in range(end_idx - 1, left - 1, -1):
        candle = df5_day.iloc[idx]
        bearish = candle["Close"] < candle["Open"]
        bullish = candle["Close"] > candle["Open"]
        if direction == 1 and bearish:
            return idx, float(candle["Low"]), float(max(candle["Open"], candle["Close"]))
        if direction == -1 and bullish:
            return idx, float(min(candle["Open"], candle["Close"])), float(candle["High"])
    return None


def has_1m_fvg(df1_day: pd.DataFrame, direction: int, start: pd.Timestamp, end: pd.Timestamp) -> tuple[str, float]:
    window = df1_day[(df1_day["Datetime"] >= start) & (df1_day["Datetime"] <= end)]
    if window.empty:
        return "", 0.0

    if direction == 1:
        hits = window[window["BullFVG"]]
        if hits.empty:
            return "", 0.0
        first = hits.iloc[0]
        return str(first["Datetime"]), float(first["BullFVGSize"])

    hits = window[window["BearFVG"]]
    if hits.empty:
        return "", 0.0
    first = hits.iloc[0]
    return str(first["Datetime"]), float(first["BearFVGSize"])


def find_5m_confirmation(
    df5_day: pd.DataFrame,
    df1_day: pd.DataFrame,
    sweep_pos: int,
    direction: int,
) -> dict | None:
    sweep = df5_day.iloc[sweep_pos]
    max_pos = min(len(df5_day) - 1, sweep_pos + 6)
    for pos in range(sweep_pos + 1, max_pos + 1):
        bar = df5_day.iloc[pos]
        if bar["Time"] > SETUP_END:
            break
        prior = df5_day.iloc[max(0, pos - 2) : pos]
        if prior.empty:
            continue

        body = abs(bar["Close"] - bar["Open"])
        atr = max(float(bar.get("ATR", 0.0)), 0.01)
        if direction == 1:
            displacement = bar["Close"] > prior["High"].max() and bar["Close"] > bar["Open"] and body >= 0.35 * atr
            fvg_time = str(bar["Datetime"]) if bool(bar["BullFVG"]) else ""
            fvg_size = float(bar["BullFVGSize"]) if bool(bar["BullFVG"]) else 0.0
        else:
            displacement = bar["Close"] < prior["Low"].min() and bar["Close"] < bar["Open"] and body >= 0.35 * atr
            fvg_time = str(bar["Datetime"]) if bool(bar["BearFVG"]) else ""
            fvg_size = float(bar["BearFVGSize"]) if bool(bar["BearFVG"]) else 0.0

        if not displacement:
            continue

        if not fvg_time:
            one_min_start = pd.Timestamp(bar["Datetime"])
            one_min_end = one_min_start + pd.Timedelta(minutes=4)
            fvg_time, fvg_size = has_1m_fvg(df1_day, direction, one_min_start, one_min_end)
        if not fvg_time:
            continue

        ob = find_order_block(df5_day, sweep_pos, pos, direction)
        if ob is None:
            continue
        _, ob_low, ob_high = ob
        return {
            "position": pos,
            "time": pd.Timestamp(bar["Datetime"]),
            "order_block_low": ob_low,
            "order_block_high": ob_high,
            "fvg_time": fvg_time,
            "fvg_size": fvg_size,
        }
    return None


def find_direct_order_block_entry(
    df1_day: pd.DataFrame,
    confirmation: dict,
    direction: int,
) -> tuple[pd.Timestamp, float] | None:
    entry_price = (confirmation["order_block_low"] + confirmation["order_block_high"]) / 2
    start = confirmation["time"] + pd.Timedelta(minutes=5)
    end = min(
        pd.Timestamp.combine(start.date(), LAST_ENTRY_TIME),
        start + pd.Timedelta(minutes=40),
    )
    future = df1_day[(df1_day["Datetime"] >= start) & (df1_day["Datetime"] <= end)]
    for _, minute in future.iterrows():
        if minute["Low"] <= entry_price <= minute["High"]:
            return pd.Timestamp(minute["Datetime"]), float(entry_price)
    return None


def find_1m_mss_entry(
    df1_day: pd.DataFrame,
    sweep_time: pd.Timestamp,
    direction: int,
) -> tuple[pd.Timestamp, float, str, float] | None:
    start = sweep_time + pd.Timedelta(minutes=1)
    end = min(
        pd.Timestamp.combine(sweep_time.date(), SETUP_END),
        sweep_time + pd.Timedelta(minutes=20),
    )
    df = df1_day[(df1_day["Datetime"] >= start) & (df1_day["Datetime"] <= end)].copy()
    if len(df) < 6:
        return None

    df["PriorHigh5"] = df1_day["High"].rolling(5).max().shift(1).reindex(df.index)
    df["PriorLow5"] = df1_day["Low"].rolling(5).min().shift(1).reindex(df.index)
    for _, minute in df.iterrows():
        if direction == 1:
            structural_shift = minute["Close"] > minute["PriorHigh5"] and minute["Close"] > minute["Open"]
            has_fvg = bool(minute["BullFVG"])
            fvg_size = float(minute["BullFVGSize"]) if has_fvg else 0.0
        else:
            structural_shift = minute["Close"] < minute["PriorLow5"] and minute["Close"] < minute["Open"]
            has_fvg = bool(minute["BearFVG"])
            fvg_size = float(minute["BearFVGSize"]) if has_fvg else 0.0
        if structural_shift and has_fvg:
            return pd.Timestamp(minute["Datetime"]), float(minute["Close"]), str(minute["Datetime"]), fvg_size
    return None


def build_stop_target(
    direction: int,
    entry_price: float,
    sweep_extreme: float,
    confirmation: dict,
) -> tuple[float, float, float, float] | None:
    if direction == 1:
        stop = min(sweep_extreme, confirmation["order_block_low"]) - TICK_BUFFER
        risk = entry_price - stop
        target = entry_price + MIN_RR * risk
    else:
        stop = max(sweep_extreme, confirmation["order_block_high"]) + TICK_BUFFER
        risk = stop - entry_price
        target = entry_price - MIN_RR * risk

    if risk <= 0:
        return None
    stop_pct = risk / entry_price
    if stop_pct > MAX_STOP_PCT:
        return None
    return float(stop), float(target), float(risk), float(stop_pct)


def simulate_exit(
    df1_day: pd.DataFrame,
    entry_time: pd.Timestamp,
    entry_price: float,
    stop: float,
    target: float,
    risk: float,
    direction: int,
    include_entry_minute: bool,
) -> dict | None:
    forced_exit = pd.Timestamp.combine(entry_time.date(), FORCED_EXIT_TIME)
    if include_entry_minute:
        path = df1_day[(df1_day["Datetime"] >= entry_time) & (df1_day["Datetime"] <= forced_exit)]
    else:
        path = df1_day[(df1_day["Datetime"] > entry_time) & (df1_day["Datetime"] <= forced_exit)]
    if path.empty:
        return None

    exit_time = pd.Timestamp(path.iloc[-1]["Datetime"])
    exit_price = float(path.iloc[-1]["Close"])
    outcome = "time_exit"
    rows_until_exit = []
    active_stop = stop
    breakeven_armed = False

    for _, bar in path.iterrows():
        rows_until_exit.append(bar)
        ts = pd.Timestamp(bar["Datetime"])
        if direction == 1:
            stop_hit = bar["Low"] <= active_stop
            target_hit = bar["High"] >= target
            breakeven_hit = bar["High"] >= entry_price + BREAKEVEN_AT_R * risk
        else:
            stop_hit = bar["High"] >= active_stop
            target_hit = bar["Low"] <= target
            breakeven_hit = bar["Low"] <= entry_price - BREAKEVEN_AT_R * risk

        if stop_hit and target_hit:
            exit_time = ts
            exit_price = float(active_stop)
            outcome = "breakeven" if breakeven_armed and active_stop == entry_price else "stop"
            break
        if stop_hit:
            exit_time = ts
            exit_price = float(active_stop)
            outcome = "breakeven" if breakeven_armed and active_stop == entry_price else "stop"
            break
        if target_hit:
            exit_time, exit_price, outcome = ts, target, "target"
            break
        if breakeven_hit and not breakeven_armed:
            active_stop = entry_price
            breakeven_armed = True

    observed = pd.DataFrame(rows_until_exit)
    if direction == 1:
        mfe_r = (observed["High"].max() - entry_price) / risk
        mae_r = (entry_price - observed["Low"].min()) / risk
        pnl = exit_price - entry_price
    else:
        mfe_r = (entry_price - observed["Low"].min()) / risk
        mae_r = (observed["High"].max() - entry_price) / risk
        pnl = entry_price - exit_price

    return {
        "exit_time": exit_time,
        "exit_price": float(exit_price),
        "outcome": outcome,
        "pnl_per_share": float(pnl),
        "r_multiple": float(pnl / risk),
        "mfe_r": float(mfe_r),
        "mae_r": float(mae_r),
        "minutes_held": float((exit_time - entry_time).total_seconds() / 60),
    }


def failure_reason(trade: dict) -> str:
    if trade["outcome"] != "stop":
        return ""
    if trade["mfe_r"] < 0.25:
        return "SMC trap: sweep kept running with almost no follow-through"
    if trade["minutes_held"] <= 20:
        return "Fast continuation through the swept level"
    if trade["sweep_reference"] == "opening_15m":
        return "Opening-range whipsaw after liquidity grab"
    if trade["mfe_r"] >= 1.0:
        return "Good move failed to reach 2R before reversing"
    return "Partial follow-through, then reversal into stop"


def generate_trades_for_variant(
    df1: pd.DataFrame,
    df5: pd.DataFrame,
    variant: Variant,
    bank_vwap: pd.DataFrame | None,
    split_start: pd.Timestamp,
    test_start: pd.Timestamp,
    end_date: pd.Timestamp,
) -> list[Trade]:
    if variant.banknifty_filter and bank_vwap is None:
        return []

    trades: list[Trade] = []
    for current_date, df5_day in df5.groupby("Date", sort=True):
        day_start = pd.Timestamp(current_date)
        if day_start < split_start or day_start > end_date:
            continue
        df1_day = df1[df1["Date"] == current_date]
        if df1_day.empty:
            continue

        session = df5_day[(df5_day["Time"] >= SETUP_START) & (df5_day["Time"] <= SETUP_END)].reset_index(drop=True)
        full_day = df5_day.reset_index(drop=True)
        trade_taken = False

        for _, sweep_row in session.iterrows():
            full_pos_matches = full_day.index[full_day["Datetime"] == sweep_row["Datetime"]].tolist()
            if not full_pos_matches:
                continue
            sweep_pos = full_pos_matches[0]
            detected = detect_sweep(sweep_row, variant)
            if detected is None:
                continue

            direction, sweep_level = detected
            if not higher_timeframe_allows(direction, sweep_row):
                continue
            if variant.banknifty_filter and not bank_filter_allows(bank_vwap, direction, pd.Timestamp(sweep_row["Datetime"])):
                continue

            confirmation = find_5m_confirmation(full_day, df1_day, sweep_pos, direction)
            if confirmation is None:
                continue

            if variant.entry_trigger == "direct_5m_ob":
                entry = find_direct_order_block_entry(df1_day, confirmation, direction)
                if entry is None:
                    continue
                entry_time, entry_price = entry
                include_entry_minute = True
                fvg_time = confirmation["fvg_time"]
                fvg_size = confirmation["fvg_size"]
            elif variant.entry_trigger == "market_1m_mss":
                mss_entry = find_1m_mss_entry(df1_day, pd.Timestamp(sweep_row["Datetime"]), direction)
                if mss_entry is None:
                    continue
                entry_time, entry_price, fvg_time, fvg_size = mss_entry
                include_entry_minute = False
            else:
                raise ValueError(f"Unknown entry trigger: {variant.entry_trigger}")

            if entry_time.time() > LAST_ENTRY_TIME:
                continue

            sweep_extreme = float(sweep_row["Low"] if direction == 1 else sweep_row["High"])
            risk_plan = build_stop_target(direction, entry_price, sweep_extreme, confirmation)
            if risk_plan is None:
                continue
            stop, target, risk, stop_pct = risk_plan

            exit_result = simulate_exit(
                df1_day,
                entry_time,
                entry_price,
                stop,
                target,
                risk,
                direction,
                include_entry_minute=include_entry_minute,
            )
            if exit_result is None:
                continue

            set_name = "test" if pd.Timestamp(current_date) >= test_start else "train"
            trade_dict = {
                "variant": variant.label,
                "set_name": set_name,
                "symbol": SYMBOL,
                "date": str(current_date),
                "direction": "LONG" if direction == 1 else "SHORT",
                "sweep_reference": variant.sweep_reference,
                "entry_trigger": variant.entry_trigger,
                "sweep_time": str(sweep_row["Datetime"]),
                "sweep_level": float(sweep_level),
                "sweep_extreme": float(sweep_extreme),
                "confirmation_time": str(confirmation["time"]),
                "entry_time": str(entry_time),
                "entry_price": float(entry_price),
                "stop_price": float(stop),
                "target_price": float(target),
                "exit_time": str(exit_result["exit_time"]),
                "exit_price": float(exit_result["exit_price"]),
                "outcome": str(exit_result["outcome"]),
                "pnl_per_share": float(exit_result["pnl_per_share"]),
                "r_multiple": float(exit_result["r_multiple"]),
                "risk_per_share": float(risk),
                "stop_pct": float(stop_pct),
                "mfe_r": float(exit_result["mfe_r"]),
                "mae_r": float(exit_result["mae_r"]),
                "minutes_held": float(exit_result["minutes_held"]),
                "bias_15m": int(sweep_row["Bias15"]),
                "bias_1h": int(sweep_row["Bias60"]),
                "fvg_time": str(fvg_time),
                "fvg_size": float(fvg_size),
                "order_block_low": float(confirmation["order_block_low"]),
                "order_block_high": float(confirmation["order_block_high"]),
            }
            trade_dict["failure_reason"] = failure_reason(trade_dict)
            trades.append(Trade(**trade_dict))
            trade_taken = True
            break

        if trade_taken:
            continue

    return trades


def metrics(trades: Iterable[Trade]) -> dict:
    rows = [asdict(trade) for trade in trades]
    if not rows:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "gross_profit_r": 0.0,
            "gross_loss_r": 0.0,
            "max_drawdown_r": 0.0,
            "avg_r": 0.0,
            "breakevens": 0,
            "losses": 0,
            "decisive_win_rate": 0.0,
        }
    df = pd.DataFrame(rows)
    r = df["r_multiple"].astype(float)
    wins = r > 0
    breakevens = r == 0
    losses = r < 0
    decisive = wins | losses
    gross_profit = r[wins].sum()
    gross_loss = -r[losses].sum()
    equity = r.cumsum()
    drawdown = equity - equity.cummax()
    pf = math.inf if gross_loss == 0 and gross_profit > 0 else (gross_profit / gross_loss if gross_loss else 0.0)
    return {
        "trades": int(len(df)),
        "win_rate": float(wins.mean() * 100),
        "decisive_win_rate": float((wins[decisive].mean() * 100) if decisive.any() else 0.0),
        "profit_factor": float(pf) if math.isfinite(pf) else "inf",
        "expectancy_r": float(r.mean()),
        "gross_profit_r": float(gross_profit),
        "gross_loss_r": float(gross_loss),
        "max_drawdown_r": float(drawdown.min()),
        "avg_r": float(r.mean()),
        "breakevens": int(breakevens.sum()),
        "losses": int(losses.sum()),
    }


def choose_best(summary: pd.DataFrame) -> str | None:
    train = summary[
        (summary["set_name"] == "train")
        & (summary["available"])
        & (summary["trades"] >= MIN_TRAIN_TRADES_FOR_SELECTION)
    ].copy()
    if train.empty:
        train = summary[(summary["set_name"] == "train") & (summary["available"]) & (summary["trades"] > 0)].copy()
    if train.empty:
        return None

    train["pf_rank_value"] = train["profit_factor"].replace("inf", 999.0).astype(float)
    train = train.sort_values(
        ["pf_rank_value", "expectancy_r", "win_rate", "trades"],
        ascending=[False, False, False, False],
    )
    return str(train.iloc[0]["variant"])


def summarize_failures(trades: list[Trade], selected_variant: str) -> pd.DataFrame:
    selected = [asdict(t) for t in trades if t.variant == selected_variant and t.outcome == "stop"]
    if not selected:
        return pd.DataFrame(columns=["failure_reason", "count", "avg_mfe_r", "avg_minutes_held"])
    df = pd.DataFrame(selected)
    return (
        df.groupby("failure_reason")
        .agg(
            count=("failure_reason", "size"),
            avg_mfe_r=("mfe_r", "mean"),
            avg_minutes_held=("minutes_held", "mean"),
        )
        .reset_index()
        .sort_values(["count", "avg_mfe_r"], ascending=[False, True])
    )


def run_research() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df1 = add_fvg_flags(load_candles(SYMBOL, "1MIN"))
    df5 = add_fvg_flags(add_atr(load_candles(SYMBOL, "5MIN")))
    df15 = load_candles(SYMBOL, "15MIN")

    levels = daily_levels(df5)
    opening = opening_range(df5)
    df5 = df5.merge(levels[["Date", "PrevHigh", "PrevLow"]], on="Date", how="left")
    df5 = df5.merge(opening, on="Date", how="left")
    df5 = attach_bias(df5, df15)

    max_ts = df5["Datetime"].max().normalize()
    start_ts = max_ts - pd.DateOffset(months=RESEARCH_MONTHS)
    test_start = max_ts - pd.DateOffset(months=TEST_MONTHS)
    df1 = df1[(df1["Datetime"] >= start_ts) & (df1["Datetime"] <= max_ts + pd.Timedelta(days=1))].copy()
    df5 = df5[(df5["Datetime"] >= start_ts) & (df5["Datetime"] <= max_ts + pd.Timedelta(days=1))].copy()

    bank_vwap = load_banknifty_vwap()
    variants = [
        Variant(sweep_reference, entry_trigger, bank_filter)
        for sweep_reference in ("previous_day", "opening_15m")
        for entry_trigger in ("direct_5m_ob", "market_1m_mss")
        for bank_filter in (False, True)
    ]

    all_trades: list[Trade] = []
    unavailable_variants: list[str] = []
    for variant in variants:
        if variant.banknifty_filter and bank_vwap is None:
            unavailable_variants.append(variant.label)
            continue
        all_trades.extend(
            generate_trades_for_variant(
                df1=df1,
                df5=df5,
                variant=variant,
                bank_vwap=bank_vwap,
                split_start=start_ts,
                test_start=test_start,
                end_date=max_ts,
            )
        )

    summary_rows = []
    for variant in variants:
        for set_name in ("train", "test"):
            subset = [trade for trade in all_trades if trade.variant == variant.label and trade.set_name == set_name]
            row = metrics(subset)
            row.update(
                {
                    "variant": variant.label,
                    "sweep_reference": variant.sweep_reference,
                    "entry_trigger": variant.entry_trigger,
                    "banknifty_filter": variant.banknifty_filter,
                    "set_name": set_name,
                    "available": variant.label not in unavailable_variants,
                }
            )
            summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)
    best_variant = choose_best(summary)
    trades_df = pd.DataFrame([asdict(trade) for trade in all_trades])
    failures = summarize_failures(all_trades, best_variant) if best_variant else pd.DataFrame()

    summary_path = OUTPUT_DIR / "sbin_smc_variant_summary.csv"
    trades_path = OUTPUT_DIR / "sbin_smc_trades.csv"
    failures_path = OUTPUT_DIR / "sbin_smc_failure_breakdown.csv"
    report_path = OUTPUT_DIR / "sbin_smc_research_report.md"
    metadata_path = OUTPUT_DIR / "sbin_smc_metadata.json"

    summary.to_csv(summary_path, index=False)
    trades_df.to_csv(trades_path, index=False)
    failures.to_csv(failures_path, index=False)

    metadata = {
        "symbol": SYMBOL,
        "data_range": {
            "available_start": str(load_candles(SYMBOL, "5MIN")["Datetime"].min()),
            "available_end": str(load_candles(SYMBOL, "5MIN")["Datetime"].max()),
            "research_start": str(start_ts.date()),
            "training_start": str(start_ts.date()),
            "training_end_exclusive": str(test_start.date()),
            "test_start": str(test_start.date()),
            "test_end": str(max_ts.date()),
            "research_months": RESEARCH_MONTHS,
            "training_months": RESEARCH_MONTHS - TEST_MONTHS,
            "test_months": TEST_MONTHS,
        },
        "banknifty_filter_source": str(find_banknifty_source()) if find_banknifty_source() else None,
        "unavailable_variants": unavailable_variants,
        "selected_variant_from_training_only": best_variant,
        "outputs": {
            "summary": str(summary_path),
            "trades": str(trades_path),
            "failures": str(failures_path),
            "report": str(report_path),
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    selected_train = summary[(summary["variant"] == best_variant) & (summary["set_name"] == "train")]
    selected_test = summary[(summary["variant"] == best_variant) & (summary["set_name"] == "test")]
    report = build_markdown_report(metadata, selected_train, selected_test, summary, failures)
    report_path.write_text(report, encoding="utf-8")

    return {
        "metadata": metadata,
        "summary": summary,
        "trades": trades_df,
        "failures": failures,
    }


def build_markdown_report(
    metadata: dict,
    selected_train: pd.DataFrame,
    selected_test: pd.DataFrame,
    summary: pd.DataFrame,
    failures: pd.DataFrame,
) -> str:
    best = metadata["selected_variant_from_training_only"]
    lines = [
        "# SBIN SMC Strategy Research",
        "",
        "## Data Split",
        f"- Research window: {metadata['data_range']['research_start']} to {metadata['data_range']['test_end']} "
        f"({metadata['data_range']['research_months']} months)",
        f"- Training: {metadata['data_range']['training_start']} to {metadata['data_range']['training_end_exclusive']} "
        f"(exclusive end, {metadata['data_range']['training_months']} months)",
        f"- Out-of-sample test: {metadata['data_range']['test_start']} to {metadata['data_range']['test_end']} "
        f"({metadata['data_range']['test_months']} months)",
        f"- Bank Nifty VWAP filter source: {metadata['banknifty_filter_source'] or 'not available locally'}",
        "",
        "## Selected Variant",
        f"- Selected from training only: {best or 'none'}",
        "",
        "## Mechanical Rules",
        "- Detect a bullish sweep when price trades below the selected liquidity level and closes back above it; bearish is the mirror image.",
        "- Liquidity level is either previous-day high/low or the opening 09:15-09:30 range high/low.",
        "- Setup window is 09:30-11:30 IST. Entry must happen by 12:00 IST.",
        "- A 5-minute displacement candle must follow the sweep within six 5-minute bars and must include a 5m or same-window 1m FVG.",
        "- The 5m order block is the last opposite-color candle before displacement.",
        "- Direct OB entry uses a limit order at the midpoint of the 5m order block, valid for 40 minutes.",
        "- 1m MSS entry uses a market entry on a 1m close beyond the prior five 1m candles, with a same-candle 1m FVG.",
        "- Stop goes beyond the swept extreme and order-block edge, plus Rs 0.05 buffer. Trade is skipped if stop exceeds 0.8% of entry price.",
        "- Target is exactly 2R. If neither stop nor target hits, exit at 15:15 IST.",
        "- Once price reaches +1R, stop is moved to breakeven. This was added from training-set failure analysis because many losers first reached about +1R, then reversed.",
        "- Higher timeframe bias comes from 15m and 1h structure breaks. A trade is blocked only if both HTFs point against it.",
        "",
        "## Selected Variant Metrics",
    ]
    if not selected_train.empty:
        train = selected_train.iloc[0].to_dict()
        lines.append(
        f"- Training: trades={train['trades']}, win_rate={train['win_rate']:.2f}%, "
        f"decisive_win_rate={train['decisive_win_rate']:.2f}%, "
        f"PF={train['profit_factor']}, expectancy={train['expectancy_r']:.3f}R, "
        f"max_drawdown={train['max_drawdown_r']:.2f}R, breakevens={train['breakevens']}"
        )
    if not selected_test.empty:
        test = selected_test.iloc[0].to_dict()
        lines.append(
            f"- Test: trades={test['trades']}, win_rate={test['win_rate']:.2f}%, "
            f"decisive_win_rate={test['decisive_win_rate']:.2f}%, "
            f"PF={test['profit_factor']}, expectancy={test['expectancy_r']:.3f}R, "
            f"max_drawdown={test['max_drawdown_r']:.2f}R, breakevens={test['breakevens']}"
        )

    lines.extend(["", "## All Variant Summary"])
    display_cols = [
        "variant",
        "set_name",
        "available",
        "trades",
        "win_rate",
        "decisive_win_rate",
        "profit_factor",
        "expectancy_r",
        "max_drawdown_r",
        "breakevens",
        "losses",
    ]
    lines.append(markdown_table(summary[display_cols]))

    lines.extend(["", "## Losing Trade Breakdown"])
    if failures.empty:
        lines.append("No stop-loss exits for the selected variant.")
    else:
        lines.append(markdown_table(failures))

    return "\n".join(lines) + "\n"


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"

    def fmt(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.4f}".rstrip("0").rstrip(".")
        text = str(value)
        return text.replace("|", "\\|")

    columns = list(df.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join(fmt(row[col]) for col in columns) + " |" for _, row in df.iterrows()]
    return "\n".join([header, separator, *rows])


if __name__ == "__main__":
    result = run_research()
    metadata = result["metadata"]
    summary = result["summary"]
    print(f"SBIN SMC research complete: {metadata['outputs']['report']}")
    print(f"Selected variant: {metadata['selected_variant_from_training_only']}")
    selected = summary[summary["variant"] == metadata["selected_variant_from_training_only"]]
    if not selected.empty:
        print(selected[["set_name", "trades", "win_rate", "profit_factor", "expectancy_r", "max_drawdown_r"]].to_string(index=False))
