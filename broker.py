"""
Todo lo que toca la API de Alpaca:
- Datos históricos
- Posiciones
- Órdenes
- Compras y ventas
- Stop Loss / Take Profit
- Trailing/SL manual de cripto
- Monitor de ejecuciones
"""

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
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
from alpaca.data.enums import Datafeed

import config


# =========================================================
# LOG
# =========================================================

log = logging.getLogger(__name__)


# =========================================================
# CLIENTES ALPACA
# =========================================================

cliente_trading = TradingClient(
    config.API_KEY,
    config.API_SECRET,
    paper=config.PAPER,
)

cliente_datos_acciones = StockHistoricalDataClient(
    config.API_KEY,
    config.API_SECRET,
)

cliente_datos_cripto = CryptoHistoricalDataClient(
    config.API_KEY,
    config.API_SECRET,
)


# =========================================================
# UTILIDADES
# =========================================================

def es_cripto(ticker: str) -> bool:
    """
    Determina si un símbolo es de criptomoneda.
    Ejemplo:
        BTC/USD -> True
        ETH/USD -> True
        NVDA    -> False
    """

    return "/" in ticker


def mercado_abierto() -> bool:
    """
    Devuelve True si el mercado de acciones está abierto.
    """

    try:

        reloj = cliente_trading.get_clock()

        return bool(reloj.is_open)

    except Exception as e:

        log.error(
            f"Error comprobando mercado: {e}"
        )

        return False


# =========================================================
# DATOS HISTÓRICOS
# =========================================================

def obtener_datos(ticker: str) -> pd.DataFrame:
    """
    Obtiene datos históricos.

    Acciones:
        Velas diarias.

    Cripto:
        Velas de 1 minuto.

    Devuelve DataFrame con:
        open
        high
        low
        close
        volume
    """

    try:

        ahora = datetime.now(timezone.utc)

        # =================================================
        # CRIPTO
        # =================================================

        if es_cripto(ticker):

            # Suficientes velas para EMA/MACD/RSI/ATR
            inicio = ahora - timedelta(
                minutes=500
            )

            request = CryptoBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame(
                    1,
                    TimeFrameUnit.Minute,
                ),
                start=inicio,
                end=ahora,
                limit=500,
            )

            resultado = cliente_datos_cripto.get_crypto_bars(
                request
            )

        # =================================================
        # ACCIONES
        # =================================================

        else:

            # Necesitamos bastantes velas diarias,
            # especialmente por EMA 200.
            inicio = ahora - timedelta(
                days=500
            )

            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Day,
                start=inicio,
                end=ahora,
                limit=300,
                feed=DataFeed=300
            )

            resultado = cliente_datos_acciones.get_stock_bars(
                request
            )

        # =================================================
        # DATAFRAME
        # =================================================

        df = resultado.df.copy()

        if df.empty:

            log.warning(
                f"{ticker}: Alpaca no devolvió datos."
            )

            return pd.DataFrame()

        # =================================================
        # MULTIINDEX DE ALPACA
        # =================================================

        if isinstance(df.index, pd.MultiIndex):

            niveles = list(df.index.names)

            if "symbol" in niveles:

                try:

                    df = df.xs(
                        ticker,
                        level="symbol",
                    )

                except KeyError:

                    # Algunos símbolos pueden venir
                    # normalizados de otra manera.
                    try:

                        df = df.xs(
                            ticker.upper(),
                            level="symbol",
                        )

                    except KeyError:

                        log.warning(
                            f"{ticker}: no se encontró "
                            f"el símbolo en los datos."
                        )

                        return pd.DataFrame()

        # =================================================
        # NORMALIZAR COLUMNAS
        # =================================================

        df.columns = [
            str(col).lower()
            for col in df.columns
        ]

        columnas_necesarias = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        faltantes = [
            columna
            for columna in columnas_necesarias
            if columna not in df.columns
        ]

        if faltantes:

            log.error(
                f"{ticker}: faltan columnas "
                f"en los datos: {faltantes}"
            )

            return pd.DataFrame()

        df = df[
            columnas_necesarias
        ].copy()

        # =================================================
        # LIMPIEZA
        # =================================================

        for columna in columnas_necesarias:

            df[columna] = pd.to_numeric(
                df[columna],
                errors="coerce",
            )

        df = df.dropna(
            subset=[
                "open",
                "high",
                "low",
                "close",
            ]
        )

        df = df.sort_index()

        # Eliminar duplicados
        df = df[
            ~df.index.duplicated(
                keep="last"
            )
        ]

        return df

    except Exception as e:

        log.error(
            f"{ticker}: error obteniendo datos: {e}"
        )

        return pd.DataFrame()


# =========================================================
# POSICIONES
# =========================================================

def obtener_posicion(ticker: str):
    """
    Devuelve la posición abierta de un ticker.
    Si no existe, devuelve None.
    """

    try:

        return cliente_trading.get_open_position(
            ticker
        )

    except Exception:

        return None


def tiene_posicion_abierta(ticker: str) -> bool:
    """
    Comprueba si existe una posición abierta.
    """

    try:

        posicion = obtener_posicion(
            ticker
        )

        return posicion is not None

    except Exception:

        return False


def contar_posiciones_abiertas() -> int:
    """
    Cuenta todas las posiciones abiertas
    en la cuenta Alpaca.

    Se utiliza para respetar
    MAX_POSICIONES_ABIERTAS.
    """

    try:

        posiciones = (
            cliente_trading.get_all_positions()
        )

        return len(posiciones)

    except Exception as e:

        log.error(
            f"Error contando posiciones abiertas: {e}"
        )

        return 0


# =========================================================
# ÓRDENES ABIERTAS
# =========================================================

def obtener_ordenes_abiertas():
    """
    Obtiene las órdenes actualmente abiertas.
    """

    try:

        request = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
        )

        return cliente_trading.get_orders(
            filter=request
        )

    except Exception as e:

        log.error(
            f"Error obteniendo órdenes abiertas: {e}"
        )

        return []


# =========================================================
# PROTECCIÓN DE POSICIONES
# =========================================================

def tiene_proteccion(ticker: str) -> bool:
    """
    Comprueba si una posición tiene órdenes
    de protección de venta.

    Busca órdenes abiertas SELL asociadas
    al ticker que tengan stop-loss o take-profit.

    Esto evita cancelar/recrear la protección
    continuamente cada ciclo.
    """

    try:

        ordenes = obtener_ordenes_abiertas()

        for orden in ordenes:

            try:

                simbolo = str(
                    getattr(
                        orden,
                        "symbol",
                        "",
                    )
                ).upper()

                lado = getattr(
                    orden,
                    "side",
                    None,
                )

                if simbolo != ticker.upper():

                    continue

                if lado != OrderSide.SELL:

                    continue

                order_class = getattr(
                    orden,
                    "order_class",
                    None,
                )

                # OCO / BRACKET
                if order_class in (
                    OrderClass.OCO,
                    OrderClass.BRACKET,
                ):

                    return True

                # Órdenes hijas de protección
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

                if (
                    stop_loss is not None
                    or take_profit is not None
                ):

                    return True

                # Por seguridad, detectar también
                # órdenes simples con stop_price
                stop_price = getattr(
                    orden,
                    "stop_price",
                    None,
                )

                if stop_price is not None:

                    return True

            except Exception:

                continue

        return False

    except Exception as e:

        log.error(
            f"{ticker}: error comprobando "
            f"protección: {e}"
        )

        return False


def proteger_posicion(
    ticker: str,
    atr_actual: float,
):
    """
    Protege una posición existente de acciones
    mediante una orden OCO:

        Stop Loss
        Take Profit

    No recrea la protección si ya existe.
    """

    try:

        if es_cripto(ticker):

            return None

        posicion = obtener_posicion(
            ticker
        )

        if posicion is None:

            return None

        if tiene_proteccion(ticker):

            return None

        cantidad = float(
            posicion.qty
        )

        precio_entrada = float(
            posicion.avg_entry_price
        )

        if cantidad <= 0:

            return None

        if precio_entrada <= 0:

            return None

        if atr_actual is None:

            return None

        atr_actual = float(
            atr_actual
        )

        if atr_actual <= 0:

            return None

        # =================================================
        # PRECIOS DE PROTECCIÓN
        # =================================================

        stop_distance = (
            atr_actual
            * config.ATR_STOP_MULTIPLICADOR
        )

        take_distance = (
            atr_actual
            * config.ATR_TAKE_PROFIT_MULTIPLICADOR
        )

        stop_price = (
            precio_entrada
            - stop_distance
        )

        take_price = (
            precio_entrada
            + take_distance
        )

        # Protección mínima adicional
        stop_pct_price = (
            precio_entrada
            * config.STOP_LOSS_PCT
        )

        take_pct_price = (
            precio_entrada
            * config.TAKE_PROFIT_PCT
        )

        # El stop no puede quedar por encima
        # de la entrada.
        stop_price = min(
            stop_price,
            precio_entrada - stop_pct_price,
        )

        # El TP queda como mínimo al porcentaje
        # configurado.
        take_price = max(
            take_price,
            precio_entrada + take_pct_price,
        )

        if stop_price <= 0:

            log.error(
                f"{ticker}: precio de Stop Loss "
                f"inválido: {stop_price}"
            )

            return None

        # =================================================
        # REDONDEO
        # =================================================

        stop_price = round(
            stop_price,
            2,
        )

        take_price = round(
            take_price,
            2,
        )

        # =================================================
        # CREAR OCO
        # =================================================

        orden = MarketOrderRequest(
            symbol=ticker,
            qty=round(
                cantidad,
                6,
            ),
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.OCO,
            stop_loss=StopLossRequest(
                stop_price=stop_price
            ),
            take_profit=TakeProfitRequest(
                limit_price=take_price
            ),
        )

        cliente_trading.submit_order(
            order_data=orden
        )

        mensaje = (
            f"🛡️ PROTECCIÓN {ticker}: "
            f"SL ${stop_price:.2f} | "
            f"TP ${take_price:.2f} "
            f"(entrada ${precio_entrada:.2f})"
        )

        log.info(
            mensaje
        )

        return mensaje

    except Exception as e:

        log.error(
            f"{ticker}: error creando protección: {e}"
        )

        return None


# =========================================================
# TAMAÑO DE POSICIÓN
# =========================================================

def calcular_tamano_posicion(
    ticker: str,
    precio: float,
    atr: float,
):
    """
    Calcula el tamaño de la posición.

    Acciones:
        Basado en riesgo por operación.

    Cripto:
        Basado en riesgo, pero limitado para evitar
        órdenes gigantes y respetar el máximo notional.
    """

    try:

        if precio <= 0:

            return 0

        if atr is None or atr <= 0:

            return 0

        cuenta = cliente_trading.get_account()

        equity = float(
            cuenta.equity
        )

        buying_power = float(
            cuenta.buying_power
        )

        if equity <= 0:

            return 0

        # =================================================
        # RIESGO EN DÓLARES
        # =================================================

        riesgo_dolares = (
            equity
            * config.RISK_PER_TRADE_PCT
        )

        distancia_stop = (
            atr
            * config.ATR_STOP_MULTIPLICADOR
        )

        if distancia_stop <= 0:

            return 0

        cantidad = (
            riesgo_dolares
            / distancia_stop
        )

        # =================================================
        # CRIPTO
        # =================================================

        if es_cripto(ticker):

            # No permitir que una sola posición
            # consuma una parte absurda de la cuenta.
            max_por_posicion = (
                equity
                * 0.20
            )

            # Límite de Alpaca por orden.
            max_notional_alpaca = 200000.0

            # No utilizar todo el buying power.
            max_buying_power = (
                buying_power
                * 0.90
            )

            max_notional = min(
                max_por_posicion,
                max_notional_alpaca,
                max_buying_power,
            )

            if max_notional <= 0:

                return 0

            cantidad_maxima = (
                max_notional
                / precio
            )

            cantidad = min(
                cantidad,
                cantidad_maxima,
            )

            # Cripto permite fracciones.
            cantidad = round(
                cantidad,
                6,
            )

            if cantidad <= 0:

                return 0

            return cantidad

        # =================================================
        # ACCIONES
        # =================================================

        # No gastar más buying power del disponible.
        cantidad_maxima = (
            buying_power
            * 0.90
            / precio
        )

        cantidad = min(
            cantidad,
            cantidad_maxima,
        )

        # Acciones enteras.
        cantidad = int(
            cantidad
        )

        if cantidad <= 0:

            return 0

        return cantidad

    except Exception as e:

        log.error(
            f"{ticker}: error calculando "
            f"tamaño de posición: {e}"
        )

        return 0


# =========================================================
# COMPRAR
# =========================================================

def comprar(
    ticker: str,
    precio: float,
    atr: float,
):
    """
    Ejecuta una compra a mercado.
    """

    try:

        if tiene_posicion_abierta(
            ticker
        ):

            log.info(
                f"{ticker}: ya existe posición, "
                f"no se compra."
            )

            return None

        cantidad = calcular_tamano_posicion(
            ticker,
            precio,
            atr,
        )

        if cantidad <= 0:

            log.warning(
                f"{ticker}: tamaño de posición "
                f"demasiado pequeño, "
                f"se omite compra."
            )

            return None

        # =================================================
        # ACCIONES
        # =================================================

        if not es_cripto(ticker):

            orden = MarketOrderRequest(
                symbol=ticker,
                qty=cantidad,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )

        # =================================================
        # CRIPTO
        # =================================================

        else:

            orden = MarketOrderRequest(
                symbol=ticker,
                qty=cantidad,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
            )

        resultado = cliente_trading.submit_order(
            order_data=orden
        )

        order_id = getattr(
            resultado,
            "id",
            None,
        )

        mensaje = (
            f"🟢 COMPRA {ticker}: "
            f"{cantidad} unidades "
            f"≈ ${precio:.2f}"
        )

        if order_id:

            mensaje += (
                f" | orden {order_id}"
            )

        log.info(
            mensaje
        )

        return mensaje

    except Exception as e:

        log.error(
            f"{ticker}: error ejecutando compra: {e}"
        )

        return None


# =========================================================
# VENDER
# =========================================================

def vender(ticker: str):
    """
    Cierra la posición completa a mercado.

    Para acciones, si existen órdenes de protección,
    Alpaca gestionará las órdenes vinculadas.
    """

    try:

        posicion = obtener_posicion(
            ticker
        )

        if posicion is None:

            log.info(
                f"{ticker}: no existe posición "
                f"para vender."
            )

            return None

        cantidad = float(
            posicion.qty
        )

        if cantidad <= 0:

            return None

        # =================================================
        # CANCELAR PROTECCIONES EXISTENTES
        # =================================================

        if not es_cripto(ticker):

            try:

                ordenes = obtener_ordenes_abiertas()

                for orden in ordenes:

                    simbolo = str(
                        getattr(
                            orden,
                            "symbol",
                            "",
                        )
                    ).upper()

                    if simbolo != ticker.upper():

                        continue

                    lado = getattr(
                        orden,
                        "side",
                        None,
                    )

                    if lado != OrderSide.SELL:

                        continue

                    order_id = getattr(
                        orden,
                        "id",
                        None,
                    )

                    if order_id:

                        try:

                            cliente_trading.cancel_order_by_id(
                                order_id
                            )

                        except Exception as e:

                            log.warning(
                                f"{ticker}: no se pudo "
                                f"cancelar protección "
                                f"{order_id}: {e}"
                            )

            except Exception as e:

                log.warning(
                    f"{ticker}: error cancelando "
                    f"protecciones: {e}"
                )

        # =================================================
        # VENTA
        # =================================================

        if es_cripto(ticker):

            cantidad_orden = round(
                cantidad,
                6,
            )

            tif = TimeInForce.GTC

        else:

            cantidad_orden = int(
                cantidad
            )

            tif = TimeInForce.DAY

        if cantidad_orden <= 0:

            return None

        orden = MarketOrderRequest(
            symbol=ticker,
            qty=cantidad_orden,
            side=OrderSide.SELL,
            time_in_force=tif,
        )

        resultado = cliente_trading.submit_order(
            order_data=orden
        )

        order_id = getattr(
            resultado,
            "id",
            None,
        )

        precio_entrada = float(
            posicion.avg_entry_price
        )

        mensaje = (
            f"🔴 VENTA {ticker}: "
            f"{cantidad_orden} unidades "
            f"(entrada ${precio_entrada:.2f})"
        )

        if order_id:

            mensaje += (
                f" | orden {order_id}"
            )

        log.info(
            mensaje
        )

        return mensaje

    except Exception as e:

        log.error(
            f"{ticker}: error ejecutando venta: {e}"
        )

        return None


# =========================================================
# INFORMACIÓN DE POSICIÓN
# =========================================================

def perdida_pct_no_realizada(
    ticker: str
):
    """
    Devuelve la pérdida/ganancia porcentual
    no realizada de una posición.
    """

    try:

        posicion = obtener_posicion(
            ticker
        )

        if posicion is None:

            return None

        precio_entrada = float(
            posicion.avg_entry_price
        )

        precio_actual = float(
            posicion.current_price
        )

        if precio_entrada <= 0:

            return None

        return (
            precio_actual
            - precio_entrada
        ) / precio_entrada

    except Exception as e:

        log.error(
            f"{ticker}: error calculando "
            f"pérdida no realizada: {e}"
        )

        return None


def precio_actual_posicion(
    ticker: str
):
    """
    Devuelve:
        (precio_entrada, precio_actual)
    """

    try:

        posicion = obtener_posicion(
            ticker
        )

        if posicion is None:

            return None

        precio_entrada = float(
            posicion.avg_entry_price
        )

        precio_actual = float(
            posicion.current_price
        )

        return (
            precio_entrada,
            precio_actual,
        )

    except Exception as e:

        log.error(
            f"{ticker}: error obteniendo "
            f"precio de posición: {e}"
        )

        return None


# =========================================================
# MONITOR DE EJECUCIONES
# =========================================================

_ordenes_notificadas = set()

_monitor_ejecuciones_inicializado = False


def obtener_ordenes_ejecutadas():
    """
    Obtiene órdenes cerradas desde Alpaca.

    Usa GetOrdersRequest porque la versión instalada
    de alpaca-py no acepta limit= directamente
    en TradingClient.get_orders().
    """

    try:

        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
        )

        ordenes = cliente_trading.get_orders(
            filter=request
        )

        return ordenes

    except Exception as e:

        log.error(
            f"[ejecuciones] Error obteniendo "
            f"ejecuciones: {e}"
        )

        return []


def inicializar_monitor_ejecuciones():
    """
    Marca como conocidas las órdenes que ya existían
    antes de iniciar el bot.

    Así no recibimos Telegram de operaciones antiguas.
    """

    global _monitor_ejecuciones_inicializado

    try:

        ordenes = obtener_ordenes_ejecutadas()

        for orden in ordenes:

            order_id = getattr(
                orden,
                "id",
                None,
            )

            if order_id:

                _ordenes_notificadas.add(
                    str(order_id)
                )

        _monitor_ejecuciones_inicializado = True

        log.info(
            "[ejecuciones] Monitor inicializado. "
            f"{len(_ordenes_notificadas)} "
            "ordenes antiguas ignoradas."
        )

    except Exception as e:

        log.error(
            f"[ejecuciones] Error inicializando "
            f"monitor: {e}"
        )

        _monitor_ejecuciones_inicializado = True


def detectar_ejecuciones():
    """
    Busca órdenes nuevas que hayan sido ejecutadas.

    Devuelve mensajes para Telegram.
    """

    mensajes = []

    try:

        ordenes = obtener_ordenes_ejecutadas()

        for orden in ordenes:

            order_id = getattr(
                orden,
                "id",
                None,
            )

            if not order_id:

                continue

            order_id = str(
                order_id
            )

            if order_id in _ordenes_notificadas:

                continue

            status = str(
                getattr(
                    orden,
                    "status",
                    "",
                )
            ).lower()

            # Solo queremos órdenes realmente llenadas.
            if "filled" not in status:

                _ordenes_notificadas.add(
                    order_id
                )

                continue

            _ordenes_notificadas.add(
                order_id
            )

            ticker = str(
                getattr(
                    orden,
                    "symbol",
                    "",
                )
            )

            side = str(
                getattr(
                    orden,
                    "side",
                    "",
                )
            ).lower()

            qty = getattr(
                orden,
                "filled_qty",
                None,
            )

            if qty is None:

                qty = getattr(
                    orden,
                    "qty",
                    None,
                )

            precio = getattr(
                orden,
                "filled_avg_price",
                None,
            )

            if precio is None:

                precio = getattr(
                    orden,
                    "limit_price",
                    None,
                )

            # =================================================
            # MENSAJE
            # =================================================

            if "buy" in side:

                emoji = "🟢"

                accion = "COMPRA"

            elif "sell" in side:

                emoji = "🔴"

                accion = "VENTA"

            else:

                emoji = "ℹ️"

                accion = "ORDEN"

            if precio is not None:

                try:

                    precio_texto = (
                        f"${float(precio):.2f}"
                    )

                except Exception:

                    precio_texto = str(
                        precio
                    )

            else:

                precio_texto = "precio no disponible"

            mensaje = (
                f"{emoji} {accion} EJECUTADA — "
                f"{ticker} | "
                f"cantidad: {qty} | "
                f"precio: {precio_texto}"
            )

            mensajes.append(
                mensaje
            )

            log.info(
                f"[ejecuciones] {mensaje}"
            )

    except Exception as e:

        log.error(
            f"[ejecuciones] Error detectando "
            f"ejecuciones: {e}"
        )

    return mensajes
