from __future__ import annotations

import sys
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import Actions as Main

IST = ZoneInfo("Asia/Kolkata")


def make_1min_bars(day, base=100):
    start = datetime.combine(day, datetime.strptime(Main.MARKET_OPEN, "%H:%M").time())
    rows = []
    for i in range(Main.EXPECTED_1MIN_BARS_PER_DAY):
        dt_ist = start + timedelta(minutes=i)
        epoch = int(dt_ist.replace(tzinfo=IST).timestamp())
        price = base + i * 0.01
        rows.append([epoch, price, price + 1, price - 1, price + 0.5, 1000 + i])
    return rows


class FakeFyers:
    def __init__(self):
        self.requests = []

    def history(self, data):
        self.assert_resolution = data["resolution"]
        range_from = datetime.strptime(data["range_from"], "%Y-%m-%d").date()
        range_to = datetime.strptime(data["range_to"], "%Y-%m-%d").date()
        self.requests.append(dict(data))
        candles = []
        day = range_from
        while day <= range_to:
            candles.extend(make_1min_bars(day, 100 + len(self.requests)))
            day += timedelta(days=1)
        return {"s": "ok", "candles": candles}


class RateLimitFyers:
    def __init__(self):
        self.requests = []

    def history(self, data):
        self.requests.append(data)
        return {"code": 429, "message": "request limit reached", "s": "error"}


class MainDataPipelineTests(unittest.TestCase):
    def test_resolve_fyers_symbol_supports_nifty_index_and_equity_defaults(self):
        self.assertEqual(Main.ResolveFyersSymbol("NIFTY"), "NSE:NIFTY50-INDEX")
        self.assertEqual(Main.resolve_fyers_symbol("NIFTY50-INDEX"), "NSE:NIFTY50-INDEX")
        self.assertEqual(Main.resolve_fyers_symbol("NSE:NIFTY50-INDEX"), "NSE:NIFTY50-INDEX")
        self.assertEqual(Main.ResolveFyersSymbol("SBIN"), "NSE:SBIN-EQ")

    def test_normalize_dedupes_and_sorts(self):
        raw = pd.DataFrame(
            {
                "Datetime": ["2024-01-11 09:15:00", "2024-01-10 09:15:00", "2024-01-10 09:15:00"],
                "Open": [102, 100, 101],
                "High": [103, 101, 102],
                "Low": [101, 99, 100],
                "Close": [102.5, 100.5, 101.5],
                "Volume": [2000, 1000, 1500],
            }
        )
        normalized = Main.normalize_candles(raw)
        self.assertEqual(len(normalized), 2)
        self.assertTrue(normalized["Datetime"].is_monotonic_increasing)
        self.assertEqual(normalized.iloc[0]["Open"], 101)

    def test_materialize_writes_symbol_folder_timeframes(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            output = Path(tmp)
            symbol = "TESTSYM"
            rows = []
            first_day = datetime(2024, 1, 1).date()
            for offset in range(30):
                rows.extend(make_1min_bars(first_day + timedelta(days=offset), 100 + offset))
            df = Main.candles_to_dataframe(rows, IST)
            symbol_folder = output / symbol
            symbol_folder.mkdir()
            df.to_csv(symbol_folder / f"{symbol}_1MIN.csv", index=False)

            result = Main.materialize_timeframe_files(symbol, str(output))
            self.assertEqual(
                result["rows"][Main.TIMEFRAME_1MIN], 30 * Main.EXPECTED_1MIN_BARS_PER_DAY
            )
            self.assertEqual(
                result["rows"][Main.TIMEFRAME_5MIN], 30 * Main.EXPECTED_5MIN_BARS_PER_DAY
            )
            self.assertTrue((output / symbol / f"{symbol}_1MIN.csv").exists())
            self.assertTrue((output / symbol / f"{symbol}_5MIN.csv").exists())
            self.assertTrue((output / symbol / f"{symbol}_15MIN.csv").exists())
            self.assertTrue((output / symbol / f"{symbol}_1D.csv").exists())
            self.assertTrue((output / symbol / f"{symbol}_1W.csv").exists())

            final = pd.read_csv(output / symbol / f"{symbol}_15MIN.csv", parse_dates=["Datetime"])
            self.assertEqual(int(final["Datetime"].duplicated().sum()), 0)
            self.assertTrue(final["Datetime"].is_monotonic_increasing)

    def test_download_fetches_only_missing_ranges_and_writes_timeframes(self):
        real_login = Main.login
        fake = FakeFyers()
        Main.login = lambda: fake
        try:
            with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
                output = Path(tmp)
                symbol = "TESTSYM"
                end_date = datetime.now(IST).date()
                start_date = end_date - timedelta(days=10)
                existing_day = start_date + timedelta(days=4)
                existing = Main.candles_to_dataframe(make_1min_bars(existing_day, 200), IST)
                symbol_folder = output / symbol
                symbol_folder.mkdir()
                existing.to_csv(symbol_folder / f"{symbol}_1MIN.csv", index=False)

                Main.download([symbol], output_folder=str(output), chunk_days=60, total_days=10)
                self.assertGreaterEqual(len(fake.requests), 1)
                self.assertEqual(fake.assert_resolution, Main.FYERS_BASE_RESOLUTION)
                self.assertTrue((output / symbol / f"{symbol}_1MIN.csv").exists())
                final_path = output / symbol / f"{symbol}_5MIN.csv"
                final = pd.read_csv(final_path, parse_dates=["Datetime"])
                self.assertEqual(int(final["Datetime"].duplicated().sum()), 0)
                self.assertTrue(final["Datetime"].is_monotonic_increasing)
                self.assertTrue((output / symbol / f"{symbol}_15MIN.csv").exists())
                self.assertTrue((output / symbol / f"{symbol}_1D.csv").exists())
                self.assertTrue((output / symbol / f"{symbol}_1W.csv").exists())
        finally:
            Main.login = real_login

    def test_download_stats_reports_api_calls_candles_and_elapsed_time(self):
        real_login = Main.login
        fake = FakeFyers()
        Main.login = lambda: fake
        try:
            with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
                output = Path(tmp)
                symbol = "TESTSYM"
                buf = StringIO()

                with redirect_stdout(buf):
                    Main.download(
                        [symbol],
                        output_folder=str(output),
                        chunk_days=60,
                        total_days=2,
                        downloadStats=True,
                    )

                text = buf.getvalue()
                self.assertIn(f"API calls: {len(fake.requests)}", text)
                self.assertIn("Downloaded Candles: 1125", text)
                self.assertIn("Time:", text)
                self.assertEqual(text.count("API calls:"), 1)
                self.assertNotIn("Download, merge, and indicator population complete.", text)
        finally:
            Main.login = real_login

    def test_main_download_wrapper_uses_login_module_without_recursion(self):
        fake = FakeFyers()
        fake_login_module = types.ModuleType("Login")
        fake_login_module.login = lambda: fake
        missing = object()
        real_login_module = sys.modules.get("Login", missing)
        sys.modules["Login"] = fake_login_module
        try:
            with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
                output = Path(tmp)
                Main.Download(["TESTSYM"], output_folder=output, chunk_days=60, total_days=1)

                self.assertGreaterEqual(len(fake.requests), 1)
                self.assertTrue((output / "TESTSYM" / "TESTSYM_1MIN.csv").exists())
        finally:
            if real_login_module is missing:
                sys.modules.pop("Login", None)
            else:
                sys.modules["Login"] = real_login_module

    def test_download_uses_nifty_index_symbol_for_history_requests(self):
        real_login = Main.login
        fake = FakeFyers()
        Main.login = lambda: fake
        try:
            with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
                output = Path(tmp)
                Main.Download(["NIFTY"], output_folder=output, chunk_days=60, total_days=1)

                self.assertGreaterEqual(len(fake.requests), 1)
                self.assertEqual(fake.requests[0]["symbol"], "NSE:NIFTY50-INDEX")
                self.assertTrue((output / "NIFTY" / "NIFTY_1MIN.csv").exists())
        finally:
            Main.login = real_login

    def test_add_indicators_short_data_uses_fallback_without_ta_warning(self):
        real_ta = Main.ta

        class ExplodingTa:
            class trend:
                @staticmethod
                def ema_indicator(*args, **kwargs):
                    raise AssertionError("ta should not be called for short data")

                class ADXIndicator:
                    def __init__(self, *args, **kwargs):
                        raise AssertionError("ta should not be called for short data")

            class volatility:
                class AverageTrueRange:
                    def __init__(self, *args, **kwargs):
                        raise AssertionError("ta should not be called for short data")

        rows = []
        start = datetime(2024, 1, 1, 9, 15)
        for i in range(15):
            rows.append(
                {
                    "Datetime": start + timedelta(days=7 * i),
                    "Open": 100 + i,
                    "High": 102 + i,
                    "Low": 99 + i,
                    "Close": 101 + i,
                    "Volume": 1000 + i,
                }
            )

        Main.ta = ExplodingTa
        try:
            messages = []
            out = Main.add_indicators(pd.DataFrame(rows), log_fn=messages.append)

            self.assertEqual(messages, [])
            self.assertEqual(len(out), 15)
            self.assertTrue({"EMA9", "EMA21", "ADX", "ATR"}.issubset(out.columns))
        finally:
            Main.ta = real_ta

    def test_download_stops_on_rate_limit_without_writing_partial_files(self):
        real_login = Main.login
        fake = RateLimitFyers()
        Main.login = lambda: fake
        try:
            with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
                output = Path(tmp)
                Main.download(
                    ["RATELIMIT"], output_folder=str(output), chunk_days=30, total_days=10
                )
                self.assertEqual(len(fake.requests), 1)
                self.assertFalse((output / "RATELIMIT").exists())
        finally:
            Main.login = real_login

    def test_candles_to_dataframe_drops_malformed_and_missing_ohlcv_rows(self):
        good_day = datetime(2024, 1, 1).date()
        good = make_1min_bars(good_day, 100)[0]
        malformed = [good[0], 100, 101]
        missing_close = [good[0] + 300, 100, 101, 99, None, 1000]

        df = Main.candles_to_dataframe([malformed, missing_close, good], IST)

        self.assertEqual(len(df), 1)
        self.assertEqual(float(df.iloc[0]["Close"]), good[4])


if __name__ == "__main__":
    unittest.main()
