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


def test_tight_book_accepts():
    client = Client(Book([Level(100.10, 1000)], [Level(99.90, 1000)]))
    result = execution_quality.evaluate_crypto_orderbook(client, "BTC/USD", 5000)
    assert result["ok"] is True
    assert result["spread_pct"] < 0.90


def test_wide_spread_blocks():
    client = Client(Book([Level(101.0, 1000)], [Level(99.0, 1000)]))
    result = execution_quality.evaluate_crypto_orderbook(client, "BTC/USD", 500)
    assert result["ok"] is False
    assert result["reason"] == "spread_too_wide"


def test_thin_book_blocks_oversized_order():
    client = Client(Book([Level(100.10, 10)], [Level(99.90, 100)]))
    result = execution_quality.evaluate_crypto_orderbook(client, "BTC/USD", 5000)
    assert result["ok"] is False
    assert result["reason"] == "thin_top_of_book"


def test_missing_client_is_non_blocking():
    result = execution_quality.evaluate_crypto_orderbook(None, "BTC/USD", 5000)
    assert result["ok"] is True
    assert result["reason"] == "disabled_or_unavailable"
