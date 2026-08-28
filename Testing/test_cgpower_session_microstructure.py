import unittest

import pandas as pd

from Research.CGPOWER.cgpower_session_microstructure import (
    Rule,
    evaluate_rule,
    simulate_trade_detail,
)
from Research.CGPOWER.premarket_context_analysis import make_available_next_day


class SessionMicrostructureTests(unittest.TestCase):
    def test_same_bar_stop_and_target_uses_conservative_stop(self):
        day = pd.DataFrame(
            {
                "Datetime": pd.to_datetime(["2026-01-05 09:30"]),
                "Time": ["09:30"],
                "Open": [100.0],
                "High": [103.0],
                "Low": [97.0],
                "Close": [101.0],
            }
        )
        trade = simulate_trade_detail(day, 1, "09:30", "09:30", 98.0, 102.0)
        self.assertEqual(trade["ExitReason"], "stop")
        self.assertEqual(trade["ExitPrice"], 98.0)

    def test_signal_enters_at_requested_next_bar_open(self):
        day = pd.DataFrame(
            {
                "Datetime": pd.to_datetime(["2026-01-05 09:30", "2026-01-05 09:31"]),
                "Time": ["09:30", "09:31"],
                "Open": [100.0, 101.0],
                "High": [100.5, 102.0],
                "Low": [99.5, 100.5],
                "Close": [100.2, 101.5],
            }
        )
        trade = simulate_trade_detail(day, 1, "09:31", "09:31", 99.0, 103.0)
        self.assertEqual(trade["EntryPrice"], 101.0)

    def test_opening_rule_supports_stricter_maximum_risk(self):
        date = pd.Timestamp("2026-01-02")
        times = pd.date_range("2026-01-02 09:15", periods=360, freq="min")
        minutes = pd.DataFrame(
            {
                "Datetime": times,
                "Date": date,
                "Time": times.strftime("%H:%M"),
                "Open": 101.0,
                "High": 101.5,
                "Low": 100.0,
                "Close": 101.0,
                "Volume": 1000,
            }
        )
        daily = pd.DataFrame(
            {
                "r15_atr": [0.5],
                "opening15_close_position": [0.9],
                "opening15_rvol20": [1.2],
                "or_low": [100.0],
                "or_high": [102.0],
            },
            index=[date],
        )
        rule = Rule("test", 0.15, 0.7, 0.5, 2.0)

        rejected = evaluate_rule(rule, daily, minutes, 1.0, max_risk_pct=0.008)
        accepted = evaluate_rule(rule, daily, minutes, 1.0, max_risk_pct=0.012)

        self.assertTrue(rejected.empty)
        self.assertEqual(len(accepted), 1)

    def test_completed_external_session_becomes_available_next_day(self):
        source = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-05"]),
                "Close": [100.0],
                "Return": [0.01],
            }
        )
        available = make_available_next_day(source, "test")
        self.assertEqual(available.loc[0, "AvailableDate"], pd.Timestamp("2026-01-06"))


if __name__ == "__main__":
    unittest.main()
