"""Integración del motor de salidas adaptativas con la protección crypto."""
from __future__ import annotations

import math
import threading
import time

import estrategia
from dynamic_exit import evaluar_salida

_LOCK = threading.RLock()
_LAST_ACTION = {}
_COOLDOWN_SECONDS = 90.0


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


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


def _gestionar_previamente(main_module):
    broker = getattr(main_module, "broker", None)
    if broker is None:
        return
    try:
        posiciones = broker.obtener_todas_las_posiciones()
    except Exception:
        return

    now = time.time()
    for position in posiciones:
        ticker = getattr(position, "symbol", None)
        if not ticker or not broker.es_cripto(ticker):
            continue
        ticker = broker.normalizar_ticker_crypto(ticker)
        ctx = _obtener_contexto(broker, ticker, position)
        if not ctx:
            continue

        decision = evaluar_salida(
            **ctx,
            trailing_stop_pct=_num(getattr(main_module.config, "TRAILING_STOP_PCT", 0.015), 0.015),
        )
        action = decision.get("action", "hold")
        if action == "hold":
            continue

        with _LOCK:
            previous = _LAST_ACTION.get(ticker)
            if previous and now - previous < _COOLDOWN_SECONDS:
                continue
            _LAST_ACTION[ticker] = now

        log = getattr(main_module, "log", None)
        if log:
            log.info(
                "[DYNAMIC-EXIT] %s action=%s pnl=%.2f%% mom=%.2f%% score=%.1f reasons=%s",
                ticker, action, ctx["pnl_pct"] * 100.0, ctx["momentum_pct"],
                _num(decision.get("score")), ",".join(decision.get("reasons", [])),
            )

        try:
            lock = getattr(main_module, "_lock_operaciones", _LOCK)
            with lock:
                if action == "reduce":
                    order = _partial_sell(broker, ticker, decision.get("reduce_fraction", 0.50))
                    if order is not None and log:
                        log.warning("[DYNAMIC-EXIT] %s reducción parcial enviada", ticker)
                elif action == "exit":
                    broker.vender(ticker)
                elif action == "tighten" and log:
                    stop = _num(decision.get("recommended_stop_pct"))
                    log.info("[DYNAMIC-EXIT] %s trailing recomendado=%.3f%%", ticker, stop * 100.0)
        except Exception as exc:
            if log:
                log.warning("[DYNAMIC-EXIT] %s acción %s omitida: %s", ticker, action, exc)


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


__all__ = ["instalar"]
