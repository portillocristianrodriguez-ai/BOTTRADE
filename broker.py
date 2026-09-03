
"""
Todo lo que toca la API de Alpaca:

- Obtener datos de mercado
- Consultar posiciones
- Ejecutar compras/ventas
- Gestionar protección SL/TP
- Controlar tamaño de posición
- Detectar ejecuciones
"""

import logging
from datetime import datetime, timedelta, timezone

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

from alpaca.data.historical import (
    StockHistoricalDataClient,
    CryptoHistoricalDataClient,
)
from alpaca.data.requests import (
    StockBarsRequest,
    CryptoBarsRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

import config


log = logging.getLogger(__name__)


# ============================================================
# CLIENTES ALPACA
# ============================================================

cliente_trading = TradingClient(
    config.API_KEY,
    config.API_SECRET,
    paper=config.PAPER,
)

cliente_datos_acciones = StockHistoricalDataClient(
    config.API_KEY,
    config.API_SECRET,
)

cliente_datos_crypto = CryptoHistoricalDataClient(
    config.API_KEY,
    config.API_SECRET,
)


# ============================================================
# UTILIDADES
# ============================================================

def es_cripto(ticker: str) -> bool:
    """
    Detecta si un ticker es criptomoneda.

    Alpaca puede devolver símbolos cripto como:

        BTC/USD
        BTCUSD

    Aceptamos ambos formatos.
    """

    ticker = str(ticker).upper().strip()

    if "/" in ticker:
        return True

    criptos = (
        "BTCUSD",
        "ETHUSD",
        "SOLUSD",
        "AVAXUSD",
        "LINKUSD",
        "DOGEUSD",
        "LTCUSD",
        "BCHUSD",
        "UNIUSD",
        "AAVEUSD",
    )

    return ticker in criptos


def normalizar_ticker_crypto(
    ticker: str,
) -> str:
    """
    Convierte símbolos cripto al formato
    utilizado por los datos de Alpaca.

    Ejemplos:

        BTCUSD  -> BTC/USD
        ETHUSD  -> ETH/USD
        SOLUSD  -> SOL/USD

    Si ya contiene '/', no se modifica.
    """

    ticker = str(ticker).upper().strip()

    if "/" in ticker:
        return ticker

    if ticker.endswith("USD"):

        base = ticker[:-3]

        if base:
            return f"{base}/USD"

    return ticker


# ============================================================
# MERCADO
# ============================================================

def mercado_abierto() -> bool:
    """
    Comprueba si el mercado de acciones está abierto.
    """

    try:

        reloj = cliente_trading.get_clock()

        return bool(
            reloj.is_open
        )

    except Exception as e:

        log.error(
            f"[mercado] Error comprobando mercado: {e}"
        )

        return False


# ============================================================
# DATOS DE MERCADO
# ============================================================

def obtener_datos(
    ticker: str,
) -> pd.DataFrame:

    try:

        ahora = datetime.now(
            timezone.utc
        )

        # ====================================================
        # CRIPTO
        # ====================================================

        if es_cripto(ticker):

            ticker_crypto = (
                normalizar_ticker_crypto(
                    ticker
                )
            )

            inicio = (
                ahora
                - timedelta(days=7)
            )

            request = CryptoBarsRequest(
                symbol_or_symbols=ticker_crypto,
                timeframe=TimeFrame(
                    5,
                    TimeFrameUnit.Minute,
                ),
                start=inicio,
                end=ahora,
            )

            datos = (
                cliente_datos_crypto
                .get_crypto_bars(
                    request
                )
            )

        # ====================================================
        # ACCIONES
        # ====================================================

        else:

            inicio = (
                ahora
                - timedelta(days=30)
            )

            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame(
                    15,
                    TimeFrameUnit.Minute,
                ),
                start=inicio,
                end=ahora,
                feed=DataFeed.IEX,
            )

            datos = (
                cliente_datos_acciones
                .get_stock_bars(
                    request
                )
            )

        # ====================================================
        # DATAFRAME
        # ====================================================

        df = datos.df.copy()

        if df is None or df.empty:

            log.warning(
                f"{ticker}: no se recibieron datos."
            )

            return pd.DataFrame()

        # ====================================================
        # MULTIINDEX
        # ====================================================

        if isinstance(
            df.index,
            pd.MultiIndex,
        ):

            if "symbol" in df.index.names:

                df = df.reset_index(
                    level="symbol",
                    drop=True,
                )

            else:

                df = df.reset_index(
                    drop=True
                )

        # ====================================================
        # COLUMNAS NECESARIAS
        # ====================================================

        columnas = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        for columna in columnas:

            if columna not in df.columns:

                log.warning(
                    f"{ticker}: falta columna "
                    f"'{columna}'."
                )

                return pd.DataFrame()

        # ====================================================
        # LIMPIEZA
        # ====================================================

        for columna in columnas:

            df[columna] = pd.to_numeric(
                df[columna],
                errors="coerce",
            )

        df = df.dropna(
            subset=columnas
        )

        df = df.sort_index()

        df = df[
            ~df.index.duplicated(
                keep="last"
            )
        ]

        log.debug(
            f"{ticker}: "
            f"{len(df)} velas obtenidas."
        )

        return df

    except Exception as e:

        log.error(
            f"{ticker}: error obteniendo datos: {e}"
        )

        return pd.DataFrame()


# ============================================================
# POSICIONES
# ============================================================

def obtener_posicion(
    ticker: str,
):

    try:

        return cliente_trading.get_open_position(
            ticker
        )

    except Exception:

        return None


def obtener_todas_las_posiciones():

    try:

        return cliente_trading.get_all_positions()

    except Exception as e:

        log.error(
            f"[posiciones] Error obteniendo "
            f"posiciones: {e}"
        )

        return []


def tiene_posicion_abierta(
    ticker: str,
) -> bool:

    return (
        obtener_posicion(ticker)
        is not None
    )


def contar_posiciones_abiertas() -> int:

    try:

        posiciones = (
            cliente_trading.get_all_positions()
        )

        return len(posiciones)

    except Exception as e:

        log.error(
            f"[posiciones] Error contando "
            f"posiciones: {e}"
        )

        return 0


# ============================================================
# ÓRDENES ABIERTAS
# ============================================================

def obtener_ordenes_abiertas():

    try:

        request = GetOrdersRequest(
            status=QueryOrderStatus.OPEN
        )

        return cliente_trading.get_orders(
            filter=request
        )

    except Exception as e:

        log.error(
            f"[ordenes] Error obteniendo "
            f"órdenes abiertas: {e}"
        )

        return []


def obtener_ordenes_ticker(
    ticker: str,
):

    try:

        ordenes = obtener_ordenes_abiertas()

        ticker_busqueda = str(
            ticker
        ).upper().strip()

        ticker_normalizado = (
            normalizar_ticker_crypto(
                ticker_busqueda
            )
            if es_cripto(ticker_busqueda)
            else ticker_busqueda
        )

        resultado = []

        for orden in ordenes:

            simbolo_orden = str(
                getattr(
                    orden,
                    "symbol",
                    "",
                )
            ).upper().strip()

            simbolo_orden_normalizado = (
                normalizar_ticker_crypto(
                    simbolo_orden
                )
                if es_cripto(
                    simbolo_orden
                )
                else simbolo_orden
            )

            if (
                simbolo_orden_normalizado
                == ticker_normalizado
            ):

                resultado.append(
                    orden
                )

        return resultado

    except Exception as e:

        log.error(
            f"{ticker}: error obteniendo órdenes: {e}"
        )

        return []


# ============================================================
# ANALIZAR ORDEN DE PROTECCIÓN
# ============================================================

def _analizar_orden_proteccion(
    orden,
):

    """
    Devuelve:

        (tiene_sl, tiene_tp)

    Una OCO válida contiene SL + TP.
    """

    try:

        side = str(
            getattr(
                orden,
                "side",
                "",
            )
        ).lower()

        if "sell" not in side:

            return False, False

        tipo = str(
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

        # ====================================================
        # OCO
        # ====================================================

        if "oco" in order_class:

            return True, True

        # ====================================================
        # BRACKET
        # ====================================================

        if "bracket" in order_class:

            return True, True

        # ====================================================
        # CAMPOS
        # ====================================================

        stop_price = getattr(
            orden,
            "stop_price",
            None
        )

        stop_loss = getattr(
            orden,
            "stop_loss",
            None
        )

        take_profit = getattr(
            orden,
            "take_profit",
            None
        )

        tiene_sl = (
            stop_price is not None
            or stop_loss is not None
            or "stop" in tipo
        )

        tiene_tp = (
            take_profit is not None
        )

        # ====================================================
        # LEGS
        # ====================================================

        legs = getattr(
            orden,
            "legs",
            None
        )

        if legs:

            for leg in legs:

                leg_side = str(
                    getattr(
                        leg,
                        "side",
                        "",
                    )
                ).lower()

                if "sell" not in leg_side:

                    continue

                leg_type = str(
                    getattr(
                        leg,
                        "type",
                        "",
                    )
                ).lower()

                leg_stop_price = getattr(
                    leg,
                    "stop_price",
                    None
                )

                leg_limit_price = getattr(
                    leg,
                    "limit_price",
                    None
                )

                if (
                    leg_stop_price is not None
                    or "stop" in leg_type
                ):

                    tiene_sl = True

                if (
                    leg_limit_price is not None
                    or "limit" in leg_type
                ):

                    tiene_tp = True

        return tiene_sl, tiene_tp

    except Exception as e:

        log.error(
            f"[protección] Error analizando orden: {e}"
        )

        return False, False


# ============================================================
# ANALIZAR PROTECCIÓN
# ============================================================

def analizar_proteccion(
    ticker: str,
) -> dict:

    resultado = {
        "tiene_sl": False,
        "tiene_tp": False,
        "tiene_proteccion": False,
        "ordenes_proteccion": [],
    }

    try:

        ordenes = obtener_ordenes_ticker(
            ticker
        )

        for orden in ordenes:

            tiene_sl, tiene_tp = (
                _analizar_orden_proteccion(
                    orden
                )
            )

            if not (
                tiene_sl
                or tiene_tp
            ):

                continue

            resultado[
                "ordenes_proteccion"
            ].append(
                orden
            )

            if tiene_sl:

                resultado[
                    "tiene_sl"
                ] = True

            if tiene_tp:

                resultado[
                    "tiene_tp"
                ] = True

            log.debug(
                f"{ticker}: "
                f"orden={getattr(orden, 'id', '?')} "
                f"type={getattr(orden, 'type', '?')} "
                f"class={getattr(orden, 'order_class', '?')} "
                f"SL={tiene_sl} "
                f"TP={tiene_tp}"
            )

        resultado[
            "tiene_proteccion"
        ] = (
            resultado["tiene_sl"]
            and resultado["tiene_tp"]
        )

        log.info(
            f"{ticker}: análisis protección → "
            f"SL="
            f"{'✅' if resultado['tiene_sl'] else '❌'} "
            f"TP="
            f"{'✅' if resultado['tiene_tp'] else '❌'} "
            f"COMPLETA="
            f"{'✅' if resultado['tiene_proteccion'] else '❌'}"
        )

        return resultado

    except Exception as e:

        log.error(
            f"{ticker}: error analizando protección: {e}"
        )

        return resultado


def tiene_proteccion(
    ticker: str,
) -> bool:

    resultado = analizar_proteccion(
        ticker
    )

    return bool(
        resultado[
            "tiene_proteccion"
        ]
    )


# ============================================================
# CANCELAR PROTECCIONES
# ============================================================

def cancelar_protecciones(
    ticker: str,
) -> bool:

    try:

        ordenes = obtener_ordenes_ticker(
            ticker
        )

        protecciones = []

        for orden in ordenes:

            tiene_sl, tiene_tp = (
                _analizar_orden_proteccion(
                    orden
                )
            )

            if tiene_sl or tiene_tp:

                protecciones.append(
                    orden
                )

        if not protecciones:

            return True

        for orden in protecciones:

            try:

                cliente_trading.cancel_order_by_id(
                    orden.id
                )

                log.info(
                    f"{ticker}: protección "
                    f"{orden.id} cancelada."
                )

            except Exception as e:

                error = str(e).lower()

                if (
                    "not found" in error
                    or "already canceled" in error
                    or "already cancelled" in error
                    or "cancelled" in error
                    or "canceled" in error
                ):

                    continue

                log.warning(
                    f"{ticker}: no se pudo "
                    f"cancelar protección "
                    f"{orden.id}: {e}"
                )

                return False

        return True

    except Exception as e:

        log.error(
            f"{ticker}: error cancelando "
            f"protecciones: {e}"
        )

        return False


# ============================================================
# PROTEGER POSICIÓN
# ============================================================

def proteger_posicion(
    ticker: str,
    atr_actual: float,
):

    try:

        # Las criptos utilizan protección manual.
        if es_cripto(ticker):

            return None

        posicion = obtener_posicion(
            ticker
        )

        if posicion is None:

            log.info(
                f"{ticker}: posición todavía "
                f"no disponible."
            )

            return None

        if (
            atr_actual is None
            or atr_actual <= 0
        ):

            log.warning(
                f"{ticker}: ATR inválido."
            )

            return None

        # ====================================================
        # COMPROBAR PROTECCIÓN
        # ====================================================

        analisis = analizar_proteccion(
            ticker
        )

        if analisis[
            "tiene_proteccion"
        ]:

            log.info(
                f"{ticker}: protección completa "
                f"ya existente."
            )

            return None

        # ====================================================
        # SI ESTÁ INCOMPLETA, RECONSTRUIR
        # ====================================================

        if (
            analisis["tiene_sl"]
            or analisis["tiene_tp"]
        ):

            log.warning(
                f"{ticker}: protección incompleta. "
                f"Reconstruyendo."
            )

            if not cancelar_protecciones(
                ticker
            ):

                log.error(
                    f"{ticker}: no se pudieron "
                    f"cancelar las protecciones."
                )

                return None

        # ====================================================
        # POSICIÓN
        # ====================================================

        cantidad = float(
            posicion.qty
        )

        precio_entrada = float(
            posicion.avg_entry_price
        )

        if (
            cantidad <= 0
            or precio_entrada <= 0
        ):

            log.warning(
                f"{ticker}: posición inválida."
            )

            return None

        # ====================================================
        # STOP LOSS
        # ====================================================

        distancia_stop = max(
            atr_actual
            * config.ATR_STOP_MULTIPLICADOR,

            precio_entrada
            * config.STOP_LOSS_PCT,
        )

        stop_price = (
            precio_entrada
            - distancia_stop
        )

        # ====================================================
        # TAKE PROFIT
        # ====================================================

        distancia_take = max(
            atr_actual
            * config.ATR_TAKE_PROFIT_MULTIPLICADOR,

            precio_entrada
            * config.TAKE_PROFIT_PCT,
        )

        take_price = (
            precio_entrada
            + distancia_take
        )

        if stop_price <= 0:

            log.warning(
                f"{ticker}: stop inválido."
            )

            return None

        if take_price <= precio_entrada:

            log.warning(
                f"{ticker}: take profit inválido."
            )

            return None

        # ====================================================
        # OCO
        # ====================================================

        orden = LimitOrderRequest(
            symbol=ticker,
            qty=cantidad,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.OCO,

            stop_loss=StopLossRequest(
                stop_price=round(
                    stop_price,
                    2,
                )
            ),

            take_profit=TakeProfitRequest(
                limit_price=round(
                    take_price,
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
            f"{ticker}: OCO creada. "
            f"Orden={resultado.id} | "
            f"SL=${stop_price:.2f} | "
            f"TP=${take_price:.2f}"
        )

        return (
            f"🛡️ PROTECCIÓN ACTIVADA\n"
            f"📈 {ticker} | 15M\n"
            f"SL: ${stop_price:.2f}\n"
            f"TP: ${take_price:.2f}\n"
            f"Entrada: ${precio_entrada:.2f}"
        )

    except Exception as e:

        log.error(
            f"{ticker}: error colocando "
            f"protección: {e}"
        )

        return None


# ============================================================
# TAMAÑO DE POSICIÓN
# ============================================================

def calcular_tamano_posicion(
    ticker: str,
    precio: float,
    atr: float,
):

    try:

        if (
            precio <= 0
            or atr is None
            or atr <= 0
        ):

            return 0

        cuenta = (
            cliente_trading
            .get_account()
        )

        equity = float(
            cuenta.equity
        )

        buying_power = float(
            cuenta.buying_power
        )

        # Riesgo = 2% por operación
        riesgo_dolares = (
            equity
            * config.RISK_PER_TRADE_PCT
        )

        distancia_stop = max(
            atr
            * config.ATR_STOP_MULTIPLICADOR,

            precio
            * config.STOP_LOSS_PCT,
        )

        if distancia_stop <= 0:

            return 0

        cantidad = (
            riesgo_dolares
            / distancia_stop
        )

        # ====================================================
        # CRIPTO
        # ====================================================

        if es_cripto(ticker):

            max_notional = min(
                equity * 0.20,
                200000,
                buying_power * 0.90,
            )

            cantidad_maxima = (
                max_notional
                / precio
            )

            cantidad = min(
                cantidad,
                cantidad_maxima,
            )

            return round(
                cantidad,
                6,
            )

        # ====================================================
        # ACCIONES
        # ====================================================

        max_notional = (
            buying_power * 0.90
        )

        cantidad_maxima = (
            max_notional
            / precio
        )

        cantidad = min(
            cantidad,
            cantidad_maxima,
        )

        return int(
            cantidad
        )

    except Exception as e:

        log.error(
            f"{ticker}: error calculando "
            f"tamaño: {e}"
        )

        return 0


# ============================================================
# COMPRAR
# ============================================================

def comprar(
    ticker: str,
    precio: float,
    atr: float,
):

    try:

        cantidad = (
            calcular_tamano_posicion(
                ticker,
                precio,
                atr,
            )
        )

        if cantidad <= 0:

            log.warning(
                f"{ticker}: tamaño de "
                f"posición inválido."
            )

            return None

        # Para enviar la orden usamos el ticker
        # configurado por el bot.
        simbolo_orden = (
            normalizar_ticker_crypto(
                ticker
            )
            if es_cripto(ticker)
            else ticker
        )

        tif = (
            TimeInForce.GTC
            if es_cripto(ticker)
            else TimeInForce.DAY
        )

        orden = MarketOrderRequest(
            symbol=simbolo_orden,
            qty=cantidad,
            side=OrderSide.BUY,
            time_in_force=tif,
        )

        resultado = (
            cliente_trading.submit_order(
                order_data=orden
            )
        )

        mensaje = (
            f"🟡 ORDEN ENVIADA\n"
            f"{'₿' if es_cripto(ticker) else '📈'} "
            f"{ticker} | "
            f"{'5M' if es_cripto(ticker) else '15M'}\n"
            f"Cantidad: {cantidad}\n"
            f"Precio estimado: ${precio:.2f}"
        )

        log.info(
            f"{ticker}: orden enviada "
            f"{resultado.id}"
        )

        return mensaje

    except Exception as e:

        log.error(
            f"{ticker}: error comprando: {e}"
        )

        return None


# ============================================================
# VENDER
# ============================================================

def vender(
    ticker: str,
):

    try:

        posicion = obtener_posicion(
            ticker
        )

        if posicion is None:

            return None

        cantidad = float(
            posicion.qty
        )

        # Antes de vender una acción,
        # cancelar sus protecciones.
        if not es_cripto(ticker):

            if not cancelar_protecciones(
                ticker
            ):

                log.warning(
                    f"{ticker}: no se pudieron "
                    f"cancelar todas las protecciones."
                )

                return None

        simbolo_orden = (
            normalizar_ticker_crypto(
                ticker
            )
            if es_cripto(ticker)
            else ticker
        )

        tif = (
            TimeInForce.GTC
            if es_cripto(ticker)
            else TimeInForce.DAY
        )

        orden = MarketOrderRequest(
            symbol=simbolo_orden,
            qty=cantidad,
            side=OrderSide.SELL,
            time_in_force=tif,
        )

        resultado = (
            cliente_trading.submit_order(
                order_data=orden
            )
        )

        mensaje = (
            f"🟡 ORDEN DE VENTA ENVIADA\n"
            f"{'₿' if es_cripto(ticker) else '📈'} "
            f"{ticker} | "
            f"{'5M' if es_cripto(ticker) else '15M'}\n"
            f"Cantidad: {cantidad}"
        )

        log.info(
            f"{ticker}: venta enviada "
            f"{resultado.id}"
        )

        return mensaje

    except Exception as e:

        log.error(
            f"{ticker}: error vendiendo: {e}"
        )

        return None


# ============================================================
# PÉRDIDA NO REALIZADA
# ============================================================

def perdida_pct_no_realizada(
    ticker: str,
) -> float:

    try:

        posicion = obtener_posicion(
            ticker
        )

        if posicion is None:

            return 0.0

        precio_entrada = float(
            posicion.avg_entry_price
        )

        precio_actual = float(
            posicion.current_price
        )

        if precio_entrada <= 0:

            return 0.0

        return (
            (
                precio_actual
                - precio_entrada
            )
            / precio_entrada
        )

    except Exception as e:

        log.error(
            f"{ticker}: error calculando "
            f"pérdida: {e}"
        )

        return 0.0


# ============================================================
# PRECIO ACTUAL
# ============================================================

def precio_actual_posicion(
    ticker: str,
):

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
            f"precio: {e}"
        )

        return None


# ============================================================
# MONITOR DE EJECUCIONES
# ============================================================

_ordenes_notificadas = set()


def obtener_ordenes_ejecutadas():

    try:

        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED
        )

        return cliente_trading.get_orders(
            filter=request
        )

    except Exception as e:

        log.error(
            f"[ejecuciones] Error obteniendo "
            f"órdenes: {e}"
        )

        return []


def inicializar_monitor_ejecuciones():

    global _ordenes_notificadas

    try:

        ordenes = (
            obtener_ordenes_ejecutadas()
        )

        for orden in ordenes:

            status = str(
                getattr(
                    orden,
                    "status",
                    "",
                )
            ).lower()

            if "filled" in status:

                _ordenes_notificadas.add(
                    str(
                        orden.id
                    )
                )

        log.info(
            f"[ejecuciones] "
            f"Monitor inicializado. "
            f"{len(_ordenes_notificadas)} "
            f"órdenes antiguas ignoradas."
        )

    except Exception as e:

        log.error(
            f"[ejecuciones] "
            f"Error inicializando monitor: {e}"
        )


def detectar_ejecuciones():

    global _ordenes_notificadas

    nuevas = []

    try:

        ordenes = (
            obtener_ordenes_ejecutadas()
        )

        for orden in ordenes:

            order_id = str(
                orden.id
            )

            if (
                order_id
                in _ordenes_notificadas
            ):

                continue

            status = str(
                getattr(
                    orden,
                    "status",
                    "",
                )
            ).lower()

            if "filled" not in status:

                continue

            _ordenes_notificadas.add(
                order_id
            )

            ticker = getattr(
                orden,
                "symbol",
                "?"
            )

            # Normalizar símbolo de cripto
            # para mensajes y lógica interna.
            ticker = (
                normalizar_ticker_crypto(
                    ticker
                )
                if es_cripto(ticker)
                else ticker
            )

            side = str(
                getattr(
                    orden,
                    "side",
                    ""
                )
            ).lower()

            qty = getattr(
                orden,
                "filled_qty",
                getattr(
                    orden,
                    "qty",
                    "?"
                )
            )

            precio = getattr(
                orden,
                "filled_avg_price",
                None
            )

            es_compra = (
                "buy" in side
            )

            es_accion = (
                not es_cripto(
                    ticker
                )
            )

            if es_compra:

                emoji = "🟢"
                accion = "COMPRA"

            else:

                emoji = "🔴"
                accion = "VENTA"

            tipo = (
                "₿ CRIPTO | 5M"
                if es_cripto(ticker)
                else "📈 ACCIÓN | 15M"
            )

            if precio is not None:

                mensaje = (
                    f"{emoji} {accion} EJECUTADA\n"
                    f"{tipo}\n"
                    f"{ticker}\n"
                    f"Cantidad: {qty}\n"
                    f"Precio: "
                    f"${float(precio):.2f}"
                )

            else:

                mensaje = (
                    f"{emoji} {accion} EJECUTADA\n"
                    f"{tipo}\n"
                    f"{ticker}\n"
                    f"Cantidad: {qty}"
                )

            nuevas.append(
                {
                    "mensaje": mensaje,
                    "ticker": ticker,
                    "compra_accion": (
                        es_compra
                        and es_accion
                    ),
                }
            )

    except Exception as e:

        log.error(
            f"[ejecuciones] "
            f"Error detectando ejecuciones: {e}"
        )

    return nuevas
