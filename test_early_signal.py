import unittest

import numpy as np
import pandas as pd

import early_signal


class EarlySignalTests(unittest.TestCase):
    def _frame(self):
        n = 70
        close = np.array([100 + (i * 0.04) + (0.15 if i % 4 == 0 else -0.03) for i in range(n)], float)
        close[-7:] = [102.8, 102.5, 102.9, 102.7, 103.0, 102.95, 103.5]
        high = close + 0.12
        low = close - 0.12
        volume = np.full(n, 1000.0)
        volume[-1] = 1500.0
        return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": volume})

    def test_detects_confluence_early(self):
        result = early_signal.evaluar(self._frame(), min_score=72)
        self.assertGreaterEqual(result["score"], 72)
        self.assertTrue(result["comprar_temprano"])
        self.assertIn("momentum temprano", result["motivos"])

    def test_does_not_use_future_rows(self):
        frame = self._frame()
        prefix = frame.iloc[:-5].copy()
        prefix_result = early_signal.evaluar(prefix, min_score=72)
        future_changed = frame.copy()
        future_changed.iloc[-5:, future_changed.columns.get_loc("close")] *= 0.5
        future_changed.iloc[-5:, future_changed.columns.get_loc("high")] *= 0.5
        future_result = early_signal.evaluar(future_changed.iloc[:-5], min_score=72)
        self.assertEqual(prefix_result["score"], future_result["score"])
        self.assertEqual(prefix_result["comprar_temprano"], future_result["comprar_temprano"])

    def test_flat_market_does_not_trigger(self):
        frame = self._frame()
        frame["close"] = 100.0
        frame["high"] = 100.1
        frame["low"] = 99.9
        frame["open"] = 100.0
        frame["volume"] = 1000.0
        result = early_signal.evaluar(frame, min_score=72)
        self.assertFalse(result["comprar_temprano"])

    def test_rejects_near_zero_volume_reference(self):
        frame = self._frame()
        frame["volume"] = 0.0
        frame.iloc[:-1, frame.columns.get_loc("volume")] = 1e-13
        frame.iloc[-1, frame.columns.get_loc("volume")] = 1.0
        result = early_signal.evaluar(frame)
        self.assertIsNone(result["volume_ratio"])


if __name__ == "__main__":
    unittest.main()
