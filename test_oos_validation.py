import unittest

import numpy as np
import pandas as pd

from oos_validation import score_oos, validar_walk_forward


class OOSValidationTests(unittest.TestCase):
    def _data(self, start="2022-01-01", n=900):
        idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
        close = np.linspace(100.0, 180.0, n)
        return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": 1000.0}, index=idx)

    def test_walk_forward_does_not_trade_before_oos_start(self):
        data = {"AAA": self._data()}
        calls = []

        def signal(symbol, df):
            calls.append((symbol, df.index[-1]))
            return "COMPRAR" if len(df) > 300 else "ESPERAR"

        rows = validar_walk_forward(data, signal, [("2023-01-01", "2023-12-31")], fee_bps=0, slippage_bps=0)
        self.assertTrue(rows)
        self.assertTrue(all(ts >= pd.Timestamp("2023-01-01", tz="UTC") for _, ts in calls))

    def test_ranking_penalizes_insufficient_trades(self):
        rows = [
            {"symbol": "GOOD", "return_pct": 10, "cagr_pct": 10, "sharpe": 1, "sortino": 1.2, "calmar": 1, "max_drawdown_pct": -10, "trades": 12, "profit_factor": 1.5},
            {"symbol": "WEAK", "return_pct": 20, "cagr_pct": 20, "sharpe": 2, "sortino": 2, "calmar": 2, "max_drawdown_pct": -8, "trades": 2, "profit_factor": 3},
        ]
        ranked = score_oos(rows, min_trades=5)
        self.assertEqual(ranked[0]["symbol"], "GOOD")
        self.assertLess(ranked[1]["score"], ranked[0]["score"])


if __name__ == "__main__":
    unittest.main()
