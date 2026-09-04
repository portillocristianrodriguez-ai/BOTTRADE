"""Entrypoint de producción para BOTTRADE."""
from __future__ import annotations

import threading

import estrategia
from execution_stream import lanzar_stream_ejecuciones

_PATTERN_CONTEXT = threading.local()
_PATTERN_RUNTIME_LOCK = threading.RLock()
_SIGNAL_CONTEXT = threading.local()
_SIZING_RUNTIME_LOCK = threading.RLock()


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


def _instalar_sizing_por_score(main_module):
    """Modula el tamaño crypto según la calidad de la señal, sin saltar guards."""
    broker_module = getattr(main_module, "broker", None)
    original_size = getattr(broker_module, "calcular_tamano_posicion", None)
    original_compra = getattr(main_module, "ejecutar_compra_scanner_crypto", None)
    if not callable(original_size) or not callable(original_compra):
        return
    if getattr(original_compra, "_bottrade_score_sizing", False):
        return

    def sizing_score_aware(ticker, precio, atr):
        qty = original_size(ticker, precio, atr)
        score = getattr(_SIGNAL_CONTEXT, "score", None)
        if score is None:
            return qty
        try:
            score = max(0.0, min(100.0, float(score)))
            if qty <= 0 or not broker_module.es_cripto(ticker):
                return qty
            factor = 0.65 + ((score - 70.0) / 30.0) * 0.50
            factor = max(0.65, min(1.15, factor))
            adjusted = float(qty) * factor
            normalizar = getattr(broker_module, "_normalizar_qty_crypto", None)
            if callable(normalizar):
                adjusted = normalizar(ticker, adjusted)
            if adjusted > 0 and abs(factor - 1.0) >= 0.02:
                broker_module.log.info(
                    f"[SIZING-SCORE] {ticker}: score={score:.1f} factor={factor:.3f} qty={qty}->{adjusted}"
                )
            return adjusted
        except Exception as exc:
            broker_module.log.warning(f"[SIZING-SCORE] {ticker}: ajuste omitido: {exc}")
            return qty

    broker_module.calcular_tamano_posicion = sizing_score_aware

    def ejecutar_con_score(ticker, df, analisis):
        anterior = getattr(_SIGNAL_CONTEXT, "score", None)
        _SIGNAL_CONTEXT.score = analisis.get("score") if isinstance(analisis, dict) else None
        try:
            return original_compra(ticker, df, analisis)
        finally:
            _SIGNAL_CONTEXT.score = anterior

    ejecutar_con_score._bottrade_score_sizing = True
    main_module.ejecutar_compra_scanner_crypto = ejecutar_con_score


def main():
    import main as bot
    _instalar_observacion_robusta(bot)
    _instalar_sizing_por_score(bot)
    lanzar_stream_ejecuciones()
    bot.main()


if __name__ == "__main__":
    main()
