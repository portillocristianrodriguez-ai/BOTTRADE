import unittest
from dataclasses import dataclass

from trade_analysis import calculate_metrics, reconstruct_trades


@dataclass
class Order:
    symbol: str
    side: str
    status: str = "filled"
    filled_qty: float = 0.0
    filled_avg_price: float = 0.0
    id: str = ""
    filled_at: str | None = None
    order_class: str = "simple"
    type: str = "market"
    legs: list | None = None


class TradeAnalysisTests(unittest.TestCase):
    def test_reconstructs_fifo_and_partial_exit(self):
        orders = [
            Order("AAPL", "buy", filled_qty=10, filled_avg_price=100, id="b1", filled_at="2026-01-01T10:00:00+00:00"),
            Order("AAPL", "buy", filled_qty=5, filled_avg_price=110, id="b2", filled_at="2026-01-01T11:00:00+00:00"),
            Order("AAPL", "sell", filled_qty=12, filled_avg_price=120, id="s1", filled_at="2026-01-01T12:00:00+00:00"),
        ]

        trades = reconstruct_trades(orders)

        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0].qty, 10)
        self.assertEqual(trades[0].pnl, 200)
        self.assertEqual(trades[1].qty, 2)
        self.assertEqual(trades[1].pnl, 20)

    def test_ignores_stop_protection(self):
        orders = [
            Order("MSFT", "buy", filled_qty=10, filled_avg_price=100, id="b1", filled_at="2026-01-01T10:00:00+00:00"),
            Order("MSFT", "sell", filled_qty=10, filled_avg_price=95, id="sl1", filled_at="2026-01-01T11:00:00+00:00", type="stop"),
        ]

        self.assertEqual(reconstruct_trades(orders), [])

    def test_ignores_oco_protection(self):
        orders = [
            Order("NVDA", "buy", filled_qty=2, filled_avg_price=100, id="b1", filled_at="2026-01-01T10:00:00+00:00"),
            Order("NVDA", "sell", filled_qty=2, filled_avg_price=110, id="oco1", filled_at="2026-01-01T11:00:00+00:00", order_class="oco"),
        ]

        self.assertEqual(reconstruct_trades(orders), [])

    def test_metrics(self):
        orders = [
            Order("AAPL", "buy", filled_qty=1, filled_avg_price=100, id="b1", filled_at="2026-01-01T10:00:00+00:00"),
            Order("AAPL", "sell", filled_qty=1, filled_avg_price=110, id="s1", filled_at="2026-01-01T11:00:00+00:00"),
            Order("MSFT", "buy", filled_qty=1, filled_avg_price=100, id="b2", filled_at="2026-01-01T12:00:00+00:00"),
            Order("MSFT", "sell", filled_qty=1, filled_avg_price=90, id="s2", filled_at="2026-01-01T13:00:00+00:00"),
        ]

        metrics = calculate_metrics(reconstruct_trades(orders))

        self.assertEqual(metrics["trades"], 2)
        self.assertEqual(metrics["wins"], 1)
        self.assertEqual(metrics["losses"], 1)
        self.assertEqual(metrics["win_rate_pct"], 50.0)
        self.assertEqual(metrics["net_profit_before_fees"], 0.0)
        self.assertEqual(metrics["profit_factor"], 1.0)
        self.assertEqual(metrics["max_drawdown"], 10.0)


if __name__ == "__main__":
    unittest.main()
