from __future__ import annotations

import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Actions as Main
from Paper.GoldPaperTrader import (
    DEFAULT_SYMBOLS,
    PaperConfig,
    _save_workbook_safely,
    append_csv,
    calculate_charges,
    ensure_live_tick_feed,
    fallback_report_file_path,
    fallback_report_xlsx_path,
    generate_live_signals,
    live_tick_session_symbols,
    offmarket_live_tick_message,
    print_status_line,
    read_report_csv,
    report_xlsx_path,
    run_once,
    should_run_single_offmarket_check,
    should_start_live_tick,
    signal_alert_message,
    timeframe_path,
)


class GoldPaperTraderTests(unittest.TestCase):
    def test_generate_live_signals_keeps_last_bar_as_pending_entry(self):
        df = pd.DataFrame(
            {
                "Datetime": pd.to_datetime(["2026-06-19 10:00"]),
                "date": ["2026-06-19"],
                "bar_no": [9],
                "Open": [100.0],
                "High": [102.0],
                "Low": [99.0],
                "Close": [101.5],
                "Volume": [100000],
                "vwap": [100.0],
                "ema13": [100.5],
                "ema21": [100.0],
                "ema34": [99.5],
                "ema55": [98.0],
                "adx_for_signal": [35.0],
                "vol_ratio20": [2.0],
                "rsi14": [60.0],
                "prev_close": [100.0],
                "atr14": [2.0],
            }
        )

        signals = generate_live_signals(df)

        self.assertEqual(len(signals), 1)
        self.assertEqual(
            pd.Timestamp(signals.iloc[0]["entry_time"]).to_pydatetime(),
            datetime(2026, 6, 19, 10, 5),
        )
        self.assertTrue(pd.isna(signals.iloc[0]["entry"]))

    def test_signal_status_line_is_green_and_detailed(self):
        signal = pd.Series(
            {
                "Datetime": pd.Timestamp("2026-06-19 10:00"),
                "entry_time": pd.Timestamp("2026-06-19 10:05"),
                "direction": 1,
                "signal_strength": 82.4,
                "strength_band": "Strong",
            }
        )
        message = signal_alert_message("CGPOWER", signal)
        output = StringIO()

        with redirect_stdout(output):
            print_status_line(datetime(2026, 6, 19, 10, 4), message)

        text = output.getvalue()
        self.assertIn("\033[92m", text)
        self.assertIn(
            "CGPOWER: SIGNAL HIT Long signal=10:00 entry=10:05 strength=82.4 band=Strong", text
        )
        self.assertIn("\033[0m", text)

    def test_charge_model_handles_short_sell_side_and_buy_side(self):
        config = PaperConfig()

        charges = calculate_charges(entry=100, exit_price=98, qty=10, direction=-1, config=config)

        self.assertEqual(round(charges["sell_value"], 2), 1000.0)
        self.assertEqual(round(charges["buy_value"], 2), 980.0)
        self.assertGreater(charges["total_charges"], 0)

    def test_run_once_rejects_stale_data_and_writes_xlsx(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            root = Path(tmp)
            data_folder = root / "Data"
            report_folder = root / "PaperReports"
            symbol = "CGPOWER"
            one_min = pd.DataFrame(
                [
                    {
                        "Datetime": datetime(2026, 6, 19, 9, 15),
                        "Open": 100,
                        "High": 101,
                        "Low": 99,
                        "Close": 100.5,
                        "Volume": 1000,
                    }
                ]
            )
            five_min = one_min.copy()
            one_min_final = Main.add_indicators(one_min, log_fn=lambda _message: None)
            five_min_final = Main.add_indicators(five_min, log_fn=lambda _message: None)
            timeframe_path(symbol, Main.TIMEFRAME_1MIN, data_folder).parent.mkdir(parents=True)
            one_min_final.to_csv(
                timeframe_path(symbol, Main.TIMEFRAME_1MIN, data_folder), index=False
            )
            five_min_final.to_csv(
                timeframe_path(symbol, Main.TIMEFRAME_5MIN, data_folder), index=False
            )

            messages = run_once(
                [symbol],
                data_folder=data_folder,
                report_folder=report_folder,
                config=PaperConfig(),
                reset=True,
                current=datetime(2026, 6, 19, 10, 0),
            )

            self.assertIn("Stale 1MIN data", messages[0])
            self.assertTrue(report_xlsx_path(report_folder, datetime(2026, 6, 19)).exists())

    def test_report_write_uses_live_copy_when_primary_xlsx_is_locked(self):
        class LockedOnceWorkbook:
            def __init__(self):
                self.saved_paths = []

            def save(self, path):
                self.saved_paths.append(Path(path))
                if len(self.saved_paths) == 1:
                    raise PermissionError("locked")

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            primary = Path(tmp) / "GoldPaperTrades_2026-06-19.xlsx"
            wb = LockedOnceWorkbook()

            saved = _save_workbook_safely(wb, primary)

            self.assertEqual(saved, fallback_report_xlsx_path(primary))
            self.assertEqual(wb.saved_paths, [primary, fallback_report_xlsx_path(primary)])

    def test_report_csv_write_uses_live_copy_when_primary_csv_is_locked(self):
        calls = []

        def fake_append(path, row):
            calls.append((Path(path), row))
            if len(calls) == 1:
                raise PermissionError("locked")

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            primary = Path(tmp) / "gold_paper_events.csv"
            with patch("Paper.GoldPaperTrader._append_csv_to_path", side_effect=fake_append):
                append_csv(primary, {"event": "NO_SIGNAL"})

            self.assertEqual(calls[0][0], primary)
            self.assertEqual(calls[1][0], fallback_report_file_path(primary))
            self.assertEqual(calls[1][1], {"event": "NO_SIGNAL"})

    def test_read_report_csv_combines_primary_and_live_copy(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            primary = Path(tmp) / "gold_paper_events.csv"
            fallback = fallback_report_file_path(primary)
            pd.DataFrame([{"event": "PRIMARY", "symbol": "CGPOWER"}]).to_csv(primary, index=False)
            pd.DataFrame([{"event": "LIVE", "symbol": "CGPOWER"}]).to_csv(fallback, index=False)

            df = read_report_csv(primary)

            self.assertEqual(df["event"].tolist(), ["PRIMARY", "LIVE"])

    def test_default_gold_paper_symbols_cover_primary_live_pair(self):
        self.assertEqual(DEFAULT_SYMBOLS, ("CGPOWER", "HDFCBANK"))

    def test_live_tick_feed_reuses_running_matching_session(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            root = Path(tmp)
            session = {"pid": 123, "metadata": {"symbols": ["CGPOWER", "HDFCBANK"]}}
            with (
                patch("Paper.GoldPaperTrader.load_session", return_value=session),
                patch(
                    "Paper.GoldPaperTrader.is_pid_running",
                    return_value=True,
                ),
            ):
                owned, thread, errors, messages = ensure_live_tick_feed(
                    ["CGPOWER"],
                    data_folder=root / "Data",
                    tick_root=root / "TickData",
                    report_folder=root / "PaperReports",
                )

            self.assertFalse(owned)
            self.assertIsNone(thread)
            self.assertEqual(errors, [])
            self.assertIn("Reusing LiveTick session PID 123", messages[0])

    def test_live_tick_feed_can_be_disabled_for_local_only_runs(self):
        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            root = Path(tmp)
            with patch("Paper.GoldPaperTrader.load_session", return_value=None):
                owned, thread, errors, messages = ensure_live_tick_feed(
                    ["CGPOWER"],
                    data_folder=root / "Data",
                    tick_root=root / "TickData",
                    report_folder=root / "PaperReports",
                    manage_live_tick=False,
                )

            self.assertFalse(owned)
            self.assertIsNone(thread)
            self.assertEqual(errors, [])
            self.assertIn("auto-start is disabled", messages[0])

    def test_live_tick_session_symbols_normalizes_fyers_names(self):
        symbols = live_tick_session_symbols(
            {"metadata": {"symbols": ["NSE:CGPOWER-EQ", "hdfcbank"]}}
        )

        self.assertEqual(symbols, {"CGPOWER", "HDFCBANK"})

    def test_live_tick_does_not_start_on_weekend_or_after_close(self):
        saturday = datetime(2026, 6, 20, 15, 17)
        friday_after_close = datetime(2026, 6, 19, 15, 31)
        friday_pre_open = datetime(2026, 6, 19, 8, 45)
        friday_holiday = datetime(2026, 6, 26, 10, 0)

        self.assertFalse(should_start_live_tick(saturday))
        self.assertFalse(should_start_live_tick(friday_after_close))
        self.assertFalse(should_start_live_tick(friday_holiday))
        self.assertTrue(should_start_live_tick(friday_pre_open))
        self.assertTrue(should_run_single_offmarket_check(saturday))
        self.assertTrue(should_run_single_offmarket_check(friday_after_close))
        self.assertTrue(should_run_single_offmarket_check(friday_holiday))
        self.assertFalse(should_run_single_offmarket_check(friday_pre_open))
        self.assertIn("closed today", offmarket_live_tick_message(saturday))
        self.assertIn("Market holiday", offmarket_live_tick_message(friday_holiday))


if __name__ == "__main__":
    unittest.main()
