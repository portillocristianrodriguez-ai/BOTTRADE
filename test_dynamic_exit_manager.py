import unittest

from dynamic_exit_manager import (
    calcular_retroceso_trailing,
    limpiar_trailing,
    obtener_trailing_estricto,
    registrar_trailing_mas_estricto,
)


class DynamicExitManagerTests(unittest.TestCase):
    def tearDown(self):
        limpiar_trailing("BTC/USD")

    def test_retroceso_desde_maximo(self):
        self.assertAlmostEqual(calcular_retroceso_trailing(100, 98), 0.02)
        self.assertEqual(calcular_retroceso_trailing(100, 101), 0.0)
        self.assertEqual(calcular_retroceso_trailing(0, 98), 0.0)

    def test_trailing_se_hace_mas_estricto_y_no_se_relaja(self):
        self.assertAlmostEqual(registrar_trailing_mas_estricto("BTC/USD", 0.012), 0.012)
        self.assertAlmostEqual(registrar_trailing_mas_estricto("BTC/USD", 0.008), 0.008)
        self.assertAlmostEqual(registrar_trailing_mas_estricto("BTC/USD", 0.020), 0.008)
        self.assertAlmostEqual(obtener_trailing_estricto("BTC/USD"), 0.008)

    def test_trailing_minimo_de_seguridad(self):
        self.assertAlmostEqual(registrar_trailing_mas_estricto("BTC/USD", 0.001), 0.0025)


if __name__ == "__main__":
    unittest.main()
