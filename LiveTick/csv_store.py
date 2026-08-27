from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

import Actions as Main
from .candle_builder import Candle


class DataContinuityError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppendResult:
    timeframe: str
    rows_appended: int
    first_datetime: datetime | None
    last_datetime: datetime | None


def read_csv_tail(path: str | Path, rows: int) -> pd.DataFrame:
    file_path = Path(path)
    if rows <= 0 or not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame(columns=Main.FINAL_COLUMNS)

    with file_path.open("rb") as handle:
        header = handle.readline().decode("utf-8").strip()
        if not header:
            return pd.DataFrame(columns=Main.FINAL_COLUMNS)

        handle.seek(0, 2)
        file_size = handle.tell()
        block_size = 8192
        data = b""
        position = file_size
        line_count = 0
        while position > 0 and line_count <= rows:
            read_size = min(block_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            data = chunk + data
            line_count = data.count(b"\n")

    lines = data.splitlines()
    if lines and lines[0].decode("utf-8", errors="ignore").strip() == header:
        lines = lines[1:]
    tail_lines = [line.decode("utf-8") for line in lines[-rows:] if line.strip()]
    if not tail_lines:
        return pd.DataFrame(columns=Main.FINAL_COLUMNS)
    return pd.read_csv(StringIO(header + "\n" + "\n".join(tail_lines)), parse_dates=["Datetime"])


def _normalize_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if ":" in value:
        value = value.split(":", 1)[1]
    return value.replace("-EQ", "")


def _timeframe_path(symbol: str, output_folder: str | Path, timeframe: str) -> Path:
    clean = _normalize_symbol(symbol)
    return Path(output_folder) / clean / f"{clean}_{timeframe}.csv"


def _ensure_raw_dataframe(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows), columns=Main.RAW_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)
    return Main.normalize_candles(df)


def _last_datetime(path: Path) -> datetime | None:
    tail = read_csv_tail(path, 1)
    if tail.empty:
        return None
    return pd.to_datetime(tail.iloc[-1]["Datetime"]).to_pydatetime()


def _is_allowed_datetime_jump(last_dt: datetime, next_dt: datetime, minutes: int) -> bool:
    if next_dt <= last_dt:
        return False
    if last_dt.date() == next_dt.date():
        return next_dt == last_dt + timedelta(minutes=minutes)
    final_bucket_start = (datetime.combine(last_dt.date(), time(15, 29)) - timedelta(minutes=minutes - 1)).time()
    return last_dt.time() >= final_bucket_start and next_dt.time() == time(9, 15)


class CandleCsvStore:
    def __init__(
        self,
        symbol: str,
        output_folder: str | Path = "./Data",
        *,
        indicator_tail_rows: int = 250,
    ) -> None:
        self.symbol = _normalize_symbol(symbol)
        self.output_folder = Path(output_folder)
        self.symbol_folder = self.output_folder / self.symbol
        self.symbol_folder.mkdir(parents=True, exist_ok=True)
        self.indicator_tail_rows = max(50, int(indicator_tail_rows))

    def path(self, timeframe: str) -> Path:
        return _timeframe_path(self.symbol, self.output_folder, timeframe)

    def last_1min_datetime(self) -> datetime | None:
        return _last_datetime(self.path(Main.TIMEFRAME_1MIN))

    def append_1min_candles(self, candles: Iterable[Candle]) -> AppendResult:
        return self.append_raw_rows(
            Main.TIMEFRAME_1MIN,
            [candle.to_raw_row() for candle in candles],
            strict_minutes=1,
        )

    def append_timeframe_candle(self, timeframe: str, candle: Candle, strict_minutes: int | None) -> AppendResult:
        return self.append_raw_rows(timeframe, [candle.to_raw_row()], strict_minutes=strict_minutes)

    def append_raw_rows(
        self,
        timeframe: str,
        raw_rows: Iterable[dict[str, Any]],
        *,
        strict_minutes: int | None,
    ) -> AppendResult:
        path = self.path(timeframe)
        raw_df = _ensure_raw_dataframe(raw_rows)
        if raw_df.empty:
            return AppendResult(timeframe, 0, None, None)

        last_dt = _last_datetime(path)
        if last_dt is not None:
            raw_df = raw_df[raw_df["Datetime"] > last_dt].copy()
            if raw_df.empty:
                return AppendResult(timeframe, 0, None, None)
            first_dt = pd.to_datetime(raw_df.iloc[0]["Datetime"]).to_pydatetime()
            if strict_minutes is not None and not _is_allowed_datetime_jump(last_dt, first_dt, strict_minutes):
                raise DataContinuityError(
                    f"{self.symbol} {timeframe} gap detected: last={last_dt}, next={first_dt}"
                )

        final_df = self._with_indicators(path, raw_df)
        write_header = not path.exists() or path.stat().st_size == 0
        final_df.to_csv(path, mode="a", header=write_header, index=False)
        first = pd.to_datetime(final_df.iloc[0]["Datetime"]).to_pydatetime()
        last = pd.to_datetime(final_df.iloc[-1]["Datetime"]).to_pydatetime()
        return AppendResult(timeframe, len(final_df), first, last)

    def _with_indicators(self, path: Path, new_raw_df: pd.DataFrame) -> pd.DataFrame:
        tail = read_csv_tail(path, self.indicator_tail_rows)
        tail_raw = tail[Main.RAW_COLUMNS].copy() if not tail.empty else pd.DataFrame(columns=Main.RAW_COLUMNS)
        combined = Main.normalize_candles(pd.concat([tail_raw, new_raw_df], ignore_index=True))
        final = Main.add_indicators(combined, log_fn=lambda _message: None)
        return final.tail(len(new_raw_df)).reset_index(drop=True)


class RollingDerivedTimeframes:
    def __init__(self, store: CandleCsvStore) -> None:
        self.store = store
        self._intraday = {
            Main.TIMEFRAME_5MIN: _IntradayAggregator(5),
            Main.TIMEFRAME_15MIN: _IntradayAggregator(15),
        }
        self._daily = _DailyAggregator()
        self._weekly = _WeeklyAggregator()

    def process_1min_candle(self, candle: Candle) -> list[AppendResult]:
        results: list[AppendResult] = []
        for timeframe, aggregator in self._intraday.items():
            completed = aggregator.process(candle)
            if completed is not None:
                minutes = 5 if timeframe == Main.TIMEFRAME_5MIN else 15
                results.append(self.store.append_timeframe_candle(timeframe, completed, minutes))

        daily = self._daily.process(candle)
        if daily is not None:
            results.append(self.store.append_timeframe_candle(Main.TIMEFRAME_1D, daily, None))

        weekly = self._weekly.process(candle)
        if weekly is not None:
            results.append(self.store.append_timeframe_candle(Main.TIMEFRAME_1W, weekly, None))
        return results

    def seed_1min_candle(self, candle: Candle) -> None:
        for aggregator in self._intraday.values():
            aggregator.process(candle)
        self._daily.process(candle)
        self._weekly.process(candle)

    def flush_completed(self) -> list[AppendResult]:
        results: list[AppendResult] = []
        for timeframe, aggregator in self._intraday.items():
            completed = aggregator.flush_completed()
            if completed is not None:
                minutes = 5 if timeframe == Main.TIMEFRAME_5MIN else 15
                results.append(self.store.append_timeframe_candle(timeframe, completed, minutes))
        return results


class _IntradayAggregator:
    def __init__(self, minutes: int) -> None:
        self.minutes = minutes
        self._bucket_start: datetime | None = None
        self._rows: list[Candle] = []

    def process(self, candle: Candle) -> Candle | None:
        bucket = self._bucket(candle.datetime)
        completed = None
        if self._bucket_start is not None and bucket != self._bucket_start:
            completed = self._finalize()
            self._rows = []
        self._bucket_start = bucket
        self._rows.append(candle)
        return completed

    def _bucket(self, dt: datetime) -> datetime:
        market_open_minutes = 9 * 60 + 15
        minutes_from_midnight = dt.hour * 60 + dt.minute
        bucket_offset = ((minutes_from_midnight - market_open_minutes) // self.minutes) * self.minutes
        bucket_minutes = market_open_minutes + bucket_offset
        return dt.replace(hour=bucket_minutes // 60, minute=bucket_minutes % 60, second=0, microsecond=0)

    def _finalize(self) -> Candle | None:
        if not self._rows or len(self._rows) < self.minutes:
            return None
        return _aggregate_candles(self._rows)

    def flush_completed(self) -> Candle | None:
        completed = self._finalize()
        if completed is not None:
            self._rows = []
            self._bucket_start = None
        return completed


class _DailyAggregator:
    def __init__(self) -> None:
        self._date = None
        self._rows: list[Candle] = []

    def process(self, candle: Candle) -> Candle | None:
        completed = None
        if self._date is not None and candle.datetime.date() != self._date:
            completed = self._finalize()
            self._rows = []
        self._date = candle.datetime.date()
        self._rows.append(candle)
        if candle.datetime.time() >= time(15, 29):
            completed = self._finalize()
            self._rows = []
            self._date = None
        return completed

    def _finalize(self) -> Candle | None:
        if not self._rows:
            return None
        return _aggregate_candles(self._rows)


class _WeeklyAggregator:
    def __init__(self) -> None:
        self._week = None
        self._rows: list[Candle] = []

    def process(self, candle: Candle) -> Candle | None:
        week = pd.Timestamp(candle.datetime).to_period("W-FRI")
        completed = None
        if self._week is not None and week != self._week:
            completed = self._finalize()
            self._rows = []
        self._week = week
        self._rows.append(candle)
        if candle.datetime.weekday() == 4 and candle.datetime.time() >= time(15, 29):
            completed = self._finalize()
            self._rows = []
            self._week = None
        return completed

    def _finalize(self) -> Candle | None:
        if not self._rows:
            return None
        aggregate = _aggregate_candles(self._rows)
        return Candle(
            datetime=self._rows[-1].datetime,
            open=aggregate.open,
            high=aggregate.high,
            low=aggregate.low,
            close=aggregate.close,
            volume=aggregate.volume,
            tick_count=aggregate.tick_count,
        )


def _aggregate_candles(rows: list[Candle]) -> Candle:
    return Candle(
        datetime=rows[0].datetime,
        open=rows[0].open,
        high=max(row.high for row in rows),
        low=min(row.low for row in rows),
        close=rows[-1].close,
        volume=sum(row.volume for row in rows),
        tick_count=sum(row.tick_count for row in rows),
    )
