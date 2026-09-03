"""
estrategia.py

Motor de señales del bot.

Gestiona:
- Indicadores técnicos
- Acciones
- Cripto
- Señales de COMPRA / VENTA / ESPERAR
- Scanner crypto 24/7
- Detección de impulso inicial
"""

import pandas as pd
import ta

import config


# ============================================================
# INDICADORES
# ============================================================

def calcular_indicadores(df):

    df = df.copy()

    df["ema_tendencia"] = ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_TENDENCIA,
    )

    df["atr"] = ta.volatility.average_true_range(
        df["high"],
        df["low"],
        df["close"],
        window=config.ATR_PERIODO,
    )

    df["ema_rapida"] = ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_RAPIDA,
    )

    df["ema_lenta"] = ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_LENTA,
    )

    df["rsi"] = ta.momentum.rsi(
        df["close"],
        window=config.RSI_PERIODO,
    )

    macd = ta.trend.MACD(
        df["close"],
        window_fast=12,
        window_slow=26,
        window_sign=9,
    )

    df["macd"] = macd.macd()

    df["macd_signal"] = macd.macd_signal()

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

    # ========================================================
    # DATOS PARA SCANNER
    # ========================================================

    df["cambio_1"] = (
        df["close"]
        .pct_change(1)
    )

    df["cambio_3"] = (
        df["close"]
        .pct_change(3)
    )

    df["cambio_6"] = (
        df["close"]
        .pct_change(6)
    )

    df["maximo_6"] = (
        df["high"]
        .rolling(6)
        .max()
        .shift(1)
    )

    df["maximo_12"] = (
        df["high"]
        .rolling(12)
        .max()
        .shift(1)
    )

    df["pendiente_ema_rapida"] = (
        df["ema_rapida"]
        .pct_change(3)
    )

    df["separacion_emas"] = (
        (
            df["ema_rapida"]
            - df["ema_lenta"]
        )
        / df["close"]
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

def _generar_senal_acciones(df):

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

    tendencia_alcista = (
        actual["close"]
        > actual["ema_tendencia"]
    )

    tendencia_bajista = (
        actual["close"]
        < actual["ema_tendencia"]
    )

    emas_alcistas = (
        actual["ema_rapida"]
        > actual["ema_lenta"]
    )

    emas_bajistas = (
        actual["ema_rapida"]
        < actual["ema_lenta"]
    )

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

    macd_alcista = (
        actual["macd"]
        > actual["macd_signal"]
    )

    macd_bajista = (
        actual["macd"]
        < actual["macd_signal"]
    )

    rsi = float(
        actual["rsi"]
    )

    rsi_alcista = (
        config.RSI_SOBREVENTA
        <= rsi
        <= config.RSI_SOBRECOMPRA
    )

    volumen_ok = (
        actual["volumen_ratio"]
        >= config.VOLUMEN_MIN_MULTIPLICADOR
    )

    atr_pct = (
        actual["atr"]
        / actual["close"]
    )

    volatilidad_ok = (
        atr_pct
        >= config.ATR_MIN_PCT
    )

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

    if compra_fuerte or compra_cruce:
        return "COMPRAR"

    margen = config.MARGEN_SALIDA_PCT

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
# SEÑAL CRYPTO NORMAL
# ============================================================

def _generar_senal_cripto(df):

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

    tendencia_alcista = (
        actual["close"]
        > actual["ema_tendencia"]
    )

    tendencia_bajista = (
        actual["close"]
        < actual["ema_tendencia"]
    )

    emas_alcistas = (
        actual["ema_rapida"]
        > actual["ema_lenta"]
    )

    emas_bajistas = (
        actual["ema_rapida"]
        < actual["ema_lenta"]
    )

    macd_alcista = (
        actual["macd"]
        > actual["macd_signal"]
    )

    macd_bajista = (
        actual["macd"]
        < actual["macd_signal"]
    )

    rsi = float(
        actual["rsi"]
    )

    entrada_rsi = (
        45 <= rsi <= 68
    )

    volumen_ok = (
        actual["volumen_ratio"]
        >= config.VOLUMEN_MIN_MULTIPLICADOR
    )

    atr_pct = (
        actual["atr"]
        / actual["close"]
    )

    volatilidad_ok = (
        atr_pct
        >= config.ATR_MIN_PCT
    )

    precio_sobre_ema = (
        actual["close"]
        > actual["ema_rapida"]
    )

    entrada_principal = (
        tendencia_alcista
        and emas_alcistas
        and macd_alcista
        and entrada_rsi
        and precio_sobre_ema
        and volumen_ok
        and volatilidad_ok
    )

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
# SCANNER CRYPTO — ANÁLISIS DE IMPULSO
# ============================================================

def analizar_impulso_crypto(
    df,
    ticker="?",
):
    """
    Analiza si una crypto está comenzando
    un movimiento alcista.

    Devuelve un diccionario con:

        score
        comprar
        precio
        rsi
        volumen_ratio
        momentum_pct
        ruptura
        tendencia
        motivo

    El objetivo NO es comprar simplemente
    porque el precio esté subiendo.

    Busca coincidencia de varias señales.
    """

    resultado = {
        "ticker": ticker,
        "score": 0.0,
        "comprar": False,
        "precio": None,
        "rsi": None,
        "volumen_ratio": None,
        "momentum_pct": None,
        "ruptura": False,
        "tendencia": False,
        "motivo": [],
    }

    try:

        minimo_velas = max(
            50,
            config.EMA_TENDENCIA + 2,
        )

        if len(df) < minimo_velas:

            resultado["motivo"].append(
                "pocas velas"
            )

            return resultado

        df = calcular_indicadores(
            df
        )

        actual = df.iloc[-1]

        columnas = [
            "close",
            "ema_tendencia",
            "ema_rapida",
            "ema_lenta",
            "rsi",
            "macd",
            "macd_signal",
            "atr",
            "volumen_ratio",
            "cambio_1",
            "cambio_3",
            "cambio_6",
            "maximo_6",
            "maximo_12",
            "pendiente_ema_rapida",
            "separacion_emas",
        ]

        if not _datos_validos(
            actual,
            columnas,
        ):

            resultado["motivo"].append(
                "indicadores incompletos"
            )

            return resultado

        precio = float(
            actual["close"]
        )

        rsi = float(
            actual["rsi"]
        )

        volumen_ratio = float(
            actual["volumen_ratio"]
        )

        atr = float(
            actual["atr"]
        )

        cambio_1 = float(
            actual["cambio_1"]
        )

        cambio_3 = float(
            actual["cambio_3"]
        )

        cambio_6 = float(
            actual["cambio_6"]
        )

        pendiente_ema = float(
            actual["pendiente_ema_rapida"]
        )

        separacion_emas = float(
            actual["separacion_emas"]
        )

        resultado["precio"] = precio
        resultado["rsi"] = rsi
        resultado["volumen_ratio"] = volumen_ratio
        resultado["momentum_pct"] = (
            cambio_3 * 100
        )

        score = 0.0
        motivos = []

        # ====================================================
        # 1. TENDENCIA
        # ====================================================

        tendencia = (
            precio
            > float(actual["ema_tendencia"])
        )

        resultado["tendencia"] = tendencia

        if tendencia:

            score += 15
            motivos.append(
                "precio sobre EMA tendencia"
            )

        # ====================================================
        # 2. EMA RÁPIDA > EMA LENTA
        # ====================================================

        emas_alcistas = (
            float(actual["ema_rapida"])
            > float(actual["ema_lenta"])
        )

        if emas_alcistas:

            score += 12
            motivos.append(
                "EMA rápida > EMA lenta"
            )

        # ====================================================
        # 3. PENDIENTE EMA
        # ====================================================

        if pendiente_ema > 0:

            score += 10
            motivos.append(
                "EMA rápida subiendo"
            )

        # ====================================================
        # 4. SEPARACIÓN DE EMAS
        # ====================================================

        if separacion_emas > 0:

            score += 5
            motivos.append(
                "momentum EMA positivo"
            )

        # ====================================================
        # 5. MACD
        # ====================================================

        macd_alcista = (
            float(actual["macd"])
            > float(actual["macd_signal"])
        )

        if macd_alcista:

            score += 12
            motivos.append(
                "MACD alcista"
            )

        # ====================================================
        # 6. RSI
        # ====================================================

        if (
            config.CRYPTO_RSI_MIN
            <= rsi
            <= config.CRYPTO_RSI_MAX
        ):

            score += 12
            motivos.append(
                "RSI saludable"
            )

        elif rsi > config.CRYPTO_RSI_MAX:

            score -= 10
            motivos.append(
                "RSI demasiado alto"
            )

        else:

            score -= 5
            motivos.append(
                "RSI débil"
            )

        # ====================================================
        # 7. VOLUMEN
        # ====================================================

        if (
            volumen_ratio
            >= config.CRYPTO_VOLUMEN_MIN_MULTIPLICADOR
        ):

            score += 15
            motivos.append(
                "volumen aumentado"
            )

        # ====================================================
        # 8. MOMENTUM
        # ====================================================

        momentum_ok = (
            cambio_3 * 100
            >= config.CRYPTO_MOMENTUM_MIN_PCT
        )

        if momentum_ok:

            score += 8
            motivos.append(
                "momentum positivo"
            )

        # ====================================================
        # 9. RUPTURA
        # ====================================================

        ruptura = False

        maximo_6 = float(
            actual["maximo_6"]
        )

        maximo_12 = float(
            actual["maximo_12"]
        )

        if precio > maximo_6:

            ruptura = True

            score += 10
            motivos.append(
                "ruptura máximo reciente"
            )

        elif precio > maximo_12:

            ruptura = True

            score += 8
            motivos.append(
                "ruptura máximo 12 velas"
            )

        resultado["ruptura"] = ruptura

        # ====================================================
        # 10. EVITAR PERSEGUIR UNA SUBIDA
        # ====================================================

        subida_previa = (
            cambio_6 * 100
        )

        if (
            subida_previa
            > config.CRYPTO_MAX_SUBIDA_PREVIA_PCT
        ):

            score -= 20

            motivos.append(
                "movimiento ya demasiado extendido"
            )

        # ====================================================
        # 11. VOLATILIDAD
        # ====================================================

        atr_pct = (
            atr
            / precio
        )

        if (
            atr_pct
            >= config.CRYPTO_ATR_MIN_PCT
        ):

            score += 6

            motivos.append(
                "volatilidad suficiente"
            )

        else:

            score -= 5

            motivos.append(
                "volatilidad baja"
            )

        # ====================================================
        # RESULTADO
        # ====================================================

        score = max(
            0.0,
            min(
                100.0,
                score,
            ),
        )

        resultado["score"] = round(
            score,
            2,
        )

        resultado["motivo"] = motivos

        # ====================================================
        # CONDICIONES MÍNIMAS
        # ====================================================

        condiciones_minimas = (
            tendencia
            and emas_alcistas
            and macd_alcista
            and momentum_ok
            and volumen_ratio
            >= config.CRYPTO_VOLUMEN_MIN_MULTIPLICADOR
            and (
                config.CRYPTO_RSI_MIN
                <= rsi
                <= config.CRYPTO_RSI_MAX
            )
        )

        resultado["comprar"] = (
            condiciones_minimas
            and score
            >= config.CRYPTO_SCORE_MINIMO
        )

        return resultado

    except Exception as e:

        resultado["motivo"] = [
            f"error: {e}"
        ]

        return resultado


# ============================================================
# GENERAR SEÑAL
# ============================================================

def generar_senal(
    df,
    ticker,
):
    """
    Genera una señal utilizando el ticker real.

    Crypto:
        BTC/USD
        ETH/USD
        SOL/USD

    El resto:
        acciones
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

        print(
            f"{ticker}: error generando "
            f"señal: {e}"
        )

        return "ESPERAR"
