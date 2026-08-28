from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN_TIME = time(9, 15)
MARKET_CLOSE_TIME = time(15, 29)
MARKET_DATA_MESSAGE_TYPES = {"sf", "if"}
CONTROL_MESSAGE_TYPES = {"cn", "ful", "sub", "unsub", "error"}


@dataclass(frozen=True)
class TickRecord:
    symbol: str
    timestamp: datetime
    price: float
    cumulative_volume: int | None
    raw: Any

    def to_jsonable(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat(sep=" ")
        return data


@dataclass(frozen=True)
class Candle:
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    tick_count: int
    partial: bool = False

    def to_raw_row(self) -> dict[str, Any]:
        return {
            "Datetime": self.datetime,
            "Open": self.open,
            "High": self.high,
            "Low": self.low,
            "Close": self.close,
            "Volume": self.volume,
        }


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _numeric(value)
    if number is None:
        return None
    return int(number)


def _epoch_to_ist_naive(value: Any) -> datetime | None:
    epoch = _numeric(value)
    if epoch is None or epoch <= 0:
        return None
    if epoch > 10_000_000_000:
        epoch = epoch / 1000
    return datetime.fromtimestamp(epoch, tz=IST).replace(tzinfo=None)


def floor_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def is_regular_market_time(dt: datetime) -> bool:
    value = dt.time()
    return MARKET_OPEN_TIME <= value <= MARKET_CLOSE_TIME


def normalize_expected_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if ":" in value:
        return value
    return f"NSE:{value}-EQ"


def extract_tick_records(
    message: Any,
    expected_symbol: str | None = None,
    *,
    now: datetime | None = None,
) -> list[TickRecord]:
    if isinstance(message, list):
        records: list[TickRecord] = []
        for item in message:
            records.extend(extract_tick_records(item, expected_symbol, now=now))
        return records

    if not isinstance(message, dict):
        return []

    if "d" in message and isinstance(message["d"], (dict, list)):
        return extract_tick_records(message["d"], expected_symbol, now=now)

    message_type = str(message.get("type", "")).lower()
    if message_type in CONTROL_MESSAGE_TYPES:
        return []
    if message_type and message_type not in MARKET_DATA_MESSAGE_TYPES:
        return []

    symbol = str(message.get("symbol") or message.get("ticker") or "").upper()
    if expected_symbol:
        expected = normalize_expected_symbol(expected_symbol)
        if symbol and symbol != expected:
            return []
        symbol = symbol or expected
    if not symbol:
        return []

    price = None
    for key in ("ltp", "last_traded_price", "lp", "LTP"):
        price = _numeric(message.get(key))
        if price is not None:
            break
    if price is None or price <= 0:
        return []

    timestamp = None
    for key in ("last_traded_time", "exch_feed_time", "timestamp", "feed_time", "ltt"):
        timestamp = _epoch_to_ist_naive(message.get(key))
        if timestamp is not None:
            break
    if timestamp is None:
        timestamp = (now or datetime.now(IST)).replace(tzinfo=None)

    cumulative_volume = None
    for key in ("vol_traded_today", "volume_traded_today", "vtt"):
        cumulative_volume = _integer(message.get(key))
        if cumulative_volume is not None:
            break

    return [
        TickRecord(
            symbol=symbol,
            timestamp=timestamp,
            price=price,
            cumulative_volume=cumulative_volume,
            raw=message,
        )
    ]


class MinuteCandleBuilder:
    def __init__(
        self,
        *,
        baseline_cumulative_volume: int | None = None,
        drop_first_partial_bucket: bool = True,
        first_tick_grace_seconds: int = 3,
    ) -> None:
        self.previous_cumulative_volume = baseline_cumulative_volume
        self.drop_first_partial_bucket = drop_first_partial_bucket
        self.first_tick_grace_seconds = max(0, int(first_tick_grace_seconds))
        self._current: dict[str, Any] | None = None
        self._first_bucket_started = False
        self._last_finalized_bucket: datetime | None = None
        self._last_finalized_close: float | None = None
        self.ignored_out_of_order_ticks = 0
        self.ignored_off_market_ticks = 0
        self.skipped_partial_candles = 0

    def set_baseline_cumulative_volume(self, value: int | None) -> None:
        self.previous_cumulative_volume = value

    def seed_last_finalized(self, bucket: datetime, close: float) -> None:
        self._last_finalized_bucket = floor_minute(bucket)
        self._last_finalized_close = float(close)
        self._current = None

    def process(self, tick: TickRecord) -> list[Candle]:
        if not is_regular_market_time(tick.timestamp):
            self.ignored_off_market_ticks += 1
            return []

        bucket = floor_minute(tick.timestamp)
        finalized: list[Candle] = []
        if self._last_finalized_bucket is not None and bucket <= self._last_finalized_bucket:
            self.ignored_out_of_order_ticks += 1
            return finalized

        if self._current is None:
            finalized.extend(self._gap_fill_until(bucket))
            self._start_bucket(bucket, tick)
            return finalized

        current_bucket = self._current["datetime"]
        if bucket < current_bucket:
            self.ignored_out_of_order_ticks += 1
            return finalized

        if bucket > current_bucket:
            candle = self._finalize_current()
            if candle is not None:
                finalized.append(candle)
            finalized.extend(self._gap_fill_until(bucket))
            self._start_bucket(bucket, tick)
            return finalized

        self._update_current(tick)
        return finalized

    def flush(self) -> list[Candle]:
        candle = self._finalize_current()
        self._current = None
        return [candle] if candle is not None else []

    def flush_ready(self, now: datetime | None = None, settle_seconds: int = 2) -> list[Candle]:
        current = (now or datetime.now(IST)).replace(tzinfo=None)
        if self._current is None:
            latest_closed_bucket = floor_minute(
                current - timedelta(seconds=max(0, int(settle_seconds)))
            )
            latest_closed_bucket -= timedelta(minutes=1)
            if (
                self._last_finalized_bucket is None
                or latest_closed_bucket <= self._last_finalized_bucket
                or not is_regular_market_time(latest_closed_bucket)
            ):
                return []
            return self._gap_fill_until(latest_closed_bucket + timedelta(minutes=1))

        bucket_close = self._current["datetime"] + timedelta(
            minutes=1, seconds=max(0, int(settle_seconds))
        )
        if current < bucket_close:
            return []
        return self.flush()

    def _start_bucket(self, bucket: datetime, tick: TickRecord) -> None:
        unsafe = False
        if not self._first_bucket_started:
            unsafe = (
                self.drop_first_partial_bucket
                and (tick.timestamp - bucket).total_seconds() > self.first_tick_grace_seconds
            )
            self._first_bucket_started = True

        self._current = {
            "datetime": bucket,
            "open": tick.price,
            "high": tick.price,
            "low": tick.price,
            "close": tick.price,
            "volume": self._volume_delta(tick),
            "tick_count": 1,
            "partial": unsafe,
        }

    def _update_current(self, tick: TickRecord) -> None:
        assert self._current is not None
        self._current["high"] = max(self._current["high"], tick.price)
        self._current["low"] = min(self._current["low"], tick.price)
        self._current["close"] = tick.price
        self._current["volume"] += self._volume_delta(tick)
        self._current["tick_count"] += 1

    def _finalize_current(self) -> Candle | None:
        if self._current is None:
            return None
        close = round(float(self._current["close"]), 2)
        self._last_finalized_bucket = self._current["datetime"]
        self._last_finalized_close = close
        if self._current["partial"]:
            self.skipped_partial_candles += 1
            return None
        return Candle(
            datetime=self._current["datetime"],
            open=round(float(self._current["open"]), 2),
            high=round(float(self._current["high"]), 2),
            low=round(float(self._current["low"]), 2),
            close=close,
            volume=int(max(0, self._current["volume"])),
            tick_count=int(self._current["tick_count"]),
            partial=bool(self._current["partial"]),
        )

    def _gap_fill_until(self, next_bucket: datetime) -> list[Candle]:
        if self._last_finalized_bucket is None or self._last_finalized_close is None:
            return []
        if self._last_finalized_bucket.date() != next_bucket.date():
            return []

        candles: list[Candle] = []
        bucket = self._last_finalized_bucket + timedelta(minutes=1)
        close = round(float(self._last_finalized_close), 2)
        while bucket < next_bucket and is_regular_market_time(bucket):
            candles.append(
                Candle(
                    datetime=bucket,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=0,
                    tick_count=0,
                )
            )
            self._last_finalized_bucket = bucket
            self._last_finalized_close = close
            bucket += timedelta(minutes=1)
        return candles

    def _volume_delta(self, tick: TickRecord) -> int:
        cumulative = tick.cumulative_volume
        if cumulative is None:
            return 0

        previous = self.previous_cumulative_volume
        if previous is None:
            self.previous_cumulative_volume = cumulative
            return 0
        if cumulative < previous:
            return 0
        self.previous_cumulative_volume = cumulative
        return max(0, cumulative - previous)


def candles_to_rows(candles: Iterable[Candle]) -> list[dict[str, Any]]:
    return [candle.to_raw_row() for candle in candles]
