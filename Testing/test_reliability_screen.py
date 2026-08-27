import unittest

import pandas as pd

from Research.Universe.reliability_screen import (
    BestFrozenFamily,
    CommonTradingDates,
    ResearchBoundaries,
    UnitScore,
)


class ReliabilityScreenTests(unittest.TestCase):
    def test_common_dates_uses_intersection(self):
        dates = pd.date_range("2025-01-01", periods=150, freq="D")
        left = pd.DataFrame({"Date": dates})
        right = pd.DataFrame({"Date": dates[1:]})

        common = CommonTradingDates({"LEFT": left, "RIGHT": right})

        self.assertEqual(common[0], dates[1])
        self.assertEqual(common[-1], dates[-1])

    def test_final_sixty_sessions_stay_sealed(self):
        dates = list(pd.date_range("2025-01-01", periods=220, freq="D"))

        boundaries = ResearchBoundaries(dates)

        self.assertEqual(boundaries["sealed_start"], dates[-60])
        self.assertLess(boundaries["selection_end"], boundaries["sealed_start"])
        self.assertLess(boundaries["development_end"], boundaries["validation_start"])

    def test_best_family_requires_cross_sample_consistency(self):
        results = pd.DataFrame(
            [
                {"Family": "flashy", "Sample": "Development", "Trades": 30, "WinRate": 0.7, "ProfitFactor": 3.0, "Expectancy": 0.01, "MaxDrawdown": -0.02},
                {"Family": "flashy", "Sample": "Validation", "Trades": 20, "WinRate": 0.3, "ProfitFactor": 0.5, "Expectancy": -0.01, "MaxDrawdown": -0.10},
                {"Family": "stable", "Sample": "Development", "Trades": 25, "WinRate": 0.55, "ProfitFactor": 1.2, "Expectancy": 0.002, "MaxDrawdown": -0.03},
                {"Family": "stable", "Sample": "Validation", "Trades": 18, "WinRate": 0.55, "ProfitFactor": 1.1, "Expectancy": 0.001, "MaxDrawdown": -0.03},
            ]
        )

        best = BestFrozenFamily(results)

        self.assertEqual(best["BestFamily"], "stable")
        self.assertTrue(best["StrategyBothPositive"])

    def test_unit_score_clips_to_zero_and_one(self):
        self.assertEqual(UnitScore(-1, 0, 10), 0.0)
        self.assertEqual(UnitScore(11, 0, 10), 1.0)
        self.assertEqual(UnitScore(5, 0, 10), 0.5)


if __name__ == "__main__":
    unittest.main()
