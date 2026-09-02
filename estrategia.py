"""
Estrategia: cruce de EMA + confirmación RSI + MACD.

- COMPRAR: EMA rápida cruza por encima de la lenta (tendencia alcista
  empezando), RSI no está en sobrecompra, MACD confirma momentum positivo.
- VENDER: EMA rápida cruza por debajo de la lenta, o RSI entra en
  sobrecompra (posible techo).
- ESPERAR: cualquier otro caso.

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
    df["rsi"] = ta.momentum.rsi(df["close"], window=config.RSI_PERIODO)
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    return df


def generar_senal(df: pd.DataFrame) -> str:
    minimo_velas = max(config.EMA_LENTA, config.RSI_PERIODO) + 2
    if len(df) < minimo_velas:
        return "ESPERAR"

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

    cruce_alcista = (
        anterior["ema_rapida"] <= anterior["ema_lenta"]
        and actual["ema_rapida"] > actual["ema_lenta"]
    )
    cruce_bajista = (
        anterior["ema_rapida"] >= anterior["ema_lenta"]
        and actual["ema_rapida"] < actual["ema_lenta"]
    )
    macd_positivo = actual["macd"] > actual["macd_signal"]

    if cruce_alcista and actual["rsi"] < config.RSI_SOBRECOMPRA and macd_positivo:
        return "COMPRAR"
    if cruce_bajista or actual["rsi"] > config.RSI_SOBRECOMPRA:
        return "VENDER"
    if actual["rsi"] < config.RSI_SOBREVENTA and macd_positivo:
        return "COMPRAR"

    return "ESPERAR"
