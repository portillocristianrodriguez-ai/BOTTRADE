import unittest

import pandas as pd

import data_quality_hardening


class DataQualityHardeningTests(unittest.TestCase):
    def test_minimum_is_at_least_strategy_requirement(self):
        class Config:
            STRATEGY_MIN_BARS = 14

        self.assertEqual(data_quality_hardening._min_bars(Config), 50)

    def test_minimum_can_be_raised_by_config(self):
        class Config:
            STRATEGY_MIN_BARS = 80

        self.assertEqual(data_quality_hardening._min_bars(Config), 80)

    def test_short_dataframe_is_rejected(self):
        df = pd.DataFrame({"close": range(10)})
        self.assertFalse(data_quality_hardening._es_dataframe_valido(df, 50))

    def test_sufficient_dataframe_is_accepted(self):
        df = pd.DataFrame({"close": range(50)})
        self.assertTrue(data_quality_hardening._es_dataframe_valido(df, 50))


if __name__ == "__main__":
    unittest.main()
