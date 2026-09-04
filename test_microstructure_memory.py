import time
import unittest

from microstructure_memory import evaluar_microestructura, limpiar, registrar


class MicrostructureMemoryTests(unittest.TestCase):
    def tearDown(self):
        limpiar("BTC/USD")

    def test_deterioro_aislado_no_confirma(self):
        registrar("BTC/USD", imbalance=-0.60, spread_pct=1.20)
        result = evaluar_microestructura("BTC/USD", min_samples=3, window_seconds=180)
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["samples"], 1)

    def test_deterioro_persistente_confirma(self):
        now = time.time()
        for i in range(3):
            registrar("BTC/USD", imbalance=-0.60, spread_pct=1.20, timestamp=now + i)
        result = evaluar_microestructura("BTC/USD", min_samples=3, window_seconds=180)
        self.assertTrue(result["confirmed"])
        self.assertGreaterEqual(result["score"], 75.0)
        self.assertEqual(result["reason"], "capitulacion_liquidity")


if __name__ == "__main__":
    unittest.main()
