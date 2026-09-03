"""
Estrategia: cruce de EMA + confirmación RSI + MACD, con filtros que
reducen señales falsas:

- Filtro de tendencia macro (EMA_TENDENCIA, 200 por defecto): solo compra
  si el precio está por encima de esta media. Evita comprar "rebotes"
  dentro de una tendencia bajista de fondo.
- Filtro de volumen: solo entra si el volumen actual iguala o supera su
  media reciente. Un cruce con volumen bajo suele ser ruido.
- Filtro de volatilidad (ATR): evita operar cuando el mercado está
  demasiado plano, condición en la que los cruces de EMA generan muchas
  señales falsas.

- COMPRAR: EMA rápida cruza por encima de la lenta (o RSI en sobreventa +
  MACD positivo), con tendencia macro alcista, volumen suficiente y
  volatilidad suficiente.
- VENDER: EMA rápida cruza por debajo de la lenta, o RSI entra en
  sobrecompra.
- ESPERAR: cualquier otro caso, incluido cuando algún filtro no se cumple.

Ningún indicador predice el futuro con certeza — esto identifica
probabilidades razonables, no garantías.
"""

import pandas as pd
import ta
import config


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_rapida"] = ta.trend.ema_indicator(df["close"], window=config.EMA_RAPIDA)
    df["ema_lenta"] = ta.trend.ema_indicator(df["close"], window=config.EMA_LENTA)
    df["ema_tendencia"] = ta.trend.ema_indicator(df["close"], window=config.EMA_TENDENCIA)
    df["rsi"] = ta.momentum.rsi(df["close"], window=config.RSI_PERIODO)
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=config.ATR_PERIODO
    )
    if "volume" in df.columns:
        df["volumen_media"] = df["volume"].rolling(window=config.VOLUMEN_SMA_PERIODO).mean()
    return df


def _filtros_ok(actual: pd.Series) -> bool:
    """Devuelve False si el contexto de mercado no es adecuado para operar,
    sin importar lo que digan las señales de cruce/RSI/MACD."""
    # Volatilidad mínima: si el ATR es muy pequeño respecto al precio, el
    # mercado está demasiado plano y los cruces suelen ser ruido.
    if pd.isna(actual.get("atr")) or actual["close"] <= 0:
        return False
    atr_pct = actual["atr"] / actual["close"]
    if atr_pct < config.ATR_MIN_PCT:
        return False

    # Volumen: si hay dato de volumen disponible, exige que esté por encima
    # de su media reciente (con margen configurable).
    if "volumen_media" in actual and not pd.isna(actual.get("volumen_media")):
        if actual["volume"] < actual["volumen_media"] * config.VOLUMEN_MIN_MULTIPLICADOR:
            return False

    return True


def generar_senal(df: pd.DataFrame) -> str:
    minimo_velas = max(config.EMA_TENDENCIA, config.EMA_LENTA, config.RSI_PERIODO) + 2
    if len(df) < minimo_velas:
        return "ESPERAR"

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

    if pd.isna(actual.get("ema_tendencia")):
        return "ESPERAR"

    tendencia_alcista = actual["close"] > actual["ema_tendencia"]

    cruce_alcista = (
        anterior["ema_rapida"] <= anterior["ema_lenta"]
        and actual["ema_rapida"] > actual["ema_lenta"]
    )
    cruce_bajista = (
        anterior["ema_rapida"] >= anterior["ema_lenta"]
        and actual["ema_rapida"] < actual["ema_lenta"]
    )
    macd_positivo = actual["macd"] > actual["macd_signal"]

    # Las ventas no dependen de los filtros de contexto: si toca salir,
    # se sale igual (el filtro solo protege las entradas de baja calidad).
    if cruce_bajista or actual["rsi"] > config.RSI_SOBRECOMPRA:
        return "VENDER"

    if not _filtros_ok(actual) or not tendencia_alcista:
        return "ESPERAR"

    if cruce_alcista and actual["rsi"] < config.RSI_SOBRECOMPRA and macd_positivo:
        return "COMPRAR"
    if actual["rsi"] < config.RSI_SOBREVENTA and macd_positivo:
        return "COMPRAR"

    return "ESPERAR"
