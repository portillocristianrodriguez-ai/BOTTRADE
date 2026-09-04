"""Detección de régimen global para el scanner crypto usando BTC/USD.

No ejecuta órdenes. Convierte el comportamiento de BTC en un filtro de
contexto para las oportunidades de altcoins.
"""
from __future__ import annotations

import pandas as pd


def _ema(series, span):
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def _timeframe_state(df, fast=20, slow=50):
    if df is None or df.empty or "close" not in df.columns:
        return None
    work = df.copy()
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work = work.dropna(subset=["close"]).sort_index()
    if len(work) < slow + 5:
        return None
    close = work["close"]
    ef = _ema(close, fast)
    es = _ema(close, slow)
    last = float(close.iloc[-1])
    ef_last = float(ef.iloc[-1])
    es_last = float(es.iloc[-1])
    ref = float(ef.iloc[-4])
    slope = (ef_last - ref) / ref if ref > 0 else 0.0
    return {
        "above": last > es_last,
        "aligned": ef_last > es_last,
        "slope": slope > 0,
        "strength": slope,
    }


def evaluar_regimen_btc(df):
    """Devuelve régimen bullish/neutral/transition/bearish y score 0-100."""
    result = {"regimen": "neutral", "score": 50.0, "confidence": 0.0}
    try:
        if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
            return result
        base = df.copy().sort_index()
        if base.index.tz is None:
            base.index = base.index.tz_localize("UTC")
        else:
            base.index = base.index.tz_convert("UTC")
        close = pd.to_numeric(base["close"], errors="coerce").dropna()
        if len(close) < 80:
            return result
        frames = {"5m": close, "15m": close.resample("15min").last().dropna(), "1h": close.resample("1h").last().dropna()}
        states = {name: _timeframe_state(pd.DataFrame({"close": series})) for name, series in frames.items()}
        if any(state is None for state in states.values()):
            return result

        weights = {"5m": 0.25, "15m": 0.35, "1h": 0.40}
        points = 0.0
        for name, state in states.items():
            value = 0.0
            value += 1.0 if state["above"] else -1.0
            value += 1.0 if state["aligned"] else -1.0
            value += 0.5 if state["slope"] else -0.5
            points += value * weights[name]

        score = max(0.0, min(100.0, 50.0 + points * 20.0))
        if score >= 72:
            regime = "alcista"
        elif score <= 32:
            regime = "bajista"
        elif score >= 55:
            regime = "transicion_alcista"
        elif score <= 45:
            regime = "transicion_bajista"
        else:
            regime = "neutral"

        confidence = min(1.0, abs(score - 50.0) / 30.0)
        return {"regimen": regime, "score": score, "confidence": confidence}
    except Exception:
        return result
