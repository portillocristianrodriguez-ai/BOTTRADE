```python
import math

import pandas as pd
import ta

import config


# ============================================================
# UTILIDADES
# ============================================================

def _es_numero_valido(valor):
    """
    Devuelve True únicamente para números finitos y válidos.
    """
    try:
        if valor is None:
            return False

        if pd.isna(valor):
            return False

        numero = float(valor)

        return math.isfinite(numero)

    except Exception:
        return False


def _config_float(nombre, default):
    """
    Obtiene un float de config de forma segura.
    """
    try:
        valor = getattr(config, nombre, default)
        valor = float(valor)

        if not math.isfinite(valor):
            return float(default)

        return valor

    except Exception:
        return float(default)


def _config_int(nombre, default):
    """
    Obtiene un entero de config de forma segura.
    """
    try:
        valor = int(getattr(config, nombre, default))
        return valor

    except Exception:
        return int(default)


# ============================================================
# INDICADORES
# ============================================================

def calcular_indicadores(df):
    """
    Calcula todos los indicadores utilizados por el bot.

    Esta función intenta ser tolerante con datos incompletos:
    - convierte columnas numéricas;
    - elimina filas inválidas;
    - evita divisiones por cero;
    - deja NaN en indicadores que todavía no tienen suficientes
      velas, en lugar de provocar excepciones.
    """

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df debe ser un pandas.DataFrame")

    if df.empty:
        return pd.DataFrame()

    df = df.copy()

    columnas_numericas = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    columnas_faltantes = [
        columna
        for columna in columnas_numericas
        if columna not in df.columns
    ]

    if columnas_faltantes:
        raise ValueError(
            "Faltan columnas requeridas: "
            + ", ".join(columnas_faltantes)
        )

    for columna in columnas_numericas:

        df[columna] = pd.to_numeric(
            df[columna],
            errors="coerce",
        )

    df = df.dropna(
        subset=columnas_numericas
    )

    if df.empty:
        return df

    df = df.sort_index()

    # ========================================================
    # ELIMINAR PRECIOS INVÁLIDOS
    # ========================================================

    df = df[
        (df["close"] > 0)
        & (df["high"] > 0)
        & (df["low"] > 0)
        & (df["open"] > 0)
        & (df["volume"] >= 0)
    ]

    if df.empty:
        return df

    # ========================================================
    # EMA TENDENCIA
    # ========================================================

    ema_tendencia_periodo = max(
        2,
        _config_int(
            "EMA_TENDENCIA",
            200,
        ),
    )

    df["ema_tendencia"] = (
        ta.trend.ema_indicator(
            df["close"],
            window=ema_tendencia_periodo,
        )
    )

    # ========================================================
    # ATR
    # ========================================================

    atr_periodo = max(
        2,
        _config_int(
            "ATR_PERIODO",
            14,
        ),
    )

    df["atr"] = (
        ta.volatility.average_true_range(
            df["high"],
            df["low"],
            df["close"],
            window=atr_periodo,
        )
    )

    # ========================================================
    # EMA RAPIDA
    # ========================================================

    ema_rapida_periodo = max(
        2,
        _config_int(
            "EMA_RAPIDA",
            9,
        ),
    )

    df["ema_rapida"] = (
        ta.trend.ema_indicator(
            df["close"],
            window=ema_rapida_periodo,
        )
    )

    # ========================================================
    # EMA LENTA
    # ========================================================

    ema_lenta_periodo = max(
        2,
        _config_int(
            "EMA_LENTA",
            21,
        ),
    )

    df["ema_lenta"] = (
        ta.trend.ema_indicator(
            df["close"],
            window=ema_lenta_periodo,
        )
    )

    # ========================================================
    # RSI
    # ========================================================

    rsi_periodo = max(
        2,
        _config_int(
            "RSI_PERIODO",
            14,
        ),
    )

    df["rsi"] = (
        ta.momentum.rsi(
            df["close"],
            window=rsi_periodo,
        )
    )

    # ========================================================
    # MACD
    # ========================================================

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

    # ========================================================
    # VOLUMEN RELATIVO
    # ========================================================

    periodo_volumen = max(
        5,
        _config_int(
            "VOLUMEN_SMA_PERIODO",
            20,
        ),
    )

    volumen_media_anterior = (
        df["volume"]
        .shift(1)
        .rolling(
            periodo_volumen,
            min_periods=5,
        )
        .mean()
    )

    df["volumen_media"] = (
        volumen_media_anterior
    )

    denominador = (
        df["volumen_media"]
        .where(
            df["volumen_media"] > 0
        )
    )

    df["volumen_ratio"] = (
        df["volume"]
        / denominador
    )

    df["volumen_ratio"] = (
        pd.to_numeric(
            df["volumen_ratio"],
            errors="coerce",
        )
    )

    df["volumen_valido"] = (
        df["volume"] > 0
    )

    # ========================================================
    # LIMPIEZA FINAL DE INFINITOS
    # ========================================================

    columnas_indicadores = [
        "ema_tendencia",
        "atr",
        "ema_rapida",
        "ema_lenta",
        "rsi",
        "macd",
        "macd_signal",
        "macd_hist",
        "volumen_ratio",
    ]

    for columna in columnas_indicadores:

        if columna in df.columns:

            df[columna] = df[columna].replace(
                [float("inf"), float("-inf")],
                pd.NA,
            )

            df[columna] = pd.to_numeric(
                df[columna],
                errors="coerce",
            )

    return df


# ============================================================
# DATOS VÁLIDOS
# ============================================================

def _datos_validos(
    actual,
    columnas,
):
    """
    Comprueba que las columnas requeridas contienen
    números finitos.
    """

    if actual is None:
        return False

    for columna in columnas:

        try:
            valor = actual.get(
                columna
            )
        except Exception:
            return False

        if not _es_numero_valido(
            valor
        ):
            return False

    return True


# ============================================================
# ÚLTIMA VELA CON VOLUMEN VÁLIDO
# ============================================================

def _obtener_indice_barra_crypto(
    df,
):
    """
    Obtiene la última posición cuyo volumen es > 0.

    Importante:
    Una vela con volumen 0 no se considera un error.
    Simplemente no se utiliza como vela activa para el
    cálculo de la señal crypto.
    """

    try:

        if df is None or df.empty:
            return None

        if "volume" not in df.columns:
            return None

        volumen = pd.to_numeric(
            df["volume"],
            errors="coerce",
        )

        indices_validos = (
            volumen[
                volumen > 0
            ].index
        )

        if len(indices_validos) == 0:
            return None

        ultimo_indice = (
            indices_validos[-1]
        )

        posiciones = (
            df.index.get_indexer(
                [ultimo_indice]
            )
        )

        if (
            len(posiciones) == 0
            or posiciones[0] < 0
        ):
            return None

        return int(
            posiciones[0]
        )

    except Exception:
        return None


# ============================================================
# SEÑAL ACCIONES
# ============================================================

def _generar_senal_acciones(
    df,
):

    ema_tendencia_periodo = max(
        2,
        _config_int(
            "EMA_TENDENCIA",
            200,
        ),
    )

    minimo_velas = (
        ema_tendencia_periodo
        + 2
    )

    if df is None or df.empty:
        return "ESPERAR"

    if len(df) < minimo_velas:
        return "ESPERAR"

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

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

    precio = float(
        actual["close"]
    )

    atr = float(
        actual["atr"]
    )

    if precio <= 0 or atr <= 0:
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

    rsi_sobreventa = _config_float(
        "RSI_SOBREVENTA",
        30,
    )

    rsi_sobrecompra = _config_float(
        "RSI_SOBRECOMPRA",
        70,
    )

    rsi_alcista = (
        rsi_sobreventa
        <= rsi
        <= rsi_sobrecompra
    )

    volumen_min = _config_float(
        "VOLUMEN_MIN_MULTIPLICADOR",
        1.0,
    )

    volumen_ok = (
        actual["volumen_ratio"]
        >= volumen_min
    )

    atr_min_pct = _config_float(
        "ATR_MIN_PCT",
        0.003,
    )

    atr_pct = (
        atr
        / precio
    )

    volatilidad_ok = (
        atr_pct
        >= atr_min_pct
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

    if (
        compra_fuerte
        or compra_cruce
    ):
        return "COMPRAR"

    margen = _config_float(
        "MARGEN_SALIDA_PCT",
        0.05,
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
# SCANNER ACCIONES
# ============================================================

def analizar_impulso_acciones(
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

        ema_tendencia_periodo = max(
            2,
            _config_int(
                "EMA_TENDENCIA",
                200,
            ),
        )

        minimo_velas = max(
            220,
            ema_tendencia_periodo + 5,
        )

        if len(df) < minimo_velas:
            return resultado

        datos = calcular_indicadores(
            df
        )

        if datos is None or datos.empty:
            return resultado

        if len(datos) < minimo_velas:
            return resultado

        indice_actual = (
            len(datos) - 1
        )

        actual = datos.iloc[
            indice_actual
        ]

        anterior = datos.iloc[
            indice_actual - 1
        ]

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

        if not _datos_validos(
            anterior,
            [
                "ema_rapida",
                "ema_lenta",
                "macd_hist",
            ],
        ):
            return resultado

        precio = float(
            actual["close"]
        )

        if precio <= 0:
            return resultado

        # ====================================================
        # RSI
        # ====================================================

        rsi = float(
            actual["rsi"]
        )

        # ====================================================
        # VOLUMEN
        # ====================================================

        volumen_ratio = float(
            actual["volumen_ratio"]
        )

        if (
            not math.isfinite(
                volumen_ratio
            )
            or volumen_ratio < 0
        ):
            return resultado

        # ====================================================
        # ATR
        # ====================================================

        atr = float(
            actual["atr"]
        )

        if (
            not math.isfinite(atr)
            or atr <= 0
        ):
            return resultado

        atr_pct = (
            atr
            / precio
            * 100
        )

        # ====================================================
        # MOMENTUM
        # ====================================================

        momentum_bars = max(
            1,
            _config_int(
                "MOMENTUM_BARS",
                _config_int(
                    "CRYPTO_MOMENTUM_BARS",
                    3,
                ),
            ),
        )

        if indice_actual < momentum_bars:
            return resultado

        precio_anterior_momentum = float(
            datos.iloc[
                indice_actual
                - momentum_bars
            ]["close"]
        )

        if (
            not math.isfinite(
                precio_anterior_momentum
            )
            or precio_anterior_momentum <= 0
        ):
            return resultado

        momentum_pct = (
            (
                precio
                - precio_anterior_momentum
            )
            / precio_anterior_momentum
        ) * 100

        # ====================================================
        # PENDIENTE EMA 9
        # ====================================================

        if indice_actual >= 3:

            ema_actual = float(
                actual["ema_rapida"]
            )

            ema_3_barras = float(
                datos.iloc[
                    indice_actual - 3
                ]["ema_rapida"]
            )

            if (
                math.isfinite(
                    ema_actual
                )
                and math.isfinite(
                    ema_3_barras
                )
                and ema_3_barras > 0
            ):

                ema_slope_pct = (
                    (
                        ema_actual
                        - ema_3_barras
                    )
                    / ema_3_barras
                ) * 100

            else:

                ema_slope_pct = 0.0

        else:

            ema_slope_pct = 0.0

        # ====================================================
        # BREAKOUT
        # ====================================================

        lookback = max(
            2,
            _config_int(
                "BREAKOUT_LOOKBACK",
                _config_int(
                    "CRYPTO_BREAKOUT_LOOKBACK",
                    12,
                ),
            ),
        )

        if indice_actual <= lookback:
            return resultado

        ventana_previa = (
            datos.iloc[
                indice_actual - lookback:
                indice_actual
            ]
        )

        if ventana_previa.empty:
            return resultado

        maximo_previo = (
            ventana_previa["high"].max()
        )

        if not _es_numero_valido(
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

        # ====================================================
        # MACD
        # ====================================================

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

        # ====================================================
        # EMAS
        # ====================================================

        ema_rapida = float(
            actual["ema_rapida"]
        )

        ema_lenta = float(
            actual["ema_lenta"]
        )

        ema_tendencia = float(
            actual["ema_tendencia"]
        )

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

        # ====================================================
        # VOLUMEN
        # ====================================================

        volumen_min = _config_float(
            "VOLUMEN_MIN_MULTIPLICADOR",
            1.0,
        )

        volumen_fuerte = (
            volumen_ratio
            >= volumen_min
        )

        volumen_medio = (
            volumen_ratio
            >= 1.20
        )

        # ====================================================
        # MOMENTUM
        # ====================================================

        momentum_minimo_config = _config_float(
            "MIN_MOMENTUM_PCT",
            _config_float(
                "CRYPTO_MIN_MOMENTUM_PCT",
                0.30,
            ),
        )

        momentum_minimo = (
            momentum_pct
            >= momentum_minimo_config
        )

        momentum_positivo = (
            momentum_pct > 0
        )

        # ====================================================
        # RSI
        # ====================================================

        rsi_min_acciones = _config_float(
            "RSI_MIN_ACCIONES",
            50.0,
        )

        rsi_max_acciones = _config_float(
            "RSI_MAX_ACCIONES",
            68.0,
        )

        rsi_en_zona = (
            rsi_min_acciones
            <= rsi
            <= rsi_max_acciones
        )

        # ====================================================
        # VOLATILIDAD
        # ====================================================

        atr_min_config = _config_float(
            "ATR_MIN_PCT",
            0.003,
        )

        volatilidad_ok = (
            atr_pct
            >= (
                atr_min_config
                * 100
            )
        )

        # ====================================================
        # EVITAR MOVIMIENTO EXCESIVAMENTE EXTENDIDO
        # ====================================================

        subida_maxima_config = _config_float(
            "MAX_RISE_PCT",
            _config_float(
                "CRYPTO_MAX_RISE_PCT",
                10.0,
            ),
        )

        subida_maxima = (
            momentum_pct
            <= subida_maxima_config
        )

        # ====================================================
        # SCORE
        # ====================================================

        score = 0.0

        motivos = []

        if precio_sobre_tendencia:

            score += 10

            motivos.append(
                "precio > EMA tendencia"
            )

        if emas_alineadas:

            score += 15

            motivos.append(
                "EMA9 > EMA21"
            )

        if slope_positivo:

            score += 10

            motivos.append(
                "EMA acelerando"
            )

        if breakout:

            score += 20

            motivos.append(
                "breakout"
            )

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

        if rsi_en_zona:

            score += 10

            motivos.append(
                "RSI saludable"
            )

        elif (
            rsi > 68
            and rsi <= 72
        ):

            score += 3

            motivos.append(
                "RSI elevado"
            )

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

        if volatilidad_ok:

            score += 5

            motivos.append(
                "volatilidad suficiente"
            )

        score = min(
            float(score),
            100.0,
        )

        # ====================================================
        # FILTROS DUROS DE COMPRA
        # ====================================================

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
            score >= 75
            and filtros_duros
        )

        # ====================================================
        # MOTIVOS DE DESCARTE
        # ====================================================

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

        # ====================================================
        # RESULTADO
        # ====================================================

        resultado = {
            "score": float(score),
            "comprar": bool(comprar),
            "motivo": motivos,
            "rsi": float(rsi),
            "volumen_ratio": float(volumen_ratio),
            "momentum_pct": float(momentum_pct),
            "atr_pct": float(atr_pct),
            "breakout": bool(breakout),
        }

        # ====================================================
        # LOG
        # ====================================================

        print(
            f"[acciones scanner] "
            f"{ticker}: "
            f"score={score:.1f} "
            f"comprar={comprar} "
            f"RSI={rsi:.1f} "
            f"vol={volumen_ratio:.2f}x "
            f"momentum={momentum_pct:+.2f}% "
            f"ATR={atr_pct:.2f}% "
            f"breakout={breakout}"
        )

        return resultado

    except Exception as e:

        # Este error NO debe propagarse al motor de trading.
        # Se devuelve un resultado seguro.
        print(
            f"[acciones scanner] "
            f"{ticker}: ERROR CONTROLADO "
            f"analizando impulso: "
            f"{type(e).__name__}: {e}"
        )

        return resultado


# ============================================================
# SEÑAL CRYPTO
# ============================================================

def _generar_senal_cripto(
    df,
):

    minimo_velas = 50

    if df is None or df.empty:
        return "ESPERAR"

    if len(df) < minimo_velas:
        return "ESPERAR"

    datos = calcular_indicadores(
        df
    )

    if datos is None or datos.empty:
        return "ESPERAR"

    if len(datos) < minimo_velas:
        return "ESPERAR"

    indice_actual = (
        _obtener_indice_barra_crypto(
            datos
        )
    )

    if indice_actual is None:
        return "ESPERAR"

    if indice_actual < 2:
        return "ESPERAR"

    actual = datos.iloc[
        indice_actual
    ]

    anterior = datos.iloc[
        indice_actual - 1
    ]

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
    ]

    if not _datos_validos(
        actual,
        columnas,
    ):
        return "ESPERAR"

    if not _datos_validos(
        anterior,
        [
            "ema_rapida",
            "ema_lenta",
            "macd",
            "macd_signal",
        ],
    ):
        return "ESPERAR"

    precio = float(
        actual["close"]
    )

    atr = float(
        actual["atr"]
    )

    if (
        not math.isfinite(precio)
        or precio <= 0
    ):
        return "ESPERAR"

    if (
        not math.isfinite(atr)
        or atr <= 0
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
        45
        <= rsi
        <= 68
    )

    volumen_min = _config_float(
        "VOLUMEN_MIN_MULTIPLICADOR",
        1.0,
    )

    volumen_ratio = float(
        actual["volumen_ratio"]
    )

    # Volumen 0 o inválido = no hay entrada.
    volumen_ok = (
        math.isfinite(
            volumen_ratio
        )
        and volumen_ratio > 0
        and volumen_ratio >= volumen_min
    )

    atr_min_pct = _config_float(
        "ATR_MIN_PCT",
        0.003,
    )

    atr_pct = (
        atr
        / precio
    )

    volatilidad_ok = (
        atr_pct
        >= atr_min_pct
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
# FUNCIÓN PRINCIPAL DE SEÑAL
# ============================================================

def generar_senal(
    df,
    ticker,
):

    try:

        if df is None or df.empty:
            return "ESPERAR"

        ticker_str = str(
            ticker
        ).upper()

        if "/" in ticker_str:
            return _generar_senal_cripto(
                df
            )

        return _generar_senal_acciones(
            df
        )

    except Exception as e:

        print(
            f"[estrategia] "
            f"{ticker}: ERROR CONTROLADO "
            f"generando señal: "
            f"{type(e).__name__}: {e}"
        )

        return "ESPERAR"
```
