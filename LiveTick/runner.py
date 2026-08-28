from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any

import Actions as Main

from .backfill import build_startup_plan, run_initial_backfill
from .csv_store import CandleCsvStore
from .live_tick import DEFAULT_DATA_TYPE, LiveTickClient
from .pipeline import LiveTickPipeline
from .session import RuntimeSession
from .tick_store import TickJsonlStore

EXPECTED_CONTROL_TYPES = {"cn", "ful", "sub", "unsub"}
EXPECTED_TICK_TYPES = {"sf", "if"}


class LiveTickSession:
    def __init__(
        self,
        symbol: str,
        *,
        output_folder: str | Path = "./Data",
        tick_root: str | Path = "./TickData",
        data_type: str = DEFAULT_DATA_TYPE,
        litemode: bool = False,
        write_to_file: bool = False,
        log_path: str = "",
        on_tick: Callable[[Any], None] | None = None,
    ) -> None:
        self.symbol = symbol.strip().upper()
        self.output_folder = Path(output_folder)
        self.tick_root = Path(tick_root)
        self.data_type = data_type
        self.litemode = litemode
        self.write_to_file = write_to_file
        self.log_path = log_path
        self.on_tick = on_tick
        self.store = CandleCsvStore(self.symbol, self.output_folder)
        self.tick_store = TickJsonlStore(self.symbol, self.tick_root)
        self.client: LiveTickClient | None = None
        self.pipeline: LiveTickPipeline | None = None
        self._backfill_thread: Thread | None = None
        self._stop_event = Event()
        self._fatal_error: BaseException | None = None
        self.runtime_session: RuntimeSession | None = None

    def start(self):
        metadata = {"symbols": [self.symbol], "data_type": self.data_type}
        with RuntimeSession("live_tick", metadata=metadata, on_stop_requested=self.stop) as session:
            self.runtime_session = session
            fyers = Main.login()
            market_is_open = _market_is_open(fyers)
            plan = build_startup_plan(market_is_open=market_is_open)

            if not plan.stream_live:
                result = run_initial_backfill(fyers, self.symbol, self.store, plan=plan)
                print(f"{self.symbol}: {result.message}")
                return result

            def on_fatal(error: BaseException) -> None:
                self._fatal_error = error
                if self.runtime_session is not None:
                    self.runtime_session.update(status="fatal")
                self._stop_event.set()
                if self.client is not None:
                    self.client.close()

            self.pipeline = LiveTickPipeline(
                self.symbol,
                store=self.store,
                tick_store=self.tick_store,
                on_fatal_error=on_fatal,
            )
            self.pipeline.start()
            self._backfill_thread = Thread(
                target=self._run_backfill,
                args=(fyers, plan),
                name=f"LiveTickBackfill-{self.symbol}",
                daemon=True,
            )
            self._backfill_thread.start()

            def handle_tick(message: Any) -> None:
                if self.on_tick is not None:
                    self.on_tick(message)
                assert self.pipeline is not None
                self.pipeline.on_message(message)

            self.client = LiveTickClient(
                data_type=self.data_type,
                litemode=self.litemode,
                write_to_file=self.write_to_file,
                log_path=self.log_path,
                on_tick=handle_tick,
            )
            self.client.subscribe(self.symbol, self.data_type)
            try:
                self.client.connect()
                self._wait_until_stopped()
                if self._fatal_error is not None:
                    raise self._fatal_error
            except KeyboardInterrupt:
                print("LiveTick interrupted by user.")
                self.stop()
                raise
            except Exception:
                self.stop()
                raise
            finally:
                self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        if self.client is not None:
            self.client.close()
        if self.pipeline is not None:
            self.pipeline.stop()
            self.pipeline.join(timeout=5)

    def _wait_until_stopped(self) -> None:
        while not self._stop_event.wait(1):
            pass

    def _run_backfill(self, fyers, plan) -> None:
        assert self.pipeline is not None
        try:
            result = run_initial_backfill(fyers, self.symbol, self.store, plan=plan)
            print(f"{self.symbol}: {result.message}")
            seed_end = result.requested_end or plan.fetch_end
            self.pipeline.seed_derived_from_csv(seed_end)
            self.pipeline.mark_ready(
                result.baseline_cumulative_volume,
                drop_first_partial_bucket=False,
            )
            print(f"{self.symbol}: live candle builder is READY.")
        except Exception as exc:
            self.pipeline.stop(exc)


class LiveTickMultiSession:
    def __init__(
        self,
        symbols: Sequence[str],
        *,
        output_folder: str | Path = "./Data",
        tick_root: str | Path = "./TickData",
        data_type: str = DEFAULT_DATA_TYPE,
        litemode: bool = False,
        write_to_file: bool = False,
        log_path: str = "",
        on_tick: Callable[[Any], None] | None = None,
    ) -> None:
        cleaned_symbols = tuple(dict.fromkeys(_symbol_key(symbol) for symbol in symbols))
        if not cleaned_symbols:
            raise ValueError("At least one symbol is required")

        self.symbols = cleaned_symbols
        self.output_folder = Path(output_folder)
        self.tick_root = Path(tick_root)
        self.data_type = data_type
        self.litemode = litemode
        self.write_to_file = write_to_file
        self.log_path = log_path
        self.on_tick = on_tick
        self.client: LiveTickClient | None = None
        self.stores: dict[str, CandleCsvStore] = {}
        self.tick_stores: dict[str, TickJsonlStore] = {}
        self.pipelines: dict[str, LiveTickPipeline] = {}
        self._backfill_threads: list[Thread] = []
        self._unknown_payload_signatures: set[str] = set()
        self._unexpected_payload_path = self.tick_root / "_unexpected_payloads.jsonl"
        self._stop_event = Event()
        self._fatal_error: BaseException | None = None
        self.runtime_session: RuntimeSession | None = None

    def start(self):
        metadata = {"symbols": list(self.symbols), "data_type": self.data_type}
        with RuntimeSession("live_tick", metadata=metadata, on_stop_requested=self.stop) as session:
            self.runtime_session = session
            fyers = Main.login()
            market_is_open = _market_is_open(fyers)
            plan = build_startup_plan(market_is_open=market_is_open)

            self.stores = {
                symbol: CandleCsvStore(symbol, self.output_folder) for symbol in self.symbols
            }

            if not plan.stream_live:
                results = {}
                for symbol in self.symbols:
                    result = run_initial_backfill(fyers, symbol, self.stores[symbol], plan=plan)
                    print(f"{symbol}: {result.message}")
                    results[symbol] = result
                return results

            def on_fatal(error: BaseException) -> None:
                self._fatal_error = error
                print(f"LiveTick fatal pipeline error; stopping socket: {error}")
                if self.runtime_session is not None:
                    self.runtime_session.update(status="fatal")
                self._stop_event.set()
                if self.client is not None:
                    self.client.close()

            self.tick_stores = {
                symbol: TickJsonlStore(symbol, self.tick_root) for symbol in self.symbols
            }
            self.pipelines = {
                symbol: LiveTickPipeline(
                    symbol,
                    store=self.stores[symbol],
                    tick_store=self.tick_stores[symbol],
                    on_fatal_error=on_fatal,
                )
                for symbol in self.symbols
            }
            for pipeline in self.pipelines.values():
                pipeline.start()

            for symbol in self.symbols:
                thread = Thread(
                    target=self._run_backfill,
                    args=(fyers, plan, symbol),
                    name=f"LiveTickBackfill-{symbol}",
                    daemon=True,
                )
                thread.start()
                self._backfill_threads.append(thread)

            self.client = LiveTickClient(
                data_type=self.data_type,
                litemode=self.litemode,
                write_to_file=self.write_to_file,
                log_path=self.log_path,
                on_tick=self._handle_message,
            )
            for symbol in self.symbols:
                self.client.subscribe(symbol, self.data_type)

            try:
                self.client.connect()
                self._wait_until_stopped()
                if self._fatal_error is not None:
                    raise self._fatal_error
            except KeyboardInterrupt:
                print("LiveTick interrupted by user.")
                self.stop()
                raise
            except Exception:
                self.stop()
                raise
            finally:
                self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        if self.client is not None:
            self.client.close()
        for pipeline in self.pipelines.values():
            pipeline.stop()
        for pipeline in self.pipelines.values():
            pipeline.join(timeout=5)

    def _wait_until_stopped(self) -> None:
        while not self._stop_event.wait(1):
            pass

    def _run_backfill(self, fyers, plan, symbol: str) -> None:
        pipeline = self.pipelines[symbol]
        try:
            result = run_initial_backfill(fyers, symbol, self.stores[symbol], plan=plan)
            print(f"{symbol}: {result.message}")
            seed_end = result.requested_end or plan.fetch_end
            pipeline.seed_derived_from_csv(seed_end)
            pipeline.mark_ready(
                result.baseline_cumulative_volume,
                drop_first_partial_bucket=False,
            )
            print(f"{symbol}: live candle builder is READY.")
        except Exception as exc:
            pipeline.stop(exc)

    def _handle_message(self, message: Any) -> None:
        if self.on_tick is not None:
            self.on_tick(message)

        symbol = _message_symbol_key(message)
        if symbol in self.pipelines:
            self.pipelines[symbol].on_message(message)
            return

        self._report_unexpected_payload(message, symbol)

        if symbol is None:
            for pipeline in self.pipelines.values():
                pipeline.on_message(message)

    def _report_unexpected_payload(self, message: Any, symbol: str | None) -> None:
        message_type = _message_type(message)
        if symbol is None and message_type in EXPECTED_CONTROL_TYPES:
            return
        if symbol in self.pipelines and message_type in EXPECTED_TICK_TYPES:
            return

        signature = f"{message_type}|{symbol}|{_payload_keys(message)}"
        if signature in self._unknown_payload_signatures:
            return
        self._unknown_payload_signatures.add(signature)
        self._persist_unexpected_payload(message, message_type, symbol)
        print(f"Unexpected live payload routed for review: {message}")

    def _persist_unexpected_payload(
        self, message: Any, message_type: str | None, symbol: str | None
    ) -> None:
        self._unexpected_payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "stored_at": datetime.now().isoformat(sep=" "),
            "message_type": message_type,
            "symbol": symbol,
            "payload_keys": _payload_keys(message),
            "raw": message,
        }
        with self._unexpected_payload_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str, separators=(",", ":")) + "\n")


def LiveTick(
    symbol: str | Sequence[str],
    *,
    output_folder: str | Path = "./Data",
    tick_root: str | Path = "./TickData",
    data_type: str = DEFAULT_DATA_TYPE,
    litemode: bool = False,
    write_to_file: bool = False,
    log_path: str = "",
    on_tick: Callable[[Any], None] | None = None,
):
    if not isinstance(symbol, str):
        session = LiveTickMultiSession(
            symbol,
            output_folder=output_folder,
            tick_root=tick_root,
            data_type=data_type,
            litemode=litemode,
            write_to_file=write_to_file,
            log_path=log_path,
            on_tick=on_tick,
        )
        return session.start()

    session = LiveTickSession(
        symbol,
        output_folder=output_folder,
        tick_root=tick_root,
        data_type=data_type,
        litemode=litemode,
        write_to_file=write_to_file,
        log_path=log_path,
        on_tick=on_tick,
    )
    return session.start()


def _symbol_key(symbol: str) -> str:
    value = str(symbol).strip().upper()
    if not value:
        raise ValueError("symbol cannot be empty")
    if ":" in value:
        value = value.split(":", 1)[1]
    if value.endswith("-EQ"):
        value = value[:-3]
    return value


def _message_symbol_key(message: Any) -> str | None:
    if isinstance(message, dict):
        for key in ("symbol", "ticker"):
            value = message.get(key)
            if value:
                return _symbol_key(str(value))
        for nested_key in ("d", "data"):
            nested = message.get(nested_key)
            nested_symbol = _message_symbol_key(nested)
            if nested_symbol:
                return nested_symbol
    elif isinstance(message, list):
        symbols = {_message_symbol_key(item) for item in message}
        symbols.discard(None)
        if len(symbols) == 1:
            return next(iter(symbols))
    return None


def _message_type(message: Any) -> str | None:
    if isinstance(message, dict):
        value = message.get("type")
        return str(value).lower() if value is not None else None
    return None


def _payload_keys(message: Any) -> str:
    if isinstance(message, dict):
        return ",".join(sorted(str(key) for key in message.keys()))
    if isinstance(message, list):
        return f"list[{len(message)}]"
    return type(message).__name__


def _market_is_open(fyers) -> bool | None:
    try:
        response = fyers.market_status()
    except Exception as exc:
        print(f"Could not read FYERS market status; using clock-based startup mode: {exc}")
        return None

    statuses = response.get("marketStatus") if isinstance(response, dict) else None
    if not isinstance(statuses, list):
        return None

    for item in statuses:
        if not isinstance(item, dict):
            continue
        exchange = item.get("exchange")
        segment = item.get("segment")
        if exchange == 10 and segment == 11:
            status = str(item.get("status", "")).upper()
            if "OPEN" in status:
                return True
            if "CLOSE" in status or "HOLIDAY" in status:
                return False

    joined = " ".join(
        str(item.get("status", "")) for item in statuses if isinstance(item, dict)
    ).upper()
    if "OPEN" in joined:
        return True
    if "CLOSE" in joined or "HOLIDAY" in joined:
        return False
    return None
