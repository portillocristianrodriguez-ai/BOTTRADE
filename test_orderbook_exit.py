import unittest
from unittest.mock import Mock

from orderbook_exit import obtener_contexto_orderbook


class TestOrderbookExit(unittest.TestCase):
    def _book(self, bid=99.0, ask=100.0, bid_size=10.0, ask_size=10.0):
        level = lambda p, s: Mock(price=p, size=s)
        return Mock(
            bids=[level(bid, bid_size), level(bid - 1, bid_size)],
            asks=[level(ask, ask_size), level(ask + 1, ask_size)],
        )

    def test_balanced_book(self):
        client = Mock()
        client.get_crypto_latest_orderbook.return_value = {"BTC/USD": self._book()}
        result = obtener_contexto_orderbook(client, "BTC/USD")
        self.assertTrue(result["available"])
        self.assertAlmostEqual(result["book_imbalance"], 0.0, places=6)
        self.assertGreater(result["spread_pct"], 0.0)

    def test_sell_pressure_is_negative(self):
        client = Mock()
        client.get_crypto_latest_orderbook.return_value = {
            "BTC/USD": self._book(bid_size=2.0, ask_size=20.0)
        }
        result = obtener_contexto_orderbook(client, "BTC/USD")
        self.assertLess(result["book_imbalance"], -0.5)

    def test_missing_book_is_non_blocking(self):
        client = Mock()
        client.get_crypto_latest_orderbook.return_value = {}
        result = obtener_contexto_orderbook(client, "BTC/USD")
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "orderbook_missing")


if __name__ == "__main__":
    unittest.main()
