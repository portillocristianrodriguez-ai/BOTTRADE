"""Señales de microestructura para salidas crypto.

No envía órdenes. Consulta el último libro disponible y transforma
spread/profundidad/desequilibrio en contexto para el motor de salida.
"""
from __future__ import annotations

import math
from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _level(level):
    price = _num(getattr(level, "price", getattr(level, "p", 0)))
    size = _num(getattr(level, "size", getattr(level, "s", 0)))
    if isinstance(level, dict):
        price = _num(level.get("price", level.get("p", price)))
        size = _num(level.get("size", level.get("s", size)))
    return price, size


def obtener_contexto_orderbook(data_client, symbol: str, niveles: int = 5) -> dict[str, Any]:
    """Obtiene spread e imbalance del último order book disponible."""
    result = {
        "available": False,
        "spread_pct": None,
        "book_imbalance": None,
        "bid_depth_usd": None,
        "ask_depth_usd": None,
        "reason": "unavailable",
    }
    if data_client is None or not symbol:
        return result
    try:
        from alpaca.data.requests import CryptoLatestOrderbookRequest

        books = data_client.get_crypto_latest_orderbook(
            CryptoLatestOrderbookRequest(symbol_or_symbols=symbol)
        )
        book = books.get(symbol) if hasattr(books, "get") else None
        if book is None and hasattr(books, "get"):
            book = books.get(symbol.replace("/", ""))
        if book is None:
            result["reason"] = "orderbook_missing"
            return result

        bids = list(getattr(book, "bids", []) or [])
        asks = list(getattr(book, "asks", []) or [])
        if not bids or not asks:
            result["reason"] = "empty_orderbook"
            return result

        bid_price, _ = _level(bids[0])
        ask_price, _ = _level(asks[0])
        if bid_price <= 0 or ask_price <= 0 or ask_price < bid_price:
            result["reason"] = "invalid_quote"
            return result

        n = max(1, int(niveles))
        bid_depth = sum(p * s for p, s in (_level(x) for x in bids[:n]) if p > 0 and s > 0)
        ask_depth = sum(p * s for p, s in (_level(x) for x in asks[:n]) if p > 0 and s > 0)
        total = bid_depth + ask_depth
        imbalance = (bid_depth - ask_depth) / total if total > 0 else 0.0
        mid = (bid_price + ask_price) / 2.0
        spread_pct = (ask_price - bid_price) / mid * 100.0

        result.update({
            "available": True,
            "spread_pct": spread_pct,
            "book_imbalance": max(-1.0, min(1.0, imbalance)),
            "bid_depth_usd": bid_depth,
            "ask_depth_usd": ask_depth,
            "reason": "ok",
        })
        return result
    except Exception as exc:
        result["reason"] = f"unavailable:{type(exc).__name__}"
        return result


__all__ = ["obtener_contexto_orderbook"]
