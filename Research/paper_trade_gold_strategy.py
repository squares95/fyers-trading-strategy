from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Actions as Main
from Login import login
from Strategies.G01 import Core as base, Gold as gold

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
PAPER_LOG_DIR = ROOT / "Research" / "paper_logs"


def now_ist() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)


def parse_time(value: str):
    return datetime.strptime(value, "%H:%M").time()


def is_market_session(ts: datetime) -> bool:
    if ts.weekday() >= 5:
        return False
    return parse_time(MARKET_OPEN) <= ts.time() <= parse_time(MARKET_CLOSE)


def latest_complete_minute(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0) - timedelta(minutes=1)


def state_path(symbol: str) -> Path:
    return PAPER_LOG_DIR / f"{symbol}_gold_paper_state.json"


def trades_path(symbol: str) -> Path:
    return PAPER_LOG_DIR / f"{symbol}_gold_paper_trades.csv"


def events_path(symbol: str) -> Path:
    return PAPER_LOG_DIR / f"{symbol}_gold_paper_events.csv"


def load_state(symbol: str, reset: bool = False) -> dict:
    PAPER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = state_path(symbol)
    today = now_ist().date().isoformat()
    if reset or not path.exists():
        state = {
            "symbol": symbol,
            "session_date": today,
            "started_at": now_ist().isoformat(timespec="seconds"),
            "open_position": None,
            "seen_signal_dates": [],
            "traded_dates": [],
            "last_status": "",
        }
        save_state(symbol, state)
        return state
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("session_date") != today:
        state.update(
            {
                "session_date": today,
                "started_at": now_ist().isoformat(timespec="seconds"),
                "open_position": None,
                "seen_signal_dates": [],
                "traded_dates": [],
                "last_status": "",
            }
        )
        save_state(symbol, state)
    return state


def save_state(symbol: str, state: dict) -> None:
    PAPER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    state_path(symbol).write_text(json.dumps(state, indent=2), encoding="utf-8")


def append_csv(path: Path, row: dict, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def append_event(symbol: str, event: str, message: str, extra: dict | None = None) -> None:
    row = {
        "timestamp": now_ist().isoformat(timespec="seconds"),
        "symbol": symbol,
        "event": event,
        "message": message,
    }
    if extra:
        row.update({k: str(v) for k, v in extra.items()})
    append_csv(events_path(symbol), row, list(row.keys()))


def fetch_missing_1min(fyers, symbol: str, output_folder: Path) -> tuple[pd.DataFrame, int, str]:
    path = Path(Main.base_1min_input_path(symbol, str(output_folder)))
    existing = Main.read_existing_candles(str(path))
    if existing.empty:
        return existing, 0, f"{path} has no existing 1MIN data; run download first."

    start_dt = existing["Datetime"].max() + timedelta(minutes=1)
    end_dt = latest_complete_minute(now_ist())
    if start_dt > end_dt:
        return existing, 0, "Local 1MIN data is already current enough."

    params = {
        "symbol": f"NSE:{symbol}-EQ",
        "resolution": Main.FYERS_BASE_RESOLUTION,
        "date_format": "0",
        "range_from": str(int(start_dt.replace(tzinfo=IST).timestamp())),
        "range_to": str(int(end_dt.replace(tzinfo=IST).timestamp())),
        "cont_flag": "1",
    }
    response = fyers.history(data=params)
    if not isinstance(response, dict):
        return existing, 0, f"Unexpected FYERS response: {response}"
    if response.get("s") == "error":
        return existing, 0, f"FYERS error: {response}"

    new_df = Main.candles_to_dataframe(response.get("candles") or [], IST)
    if new_df.empty:
        return existing, 0, "FYERS returned no new candles."

    merged = Main.normalize_candles(pd.concat([existing, new_df], ignore_index=True))
    # Keep the source file usable by the rest of the project without refreshing
    # every derived timeframe on each paper-trading poll.
    Main.add_indicators(merged).to_csv(path, index=False)
    return merged, len(new_df), f"Fetched {len(new_df)} new 1MIN candles."


def complete_5min_from_1min(df_1m: pd.DataFrame) -> pd.DataFrame:
    df = Main.normalize_candles(df_1m)
    if df.empty:
        return df
    open_time = parse_time("09:15")
    close_time = parse_time("15:29")
    df = df[(df["Datetime"].dt.time >= open_time) & (df["Datetime"].dt.time <= close_time)].copy()
    open_minutes = open_time.hour * 60 + open_time.minute
    minutes = df["Datetime"].dt.hour * 60 + df["Datetime"].dt.minute
    df["_date"] = df["Datetime"].dt.date
    df["_bucket"] = ((minutes - open_minutes) // 5).astype(int)
    grouped = df.groupby(["_date", "_bucket"], sort=True)
    bars = grouped.agg(
        Datetime=("Datetime", "first"),
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
        _count=("Datetime", "count"),
    ).reset_index(drop=True)
    bars = bars[bars["_count"] == 5].drop(columns=["_count"])
    return Main.add_indicators(Main.normalize_candles(bars))


def prepare_live_features(df_5m: pd.DataFrame) -> pd.DataFrame:
    df = df_5m.sort_values("Datetime").reset_index(drop=True).copy()
    df["date"] = df["Datetime"].dt.date.astype(str)
    df["time"] = df["Datetime"].dt.strftime("%H:%M")
    df["bar_no"] = df.groupby("date").cumcount()

    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    df["vwap"] = (typical * df["Volume"]).groupby(df["date"]).cumsum() / df["Volume"].groupby(
        df["date"]
    ).cumsum()
    for span in (13, 21, 34, 55):
        df[f"ema{span}"] = base.ema(df["Close"], span)
    df["rsi14"] = base.rsi(df["Close"], 14)
    df["atr14"] = base.atr(df, 14)
    df["adx_for_signal"] = df["ADX"] if "ADX" in df.columns else np.nan
    df["vol_avg20_samebar"] = df.groupby("bar_no")["Volume"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=5).mean()
    )
    df["vol_ratio20"] = df["Volume"] / df["vol_avg20_samebar"]
    df["prev_close"] = df["Close"].shift(1)
    return df


def current_final_signal(df: pd.DataFrame) -> pd.Series | None:
    today = now_ist().date().isoformat()
    regime = gold.daily_regime_table(df)
    tradeable_dates = set(regime.loc[regime["regime_tradeable"], "date"])
    if today not in tradeable_dates:
        return None

    signals = base.generate_signals(df, gold.GOLD_CONFIG)
    signals = signals[signals["date"].isin(tradeable_dates)].copy()
    if signals.empty:
        return None

    strength = gold.signal_strength_table(df, signals, gold.GOLD_CONFIG)
    final = strength[
        (strength["signal_strength"] >= gold.MIN_SIGNAL_STRENGTH)
        & (strength["strength_trigger_component"] >= gold.MIN_TRIGGER_COMPONENT)
    ].copy()
    final = final[final["date"] == today]
    if final.empty:
        return None
    return final.iloc[0]


def open_position_from_signal(symbol: str, signal: pd.Series) -> dict:
    return {
        "symbol": symbol,
        "date": str(signal["date"]),
        "direction": int(signal["direction"]),
        "signal_time": pd.Timestamp(signal["Datetime"]).isoformat(),
        "entry_time": pd.Timestamp(signal["entry_time"]).isoformat(),
        "entry": float(signal["entry"]),
        "stop": float(signal["stop"]),
        "target": float(signal["target"]),
        "stop_distance": float(signal["stop_distance"]),
        "signal_strength": float(signal["signal_strength"]),
        "strength_band": str(signal["strength_band"]),
    }


def check_exit(symbol: str, position: dict, df_1m: pd.DataFrame) -> tuple[dict | None, str]:
    entry_time = pd.Timestamp(position["entry_time"]).to_pydatetime()
    after_entry = df_1m[df_1m["Datetime"] >= entry_time].copy()
    if after_entry.empty:
        return None, "Waiting for candles after entry."

    direction = int(position["direction"])
    stop = float(position["stop"])
    target = float(position["target"])
    entry = float(position["entry"])
    exit_price = float(after_entry.iloc[-1]["Close"])
    exit_time = pd.Timestamp(after_entry.iloc[-1]["Datetime"])
    exit_reason = None

    for row in after_entry.itertuples(index=False):
        if direction == 1:
            stop_hit = float(row.Low) <= stop
            target_hit = float(row.High) >= target
        else:
            stop_hit = float(row.High) >= stop
            target_hit = float(row.Low) <= target
        if stop_hit and target_hit:
            exit_price = stop
            exit_time = pd.Timestamp(row.Datetime)
            exit_reason = "stop_same_minute"
            break
        if stop_hit:
            exit_price = stop
            exit_time = pd.Timestamp(row.Datetime)
            exit_reason = "stop"
            break
        if target_hit:
            exit_price = target
            exit_time = pd.Timestamp(row.Datetime)
            exit_reason = "target"
            break

    if exit_reason is None and now_ist().time() >= parse_time("15:25"):
        exit_reason = "eod"

    if exit_reason is None:
        return None, "Position open; stop/target not hit."

    gross_return = direction * (exit_price / entry - 1)
    net_return = gross_return - (2 * gold.GOLD_CONFIG.cost_bps_per_side / 10000)
    exit_row = {
        **position,
        "exit_time": exit_time.isoformat(),
        "exit": round(exit_price, 4),
        "exit_reason": exit_reason,
        "gross_return_pct": round(gross_return * 100, 4),
        "net_return_pct": round(net_return * 100, 4),
    }
    return exit_row, f"Paper exit: {exit_reason}, net {net_return * 100:.2f}%."


def run_once(symbol: str, output_folder: Path, reset: bool = False) -> str:
    state = load_state(symbol, reset=reset)
    fyers = login()
    df_1m, fetched_rows, fetch_msg = fetch_missing_1min(fyers, symbol, output_folder)
    append_event(symbol, "FETCH", fetch_msg, {"fetched_rows": fetched_rows})

    if df_1m.empty:
        state["last_status"] = fetch_msg
        save_state(symbol, state)
        return fetch_msg

    if state.get("open_position"):
        exit_row, exit_msg = check_exit(symbol, state["open_position"], df_1m)
        if exit_row:
            fields = list(exit_row.keys())
            append_csv(trades_path(symbol), exit_row, fields)
            append_event(symbol, "EXIT", exit_msg, exit_row)
            state["open_position"] = None
            state["traded_dates"] = sorted(set(state.get("traded_dates", []) + [exit_row["date"]]))
        state["last_status"] = exit_msg
        save_state(symbol, state)
        return exit_msg

    df_5m = complete_5min_from_1min(df_1m)
    live = prepare_live_features(df_5m)
    signal = current_final_signal(live)
    today = now_ist().date().isoformat()
    if signal is None:
        msg = f"No final CGPOWER gold signal for {today} yet."
        state["last_status"] = msg
        save_state(symbol, state)
        append_event(symbol, "NO_SIGNAL", msg)
        return msg

    signal_time = pd.Timestamp(signal["Datetime"]).to_pydatetime()
    started_at = pd.Timestamp(state["started_at"]).to_pydatetime()
    if str(signal["date"]) in state.get("seen_signal_dates", []):
        msg = f"Signal already seen for {signal['date']}; no duplicate paper entry."
        state["last_status"] = msg
        save_state(symbol, state)
        return msg
    if signal_time < started_at - timedelta(minutes=5):
        msg = f"Found an older signal from {signal_time}; marked as missed, not entering retroactively."
        state["seen_signal_dates"] = sorted(
            set(state.get("seen_signal_dates", []) + [str(signal["date"])])
        )
        state["last_status"] = msg
        save_state(symbol, state)
        append_event(symbol, "MISSED_SIGNAL", msg, signal.to_dict())
        return msg

    position = open_position_from_signal(symbol, signal)
    state["open_position"] = position
    state["seen_signal_dates"] = sorted(
        set(state.get("seen_signal_dates", []) + [str(signal["date"])])
    )
    state["last_status"] = "Paper position opened."
    save_state(symbol, state)
    append_event(symbol, "ENTRY", "Paper position opened.", position)
    return (
        f"Paper entry opened: {'LONG' if position['direction'] == 1 else 'SHORT'} "
        f"{symbol} at {position['entry']:.2f}, stop {position['stop']:.2f}, "
        f"target {position['target']:.2f}, strength {position['signal_strength']:.1f}."
    )


def run_loop(
    symbol: str, output_folder: Path, poll_seconds: int, duration_minutes: int, reset: bool
) -> None:
    end_at = now_ist() + timedelta(minutes=duration_minutes)
    first = True
    while now_ist() <= end_at:
        current = now_ist()
        if is_market_session(current):
            try:
                status = run_once(symbol, output_folder, reset=reset and first)
                print(f"{current.isoformat(timespec='seconds')} {status}", flush=True)
            except Exception as exc:
                append_event(symbol, "ERROR", str(exc))
                print(f"{current.isoformat(timespec='seconds')} ERROR: {exc}", flush=True)
        else:
            print(f"{current.isoformat(timespec='seconds')} Market session not active.", flush=True)
        first = False
        time.sleep(max(10, poll_seconds))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Paper-trade the CGPOWER gold strategy without placing real orders."
    )
    parser.add_argument("--symbol", default="CGPOWER")
    parser.add_argument("--output-folder", default=str(ROOT / "Data" / "NSE30"))
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--duration-minutes", type=int, default=240)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    output_folder = Path(args.output_folder)
    if args.once:
        print(run_once(symbol, output_folder, reset=args.reset))
    else:
        run_loop(symbol, output_folder, args.poll_seconds, args.duration_minutes, args.reset)


if __name__ == "__main__":
    main()
