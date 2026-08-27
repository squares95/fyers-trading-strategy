import unittest

import pandas as pd

from Download import ResolveFyersSymbol
from Research.CGPOWER.cgpower_session_microstructure import COST_RATE
from Research.HDFCBANK.hdfcbank_index_aligned_strategy import passes_research_gate, simulate


class HdfcBankIndexAlignedTests(unittest.TestCase):
    def test_bank_nifty_alias_uses_index_symbol(self):
        self.assertEqual(ResolveFyersSymbol("BANKNIFTY"), "NSE:NIFTYBANK-INDEX")
        self.assertEqual(ResolveFyersSymbol("NIFTYBANK"), "NSE:NIFTYBANK-INDEX")

    def test_signal_enters_at_next_minute_open_and_includes_cost(self):
        day = pd.DataFrame(
            {
                "Datetime": pd.to_datetime(["2026-01-02 09:45", "2026-01-02 09:46"]),
                "Time": ["09:45", "09:46"],
                "H_Open": [100.0, 101.0],
                "H_High": [100.5, 104.0],
                "H_Low": [100.5, 100.6],
                "H_Close": [100.0, 103.0],
                "H_VWAP": [100.0, 101.0],
                "N_FromOpen": [0.001, 0.002],
                "H_VWAPDist": [0.0, 0.02],
            }
        )

        trade = simulate(day, signal_idx=0, direction=1, stop_lookback=1, target_r=2.0)

        self.assertIsNotNone(trade)
        self.assertEqual(trade["EntryTime"], "09:46")
        self.assertEqual(trade["EntryPrice"], 101.0)
        self.assertAlmostEqual(trade["GrossReturn"], 1 / 101)
        self.assertAlmostEqual(trade["NetReturn"], 1 / 101 - COST_RATE)

    def test_rejects_stop_wider_than_point_eight_percent(self):
        day = pd.DataFrame(
            {
                "Datetime": pd.to_datetime(["2026-01-02 09:45", "2026-01-02 09:46"]),
                "Time": ["09:45", "09:46"],
                "H_Open": [100.0, 101.0],
                "H_High": [100.5, 102.0],
                "H_Low": [99.0, 100.0],
                "H_Close": [100.0, 101.5],
                "H_VWAP": [100.0, 100.5],
                "N_FromOpen": [0.001, 0.002],
                "H_VWAPDist": [0.0, 0.01],
            }
        )

        self.assertIsNone(simulate(day, signal_idx=0, direction=1, stop_lookback=1, target_r=2.0))

    def test_research_gate_requires_both_samples_to_be_profitable(self):
        passing = pd.DataFrame(
            {
                "Sample": ["Discovery", "Holdout"],
                "Trades": [30, 25],
                "ProfitFactor": [1.2, 1.1],
                "Expectancy": [0.001, 0.0005],
            }
        )
        failing = passing.copy()
        failing.loc[failing["Sample"] == "Holdout", "ProfitFactor"] = 0.9

        self.assertTrue(passes_research_gate(passing))
        self.assertFalse(passes_research_gate(failing))


if __name__ == "__main__":
    unittest.main()
