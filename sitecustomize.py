"""Hardening de ejecución de BOTTRADE.

Se mantiene deliberadamente acotado al módulo ``broker`` de este proyecto.
No modifica globalmente el SDK de Alpaca. La capa principal de broker sigue
siendo la responsable de las validaciones funcionales de las órdenes.
"""

from __future__ import annotations

import builtins
import hashlib
import time

_INSTALLED = False
_ORIGINAL_IMPORT = builtins.__import__


def _client_id(order_data) -> str:
    """ID determinista corto para evitar dobles envíos de la misma intención."""
    symbol = str(getattr(order_data, "symbol", "ORDER") or "ORDER").upper().replace("/", "")
    side = str(getattr(order_data, "side", "NA") or "NA").upper()
    order_type = str(getattr(order_data, "type", getattr(order_data, "order_type", "market")) or "market").lower()
    qty = str(getattr(order_data, "qty", "") or "")
    notional = str(getattr(order_data, "notional", "") or "")
    limit_price = str(getattr(order_data, "limit_price", "") or "")
    stop_price = str(getattr(order_data, "stop_price", "") or "")
    # Cinco minutos: suficientemente corto para el scanner y suficientemente
    # estable para que dos procesos que detecten la misma señal coincidan.
    bucket = int(time.time() // 300)
    payload = "|".join((symbol, side, order_type, qty, notional, limit_price, stop_price, str(bucket)))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"BT-MOM-{symbol[:12]}-{digest}"


def _install(broker_module):
    global _INSTALLED
    if _INSTALLED:
        return

    client = getattr(broker_module, "cliente_trading", None)
    original_submit = getattr(client, "submit_order", None) if client is not None else None
    original_validate = getattr(broker_module, "_validar_orden_compra_final", None)
    if client is None or not callable(original_submit) or not callable(original_validate):
        return

    def validar_con_riesgo_final(ticker, cantidad, precio_referencia):
        if not original_validate(ticker, cantidad, precio_referencia):
            return False

        try:
            import config
            import execution_guard
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest

            cuenta = client.get_account()
            equity = float(getattr(cuenta, "equity", 0) or 0)
            buying_power = float(getattr(cuenta, "buying_power", 0) or 0)
            proposed = float(cantidad) * float(precio_referencia)
            if equity <= 0 or buying_power <= 0 or proposed <= 0:
                return False

            max_bp_pct = float(getattr(config, "MAX_BUYING_POWER_USAGE_PCT", 0.90))
            max_bp_pct = min(0.99, max(0.10, max_bp_pct))
            if proposed > buying_power * max_bp_pct + 0.01:
                broker_module.log.critical(
                    f"[GUARDIA] {ticker}: compra bloqueada por buying power. "
                    f"Notional=${proposed:,.2f} > ${buying_power * max_bp_pct:,.2f}"
                )
                return False

            if broker_module.es_cripto(ticker):
                internal_cap = float(getattr(config, "CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD", 100000.0))
                if internal_cap > 0 and proposed > internal_cap + 0.01:
                    broker_module.log.critical(
                        f"[GUARDIA] {ticker}: crypto bloqueada por cap interno. "
                        f"Notional=${proposed:,.2f} > ${internal_cap:,.2f}"
                    )
                    return False

            # Usamos únicamente APIs que existen en la capa actual del broker.
            # Así el guard no puede romper el scanner por depender de helpers
            # inexistentes.
            positions = client.get_all_positions()
            open_filter = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                limit=500,
                nested=True,
            )
            open_orders = client.get_orders(filter=open_filter)

            # Segunda barrera específica contra duplicados por símbolo.
            if broker_module.tiene_posicion_abierta(ticker):
                return False
            if broker_module.obtener_ordenes_ticker(ticker):
                return False

            ok, reason = execution_guard.validar_exposicion_compra(
                equity=equity,
                proposed_notional=proposed,
                positions=positions,
                open_orders=open_orders,
                max_single_position_pct=float(getattr(config, "MAX_SINGLE_POSITION_PCT", 0.20)),
                max_total_exposure_pct=float(getattr(config, "MAX_TOTAL_EXPOSURE_PCT", 0.50)),
            )
            if not ok:
                broker_module.log.critical(
                    f"[GUARDIA] {ticker}: compra bloqueada por exposición: {reason}"
                )
                return False

            broker_module.log.info(
                f"[GUARDIA] {ticker}: riesgo final OK | Notional=${proposed:,.2f}"
            )
            return True
        except Exception as exc:
            # Fail closed: un fallo en la comprobación final nunca debe abrir
            # una operación que no ha podido validarse.
            broker_module.log.critical(
                f"[GUARDIA] {ticker}: validación final fallida. ORDEN BLOQUEADA: {exc}"
            )
            return False

    def submit_order_guarded(order_data=None, *args, **kwargs):
        if order_data is not None and not getattr(order_data, "client_order_id", None):
            cid = _client_id(order_data)
            try:
                order_data.client_order_id = cid
            except Exception:
                dumped = order_data.model_dump()
                dumped["client_order_id"] = cid
                order_data = type(order_data)(**dumped)
            broker_module.log.info(
                f"[GUARDIA] client_order_id={cid} | symbol={getattr(order_data, 'symbol', '?')}"
            )
        return original_submit(order_data=order_data, *args, **kwargs)

    broker_module._validar_orden_compra_final = validar_con_riesgo_final
    client.submit_order = submit_order_guarded
    _INSTALLED = True


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    if name == "broker" or name.endswith(".broker"):
        try:
            _install(module)
        except Exception:
            # La aplicación puede arrancar con las defensas nativas del broker
            # aunque el hook opcional no pueda instalarse.
            pass
    return module


builtins.__import__ = _import
