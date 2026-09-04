import unittest

import numpy as np
import pandas as pd

from portfolio_backtest import run_portfolio


class PortfolioBacktestTests(unittest.TestCase):
    def _data(self, start, prices):
        idx = pd.date_range(start, periods=len(prices), freq="D", tz="UTC")
        close = np.asarray(prices, dtype=float)
        return pd.DataFrame({
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1000.0,
        }, index=idx)

    def test_signals_execute_next_bar_and_share_cash(self):
        a = self._data("2025-01-01", np.linspace(100, 120, 12))
        b = self._data("2025-01-01", np.linspace(50, 70, 12))

        def signal(symbol, df):
            return "COMPRAR" if len(df) == 5 else "ESPERAR"

        stats, equity, trades = run_portfolio(
            {"AAA": a, "BBB": b},
            signal_fn=signal,
            risk_per_trade_pct=0.02,
            max_positions=2,
            max_total_exposure_pct=0.50,
            max_single_position_pct=0.20,
        )
        self.assertEqual(stats["symbols_traded"], 2)
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0].entry_time, a.index[5])
        self.assertEqual(trades[1].entry_time, b.index[5])
        self.assertEqual(float(equity.loc[a.index[4], "equity"]), 100000.0)

    def test_no_signals_preserves_equity(self):
        data = self._data("2025-01-01", np.linspace(100, 110, 10))
        stats, equity, trades = run_portfolio({"AAA": data}, signal_fn=lambda *_: "ESPERAR")
        self.assertEqual(stats["trades"], 0)
        self.assertTrue((equity["equity"] == 100000.0).all())
        self.assertEqual(trades, [])


if __name__ == "__main__":
    unittest.main()
