"""Entrypoint de producción para BOTTRADE."""
from __future__ import annotations

import math
import threading

import estrategia
import crypto_ranker
import early_signal
import dynamic_exit_manager_v2 as dynamic_exit_manager
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


def _es_crypto_ticker(main_module, ticker):
    symbol = str(ticker or "").strip().upper()
    if "/" in symbol:
        return True
    configured = getattr(getattr(main_module, "config", None), "CRYPTO_TICKERS", [])
    return symbol in {str(x).strip().upper() for x in configured}


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
        es_crypto = _es_crypto_ticker(main_module, ticker)
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


def _integrar_senal_temprana(original, df, ticker, es_crypto):
    """Añade una entrada temprana solo cuando hay confluencia suficiente.

    No sustituye la estrategia base: conserva su score/diagnóstico y solo
    habilita `comprar` cuando la aceleración temprana supera un umbral alto.
    """
    resultado = original(df, ticker)
    if not isinstance(resultado, dict):
        return resultado
    try:
        cfg = __import__("config")
        enabled = bool(getattr(cfg, "EARLY_SIGNAL_ENABLED", True))
        trading = bool(getattr(cfg, "EARLY_SIGNAL_TRADING_ENABLED", True))
        threshold = float(getattr(cfg, "EARLY_SIGNAL_MIN_SCORE", 82.0))
        if not enabled:
            return resultado

        early = early_signal.evaluar(df, es_crypto=es_crypto, min_score=threshold)
        salida = dict(resultado)
        salida["early_signal"] = early
        salida["early_signal_score"] = float(early.get("score", 0.0) or 0.0)
        salida["early_signal_active"] = bool(early.get("comprar_temprano"))

        if trading and early.get("comprar_temprano"):
            base_score = float(salida.get("score", 0.0) or 0.0)
            # El motor temprano no puede rescatar una señal claramente bajista.
            regimen = str(salida.get("regimen", "")).lower()
            if regimen not in {"bajista"} and base_score >= float(getattr(cfg, "EARLY_SIGNAL_BASE_SCORE_FLOOR", 55.0)):
                salida["comprar"] = True
                salida["score"] = max(base_score, threshold)
                motivos = list(salida.get("motivo", []) or [])
                motivos.append("⚡ señal temprana: aceleración + momentum + confluencia")
                motivos.extend(f"early:{m}" for m in early.get("motivos", [])[:4])
                salida["motivo"] = motivos
        return salida
    except Exception as exc:
        try:
            __import__("logging").getLogger(__name__).debug("[early-signal] %s omitida: %s", ticker, exc)
        except Exception:
            pass
        return resultado


def _instalar_senales_tempranas():
    """Envuelve acciones y crypto para no perder el inicio de impulsos."""
    original_crypto = getattr(estrategia, "analizar_impulso_crypto", None)
    original_acciones = getattr(estrategia, "analizar_impulso_acciones", None)
    if callable(original_crypto) and not getattr(original_crypto, "_bottrade_early_signal", False):
        def crypto_early(df, ticker):
            return _integrar_senal_temprana(original_crypto, df, ticker, True)
        crypto_early._bottrade_early_signal = True
        estrategia.analizar_impulso_crypto = crypto_early
    if callable(original_acciones) and not getattr(original_acciones, "_bottrade_early_signal", False):
        def acciones_early(df, ticker):
            return _integrar_senal_temprana(original_acciones, df, ticker, False)
        acciones_early._bottrade_early_signal = True
        estrategia.analizar_impulso_acciones = acciones_early


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
    _instalar_senales_tempranas()
    _instalar_ranking_crypto(bot)
    _instalar_sizing_por_score(bot)
    dynamic_exit_manager.instalar(bot)
    lanzar_stream_ejecuciones()
    bot.main()


if __name__ == "__main__":
    main()
