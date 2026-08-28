from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from time import sleep
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

import Actions as Main

from .candle_builder import Candle
from .csv_store import CandleCsvStore, RollingDerivedTimeframes, read_csv_tail

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN_TIME = time(9, 15)
MARKET_CLOSE_TIME = time(15, 29)
MAX_ZERO_VOLUME_BACKFILL_MINUTES = 30


class BackfillError(RuntimeError):
    pass


@dataclass(frozen=True)
class StartupPlan:
    phase: str
    stream_live: bool
    fetch_end: datetime | None
    wait_until: datetime | None
    require_fetch_end: bool
    prompt: str


@dataclass(frozen=True)
class BackfillResult:
    appended_rows: int
    requested_start: datetime | None
    requested_end: datetime | None
    baseline_cumulative_volume: int | None
    message: str


def build_startup_plan(
    *,
    now: datetime | None = None,
    market_is_open: bool | None = None,
    settle_seconds: int = 2,
) -> StartupPlan:
    current = (now or datetime.now(IST)).astimezone(IST).replace(tzinfo=None)
    settle_seconds = max(0, int(settle_seconds))
    market_open = current.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = current.replace(hour=15, minute=29, second=0, microsecond=0)

    if current < market_open:
        return StartupPlan(
            phase="BEFORE_OPEN",
            stream_live=True,
            fetch_end=current,
            wait_until=None,
            require_fetch_end=False,
            prompt=(
                "Market has not opened yet. Will repair previous candle gaps, "
                "then wait on websocket for the 09:15 tick stream."
            ),
        )

    if current > market_close + timedelta(seconds=settle_seconds):
        return StartupPlan(
            phase="AFTER_CLOSE",
            stream_live=False,
            fetch_end=market_close,
            wait_until=None,
            require_fetch_end=False,
            prompt="Market is past close. Will reconcile candle CSVs and exit without opening live tick stream.",
        )

    if market_is_open is False:
        return StartupPlan(
            phase="MARKET_CLOSED_AT_MARKET_TIME",
            stream_live=False,
            fetch_end=current,
            wait_until=None,
            require_fetch_end=False,
            prompt=(
                "FYERS reports the market is closed during normal market hours. "
                "Will reconcile available history and exit without live streaming."
            ),
        )

    wait_until = current.replace(second=0, microsecond=0) + timedelta(
        minutes=1, seconds=settle_seconds
    )
    target_end = wait_until.replace(second=0, microsecond=0) - timedelta(minutes=1)
    target_end = min(target_end, market_close)
    return StartupPlan(
        phase="MARKET_OPEN",
        stream_live=True,
        fetch_end=target_end,
        wait_until=wait_until,
        require_fetch_end=True,
        prompt=(
            f"Market is open. Capturing raw ticks now, waiting until {wait_until.time()} "
            f"to backfill through the safely closed {target_end.time()} candle."
        ),
    )


def latest_completed_market_minute(now: datetime | None = None) -> datetime | None:
    current = (now or datetime.now(IST)).astimezone(IST).replace(tzinfo=None)
    market_open = current.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = current.replace(hour=15, minute=29, second=0, microsecond=0)
    if current < market_open + timedelta(minutes=1):
        return None
    if current >= market_close + timedelta(minutes=1):
        return market_close
    candidate = current.replace(second=0, microsecond=0) - timedelta(minutes=1)
    if candidate < market_open:
        return None
    return candidate


def run_initial_backfill(
    fyers,
    symbol: str,
    store: CandleCsvStore,
    *,
    now: datetime | None = None,
    plan: StartupPlan | None = None,
) -> BackfillResult:
    if plan is None:
        plan = build_startup_plan(now=now)
    print(f"{symbol}: {plan.prompt}")

    if plan.wait_until is not None:
        current = datetime.now(IST).replace(tzinfo=None)
        seconds_to_wait = (plan.wait_until - current).total_seconds()
        if seconds_to_wait > 0:
            sleep(seconds_to_wait)

    target_end = plan.fetch_end
    if target_end is None:
        baseline = baseline_volume_for_plan(store, plan, datetime.now(IST).replace(tzinfo=None))
        return BackfillResult(
            0, None, None, baseline, "No safe history backfill target is available yet."
        )

    last_dt = store.last_1min_datetime()
    if last_dt is None and target_end.time() < MARKET_OPEN_TIME:
        baseline = baseline_volume_for_plan(store, plan, target_end)
        return BackfillResult(
            0,
            None,
            None,
            baseline,
            "No local 1MIN CSV exists and no completed market candle is available yet.",
        )

    if last_dt is None:
        start_dt = target_end.replace(hour=9, minute=15, second=0, microsecond=0)
    elif last_dt >= target_end:
        baseline = baseline_volume_for_plan(store, plan, target_end)
        return BackfillResult(
            0, None, None, baseline, "Local 1MIN CSV already covers the safe live range."
        )
    else:
        start_dt = last_dt + timedelta(minutes=1)

    if start_dt > target_end:
        baseline = baseline_volume_for_plan(store, plan, target_end)
        return BackfillResult(0, None, None, baseline, "No backfill required.")

    fetched = fetch_history_between(fyers, symbol, start_dt, target_end)
    if fetched.empty:
        if plan.require_fetch_end or _local_state_requires_repair(last_dt, target_end):
            filled = zero_fill_history_gap(store, start_dt, target_end)
            if not filled.empty:
                append_result = store.append_raw_rows(
                    Main.TIMEFRAME_1MIN,
                    filled.to_dict("records"),
                    strict_minutes=1,
                )
                replay_derived_timeframes(
                    store, affected_replay_start(start_dt, target_end), target_end
                )
                baseline = baseline_volume_for_plan(store, plan, target_end)
                return BackfillResult(
                    append_result.rows_appended,
                    start_dt,
                    target_end,
                    baseline,
                    f"Zero-filled {append_result.rows_appended} no-trade 1MIN rows through {target_end}.",
                )
            raise BackfillError(
                f"Fyers returned no candles for required gap {start_dt} to {target_end}."
            )
        baseline = baseline_volume_for_plan(store, plan, target_end)
        return BackfillResult(
            0,
            start_dt,
            target_end,
            baseline,
            "No new history candles were available; local CSV state was left unchanged.",
        )

    fetched_start = pd.to_datetime(fetched.iloc[0]["Datetime"]).to_pydatetime()
    fetched_end = pd.to_datetime(fetched.iloc[-1]["Datetime"]).to_pydatetime()
    same_session_gap = start_dt.date() == target_end.date()
    if not same_session_gap and plan.require_fetch_end and fetched_end < target_end:
        raise BackfillError(
            f"Fyers history did not fully cover gap {start_dt} to {target_end}; "
            f"got {fetched_start} to {fetched_end}."
        )
    effective_end = (
        target_end if same_session_gap and plan.require_fetch_end else min(fetched_end, target_end)
    )
    if same_session_gap:
        fetched = fill_intraday_history_gaps(store, fetched, start_dt, effective_end)
        if fetched.empty:
            raise BackfillError(
                f"Could not fill required same-session gap {start_dt} to {effective_end}."
            )

    append_result = store.append_raw_rows(
        Main.TIMEFRAME_1MIN,
        fetched.to_dict("records"),
        strict_minutes=1,
    )
    replay_derived_timeframes(store, affected_replay_start(start_dt, effective_end), effective_end)
    baseline = baseline_volume_for_plan(store, plan, effective_end)
    return BackfillResult(
        append_result.rows_appended,
        start_dt,
        effective_end,
        baseline,
        f"Backfilled {append_result.rows_appended} 1MIN rows through {effective_end}.",
    )


def _local_state_requires_repair(last_dt: datetime | None, target_end: datetime) -> bool:
    if last_dt is None:
        return False
    if last_dt.date() == target_end.date():
        return last_dt < target_end
    return last_dt.time() < MARKET_CLOSE_TIME


def fetch_history_between(fyers, symbol: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    if end_dt < start_dt:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)

    params = {
        "symbol": normalize_fyers_symbol(symbol),
        "resolution": Main.FYERS_BASE_RESOLUTION,
        "date_format": "0",
        "range_from": int(start_dt.replace(tzinfo=IST).timestamp()),
        "range_to": int(end_dt.replace(tzinfo=IST).timestamp()),
        "cont_flag": "1",
    }
    response = fyers.history(data=params)
    if not isinstance(response, dict):
        raise BackfillError(f"Unexpected Fyers history response: {response!r}")
    if response.get("s") == "error":
        raise BackfillError(f"Fyers history error: {response}")
    candles = response.get("candles") or []
    return Main.candles_to_dataframe(candles, IST)


def normalize_fyers_symbol(symbol: str) -> str:
    return Main.resolve_fyers_symbol(symbol)


def cumulative_volume_for_day(path: str | Path, day) -> int | None:
    end_dt = datetime.combine(day, time(23, 59, 59))
    return cumulative_volume_until(path, end_dt)


def cumulative_volume_until(path: str | Path, end_dt: datetime) -> int | None:
    file_path = Path(path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return None

    total = 0
    found = False
    for chunk in pd.read_csv(
        file_path, usecols=["Datetime", "Volume"], parse_dates=["Datetime"], chunksize=100_000
    ):
        rows = chunk[(chunk["Datetime"].dt.date == end_dt.date()) & (chunk["Datetime"] <= end_dt)]
        if not rows.empty:
            total += pd.to_numeric(rows["Volume"], errors="coerce").fillna(0).astype(int).sum()
            found = True
    return int(total) if found else None


def baseline_volume_for_plan(
    store: CandleCsvStore, plan: StartupPlan, end_dt: datetime
) -> int | None:
    if plan.phase == "BEFORE_OPEN":
        return 0
    return cumulative_volume_until(store.path(Main.TIMEFRAME_1MIN), end_dt)


def last_1min_close(store: CandleCsvStore) -> float | None:
    tail = read_csv_tail(store.path(Main.TIMEFRAME_1MIN), 1)
    if tail.empty:
        return None
    close = pd.to_numeric(tail.iloc[-1]["Close"], errors="coerce")
    if pd.isna(close):
        return None
    return float(close)


def zero_fill_history_gap(
    store: CandleCsvStore, start_dt: datetime, end_dt: datetime
) -> pd.DataFrame:
    if start_dt.date() != end_dt.date():
        return pd.DataFrame(columns=Main.RAW_COLUMNS)
    minute_count = int((end_dt - start_dt).total_seconds() // 60) + 1
    if minute_count <= 0 or minute_count > MAX_ZERO_VOLUME_BACKFILL_MINUTES:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)
    previous_close = last_1min_close(store)
    if previous_close is None:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)
    return flat_minutes(start_dt, end_dt, previous_close)


def fill_intraday_history_gaps(
    store: CandleCsvStore,
    fetched: pd.DataFrame,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    normalized = Main.normalize_candles(fetched)
    if start_dt.date() != end_dt.date():
        return normalized

    by_datetime = {
        pd.to_datetime(row.Datetime).to_pydatetime(): row
        for row in normalized.itertuples(index=False)
        if start_dt <= pd.to_datetime(row.Datetime).to_pydatetime() <= end_dt
    }
    previous_close = last_1min_close(store)
    rows = []
    missing_rows = 0
    current = start_dt
    while current <= end_dt:
        row = by_datetime.get(current)
        if row is None:
            if previous_close is None:
                return pd.DataFrame(columns=Main.RAW_COLUMNS)
            rows.append(flat_minute(current, previous_close))
            missing_rows += 1
        else:
            rows.append(
                {
                    "Datetime": current,
                    "Open": float(row.Open),
                    "High": float(row.High),
                    "Low": float(row.Low),
                    "Close": float(row.Close),
                    "Volume": int(row.Volume),
                }
            )
            previous_close = float(row.Close)
        current += timedelta(minutes=1)

    if missing_rows > MAX_ZERO_VOLUME_BACKFILL_MINUTES:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)
    return Main.normalize_candles(pd.DataFrame(rows, columns=Main.RAW_COLUMNS))


def flat_minutes(start_dt: datetime, end_dt: datetime, close: float) -> pd.DataFrame:
    rows = []
    current = start_dt
    while current <= end_dt:
        rows.append(flat_minute(current, close))
        current += timedelta(minutes=1)
    return Main.normalize_candles(pd.DataFrame(rows, columns=Main.RAW_COLUMNS))


def flat_minute(dt: datetime, close: float) -> dict[str, Any]:
    price = round(float(close), 2)
    return {
        "Datetime": dt,
        "Open": price,
        "High": price,
        "Low": price,
        "Close": price,
        "Volume": 0,
    }


def affected_replay_start(start_dt: datetime, end_dt: datetime) -> datetime:
    replay_start = floor_intraday_bucket(start_dt, 15)
    if end_dt.time() >= MARKET_CLOSE_TIME:
        replay_start = min(replay_start, end_dt.replace(hour=9, minute=15, second=0, microsecond=0))
        if end_dt.weekday() == 4:
            replay_start = min(replay_start, end_dt - timedelta(days=7))
            replay_start = replay_start.replace(hour=9, minute=15, second=0, microsecond=0)
    return replay_start


def floor_intraday_bucket(dt: datetime, minutes: int) -> datetime:
    market_open_minutes = 9 * 60 + 15
    total_minutes = dt.hour * 60 + dt.minute
    bucket_offset = ((total_minutes - market_open_minutes) // minutes) * minutes
    bucket_minutes = market_open_minutes + bucket_offset
    return dt.replace(
        hour=bucket_minutes // 60, minute=bucket_minutes % 60, second=0, microsecond=0
    )


def replay_derived_timeframes(store: CandleCsvStore, start_dt: datetime, end_dt: datetime) -> None:
    df = load_1min_between(store.path(Main.TIMEFRAME_1MIN), start_dt, end_dt)
    if df.empty:
        return

    derived = RollingDerivedTimeframes(store)
    for row in df.itertuples(index=False):
        candle = Candle(
            datetime=pd.to_datetime(row.Datetime).to_pydatetime(),
            open=float(row.Open),
            high=float(row.High),
            low=float(row.Low),
            close=float(row.Close),
            volume=int(row.Volume),
            tick_count=0,
        )
        derived.process_1min_candle(candle)
    derived.flush_completed()


def load_1min_between(path: str | Path, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)

    parts = []
    for chunk in pd.read_csv(file_path, parse_dates=["Datetime"], chunksize=100_000):
        rows = chunk[(chunk["Datetime"] >= start_dt) & (chunk["Datetime"] <= end_dt)]
        if not rows.empty:
            parts.append(rows[Main.RAW_COLUMNS])
    if not parts:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)
    return Main.normalize_candles(pd.concat(parts, ignore_index=True))
