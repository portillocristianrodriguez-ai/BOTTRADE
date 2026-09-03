"""Todo lo que toca la API de Alpaca: datos, posiciones y órdenes."""

import logging
from datetime import datetime, timedelta

import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
    OrderClass,
    QueryOrderStatus,
    OrderType,
)

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

import config

log = logging.getLogger(__name__)

trading_client = TradingClient(
    config.API_KEY,
    config.API_SECRET,
    paper=config.PAPER,
)

data_client = StockHistoricalDataClient(
    config.API_KEY,
    config.API_SECRET,
)

crypto_data_client = CryptoHistoricalDataClient()

TIMEFRAME_ACCIONES = TimeFrame.Day
TIMEFRAME_CRIPTO = TimeFrame.Minute


def es_cripto(ticker: str) -> bool:
    return "/" in ticker


def mercado_abierto() -> bool:
    return trading_client.get_clock().is_open


def obtener_datos(ticker: str) -> pd.DataFrame:
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

    return (
        bars.xs(ticker, level=0)
        if isinstance(bars.index, pd.MultiIndex)
        else bars
    )


def tiene_posicion_abierta(ticker: str) -> bool:
    try:
        trading_client.get_open_position(ticker.replace("/", ""))
        return True
    except Exception:
        return False


def contar_posiciones_abiertas() -> int:
    return len(trading_client.get_all_positions())


def obtener_posicion(ticker: str):
    try:
        return trading_client.get_open_position(
            ticker.replace("/", "")
        )
    except Exception:
        return None


def perdida_pct_no_realizada(ticker: str) -> float | None:
    try:
        posicion = obtener_posicion(ticker)

        if posicion is None:
            return None

        return float(posicion.unrealized_plpc)

    except Exception:
        return None


def precio_actual_posicion(ticker: str):
    try:
        posicion = obtener_posicion(ticker)

        if posicion is None:
            return None

        return (
            float(posicion.avg_entry_price),
            float(posicion.current_price),
        )

    except Exception:
        return None


def obtener_ordenes_abiertas(ticker: str):
    """Devuelve las órdenes abiertas de un ticker."""
    try:
        filtro = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[ticker],
        )

        return trading_client.get_orders(filter=filtro)

    except Exception as e:
        log.error(
            f"{ticker}: error consultando órdenes abiertas: {e}"
        )
        return []


def tiene_proteccion(ticker: str) -> tuple[bool, bool]:
    """
    Comprueba si una posición tiene Stop Loss y Take Profit abiertos.

    Devuelve:
        (tiene_stop_loss, tiene_take_profit)
    """

    stop = False
    take_profit = False

    ordenes = obtener_ordenes_abiertas(ticker)

    for orden in ordenes:
        try:
            # Orden OCO principal
            if str(orden.order_class).lower().endswith("oco"):
                if orden.take_profit is not None:
                    take_profit = True

                if orden.stop_loss is not None:
                    stop = True

            # Órdenes hijas de un bracket
            orden_tipo = str(getattr(orden, "type", "")).lower()

            if "stop" in orden_tipo:
                stop = True

            if "limit" in orden_tipo:
                take_profit = True

        except Exception:
            continue

    return stop, take_profit


def calcular_tamano_posicion(
    ticker: str,
    precio: float,
    atr: float,
):
    cuenta = trading_client.get_account()

    capital = float(cuenta.equity)
    riesgo_dolares = capital * config.RISK_PER_TRADE_PCT

    riesgo_por_unidad = (
        atr * config.ATR_STOP_MULTIPLICADOR
    )

    if (
        riesgo_por_unidad <= 0
        or pd.isna(riesgo_por_unidad)
    ):
        return 0

    if es_cripto(ticker):
        cantidad = round(
            riesgo_dolares / riesgo_por_unidad,
            6,
        )
        return max(cantidad, 0)

    return max(
        int(riesgo_dolares / riesgo_por_unidad),
        0,
    )


def comprar(
    ticker: str,
    precio: float,
    atr: float,
) -> str | None:

    cantidad = calcular_tamano_posicion(
        ticker,
        precio,
        atr,
    )

    if cantidad <= 0:
        log.warning(
            f"{ticker}: tamaño de posición calculado es 0."
        )
        return None

    # =========================================================
    # CRIPTO
    # =========================================================

    if es_cripto(ticker):

        orden = MarketOrderRequest(
            symbol=ticker,
            qty=cantidad,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
        )

        trading_client.submit_order(orden)

        mensaje = (
            f"COMPRA {ticker}: {cantidad} unidades "
            f"@ ~${precio:.2f} "
            f"(SL/TP manual)"
        )

        log.info(mensaje)

        return mensaje

    # =========================================================
    # ACCIONES — BRACKET
    # =========================================================

    stop_loss = round(
        precio - atr * config.ATR_STOP_MULTIPLICADOR,
        2,
    )

    take_profit = round(
        precio + atr * config.ATR_TAKE_PROFIT_MULTIPLICADOR,
        2,
    )

    stop_loss = max(stop_loss, 0.01)

    # Seguridad: el SL debe estar por debajo
    # y el TP por encima del precio de entrada.
    if stop_loss >= precio:
        log.error(
            f"{ticker}: SL inválido "
            f"(${stop_loss}) >= entrada (${precio})."
        )
        return None

    if take_profit <= precio:
        log.error(
            f"{ticker}: TP inválido "
            f"(${take_profit}) <= entrada (${precio})."
        )
        return None

    orden = MarketOrderRequest(
        symbol=ticker,
        qty=cantidad,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        stop_loss=StopLossRequest(
            stop_price=stop_loss
        ),
        take_profit=TakeProfitRequest(
            limit_price=take_profit
        ),
    )

    trading_client.submit_order(orden)

    mensaje = (
        f"COMPRA {ticker}: {cantidad} acciones "
        f"@ ~${precio:.2f} "
        f"(SL: ${stop_loss:.2f} | "
        f"TP: ${take_profit:.2f})"
    )

    log.info(mensaje)

    return mensaje


def proteger_posicion(
    ticker: str,
    atr: float,
) -> str | None:
    """
    Protege una posición de acciones existente que no tenga
    Stop Loss y/o Take Profit.

    Utiliza una orden OCO para que solo uno de los dos exits
    pueda ejecutarse.
    """

    if es_cripto(ticker):
        return None

    posicion = obtener_posicion(ticker)

    if posicion is None:
        return None

    try:
        cantidad = float(posicion.qty)
        precio_entrada = float(posicion.avg_entry_price)

    except Exception as e:
        log.error(
            f"{ticker}: no se pudo leer la posición: {e}"
        )
        return None

    if cantidad <= 0:
        return None

    tiene_sl, tiene_tp = tiene_proteccion(ticker)

    if tiene_sl and tiene_tp:
        log.info(
            f"{ticker}: posición ya protegida "
            f"(SL ✅ | TP ✅)."
        )
        return None

    # Si hay alguna orden abierta de salida incompleta,
    # la eliminamos antes de crear la protección completa.
    ordenes = obtener_ordenes_abiertas(ticker)

    for orden in ordenes:
        try:
            side = str(orden.side).lower()

            if "sell" in side:
                trading_client.cancel_order_by_id(orden.id)

        except Exception as e:
            log.warning(
                f"{ticker}: no se pudo cancelar "
                f"orden {orden.id}: {e}"
            )

    stop_loss = round(
        precio_entrada
        - atr * config.ATR_STOP_MULTIPLICADOR,
        2,
    )

    take_profit = round(
        precio_entrada
        + atr * config.ATR_TAKE_PROFIT_MULTIPLICADOR,
        2,
    )

    stop_loss = max(stop_loss, 0.01)

    if stop_loss >= precio_entrada:
        log.error(
            f"{ticker}: SL calculado inválido."
        )
        return None

    if take_profit <= precio_entrada:
        log.error(
            f"{ticker}: TP calculado inválido."
        )
        return None

    try:
        orden = LimitOrderRequest(
            symbol=ticker,
            qty=cantidad,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.OCO,
            limit_price=take_profit,
            take_profit=TakeProfitRequest(
                limit_price=take_profit
            ),
            stop_loss=StopLossRequest(
                stop_price=stop_loss
            ),
        )

        trading_client.submit_order(orden)

        mensaje = (
            f"🛡️ PROTECCIÓN {ticker}: "
            f"SL ${stop_loss:.2f} | "
            f"TP ${take_profit:.2f} "
            f"(entrada ${precio_entrada:.2f})"
        )

        log.info(mensaje)

        return mensaje

    except Exception as e:
        log.error(
            f"{ticker}: ERROR creando protección: {e}"
        )
        return None


def _cancelar_ordenes_abiertas(
    ticker: str,
) -> None:

    ordenes = obtener_ordenes_abiertas(ticker)

    for orden in ordenes:
        try:
            trading_client.cancel_order_by_id(
                orden.id
            )

        except Exception as e:
            log.warning(
                f"No se pudo cancelar orden "
                f"{orden.id} de {ticker}: {e}"
            )


def vender(ticker: str) -> str | None:

    try:
        _cancelar_ordenes_abiertas(ticker)

        trading_client.close_position(
            ticker.replace("/", "")
        )

        mensaje = (
            f"VENTA {ticker}: posición cerrada."
        )

        log.info(mensaje)

        return mensaje

    except Exception as e:

        log.error(
            f"Error al vender {ticker}: {e}"
        )

        return None
