import unittest

import numpy as np
import pandas as pd

import estrategia


def _df(rows=180):
    index = pd.date_range("2026-01-01", periods=rows, freq="5min", tz="UTC")
    close = 100 + np.linspace(0, 12, rows) + np.sin(np.arange(rows) / 5.0)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(rows, 1000.0),
        },
        index=index,
    )


class StrategyCompatibilityTests(unittest.TestCase):
    def test_generar_senal_publica_existe_y_no_falla(self):
        self.assertTrue(callable(getattr(estrategia, "generar_senal", None)))
        self.assertIn(estrategia.generar_senal(_df()), {"COMPRAR", "VENDER", "ESPERAR"})

    def test_mtf_expone_alias_compatible(self):
        result = estrategia._confirmacion_multitimeframe(_df())
        self.assertIn("alineacion", result)
        self.assertIn("mtf_alineacion", result)
        self.assertEqual(result["mtf_alineacion"], result["alineacion"])


if __name__ == "__main__":
    unittest.main()
