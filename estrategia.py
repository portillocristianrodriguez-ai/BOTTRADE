import pandas as pd
import ta
import config

def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
df = df.copy()

# =========================================================
# INDICADORES
# =========================================================
df["ema_tendencia"] = ta.trend.ema_indicator(
    df["close"],
    window=config.EMA_TENDENCIA
)
df["atr"] = ta.volatility.average_true_range(
    df["high"],
    df["low"],
    df["close"],
    window=config.ATR_PERIODO
)
# Indicadores adicionales utilizados SOLO por cripto.
df["ema_rapida"] = ta.trend.ema_indicator(
    df["close"],
    window=config.EMA_RAPIDA
)
df["ema_lenta"] = ta.trend.ema_indicator(
    df["close"],
    window=config.EMA_LENTA
)
df["rsi"] = ta.momentum.rsi(
    df["close"],
    window=config.RSI_PERIODO
)
macd = ta.trend.MACD(
    df["close"]
)
df["macd"] = macd.macd()
df["macd_signal"] = macd.macd_signal()
return df

=============================================================

ESTRATEGIA ORIGINAL DE ACCIONES

=============================================================

def _generar_senal_acciones(df: pd.DataFrame) -> str:
"""
ESTRATEGIA ORIGINAL DE ACCIONES.

No se modifica.
"""
minimo_velas = config.EMA_TENDENCIA + 2
if len(df) < minimo_velas:
    return "ESPERAR"
actual = df.iloc[-1]
anterior = df.iloc[-2]
if (
    pd.isna(actual.get("ema_tendencia"))
    or pd.isna(anterior.get("ema_tendencia"))
):
    return "ESPERAR"
margen = config.MARGEN_SALIDA_PCT
cruce_alcista = (
    anterior["close"] <= anterior["ema_tendencia"]
    and actual["close"] > actual["ema_tendencia"]
)
umbral_salida = (
    actual["ema_tendencia"]
    * (1 - margen)
)
umbral_salida_anterior = (
    anterior["ema_tendencia"]
    * (1 - margen)
)
cruce_bajista_confirmado = (
    anterior["close"] >= umbral_salida_anterior
    and actual["close"] < umbral_salida
)
if cruce_bajista_confirmado:
    return "VENDER"
if cruce_alcista:
    return "COMPRAR"
return "ESPERAR"

=============================================================

DETECCIÓN SEGURA DE CRIPTO

=============================================================

def _es_cripto_dataframe(df: pd.DataFrame) -> bool:
“””
Intenta detectar si el DataFrame corresponde a un par cripto
como BTC/USD o ETH/USD.

Si no puede demostrar que es cripto, devuelve False.
Esto protege la estrategia de acciones.
"""
# ---------------------------------------------------------
# Caso 1: columna symbol
# ---------------------------------------------------------
try:
    if "symbol" in df.columns:
        valores = (
            df["symbol"]
            .dropna()
            .astype(str)
            .str.upper()
        )
        if any("/" in valor for valor in valores):
            return True
except Exception:
    pass
# ---------------------------------------------------------
# Caso 2: índice MultiIndex
# ---------------------------------------------------------
try:
    if isinstance(df.index, pd.MultiIndex):
        for nivel in range(
            df.index.nlevels
        ):
            valores = (
                df.index
                .get_level_values(nivel)
                .astype(str)
                .str.upper()
            )
            if any(
                "/" in valor
                for valor in valores
            ):
                return True
except Exception:
    pass
# ---------------------------------------------------------
# Caso 3: índice normal
# ---------------------------------------------------------
try:
    valores = (
        df.index
        .astype(str)
        .str.upper()
    )
    if any(
        "/" in valor
        for valor in valores
    ):
        return True
except Exception:
    pass
return False

=============================================================

ESTRATEGIA EXCLUSIVA DE CRIPTO

=============================================================

def _generar_senal_cripto(df: pd.DataFrame) -> str:
“””
Estrategia específica para criptomonedas.

Busca:
- Precio por encima de EMA 200.
- EMA rápida por encima de EMA lenta.
- Momentum positivo mediante MACD.
- RSI en zona saludable.
- Confirmación de tendencia.
No afecta a las acciones.
"""
minimo_velas = max(
    config.EMA_TENDENCIA,
    config.EMA_LENTA,
    config.RSI_PERIODO,
    config.ATR_PERIODO,
) + 5
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
]
for columna in columnas:
    if (
        pd.isna(actual.get(columna))
        or pd.isna(anterior.get(columna))
    ):
        return "ESPERAR"
# =========================================================
# TENDENCIA
# =========================================================
precio_sobre_tendencia = (
    actual["close"]
    > actual["ema_tendencia"]
)
ema_alcista = (
    actual["ema_rapida"]
    > actual["ema_lenta"]
)
# =========================================================
# MOMENTUM
# =========================================================
macd_alcista = (
    actual["macd"]
    > actual["macd_signal"]
)
# =========================================================
# RSI
# =========================================================
rsi = float(actual["rsi"])
rsi_favorable = (
    rsi >= 45
    and rsi <= 68
)
# =========================================================
# CONFIRMACIÓN DE ENTRADA
# =========================================================
cruce_ema_alcista = (
    anterior["ema_rapida"]
    <= anterior["ema_lenta"]
    and actual["ema_rapida"]
    > actual["ema_lenta"]
)
# Entrada normal cuando la tendencia y momentum
# están alineados.
entrada_tendencia = (
    precio_sobre_tendencia
    and ema_alcista
    and macd_alcista
    and rsi_favorable
)
# Entrada especialmente fuerte cuando además acaba
# de producirse el cruce EMA.
entrada_por_cruce = (
    entrada_tendencia
    and cruce_ema_alcista
)
if entrada_por_cruce:
    return "COMPRAR"
# Permitimos también una entrada cuando la tendencia
# ya está confirmada. Esto evita depender únicamente
# de acertar el minuto exacto del cruce.
if entrada_tendencia:
    return "COMPRAR"
# =========================================================
# SALIDA
# =========================================================
cruce_ema_bajista = (
    anterior["ema_rapida"]
    >= anterior["ema_lenta"]
    and actual["ema_rapida"]
    < actual["ema_lenta"]
)
macd_bajista = (
    actual["macd"]
    < actual["macd_signal"]
)
precio_bajo_tendencia = (
    actual["close"]
    < actual["ema_tendencia"]
)
salida_confirmada = (
    cruce_ema_bajista
    or (
        precio_bajo_tendencia
        and macd_bajista
        and rsi < 45
    )
)
if salida_confirmada:
    return "VENDER"
return "ESPERAR"

=============================================================

SELECTOR PRINCIPAL

=============================================================

def generar_senal(df: pd.DataFrame) -> str:
“””
Selecciona automáticamente la estrategia.

CRIPTO:
    estrategia específica de cripto.
ACCIONES:
    estrategia original.
"""
if _es_cripto_dataframe(df):
    return _generar_senal_cripto(df)
return _generar_senal_acciones(df)
