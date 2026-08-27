from __future__ import annotations

from datetime import datetime, timedelta
from queue import Full, Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .candle_builder import MARKET_CLOSE_TIME
from .candle_builder import Candle, MinuteCandleBuilder, TickRecord, extract_tick_records
from .csv_store import CandleCsvStore, DataContinuityError, RollingDerivedTimeframes, read_csv_tail
from .tick_store import TickJsonlStore


FatalCallback = Callable[[BaseException], None]
IST = ZoneInfo("Asia/Kolkata")
MAX_LIVE_ZERO_FILL_GAP_MINUTES = 30


class LiveTickPipeline:
    def __init__(
        self,
        symbol: str,
        *,
        store: CandleCsvStore,
        tick_store: TickJsonlStore,
        queue_size: int = 20_000,
        max_pending_ticks: int = 50_000,
        on_fatal_error: FatalCallback | None = None,
    ) -> None:
        self.symbol = symbol
        self.store = store
        self.tick_store = tick_store
        self.queue: Queue[tuple[str, Any]] = Queue(maxsize=max(100, int(queue_size)))
        self.max_pending_ticks = max(1_000, int(max_pending_ticks))
        self.on_fatal_error = on_fatal_error
        self.builder = MinuteCandleBuilder()
        self.derived = RollingDerivedTimeframes(store)
        self.ready = Event()
        self.stop_requested = Event()
        self._thread: Thread | None = None
        self._pending: list[TickRecord] = []
        self._pending_lock = Lock()
        self._fatal_error: BaseException | None = None
        self.messages_seen = 0
        self.ticks_seen = 0
        self.candles_appended = 0

    @property
    def fatal_error(self) -> BaseException | None:
        return self._fatal_error

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = Thread(target=self._run, name=f"LiveTickPipeline-{self.symbol}", daemon=True)
        self._thread.start()

    def stop(self, error: BaseException | None = None) -> None:
        if error is not None:
            self._set_fatal(error)
        self.stop_requested.set()
        try:
            self.queue.put_nowait(("stop", None))
        except Full:
            pass

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self.tick_store.close()

    def on_message(self, message: Any) -> None:
        if self.stop_requested.is_set():
            return
        self._enqueue("message", message)

    def mark_ready(
        self,
        baseline_cumulative_volume: int | None,
        *,
        drop_first_partial_bucket: bool | None = None,
    ) -> None:
        self.builder.set_baseline_cumulative_volume(baseline_cumulative_volume)
        if drop_first_partial_bucket is not None:
            self.builder.drop_first_partial_bucket = drop_first_partial_bucket
        self.ready.set()
        self._enqueue("flush", None)

    def seed_derived_from_csv(self, end_dt: datetime | None) -> None:
        if end_dt is None:
            return
        from .backfill import load_1min_between

        df = load_1min_between(self.store.path("1MIN"), week_seed_start(end_dt), end_dt)
        last_candle: Candle | None = None
        for row in df.itertuples(index=False):
            raw_dt = row.Datetime
            candle_dt = raw_dt.to_pydatetime() if hasattr(raw_dt, "to_pydatetime") else raw_dt
            last_candle = Candle(
                datetime=candle_dt,
                open=float(row.Open),
                high=float(row.High),
                low=float(row.Low),
                close=float(row.Close),
                volume=int(row.Volume),
                tick_count=0,
            )
            self.derived.seed_1min_candle(last_candle)
        if last_candle is not None:
            self.builder.seed_last_finalized(last_candle.datetime, last_candle.close)

    def _enqueue(self, kind: str, payload: Any) -> None:
        try:
            self.queue.put_nowait((kind, payload))
        except Full:
            self._set_fatal(RuntimeError(f"Live tick queue overflow for {self.symbol}; stopping to protect data quality."))
            self.stop_requested.set()

    def _run(self) -> None:
        while not self.stop_requested.is_set() or not self.queue.empty():
            try:
                kind, payload = self.queue.get(timeout=0.5)
            except Empty:
                try:
                    self._flush_time_closed_candles()
                except BaseException as exc:
                    self._set_fatal(exc)
                    self.stop_requested.set()
                continue

            try:
                if kind == "message":
                    self._handle_message(payload)
                elif kind == "flush":
                    self._flush_pending()
                elif kind == "stop":
                    break
            except BaseException as exc:
                self._set_fatal(exc)
                self.stop_requested.set()
            finally:
                self.queue.task_done()

    def _handle_message(self, message: Any) -> None:
        self.messages_seen += 1
        ticks = extract_tick_records(message, self.symbol)
        if not ticks:
            self.tick_store.write(message, None)
            return

        for tick in ticks:
            self.ticks_seen += 1
            self.tick_store.write(message, tick)
            if self.ready.is_set():
                self._flush_pending()
                self._process_tick(tick)
            else:
                self._hold_pending(tick)

    def _hold_pending(self, tick: TickRecord) -> None:
        with self._pending_lock:
            if len(self._pending) >= self.max_pending_ticks:
                raise RuntimeError(
                    f"Pending tick buffer exceeded {self.max_pending_ticks}; "
                    "backfill is too slow or stuck."
                )
            self._pending.append(tick)

    def _flush_pending(self) -> None:
        if not self.ready.is_set():
            return
        with self._pending_lock:
            pending = sorted(self._pending, key=lambda item: item.timestamp)
            self._pending = []
        for tick in pending:
            self._process_tick(tick)

    def _process_tick(self, tick: TickRecord) -> None:
        finalized = self.builder.process(tick)
        self._append_finalized_candles(finalized)

    def _flush_time_closed_candles(self) -> None:
        if not self.ready.is_set() or self.stop_requested.is_set():
            return
        finalized = self.builder.flush_ready(datetime.now(IST).replace(tzinfo=None))
        self._append_finalized_candles(finalized)

    def _append_finalized_candles(self, finalized: list[Candle]) -> None:
        for candle in finalized:
            gap_fill = self._repairable_gap_candles_before(candle)
            if gap_fill:
                print(
                    f"{self.symbol}: repaired {len(gap_fill)} missing 1MIN candle(s) before "
                    f"{candle.datetime.strftime('%H:%M')}",
                    flush=True,
                )
            for gap_candle in gap_fill:
                self._append_single_finalized_candle(gap_candle)
            self._append_single_finalized_candle(candle)

    def _append_single_finalized_candle(self, candle: Candle) -> None:
        result = self.store.append_1min_candles([candle])
        if result.rows_appended:
            self.candles_appended += result.rows_appended
            self.derived.process_1min_candle(candle)
            if candle.datetime.time() >= MARKET_CLOSE_TIME:
                self.derived.flush_completed()
            print(
                f"{self.symbol}  {candle.datetime.hour:02d}:{candle.datetime.minute:02d} "
                f"Open:{candle.open:.2f}  Close:{candle.close:.2f}",
                flush=True,
            )

    def _repairable_gap_candles_before(self, candle: Candle) -> list[Candle]:
        last_dt = self.store.last_1min_datetime()
        if last_dt is None or candle.datetime <= last_dt:
            return []

        expected = last_dt + timedelta(minutes=1)
        if candle.datetime == expected:
            return []

        if last_dt.date() != candle.datetime.date():
            raise DataContinuityError(
                f"{self.symbol} 1MIN overnight gap cannot be repaired live: last={last_dt}, next={candle.datetime}"
            )

        missing_minutes = int((candle.datetime - expected).total_seconds() // 60) + 1
        if missing_minutes <= 0:
            return []
        if missing_minutes > MAX_LIVE_ZERO_FILL_GAP_MINUTES:
            raise DataContinuityError(
                f"{self.symbol} 1MIN live gap too large to zero-fill safely: "
                f"last={last_dt}, next={candle.datetime}, missing={missing_minutes}"
            )

        previous_close = self._last_saved_close()
        if previous_close is None:
            raise DataContinuityError(
                f"{self.symbol} 1MIN gap cannot be repaired because last saved close is unavailable: "
                f"last={last_dt}, next={candle.datetime}"
            )

        gap_candles = []
        close = round(previous_close, 2)
        bucket = expected
        while bucket < candle.datetime:
            gap_candles.append(
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
            bucket += timedelta(minutes=1)
        return gap_candles

    def _last_saved_close(self) -> float | None:
        tail = read_csv_tail(self.store.path("1MIN"), 1)
        if tail.empty:
            return None
        close = tail.iloc[-1].get("Close")
        try:
            return float(close)
        except (TypeError, ValueError):
            return None

    def _set_fatal(self, error: BaseException) -> None:
        if self._fatal_error is not None:
            return
        self._fatal_error = error
        if isinstance(error, DataContinuityError):
            print(f"{self.symbol}: data continuity failure: {error}")
        else:
            print(f"{self.symbol}: live pipeline stopped: {error}")
        if self.on_fatal_error is not None:
            try:
                self.on_fatal_error(error)
            except Exception as callback_error:
                print(f"{self.symbol}: fatal-error callback failed: {callback_error}")


def week_seed_start(end_dt: datetime) -> datetime:
    monday = end_dt.date() - timedelta(days=end_dt.weekday())
    return datetime.combine(monday, datetime.strptime("09:15", "%H:%M").time())
