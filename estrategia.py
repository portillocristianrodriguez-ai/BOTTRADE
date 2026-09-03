"""
estrategia.py

Motor de señales del bot.

Gestiona:
- Indicadores técnicos
- Acciones
- Cripto
- Señales de COMPRA / VENTA / ESPERAR

La estrategia mantiene los parámetros de riesgo
definidos en config.py.
"""

import pandas as pd
import ta

import config


# ============================================================
# INDICADORES
# ============================================================

def calcular_indicadores(df):

    df = df.copy()

    # --------------------------------------------------------
    # EMA TENDENCIA
    # --------------------------------------------------------

    df["ema_tendencia"] = ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_TENDENCIA,
    )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    df["atr"] = ta.volatility.average_true_range(
        df["high"],
        df["low"],
        df["close"],
        window=config.ATR_PERIODO,
    )

    # --------------------------------------------------------
    # EMA RÁPIDA
    # --------------------------------------------------------

    df["ema_rapida"] = ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_RAPIDA,
    )

    # --------------------------------------------------------
    # EMA LENTA
    # --------------------------------------------------------

    df["ema_lenta"] = ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_LENTA,
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    df["rsi"] = ta.momentum.rsi(
        df["close"],
        window=config.RSI_PERIODO,
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    macd = ta.trend.MACD(
        df["close"],
        window_fast=12,
        window_slow=26,
        window_sign=9,
    )

    df["macd"] = macd.macd()

    df["macd_signal"] = (
        macd.macd_signal()
    )

    # --------------------------------------------------------
    # VOLUMEN
    # --------------------------------------------------------

    df["volumen_media"] = (
        df["volume"]
        .rolling(
            config.VOLUMEN_SMA_PERIODO
        )
        .mean()
    )

    df["volumen_ratio"] = (
        df["volume"]
        / df["volumen_media"]
    )

    return df


# ============================================================
# VALIDAR DATOS
# ============================================================

def _datos_validos(
    actual,
    columnas,
):

    for columna in columnas:

        valor = actual.get(
            columna
        )

        if pd.isna(valor):

            return False

    return True


# ============================================================
# SEÑAL ACCIONES
# ============================================================

def _generar_senal_acciones(
    df,
):

    minimo_velas = (
        config.EMA_TENDENCIA + 2
    )

    if len(df) < minimo_velas:

        return "ESPERAR"

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

    columnas = [
        "ema_tendencia",
        "ema_rapida",
        "ema_lenta",
        "rsi",
        "macd",
        "macd_signal",
        "atr",
        "volumen_ratio",
    ]

    if not _datos_validos(
        actual,
        columnas,
    ):

        return "ESPERAR"

    if not _datos_validos(
        anterior,
        [
            "ema_tendencia",
            "ema_rapida",
            "ema_lenta",
            "rsi",
            "macd",
            "macd_signal",
        ],
    ):

        return "ESPERAR"

    # ========================================================
    # TENDENCIA
    # ========================================================

    tendencia_alcista = (
        actual["close"]
        > actual["ema_tendencia"]
    )

    tendencia_bajista = (
        actual["close"]
        < actual["ema_tendencia"]
    )

    # ========================================================
    # EMA
    # ========================================================

    emas_alcistas = (
        actual["ema_rapida"]
        > actual["ema_lenta"]
    )

    emas_bajistas = (
        actual["ema_rapida"]
        < actual["ema_lenta"]
    )

    # ========================================================
    # CRUCES
    # ========================================================

    cruce_ema_alcista = (
        anterior["ema_rapida"]
        <= anterior["ema_lenta"]
        and
        actual["ema_rapida"]
        > actual["ema_lenta"]
    )

    cruce_ema_bajista = (
        anterior["ema_rapida"]
        >= anterior["ema_lenta"]
        and
        actual["ema_rapida"]
        < actual["ema_lenta"]
    )

    # ========================================================
    # MACD
    # ========================================================

    macd_alcista = (
        actual["macd"]
        > actual["macd_signal"]
    )

    macd_bajista = (
        actual["macd"]
        < actual["macd_signal"]
    )

    # ========================================================
    # RSI
    # ========================================================

    rsi = float(
        actual["rsi"]
    )

    rsi_alcista = (
        config.RSI_SOBREVENTA
        <= rsi
        <= config.RSI_SOBRECOMPRA
    )

    # ========================================================
    # VOLUMEN
    # ========================================================

    volumen_ok = (
        actual["volumen_ratio"]
        >= config.VOLUMEN_MIN_MULTIPLICADOR
    )

    # ========================================================
    # ATR
    # ========================================================

    atr_pct = (
        actual["atr"]
        / actual["close"]
    )

    volatilidad_ok = (
        atr_pct
        >= config.ATR_MIN_PCT
    )

    # ========================================================
    # COMPRA
    # ========================================================

    compra_fuerte = (
        tendencia_alcista
        and emas_alcistas
        and macd_alcista
        and rsi_alcista
        and volumen_ok
        and volatilidad_ok
    )

    compra_cruce = (
        cruce_ema_alcista
        and tendencia_alcista
        and macd_alcista
        and rsi <= 70
        and volumen_ok
        and volatilidad_ok
    )

    if (
        compra_fuerte
        or compra_cruce
    ):

        return "COMPRAR"

    # ========================================================
    # VENTA
    # ========================================================

    margen = (
        config.MARGEN_SALIDA_PCT
    )

    umbral_salida = (
        actual["ema_tendencia"]
        * (1 - margen)
    )

    venta_tendencia = (
        actual["close"]
        < umbral_salida
        and macd_bajista
    )

    venta_ema = (
        cruce_ema_bajista
        and macd_bajista
    )

    venta_fuerte = (
        tendencia_bajista
        and emas_bajistas
        and macd_bajista
        and rsi < 45
    )

    if (
        venta_tendencia
        or venta_ema
        or venta_fuerte
    ):

        return "VENDER"

    return "ESPERAR"


# ============================================================
# SEÑAL CRIPTO
# ============================================================

def _generar_senal_cripto(
    df,
):

    minimo_velas = 50

    if len(df) < minimo_velas:

        return "ESPERAR"

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

    columnas = [
        "ema_tendencia",
        "ema_rapida",
        "ema_lenta",
        "rsi",
        "macd",
        "macd_signal",
        "atr",
        "volumen_ratio",
    ]

    if not _datos_validos(
        actual,
        columnas,
    ):

        return "ESPERAR"

    # ========================================================
    # TENDENCIA
    # ========================================================

    tendencia_alcista = (
        actual["close"]
        > actual["ema_tendencia"]
    )

    tendencia_bajista = (
        actual["close"]
        < actual["ema_tendencia"]
    )

    # ========================================================
    # EMA
    # ========================================================

    emas_alcistas = (
        actual["ema_rapida"]
        > actual["ema_lenta"]
    )

    emas_bajistas = (
        actual["ema_rapida"]
        < actual["ema_lenta"]
    )

    # ========================================================
    # MACD
    # ========================================================

    macd_alcista = (
        actual["macd"]
        > actual["macd_signal"]
    )

    macd_bajista = (
        actual["macd"]
        < actual["macd_signal"]
    )

    # ========================================================
    # RSI
    # ========================================================

    rsi = float(
        actual["rsi"]
    )

    entrada_rsi = (
        45
        <= rsi
        <= 68
    )

    # ========================================================
    # VOLUMEN
    # ========================================================

    volumen_ok = (
        actual["volumen_ratio"]
        >= config.VOLUMEN_MIN_MULTIPLICADOR
    )

    # ========================================================
    # ATR
    # ========================================================

    atr_pct = (
        actual["atr"]
        / actual["close"]
    )

    volatilidad_ok = (
        atr_pct
        >= config.ATR_MIN_PCT
    )

    # ========================================================
    # MOMENTUM
    # ========================================================

    precio_sobre_ema = (
        actual["close"]
        > actual["ema_rapida"]
    )

    # ========================================================
    # COMPRA
    # ========================================================

    entrada_principal = (
        tendencia_alcista
        and emas_alcistas
        and macd_alcista
        and entrada_rsi
        and precio_sobre_ema
        and volumen_ok
        and volatilidad_ok
    )

    # Entrada por cruce reciente
    cruce_ema_alcista = (
        anterior["ema_rapida"]
        <= anterior["ema_lenta"]
        and
        actual["ema_rapida"]
        > actual["ema_lenta"]
    )

    entrada_cruce = (
        cruce_ema_alcista
        and tendencia_alcista
        and macd_alcista
        and rsi <= 70
        and volumen_ok
        and volatilidad_ok
    )

    if (
        entrada_principal
        or entrada_cruce
    ):

        return "COMPRAR"

    # ========================================================
    # VENTA
    # ========================================================

    cruce_ema_bajista = (
        anterior["ema_rapida"]
        >= anterior["ema_lenta"]
        and
        actual["ema_rapida"]
        < actual["ema_lenta"]
    )

    salida_tendencia = (
        tendencia_bajista
        and macd_bajista
        and rsi < 45
    )

    salida_momentum = (
        cruce_ema_bajista
        and macd_bajista
    )

    if (
        salida_tendencia
        or salida_momentum
    ):

        return "VENDER"

    return "ESPERAR"


# ============================================================
# GENERAR SEÑAL
# ============================================================

def generar_senal(
    df,
    ticker,
):

    """
    Genera una señal utilizando el ticker real.

    Las criptomonedas contienen "/":
        BTC/USD
        ETH/USD
        SOL/USD

    El resto se considera acción.
    """

    try:

        if "/" in str(ticker):

            return _generar_senal_cripto(
                df
            )

        return _generar_senal_acciones(
            df
        )

    except Exception as e:

        log_message = (
            f"{ticker}: error generando "
            f"señal: {e}"
        )

        print(
            log_message
        )

        return "ESPERAR"
