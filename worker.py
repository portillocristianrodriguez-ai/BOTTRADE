"""Entrypoint de producción para BOTTRADE."""
from __future__ import annotations

import threading

import estrategia
from execution_stream import lanzar_stream_ejecuciones

_PATTERN_CONTEXT = threading.local()
_PATTERN_RUNTIME_LOCK = threading.RLock()


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
        try:
            columnas = {"atr", "rsi", "macd", "ema_rapida", "ema_lenta", "ema_tendencia", "volumen_ratio"}
            if not columnas.issubset(set(df.columns)):
                df_observacion = estrategia.calcular_indicadores(df)
        except Exception as exc:
            main_module.log.warning("[patrones] %s: indicadores no disponibles: %s", ticker, exc)

        anterior = getattr(_PATTERN_CONTEXT, "crypto_24_7", False)
        _PATTERN_CONTEXT.crypto_24_7 = es_crypto
        original_error_operativo = getattr(main_module, "registrar_error_operativo", None)

        def error_observacion_aislado(origen, error):
            main_module.log.warning("[patrones] %s: fallo aislado de observación: %s", ticker, error)

        with _PATTERN_RUNTIME_LOCK:
            if callable(original_error_operativo):
                main_module.registrar_error_operativo = error_observacion_aislado
            try:
                return original_observacion(ticker, df_observacion, analisis_scanner, senal)
            finally:
                if callable(original_error_operativo):
                    main_module.registrar_error_operativo = original_error_operativo
                _PATTERN_CONTEXT.crypto_24_7 = anterior

    registrar_observacion_pattern._bottrade_hardened = True
    main_module.registrar_observacion_pattern = registrar_observacion_pattern


def main():
    import main as bot
    _instalar_observacion_robusta(bot)
    lanzar_stream_ejecuciones()
    bot.main()


if __name__ == "__main__":
    main()
