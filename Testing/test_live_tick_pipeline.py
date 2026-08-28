from __future__ import annotations

import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import Actions as Main
from LiveTick.backfill import build_startup_plan, run_initial_backfill
from LiveTick.candle_builder import Candle, MinuteCandleBuilder, TickRecord, extract_tick_records
from LiveTick.csv_store import CandleCsvStore, DataContinuityError
from LiveTick.pipeline import LiveTickPipeline
from LiveTick.session import RuntimeSession, RuntimeSessionError, load_session
from LiveTick.tick_store import TickJsonlStore
from LiveTick.validator import compare_candle_frames

IST = ZoneInfo("Asia/Kolkata")


def epoch(dt: datetime) -> int:
    return int(dt.replace(tzinfo=IST).timestamp())


def tick(symbol: str, dt: datetime, price: float, cumulative_volume: int):
    return {
        "symbol": f"NSE:{symbol}-EQ",
        "ltp": price,
        "vol_traded_today": cumulative_volume,
        "last_traded_time": epoch(dt),
        "exch_feed_time": epoch(dt),
    }


class LiveTickPipelineTests(unittest.TestCase):
    def test_runtime_session_blocks_duplicate_running_pid(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            session = RuntimeSession("live_tick", session_dir=tmp, heartbeat_seconds=1)
            session.start()
            try:
                with self.assertRaises(RuntimeSessionError):
                    RuntimeSession("live_tick", session_dir=tmp).start()
            finally:
                session.finish()

    def test_runtime_session_replaces_stale_pid(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            path = Path(tmp) / "live_tick.json"
            path.write_text(
                '{"name":"live_tick","pid":99999999,"status":"running","started_at":"old"}',
                encoding="utf-8",
            )
            session = RuntimeSession("live_tick", session_dir=tmp, heartbeat_seconds=1)
            session.start()
            try:
                state = load_session("live_tick", tmp)
                self.assertEqual(state["pid"], os.getpid())
                self.assertEqual(state["status"], "running")
            finally:
                session.finish()

    def test_startup_plan_before_open_streams_without_required_target(self):
        plan = build_startup_plan(
            now=datetime(2026, 6, 19, 8, 55, tzinfo=IST), market_is_open=False
        )

        self.assertEqual(plan.phase, "BEFORE_OPEN")
        self.assertTrue(plan.stream_live)
        self.assertFalse(plan.require_fetch_end)

    def test_startup_plan_market_open_waits_for_current_minute_close(self):
        plan = build_startup_plan(
            now=datetime(2026, 6, 19, 11, 12, 50, tzinfo=IST), market_is_open=True
        )

        self.assertEqual(plan.phase, "MARKET_OPEN")
        self.assertTrue(plan.stream_live)
        self.assertEqual(plan.fetch_end, datetime(2026, 6, 19, 11, 12))
        self.assertEqual(plan.wait_until, datetime(2026, 6, 19, 11, 13, 2))
        self.assertTrue(plan.require_fetch_end)

    def test_startup_plan_after_close_reconciles_without_streaming(self):
        plan = build_startup_plan(
            now=datetime(2026, 6, 19, 16, 1, tzinfo=IST), market_is_open=False
        )

        self.assertEqual(plan.phase, "AFTER_CLOSE")
        self.assertFalse(plan.stream_live)
        self.assertEqual(plan.fetch_end, datetime(2026, 6, 19, 15, 29))

    def test_before_open_backfill_does_not_fail_without_local_csv(self):
        class EmptyFyers:
            def history(self, data):
                return {"s": "ok", "candles": []}

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            store = CandleCsvStore("CGPOWER", tmp)
            plan = build_startup_plan(
                now=datetime(2026, 6, 19, 8, 55, tzinfo=IST), market_is_open=False
            )
            result = run_initial_backfill(EmptyFyers(), "CGPOWER", store, plan=plan)

            self.assertEqual(result.appended_rows, 0)
            self.assertIn("No local 1MIN CSV", result.message)

    def test_before_open_backfill_ignores_stale_same_day_volume_seed(self):
        class EmptyFyers:
            def history(self, data):
                return {"s": "ok", "candles": []}

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            store = CandleCsvStore("CGPOWER", tmp)
            store.append_raw_rows(
                Main.TIMEFRAME_1MIN,
                [
                    {
                        "Datetime": datetime(2026, 6, 19, 9, 15),
                        "Open": 100,
                        "High": 101,
                        "Low": 99,
                        "Close": 100.5,
                        "Volume": 5000,
                    }
                ],
                strict_minutes=1,
            )
            plan = build_startup_plan(
                now=datetime(2026, 6, 19, 8, 55, tzinfo=IST), market_is_open=False
            )

            result = run_initial_backfill(EmptyFyers(), "CGPOWER", store, plan=plan)

            self.assertEqual(result.baseline_cumulative_volume, 0)

    def test_market_open_baseline_uses_only_rows_through_safe_target(self):
        class EmptyFyers:
            def history(self, data):
                return {"s": "ok", "candles": []}

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            store = CandleCsvStore("CGPOWER", tmp)
            for minute, volume in [(15, 100), (16, 200), (17, 300)]:
                store.append_raw_rows(
                    Main.TIMEFRAME_1MIN,
                    [
                        {
                            "Datetime": datetime(2026, 6, 19, 9, minute),
                            "Open": 100,
                            "High": 101,
                            "Low": 99,
                            "Close": 100.5,
                            "Volume": volume,
                        }
                    ],
                    strict_minutes=1,
                )
            plan = build_startup_plan(
                now=datetime(2026, 6, 19, 9, 16, 50, tzinfo=IST), market_is_open=True
            )
            plan = type(plan)(
                phase=plan.phase,
                stream_live=plan.stream_live,
                fetch_end=plan.fetch_end,
                wait_until=None,
                require_fetch_end=plan.require_fetch_end,
                prompt=plan.prompt,
            )

            result = run_initial_backfill(EmptyFyers(), "CGPOWER", store, plan=plan)

            self.assertEqual(result.baseline_cumulative_volume, 300)

    def test_active_market_backfill_requires_closed_target_candle(self):
        class EmptyFyers:
            def history(self, data):
                return {"s": "ok", "candles": []}

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            store = CandleCsvStore("CGPOWER", tmp)
            plan = build_startup_plan(
                now=datetime(2026, 6, 19, 11, 12, 50, tzinfo=IST), market_is_open=True
            )
            plan = type(plan)(
                phase=plan.phase,
                stream_live=plan.stream_live,
                fetch_end=plan.fetch_end,
                wait_until=None,
                require_fetch_end=plan.require_fetch_end,
                prompt=plan.prompt,
            )

            with self.assertRaises(Exception):
                run_initial_backfill(EmptyFyers(), "CGPOWER", store, plan=plan)

    def test_active_market_backfill_zero_fills_sparse_same_session_history(self):
        class SparseFyers:
            def history(self, data):
                candle_dt = datetime(2026, 6, 19, 9, 17)
                return {"s": "ok", "candles": [[epoch(candle_dt), 101, 102, 100, 101.5, 250]]}

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            store = CandleCsvStore("CGPOWER", tmp)
            store.append_raw_rows(
                Main.TIMEFRAME_1MIN,
                [
                    {
                        "Datetime": datetime(2026, 6, 19, 9, 15),
                        "Open": 100,
                        "High": 101,
                        "Low": 99,
                        "Close": 100.5,
                        "Volume": 1000,
                    }
                ],
                strict_minutes=1,
            )
            plan = build_startup_plan(
                now=datetime(2026, 6, 19, 9, 17, 50, tzinfo=IST), market_is_open=True
            )
            plan = type(plan)(
                phase=plan.phase,
                stream_live=plan.stream_live,
                fetch_end=plan.fetch_end,
                wait_until=None,
                require_fetch_end=plan.require_fetch_end,
                prompt=plan.prompt,
            )

            result = run_initial_backfill(SparseFyers(), "CGPOWER", store, plan=plan)

            self.assertEqual(result.appended_rows, 2)
            saved = pd.read_csv(store.path(Main.TIMEFRAME_1MIN), parse_dates=["Datetime"])
            gap = saved[saved["Datetime"] == datetime(2026, 6, 19, 9, 16)].iloc[0]
            actual = saved[saved["Datetime"] == datetime(2026, 6, 19, 9, 17)].iloc[0]
            self.assertEqual(gap["Volume"], 0)
            self.assertEqual(gap["Close"], 100.5)
            self.assertEqual(actual["Volume"], 250)

    def test_extract_tick_records_from_symbol_update(self):
        dt = datetime(2026, 6, 19, 9, 15)
        records = extract_tick_records(tick("CGPOWER", dt, 606.4, 3045212), "CGPOWER")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].symbol, "NSE:CGPOWER-EQ")
        self.assertEqual(records[0].timestamp, dt)
        self.assertEqual(records[0].price, 606.4)
        self.assertEqual(records[0].cumulative_volume, 3045212)

    def test_extractor_ignores_fyers_control_metadata(self):
        messages = [
            {"type": "cn", "code": 200, "message": "Authentication done", "s": "ok"},
            {"type": "ful", "code": 200, "message": "Full Mode On", "s": "ok"},
            {"type": "sub", "code": 200, "message": "Subscribed", "s": "ok"},
        ]

        for message in messages:
            self.assertEqual(extract_tick_records(message, "CGPOWER"), [])

    def test_extractor_accepts_real_fyers_sf_message(self):
        message = {
            "ltp": 954.45,
            "vol_traded_today": 3552746,
            "last_traded_time": epoch(datetime(2026, 6, 19, 15, 29, 21)),
            "exch_feed_time": epoch(datetime(2026, 6, 19, 17, 0, 35)),
            "bid_size": 0,
            "ask_size": 356,
            "bid_price": 0.0,
            "ask_price": 954.45,
            "last_traded_qty": 460,
            "tot_buy_qty": 0,
            "tot_sell_qty": 356,
            "avg_trade_price": 954.16,
            "low_price": 945.25,
            "high_price": 969.9,
            "open_price": 969.9,
            "prev_close_price": 963.75,
            "type": "sf",
            "symbol": "NSE:CGPOWER-EQ",
            "ch": -9.3,
            "chp": -0.965,
        }

        records = extract_tick_records(message, "CGPOWER")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].price, 954.45)
        self.assertEqual(records[0].timestamp, datetime(2026, 6, 19, 15, 29, 21))
        self.assertEqual(records[0].cumulative_volume, 3552746)

    def test_minute_candle_uses_cumulative_volume_delta(self):
        builder = MinuteCandleBuilder(baseline_cumulative_volume=1000)
        first = TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 15), 100, 1005, {})
        second = TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 15, 30), 102, 1010, {})
        rollover = TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 16), 101, 1020, {})

        self.assertEqual(builder.process(first), [])
        self.assertEqual(builder.process(second), [])
        candles = builder.process(rollover)

        self.assertEqual(len(candles), 1)
        candle = candles[0]
        self.assertEqual(candle.datetime, datetime(2026, 6, 19, 9, 15))
        self.assertEqual(candle.open, 100)
        self.assertEqual(candle.high, 102)
        self.assertEqual(candle.low, 100)
        self.assertEqual(candle.close, 102)
        self.assertEqual(candle.volume, 10)

    def test_stale_pending_tick_does_not_lower_volume_baseline(self):
        builder = MinuteCandleBuilder(baseline_cumulative_volume=2000)
        stale = TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 11, 12, 50), 100, 1900, {})
        fresh = TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 11, 13), 101, 2010, {})
        rollover = TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 11, 14), 102, 2025, {})

        builder.process(stale)
        builder.process(fresh)
        candles = builder.process(rollover)

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].volume, 10)

    def test_candle_flushes_by_clock_without_next_tick(self):
        builder = MinuteCandleBuilder(baseline_cumulative_volume=1000)
        first = TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 15), 100, 1005, {})

        builder.process(first)
        candles = builder.flush_ready(datetime(2026, 6, 19, 9, 16, 3), settle_seconds=2)
        late = builder.process(
            TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 15, 30), 101, 1010, {})
        )

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].datetime, datetime(2026, 6, 19, 9, 15))
        self.assertEqual(late, [])
        self.assertEqual(builder.ignored_out_of_order_ticks, 1)

    def test_builder_fills_no_trade_minutes_after_clock_flush(self):
        builder = MinuteCandleBuilder(baseline_cumulative_volume=1000)
        builder.process(TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 15), 100, 1005, {}))
        builder.flush_ready(datetime(2026, 6, 19, 9, 16, 3), settle_seconds=2)

        gap_candles = builder.process(
            TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 18), 101, 1010, {})
        )

        self.assertEqual(
            [item.datetime for item in gap_candles],
            [
                datetime(2026, 6, 19, 9, 16),
                datetime(2026, 6, 19, 9, 17),
            ],
        )
        self.assertEqual([item.volume for item in gap_candles], [0, 0])
        self.assertEqual([item.close for item in gap_candles], [100, 100])

    def test_seeded_builder_fills_no_trade_minutes_after_restart(self):
        builder = MinuteCandleBuilder(baseline_cumulative_volume=1000)
        builder.seed_last_finalized(datetime(2026, 6, 19, 9, 31), 100)

        gap_candles = builder.process(
            TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 34), 101, 1010, {})
        )

        self.assertEqual(
            [item.datetime for item in gap_candles],
            [
                datetime(2026, 6, 19, 9, 32),
                datetime(2026, 6, 19, 9, 33),
            ],
        )
        self.assertEqual([item.volume for item in gap_candles], [0, 0])
        self.assertEqual([item.open for item in gap_candles], [100, 100])

    def test_clock_flush_fills_no_trade_minutes_without_next_tick(self):
        builder = MinuteCandleBuilder(baseline_cumulative_volume=1000)
        builder.seed_last_finalized(datetime(2026, 6, 19, 9, 35), 100)

        gap_candles = builder.flush_ready(datetime(2026, 6, 19, 9, 38, 3), settle_seconds=2)

        self.assertEqual(
            [item.datetime for item in gap_candles],
            [
                datetime(2026, 6, 19, 9, 36),
                datetime(2026, 6, 19, 9, 37),
            ],
        )
        self.assertEqual([item.volume for item in gap_candles], [0, 0])
        self.assertEqual([item.close for item in gap_candles], [100, 100])

    def test_before_open_ready_allows_first_live_bucket_after_open(self):
        builder = MinuteCandleBuilder(baseline_cumulative_volume=1000)
        builder.drop_first_partial_bucket = False
        first = TickRecord("NSE:CGPOWER-EQ", datetime(2026, 6, 19, 9, 15, 10), 100, 1005, {})

        builder.process(first)
        candles = builder.flush_ready(datetime(2026, 6, 19, 9, 16, 3), settle_seconds=2)

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].datetime, datetime(2026, 6, 19, 9, 15))

    def test_csv_store_appends_and_rejects_same_day_gap(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            store = CandleCsvStore("CGPOWER", tmp)
            first = {
                "Datetime": datetime(2026, 6, 19, 9, 15),
                "Open": 100,
                "High": 101,
                "Low": 99,
                "Close": 100.5,
                "Volume": 1000,
            }
            second = {
                "Datetime": datetime(2026, 6, 19, 9, 16),
                "Open": 101,
                "High": 102,
                "Low": 100,
                "Close": 101.5,
                "Volume": 1001,
            }
            gap = {
                "Datetime": datetime(2026, 6, 19, 9, 18),
                "Open": 102,
                "High": 103,
                "Low": 101,
                "Close": 102.5,
                "Volume": 1002,
            }

            self.assertEqual(
                store.append_raw_rows(Main.TIMEFRAME_1MIN, [first], strict_minutes=1).rows_appended,
                1,
            )
            self.assertEqual(
                store.append_raw_rows(
                    Main.TIMEFRAME_1MIN, [second], strict_minutes=1
                ).rows_appended,
                1,
            )
            with self.assertRaises(DataContinuityError):
                store.append_raw_rows(Main.TIMEFRAME_1MIN, [gap], strict_minutes=1)

            saved = pd.read_csv(store.path(Main.TIMEFRAME_1MIN), parse_dates=["Datetime"])
            self.assertEqual(len(saved), 2)
            self.assertTrue({"EMA9", "EMA21", "ADX", "ATR"}.issubset(saved.columns))

    def test_higher_timeframe_overnight_jump_uses_bucket_start_close(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            store = CandleCsvStore("CGPOWER", tmp)
            last_5min = {
                "Datetime": datetime(2026, 6, 19, 15, 25),
                "Open": 100,
                "High": 101,
                "Low": 99,
                "Close": 100.5,
                "Volume": 1000,
            }
            next_5min = {
                "Datetime": datetime(2026, 6, 22, 9, 15),
                "Open": 101,
                "High": 102,
                "Low": 100,
                "Close": 101.5,
                "Volume": 1001,
            }

            store.append_raw_rows(Main.TIMEFRAME_5MIN, [last_5min], strict_minutes=5)
            result = store.append_raw_rows(Main.TIMEFRAME_5MIN, [next_5min], strict_minutes=5)

            self.assertEqual(result.rows_appended, 1)

    def test_pipeline_persists_ticks_and_appends_closed_candle(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            root = Path(tmp)
            store = CandleCsvStore("CGPOWER", root / "Data")
            tick_store = TickJsonlStore("CGPOWER", root / "TickData")
            pipeline = LiveTickPipeline("CGPOWER", store=store, tick_store=tick_store)
            pipeline.start()
            pipeline.mark_ready(1000)

            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 9, 15), 100, 1005))
            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 9, 15, 20), 101, 1010))
            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 9, 16), 102, 1020))
            pipeline.queue.join()
            pipeline.stop()
            pipeline.join(timeout=5)

            self.assertIsNone(pipeline.fatal_error)
            saved = pd.read_csv(store.path(Main.TIMEFRAME_1MIN), parse_dates=["Datetime"])
            self.assertEqual(len(saved), 1)
            self.assertEqual(
                saved.iloc[0]["Datetime"].to_pydatetime(), datetime(2026, 6, 19, 9, 15)
            )
            tick_files = list((root / "TickData" / "CGPOWER").glob("*_ticks.jsonl"))
            self.assertEqual(len(tick_files), 1)
            self.assertGreater(tick_files[0].stat().st_size, 0)

    def test_pipeline_prints_compact_closed_candle_summary(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            root = Path(tmp)
            store = CandleCsvStore("CGPOWER", root / "Data")
            tick_store = TickJsonlStore("CGPOWER", root / "TickData")
            pipeline = LiveTickPipeline("CGPOWER", store=store, tick_store=tick_store)
            output = StringIO()
            pipeline.start()
            pipeline.mark_ready(1000)
            with redirect_stdout(output):
                pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 9, 31), 100.12, 1005))
                pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 9, 31, 20), 101.45, 1010))
                pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 9, 32), 101.50, 1020))
                pipeline.queue.join()
            pipeline.stop()
            pipeline.join(timeout=5)

            text = output.getvalue()
            self.assertIn("CGPOWER  09:31 Open:100.12  Close:101.45", text)
            self.assertNotIn("appended 1MIN candle", text)

    def test_pipeline_keeps_first_buffered_bucket_after_backfill(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            root = Path(tmp)
            store = CandleCsvStore("CGPOWER", root / "Data")
            store.append_raw_rows(
                Main.TIMEFRAME_1MIN,
                [
                    {
                        "Datetime": datetime(2026, 6, 19, 11, 50),
                        "Open": 100,
                        "High": 101,
                        "Low": 99,
                        "Close": 100.5,
                        "Volume": 1000,
                    }
                ],
                strict_minutes=1,
            )
            tick_store = TickJsonlStore("CGPOWER", root / "TickData")
            pipeline = LiveTickPipeline("CGPOWER", store=store, tick_store=tick_store)
            pipeline.start()
            pipeline.seed_derived_from_csv(datetime(2026, 6, 19, 11, 50))
            pipeline.mark_ready(1000, drop_first_partial_bucket=False)

            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 11, 51, 10), 101, 1005))
            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 11, 52), 102, 1010))
            pipeline.queue.join()
            pipeline.stop()
            pipeline.join(timeout=5)

            self.assertIsNone(pipeline.fatal_error)
            saved = pd.read_csv(store.path(Main.TIMEFRAME_1MIN), parse_dates=["Datetime"])
            self.assertIn(datetime(2026, 6, 19, 11, 51), set(saved["Datetime"].dt.to_pydatetime()))

    def test_pipeline_repairs_small_same_session_gap_before_append(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            root = Path(tmp)
            store = CandleCsvStore("CGPOWER", root / "Data")
            store.append_raw_rows(
                Main.TIMEFRAME_1MIN,
                [
                    {
                        "Datetime": datetime(2026, 6, 19, 11, 50),
                        "Open": 100,
                        "High": 101,
                        "Low": 99,
                        "Close": 100.5,
                        "Volume": 1000,
                    }
                ],
                strict_minutes=1,
            )
            tick_store = TickJsonlStore("CGPOWER", root / "TickData")
            pipeline = LiveTickPipeline("CGPOWER", store=store, tick_store=tick_store)

            pipeline._append_finalized_candles(
                [
                    Candle(
                        datetime=datetime(2026, 6, 19, 11, 52),
                        open=102,
                        high=103,
                        low=101,
                        close=102.5,
                        volume=100,
                        tick_count=4,
                    )
                ]
            )
            pipeline.join(timeout=0)

            saved = pd.read_csv(store.path(Main.TIMEFRAME_1MIN), parse_dates=["Datetime"])
            by_time = {row.Datetime.to_pydatetime(): row for row in saved.itertuples(index=False)}
            self.assertIn(datetime(2026, 6, 19, 11, 51), by_time)
            self.assertIn(datetime(2026, 6, 19, 11, 52), by_time)
            self.assertEqual(by_time[datetime(2026, 6, 19, 11, 51)].Volume, 0)
            self.assertEqual(by_time[datetime(2026, 6, 19, 11, 51)].Close, 100.5)

    def test_pipeline_seeds_partial_higher_timeframe_bucket_after_midday_start(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            root = Path(tmp)
            store = CandleCsvStore("CGPOWER", root / "Data")
            for minute in [10, 11, 12]:
                store.append_raw_rows(
                    Main.TIMEFRAME_1MIN,
                    [
                        {
                            "Datetime": datetime(2026, 6, 19, 11, minute),
                            "Open": 100 + minute,
                            "High": 101 + minute,
                            "Low": 99 + minute,
                            "Close": 100.5 + minute,
                            "Volume": 1000 + minute,
                        }
                    ],
                    strict_minutes=1,
                )
            store.append_raw_rows(
                Main.TIMEFRAME_5MIN,
                [
                    {
                        "Datetime": datetime(2026, 6, 19, 11, 5),
                        "Open": 100,
                        "High": 101,
                        "Low": 99,
                        "Close": 100.5,
                        "Volume": 1000,
                    }
                ],
                strict_minutes=5,
            )
            tick_store = TickJsonlStore("CGPOWER", root / "TickData")
            pipeline = LiveTickPipeline("CGPOWER", store=store, tick_store=tick_store)
            pipeline.start()
            pipeline.seed_derived_from_csv(datetime(2026, 6, 19, 11, 12))
            pipeline.mark_ready(3012)

            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 11, 13), 113, 3013))
            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 11, 14), 114, 3014))
            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 11, 15), 115, 3015))
            pipeline.on_message(tick("CGPOWER", datetime(2026, 6, 19, 11, 16), 116, 3016))
            pipeline.queue.join()
            pipeline.stop()
            pipeline.join(timeout=5)

            saved_5min = pd.read_csv(store.path(Main.TIMEFRAME_5MIN), parse_dates=["Datetime"])
            self.assertIn(
                datetime(2026, 6, 19, 11, 10), set(saved_5min["Datetime"].dt.to_pydatetime())
            )

    def test_validation_report_flags_ohlcv_mismatch(self):
        dt = datetime(2026, 6, 19, 9, 15)
        local = pd.DataFrame(
            [
                {
                    "Datetime": dt,
                    "Open": 100,
                    "High": 101,
                    "Low": 99,
                    "Close": 100.5,
                    "Volume": 1000,
                },
            ]
        )
        reference = pd.DataFrame(
            [
                {
                    "Datetime": dt,
                    "Open": 100,
                    "High": 101,
                    "Low": 98,
                    "Close": 100.5,
                    "Volume": 1000,
                },
            ]
        )

        report = compare_candle_frames(local, reference)

        self.assertFalse(report.passed)
        self.assertEqual(report.mismatch_rows, 1)
        self.assertEqual(report.max_abs_price_diff, 1.0)


if __name__ == "__main__":
    unittest.main()
