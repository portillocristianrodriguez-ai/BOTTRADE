"""Puente de sizing adaptativo basado en la calidad de señal.

No envía órdenes. Mantiene el último score por símbolo durante el ciclo de
análisis y ajusta el sizing ya calculado por ATR/liquidez, sin poder superar
los límites del broker.
"""
from __future__ import annotations

import threading
import time

import config

_LOCK = threading.RLock()
_SIGNALS = {}
_INSTALLED = False


def registrar_senal(ticker, analisis):
    try:
        score = float((analisis or {}).get("portfolio_score", (analisis or {}).get("score", 0)) or 0)
    except (TypeError, ValueError):
        return
    if score <= 0:
        return
    with _LOCK:
        _SIGNALS[str(ticker).upper()] = (score, time.monotonic())


def obtener_score(ticker, max_age_seconds=600):
    clave = str(ticker).upper()
    with _LOCK:
        dato = _SIGNALS.get(clave)
    if dato is None:
        return None
    score, timestamp = dato
    if time.monotonic() - timestamp > max_age_seconds:
        return None
    return score


def factor_score(score):
    """Convierte score 70..100 en factor 0.70..1.15 de sizing."""
    if score is None:
        return 1.0
    minimo = float(getattr(config, "CRYPTO_SCORE_MINIMO", 70.0))
    minimo = min(95.0, max(0.0, minimo))
    if score <= minimo:
        return 0.70
    factor = 0.70 + (float(score) - minimo) / max(1.0, 100.0 - minimo) * 0.45
    return min(1.15, max(0.70, factor))


def instalar(broker_module, estrategia_module):
    global _INSTALLED
    if _INSTALLED:
        return

    original_size = getattr(broker_module, "calcular_tamano_posicion", None)
    original_analysis = getattr(estrategia_module, "analizar_impulso_crypto", None)
    if not callable(original_size) or not callable(original_analysis):
        return

    def analizar_con_contexto(df, ticker):
        resultado = original_analysis(df, ticker)
        if isinstance(resultado, dict):
            registrar_senal(ticker, resultado)
        return resultado

    def size_con_score(ticker, precio, atr):
        qty = original_size(ticker, precio, atr)
        score = obtener_score(ticker)
        factor = factor_score(score)
        if score is None or factor == 1.0:
            return qty
        try:
            if broker_module.es_cripto(ticker):
                ajustada = float(qty) * factor
                normalizador = getattr(broker_module, "_normalizar_qty_crypto", None)
                if callable(normalizador):
                    ajustada = normalizador(ticker, ajustada)
                else:
                    ajustada = max(0.0, ajustada)
            else:
                ajustada = max(1, int(float(qty) * factor))
            broker_module.log.info(
                "[SIZING] %s: score=%.1f factor=%.3f qty=%s->%s",
                ticker, score, factor, qty, ajustada,
            )
            return ajustada
        except Exception as exc:
            broker_module.log.warning("[SIZING] %s: ajuste por score omitido: %s", ticker, exc)
            return qty

    estrategia_module.analizar_impulso_crypto = analizar_con_contexto
    broker_module.calcular_tamano_posicion = size_con_score
    _INSTALLED = True


def resetear():
    with _LOCK:
        _SIGNALS.clear()
