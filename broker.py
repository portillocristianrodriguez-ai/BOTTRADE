"""Todo lo que toca la API de Alpaca: traer datos y ejecutar órdenes.

Soporta dos tipos de ticker:
- Acciones (ej. "AAPL"): velas DIARIAS (la EMA_TENDENCIA=200 representa
  tendencia real de ~10 meses, no ruido de corto plazo), bracket orders
  (stop-loss + take-profit automáticos), solo operan en horario de mercado.
- Cripto (ej. "BTC/USD", con "/"): velas de 1 minuto, operan 24/7, pero
  Alpaca NO soporta bracket orders para cripto, así que la salida depende
  del stop-loss/trailing manual en main.py.
"""

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
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

import config

log = logging.getLogger(__name__)

trading_client = TradingClient(config.API_KEY, config.API_SECRET, paper=config.PAPER)
data_client = StockHistoricalDataClient(config.API_KEY, config.API_SECRET)
crypto_data_client = CryptoHistoricalDataClient()

TIMEFRAME_ACCIONES = TimeFrame.Day
TIMEFRAME_CRIPTO = TimeFrame.Minute


def es_cripto(ticker: str) -> bool:
    return "/" in ticker


def mercado_abierto() -> bool:
    return trading_client.get_clock().is_open


def obtener_datos(ticker: str) -> pd.DataFrame:
    """Acciones: velas diarias, con ~500 días naturales de histórico
    (sobra para EMA_TENDENCIA=200, que necesita ~200 velas de mercado).
    Cripto: velas de 1 min, con las últimas ~500 velas (mercado 24/7)."""
    if es_cripto(ticker):
        request = CryptoBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TIMEFRAME_CRIPTO,
            start=datetime.utcnow() - timedelta(minutes=500),
        )
        bars = crypto_data_client.get_crypto_bars(request).df
    else:
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TIMEFRAME_ACCIONES,
            start=datetime.utcnow() - timedelta(days=500),
        )
        bars = data_client.get_stock_bars(request).df

    if bars.empty:
        return pd.DataFrame()
    return bars.xs(ticker, level=0) if isinstance(bars.index, pd.MultiIndex) else bars


def tiene_posicion_abierta(ticker: str) -> bool:
    try:
        trading_client.get_open_position(ticker.replace("/", ""))
        return True
    except Exception:
        return False


def contar_posiciones_abiertas() -> int:
    return len(trading_client.get_all_positions())


def perdida_pct_no_realizada(ticker: str) -> float | None:
    try:
        posicion = trading_client.get_open_position(ticker.replace("/", ""))
        return float(posicion.unrealized_plpc)
    except Exception:
        return None


def precio_actual_posicion(ticker: str):
    try:
        posicion = trading_client.get_open_position(ticker.replace("/", ""))
        return float(posicion.avg_entry_price), float(posicion.current_price)
    except Exception:
        return None


def calcular_tamano_posicion(ticker: str, precio: float, atr: float):
    cuenta = trading_client.get_account()
    capital = float(cuenta.equity)
    riesgo_dolares = capital * config.RISK_PER_TRADE_PCT

    riesgo_por_unidad = atr * config.ATR_STOP_MULTIPLICADOR
    if riesgo_por_unidad <= 0 or pd.isna(riesgo_por_unidad):
        return 0

    if es_cripto(ticker):
        cantidad = round(riesgo_dolares / riesgo_por_unidad, 6)
        return max(cantidad, 0)
    return max(int(riesgo_dolares / riesgo_por_unidad), 0)


def comprar(ticker: str, precio: float, atr: float) -> str | None:
    cantidad = calcular_tamano_posicion(ticker, precio, atr)
    if cantidad <= 0:
        log.warning(f"{ticker}: tamaño de posición calculado es 0, se omite orden.")
        return None

    if es_cripto(ticker):
        orden = MarketOrderRequest(
            symbol=ticker,
            qty=cantidad,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
        )
        trading_client.submit_order(orden)
        mensaje = (
            f"COMPRA {ticker}: {cantidad} unidades @ ~${precio:.2f} "
            f"(sin SL/TP automático — gestionado por stop-loss/trailing manual)"
        )
        log.info(mensaje)
        return mensaje

    stop_loss = round(precio - atr * config.ATR_STOP_MULTIPLICADOR, 2)
    take_profit = round(precio + atr * config.ATR_TAKE_PROFIT_MULTIPLICADOR, 2)
    stop_loss = max(stop_loss, 0.01)

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
        f"(SL: ${stop_loss} [ATR x{config.ATR_STOP_MULTIPLICADOR}], "
        f"TP: ${take_profit} [ATR x{config.ATR_TAKE_PROFIT_MULTIPLICADOR}])"
    )
    log.info(mensaje)
    return mensaje


def _cancelar_ordenes_abiertas(ticker: str) -> None:
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
        trading_client.close_position(ticker.replace("/", ""))
        mensaje = f"VENTA {ticker}: posición cerrada."
        log.info(mensaje)
        return mensaje
    except Exception as e:
        log.error(f"Error al vender {ticker}: {e}")
        return None
