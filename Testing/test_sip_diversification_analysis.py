from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "Research"
    / "MutualFunds"
    / "PortfolioComparison"
    / "sip_diversification_analysis.py"
)
SPEC = importlib.util.spec_from_file_location("sip_diversification_analysis", MODULE_PATH)
Analysis = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = Analysis
SPEC.loader.exec_module(Analysis)


class SipDiversificationAnalysisTests(unittest.TestCase):
    def test_etf_history_parser_flattens_and_sorts(self):
        html = """
        <html><body><h1>TESTETF Historical Data</h1><table>
        <tr><th>Date</th><th>Price</th><th>Open</th><th>High</th><th>Low</th><th>Volume</th><th>Change(%)</th></tr>
        <tr><td>02 Jan 2026</td><td>101</td><td>100</td><td>102</td><td>99</td><td>1,000</td><td>1%</td></tr>
        <tr><td>01 Jan 2026</td><td>100</td><td>100</td><td>101</td><td>99</td><td>900</td><td>0%</td></tr>
        </table></body></html>
        """

        result = Analysis.ParseEtfHistory(html, "TESTETF")

        self.assertEqual(result["Date"].dt.strftime("%Y-%m-%d").tolist(), ["2026-01-01", "2026-01-02"])
        self.assertEqual(result["Close"].tolist(), [100, 101])
        self.assertEqual(result["Volume"].tolist(), [900, 1000])

    def test_etf_sip_uses_whole_units_and_carries_cash(self):
        dates = pd.to_datetime(["2026-07-01", "2026-08-03", "2026-08-24"])
        frame = pd.DataFrame({"Date": dates, "Close": [60.0, 80.0, 100.0]})

        result = Analysis.SimulateSip(
            "ETF",
            frame,
            100.0,
            valuation_date=pd.Timestamp("2026-08-24"),
            months=2,
            sip_day=1,
            whole_units=True,
        )

        self.assertEqual(result.Units, 2.0)
        self.assertEqual(result.Cash, 60.0)
        self.assertEqual(result.CurrentValue, 260.0)

    def test_mutual_fund_sip_uses_fractional_units(self):
        dates = pd.to_datetime(["2026-07-01", "2026-08-03", "2026-08-24"])
        frame = pd.DataFrame({"Date": dates, "Close": [40.0, 50.0, 60.0]})

        result = Analysis.SimulateSip(
            "MF",
            frame,
            100.0,
            valuation_date=pd.Timestamp("2026-08-24"),
            months=2,
            sip_day=1,
            whole_units=False,
        )

        self.assertEqual(result.Units, 4.5)
        self.assertAlmostEqual(result.Cash, 0.0)
        self.assertEqual(result.CurrentValue, 270.0)

    def test_build_months_creates_exactly_eighteen_installments(self):
        months = Analysis.BuildMonths(pd.Timestamp("2026-08-24"), 18)

        self.assertEqual(len(months), 18)
        self.assertEqual(str(months[0]), "2025-03")
        self.assertEqual(str(months[-1]), "2026-08")

    def test_build_months_supports_two_year_comparison(self):
        months = Analysis.BuildMonths(pd.Timestamp("2026-08-24"), 24)

        self.assertEqual(len(months), 24)
        self.assertEqual(str(months[0]), "2024-09")
        self.assertEqual(str(months[-1]), "2026-08")


if __name__ == "__main__":
    unittest.main()
