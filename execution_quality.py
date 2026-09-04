"""Pre-trade crypto execution-quality checks.

No orders are sent here. The module evaluates the current bid/ask and
order-book depth and returns both a hard gate and a recommended notional.
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


def _vwap_impact(asks, notional, mid):
    remaining = max(0.0, _num(notional))
    cost = 0.0
    filled_notional = 0.0
    for level in asks[:10]:
        price, size = _level_price_size(level)
        if price <= 0 or size <= 0 or remaining <= 0:
            continue
        take_notional = min(size * price, remaining)
        cost += take_notional
        filled_notional += take_notional
        remaining -= take_notional
    if filled_notional <= 0 or mid <= 0:
        return None, remaining
    vwap = cost / (filled_notional / mid) if filled_notional > 0 else mid
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
    """Evalúa spread, profundidad e impacto y propone un tamaño ejecutable."""
    proposed = max(0.0, _num(proposed_notional))
    result = {
        "ok": True,
        "reason": "disabled_or_unavailable",
        "spread_pct": None,
        "top_ask_depth_usd": None,
        "depth_ratio": None,
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
        max_ratio = min(1.0, max(0.05, _num(max_depth_ratio, 0.60)))
        depth_ratio = proposed / top_depth if top_depth > 0 else math.inf
        impact_pct, unfilled = _vwap_impact(asks, proposed, mid)

        result.update({
            "spread_pct": spread_pct,
            "top_ask_depth_usd": top_depth,
            "depth_ratio": depth_ratio,
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

        impact_limit = max(0.10, spread_limit * 1.5)
        if unfilled > 0:
            # If the top 10 levels cannot absorb the proposed order, use the
            # same depth cap rather than pretending the full order is liquid.
            recommended = min(recommended, max(0.0, top_depth * max_ratio))

        if impact_pct is not None and impact_pct > impact_limit:
            # Try a smaller executable size before hard-blocking.
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
        if recommended < proposed:
            result["reason"] = result["reason"] if result["reason"] != "ok" else "reduced_for_depth"
        return result
    except Exception as exc:
        result["reason"] = f"unavailable:{type(exc).__name__}"
        return result
