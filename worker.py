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


_PATTERN_RUNTIME_LOCK = threading.RLock()


def _instalar_observacion_robusta(main_module):
    original = getattr(main_module, "registrar_observacion_pattern", None)
    if not callable(original) or getattr(original, "_bottrade_hardened", False):
        return

    def registrar_observacion_pattern(ticker, df, analisis_scanner=None, senal=None):
        if df is None or getattr(df, "empty", True):
            return

        es_crypto = bool(main_module.broker.es_cripto(ticker))
        df_observacion = df

        # El scanner crypto recibe datos OHLCV crudos, mientras que el
        # motor de patrones espera columnas derivadas. Calculamos aquí
        # los indicadores una sola vez antes de observar.
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

        # obtener_sesion_mercado() pertenece al calendario de acciones.
        # Para crypto no debemos etiquetar la observación como PREMARKET.
        if es_crypto:
            with _PATTERN_RUNTIME_LOCK:
                sesion_original = main_module.obtener_sesion_mercado
                main_module.obtener_sesion_mercado = lambda: "CRYPTO_24_7"
                try:
                    return original(ticker, df_observacion, analisis_scanner, senal)
                finally:
                    main_module.obtener_sesion_mercado = sesion_original

        return original(ticker, df_observacion, analisis_scanner, senal)

    registrar_observacion_pattern._bottrade_hardened = True
    main_module.registrar_observacion_pattern = registrar_observacion_pattern


def main():
    import main as bot

    _instalar_observacion_robusta(bot)
    bot.main()


if __name__ == "__main__":
    main()
