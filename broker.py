"""Todo lo que toca la API de Alpaca: traer datos y ejecutar órdenes."""

import logging
from datetime import datetime, timedelta

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

import config

log = logging.getLogger(__name__)

trading_client = TradingClient(config.API_KEY, config.API_SECRET, paper=config.PAPER)
data_client = StockHistoricalDataClient(config.API_KEY, config.API_SECRET)


def mercado_abierto() -> bool:
    return trading_client.get_clock().is_open


def obtener_datos(ticker: str, minutos_historia: int = 500) -> pd.DataFrame:
    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Minute,
        start=datetime.utcnow() - timedelta(minutes=minutos_historia),
    )
    bars = data_client.get_stock_bars(request).df
    if bars.empty:
        return pd.DataFrame()
    return bars.xs(ticker, level=0) if isinstance(bars.index, pd.MultiIndex) else bars


def tiene_posicion_abierta(ticker: str) -> bool:
    try:
        trading_client.get_open_position(ticker)
        return True
    except Exception:
        return False


def contar_posiciones_abiertas() -> int:
    return len(trading_client.get_all_positions())


def calcular_tamano_posicion(precio: float) -> int:
    cuenta = trading_client.get_account()
    capital = float(cuenta.equity)
    riesgo_dolares = capital * config.RISK_PER_TRADE_PCT
    riesgo_por_accion = precio * config.STOP_LOSS_PCT
    if riesgo_por_accion <= 0:
        return 0
    return max(int(riesgo_dolares / riesgo_por_accion), 0)


def comprar(ticker: str, precio: float) -> str | None:
    """Ejecuta una compra con bracket order (stop-loss + take-profit incluidos).
    Devuelve un mensaje descriptivo, o None si no se ejecutó nada."""
    cantidad = calcular_tamano_posicion(precio)
    if cantidad <= 0:
        log.warning(f"{ticker}: tamaño de posición calculado es 0, se omite orden.")
        return None

    stop_loss = round(precio * (1 - config.STOP_LOSS_PCT), 2)
    take_profit = round(precio * (1 + config.TAKE_PROFIT_PCT), 2)

    orden = MarketOrderRequest(
        symbol=ticker,
        qty=cantidad,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        stop_loss=StopLossRequest(stop_price=stop_loss),
        take_profit=TakeProfitRequest(limit_price=take_profit),
    )
    trading_client.submit_order(orden)
    mensaje = (
        f"COMPRA {ticker}: {cantidad} acciones @ ~${precio:.2f} "
        f"(SL: ${stop_loss}, TP: ${take_profit})"
    )
    log.info(mensaje)
    return mensaje


def _cancelar_ordenes_abiertas(ticker: str) -> None:
    """Cancela las órdenes abiertas (p. ej. stop-loss/take-profit pendientes de
    un bracket order) de un ticker concreto. Necesario antes de vender, porque
    esas órdenes 'reservan' las acciones (held_for_orders) e impiden cerrar
    la posición con close_position()."""
    filtro = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
    ordenes = trading_client.get_orders(filter=filtro)
    for orden in ordenes:
        try:
            trading_client.cancel_order_by_id(orden.id)
        except Exception as e:
            log.warning(f"No se pudo cancelar orden {orden.id} de {ticker}: {e}")


def vender(ticker: str) -> str | None:
    try:
        _cancelar_ordenes_abiertas(ticker)
        trading_client.close_position(ticker)
        mensaje = f"VENTA {ticker}: posición cerrada."
        log.info(mensaje)
        return mensaje
    except Exception as e:
        log.error(f"Error al vender {ticker}: {e}")
        return None
