from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import pandas as pd

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "Research"
    / "MutualFunds"
    / "LongTermComparison"
    / "long_term_fund_analysis.py"
)
SPEC = importlib.util.spec_from_file_location("long_term_fund_analysis", MODULE_PATH)
Analysis = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = Analysis
SPEC.loader.exec_module(Analysis)


class LongTermFundAnalysisTests(unittest.TestCase):
    def test_date_chunks_cover_range_without_overlap(self):
        chunks = Analysis.BuildDateChunks(
            pd.Timestamp("2020-01-01"),
            pd.Timestamp("2022-01-15"),
        )

        self.assertEqual(chunks[0][0], pd.Timestamp("2020-01-01"))
        self.assertEqual(chunks[-1][1], pd.Timestamp("2022-01-15"))
        for prior, current in zip(chunks, chunks[1:], strict=False):
            self.assertEqual(current[0], prior[1] + pd.Timedelta(days=1))
            self.assertLessEqual((prior[1] - prior[0]).days, 364)

    def test_tri_parser_validates_identity_and_sorts(self):
        definition = Analysis.INDICES[0]
        payload = json.dumps(
            [
                {
                    "Index Name": "Nifty Midcap 150",
                    "Date": "02 Jan 2026",
                    "TotalReturnsIndex": "101.5",
                },
                {
                    "Index Name": "Nifty Midcap 150",
                    "Date": "01 Jan 2026",
                    "TotalReturnsIndex": "100.0",
                },
            ]
        )

        result = Analysis.ParseTriPayload(payload, definition)

        self.assertEqual(result[definition.Key].tolist(), [100.0, 101.5])
        self.assertEqual(
            result["Date"].dt.strftime("%Y-%m-%d").tolist(), ["2026-01-01", "2026-01-02"]
        )

        wrong = payload.replace("Nifty Midcap 150", "Nifty Smallcap 250")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            Analysis.ParseTriPayload(wrong, definition)

    def test_rebalanced_portfolio_preserves_constant_assets(self):
        frame = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-01", "2025-12-31", "2026-01-01"]),
                "A": [100.0, 100.0, 100.0],
                "B": [200.0, 200.0, 200.0],
            }
        )

        result = Analysis.RebalancedPortfolio(frame, {"A": 0.6, "B": 0.4})

        self.assertEqual(result.tolist(), [1.0, 1.0, 1.0])

    def test_sip_uses_fractional_units_and_exact_weights(self):
        dates = pd.to_datetime(["2026-01-05", "2026-02-05", "2026-02-27"])
        frame = pd.DataFrame(
            {
                "Date": dates,
                "A": [100.0, 100.0, 200.0],
                "B": [100.0, 100.0, 100.0],
            }
        )

        result = Analysis.SimulateSip(frame, {"A": 0.5, "B": 0.5}, monthly_amount=100.0)

        self.assertEqual(result["Installments"], 2)
        self.assertEqual(result["Invested"], 200.0)
        self.assertEqual(result["CurrentValue"], 300.0)

    def test_trailing_cagr_uses_requested_horizon(self):
        dates = pd.to_datetime(["2021-01-01", "2026-01-01"])
        series = pd.Series([100.0, 200.0], index=dates)

        result = Analysis.TrailingCagr(series, 5)

        self.assertAlmostEqual(result, (2 ** (1 / 5) - 1) * 100, places=2)


if __name__ == "__main__":
    unittest.main()
