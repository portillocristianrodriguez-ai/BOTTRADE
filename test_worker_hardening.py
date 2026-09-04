import unittest

from worker import _es_crypto_ticker, _observacion_valida_crypto


class WorkerHardeningTests(unittest.TestCase):
    def test_crypto_ticker_detectado_por_par(self):
        self.assertTrue(_es_crypto_ticker(type("M", (), {})(), "BTC/USD"))

    def test_observacion_crypto_rechaza_atr_cero(self):
        class Row:
            def get(self, key):
                values = {
                    "close": 100,
                    "atr": 0,
                    "rsi": 50,
                    "ema_rapida": 100,
                    "ema_lenta": 99,
                    "ema_tendencia": 95,
                }
                return values.get(key)

        class DF:
            empty = False
            def iloc(self):
                return None

        df = type("DF", (), {"empty": False, "iloc": {"__getitem__": lambda self, _: Row()}})()
        ok, reason = _observacion_valida_crypto(df)
        self.assertFalse(ok)
        self.assertEqual(reason, "atr_no_disponible")

    def test_observacion_crypto_acepta_indicadores_validos(self):
        class Row:
            def get(self, key):
                return {
                    "close": 100,
                    "atr": 1,
                    "rsi": 55,
                    "ema_rapida": 101,
                    "ema_lenta": 99,
                    "ema_tendencia": 95,
                }.get(key)

        class ILoc:
            def __getitem__(self, _):
                return Row()

        df = type("DF", (), {"empty": False, "iloc": ILoc()})()
        ok, reason = _observacion_valida_crypto(df)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")


if __name__ == "__main__":
    unittest.main()
