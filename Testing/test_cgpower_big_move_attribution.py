import unittest

import pandas as pd

from Research.CGPOWER.cgpower_big_move_attribution import Event, classify_path, event_windows


class BigMoveAttributionTests(unittest.TestCase):
    def test_classifies_gap_recovery(self):
        row = pd.Series(
            {
                "gap_pct": -5.0,
                "intraday_pct": 2.0,
                "close_position": 0.7,
                "volume_ratio20": 2.0,
                "return_pct": -3.1,
            }
        )
        self.assertEqual(classify_path(row), "negative_gap_recovery")

    def test_classifies_high_volume_intraday_accumulation(self):
        row = pd.Series(
            {
                "gap_pct": 0.2,
                "intraday_pct": 4.0,
                "close_position": 0.9,
                "volume_ratio20": 3.0,
                "return_pct": 4.2,
            }
        )
        self.assertEqual(classify_path(row), "intraday_accumulation")

    def test_after_market_event_uses_explicit_reaction_session(self):
        index = pd.to_datetime(["2025-01-28", "2025-01-29", "2025-01-30"])
        daily = pd.DataFrame(
            index=index,
            data={
                "pre5_pct": [0.0] * 3,
                "pre20_pct": [0.0] * 3,
                "return_pct": [-3.0, 7.5, 1.0],
                "gap_pct": [0.0] * 3,
                "intraday_pct": [-3.0, 7.0, 1.0],
                "range_pct": [4.0, 8.0, 2.0],
                "volume_ratio20": [2.0, 4.0, 1.0],
                "close_position": [0.1, 0.9, 0.5],
                "post1_pct": [7.5, 1.0, 0.0],
                "post5_pct": [0.0] * 3,
                "post20_pct": [0.0] * 3,
                "path_type": ["ordinary", "intraday_accumulation", "ordinary"],
            },
        )
        event = Event(
            "2025-01-28",
            "2025-01-29",
            "After-close result",
            "Earnings",
            "Positive",
            "https://example.com",
        )
        result = event_windows([event], daily)
        self.assertEqual(result.loc[0, "trading_date"], pd.Timestamp("2025-01-29"))
        self.assertEqual(result.loc[0, "event_return_pct"], 7.5)


if __name__ == "__main__":
    unittest.main()
