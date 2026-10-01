"""Correcciones de seguridad derivadas de la revisión operativa del 2026-09-07.

No cambia señales ni abre operaciones. Endurece la idempotencia de salidas
crypto, la detección de órdenes activas/protecciones y reconcilia en PAPER
órdenes BUY de mercado antiguas que nunca recibieron ningún fill.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import threading


class _CooldownRegistry(dict):
    """Registro cuyo pop normal no borra el último timestamp de ejecución."""
    def pop(self, key, default=None):
        return self.get(key, default)


_ACTIVE_STATUSES = {
    "new", "accepted", "pending", "held", "partially_filled",
    "partially", "open", "calculated", "pending_new", "pending_cancel",
    "pending_replace", "accepted_for_bidding", "stopped", "suspended",
    "done_for_day",
}


def _enum_value(value):
    return str(getattr(value, "value", value) or "").lower().rsplit(".", 1)[-1]


def _status_activo(order) -> bool:
    return _enum_value(getattr(order, "status", "")) in _ACTIVE_STATUSES


def _edad_segundos(order, now=None):
    value = getattr(order, "created_at", None) or getattr(order, "submitted_at", None)
    if value is None:
        return None
    if isinstance(value, datetime):
        created = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        try:
            text = str(value).replace("Z", "+00:00")
            created = datetime.fromisoformat(text)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - created).total_seconds())


def _reconciliar_market_buys_paper(bot_module, broker, log):
    """Cancela BUY market PAPER sin fills que lleven >=30 min activas.

    Nunca se ejecuta en LIVE. No cancela SELL, stops, OCO, limits ni órdenes
    parcialmente ejecutadas.
    """
    config = getattr(bot_module, "config", None)
    if getattr(config, "PAPER", False) is not True:
        return 0
    client = getattr(broker, "cliente_trading", None)
    if client is None:
        return 0
    canceladas = 0
    try:
        orders = broker.obtener_ordenes_abiertas(strict=True)
    except Exception as exc:
        if log:
            log.warning("[REVIEW-FIX] No se pudieron consultar BUY market antiguas: %s", exc)
        return 0
    for order in orders:
        try:
            if not _status_activo(order):
                continue
            side = _enum_value(getattr(order, "side", ""))
            order_type = _enum_value(getattr(order, "type", ""))
            order_class = _enum_value(getattr(order, "order_class", ""))
            filled_qty = float(getattr(order, "filled_qty", None))
            age = _edad_segundos(order)
            if side != "buy" or order_type != "market" or order_class != "simple":
                continue
            if not math.isfinite(filled_qty) or filled_qty != 0:
                continue
            if age is None or age < 1800:
                continue
            client.cancel_order_by_id(order.id)
            canceladas += 1
            if log:
                log.warning(
                    "[REVIEW-FIX] %s: BUY market PAPER sin fill cancelada tras %.0f min (id=%s).",
                    getattr(order, "symbol", "?"), age / 60.0, order.id,
                )
        except Exception as exc:
            if log:
                log.warning("[REVIEW-FIX] BUY market omitida durante reconciliación: %s", exc)
    return canceladas


def instalar(bot_module, dynamic_exit_module) -> bool:
    """Instala los fixes sin cambiar señales ni parámetros de trading."""
    log = getattr(bot_module, "log", None)
    broker = getattr(bot_module, "broker", None)
    if broker is None:
        return False

    registry = getattr(dynamic_exit_module, "_LAST_ACTION", None)
    if not isinstance(registry, _CooldownRegistry):
        dynamic_exit_module._LAST_ACTION = _CooldownRegistry(registry or {})
        if log:
            log.info("[REVIEW-FIX] Cooldown persistente de salidas crypto activado.")

    original_abiertas = getattr(broker, "obtener_ordenes_abiertas", None)
    original_ticker = getattr(broker, "obtener_ordenes_ticker", None)
    if callable(original_abiertas) and callable(original_ticker) and not getattr(original_ticker, "_review_active_orders", False):
        def obtener_ordenes_ticker_activo(ticker):
            try:
                objetivo = broker.ticker_comparacion(ticker)
                resultado = []
                for order in original_abiertas(strict=True):
                    if not _status_activo(order):
                        continue
                    if broker.ticker_comparacion(getattr(order, "symbol", "")) == objetivo:
                        resultado.append(order)
                return resultado
            except Exception as exc:
                if log:
                    log.warning("[REVIEW-FIX] %s: consulta de órdenes activas fallida: %s", ticker, exc)
                raise
        obtener_ordenes_ticker_activo._review_active_orders = True
        broker.obtener_ordenes_ticker = obtener_ordenes_ticker_activo

    original_vender = getattr(broker, "vender", None)
    if callable(original_vender) and not getattr(original_vender, "_review_sell_guard", False):
        sell_lock = getattr(broker, "_lock_ordenes", None)
        if sell_lock is None:
            sell_lock = threading.RLock()
            broker._lock_ordenes = sell_lock
        def vender_guardado(ticker):
            with sell_lock:
                return vender_comprobado(ticker)

        def vender_comprobado(ticker):
            try:
                if broker.es_cripto(ticker):
                    for order in broker.obtener_ordenes_ticker(ticker):
                        side = str(getattr(order, "side", "") or "").lower()
                        if "sell" in side and _status_activo(order):
                            if log:
                                log.warning(
                                    "[REVIEW-FIX] %s: SELL duplicada bloqueada; ya existe SELL activa (%s).",
                                    ticker, getattr(order, "status", "?"),
                                )
                            return None
            except Exception as exc:
                if log:
                    log.warning("[REVIEW-FIX] %s: no se pudo comprobar SELL activa: %s", ticker, exc)
                return None
            return original_vender(ticker)
        vender_guardado._review_sell_guard = True
        broker.vender = vender_guardado

    canceladas = _reconciliar_market_buys_paper(bot_module, broker, log)
    if log:
        log.info("[REVIEW-FIX] Guardas instaladas; BUY market PAPER antiguas canceladas=%s.", canceladas)
    return True


__all__ = ["instalar"]
