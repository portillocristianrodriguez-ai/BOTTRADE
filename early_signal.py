"""Motor de señales tempranas sin look-ahead para BOTTRADE.

El objetivo es detectar aceleración antes de que un breakout quede plenamente
confirmado, pero sin convertir un único tick/barra ruidosa en una entrada.
Solo usa datos disponibles hasta la última barra recibida.
"""
from __future__ import annotations

import math

import pandas as pd


_MIN_REFERENCE_VOLUME = 1e-12


def _f(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _volume_ratio(current_volume, reference_volume):
    """Calcula un ratio solo con una referencia numéricamente fiable."""
    current = _f(current_volume)
    reference = _f(reference_volume)
    if current is None or current < 0 or reference is None or reference <= _MIN_REFERENCE_VOLUME:
        return None
    ratio = current / reference
    return _f(ratio)


def evaluar(df, *, es_crypto=False, min_score=72.0):
    """Devuelve un pre-señal conservadora y explicable.

    No mira barras futuras. La entrada temprana exige confluencia de tendencia,
    aceleración de momentum, volumen y estructura; el score original de la
    estrategia sigue siendo una condición adicional en el integrador.
    """
    vacio = {
        "enabled": True,
        "comprar_temprano": False,
        "score": 0.0,
        "motivos": [],
        "breakout_distance_pct": None,
        "momentum_pct": None,
        "momentum_accel_pct": None,
        "volume_ratio": None,
        "rsi": None,
    }
    if df is None or getattr(df, "empty", True) or len(df) < 30:
        return vacio
    try:
        x = df.copy()
        for col in ("open", "high", "low", "close", "volume"):
            if col in x:
                x[col] = pd.to_numeric(x[col], errors="coerce")
        x = x.dropna(subset=["high", "close", "volume"])
        if len(x) < 30:
            return vacio

        close = x["close"]
        high = x["high"]
        volume = x["volume"]
        price = _f(close.iloc[-1])
        if price is None or price <= 0:
            return vacio

        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema_fast = _f(ema9.iloc[-1])
        ema_slow = _f(ema21.iloc[-1])
        ema_ref = _f(ema50.iloc[-1])
        if any(v is None or v <= 0 for v in (ema_fast, ema_slow, ema_ref)):
            return vacio

        ret3 = _f((close.iloc[-1] / close.iloc[-4] - 1.0) * 100.0)
        ret6 = _f((close.iloc[-1] / close.iloc[-7] - 1.0) * 100.0)
        prior3 = _f((close.iloc[-4] / close.iloc[-7] - 1.0) * 100.0)
        accel = _f((ret3 or 0.0) - (prior3 or 0.0))

        vol_base = volume.shift(1).rolling(20, min_periods=10).mean().iloc[-1]
        vol_ratio = _volume_ratio(volume.iloc[-1], vol_base)

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi = _f((100.0 - (100.0 / (1.0 + rs.iloc[-1]))) if not pd.isna(rs.iloc[-1]) else 100.0)

        prev_high = _f(high.iloc[-13:-1].max())
        distance = _f((price / prev_high - 1.0) * 100.0) if prev_high and prev_high > 0 else None

        trend = price > ema_ref and ema_fast > ema_slow
        slope = _f((ema_fast / _f(ema9.iloc[-4]) - 1.0) * 100.0) if _f(ema9.iloc[-4]) else None
        near_breakout = distance is not None and -0.35 <= distance <= 0.35
        momentum_ok = (ret3 or -999) > (0.12 if es_crypto else 0.08)
        accel_ok = (accel or -999) > (0.08 if es_crypto else 0.05)
        volume_ok = (vol_ratio or 0.0) >= (1.15 if es_crypto else 1.05)
        rsi_ok = rsi is not None and 50.0 <= rsi <= (76.0 if es_crypto else 74.0)
        slope_ok = (slope or -999) > 0.02

        score = 0.0
        motivos = []
        for ok, points, text in (
            (trend, 22, "tendencia local alcista"),
            (slope_ok, 12, "EMA9 acelerando"),
            (momentum_ok, 18, "momentum temprano"),
            (accel_ok, 16, "aceleración del momentum"),
            (volume_ok, 16, "volumen por encima de base"),
            (rsi_ok, 8, "RSI en zona de impulso"),
            (near_breakout, 8, "precio próximo a ruptura"),
        ):
            if ok:
                score += points
                motivos.append(text)

        comprar = bool(
            score >= float(min_score)
            and trend
            and momentum_ok
            and accel_ok
            and (volume_ok or near_breakout)
            and rsi_ok
        )

        return {
            **vacio,
            "comprar_temprano": comprar,
            "score": min(score, 100.0),
            "motivos": motivos,
            "breakout_distance_pct": distance,
            "momentum_pct": ret3,
            "momentum_accel_pct": accel,
            "volume_ratio": vol_ratio,
            "rsi": rsi,
        }
    except Exception:
        return vacio
