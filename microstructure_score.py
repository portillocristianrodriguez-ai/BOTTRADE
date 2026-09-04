"""Score acumulativo de microestructura para salidas crypto."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from threading import RLock
from time import time

_LOCK = RLock()
_HISTORY = defaultdict(lambda: deque(maxlen=8))


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def registrar(ticker, imbalance=None, spread_pct=None, bid_depth_usd=None, ask_depth_usd=None, ts=None):
    key = str(ticker or "").upper()
    if not key:
        return None
    item = {
        "ts": _num(ts, time()),
        "imbalance": None if imbalance is None else _num(imbalance),
        "spread": None if spread_pct is None else abs(_num(spread_pct)),
        "bid": None if bid_depth_usd is None else max(0.0, _num(bid_depth_usd)),
        "ask": None if ask_depth_usd is None else max(0.0, _num(ask_depth_usd)),
    }
    with _LOCK:
        _HISTORY[key].append(item)
    return dict(item)


def evaluar(ticker, window_seconds=180.0):
    key = str(ticker or "").upper()
    now = time()
    with _LOCK:
        samples = [x for x in _HISTORY.get(key, ()) if now - x["ts"] <= window_seconds]
    if not samples:
        return {"score": 0.0, "class": "unknown", "samples": 0, "persistence": 0.0}

    weights = []
    adverse = []
    for item in samples:
        imb = item["imbalance"]
        spread = item["spread"]
        if imb is None:
            imb_component = 0.0
        else:
            imb_component = max(0.0, min(1.0, (-imb - 0.10) / 0.50)) * 55.0
        spread_component = 0.0 if spread is None else max(0.0, min(1.0, (spread - 0.35) / 1.20)) * 20.0
        bid, ask = item["bid"], item["ask"]
        depth_component = 0.0
        if bid is not None and ask is not None and bid + ask > 0:
            depth_component = max(0.0, min(1.0, (ask - bid) / (ask + bid))) * 25.0
        value = imb_component + spread_component + depth_component
        adverse.append(value >= 25.0)
        weights.append(value)

    persistence = sum(adverse) / len(adverse)
    intensity = sum(weights) / len(weights)
    recency = sum((i + 1) / len(weights) * v for i, v in enumerate(weights)) / len(weights)
    score = min(100.0, intensity * 0.65 + recency * 0.35)

    if score >= 70 and persistence >= 0.60:
        cls = "capitulacion"
    elif score >= 45 and persistence >= 0.50:
        cls = "deterioro_serio"
    elif score >= 25 and persistence >= 0.40:
        cls = "presion_vendedora"
    else:
        cls = "ruido"

    return {
        "score": round(score, 2),
        "class": cls,
        "samples": len(samples),
        "persistence": round(persistence, 3),
        "intensity": round(intensity, 2),
    }


def limpiar(ticker):
    with _LOCK:
        _HISTORY.pop(str(ticker or "").upper(), None)


__all__ = ["registrar", "evaluar", "limpiar"]
