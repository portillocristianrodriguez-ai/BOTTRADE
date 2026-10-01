import unittest

import pandas as pd

import config

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
        # Each slice must satisfy the real backtest warm-up requirement.
        window_bars = int(config.EMA_TENDENCIA) + 5
        n = 3 * window_bars  # One training slice followed by two OOS slices.
        idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
        df = pd.DataFrame({
            "open": range(100, 100 + n),
            "high": range(101, 101 + n),
            "low": range(99, 99 + n),
            "close": range(100, 100 + n),
            "volume": [1000] * n,
        }, index=idx)
        windows = walk_forward(
            df, signal_fn=lambda _: "ESPERAR",
            train_bars=window_bars, test_bars=window_bars,
        )
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0].test_start, idx[window_bars])
        self.assertEqual(windows[0].test_end, idx[2 * window_bars - 1])
        self.assertEqual(windows[1].test_start, idx[2 * window_bars])
        self.assertEqual(windows[1].test_end, idx[-1])
        for window in windows:
            self.assertLess(window.train_end, window.test_start)
        summary = summarize_walk_forward(windows)
        self.assertEqual(summary["windows"], 2)
        self.assertEqual(summary["consistency_pct"], 0.0)

    def test_walk_forward_selects_candidate_only_from_train_slice(self):
        test_bars = int(config.EMA_TENDENCIA) + 5
        train_bars = 2 * test_bars
        n = train_bars + test_bars  # Exactly one candidate-selection window.
        idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
        df = pd.DataFrame({
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [1000.0] * n,
        }, index=idx)
        calls = []

        def factory(params):
            calls.append(dict(params))
            return lambda _: "ESPERAR"

        windows = walk_forward(
            df,
            train_bars=train_bars,
            test_bars=test_bars,
            parameter_grid=[{"risk_per_trade_pct": 0.01}, {"risk_per_trade_pct": 0.02}],
            signal_factory=factory,
            min_train_trades=0,
        )
        self.assertEqual(len(windows), 1)
        self.assertIn(windows[0].selected_params, ({"risk_per_trade_pct": 0.01}, {"risk_per_trade_pct": 0.02}))
        self.assertIsNotNone(windows[0].train_stats)
        self.assertEqual(calls, [
            {"risk_per_trade_pct": 0.01},
            {"risk_per_trade_pct": 0.02},
        ])

    def test_walk_forward_requires_factory_for_parameter_grid(self):
        idx = pd.date_range("2026-01-01", periods=12, freq="h", tz="UTC")
        df = pd.DataFrame({
            "open": [100.0] * 12,
            "high": [101.0] * 12,
            "low": [99.0] * 12,
            "close": [100.0] * 12,
            "volume": [1000.0] * 12,
        }, index=idx)
        with self.assertRaises(ValueError):
            walk_forward(df, train_bars=6, test_bars=4, parameter_grid=[{}])

    def test_monte_carlo_requires_enough_trades(self):
        trade = Trade(0, 1, 100, 101, 1, 1, 1.0, "signal")
        with self.assertRaises(ValueError):
            monte_carlo([trade], simulations=200)


if __name__ == "__main__":
    unittest.main()
