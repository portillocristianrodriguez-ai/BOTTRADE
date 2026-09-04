"""Pre-trade crypto execution-quality checks.

No orders are sent here. The module evaluates the current bid/ask and
order-book depth so the execution layer can reject or reduce trades that are
likely to suffer excessive spread or market impact.
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


def evaluate_crypto_orderbook(data_client, symbol: str, proposed_notional: float,
                              max_spread_pct: float = 0.90,
                              min_top_depth_usd: float = 1500.0,
                              max_depth_ratio: float = 0.60,
                              min_execution_notional_usd: float = 25.0) -> Dict[str, Any]:
    """Evaluate a crypto buy and recommend a safe notional when depth is thin."""
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

        remaining = proposed
        cost = 0.0
        filled = 0.0
        for level in asks[:10]:
            price, size = _level_price_size(level)
            if price <= 0 or size <= 0:
                continue
            take = min(size, remaining / price) if remaining > 0 else 0.0
            if take <= 0:
                break
            cost += take * price
            filled += take
            remaining -= take * price
            if remaining <= 0:
                break

        impact_pct = None
        if filled > 0:
            vwap = cost / filled
            impact_pct = (vwap / mid - 1.0) * 100.0

        result.update({
            "spread_pct": spread_pct,
            "top_ask_depth_usd": top_depth,
            "depth_ratio": depth_ratio,
            "estimated_impact_pct": impact_pct,
            "recommended_notional": proposed,
            "reason": "ok",
        })

        if spread_pct > max(0.05, _num(max_spread_pct, 0.90)):
            result["ok"] = False
            result["reason"] = "spread_too_wide"
            return result

        min_depth = max(0.0, _num(min_top_depth_usd, 1500.0))
        minimum = max(0.0, _num(min_execution_notional_usd, 25.0))
        if top_depth < min_depth and proposed > top_depth * max_ratio:
            recommended = top_depth * max_ratio
            if recommended >= minimum:
                result["recommended_notional"] = recommended
                result["reason"] = "reduced_for_thin_book"
                return result
            result["ok"] = False
            result["reason"] = "thin_top_of_book"
            result["recommended_notional"] = recommended
            return result

        if depth_ratio > max_ratio and top_depth > 0:
            recommended = top_depth * max_ratio
            if recommended >= minimum:
                result["recommended_notional"] = recommended
                result["reason"] = "reduced_for_depth"
            else:
                result["ok"] = False
                result["reason"] = "insufficient_depth"
                result["recommended_notional"] = recommended
                return result

        impact_limit = max(0.10, _num(max_spread_pct, 0.90) * 1.5)
        if impact_pct is not None and impact_pct > impact_limit:
            result["ok"] = False
            result["reason"] = "estimated_impact_too_high"
            return result

        return result
    except Exception as exc:
        # Market-data outages must not manufacture a false rejection. The
        # normal exposure/risk guards remain authoritative.
        result["reason"] = f"unavailable:{type(exc).__name__}"
        return result
