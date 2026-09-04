import unittest

from worker import _es_crypto_ticker, _observacion_valida_crypto


class WorkerHardeningTests(unittest.TestCase):
    def test_crypto_ticker_detectado_por_par(self):
        self.assertTrue(_es_crypto_ticker(type("M", (), {})(), "BTC/USD"))

    def _df(self, atr=1):
        class Row:
            def get(self, key):
                return {
                    "close": 100,
                    "atr": atr,
                    "rsi": 55,
                    "ema_rapida": 101,
                    "ema_lenta": 99,
                    "ema_tendencia": 95,
                }.get(key)

        class ILoc:
            def __getitem__(self, _):
                return Row()

        return type("DF", (), {"empty": False, "iloc": ILoc()})()

    def test_observacion_crypto_rechaza_atr_cero(self):
        ok, reason = _observacion_valida_crypto(self._df(atr=0))
        self.assertFalse(ok)
        self.assertEqual(reason, "atr_no_disponible")

    def test_observacion_crypto_acepta_indicadores_validos(self):
        ok, reason = _observacion_valida_crypto(self._df(atr=1))
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")


if __name__ == "__main__":
    unittest.main()
