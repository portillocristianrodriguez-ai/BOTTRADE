"""
broker.py

Todo lo que toca la API de Alpaca:

- Obtener datos de mercado
- Consultar posiciones
- Consultar cuenta
- Ejecutar compras/ventas
- Gestionar protección SL/TP
- Controlar tamaño de posición
- Detectar ejecuciones
- Consultar segunda cuenta
"""

import logging
import os
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
# CLIENTES ALPACA - CUENTA PRINCIPAL
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
# CLIENTE ALPACA - SEGUNDA CUENTA
# ============================================================

SECOND_API_KEY = os.environ.get(
    "SECOND_ALPACA_API_KEY",
    "",
)

SECOND_API_SECRET = os.environ.get(
    "SECOND_ALPACA_API_SECRET",
    "",
)

cliente_trading_secundaria = None

if (
    SECOND_API_KEY
    and SECOND_API_SECRET
):

    try:

        cliente_trading_secundaria = TradingClient(
            SECOND_API_KEY,
            SECOND_API_SECRET,
            paper=config.PAPER,
        )

        log.info(
            "[segunda cuenta] "
            "Cliente Alpaca secundario inicializado."
        )

    except Exception as e:

        log.error(
            "[segunda cuenta] "
            f"No se pudo inicializar el cliente: {e}"
        )

else:

    log.warning(
        "[segunda cuenta] "
        "Credenciales secundarias no configuradas."
    )


# ============================================================
# UTILIDADES
# ============================================================

def es_cripto(
    ticker: str,
) -> bool:

    ticker = str(
        ticker
    ).upper().strip()

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
        "HYPEUSD",
    )

    return ticker in criptos


def normalizar_ticker_crypto(
    ticker: str,
) -> str:

    """
    Formato utilizado para datos de mercado.

    BTCUSD -> BTC/USD
    BTC/USD -> BTC/USD
    """

    ticker = str(
        ticker
    ).upper().strip()

    if "/" in ticker:
        return ticker

    if ticker.endswith("USD"):

        base = ticker[:-3]

        if base:
            return f"{base}/USD"

    return ticker


def ticker_comparacion(
    ticker: str,
) -> str:

    """
    Normaliza símbolos para comparar posiciones
    y órdenes independientemente de si Alpaca
    devuelve BTC/USD o BTCUSD.
    """

    ticker = str(
        ticker
    ).upper().strip()

    if es_cripto(ticker):

        return (
            ticker
            .replace("/", "")
            .replace("-", "")
            .replace(" ", "")
        )

    return ticker


# ============================================================
# MERCADO
# ============================================================

def mercado_abierto() -> bool:

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
# POSICIONES - CUENTA PRINCIPAL
# ============================================================

def obtener_posicion(
    ticker: str,
):

    try:

        simbolo_buscado = (
            ticker_comparacion(
                ticker
            )
        )

        # ====================================================
        # PRIMERO: endpoint directo
        # ====================================================

        try:

            simbolo_directo = (
                normalizar_ticker_crypto(
                    ticker
                )
                if es_cripto(ticker)
                else ticker
            )

            posicion = (
                cliente_trading
                .get_open_position(
                    simbolo_directo
                )
            )

            if posicion is not None:

                return posicion

        except Exception:

            pass

        # ====================================================
        # SEGUNDO: buscar entre todas las posiciones
        # ====================================================

        posiciones = (
            cliente_trading
            .get_all_positions()
        )

        for posicion in posiciones:

            simbolo_posicion = getattr(
                posicion,
                "symbol",
                "",
            )

            if (
                ticker_comparacion(
                    simbolo_posicion
                )
                == simbolo_buscado
            ):

                return posicion

        return None

    except Exception as e:

        log.error(
            f"{ticker}: error obteniendo posición: {e}"
        )

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

    posicion = obtener_posicion(
        ticker
    )

    return posicion is not None


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
# INFORMACIÓN DE CUENTA PRINCIPAL PARA TELEGRAM
# ============================================================

def obtener_resumen_cuenta():

    """
    Obtiene información general de la cuenta
    para los comandos de Telegram.
    """

    try:

        cuenta = (
            cliente_trading
            .get_account()
        )

        equity = float(
            getattr(
                cuenta,
                "equity",
                0,
            )
            or 0
        )

        cash = float(
            getattr(
                cuenta,
                "cash",
                0,
            )
            or 0
        )

        buying_power = float(
            getattr(
                cuenta,
                "buying_power",
                0,
            )
            or 0
        )

        last_equity = float(
            getattr(
                cuenta,
                "last_equity",
                0,
            )
            or 0
        )

        beneficio_dia = (
            equity
            - last_equity
        )

        posiciones = (
            cliente_trading
            .get_all_positions()
        )

        beneficio_posiciones = 0.0

        for posicion in posiciones:

            beneficio_posiciones += float(
                getattr(
                    posicion,
                    "unrealized_pl",
                    0,
                )
                or 0
            )

        return {
            "equity": equity,
            "cash": cash,
            "buying_power": buying_power,
            "beneficio_dia": beneficio_dia,
            "beneficio_posiciones": beneficio_posiciones,
            "numero_posiciones": len(posiciones),
        }

    except Exception as e:

        log.error(
            f"[cuenta] Error obteniendo "
            f"resumen: {e}"
        )

        return None


def obtener_posiciones_telegram():

    """
    Devuelve información detallada de las posiciones
    abiertas para mostrarla en Telegram.
    """

    try:

        posiciones = (
            cliente_trading
            .get_all_positions()
        )

        resultado = []

        for posicion in posiciones:

            simbolo = str(
                getattr(
                    posicion,
                    "symbol",
                    "?",
                )
            )

            cantidad = getattr(
                posicion,
                "qty",
                "?",
            )

            precio_entrada = float(
                getattr(
                    posicion,
                    "avg_entry_price",
                    0,
                )
                or 0
            )

            precio_actual = float(
                getattr(
                    posicion,
                    "current_price",
                    0,
                )
                or 0
            )

            beneficio = float(
                getattr(
                    posicion,
                    "unrealized_pl",
                    0,
                )
                or 0
            )

            beneficio_pct = float(
                getattr(
                    posicion,
                    "unrealized_plpc",
                    0,
                )
                or 0
            ) * 100

            resultado.append(
                {
                    "simbolo": simbolo,
                    "cantidad": cantidad,
                    "entrada": precio_entrada,
                    "actual": precio_actual,
                    "beneficio": beneficio,
                    "beneficio_pct": beneficio_pct,
                }
            )

        return resultado

    except Exception as e:

        log.error(
            f"[cuenta] Error obteniendo "
            f"posiciones para Telegram: {e}"
        )

        return []


# ============================================================
# SEGUNDA CUENTA - RESUMEN
# ============================================================

def obtener_resumen_cuenta_secundaria():

    """
    Consulta la segunda cuenta de Alpaca.

    IMPORTANTE:
    Este cliente solamente se utiliza para CONSULTA.
    No se usa para comprar, vender ni modificar órdenes.
    """

    if cliente_trading_secundaria is None:

        log.error(
            "[segunda cuenta] "
            "Credenciales de Alpaca no configuradas."
        )

        return None

    try:

        cuenta = (
            cliente_trading_secundaria
            .get_account()
        )

        equity = float(
            getattr(
                cuenta,
                "equity",
                0,
            )
            or 0
        )

        cash = float(
            getattr(
                cuenta,
                "cash",
                0,
            )
            or 0
        )

        buying_power = float(
            getattr(
                cuenta,
                "buying_power",
                0,
            )
            or 0
        )

        last_equity = float(
            getattr(
                cuenta,
                "last_equity",
                0,
            )
            or 0
        )

        beneficio_dia = (
            equity
            - last_equity
        )

        posiciones = (
            cliente_trading_secundaria
            .get_all_positions()
        )

        beneficio_posiciones = 0.0

        for posicion in posiciones:

            beneficio_posiciones += float(
                getattr(
                    posicion,
                    "unrealized_pl",
                    0,
                )
                or 0
            )

        log.info(
            "[segunda cuenta] "
            f"Consulta realizada correctamente. "
            f"Posiciones={len(posiciones)}"
        )

        return {
            "equity": equity,
            "cash": cash,
            "buying_power": buying_power,
            "beneficio_dia": beneficio_dia,
            "beneficio_posiciones": beneficio_posiciones,
            "numero_posiciones": len(posiciones),
        }

    except Exception as e:

        log.error(
            "[segunda cuenta] "
            f"Error obteniendo resumen: {e}"
        )

        return None


# ============================================================
# SEGUNDA CUENTA - POSICIONES
# ============================================================

def obtener_posiciones_secundaria():

    """
    Obtiene las posiciones abiertas de la segunda cuenta.

    Solo lectura.
    """

    if cliente_trading_secundaria is None:

        log.error(
            "[segunda cuenta] "
            "Credenciales de Alpaca no configuradas."
        )

        return []

    try:

        posiciones = (
            cliente_trading_secundaria
            .get_all_positions()
        )

        resultado = []

        for posicion in posiciones:

            simbolo = str(
                getattr(
                    posicion,
                    "symbol",
                    "?",
                )
            )

            cantidad = getattr(
                posicion,
                "qty",
                "?",
            )

            entrada = float(
                getattr(
                    posicion,
                    "avg_entry_price",
                    0,
                )
                or 0
            )

            actual = float(
                getattr(
                    posicion,
                    "current_price",
                    0,
                )
                or 0
            )

            beneficio = float(
                getattr(
                    posicion,
                    "unrealized_pl",
                    0,
                )
                or 0
            )

            beneficio_pct = float(
                getattr(
                    posicion,
                    "unrealized_plpc",
                    0,
                )
                or 0
            ) * 100

            resultado.append(
                {
                    "simbolo": simbolo,
                    "cantidad": cantidad,
                    "entrada": entrada,
                    "actual": actual,
                    "beneficio": beneficio,
                    "beneficio_pct": beneficio_pct,
                }
            )

        log.info(
            "[segunda cuenta] "
            f"Posiciones obtenidas: "
            f"{len(resultado)}"
        )

        return resultado

    except Exception as e:

        log.error(
            "[segunda cuenta] "
            f"Error obteniendo posiciones: {e}"
        )

        return []


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

        ordenes = (
            obtener_ordenes_abiertas()
        )

        ticker_normalizado = (
            ticker_comparacion(
                ticker
            )
        )

        resultado = []

        for orden in ordenes:

            simbolo_orden = getattr(
                orden,
                "symbol",
                "",
            )

            if (
                ticker_comparacion(
                    simbolo_orden
                )
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
            None,
        )

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
            None,
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
                    None,
                )

                leg_limit_price = getattr(
                    leg,
                    "limit_price",
                    None,
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

        ordenes = (
            obtener_ordenes_ticker(
                ticker
            )
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

    resultado = (
        analizar_proteccion(
            ticker
        )
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

        ordenes = (
            obtener_ordenes_ticker(
                ticker
            )
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

        analisis = (
            analizar_proteccion(
                ticker
            )
        )

        if analisis[
            "tiene_proteccion"
        ]:

            log.info(
                f"{ticker}: protección completa "
                f"ya existente."
            )

            return None

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

            log.warning(
                f"{ticker}: no se encontró "
                f"posición para vender."
            )

            return None

        cantidad = float(
            posicion.qty
        )

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

_inicio_monitor_ejecuciones = None


def obtener_ordenes_ejecutadas():

    try:

        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=500,
        )

        ordenes = (
            cliente_trading.get_orders(
                filter=request
            )
        )

        log.info(
            f"[ejecuciones] "
            f"Órdenes cerradas encontradas: "
            f"{len(ordenes)}"
        )

        return ordenes

    except Exception as e:

        log.error(
            f"[ejecuciones] Error obteniendo "
            f"órdenes: {e}"
        )

        return []


def _obtener_fecha_ejecucion(
    orden,
):

    """
    Obtiene la fecha real de ejecución.

    Prioridad:
        filled_at
        submitted_at
        created_at
    """

    for campo in (
        "filled_at",
        "submitted_at",
        "created_at",
    ):

        valor = getattr(
            orden,
            campo,
            None,
        )

        if valor is None:

            continue

        try:

            if isinstance(
                valor,
                datetime,
            ):

                fecha = valor

            else:

                fecha = datetime.fromisoformat(
                    str(valor).replace(
                        "Z",
                        "+00:00",
                    )
                )

            if fecha.tzinfo is None:

                fecha = fecha.replace(
                    tzinfo=timezone.utc
                )

            return fecha.astimezone(
                timezone.utc
            )

        except Exception:

            continue

    return None


def inicializar_monitor_ejecuciones():

    global _ordenes_notificadas
    global _inicio_monitor_ejecuciones

    try:

        _inicio_monitor_ejecuciones = (
            datetime.now(
                timezone.utc
            )
        )

        ordenes = (
            obtener_ordenes_ejecutadas()
        )

        antiguas = 0

        for orden in ordenes:

            order_id = str(
                getattr(
                    orden,
                    "id",
                    "",
                )
            )

            if not order_id:

                continue

            fecha_ejecucion = (
                _obtener_fecha_ejecucion(
                    orden
                )
            )

            if (
                fecha_ejecucion is None
                or fecha_ejecucion
                <= _inicio_monitor_ejecuciones
            ):

                _ordenes_notificadas.add(
                    order_id
                )

                antiguas += 1

        log.info(
            f"[ejecuciones] "
            f"Monitor inicializado. "
            f"{antiguas} órdenes antiguas "
            f"ignoradas."
        )

        log.info(
            f"[ejecuciones] "
            f"Vigilando ejecuciones posteriores a "
            f"{_inicio_monitor_ejecuciones.isoformat()}"
        )

    except Exception as e:

        log.error(
            f"[ejecuciones] "
            f"Error inicializando monitor: {e}"
        )


def detectar_ejecuciones():

    global _ordenes_notificadas
    global _inicio_monitor_ejecuciones

    nuevas = []

    try:

        if _inicio_monitor_ejecuciones is None:

            log.warning(
                "[ejecuciones] "
                "Monitor todavía no inicializado."
            )

            return nuevas

        ordenes = (
            obtener_ordenes_ejecutadas()
        )

        for orden in ordenes:

            order_id = str(
                getattr(
                    orden,
                    "id",
                    "",
                )
            )

            if not order_id:

                continue

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

                _ordenes_notificadas.add(
                    order_id
                )

                continue

            fecha_ejecucion = (
                _obtener_fecha_ejecucion(
                    orden
                )
            )

            if (
                fecha_ejecucion is None
                or fecha_ejecucion
                <= _inicio_monitor_ejecuciones
            ):

                _ordenes_notificadas.add(
                    order_id
                )

                continue

            _ordenes_notificadas.add(
                order_id
            )

            ticker = getattr(
                orden,
                "symbol",
                "?",
            )

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
                    "",
                )
            ).lower()

            qty = getattr(
                orden,
                "filled_qty",
                getattr(
                    orden,
                    "qty",
                    "?",
                ),
            )

            precio = getattr(
                orden,
                "filled_avg_price",
                None,
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

            log.info(
                f"[ejecuciones] "
                f"NUEVA EJECUCIÓN DETECTADA: "
                f"{ticker} | "
                f"{accion} | "
                f"ID={order_id} | "
                f"Hora={fecha_ejecucion.isoformat()}"
            )

            if precio is not None:

                try:

                    precio_formateado = (
                        f"${float(precio):.2f}"
                    )

                except Exception:

                    precio_formateado = (
                        str(precio)
                    )

                mensaje = (
                    f"{emoji} {accion} EJECUTADA\n"
                    f"{tipo}\n"
                    f"{ticker}\n"
                    f"Cantidad: {qty}\n"
                    f"Precio: "
                    f"{precio_formateado}"
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
