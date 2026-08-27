from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Strategies.G01 import Gold as gold
from Strategies.G01.Strategy import G01Strategy


class CGPowerGoldStrategyTests(unittest.TestCase):
    def test_signal_strength_scores_and_bands_signals(self):
        df = pd.DataFrame(
            {
                "Datetime": pd.to_datetime(["2024-01-01 10:00", "2024-01-02 10:00"]),
                "date": ["2024-01-01", "2024-01-02"],
                "Close": [100.1, 103.0],
                "vwap": [100.0, 101.0],
                "ema13": [100.0, 102.0],
                "ema21": [100.0, 101.0],
                "ema34": [100.0, 101.0],
                "ema55": [100.0, 99.0],
                "adx_for_signal": [26.0, 44.0],
                "vol_ratio20": [1.2, 2.7],
                "prev_close": [100.1, 102.0],
                "atr14": [2.0, 2.0],
            }
        )
        signals = pd.DataFrame(
            {
                "Datetime": df["Datetime"],
                "date": df["date"],
                "signal_index": [0, 1],
                "direction": [1, 1],
            }
        )

        scored = gold.signal_strength_table(df, signals)

        self.assertTrue(scored["signal_strength"].between(0, 100).all())
        self.assertLess(scored.loc[0, "signal_strength"], gold.MIN_SIGNAL_STRENGTH)
        self.assertGreater(scored.loc[1, "signal_strength"], 80)
        self.assertEqual(scored.loc[0, "strength_band"], "<40")
        self.assertEqual(scored.loc[1, "strength_band"], "80+")

    def test_strategy_scan_refreshes_data_by_default(self):
        def fake_build_trades(symbol, data_folder):
            df = pd.DataFrame(
                {
                    "Datetime": pd.to_datetime(["2026-06-18 09:15", "2026-06-19 09:15"]),
                    "date": ["2026-06-18", "2026-06-19"],
                }
            )
            empty = pd.DataFrame(columns=["date"])
            return df, empty, empty

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            report_path = Path(tmp) / "scan.xlsx"
            strategy = G01Strategy(data_folder=Path(tmp) / "Data", report_folder=Path(tmp))
            with patch("Strategies.G01.Strategy.DataDownload.Download") as download, patch(
                "Strategies.G01.Strategy.BuildTrades",
                side_effect=fake_build_trades,
            ), patch("Strategies.G01.Strategy.SaveScanReport", return_value=report_path):
                strategy.Scan(["CGPOWER"], days=5)

            download.assert_called_once()
            self.assertEqual(download.call_args.kwargs["output_folder"], str(Path(tmp) / "Data"))
            self.assertEqual(download.call_args.kwargs["total_days"], 120)

    def test_strategy_scan_can_skip_refresh(self):
        def fake_build_trades(symbol, data_folder):
            df = pd.DataFrame(
                {
                    "Datetime": pd.to_datetime(["2026-06-19 09:15"]),
                    "date": ["2026-06-19"],
                }
            )
            empty = pd.DataFrame(columns=["date"])
            return df, empty, empty

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            strategy = G01Strategy(data_folder=Path(tmp) / "Data", report_folder=Path(tmp))
            with patch("Strategies.G01.Strategy.DataDownload.Download") as download, patch(
                "Strategies.G01.Strategy.BuildTrades",
                side_effect=fake_build_trades,
            ), patch("Strategies.G01.Strategy.SaveScanReport", return_value=Path(tmp) / "scan.xlsx"):
                strategy.Scan(["CGPOWER"], days=5, updateData=False)

            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
