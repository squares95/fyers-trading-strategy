import unittest

from Research.Universe.finalist_validation import PassesFinal, PassesSelection


class FinalistValidationTests(unittest.TestCase):
    def test_selection_requires_both_periods(self):
        development = {
            "Trades": 30,
            "ProfitFactor": 1.3,
            "Expectancy": 0.001,
            "MaxDrawdown": -0.05,
        }
        validation = {
            "Trades": 15,
            "ProfitFactor": 1.2,
            "Expectancy": 0.001,
            "MaxDrawdown": -0.04,
        }

        self.assertTrue(PassesSelection(development, validation))
        validation["Expectancy"] = -0.0001
        self.assertFalse(PassesSelection(development, validation))

    def test_final_gate_rejects_tiny_samples(self):
        final = {
            "Trades": 7,
            "ProfitFactor": 2.0,
            "Expectancy": 0.002,
            "MaxDrawdown": -0.02,
        }

        self.assertFalse(PassesFinal(final))
        final["Trades"] = 8
        self.assertTrue(PassesFinal(final))


if __name__ == "__main__":
    unittest.main()
