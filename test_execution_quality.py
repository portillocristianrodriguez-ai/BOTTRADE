"""Regression tests for adaptive crypto execution quality.

Run with: python -m unittest test_execution_quality.py
"""

import unittest

import execution_quality


class Level:
    def __init__(self, price, size):
        self.price = price
        self.size = size


class Book:
    def __init__(self, asks, bids):
        self.asks = asks
        self.bids = bids


class Client:
    def __init__(self, book):
        self.book = book

    def get_crypto_latest_orderbook(self, request):
        return {request.symbol_or_symbols: self.book}


class ExecutionQualityTests(unittest.TestCase):
    def test_tight_liquid_book_accepts(self):
        client = Client(Book(
            asks=[Level(100.10, 1000)],
            bids=[Level(99.90, 1000)],
        ))
        result = execution_quality.evaluate_crypto_orderbook(
            client, "BTC/USD", 5000, max_spread_pct=0.90,
            min_top_depth_usd=1500, max_depth_ratio=0.60,
        )
        self.assertTrue(result["ok"])
        self.assertLess(result["spread_pct"], 0.90)

    def test_wide_spread_blocks(self):
        client = Client(Book(
            asks=[Level(101.0, 1000)],
            bids=[Level(99.0, 1000)],
        ))
        result = execution_quality.evaluate_crypto_orderbook(
            client, "BTC/USD", 500, max_spread_pct=0.90,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "spread_too_wide")

    def test_thin_book_recommends_smaller_size(self):
        client = Client(Book(
            asks=[Level(100.10, 10)],
            bids=[Level(99.90, 100)],
        ))
        result = execution_quality.evaluate_crypto_orderbook(
            client, "BTC/USD", 5000, max_spread_pct=0.90,
            min_top_depth_usd=1500, max_depth_ratio=0.60,
        )
        self.assertTrue(result["ok"])
        self.assertLess(result["recommended_notional"], 5000)

    def test_missing_data_is_non_blocking(self):
        result = execution_quality.evaluate_crypto_orderbook(
            None, "BTC/USD", 5000,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "unavailable")


if __name__ == "__main__":
    unittest.main()
