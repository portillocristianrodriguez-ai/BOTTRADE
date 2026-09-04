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


def test_reconstructs_fifo_and_partial_exit():
    orders = [
        Order("AAPL", "buy", filled_qty=10, filled_avg_price=100, id="b1", filled_at="2026-01-01T10:00:00+00:00"),
        Order("AAPL", "buy", filled_qty=5, filled_avg_price=110, id="b2", filled_at="2026-01-01T11:00:00+00:00"),
        Order("AAPL", "sell", filled_qty=12, filled_avg_price=120, id="s1", filled_at="2026-01-01T12:00:00+00:00"),
    ]

    trades = reconstruct_trades(orders)

    assert len(trades) == 2
    assert trades[0].qty == 10
    assert trades[0].pnl == 200
    assert trades[1].qty == 2
    assert trades[1].pnl == 20


def test_ignores_stop_protection():
    orders = [
        Order("MSFT", "buy", filled_qty=10, filled_avg_price=100, id="b1", filled_at="2026-01-01T10:00:00+00:00"),
        Order("MSFT", "sell", filled_qty=10, filled_avg_price=95, id="sl1", filled_at="2026-01-01T11:00:00+00:00", type="stop"),
    ]

    assert reconstruct_trades(orders) == []


def test_metrics():
    orders = [
        Order("AAPL", "buy", filled_qty=1, filled_avg_price=100, id="b1", filled_at="2026-01-01T10:00:00+00:00"),
        Order("AAPL", "sell", filled_qty=1, filled_avg_price=110, id="s1", filled_at="2026-01-01T11:00:00+00:00"),
        Order("MSFT", "buy", filled_qty=1, filled_avg_price=100, id="b2", filled_at="2026-01-01T12:00:00+00:00"),
        Order("MSFT", "sell", filled_qty=1, filled_avg_price=90, id="s2", filled_at="2026-01-01T13:00:00+00:00"),
    ]

    metrics = calculate_metrics(reconstruct_trades(orders))

    assert metrics["trades"] == 2
    assert metrics["wins"] == 1
    assert metrics["losses"] == 1
    assert metrics["win_rate_pct"] == 50.0
    assert metrics["net_profit_before_fees"] == 0.0
    assert metrics["profit_factor"] == 1.0
    assert metrics["max_drawdown"] == 10.0
