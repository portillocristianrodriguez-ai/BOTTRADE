"""Entrypoint de producción para BOTTRADE.

Carga main y aplica una pequeña capa de compatibilidad al motor de
observación de patrones antes de arrancar los hilos. El objetivo es que
la observación crypto use indicadores reales y una sesión 24/7, sin
convertirse en una fuente de errores del circuit breaker.

No modifica el modo PAPER ni habilita trading live.
"""
from __future__ import annotations

import threading

import estrategia


_PATTERN_CONTEXT = threading.local()


def _instalar_observacion_robusta(main_module):
    original_observacion = getattr(main_module, "registrar_observacion_pattern", None)
    original_sesion = getattr(main_module, "obtener_sesion_mercado", None)

    if not callable(original_observacion) or not callable(original_sesion):
        return
    if getattr(original_observacion, "_bottrade_hardened", False):
        return

    def sesion_contextual():
        if getattr(_PATTERN_CONTEXT, "crypto_24_7", False):
            return "CRYPTO_24_7"
        return original_sesion()

    main_module.obtener_sesion_mercado = sesion_contextual

    def registrar_observacion_pattern(ticker, df, analisis_scanner=None, senal=None):
        if df is None or getattr(df, "empty", True):
            return

        es_crypto = bool(main_module.broker.es_cripto(ticker))
        df_observacion = df

        # El scanner crypto recibe OHLCV crudo, mientras que el motor de
        # patrones espera columnas derivadas. Las completamos antes de
        # observar para evitar RSI/ATR/volumen artificialmente iguales a 0.
        try:
            columnas_necesarias = {
                "atr", "rsi", "macd", "ema_rapida", "ema_lenta",
                "ema_tendencia", "volumen_ratio",
            }
            if not columnas_necesarias.issubset(set(df.columns)):
                df_observacion = estrategia.calcular_indicadores(df)
        except Exception as exc:
            main_module.log.warning(
                f"[patrones] {ticker}: no se pudieron completar indicadores: {exc}"
            )
            df_observacion = df

        anterior = getattr(_PATTERN_CONTEXT, "crypto_24_7", False)
        _PATTERN_CONTEXT.crypto_24_7 = es_crypto
        try:
            return original_observacion(
                ticker,
                df_observacion,
                analisis_scanner,
                senal,
            )
        finally:
            _PATTERN_CONTEXT.crypto_24_7 = anterior

    registrar_observacion_pattern._bottrade_hardened = True
    main_module.registrar_observacion_pattern = registrar_observacion_pattern


def main():
    import main as bot

    _instalar_observacion_robusta(bot)
    bot.main()


if __name__ == "__main__":
    main()
