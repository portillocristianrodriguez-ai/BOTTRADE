import unittest

import pandas as pd

from backtest_engine import Trade
from research_lab import monte_carlo, summarize_walk_forward, walk_forward


class ResearchLabTests(unittest.TestCase):
    def test_monte_carlo_is_deterministic_with_seed(self):
        trades = [
            Trade(0, 1, 100, 102, 1, 2, 2.0, "take_profit"),
            Trade(1, 2, 100, 99, 1, -1, -1.0, "stop"),
            Trade(2, 3, 100, 101, 1, 1, 1.0, "signal"),
        ]
        first = monte_carlo(trades, simulations=200, seed=7)
        second = monte_carlo(trades, simulations=200, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first.simulations, 200)

    def test_walk_forward_only_reports_out_of_sample_windows(self):
        idx = pd.date_range("2026-01-01", periods=20, freq="h", tz="UTC")
        df = pd.DataFrame({
            "open": range(100, 120),
            "high": range(101, 121),
            "low": range(99, 119),
            "close": range(100, 120),
            "volume": [1000] * 20,
        }, index=idx)
        windows = walk_forward(df, signal_fn=lambda _: "ESPERAR", train_bars=8, test_bars=4)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0].test_start, idx[8])
        self.assertEqual(windows[0].test_end, idx[11])
        summary = summarize_walk_forward(windows)
        self.assertEqual(summary["windows"], 2)
        self.assertEqual(summary["consistency_pct"], 0.0)

    def test_monte_carlo_requires_enough_trades(self):
        trade = Trade(0, 1, 100, 101, 1, 1, 1.0, "signal")
        with self.assertRaises(ValueError):
            monte_carlo([trade], simulations=200)


if __name__ == "__main__":
    unittest.main()
