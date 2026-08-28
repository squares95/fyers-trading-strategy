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
    / "PPFCF"
    / "dip_entry_research.py"
)
SPEC = importlib.util.spec_from_file_location("dip_entry_research", MODULE_PATH)
Research = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = Research
SPEC.loader.exec_module(Research)


class DipEntryResearchTests(unittest.TestCase):
    def test_signal_is_bought_at_next_available_nav(self):
        nav = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                "NAV": [100.0, 80.0, 120.0],
            }
        )
        signal = pd.Series([True, False, False])
        period = Research.Period("Test", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31"))

        result = Research.MonthlyInvestmentResult(
            nav,
            signal,
            period,
            wait_days=2,
            core_fraction=0.0,
        )

        self.assertAlmostEqual(result["Units"], Research.MONTHLY_CONTRIBUTION / 80.0)
        self.assertEqual(result["SignalBuys"], 1)

    def test_final_oos_cannot_change_rule_selection(self):
        rows = []
        for period, lift in (("Development", 1.0), ("Validation", 1.0), ("FinalOOS", -99.0)):
            rows.append(
                {
                    "Rule": "Candidate",
                    "Period": period,
                    "Count60": 20,
                    "MedianLift60Pct": lift,
                    "MedianLift120Pct": lift,
                }
            )

        selected, _ = Research.SelectResearchRule(pd.DataFrame(rows))

        self.assertEqual(selected, "Candidate")

    def test_market_shock_diagnostics_use_next_nav_and_report_false_start(self):
        dates = pd.bdate_range("2024-08-26", periods=80)
        nav = pd.DataFrame({"Date": dates, "NAV": [100.0] * 80})
        nav.loc[1, "NAV"] = 99.0
        nav.loc[2, "NAV"] = 98.0
        nav = Research.AddFeatures(nav)
        nifty = pd.DataFrame({"Date": dates, "NiftyClose": [100.0] * 80})
        nifty.loc[1:, "NiftyClose"] = 98.0

        result = Research.MarketShockDiagnostics(nav, nifty).set_index("Rule")

        day_rule = result.loc["NiftyDayDown1"]
        self.assertEqual(day_rule["Signals"], 1)
        self.assertEqual(pd.Timestamp(day_rule["FirstEntry"]), dates[2])
        self.assertEqual(day_rule["FellFurtherWithin5DaysPct"], 0.0)


if __name__ == "__main__":
    unittest.main()
