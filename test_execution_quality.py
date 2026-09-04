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


def test_tight_liquid_book_accepts():
    client = Client(Book(
        asks=[Level(100.10, 1000)],
        bids=[Level(99.90, 1000)],
    ))
    result = execution_quality.evaluate_crypto_orderbook(
        client, "BTC/USD", 5000, max_spread_pct=0.90,
        min_top_depth_usd=1500, max_depth_ratio=0.60,
    )
    assert result["ok"] is True
    assert result["spread_pct"] < 0.90
    assert result["recommended_notional"] == 5000


def test_wide_spread_blocks():
    client = Client(Book(
        asks=[Level(101.0, 1000)],
        bids=[Level(99.0, 1000)],
    ))
    result = execution_quality.evaluate_crypto_orderbook(
        client, "BTC/USD", 500, max_spread_pct=0.90,
    )
    assert result["ok"] is False
    assert result["reason"] == "spread_too_wide"


def test_thin_book_recommends_smaller_size():
    client = Client(Book(
        asks=[Level(100.10, 10)],
        bids=[Level(99.90, 100)],
    ))
    result = execution_quality.evaluate_crypto_orderbook(
        client, "BTC/USD", 5000, max_spread_pct=0.90,
        min_top_depth_usd=1500, max_depth_ratio=0.60,
    )
    assert result["ok"] is True
    assert result["reason"] == "reduced_for_thin_book"
    assert result["recommended_notional"] < 5000
    assert result["recommended_notional"] >= 25


def test_too_thin_book_blocks_below_minimum():
    client = Client(Book(
        asks=[Level(100.10, 0.10)],
        bids=[Level(99.90, 100)],
    ))
    result = execution_quality.evaluate_crypto_orderbook(
        client, "BTC/USD", 5000, max_spread_pct=0.90,
        min_top_depth_usd=1500, max_depth_ratio=0.60,
        min_execution_notional_usd=25,
    )
    assert result["ok"] is False
    assert result["reason"] == "thin_top_of_book"
    assert result["recommended_notional"] < 25


def test_missing_orderbook_is_non_blocking():
    result = execution_quality.evaluate_crypto_orderbook(
        None, "BTC/USD", 5000,
    )
    assert result["ok"] is True
    assert result["reason"] == "disabled_or_unavailable"
