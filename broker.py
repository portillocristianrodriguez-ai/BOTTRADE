"""
Todo lo que toca la API de Alpaca:
datos, posiciones y ordenes.
"""

import logging
from datetime import datetime, timedelta

import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
    OrderClass,
    QueryOrderStatus,
)

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

import config


log = logging.getLogger(__name__)


# =========================================================
# CLIENTES ALPACA
# =========================================================

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


# =========================================================
# TIMEFRAMES
# =========================================================

TIMEFRAME_ACCIONES = TimeFrame.Day
TIMEFRAME_CRIPTO = TimeFrame.Minute


# =========================================================
# UTILIDADES
# =========================================================

def es_cripto(ticker: str) -> bool:
    return "/" in ticker


def mercado_abierto() -> bool:
    return trading_client.get_clock().is_open


# =========================================================
# DATOS DE MERCADO
# =========================================================

def obtener_datos(ticker: str) -> pd.DataFrame:

    if es_cripto(ticker):

        request = CryptoBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TIMEFRAME_CRIPTO,
            start=datetime.utcnow() - timedelta(minutes=500),
        )

        bars = crypto_data_client.get_crypto_bars(
            request
        ).df

    else:

        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TIMEFRAME_ACCIONES,
            start=datetime.utcnow() - timedelta(days=500),
        )

        bars = data_client.get_stock_bars(
            request
        ).df

    if bars.empty:
        return pd.DataFrame()

    return (
        bars.xs(ticker, level=0)
        if isinstance(bars.index, pd.MultiIndex)
        else bars
    )


# =========================================================
# POSICIONES
# =========================================================

def tiene_posicion_abierta(ticker: str) -> bool:

    try:

        trading_client.get_open_position(
            ticker.replace("/", "")
        )

        return True

    except Exception:

        return False


def contar_posiciones_abiertas() -> int:

    return len(
        trading_client.get_all_positions()
    )


def obtener_posicion(ticker: str):

    try:

        return trading_client.get_open_position(
            ticker.replace("/", "")
        )

    except Exception:

        return None


def perdida_pct_no_realizada(
    ticker: str,
) -> float | None:

    try:

        posicion = obtener_posicion(ticker)

        if posicion is None:
            return None

        return float(
            posicion.unrealized_plpc
        )

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


# =========================================================
# ORDENES ABIERTAS
# =========================================================

def obtener_ordenes_abiertas(ticker: str):

    try:

        filtro = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[
                ticker.replace("/", "")
            ],
        )

        return trading_client.get_orders(
            filter=filtro
        )

    except Exception as e:

        log.error(
            f"{ticker}: error consultando "
            f"ordenes abiertas: {e}"
        )

        return []


# =========================================================
# COMPROBAR PROTECCION
# =========================================================

def tiene_proteccion(
    ticker: str,
) -> tuple[bool, bool]:

    tiene_sl = False
    tiene_tp = False

    ordenes = obtener_ordenes_abiertas(
        ticker
    )

    for orden in ordenes:

        try:

            order_type = str(
                getattr(
                    orden,
                    "type",
                    "",
                )
            ).lower()

            order_class = str(
                getattr(
                    orden,
                    "order_class",
                    "",
                )
            ).lower()

            stop_loss = getattr(
                orden,
                "stop_loss",
                None,
            )

            take_profit = getattr(
                orden,
                "take_profit",
                None,
            )

            # -------------------------------------------------
            # OCO
            # -------------------------------------------------

            if "oco" in order_class:

                if stop_loss is not None:
                    tiene_sl = True

                if take_profit is not None:
                    tiene_tp = True

            # -------------------------------------------------
            # STOP
            # -------------------------------------------------

            if "stop" in order_type:
                tiene_sl = True

            # -------------------------------------------------
            # LIMIT
            # -------------------------------------------------

            if "limit" in order_type:
                tiene_tp = True

        except Exception:

            continue

    return tiene_sl, tiene_tp


# =========================================================
# TAMAÑO DE POSICION
# =========================================================

def calcular_tamano_posicion(
    ticker: str,
    precio: float,
    atr: float,
):

    cuenta = trading_client.get_account()

    capital = float(
        cuenta.equity
    )

    riesgo_dolares = (
        capital
        * config.RISK_PER_TRADE_PCT
    )

    riesgo_por_unidad = (
        atr
        * config.ATR_STOP_MULTIPLICADOR
    )

    if (
        riesgo_por_unidad <= 0
        or pd.isna(riesgo_por_unidad)
    ):

        return 0

    if es_cripto(ticker):

        cantidad = round(
            riesgo_dolares
            / riesgo_por_unidad,
            6,
        )

        return max(
            cantidad,
            0,
        )

    return max(
        int(
            riesgo_dolares
            / riesgo_por_unidad
        ),
        0,
    )


# =========================================================
# COMPRAR
# =========================================================

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
            f"{ticker}: tamano de posicion "
            f"calculado es 0."
        )

        return None

    # -----------------------------------------------------
    # CRIPTO
    # -----------------------------------------------------

    if es_cripto(ticker):

        orden = MarketOrderRequest(
            symbol=ticker,
            qty=cantidad,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
        )

        trading_client.submit_order(
            orden
        )

        mensaje = (
            f"COMPRA {ticker}: "
            f"{cantidad} unidades "
            f"@ ~${precio:.2f} "
            f"(SL/TP manual)"
        )

        log.info(mensaje)

        return mensaje

    # -----------------------------------------------------
    # ACCIONES - BRACKET
    # -----------------------------------------------------

    stop_loss = round(
        precio
        - atr
        * config.ATR_STOP_MULTIPLICADOR,
        2,
    )

    take_profit = round(
        precio
        + atr
        * config.ATR_TAKE_PROFIT_MULTIPLICADOR,
        2,
    )

    stop_loss = max(
        stop_loss,
        0.01,
    )

    if stop_loss >= precio:

        log.error(
            f"{ticker}: SL invalido "
            f"(${stop_loss}) >= "
            f"entrada (${precio})."
        )

        return None

    if take_profit <= precio:

        log.error(
            f"{ticker}: TP invalido "
            f"(${take_profit}) <= "
            f"entrada (${precio})."
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

    trading_client.submit_order(
        orden
    )

    mensaje = (
        f"COMPRA {ticker}: "
        f"{cantidad} acciones "
        f"@ ~${precio:.2f} "
        f"(SL: ${stop_loss:.2f} | "
        f"TP: ${take_profit:.2f})"
    )

    log.info(mensaje)

    return mensaje


# =========================================================
# PROTEGER POSICION EXISTENTE
# =========================================================

def proteger_posicion(
    ticker: str,
    atr: float,
) -> str | None:

    if es_cripto(ticker):
        return None

    posicion = obtener_posicion(
        ticker
    )

    if posicion is None:
        return None

    try:

        cantidad = float(
            posicion.qty
        )

        precio_entrada = float(
            posicion.avg_entry_price
        )

    except Exception as e:

        log.error(
            f"{ticker}: no se pudo leer "
            f"la posicion: {e}"
        )

        return None

    if cantidad <= 0:
        return None

    # -----------------------------------------------------
    # COMPROBAR PROTECCION ANTES DE HACER NADA
    # -----------------------------------------------------

    tiene_sl, tiene_tp = tiene_proteccion(
        ticker
    )

    if tiene_sl and tiene_tp:

        log.info(
            f"{ticker}: posicion ya protegida "
            f"(SL OK | TP OK)."
        )

        return None

    # -----------------------------------------------------
    # SI FALTA ALGUNA PROTECCION, LIMPIAR SOLO LAS
    # ORDENES DE VENTA ABIERTAS Y CREAR UNA OCO NUEVA
    # -----------------------------------------------------

    ordenes = obtener_ordenes_abiertas(
        ticker
    )

    for orden in ordenes:

        try:

            side = str(
                getattr(
                    orden,
                    "side",
                    "",
                )
            ).lower()

            if "sell" in side:

                trading_client.cancel_order_by_id(
                    orden.id
                )

        except Exception as e:

            log.warning(
                f"{ticker}: no se pudo cancelar "
                f"orden {getattr(orden, 'id', '?')}: {e}"
            )

    stop_loss = round(
        precio_entrada
        - atr
        * config.ATR_STOP_MULTIPLICADOR,
        2,
    )

    take_profit = round(
        precio_entrada
        + atr
        * config.ATR_TAKE_PROFIT_MULTIPLICADOR,
        2,
    )

    stop_loss = max(
        stop_loss,
        0.01,
    )

    if stop_loss >= precio_entrada:

        log.error(
            f"{ticker}: SL calculado invalido."
        )

        return None

    if take_profit <= precio_entrada:

        log.error(
            f"{ticker}: TP calculado invalido."
        )

        return None

    try:

        orden = LimitOrderRequest(
            symbol=ticker,
            qty=cantidad,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.OCO,
            take_profit=TakeProfitRequest(
                limit_price=take_profit
            ),
            stop_loss=StopLossRequest(
                stop_price=stop_loss
            ),
        )

        trading_client.submit_order(
            orden
        )

        mensaje = (
            f"PROTECCION {ticker}: "
            f"SL ${stop_loss:.2f} | "
            f"TP ${take_profit:.2f} "
            f"(entrada "
            f"${precio_entrada:.2f})"
        )

        log.info(mensaje)

        return mensaje

    except Exception as e:

        log.error(
            f"{ticker}: ERROR creando "
            f"proteccion: {e}"
        )

        return None


# =========================================================
# CANCELAR ORDENES
# =========================================================

def _cancelar_ordenes_abiertas(
    ticker: str,
) -> None:

    ordenes = obtener_ordenes_abiertas(
        ticker
    )

    for orden in ordenes:

        try:

            trading_client.cancel_order_by_id(
                orden.id
            )

        except Exception as e:

            log.warning(
                f"No se pudo cancelar "
                f"orden {orden.id} "
                f"de {ticker}: {e}"
            )


# =========================================================
# VENDER
# =========================================================

def vender(
    ticker: str,
) -> str | None:

    try:

        _cancelar_ordenes_abiertas(
            ticker
        )

        trading_client.close_position(
            ticker.replace("/", "")
        )

        mensaje = (
            f"VENTA {ticker}: "
            f"posicion cerrada."
        )

        log.info(mensaje)

        return mensaje

    except Exception as e:

        log.error(
            f"Error al vender "
            f"{ticker}: {e}"
        )

        return None


# =========================================================
# MONITOR DE ORDENES EJECUTADAS
# =========================================================

_ordenes_notificadas = set()
_monitor_ejecuciones_inicializado = False


def obtener_ordenes_ejecutadas():

    try:

        filtro = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=50,
        )

        ordenes = trading_client.get_orders(
            filter=filtro
        )

        return [
            orden
            for orden in ordenes
            if str(
                getattr(
                    orden,
                    "status",
                    "",
                )
            ).lower().endswith("filled")
        ]

    except Exception as e:

        log.error(
            f"Error consultando "
            f"ordenes ejecutadas: {e}"
        )

        return []


def inicializar_monitor_ejecuciones():

    global _monitor_ejecuciones_inicializado

    if _monitor_ejecuciones_inicializado:
        return

    ordenes = obtener_ordenes_ejecutadas()

    for orden in ordenes:

        try:

            _ordenes_notificadas.add(
                str(orden.id)
            )

        except Exception:

            continue

    _monitor_ejecuciones_inicializado = True

    log.info(
        f"[ejecuciones] Monitor inicializado. "
        f"{len(_ordenes_notificadas)} "
        f"ordenes antiguas ignoradas."
    )


def detectar_ejecuciones():

    mensajes = []

    ordenes = obtener_ordenes_ejecutadas()

    for orden in ordenes:

        try:

            order_id = str(
                orden.id
            )

            if order_id in _ordenes_notificadas:
                continue

            side = str(
                getattr(
                    orden,
                    "side",
                    "",
                )
            ).lower()

            if "buy" in side:

                emoji = "🟢"
                accion = "COMPRA"

            elif "sell" in side:

                emoji = "🔴"
                accion = "VENTA"

            else:

                continue

            ticker = str(
                getattr(
                    orden,
                    "symbol",
                    "?",
                )
            )

            cantidad = getattr(
                orden,
                "filled_qty",
                None,
            )

            precio = getattr(
                orden,
                "filled_avg_price",
                None,
            )

            if cantidad is not None:

                try:

                    cantidad = float(
                        cantidad
                    )

                    cantidad_txt = (
                        f"{cantidad:g}"
                    )

                except Exception:

                    cantidad_txt = str(
                        cantidad
                    )

            else:

                cantidad_txt = "?"

            if precio is not None:

                try:

                    precio = float(
                        precio
                    )

                    precio_txt = (
                        f"${precio:.2f}"
                    )

                except Exception:

                    precio_txt = str(
                        precio
                    )

            else:

                precio_txt = (
                    "precio desconocido"
                )

            mensaje = (
                f"{emoji} {accion} EJECUTADA\n"
                f"📊 {ticker}\n"
                f"📦 Cantidad: "
                f"{cantidad_txt}\n"
                f"💰 Precio: "
                f"{precio_txt}\n"
                f"🆔 Orden: "
                f"{order_id[:8]}"
            )

            mensajes.append(
                mensaje
            )

            _ordenes_notificadas.add(
                order_id
            )

        except Exception as e:

            log.warning(
                "No se pudo procesar "
                f"una orden ejecutada: {e}"
            )

    return mensajes
