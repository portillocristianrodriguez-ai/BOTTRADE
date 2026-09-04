"""Memoria de microestructura para confirmar deterioro antes de salir."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_LOCK = threading.RLock()
_HISTORY = defaultdict(lambda: deque(maxlen=5))


def registrar(ticker: str, imbalance=None, spread_pct=None, timestamp=None):
    key = str(ticker or "").upper()
    if not key:
        return None
    item = {
        "ts": float(timestamp if timestamp is not None else time.time()),
        "imbalance": None if imbalance is None else float(imbalance),
        "spread_pct": None if spread_pct is None else float(spread_pct),
    }
    with _LOCK:
        _HISTORY[key].append(item)
        return dict(item)


def confirmar_deterioro(ticker: str, min_samples: int = 3, imbalance_threshold: float = -0.25,
                        spread_threshold: float = 0.90, window_seconds: float = 180.0) -> dict:
    key = str(ticker or "").upper()
    now = time.time()
    with _LOCK:
        samples = [x for x in _HISTORY.get(key, ()) if now - x["ts"] <= window_seconds]
    if not samples:
        return {"confirmed": False, "samples": 0, "bad_samples": 0, "reason": "no_history"}

    bad = 0
    for item in samples:
        adverse_imbalance = item["imbalance"] is not None and item["imbalance"] < imbalance_threshold
        wide_spread = item["spread_pct"] is not None and item["spread_pct"] > spread_threshold
        if adverse_imbalance or wide_spread:
            bad += 1

    required = max(1, int(min_samples))
    confirmed = len(samples) >= required and bad >= required
    return {
        "confirmed": confirmed,
        "samples": len(samples),
        "bad_samples": bad,
        "reason": "persistent_deterioration" if confirmed else "transient_or_insufficient",
    }


def limpiar(ticker: str):
    with _LOCK:
        _HISTORY.pop(str(ticker or "").upper(), None)


__all__ = ["registrar", "confirmar_deterioro", "limpiar"]
