"""
estrategia.py

Motor de señales del bot.

Gestiona:

- Indicadores técnicos
- Acciones
- Cripto
- Señales de COMPRA / VENTA / ESPERAR
- Scanner de impulso crypto
- Score de oportunidad crypto

IMPORTANTE:
La estrategia no garantiza detectar el inicio exacto
de una subida. Busca confirmar impulso temprano
mediante varios factores simultáneos.
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

    df["macd_signal"] = (
        macd.macd_signal()
    )

    df["macd_hist"] = (
        df["macd"]
        - df["macd_signal"]
    )

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
# DATOS VÁLIDOS
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
        config.EMA_TENDENCIA
        + 2
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

    # --------------------------------------------------------
    # TENDENCIA
    # --------------------------------------------------------

    tendencia_alcista = (
        actual["close"]
        > actual["ema_tendencia"]
    )

    tendencia_bajista = (
        actual["close"]
        < actual["ema_tendencia"]
    )

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    macd_alcista = (
        actual["macd"]
        > actual["macd_signal"]
    )

    macd_bajista = (
        actual["macd"]
        < actual["macd_signal"]
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi = float(
        actual["rsi"]
    )

    rsi_alcista = (
        config.RSI_SOBREVENTA
        <= rsi
        <= config.RSI_SOBRECOMPRA
    )

    # --------------------------------------------------------
    # VOLUMEN
    # --------------------------------------------------------

    volumen_ok = (
        actual["volumen_ratio"]
        >= config.VOLUMEN_MIN_MULTIPLICADOR
    )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    atr_pct = (
        actual["atr"]
        / actual["close"]
    )

    volatilidad_ok = (
        atr_pct
        >= config.ATR_MIN_PCT
    )

    # --------------------------------------------------------
    # COMPRA FUERTE
    # --------------------------------------------------------

    compra_fuerte = (
        tendencia_alcista
        and emas_alcistas
        and macd_alcista
        and rsi_alcista
        and volumen_ok
        and volatilidad_ok
    )

    # --------------------------------------------------------
    # CRUCE EMA
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # VENTAS
    # --------------------------------------------------------

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
# SEÑAL CRYPTO
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

    # --------------------------------------------------------
    # TENDENCIA
    # --------------------------------------------------------

    tendencia_alcista = (
        actual["close"]
        > actual["ema_tendencia"]
    )

    tendencia_bajista = (
        actual["close"]
        < actual["ema_tendencia"]
    )

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    emas_alcistas = (
        actual["ema_rapida"]
        > actual["ema_lenta"]
    )

    emas_bajistas = (
        actual["ema_rapida"]
        < actual["ema_lenta"]
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    macd_alcista = (
        actual["macd"]
        > actual["macd_signal"]
    )

    macd_bajista = (
        actual["macd"]
        < actual["macd_signal"]
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi = float(
        actual["rsi"]
    )

    entrada_rsi = (
        45
        <= rsi
        <= 68
    )

    # --------------------------------------------------------
    # VOLUMEN
    # --------------------------------------------------------

    volumen_ok = (
        actual["volumen_ratio"]
        >= config.VOLUMEN_MIN_MULTIPLICADOR
    )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    atr_pct = (
        actual["atr"]
        / actual["close"]
    )

    volatilidad_ok = (
        atr_pct
        >= config.ATR_MIN_PCT
    )

    # --------------------------------------------------------
    # PRECIO SOBRE EMA
    # --------------------------------------------------------

    precio_sobre_ema = (
        actual["close"]
        > actual["ema_rapida"]
    )

    # --------------------------------------------------------
    # ENTRADA PRINCIPAL
    # --------------------------------------------------------

    entrada_principal = (
        tendencia_alcista
        and emas_alcistas
        and macd_alcista
        and entrada_rsi
        and precio_sobre_ema
        and volumen_ok
        and volatilidad_ok
    )

    # --------------------------------------------------------
    # CRUCE EMA
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # VENTAS
    # --------------------------------------------------------

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
# SCANNER CRYPTO — ANALIZAR IMPULSO
# ============================================================

def analizar_impulso_crypto(
    df,
    ticker,
):

    resultado = {
        "score": 0.0,
        "comprar": False,
        "motivo": [],
        "rsi": 0.0,
        "volumen_ratio": 0.0,
        "momentum_pct": 0.0,
        "atr_pct": 0.0,
        "breakout": False,
    }

    try:

        if df is None or df.empty:

            return resultado

        # ----------------------------------------------------
        # MÍNIMO DE VELAS
        # ----------------------------------------------------

        minimo_velas = max(
            220,
            config.EMA_TENDENCIA + 5,
        )

        if len(df) < minimo_velas:

            return resultado

        datos = (
            calcular_indicadores(
                df
            )
        )

        if len(datos) < minimo_velas:

            return resultado

        actual = datos.iloc[-1]

        anterior = datos.iloc[-2]

        # ----------------------------------------------------
        # DATOS FUNDAMENTALES
        # ----------------------------------------------------

        columnas = [
            "close",
            "ema_tendencia",
            "ema_rapida",
            "ema_lenta",
            "rsi",
            "macd",
            "macd_signal",
            "macd_hist",
            "atr",
            "volumen_ratio",
        ]

        if not _datos_validos(
            actual,
            columnas,
        ):

            return resultado

        precio = float(
            actual["close"]
        )

        if precio <= 0:

            return resultado

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        rsi = float(
            actual["rsi"]
        )

        # ----------------------------------------------------
        # VOLUMEN
        # ----------------------------------------------------

        volumen_ratio = float(
            actual["volumen_ratio"]
        )

        # ----------------------------------------------------
        # ATR
        # ----------------------------------------------------

        atr = float(
            actual["atr"]
        )

        atr_pct = (
            atr
            / precio
            * 100
        )

        # ----------------------------------------------------
        # MOMENTUM
        # ----------------------------------------------------

        momentum_bars = max(
            1,
            int(
                config.CRYPTO_MOMENTUM_BARS
            ),
        )

        if len(datos) <= momentum_bars:

            return resultado

        precio_anterior_momentum = (
            float(
                datos.iloc[
                    -1
                    - momentum_bars
                ]["close"]
            )
        )

        if (
            precio_anterior_momentum
            <= 0
        ):

            return resultado

        momentum_pct = (
            (
                precio
                - precio_anterior_momentum
            )
            / precio_anterior_momentum
        ) * 100

        # ----------------------------------------------------
        # SLOPE EMA RÁPIDA
        # ----------------------------------------------------

        if len(datos) >= 4:

            ema_3_barras = float(
                datos.iloc[-4][
                    "ema_rapida"
                ]
            )

            ema_slope_pct = (
                (
                    float(
                        actual[
                            "ema_rapida"
                        ]
                    )
                    - ema_3_barras
                )
                / ema_3_barras
            ) * 100

        else:

            ema_slope_pct = 0.0

        # ----------------------------------------------------
        # BREAKOUT
        # ----------------------------------------------------

        lookback = max(
            2,
            int(
                config.CRYPTO_BREAKOUT_LOOKBACK
            ),
        )

        if len(datos) <= lookback:

            return resultado

        maximo_previo = (
            datos[
                "high"
            ]
            .shift(1)
            .rolling(
                lookback
            )
            .max()
            .iloc[-1]
        )

        if pd.isna(
            maximo_previo
        ):

            return resultado

        maximo_previo = float(
            maximo_previo
        )

        breakout = (
            precio
            > maximo_previo
        )

        # ----------------------------------------------------
        # MACD HISTOGRAMA
        # ----------------------------------------------------

        macd_hist = float(
            actual["macd_hist"]
        )

        macd_hist_anterior = float(
            anterior["macd_hist"]
        )

        macd_hist_positivo = (
            macd_hist > 0
        )

        macd_hist_creciendo = (
            macd_hist
            > macd_hist_anterior
        )

        # ----------------------------------------------------
        # EMA
        # ----------------------------------------------------

        ema_rapida = float(
            actual["ema_rapida"]
        )

        ema_lenta = float(
            actual["ema_lenta"]
        )

        ema_tendencia = float(
            actual["ema_tendencia"]
        )

        # ----------------------------------------------------
        # CONDICIONES
        # ----------------------------------------------------

        precio_sobre_tendencia = (
            precio
            > ema_tendencia
        )

        emas_alineadas = (
            ema_rapida
            > ema_lenta
        )

        slope_positivo = (
            ema_slope_pct
            > 0
        )

        volumen_fuerte = (
            volumen_ratio
            >= config.CRYPTO_VOLUME_MIN_MULTIPLICADOR
        )

        volumen_medio = (
            volumen_ratio
            >= 1.20
        )

        momentum_minimo = (
            momentum_pct
            >= config.CRYPTO_MIN_MOMENTUM_PCT
        )

        momentum_positivo = (
            momentum_pct > 0
        )

        rsi_en_zona = (
            config.CRYPTO_RSI_MIN
            <= rsi
            <= config.CRYPTO_RSI_MAX
        )

        volatilidad_ok = (
            atr_pct
            >= (
                config.ATR_MIN_PCT
                * 100
            )
        )

        # ----------------------------------------------------
        # MOVIMIENTO DEMASIADO EXTENDIDO
        # ----------------------------------------------------

        subida_maxima = (
            momentum_pct
            <= config.CRYPTO_MAX_RISE_PCT
        )

        # ----------------------------------------------------
        # SCORE
        # ----------------------------------------------------

        score = 0.0

        motivos = []

        # Precio sobre EMA tendencia
        if precio_sobre_tendencia:

            score += 10

            motivos.append(
                "precio > EMA tendencia"
            )

        # EMA rápida > lenta
        if emas_alineadas:

            score += 15

            motivos.append(
                "EMA9 > EMA21"
            )

        # Pendiente EMA positiva
        if slope_positivo:

            score += 10

            motivos.append(
                "EMA acelerando"
            )

        # Ruptura
        if breakout:

            score += 20

            motivos.append(
                "breakout"
            )

        # Volumen fuerte
        if volumen_fuerte:

            score += 20

            motivos.append(
                "volumen fuerte"
            )

        elif volumen_medio:

            score += 10

            motivos.append(
                "volumen creciente"
            )

        # RSI
        if rsi_en_zona:

            score += 10

            motivos.append(
                "RSI saludable"
            )

        elif (
            rsi
            > config.CRYPTO_RSI_MAX
            and rsi <= 75
        ):

            score += 3

            motivos.append(
                "RSI elevado"
            )

        # MACD
        if macd_hist_positivo:

            score += 5

            motivos.append(
                "MACD positivo"
            )

        if macd_hist_creciendo:

            score += 5

            motivos.append(
                "MACD creciendo"
            )

        # Momentum
        if momentum_minimo:

            score += 5

            motivos.append(
                "momentum positivo"
            )

        elif momentum_positivo:

            score += 2

            motivos.append(
                "momentum positivo débil"
            )

        # ATR
        if volatilidad_ok:

            score += 5

            motivos.append(
                "volatilidad suficiente"
            )

        # ----------------------------------------------------
        # LIMITAR SCORE
        # ----------------------------------------------------

        score = min(
            score,
            100,
        )

        # ----------------------------------------------------
        # HARD FILTERS
        # ----------------------------------------------------

        filtros_duros = (
            precio_sobre_tendencia
            and emas_alineadas
            and slope_positivo
            and volumen_fuerte
            and momentum_minimo
            and rsi_en_zona
            and volatilidad_ok
            and subida_maxima
        )

        comprar = (
            score
            >= config.CRYPTO_SCORE_MINIMO
            and filtros_duros
        )

        # ----------------------------------------------------
        # MOTIVOS DE RECHAZO
        # ----------------------------------------------------

        if not precio_sobre_tendencia:

            motivos.append(
                "debajo EMA tendencia"
            )

        if not emas_alineadas:

            motivos.append(
                "EMA no alineadas"
            )

        if not slope_positivo:

            motivos.append(
                "EMA sin aceleración"
            )

        if not volumen_fuerte:

            motivos.append(
                "volumen insuficiente"
            )

        if not momentum_minimo:

            motivos.append(
                "momentum insuficiente"
            )

        if not rsi_en_zona:

            motivos.append(
                "RSI fuera de zona"
            )

        if not volatilidad_ok:

            motivos.append(
                "ATR insuficiente"
            )

        if not subida_maxima:

            motivos.append(
                "movimiento demasiado extendido"
            )

        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------

        resultado = {
            "score": float(
                score
            ),
            "comprar": bool(
                comprar
            ),
            "motivo": motivos,
            "rsi": float(
                rsi
            ),
            "volumen_ratio": float(
                volumen_ratio
            ),
            "momentum_pct": float(
                momentum_pct
            ),
            "atr_pct": float(
                atr_pct
            ),
            "breakout": bool(
                breakout
            ),
        }

        log_message = (
            f"{ticker}: "
            f"score={score:.1f} "
            f"comprar={comprar} "
            f"RSI={rsi:.1f} "
            f"vol={volumen_ratio:.2f}x "
            f"momentum={momentum_pct:+.2f}% "
            f"ATR={atr_pct:.2f}% "
            f"breakout={breakout}"
        )

        # No usamos logging aquí para evitar
        # duplicar configuración de logging.
        print(
            f"[crypto scanner] {log_message}"
        )

        return resultado

    except Exception as e:

        print(
            f"[crypto scanner] "
            f"{ticker}: error analizando "
            f"impulso: {e}"
        )

        return resultado


# ============================================================
# FUNCIÓN PRINCIPAL DE SEÑAL
# ============================================================

def generar_senal(
    df,
    ticker,
):

    """
    Genera una señal utilizando el ticker real.

    Criptomonedas:
        BTC/USD
        ETH/USD
        SOL/USD

    El resto se considera acción.
    """

    try:

        if "/" in str(
            ticker
        ):

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
