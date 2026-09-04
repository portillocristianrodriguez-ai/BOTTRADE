import unittest
import numpy as np
import pandas as pd

from backtest_engine import run, resumen


class BacktestEngineTests(unittest.TestCase):
    def _data(self, n=260):
        idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
        close = np.linspace(100.0, 160.0, n)
        return pd.DataFrame({
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(n, 1000.0),
        }, index=idx)

    def test_no_signal_means_no_trades(self):
        data = self._data()
        stats, equity, trades = run(data, signal_fn=lambda _: "ESPERAR")
        self.assertEqual(stats["trades"], 0)
        self.assertEqual(stats["final_equity"], 100000.0)
        self.assertEqual(len(equity), len(data))
        self.assertEqual(trades, [])

    def test_entry_is_next_bar_open(self):
        data = self._data()
        calls = {"n": 0}

        def signal(df):
            calls["n"] += 1
            return "COMPRAR" if len(df) == 210 else "VENDER" if len(df) == 211 else "ESPERAR"

        stats, _, trades = run(data, signal_fn=signal, slippage_bps=0, fee_bps=0)
        self.assertGreaterEqual(stats["trades"], 1)
        self.assertEqual(trades[0].entry_time, data.index[210])
        self.assertEqual(trades[0].entry, float(data.iloc[210]["open"]))

    def test_summary_drawdown_and_profit_factor(self):
        trades = []
        equity = pd.Series([100, 110, 99, 120], index=pd.date_range("2024-01-01", periods=4))
        stats = resumen(trades, equity, 100)
        self.assertAlmostEqual(stats["total_return_pct"], 20.0)
        self.assertLess(stats["max_drawdown_pct"], 0.0)
        self.assertEqual(stats["trades"], 0)


if __name__ == "__main__":
    unittest.main()
