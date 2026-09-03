import pandas as pd
import ta
import config

def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
df = df.copy()

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
macd = ta.trend.MACD(df["close"])
df["macd"] = macd.macd()
df["macd_signal"] = macd.macd_signal()
return df

def _generar_senal_acciones(df: pd.DataFrame) -> str:

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
    actual["ema_tendencia"] * (1 - margen)
)
umbral_salida_anterior = (
    anterior["ema_tendencia"] * (1 - margen)
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

def _es_cripto_dataframe(df: pd.DataFrame) -> bool:

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
try:
    if isinstance(df.index, pd.MultiIndex):
        for nivel in range(df.index.nlevels):
            valores = (
                df.index
                .get_level_values(nivel)
                .astype(str)
                .str.upper()
            )
            if any("/" in valor for valor in valores):
                return True
except Exception:
    pass
try:
    valores = (
        df.index
        .astype(str)
        .str.upper()
    )
    if any("/" in valor for valor in valores):
        return True
except Exception:
    pass
return False

def _generar_senal_cripto(df: pd.DataFrame) -> str:

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
precio_sobre_tendencia = (
    actual["close"] > actual["ema_tendencia"]
)
ema_alcista = (
    actual["ema_rapida"] > actual["ema_lenta"]
)
macd_alcista = (
    actual["macd"] > actual["macd_signal"]
)
rsi = float(actual["rsi"])
rsi_favorable = (
    rsi >= 45
    and rsi <= 68
)
cruce_ema_alcista = (
    anterior["ema_rapida"] <= anterior["ema_lenta"]
    and actual["ema_rapida"] > actual["ema_lenta"]
)
entrada_tendencia = (
    precio_sobre_tendencia
    and ema_alcista
    and macd_alcista
    and rsi_favorable
)
entrada_por_cruce = (
    entrada_tendencia
    and cruce_ema_alcista
)
if entrada_por_cruce:
    return "COMPRAR"
if entrada_tendencia:
    return "COMPRAR"
cruce_ema_bajista = (
    anterior["ema_rapida"] >= anterior["ema_lenta"]
    and actual["ema_rapida"] < actual["ema_lenta"]
)
macd_bajista = (
    actual["macd"] < actual["macd_signal"]
)
precio_bajo_tendencia = (
    actual["close"] < actual["ema_tendencia"]
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

def generar_senal(df: pd.DataFrame) -> str:

if _es_cripto_dataframe(df):
    return _generar_senal_cripto(df)
return _generar_senal_acciones(df)
