“””
estrategia.py

Motor de señales del bot.

Gestiona:

* Indicadores técnicos
* Acciones
* Crypto
* Señales de COMPRA / VENTA / ESPERAR
* Scanner de impulso crypto
* Score de oportunidad crypto
* Volumen relativo robusto

IMPORTANTE:
La estrategia no garantiza detectar el inicio exacto
de una subida. Busca confirmar impulso temprano
mediante varios factores simultáneos.
“””

import pandas as pd
import ta

import config

============================================================

INDICADORES

============================================================

def calcular_indicadores(df):

df = df.copy()
# --------------------------------------------------------
# LIMPIEZA BÁSICA
# --------------------------------------------------------
columnas_numericas = [
    "open",
    "high",
    "low",
    "close",
    "volume",
]
for columna in columnas_numericas:
    if columna in df.columns:
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
        "volume",
    ]
)
df = df.sort_index()
# --------------------------------------------------------
# EMA TENDENCIA
# --------------------------------------------------------
df["ema_tendencia"] = (
    ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_TENDENCIA,
    )
)
# --------------------------------------------------------
# ATR
# --------------------------------------------------------
df["atr"] = (
    ta.volatility.average_true_range(
        df["high"],
        df["low"],
        df["close"],
        window=config.ATR_PERIODO,
    )
)
# --------------------------------------------------------
# EMAs RÁPIDA / LENTA
# --------------------------------------------------------
df["ema_rapida"] = (
    ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_RAPIDA,
    )
)
df["ema_lenta"] = (
    ta.trend.ema_indicator(
        df["close"],
        window=config.EMA_LENTA,
    )
)
# --------------------------------------------------------
# RSI
# --------------------------------------------------------
df["rsi"] = (
    ta.momentum.rsi(
        df["close"],
        window=config.RSI_PERIODO,
    )
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
df["macd"] = (
    macd.macd()
)
df["macd_signal"] = (
    macd.macd_signal()
)
df["macd_hist"] = (
    df["macd"]
    - df["macd_signal"]
)
# ========================================================
# VOLUMEN
# ========================================================
#
# IMPORTANTE:
#
# Antes:
#
# volumen actual / media incluyendo la propia vela
#
# Ahora:
#
# volumen actual / media de las velas ANTERIORES
#
# Esto evita que un pico de volumen se "diluya"
# dentro de su propia media.
#
# También protegemos contra volumen 0.
# ========================================================
periodo_volumen = max(
    5,
    int(
        config.VOLUMEN_SMA_PERIODO
    ),
)
volumen_anterior = (
    df["volume"]
    .shift(1)
    .rolling(
        periodo_volumen,
        min_periods=5,
    )
    .mean()
)
df["volumen_media"] = (
    volumen_anterior
)
df["volumen_ratio"] = (
    df["volume"]
    / df["volumen_media"].replace(
        0,
        pd.NA,
    )
)
df["volumen_ratio"] = (
    pd.to_numeric(
        df["volumen_ratio"],
        errors="coerce",
    )
)
# --------------------------------------------------------
# VOLUMEN VÁLIDO
# --------------------------------------------------------
df["volumen_valido"] = (
    df["volume"]
    > 0
)
return df

============================================================

DATOS VÁLIDOS

============================================================

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

============================================================

OBTENER ÚLTIMA VELA CON VOLUMEN ÚTIL

============================================================

def _obtener_indice_barra_crypto(
df,
):

"""
Busca la última vela crypto con volumen > 0.
Esto evita basar el scanner en una vela que todavía
esté formándose o que temporalmente haya llegado con
volumen 0.
Devuelve el índice entero de la vela.
"""
try:
    if df is None or df.empty:
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

============================================================

SEÑAL ACCIONES

============================================================

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
if (
    compra_fuerte
    or compra_cruce
):
    return "COMPRAR"
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

============================================================

SEÑAL CRYPTO

============================================================

def _generar_senal_cripto(
df,
):

minimo_velas = 50
if len(df) < minimo_velas:
    return "ESPERAR"
indice = (
    _obtener_indice_barra_crypto(
        df
    )
)
if indice is None:
    return "ESPERAR"
if indice < 2:
    return "ESPERAR"
datos = (
    calcular_indicadores(
        df
    )
)
if len(datos) < minimo_velas:
    return "ESPERAR"
actual = datos.iloc[
    indice
]
anterior = datos.iloc[
    indice - 1
]
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
    45
    <= rsi
    <= 68
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

============================================================

SCANNER CRYPTO — ANALIZAR IMPULSO

============================================================

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
    # ----------------------------------------------------
    # BUSCAR ÚLTIMA VELA CON VOLUMEN
    # ----------------------------------------------------
    indice_actual = (
        _obtener_indice_barra_crypto(
            datos
        )
    )
    if indice_actual is None:
        return resultado
    if indice_actual < 10:
        return resultado
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
    precio = float(
        actual["close"]
    )
    if precio <= 0:
        return resultado
    rsi = float(
        actual["rsi"]
    )
    volumen_ratio = float(
        actual["volumen_ratio"]
    )
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
    if (
        indice_actual
        < momentum_bars
    ):
        return resultado
    precio_anterior_momentum = (
        float(
            datos.iloc[
                indice_actual
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
    # PENDIENTE EMA
    # ----------------------------------------------------
    if indice_actual >= 3:
        ema_3_barras = float(
            datos.iloc[
                indice_actual - 3
            ]["ema_rapida"]
        )
        if ema_3_barras > 0:
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
    if (
        indice_actual
        <= lookback
    ):
        return resultado
    ventana_previa = (
        datos.iloc[
            indice_actual
            - lookback:
            indice_actual
        ]
    )
    maximo_previo = (
        ventana_previa[
            "high"
        ].max()
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
    # MACD
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
    # EMAs
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
    # ----------------------------------------------------
    # VOLUMEN
    # ----------------------------------------------------
    volumen_fuerte = (
        volumen_ratio
        >= config.CRYPTO_VOLUME_MIN_MULTIPLICADOR
    )
    volumen_medio = (
        volumen_ratio
        >= 1.20
    )
    # ----------------------------------------------------
    # MOMENTUM
    # ----------------------------------------------------
    momentum_minimo = (
        momentum_pct
        >= config.CRYPTO_MIN_MOMENTUM_PCT
    )
    momentum_positivo = (
        momentum_pct > 0
    )
    # ----------------------------------------------------
    # RSI
    # ----------------------------------------------------
    rsi_en_zona = (
        config.CRYPTO_RSI_MIN
        <= rsi
        <= config.CRYPTO_RSI_MAX
    )
    # ----------------------------------------------------
    # ATR
    # ----------------------------------------------------
    volatilidad_ok = (
        atr_pct
        >= (
            config.ATR_MIN_PCT
            * 100
        )
    )
    # ----------------------------------------------------
    # EVITAR ENTRADAS DEMASIADO EXTENDIDAS
    # ----------------------------------------------------
    subida_maxima = (
        momentum_pct
        <= config.CRYPTO_MAX_RISE_PCT
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
        rsi
        > config.CRYPTO_RSI_MAX
        and rsi <= 75
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
        score,
        100,
    )
    # ====================================================
    # FILTROS DUROS
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
        score
        >= config.CRYPTO_SCORE_MINIMO
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
    # ====================================================
    # LOG
    # ====================================================
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
    print(
        f"[crypto scanner] "
        f"{log_message}"
    )
    return resultado
except Exception as e:
    print(
        f"[crypto scanner] "
        f"{ticker}: error analizando "
        f"impulso: {e}"
    )
    return resultado

============================================================

FUNCIÓN PRINCIPAL DE SEÑAL

============================================================

def generar_senal(
df,
ticker,
):

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

“””
