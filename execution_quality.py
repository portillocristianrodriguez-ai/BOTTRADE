"""Pre-trade crypto execution-quality checks.

No orders are sent here. The module evaluates the current bid/ask, order-book
depth, imbalance and estimated market impact and returns a hard gate plus a
recommended notional for the proposed BUY.
"""
from __future__ import annotations

import math
from typing import Any, Dict


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except Exception:
        return default


def _level_price_size(level):
    price = _num(getattr(level, "price", getattr(level, "p", 0)))
    size = _num(getattr(level, "size", getattr(level, "s", 0)))
    if isinstance(level, dict):
        price = _num(level.get("price", level.get("p", price)))
        size = _num(level.get("size", level.get("s", size)))
    return price, size


def _side_depth_usd(levels, limit=5):
    total = 0.0
    for level in list(levels or [])[:limit]:
        price, size = _level_price_size(level)
        if price > 0 and size > 0:
            total += price * size
    return total


def _vwap_impact(asks, notional, mid):
    remaining = max(0.0, _num(notional))
    cost = 0.0
    quantity = 0.0
    for level in asks[:10]:
        price, size = _level_price_size(level)
        if price <= 0 or size <= 0 or remaining <= 0:
            continue
        take_notional = min(size * price, remaining)
        take_qty = take_notional / price
        cost += take_notional
        quantity += take_qty
        remaining -= take_notional
    if quantity <= 0 or mid <= 0:
        return None, remaining
    vwap = cost / quantity
    impact_pct = (vwap / mid - 1.0) * 100.0
    return impact_pct, remaining


def evaluate_crypto_orderbook(
    data_client,
    symbol: str,
    proposed_notional: float,
    max_spread_pct: float = 0.90,
    min_top_depth_usd: float = 1500.0,
    max_depth_ratio: float = 0.60,
    min_execution_notional_usd: float = 25.0,
) -> Dict[str, Any]:
    """Evalúa spread, profundidad, imbalance e impacto y propone un tamaño ejecutable."""
    proposed = max(0.0, _num(proposed_notional))
    result = {
        "ok": True,
        "reason": "disabled_or_unavailable",
        "spread_pct": None,
        "top_ask_depth_usd": None,
        "top_bid_depth_usd": None,
        "depth_ratio": None,
        "book_imbalance": None,
        "estimated_impact_pct": None,
        "recommended_notional": proposed,
    }
    try:
        if data_client is None or proposed <= 0:
            result["reason"] = "unavailable"
            return result

        from alpaca.data.requests import CryptoLatestOrderbookRequest

        request = CryptoLatestOrderbookRequest(symbol_or_symbols=symbol)
        books = data_client.get_crypto_latest_orderbook(request)
        book = books.get(symbol) if hasattr(books, "get") else None
        if book is None and hasattr(books, "get"):
            book = books.get(symbol.replace("/", ""))
        if book is None:
            result["reason"] = "orderbook_missing"
            return result

        asks = list(getattr(book, "asks", []) or [])
        bids = list(getattr(book, "bids", []) or [])
        if not asks or not bids:
            result["reason"] = "empty_orderbook"
            return result

        ask_price, ask_size = _level_price_size(asks[0])
        bid_price, _ = _level_price_size(bids[0])
        if ask_price <= 0 or bid_price <= 0 or ask_price < bid_price:
            result["reason"] = "invalid_quote"
            return result

        mid = (ask_price + bid_price) / 2.0
        spread_pct = (ask_price - bid_price) / mid * 100.0
        top_depth = ask_price * ask_size
        bid_depth = _side_depth_usd(bids, 5)
        ask_depth = _side_depth_usd(asks, 5)
        total_depth = bid_depth + ask_depth
        imbalance = ((bid_depth - ask_depth) / total_depth) if total_depth > 0 else 0.0

        max_ratio = min(1.0, max(0.05, _num(max_depth_ratio, 0.60)))
        depth_ratio = proposed / top_depth if top_depth > 0 else math.inf
        impact_pct, unfilled = _vwap_impact(asks, proposed, mid)

        result.update({
            "spread_pct": spread_pct,
            "top_ask_depth_usd": top_depth,
            "top_bid_depth_usd": bid_depth,
            "depth_ratio": depth_ratio,
            "book_imbalance": imbalance,
            "estimated_impact_pct": impact_pct,
            "reason": "ok",
        })

        spread_limit = max(0.05, _num(max_spread_pct, 0.90))
        if spread_pct > spread_limit:
            result["ok"] = False
            result["reason"] = "spread_too_wide"
            return result

        minimum = max(0.0, _num(min_execution_notional_usd, 25.0))
        recommended = proposed
        if top_depth > 0 and (top_depth < max(0.0, _num(min_top_depth_usd, 1500.0)) or depth_ratio > max_ratio):
            recommended = min(recommended, top_depth * max_ratio)

        # Para una compra, una pared de ventas muy superior a las compras
        # disponibles suele implicar peor absorción inmediata. No bloqueamos
        # por sí sola: reducimos tamaño de forma progresiva.
        if imbalance < -0.20:
            imbalance_factor = max(0.55, 1.0 + imbalance * 0.75)
            recommended = min(recommended, proposed * imbalance_factor)
            result["reason"] = "reduced_for_imbalance"

        impact_limit = max(0.10, spread_limit * 1.5)
        if unfilled > 0:
            recommended = min(recommended, max(0.0, top_depth * max_ratio))

        if impact_pct is not None and impact_pct > impact_limit:
            recommended = min(recommended, max(0.0, top_depth * max_ratio))
            if recommended < minimum:
                result["ok"] = False
                result["reason"] = "estimated_impact_too_high"
                result["recommended_notional"] = recommended
                return result
            result["reason"] = "reduced_for_impact"

        if recommended < minimum:
            result["ok"] = False
            result["reason"] = "insufficient_depth"
            result["recommended_notional"] = recommended
            return result

        result["recommended_notional"] = recommended
        if recommended < proposed and result["reason"] == "ok":
            result["reason"] = "reduced_for_depth"
        return result
    except Exception as exc:
        result["reason"] = f"unavailable:{type(exc).__name__}"
        return result
