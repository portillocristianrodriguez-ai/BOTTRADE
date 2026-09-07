import unittest
import numpy as np
import pandas as pd
import estrategia
from early_signal import _volume_ratio


class OriginVolumeTests(unittest.TestCase):
    def data(self, volumes):
        return pd.DataFrame(dict(open=100., high=101., low=99., close=100., volume=volumes))

    def test_normal_ratio_uses_only_prior_bars(self):
        result = estrategia.calcular_indicadores(self.data([100.] * 99 + [250.]))
        self.assertEqual(result.iloc[-1]['volumen_ratio'], 2.5)
        self.assertTrue(pd.isna(result.iloc[4]['volumen_ratio']))

    def test_bonk_zero_tiny_invalid_and_negative_reference(self):
        for reference in [0., 1e-13, 1e-9, np.nan, np.inf, -10.]:
            with self.subTest(reference=reference):
                result = estrategia.calcular_indicadores(self.data([reference] * 99 + [620.]))
                self.assertTrue(pd.isna(result.iloc[-1]['volumen_ratio']))
                self.assertFalse(np.isinf(result['volumen_ratio']).any())

    def test_invalid_bar_does_not_bridge_reference_window(self):
        data = self.data([100.] * 100)
        data.loc[98, 'volume'] = np.nan
        result = estrategia.calcular_indicadores(data)
        self.assertTrue(pd.isna(result.iloc[-1]['volumen_ratio']))

    def test_early_ratio_rejects_bonk_and_keeps_normal(self):
        self.assertIsNone(_volume_ratio(620., 1e-9))
        self.assertEqual(_volume_ratio(250., 100.), 2.5)
