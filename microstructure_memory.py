"""Memoria y score acumulativo de microestructura para salidas crypto."""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

_LOCK = threading.RLock()
_HISTORY = defaultdict(lambda: deque(maxlen=8))


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def registrar(ticker: str, imbalance=None, spread_pct=None, timestamp=None):
    key = str(ticker or "").upper()
    if not key:
        return None
    item = {
        "ts": float(timestamp if timestamp is not None else time.time()),
        "imbalance": None if imbalance is None else _num(imbalance),
        "spread_pct": None if spread_pct is None else _num(spread_pct),
    }
    with _LOCK:
        _HISTORY[key].append(item)
        return dict(item)


def evaluar_microestructura(
    ticker: str,
    min_samples: int = 3,
    window_seconds: float = 180.0,
    imbalance_threshold: float = -0.25,
    spread_threshold: float = 0.90,
) -> dict:
    """Calcula intensidad/persistencia del deterioro del libro sin ejecutar órdenes."""
    key = str(ticker or "").upper()
    now = time.time()
    with _LOCK:
        samples = [x for x in _HISTORY.get(key, ()) if now - x["ts"] <= window_seconds]

    if not samples:
        return {"confirmed": False, "score": 0.0, "samples": 0, "bad_samples": 0, "reason": "no_history"}

    required = max(1, int(min_samples))
    bad = 0
    pressure_scores = []
    for item in samples:
        imbalance = item["imbalance"]
        spread = item["spread_pct"]
        imbalance_pressure = 0.0
        spread_pressure = 0.0
        if imbalance is not None and imbalance < imbalance_threshold:
            imbalance_pressure = min(1.0, abs(imbalance - imbalance_threshold) / 0.75 + 0.25)
        if spread is not None and spread > spread_threshold:
            spread_pressure = min(1.0, (spread - spread_threshold) / 2.0 + 0.25)
        pressure = max(imbalance_pressure, spread_pressure)
        if pressure > 0:
            bad += 1
            pressure_scores.append(pressure)
        else:
            pressure_scores.append(0.0)

    persistence = min(1.0, bad / required)
    intensity = sum(pressure_scores) / max(1, len(pressure_scores))
    recent = samples[-min(len(samples), required):]
    recent_pressure = []
    for item in recent:
        imp = item["imbalance"]
        spr = item["spread_pct"]
        p1 = min(1.0, abs(imp - imbalance_threshold) / 0.75 + 0.25) if imp is not None and imp < imbalance_threshold else 0.0
        p2 = min(1.0, (spr - spread_threshold) / 2.0 + 0.25) if spr is not None and spr > spread_threshold else 0.0
        recent_pressure.append(max(p1, p2))
    recency = sum(recent_pressure) / max(1, len(recent_pressure))
    score = round(min(100.0, persistence * 55.0 + intensity * 25.0 + recency * 20.0), 2)
    confirmed = len(samples) >= required and bad >= required
    if confirmed and score >= 75:
        reason = "capitulacion_liquidity"
    elif confirmed:
        reason = "persistent_deterioration"
    else:
        reason = "transient_or_insufficient"
    return {"confirmed": confirmed, "score": score, "samples": len(samples), "bad_samples": bad, "reason": reason}


def confirmar_deterioro(ticker: str, min_samples: int = 3, imbalance_threshold: float = -0.25,
                        spread_threshold: float = 0.90, window_seconds: float = 180.0) -> dict:
    """Compatibilidad: confirma deterioro persistente."""
    return evaluar_microestructura(ticker, min_samples, window_seconds, imbalance_threshold, spread_threshold)


def limpiar(ticker: str):
    with _LOCK:
        _HISTORY.pop(str(ticker or "").upper(), None)


__all__ = ["registrar", "evaluar_microestructura", "confirmar_deterioro", "limpiar"]
