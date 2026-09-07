"""Correcciones de seguridad derivadas de la revisión operativa del 2026-09-07.

No cambia señales ni abre operaciones. Endurece la idempotencia de salidas
crypto y la detección de órdenes activas/protecciones en Alpaca.
"""
from __future__ import annotations

import time


class _CooldownRegistry(dict):
    """Registro cuyo pop normal no borra el último timestamp de ejecución.

    dynamic_exit_manager_v2 hacía pop() en finally, anulando en la práctica
    DYNAMIC_EXIT_COOLDOWN_SECONDS. Mantener el timestamp permite que el ciclo
    siguiente respete el cooldown. Los timestamps antiguos son inocuos y se
    reemplazan en la siguiente acción del mismo ticker.
    """

    def pop(self, key, default=None):
        return self.get(key, default)


_ACTIVE_STATUS_TOKENS = (
    "new",
    "accepted",
    "pending",
    "held",
    "partially_filled",
    "partially",
    "open",
    "calculated",
)


def _status_activo(order) -> bool:
    status = str(getattr(order, "status", "") or "").lower()
    return any(token in status for token in _ACTIVE_STATUS_TOKENS)


def instalar(bot_module, dynamic_exit_module) -> bool:
    """Instala los fixes sin tocar estrategia ni parámetros de trading."""
    log = getattr(bot_module, "log", None)
    broker = getattr(bot_module, "broker", None)
    if broker is None:
        return False

    # 1) Cooldown real para salidas/reducciones crypto.
    registry = getattr(dynamic_exit_module, "_LAST_ACTION", None)
    if not isinstance(registry, _CooldownRegistry):
        dynamic_exit_module._LAST_ACTION = _CooldownRegistry(registry or {})
        if log:
            log.info("[REVIEW-FIX] Cooldown persistente de salidas crypto activado.")

    # 2) obtener_ordenes_ticker debe reconocer cualquier orden activa devuelta
    # por Alpaca, incluidos estados HELD de legs OCO.
    original_abiertas = getattr(broker, "obtener_ordenes_abiertas", None)
    original_ticker = getattr(broker, "obtener_ordenes_ticker", None)
    if callable(original_abiertas) and callable(original_ticker) and not getattr(original_ticker, "_review_active_orders", False):
        def obtener_ordenes_ticker_activo(ticker):
            try:
                objetivo = broker.ticker_comparacion(ticker)
                resultado = []
                for order in original_abiertas():
                    if not _status_activo(order):
                        continue
                    symbol = getattr(order, "symbol", "")
                    if broker.ticker_comparacion(symbol) == objetivo:
                        resultado.append(order)
                return resultado
            except Exception as exc:
                if log:
                    log.warning("[REVIEW-FIX] %s: fallback de órdenes activas: %s", ticker, exc)
                return original_ticker(ticker)

        obtener_ordenes_ticker_activo._review_active_orders = True
        broker.obtener_ordenes_ticker = obtener_ordenes_ticker_activo

    # 3) Barrera adicional: una SELL crypto activa bloquea otra SELL, incluso
    # si llega desde una ruta distinta del dynamic-exit.
    original_vender = getattr(broker, "vender", None)
    if callable(original_vender) and not getattr(original_vender, "_review_sell_guard", False):
        def vender_guardado(ticker):
            try:
                if broker.es_cripto(ticker):
                    for order in broker.obtener_ordenes_ticker(ticker):
                        side = str(getattr(order, "side", "") or "").lower()
                        if "sell" in side and _status_activo(order):
                            if log:
                                log.warning(
                                    "[REVIEW-FIX] %s: SELL duplicada bloqueada; ya existe una SELL activa (%s).",
                                    ticker,
                                    getattr(order, "status", "?"),
                                )
                            return None
            except Exception as exc:
                if log:
                    log.warning("[REVIEW-FIX] %s: no se pudo comprobar SELL activa: %s", ticker, exc)
            return original_vender(ticker)

        vender_guardado._review_sell_guard = True
        broker.vender = vender_guardado

    if log:
        log.info("[REVIEW-FIX] Guardas de revisión operativa instaladas.")
    return True


__all__ = ["instalar"]
