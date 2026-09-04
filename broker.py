"""
broker.py

Todo lo que toca la API de Alpaca:

- Obtener datos de mercado
- Descubrir criptomonedas negociables
- Escanear criptomonedas en lote
- Consultar posiciones
- Consultar cuenta
- Ejecutar compras/ventas
- Gestionar protección de acciones
- Controlar tamaño de posición
- Detectar ejecuciones
- Consultar segunda cuenta

IMPORTANTE:
La cuenta secundaria es SOLO LECTURA.
Nunca se envían órdenes a la cuenta secundaria.
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

from alpaca.data.timeframe import (
    TimeFrame,
    TimeFrameUnit,
)

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
# SEGUNDA CUENTA — SOLO LECTURA
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


if SECOND_API_KEY and SECOND_API_SECRET:

    try:

        cliente_trading_secundaria = TradingClient(
            SECOND_API_KEY,
            SECOND_API_SECRET,
            paper=config.PAPER,
        )

        log.info(
            "[segunda cuenta] Cliente Alpaca "
            "secundario inicializado."
        )

    except Exception as e:

        log.error(
            "[segunda cuenta] No se pudo "
            f"inicializar el cliente: {e}"
        )

else:

    log.warning(
        "[segunda cuenta] Credenciales "
        "secundarias no configuradas."
    )


# ============================================================
# CACHE DEL UNIVERSO CRYPTO
# ============================================================

_universo_crypto_cache = []

_universo_crypto_actualizado = None


# ============================================================
# CRIPTOMONEDAS ESTABLES
# ============================================================

_ESTABLES = {
    "USDT",
    "USDC",
    "DAI",
    "USDG",
    "PYUSD",
    "USDS",
    "FDUSD",
    "TUSD",
    "USDP",
    "GUSD",
    "EURC",
}


# ============================================================
# IDENTIFICAR CRYPTO
# ============================================================

def es_cripto(ticker: str) -> bool:

    ticker = str(
        ticker
    ).upper().strip()

    if not ticker:
        return False

    if "/" in ticker:
        return True

    if ticker.endswith("USD"):

        base = ticker[:-3]

        if base:
            return True

    return False


# ============================================================
# NORMALIZAR CRYPTO
# ============================================================

def normalizar_ticker_crypto(
    ticker: str,
) -> str:

    ticker = str(
        ticker
    ).upper().strip()

    if "/" in ticker:

        partes = ticker.split("/")

        if (
            len(partes) == 2
            and partes[1] == "USD"
            and partes[0]
        ):

            return f"{partes[0]}/USD"

        return ticker

    if ticker.endswith("USD"):

        base = ticker[:-3]

        if base:

            return f"{base}/USD"

    return ticker


# ============================================================
# TICKER PARA COMPARACIONES
# ============================================================

def ticker_comparacion(
    ticker: str,
) -> str:

    ticker = str(
        ticker
    ).upper().strip()

    if es_cripto(ticker):

        return (
            normalizar_ticker_crypto(
                ticker
            )
            .replace("/", "")
            .replace("-", "")
            .replace(" ", "")
        )

    return ticker


# ============================================================
# DESCUBRIR UNIVERSO CRYPTO
# ============================================================

def obtener_universo_crypto():

    global _universo_crypto_cache
    global _universo_crypto_actualizado

    try:

        ahora = datetime.now(
            timezone.utc
        )

        if (
            _universo_crypto_cache
            and _universo_crypto_actualizado
        ):

            minutos = (
                ahora
                - _universo_crypto_actualizado
            ).total_seconds() / 60

            refresh = getattr(
                config,
                "CRYPTO_UNIVERSE_REFRESH_MINUTES",
                30,
            )

            if minutos < refresh:

                return list(
                    _universo_crypto_cache
                )

        activos = (
            cliente_trading.get_all_assets()
        )

        universo = []

        for activo in activos:

            try:

                simbolo = str(
                    getattr(
                        activo,
                        "symbol",
                        "",
                    )
                ).upper().strip()

                if not simbolo:
                    continue

                simbolo_normalizado = (
                    normalizar_ticker_crypto(
                        simbolo
                    )
                )

                if not simbolo_normalizado.endswith(
                    "/USD"
                ):
                    continue

                tradable = getattr(
                    activo,
                    "tradable",
                    False,
                )

                if not bool(tradable):
                    continue

                status = str(
                    getattr(
                        activo,
                        "status",
                        "",
                    )
                ).lower()

                if (
                    status
                    and "active" not in status
                ):
                    continue

                clase = getattr(
                    activo,
                    "asset_class",
                    None,
                )

                if clase is None:

                    clase = getattr(
                        activo,
                        "class",
                        "",
                    )

                clase_texto = str(
                    clase
                ).lower()

                if (
                    clase_texto
                    and "crypto"
                    not in clase_texto
                ):
                    continue

                base = (
                    simbolo_normalizado
                    .split("/")[0]
                )

                excluir_estables = getattr(
                    config,
                    "CRYPTO_EXCLUIR_ESTABLES",
                    True,
                )

                if (
                    excluir_estables
                    and base in _ESTABLES
                ):
                    continue

                universo.append(
                    simbolo_normalizado
                )

            except Exception as e:

                log.debug(
                    "[crypto] Error procesando "
                    f"activo: {e}"
                )

        manuales = getattr(
            config,
            "CRYPTO_TICKERS",
            [],
        )

        for ticker in manuales:

            normalizado = (
                normalizar_ticker_crypto(
                    ticker
                )
            )

            if not normalizado.endswith(
                "/USD"
            ):
                continue

            if normalizado not in universo:

                universo.append(
                    normalizado
                )

        universo = sorted(
            set(universo)
        )

        _universo_crypto_cache = (
            universo
        )

        _universo_crypto_actualizado = (
            ahora
        )

        log.info(
            "[crypto] Universo actualizado: "
            f"{len(universo)} activos "
            "crypto USD negociables."
        )

        return list(
            universo
        )

    except Exception as e:

        log.error(
            "[crypto] Error obteniendo "
            f"universo crypto: {e}"
        )

        if _universo_crypto_cache:

            return list(
                _universo_crypto_cache
            )

        manuales = getattr(
            config,
            "CRYPTO_TICKERS",
            [],
        )

        return [
            normalizar_ticker_crypto(
                ticker
            )
            for ticker in manuales
        ]


# ============================================================
# DATOS CRYPTO EN LOTE
# ============================================================

def obtener_datos_crypto_lote(
    tickers,
    dias=3,
):

    resultado = {}

    if not tickers:
        return resultado

    try:

        ahora = datetime.now(
            timezone.utc
        )

        inicio = (
            ahora
            - timedelta(
                days=dias
            )
        )

        batch_size = getattr(
            config,
            "CRYPTO_SCAN_BATCH_SIZE",
            50,
        )

        try:
            batch_size = int(
                batch_size
            )
        except Exception:
            batch_size = 50

        if batch_size <= 0:
            batch_size = 50

        tickers_normalizados = []

        for ticker in tickers:

            normalizado = (
                normalizar_ticker_crypto(
                    ticker
                )
            )

            if (
                normalizado
                not in tickers_normalizados
            ):

                tickers_normalizados.append(
                    normalizado
                )

        for posicion_inicio in range(
            0,
            len(tickers_normalizados),
            batch_size,
        ):

            lote = tickers_normalizados[
                posicion_inicio:
                posicion_inicio + batch_size
            ]

            try:

                request = CryptoBarsRequest(
                    symbol_or_symbols=lote,
                    timeframe=TimeFrame(
                        5,
                        TimeFrameUnit.Minute,
                    ),
                    start=inicio,
                    end=ahora,
                )

                datos = (
                    cliente_datos_crypto.get_crypto_bars(
                        request
                    )
                )

                df = datos.df.copy()

                if df is None or df.empty:

                    log.warning(
                        "[crypto] Lote sin datos: "
                        f"{len(lote)} símbolos."
                    )

                    continue

                if isinstance(
                    df.index,
                    pd.MultiIndex,
                ):

                    nombres = list(
                        df.index.names
                    )

                    if "symbol" in nombres:

                        for (
                            simbolo,
                            grupo,
                        ) in df.groupby(
                            level="symbol"
                        ):

                            try:

                                grupo = (
                                    grupo
                                    .droplevel(
                                        "symbol"
                                    )
                                    .copy()
                                )

                                ticker_normalizado = (
                                    normalizar_ticker_crypto(
                                        simbolo
                                    )
                                )

                                resultado[
                                    ticker_normalizado
                                ] = (
                                    _limpiar_dataframe_crypto(
                                        grupo
                                    )
                                )

                            except Exception as e:

                                log.debug(
                                    "[crypto] Error "
                                    f"separando {simbolo}: "
                                    f"{e}"
                                )

                    else:

                        for clave, grupo in (
                            df.groupby(
                                level=0
                            )
                        ):

                            try:

                                grupo = (
                                    grupo
                                    .droplevel(
                                        0
                                    )
                                    .copy()
                                )

                                ticker_normalizado = (
                                    normalizar_ticker_crypto(
                                        clave
                                    )
                                )

                                resultado[
                                    ticker_normalizado
                                ] = (
                                    _limpiar_dataframe_crypto(
                                        grupo
                                    )
                                )

                            except Exception:
                                continue

                else:

                    if (
                        "symbol"
                        in df.columns
                    ):

                        for (
                            simbolo,
                            grupo,
                        ) in df.groupby(
                            "symbol"
                        ):

                            ticker_normalizado = (
                                normalizar_ticker_crypto(
                                    simbolo
                                )
                            )

                            grupo = (
                                grupo
                                .drop(
                                    columns=[
                                        "symbol"
                                    ],
                                    errors="ignore",
                                )
                            )

                            resultado[
                                ticker_normalizado
                            ] = (
                                _limpiar_dataframe_crypto(
                                    grupo
                                )
                            )

            except Exception as e:

                log.error(
                    "[crypto] Error obteniendo "
                    f"lote: {e}"
                )

        log.info(
            "[crypto] Datos recibidos: "
            f"{len(resultado)} / "
            f"{len(tickers_normalizados)}"
        )

        return resultado

    except Exception as e:

        log.error(
            "[crypto] Error general "
            f"obteniendo datos en lote: {e}"
        )

        return resultado


# ============================================================
# LIMPIAR DATAFRAME CRYPTO
# ============================================================

def _limpiar_dataframe_crypto(
    df,
):

    try:

        df = df.copy()

        columnas = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        for columna in columnas:

            if columna not in df.columns:
                return pd.DataFrame()

            df[columna] = pd.to_numeric(
                df[columna],
                errors="coerce",
            )

        df = df.dropna(
            subset=columnas
        )

        if df.empty:
            return df

        df = df.sort_index()

        df = df[
            ~df.index.duplicated(
                keep="last"
            )
        ]

        return df

    except Exception as e:

        log.debug(
            f"[crypto] Error limpiando "
            f"datos: {e}"
        )

        return pd.DataFrame()


# ============================================================
# MERCADO ACCIONES
# ============================================================

def mercado_abierto() -> bool:

    try:

        reloj = (
            cliente_trading.get_clock()
        )

        return bool(
            reloj.is_open
        )

    except Exception as e:

        log.error(
            "[mercado] Error comprobando "
            f"mercado: {e}"
        )

        return False


# ============================================================
# DATOS DE UN TICKER
# ============================================================

def obtener_datos(
    ticker: str,
) -> pd.DataFrame:

    try:

        ahora = datetime.now(
            timezone.utc
        )

        if es_cripto(ticker):

            ticker_crypto = (
                normalizar_ticker_crypto(
                    ticker
                )
            )

            inicio = (
                ahora
                - timedelta(
                    days=7
                )
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
                cliente_datos_crypto.get_crypto_bars(
                    request
                )
            )

        else:

            inicio = (
                ahora
                - timedelta(
                    days=30
                )
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
                cliente_datos_acciones.get_stock_bars(
                    request
                )
            )

        df = datos.df.copy()

        if df is None or df.empty:

            log.warning(
                f"{ticker}: no se recibieron "
                "datos."
            )

            return pd.DataFrame()

        if isinstance(
            df.index,
            pd.MultiIndex,
        ):

            if "symbol" in df.index.names:

                simbolos = (
                    df.index
                    .get_level_values(
                        "symbol"
                    )
                    .unique()
                    .tolist()
                )

                if len(simbolos) > 0:

                    df = (
                        df.xs(
                            simbolos[0],
                            level="symbol",
                        )
                        .copy()
                    )

            else:

                df = (
                    df.reset_index(
                        drop=True
                    )
                )

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
            f"{ticker}: error obteniendo "
            f"datos: {e}"
        )

        return pd.DataFrame()


# ============================================================
# OBTENER POSICIÓN
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

        try:

            simbolo_directo = (
                normalizar_ticker_crypto(
                    ticker
                )
                if es_cripto(ticker)
                else ticker
            )

            posicion = (
                cliente_trading.get_open_position(
                    simbolo_directo
                )
            )

            if posicion is not None:
                return posicion

        except Exception:
            pass

        posiciones = (
            cliente_trading.get_all_positions()
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
            f"{ticker}: error obteniendo "
            f"posición: {e}"
        )

        return None


# ============================================================
# TODAS LAS POSICIONES
# ============================================================

def obtener_todas_las_posiciones():

    try:

        return (
            cliente_trading.get_all_positions()
        )

    except Exception as e:

        log.error(
            "[posiciones] Error obteniendo "
            f"posiciones: {e}"
        )

        return []


# ============================================================
# POSICIÓN ABIERTA
# ============================================================

def tiene_posicion_abierta(
    ticker: str,
) -> bool:

    posicion = (
        obtener_posicion(
            ticker
        )
    )

    return posicion is not None


# ============================================================
# CONTAR POSICIONES
# ============================================================

def contar_posiciones_abiertas() -> int:

    try:

        posiciones = (
            cliente_trading.get_all_positions()
        )

        return len(
            posiciones
        )

    except Exception as e:

        log.error(
            "[posiciones] Error contando "
            f"posiciones: {e}"
        )

        return 0


# ============================================================
# RESUMEN CUENTA PRINCIPAL
# ============================================================

def obtener_resumen_cuenta():

    try:

        cuenta = (
            cliente_trading.get_account()
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
            cliente_trading.get_all_positions()
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
            "numero_posiciones": len(
                posiciones
            ),
        }

    except Exception as e:

        log.error(
            "[cuenta] Error obteniendo "
            f"resumen: {e}"
        )

        return None


# ============================================================
# POSICIONES TELEGRAM PRINCIPAL
# ============================================================

def obtener_posiciones_telegram():

    try:

        posiciones = (
            cliente_trading.get_all_positions()
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
            "[cuenta] Error obteniendo "
            f"posiciones para Telegram: {e}"
        )

        return []


# ============================================================
# RESUMEN SEGUNDA CUENTA
# ============================================================

def obtener_resumen_cuenta_secundaria():

    if (
        cliente_trading_secundaria
        is None
    ):

        log.error(
            "[segunda cuenta] Credenciales "
            "de Alpaca no configuradas."
        )

        return None

    try:

        cuenta = (
            cliente_trading_secundaria.get_account()
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
            "[segunda cuenta] Consulta "
            "realizada correctamente. "
            f"Posiciones={len(posiciones)}"
        )

        return {
            "equity": equity,
            "cash": cash,
            "buying_power": buying_power,
            "beneficio_dia": beneficio_dia,
            "beneficio_posiciones": beneficio_posiciones,
            "numero_posiciones": len(
                posiciones
            ),
        }

    except Exception as e:

        log.error(
            "[segunda cuenta] Error "
            f"obteniendo resumen: {e}"
        )

        return None


# ============================================================
# POSICIONES SEGUNDA CUENTA
# ============================================================

def obtener_posiciones_secundaria():

    if (
        cliente_trading_secundaria
        is None
    ):

        log.error(
            "[segunda cuenta] Credenciales "
            "de Alpaca no configuradas."
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
            "[segunda cuenta] Posiciones "
            f"obtenidas: {len(resultado)}"
        )

        return resultado

    except Exception as e:

        log.error(
            "[segunda cuenta] Error "
            f"obteniendo posiciones: {e}"
        )

        return []


# ============================================================
# ÓRDENES ABIERTAS
# ============================================================

def obtener_ordenes_abiertas():

    try:

        # IMPORTANTE:
        # nested=True hace que Alpaca devuelva las
        # órdenes OCO/bracket con sus legs.
        #
        # Esto permite detectar correctamente:
        # - Take Profit
        # - Stop Loss

        request = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            nested=True,
            limit=500,
        )

        return (
            cliente_trading.get_orders(
                filter=request
            )
        )

    except Exception as e:

        log.error(
            "[ordenes] Error obteniendo "
            f"órdenes abiertas: {e}"
        )

        return []


# ============================================================
# ÓRDENES DE UN TICKER
# ============================================================

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
            f"{ticker}: error obteniendo "
            f"órdenes: {e}"
        )

        return []


# ============================================================
# ANALIZAR ORDEN DE PROTECCIÓN
# ============================================================

def _analizar_orden_proteccion(
    orden,
):

    tiene_sl = False
    tiene_tp = False

    try:

        side = str(
            getattr(
                orden,
                "side",
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

        tipo = str(
            getattr(
                orden,
                "type",
                "",
            )
        ).lower()

        # ----------------------------------------------------
        # SOLO SALIDAS
        # ----------------------------------------------------

        if "sell" not in side:

            return False, False

        # ----------------------------------------------------
        # OCO / BRACKET
        # ----------------------------------------------------

        if (
            "oco" in order_class
            or "bracket" in order_class
        ):

            # Con nested=True, Alpaca devuelve
            # las patas en order.legs.
            #
            # No debemos asumir simplemente que
            # toda OCO tiene ambas patas activas:
            # las inspeccionamos realmente.

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

                    leg_order_class = str(
                        getattr(
                            leg,
                            "order_class",
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

                    # STOP / STOP LIMIT
                    if (
                        leg_stop_price is not None
                        or "stop" in leg_type
                    ):

                        tiene_sl = True

                    # LIMIT
                    if (
                        leg_limit_price is not None
                        and "stop" not in leg_type
                    ):

                        tiene_tp = True

                    # Algunos objetos pueden conservar
                    # la clase OCO en la pata.
                    if (
                        "oco" in leg_order_class
                        and leg_limit_price is not None
                    ):

                        tiene_tp = True

                return (
                    tiene_sl,
                    tiene_tp,
                )

            # ------------------------------------------------
            # FALLBACK
            # ------------------------------------------------

            # Si Alpaca no devuelve legs, inspeccionamos
            # los campos disponibles del objeto principal.

            stop_price = getattr(
                orden,
                "stop_price",
                None,
            )

            limit_price = getattr(
                orden,
                "limit_price",
                None,
            )

            if stop_price is not None:
                tiene_sl = True

            if (
                limit_price is not None
                and "stop" not in tipo
            ):
                tiene_tp = True

            return (
                tiene_sl,
                tiene_tp,
            )

        # ----------------------------------------------------
        # ORDEN SIMPLE STOP
        # ----------------------------------------------------

        stop_price = getattr(
            orden,
            "stop_price",
            None,
        )

        limit_price = getattr(
            orden,
            "limit_price",
            None,
        )

        if (
            stop_price is not None
            or "stop" in tipo
        ):

            tiene_sl = True

        # Una orden limit SELL simple puede ser TP.
        if (
            limit_price is not None
            and "stop" not in tipo
        ):

            tiene_tp = True

        # ----------------------------------------------------
        # LEGS COMO FALLBACK
        # ----------------------------------------------------

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
                    and "stop" not in leg_type
                ):

                    tiene_tp = True

        return (
            tiene_sl,
            tiene_tp,
        )

    except Exception as e:

        log.error(
            "[protección] Error analizando "
            f"orden: {e}"
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
            f"{'✅' if resultado['tiene_proteccion'] else '❌'} "
            f"ÓRDENES="
            f"{len(resultado['ordenes_proteccion'])}"
        )

        return resultado

    except Exception as e:

        log.error(
            f"{ticker}: error analizando "
            f"protección: {e}"
        )

        return resultado


# ============================================================
# TIENE PROTECCIÓN
# ============================================================

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

            if (
                tiene_sl
                or tiene_tp
            ):

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

                error = str(
                    e
                ).lower()

                if (
                    "not found"
                    in error
                    or "already canceled"
                    in error
                    or "already cancelled"
                    in error
                    or "cancelled"
                    in error
                    or "canceled"
                    in error
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
# PROTEGER ACCIÓN
# ============================================================

def proteger_posicion(
    ticker: str,
    atr_actual: float,
):

    try:

        if es_cripto(ticker):

            return None

        posicion = (
            obtener_posicion(
                ticker
            )
        )

        if posicion is None:

            log.info(
                f"{ticker}: posición "
                "todavía no disponible."
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

        # ----------------------------------------------------
        # COMPROBAR PROTECCIÓN EXISTENTE
        # ----------------------------------------------------

        analisis = (
            analizar_proteccion(
                ticker
            )
        )

        if analisis[
            "tiene_proteccion"
        ]:

            log.info(
                f"{ticker}: protección "
                "SL + TP completa ya existente."
            )

            return None

        # ----------------------------------------------------
        # PROTECCIÓN PARCIAL
        # ----------------------------------------------------

        if (
            analisis["tiene_sl"]
            or analisis["tiene_tp"]
        ):

            log.warning(
                f"{ticker}: protección "
                "incompleta. Reconstruyendo "
                "SL + TP."
            )

            if not cancelar_protecciones(
                ticker
            ):

                log.error(
                    f"{ticker}: no se pudieron "
                    "cancelar las protecciones "
                    "anteriores."
                )

                return None

        # ----------------------------------------------------
        # DATOS POSICIÓN
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # STOP LOSS
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # TAKE PROFIT
        # ----------------------------------------------------

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

        if (
            take_price
            <= precio_entrada
        ):

            log.warning(
                f"{ticker}: take profit "
                "inválido."
            )

            return None

        # ----------------------------------------------------
        # REDONDEO DE PRECIOS
        # ----------------------------------------------------

        stop_price = round(
            stop_price,
            2,
        )

        take_price = round(
            take_price,
            2,
        )

        if (
            stop_price <= 0
            or take_price <= precio_entrada
        ):

            log.warning(
                f"{ticker}: precios de "
                "protección inválidos después "
                "del redondeo."
            )

            return None

        # ----------------------------------------------------
        # OCO
        # ----------------------------------------------------

        orden = LimitOrderRequest(
            symbol=ticker,
            qty=cantidad,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.OCO,
            stop_loss=StopLossRequest(
                stop_price=stop_price,
            ),
            take_profit=TakeProfitRequest(
                limit_price=take_price,
            ),
        )

        resultado = (
            cliente_trading.submit_order(
                order_data=orden
            )
        )

        log.info(
            f"{ticker}: OCO creada correctamente. "
            f"Orden={resultado.id} | "
            f"SL=${stop_price:.2f} | "
            f"TP=${take_price:.2f} | "
            f"Entrada=${precio_entrada:.2f}"
        )

        return (
            "🛡️ PROTECCIÓN ACTIVADA\n"
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
            cliente_trading.get_account()
        )

        equity = float(
            cuenta.equity
        )

        buying_power = float(
            cuenta.buying_power
        )

        if es_cripto(ticker):

            riesgo_pct = getattr(
                config,
                "CRYPTO_RISK_PER_TRADE_PCT",
                0.01,
            )

        else:

            riesgo_pct = (
                config.RISK_PER_TRADE_PCT
            )

        riesgo_dolares = (
            equity
            * riesgo_pct
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

        # ----------------------------------------------------
        # CRYPTO
        # ----------------------------------------------------

        if es_cripto(ticker):

            max_notional_pct = getattr(
                config,
                "CRYPTO_MAX_NOTIONAL_PCT",
                0.10,
            )

            max_notional = min(
                equity
                * max_notional_pct,
                200000,
                buying_power
                * 0.90,
            )

            cantidad_maxima = (
                max_notional
                / precio
            )

            cantidad = min(
                cantidad,
                cantidad_maxima,
            )

            cantidad = round(
                cantidad,
                6,
            )

            return cantidad

        # ----------------------------------------------------
        # ACCIONES
        # ----------------------------------------------------

        max_notional = (
            buying_power
            * 0.90
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
                "posición inválido."
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
            "🟡 ORDEN ENVIADA\n"
            f"{'₿' if es_cripto(ticker) else '📈'} "
            f"{ticker} | "
            f"{'5M' if es_cripto(ticker) else '15M'}\n"
            f"Cantidad: {cantidad}\n"
            f"Precio estimado: "
            f"${precio:.6f}"
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

        posicion = (
            obtener_posicion(
                ticker
            )
        )

        if posicion is None:

            log.warning(
                f"{ticker}: no se encontró "
                "posición para vender."
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
                    "cancelar todas las "
                    "protecciones."
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
            "🟡 ORDEN DE VENTA ENVIADA\n"
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
# PÉRDIDA / GANANCIA
# ============================================================

def perdida_pct_no_realizada(
    ticker: str,
) -> float:

    try:

        posicion = (
            obtener_posicion(
                ticker
            )
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
            precio_actual
            - precio_entrada
        ) / precio_entrada

    except Exception as e:

        log.error(
            f"{ticker}: error calculando "
            f"pérdida: {e}"
        )

        return 0.0


# ============================================================
# PRECIO POSICIÓN
# ============================================================

def precio_actual_posicion(
    ticker: str,
):

    try:

        posicion = (
            obtener_posicion(
                ticker
            )
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


# ============================================================
# ÓRDENES EJECUTADAS
# ============================================================

def obtener_ordenes_ejecutadas():

    try:

        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=500,
            nested=True,
        )

        ordenes = (
            cliente_trading.get_orders(
                filter=request
            )
        )

        log.info(
            "[ejecuciones] Órdenes cerradas "
            f"consultadas: {len(ordenes)}"
        )

        return ordenes

    except Exception as e:

        log.error(
            "[ejecuciones] Error obteniendo "
            f"órdenes: {e}"
        )

        return []


# ============================================================
# FECHA EJECUCIÓN
# ============================================================

def _obtener_fecha_ejecucion(
    orden,
):

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


# ============================================================
# INICIALIZAR MONITOR
# ============================================================

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
            "[ejecuciones] Monitor "
            f" inicializado. {antiguas} "
            "órdenes antiguas ignoradas."
        )

        log.info(
            "[ejecuciones] Vigilando "
            "ejecuciones posteriores a "
            f"{_inicio_monitor_ejecuciones.isoformat()}"
        )

    except Exception as e:

        log.error(
            "[ejecuciones] Error "
            f"inicializando monitor: {e}"
        )


# ============================================================
# DETECTAR EJECUCIONES
# ============================================================

def detectar_ejecuciones():

    global _ordenes_notificadas
    global _inicio_monitor_ejecuciones

    nuevas = []

    try:

        if (
            _inicio_monitor_ejecuciones
            is None
        ):

            log.warning(
                "[ejecuciones] Monitor "
                "todavía no inicializado."
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

            # Solo nos interesan ejecuciones reales.
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

            # ------------------------------------------------
            # MARCAR COMO PROCESADA
            # ------------------------------------------------

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
                "buy"
                in side
            )

            es_accion = not es_cripto(
                ticker
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
                "[ejecuciones] NUEVA "
                "EJECUCIÓN DETECTADA: "
                f"{ticker} | "
                f"{accion} | "
                f"ID={order_id} | "
                f"Hora="
                f"{fecha_ejecucion.isoformat()}"
            )

            if precio is not None:

                try:

                    precio_formateado = (
                        f"${float(precio):.6f}"
                        if es_cripto(ticker)
                        else f"${float(precio):.2f}"
                    )

                except Exception:

                    precio_formateado = (
                        str(precio)
                    )

                mensaje = (
                    f"{emoji} "
                    f"{accion} EJECUTADA\n"
                    f"{tipo}\n"
                    f"{ticker}\n"
                    f"Cantidad: {qty}\n"
                    f"Precio: "
                    f"{precio_formateado}"
                )

            else:

                mensaje = (
                    f"{emoji} "
                    f"{accion} EJECUTADA\n"
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
            "[ejecuciones] Error "
            f"detectando ejecuciones: {e}"
        )

    return nuevas
