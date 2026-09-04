"""Integración del motor de salidas adaptativas con la protección crypto."""
from __future__ import annotations

import math
import threading
import time

import estrategia
from dynamic_exit import evaluar_salida

_LOCK = threading.RLock()
_LAST_ACTION = {}
_TIGHTENED_TRAIL = {}
_COOLDOWN_SECONDS = 90.0


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def calcular_retroceso_trailing(maximo, precio_actual):
    """Devuelve el retroceso porcentual desde el máximo alcanzado."""
    maximo = _num(maximo)
    precio_actual = _num(precio_actual)
    if maximo <= 0 or precio_actual <= 0 or precio_actual > maximo:
        return 0.0
    return max(0.0, (maximo - precio_actual) / maximo)


def registrar_trailing_mas_estricto(ticker, trail_pct):
    """Registra un trailing más protector y nunca permite relajarlo."""
    ticker = str(ticker or "").upper()
    trail_pct = abs(_num(trail_pct, 0.015))
    if not ticker or trail_pct <= 0:
        return None
    trail_pct = max(0.0025, min(0.05, trail_pct))
    with _LOCK:
        anterior = _TIGHTENED_TRAIL.get(ticker)
        nuevo = trail_pct if anterior is None else min(float(anterior), trail_pct)
        _TIGHTENED_TRAIL[ticker] = nuevo
        return nuevo


def obtener_trailing_estricto(ticker, default=0.015):
    with _LOCK:
        return float(_TIGHTENED_TRAIL.get(str(ticker or "").upper(), default))


def limpiar_trailing(ticker):
    with _LOCK:
        key = str(ticker or "").upper()
        _TIGHTENED_TRAIL.pop(key, None)
        _LAST_ACTION.pop(key, None)


def _partial_sell(broker, ticker, fraction):
    """Vende parcialmente una posición crypto sin competir con otra SELL."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    position = broker.obtener_posicion(ticker)
    if position is None:
        return None
    qty = _num(getattr(position, "qty", 0))
    if qty <= 0:
        return None

    for order in broker.obtener_ordenes_ticker(ticker):
        side = str(getattr(order, "side", "")).lower()
        status = str(getattr(order, "status", "")).lower()
        if "sell" in side and any(x in status for x in ("new", "accepted", "pending", "partially")):
            return None

    fraction = max(0.10, min(1.0, _num(fraction, 0.5)))
    sell_qty = qty * fraction
    normalizar = getattr(broker, "_normalizar_qty_crypto", None)
    if callable(normalizar):
        sell_qty = normalizar(ticker, sell_qty)
    if sell_qty <= 0:
        return None

    order = MarketOrderRequest(
        symbol=broker.normalizar_ticker_crypto(ticker),
        qty=sell_qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC,
    )
    import execution_idempotency
    return execution_idempotency.submit_order_idempotente(
        broker.cliente_trading,
        order,
        submit_callable=broker.cliente_trading.submit_order,
    )


def _obtener_contexto(broker, ticker, position):
    try:
        datos = broker.obtener_datos_crypto_lote([ticker], dias=3)
        df = datos.get(ticker)
        if df is None:
            df = datos.get(str(ticker).replace("/", ""))
        if df is None or getattr(df, "empty", True):
            return None
        indicadores = estrategia.calcular_indicadores(df)
        row = indicadores.iloc[-1]
        precio = _num(row.get("close"))
        atr = abs(_num(row.get("atr")))
        if precio <= 0 or atr <= 0:
            return None
        analysis = estrategia.analizar_impulso_crypto(df, ticker)
        return {
            "precio_actual": precio,
            "pnl_pct": _num(getattr(position, "unrealized_plpc", 0)),
            "atr_pct": atr / precio,
            "momentum_pct": _num(analysis.get("momentum_pct", 0)),
            "rsi": _num(analysis.get("rsi", row.get("rsi", 50)), 50),
            "adx": _num(analysis.get("adx", row.get("adx", 0))),
            "regimen": analysis.get("regimen_local", "neutral"),
            "breakout": bool(analysis.get("breakout", False)),
        }
    except Exception:
        return None


def _ejecutar_exit_si_corresponde(main_module, broker, ticker, log, motivo):
    """Ejecuta salida completa solo una vez por ventana de seguridad."""
    now = time.time()
    with _LOCK:
        previous = _LAST_ACTION.get(ticker)
        if previous and now - previous < _COOLDOWN_SECONDS:
            return False
        _LAST_ACTION[ticker] = now

    try:
        lock = getattr(main_module, "_lock_operaciones", _LOCK)
        with lock:
            if not broker.tiene_posicion_abierta(ticker):
                return False
            mensaje = broker.vender(ticker)
        if mensaje and log:
            log.warning("[DYNAMIC-EXIT] %s salida completa ejecutada: %s", ticker, motivo)
            try:
                main_module.notificaciones.notificar(
                    f"📉 DYNAMIC EXIT {ticker}\n{motivo}\n{mensaje}"
                )
            except Exception:
                pass
        return bool(mensaje)
    except Exception as exc:
        if log:
            log.warning("[DYNAMIC-EXIT] %s salida %s omitida: %s", ticker, motivo, exc)
        return False
    finally:
        with _LOCK:
            _LAST_ACTION.pop(ticker, None)


def _gestionar_trailing_estricto(main_module, broker, ticker, ctx, log):
    """Comprueba siempre el trailing adaptativo ya endurecido."""
    if ctx["pnl_pct"] <= 0:
        return False

    maximos = getattr(main_module, "_maximos_cripto", {})
    maximo = max(_num(maximos.get(ticker, ctx["precio_actual"])), ctx["precio_actual"])
    maximos[ticker] = maximo

    default_trail = _num(
        getattr(main_module.config, "TRAILING_STOP_PCT", 0.015),
        0.015,
    )
    trail = obtener_trailing_estricto(ticker, default_trail)
    retroceso = calcular_retroceso_trailing(maximo, ctx["precio_actual"])
    if retroceso < trail:
        return False

    return _ejecutar_exit_si_corresponde(
        main_module,
        broker,
        ticker,
        log,
        f"trailing adaptativo {retroceso:.2%} >= {trail:.2%}",
    )


def _gestionar_previamente(main_module):
    broker = getattr(main_module, "broker", None)
    if broker is None:
        return
    try:
        posiciones = broker.obtener_todas_las_posiciones()
    except Exception:
        return

    presentes = set()
    log = getattr(main_module, "log", None)

    for position in posiciones:
        ticker = getattr(position, "symbol", None)
        if not ticker or not broker.es_cripto(ticker):
            continue
        ticker = broker.normalizar_ticker_crypto(ticker)
        presentes.add(ticker)
        ctx = _obtener_contexto(broker, ticker, position)
        if not ctx:
            continue

        # Actualizamos primero el máximo; nunca usamos el precio actual como
        # máximo después de una caída si ya existe un HWM superior.
        maximos = getattr(main_module, "_maximos_cripto", {})
        maximos[ticker] = max(_num(maximos.get(ticker, ctx["precio_actual"])), ctx["precio_actual"])

        # El trailing ya endurecido se comprueba en CADA ciclo, incluso si la
        # nueva lectura de la señal pasa a "hold". Esto evita perder el stop.
        if _gestionar_trailing_estricto(main_module, broker, ticker, ctx, log):
            limpiar_trailing(ticker)
            continue

        decision = evaluar_salida(
            pnl_pct=ctx["pnl_pct"],
            atr_pct=ctx["atr_pct"],
            momentum_pct=ctx["momentum_pct"],
            rsi=ctx["rsi"],
            adx=ctx["adx"],
            regimen=ctx["regimen"],
            breakout=ctx["breakout"],
            trailing_stop_pct=_num(
                getattr(main_module.config, "TRAILING_STOP_PCT", 0.015),
                0.015,
            ),
        )
        action = decision.get("action", "hold")

        if action == "tighten":
            stop = _num(decision.get("recommended_stop_pct"))
            if stop > 0:
                efectivo = registrar_trailing_mas_estricto(ticker, stop)
                if log:
                    log.info("[DYNAMIC-EXIT] %s trailing ADAPTATIVO=%0.3f%%", ticker, efectivo * 100.0)
            continue

        if action == "reduce":
            now = time.time()
            with _LOCK:
                previous = _LAST_ACTION.get(ticker)
                if previous and now - previous < _COOLDOWN_SECONDS:
                    continue
                _LAST_ACTION[ticker] = now
            try:
                lock = getattr(main_module, "_lock_operaciones", _LOCK)
                with lock:
                    order = _partial_sell(broker, ticker, decision.get("reduce_fraction", 0.50))
                if order is not None and log:
                    log.warning("[DYNAMIC-EXIT] %s reducción parcial enviada", ticker)
            except Exception as exc:
                if log:
                    log.warning("[DYNAMIC-EXIT] %s reducción parcial omitida: %s", ticker, exc)
            finally:
                with _LOCK:
                    _LAST_ACTION.pop(ticker, None)
            continue

        if action == "exit":
            if _ejecutar_exit_si_corresponde(
                main_module,
                broker,
                ticker,
                log,
                ", ".join(decision.get("reasons", [])) or "deterioro confirmado",
            ):
                limpiar_trailing(ticker)

    for ticker in list(_TIGHTENED_TRAIL):
        if ticker not in presentes:
            limpiar_trailing(ticker)


def instalar(main_module):
    """Conecta el motor antes de la gestión legacy de protección."""
    original = getattr(main_module, "gestionar_posiciones_crypto", None)
    if not callable(original) or getattr(original, "_dynamic_exit_installed", False):
        return False

    def wrapper():
        _gestionar_previamente(main_module)
        return original()

    wrapper._dynamic_exit_installed = True
    main_module.gestionar_posiciones_crypto = wrapper
    main_module.log.info("[DYNAMIC-EXIT] Motor de salidas adaptativas conectado.")
    return True


__all__ = [
    "calcular_retroceso_trailing",
    "registrar_trailing_mas_estricto",
    "obtener_trailing_estricto",
    "limpiar_trailing",
    "instalar",
]
