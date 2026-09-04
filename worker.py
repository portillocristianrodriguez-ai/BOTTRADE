"""Entrypoint de producción para BOTTRADE."""
from __future__ import annotations

import math
import threading

import estrategia
import crypto_ranker
import dynamic_exit_manager
from execution_stream import lanzar_stream_ejecuciones

_PATTERN_CONTEXT = threading.local()
_PATTERN_RUNTIME_LOCK = threading.RLock()
_SIGNAL_CONTEXT = threading.local()


def _numero_finito(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _observacion_valida_crypto(df):
    """Evita guardar observaciones crypto con indicadores todavía no calculados."""
    if df is None or getattr(df, "empty", True):
        return False, "sin_datos"
    try:
        row = df.iloc[-1]
        precio = _numero_finito(row.get("close"))
        atr = _numero_finito(row.get("atr"))
        rsi = _numero_finito(row.get("rsi"))
        ema_rapida = _numero_finito(row.get("ema_rapida"))
        ema_lenta = _numero_finito(row.get("ema_lenta"))
        ema_tendencia = _numero_finito(row.get("ema_tendencia"))
        if precio is None or precio <= 0:
            return False, "precio_invalido"
        if atr is None or atr <= 0:
            return False, "atr_no_disponible"
        if rsi is None or not 0 <= rsi <= 100:
            return False, "rsi_no_disponible"
        if any(value is None for value in (ema_rapida, ema_lenta, ema_tendencia)):
            return False, "ema_no_disponible"
        return True, "ok"
    except Exception:
        return False, "indicadores_invalidos"


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

        if es_crypto:
            valido, razon = _observacion_valida_crypto(df_observacion)
            if not valido:
                main_module.log.debug("[patrones] %s: observación crypto omitida (%s)", ticker, razon)
                return

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


def _instalar_ranking_crypto(main_module):
    """Conecta el ranking de cartera al score que ya consume el scanner."""
    original_analysis = getattr(estrategia, "analizar_impulso_crypto", None)
    if not callable(original_analysis):
        return
    if getattr(original_analysis, "_bottrade_portfolio_ranked", False):
        return

    def analizar_ranked(df, ticker):
        resultado = original_analysis(df, ticker)
        if not isinstance(resultado, dict):
            return resultado
        try:
            volumen_dolar_medio = 0.0
            if df is not None and not getattr(df, "empty", True):
                ultimas = df.tail(12)
                volumen_dolar_medio = float((ultimas["close"] * ultimas["volume"]).mean())

            signal_score = float(resultado.get("score", 0.0) or 0.0)
            portfolio_score = crypto_ranker.calcular_score_cartera(resultado, volumen_dolar_medio)

            resultado = dict(resultado)
            resultado["signal_score"] = signal_score
            resultado["volumen_dolar_medio"] = volumen_dolar_medio
            resultado["portfolio_score"] = portfolio_score
            resultado["ranking_score"] = portfolio_score
            resultado["score"] = portfolio_score
            return resultado
        except Exception as exc:
            main_module.log.warning("[ranking] %s: ranking omitido: %s", ticker, exc)
            return resultado

    analizar_ranked._bottrade_portfolio_ranked = True
    estrategia.analizar_impulso_crypto = analizar_ranked


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
                broker_module.log.info(f"[SIZING-SCORE] {ticker}: score={score:.1f} factor={factor:.3f} qty={qty}->{adjusted}")
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
    _instalar_ranking_crypto(bot)
    _instalar_sizing_por_score(bot)
    dynamic_exit_manager.instalar(bot)
    lanzar_stream_ejecuciones()
    bot.main()


if __name__ == "__main__":
    main()
