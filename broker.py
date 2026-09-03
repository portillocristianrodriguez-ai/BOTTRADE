"""
Todo lo que toca la API de Alpaca:
- traer datos
- consultar posiciones
- ejecutar órdenes
- proteger posiciones
- detectar ejecuciones
"""

import logging
from datetime import datetime, timedelta

import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
    OrderClass,
)

from alpaca.data.historical import (
    StockHistoricalDataClient,
    CryptoHistoricalDataClient,
)

from alpaca.data.requests import (
    StockBarsRequest,
    CryptoBarsRequest,
)

from alpaca.data.timeframe import (
    TimeFrame,
    TimeFrameUnit,
)

import config


log = logging.getLogger(__name__)


# ============================================================
# CLIENTES ALPACA
# ============================================================

cliente_trading = TradingClient(
    config.ALPACA_API_KEY,
    config.ALPACA_API_SECRET,
    paper=config.ALPACA_PAPER,
)

cliente_datos_acciones = StockHistoricalDataClient(
    config.ALPACA_API_KEY,
    config.ALPACA_API_SECRET,
)

cliente_datos_crypto = CryptoHistoricalDataClient(
    config.ALPACA_API_KEY,
    config.ALPACA_API_SECRET,
)


# ============================================================
# UTILIDADES
# ============================================================

def es_cripto(ticker):
    """Determina si el símbolo corresponde a una criptomoneda."""
    return "/" in ticker


def obtener_datos(ticker, limit=200):
    """
    Obtiene datos históricos:
    - Acciones: velas diarias
    - Cripto: velas de 1 minuto
    """

    if es_cripto(ticker):

        request = CryptoBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame(1, TimeFrameUnit.Minute),
            limit=limit,
        )

        bars = cliente_datos_crypto.get_crypto_bars(request)

    else:

        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Day,
            limit=limit,
        )

        bars = cliente_datos_acciones.get_stock_bars(request)

    try:
        df = bars.df.copy()

        if df.empty:
            return df

        # Si Alpaca devuelve MultiIndex, dejamos solamente
        # el índice temporal para facilitar el procesamiento.
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index()

            if "symbol" in df.columns:
                df = df[df["symbol"] == ticker]

            if "timestamp" in df.columns:
                df = df.set_index("timestamp")

        return df

    except Exception as e:
        log.error(f"{ticker}: error procesando datos: {e}")
        return pd.DataFrame()


# ============================================================
# POSICIONES
# ============================================================

def obtener_posicion(ticker):
    """Obtiene la posición abierta de un símbolo."""

    try:
        simbolo = ticker.replace("/", "")
        return cliente_trading.get_open_position(simbolo)

    except Exception:
        return None


def tiene_posicion_abierta(ticker):
    """Devuelve True si existe una posición abierta."""

    try:
        simbolo = ticker.replace("/", "")
        cliente_trading.get_open_position(simbolo)
        return True

    except Exception:
        return False


# ============================================================
# ÓRDENES ABIERTAS
# ============================================================

def obtener_ordenes_abiertas(ticker):
    """Obtiene las órdenes abiertas de un ticker."""

    try:
        ordenes = cliente_trading.get_orders(
            filter="open"
        )

        simbolo = ticker.replace("/", "")

        return [
            orden
            for orden in ordenes
            if str(orden.symbol).replace("/", "") == simbolo
        ]

    except Exception as e:
        log.error(
            f"{ticker}: error obteniendo órdenes abiertas: {e}"
        )
        return []


# ============================================================
# PROTECCIÓN SL / TP
# ============================================================

def tiene_proteccion(ticker):
    """
    Comprueba si una posición tiene Stop Loss y Take Profit.

    Detecta:
    - órdenes OCO
    - stop
    - limit
    """

    try:

        ordenes = obtener_ordenes_abiertas(ticker)

        tiene_sl = False
        tiene_tp = False

        for orden in ordenes:

            order_class = str(
                getattr(orden, "order_class", "")
            ).lower()

            # ------------------------------------------------
            # OCO
            # ------------------------------------------------

            if "oco" in order_class:

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

                if stop_loss is not None:
                    tiene_sl = True

                if take_profit is not None:
                    tiene_tp = True

            # ------------------------------------------------
            # Órdenes individuales
            # ------------------------------------------------

            order_type = str(
                getattr(orden, "type", "")
            ).lower()

            if "stop" in order_type:
                tiene_sl = True

            if "limit" in order_type:
                tiene_tp = True

        return tiene_sl, tiene_tp

    except Exception as e:

        log.error(
            f"{ticker}: error comprobando protección: {e}"
        )

        return False, False


# ============================================================
# PROTEGER POSICIÓN
# ============================================================

def proteger_posicion(ticker):
    """
    Crea protección OCO para acciones.

    Las criptomonedas utilizan gestión manual
    desde main.py.
    """

    if es_cripto(ticker):
        return

    try:

        posicion = obtener_posicion(ticker)

        if posicion is None:
            return

        qty = float(posicion.qty)
        precio_entrada = float(
            posicion.avg_entry_price
        )

        # ----------------------------------------------------
        # COMPROBAR SI YA ESTÁ PROTEGIDA
        # ----------------------------------------------------

        tiene_sl, tiene_tp = tiene_proteccion(ticker)

        if tiene_sl and tiene_tp:

            log.info(
                f"{ticker}: posición ya protegida"
            )

            return

        # ----------------------------------------------------
        # PRECIOS DE PROTECCIÓN
        # ----------------------------------------------------

        stop_loss_pct = float(
            config.STOP_LOSS_PCT
        )

        take_profit_pct = float(
            config.TAKE_PROFIT_PCT
        )

        precio_sl = precio_entrada * (
            1 - stop_loss_pct
        )

        precio_tp = precio_entrada * (
            1 + take_profit_pct
        )

        # ----------------------------------------------------
        # CANCELAR PROTECCIONES ANTIGUAS
        # ----------------------------------------------------

        ordenes = obtener_ordenes_abiertas(ticker)

        for orden in ordenes:

            if str(orden.side).lower() == "sell":

                try:

                    cliente_trading.cancel_order_by_id(
                        orden.id
                    )

                    log.info(
                        f"{ticker}: orden SELL antigua cancelada"
                    )

                except Exception as e:

                    log.warning(
                        f"{ticker}: no se pudo cancelar "
                        f"orden antigua: {e}"
                    )

        # ----------------------------------------------------
        # CREAR OCO
        # ----------------------------------------------------

        orden_proteccion = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.OCO,
            stop_loss=StopLossRequest(
                stop_price=round(precio_sl, 2)
            ),
            take_profit=TakeProfitRequest(
                limit_price=round(precio_tp, 2)
            ),
        )

        cliente_trading.submit_order(
            order_data=orden_proteccion
        )

        log.info(
            f"PROTECCION {ticker}: "
            f"SL ${precio_sl:.2f} | "
            f"TP ${precio_tp:.2f} "
            f"(entrada ${precio_entrada:.2f})"
        )

    except Exception as e:

        log.error(
            f"{ticker}: error protegiendo posición: {e}"
        )


# ============================================================
# TAMAÑO DE POSICIÓN
# ============================================================

def calcular_tamano_posicion(ticker, precio, atr):
    """
    Calcula el tamaño de posición según riesgo.

    ACCIONES:
        Mantiene el cálculo basado en riesgo.

    CRIPTO:
        Mantiene el cálculo basado en riesgo pero aplica
        límites para evitar órdenes gigantescas.
    """

    try:

        cuenta = cliente_trading.get_account()

        capital = float(cuenta.equity)

        riesgo_dolares = (
            capital * config.RISK_PER_TRADE_PCT
        )

        if precio <= 0 or atr <= 0:
            return 0

        riesgo_por_unidad = (
            atr * config.ATR_STOP_MULTIPLICADOR
        )

        if riesgo_por_unidad <= 0:
            return 0

        # ====================================================
        # CÁLCULO ORIGINAL
        # ====================================================

        cantidad_riesgo = (
            riesgo_dolares / riesgo_por_unidad
        )

        # ====================================================
        # CRIPTO
        # ====================================================

        if es_cripto(ticker):

            # Máximo 20% del capital en una sola
            # operación de criptomonedas.
            max_notional_capital = (
                capital * 0.20
            )

            # Límite máximo de Alpaca.
            max_notional_alpaca = 200000.0

            # Intentar respetar buying power.
            try:

                buying_power = float(
                    cuenta.buying_power
                )

                max_notional_buying_power = (
                    buying_power * 0.90
                )

            except (TypeError, ValueError):

                max_notional_buying_power = (
                    max_notional_capital
                )

            # El límite final es el menor de los tres.
            max_notional = min(
                max_notional_capital,
                max_notional_alpaca,
                max_notional_buying_power,
            )

            cantidad_maxima = (
                max_notional / precio
            )

            cantidad = min(
                cantidad_riesgo,
                cantidad_maxima,
            )

            cantidad = round(
                max(cantidad, 0),
                6,
            )

            log.info(
                f"{ticker}: "
                f"tamaño cripto calculado="
                f"{cantidad_riesgo:.6f} | "
                f"limitado={cantidad:.6f} | "
                f"notional="
                f"${cantidad * precio:,.2f}"
            )

            return cantidad

        # ====================================================
        # ACCIONES
        # ====================================================

        cantidad = int(
            riesgo_dolares /
            riesgo_por_unidad
        )

        return max(cantidad, 0)

    except Exception as e:

        log.error(
            f"Error calculando tamaño de posición "
            f"para {ticker}: {e}"
        )

        return 0


# ============================================================
# COMPRAR
# ============================================================

def comprar(ticker, precio, atr):
    """Ejecuta una compra."""

    try:

        cantidad = calcular_tamano_posicion(
            ticker,
            precio,
            atr,
        )

        if cantidad <= 0:

            log.warning(
                f"{ticker}: tamaño de posición inválido"
            )

            return None

        # ====================================================
        # CRIPTO
        # ====================================================

        if es_cripto(ticker):

            orden = MarketOrderRequest(
                symbol=ticker,
                qty=cantidad,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
            )

            resultado = (
                cliente_trading.submit_order(
                    order_data=orden
                )
            )

            log.info(
                f"COMPRA {ticker}: "
                f"{cantidad} unidades "
                f"(mercado)"
            )

            return resultado

        # ====================================================
        # ACCIONES
        # ====================================================

        stop_loss_pct = float(
            config.STOP_LOSS_PCT
        )

        take_profit_pct = float(
            config.TAKE_PROFIT_PCT
        )

        precio_sl = precio * (
            1 - stop_loss_pct
        )

        precio_tp = precio * (
            1 + take_profit_pct
        )

        orden = MarketOrderRequest(
            symbol=ticker,
            qty=cantidad,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            stop_loss=StopLossRequest(
                stop_price=round(
                    precio_sl,
                    2,
                )
            ),
            take_profit=TakeProfitRequest(
                limit_price=round(
                    precio_tp,
                    2,
                )
            ),
        )

        resultado = (
            cliente_trading.submit_order(
                order_data=orden
            )
        )

        log.info(
            f"COMPRA {ticker}: "
            f"{cantidad} acciones | "
            f"SL ${precio_sl:.2f} | "
            f"TP ${precio_tp:.2f}"
        )

        return resultado

    except Exception as e:

        log.error(
            f"{ticker}: error ejecutando compra: {e}"
        )

        return None


# ============================================================
# VENDER
# ============================================================

def vender(ticker):
    """Cierra una posición."""

    try:

        simbolo = ticker.replace("/", "")

        posicion = cliente_trading.get_open_position(
            simbolo
        )

        qty = float(posicion.qty)

        # ----------------------------------------------------
        # CANCELAR ÓRDENES ABIERTAS
        # ----------------------------------------------------

        ordenes = obtener_ordenes_abiertas(ticker)

        for orden in ordenes:

            try:

                cliente_trading.cancel_order_by_id(
                    orden.id
                )

            except Exception as e:

                log.warning(
                    f"{ticker}: error cancelando "
                    f"orden {orden.id}: {e}"
                )

        # ----------------------------------------------------
        # CERRAR POSICIÓN
        # ----------------------------------------------------

        orden = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=(
                TimeInForce.GTC
                if es_cripto(ticker)
                else TimeInForce.DAY
            ),
        )

        resultado = (
            cliente_trading.submit_order(
                order_data=orden
            )
        )

        log.info(
            f"VENTA {ticker}: "
            f"{qty} unidades"
        )

        return resultado

    except Exception as e:

        log.error(
            f"{ticker}: error ejecutando venta: {e}"
        )

        return None


# ============================================================
# MONITOR DE EJECUCIONES
# ============================================================

_ordenes_notificadas = set()

_monitor_ejecuciones_inicializado = False


def obtener_ordenes_ejecutadas():
    """
    Obtiene órdenes FILLED recientes.
    """

    try:

        ordenes = cliente_trading.get_orders(
            filter="closed",
            limit=100,
        )

        ejecutadas = []

        for orden in ordenes:

            status = str(
                getattr(
                    orden,
                    "status",
                    ""
                )
            ).lower()

            if status == "filled":
                ejecutadas.append(orden)

        return ejecutadas

    except Exception as e:

        log.error(
            f"[ejecuciones] "
            f"Error obteniendo ejecuciones: {e}"
        )

        return []


def inicializar_monitor_ejecuciones():
    """
    Marca como antiguas todas las órdenes ya ejecutadas
    cuando arranca el bot.
    """

    global _monitor_ejecuciones_inicializado

    if _monitor_ejecuciones_inicializado:
        return

    try:

        ordenes = obtener_ordenes_ejecutadas()

        for orden in ordenes:

            _ordenes_notificadas.add(
                str(orden.id)
            )

        _monitor_ejecuciones_inicializado = True

        log.info(
            "[ejecuciones] Monitor inicializado. "
            f"{len(ordenes)} ordenes antiguas ignoradas."
        )

    except Exception as e:

        log.error(
            f"[ejecuciones] "
            f"Error inicializando monitor: {e}"
        )


def detectar_ejecuciones():
    """
    Detecta nuevas órdenes ejecutadas.

    Devuelve una lista de mensajes.
    """

    global _monitor_ejecuciones_inicializado

    if not _monitor_ejecuciones_inicializado:

        inicializar_monitor_ejecuciones()

        return []

    mensajes = []

    try:

        ordenes = obtener_ordenes_ejecutadas()

        for orden in ordenes:

            order_id = str(orden.id)

            if order_id in _ordenes_notificadas:
                continue

            _ordenes_notificadas.add(
                order_id
            )

            side = str(
                getattr(
                    orden,
                    "side",
                    ""
                )
            ).lower()

            simbolo = getattr(
                orden,
                "symbol",
                ""
            )

            qty = getattr(
                orden,
                "filled_qty",
                None
            )

            precio = getattr(
                orden,
                "filled_avg_price",
                None
            )

            if side == "buy":

                emoji = "🟢"
                tipo = "COMPRA"

            elif side == "sell":

                emoji = "🔴"
                tipo = "VENTA"

            else:

                emoji = "⚪"
                tipo = side.upper()

            mensaje = (
                f"{emoji} {tipo} EJECUTADA\n"
                f"Ticker: {simbolo}\n"
                f"Cantidad: {qty}\n"
                f"Precio: ${precio}\n"
                f"Order ID: {order_id}"
            )

            mensajes.append(mensaje)

            log.info(
                f"[ejecuciones] "
                f"{tipo} {simbolo} "
                f"qty={qty} "
                f"precio={precio}"
            )

        return mensajes

    except Exception as e:

        log.error(
            f"[ejecuciones] "
            f"Error detectando ejecuciones: {e}"
        )

        return []
