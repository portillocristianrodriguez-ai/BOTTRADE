import unittest

import pandas as pd

import strategy_data_hardening


class StrategyDataHardeningTests(unittest.TestCase):
    def test_invalid_volume_denominator_becomes_neutral(self):
        df = pd.DataFrame({
            "volume": [100.0, 0.0, 50.0],
            "volumen_media": [10.0, 0.0, 0.0],
            "volumen_media_corta": [5.0, 0.0, 0.0],
            "volumen_ratio": [10.0, 0.0, 0.0],
            "aceleracion_volumen": [20.0, 0.0, 0.0],
        })
        out = strategy_data_hardening._sanear_indicadores(df)
        self.assertEqual(float(out.loc[1, "volumen_ratio"]), 0.0)
        self.assertEqual(float(out.loc[2, "volumen_ratio"]), 0.0)
        self.assertEqual(float(out.loc[1, "aceleracion_volumen"]), 0.0)

    def test_finite_normal_ratio_is_preserved(self):
        df = pd.DataFrame({
            "volume": [100.0],
            "volumen_media": [20.0],
            "volumen_media_corta": [25.0],
        })
        out = strategy_data_hardening._sanear_indicadores(df)
        self.assertAlmostEqual(float(out.loc[0, "volumen_ratio"]), 5.0)
        self.assertAlmostEqual(float(out.loc[0, "aceleracion_volumen"]), 4.0)

    def test_non_finite_values_become_neutral(self):
        df = pd.DataFrame({
            "volume": [float("inf"), 100.0],
            "volumen_media": [10.0, float("nan")],
            "volumen_media_corta": [5.0, 0.0],
        })
        out = strategy_data_hardening._sanear_indicadores(df)
        self.assertEqual(float(out.loc[0, "volumen_ratio"]), 0.0)
        self.assertEqual(float(out.loc[1, "volumen_ratio"]), 0.0)


if __name__ == "__main__":
    unittest.main()
