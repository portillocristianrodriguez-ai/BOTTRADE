import pandas as pd
import ta
import config


def calcular_indicadores(df):
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
        window=9
    )

    df["ema_lenta"] = ta.trend.ema_indicator(
        df["close"],
        window=21
    )

    df["rsi"] = ta.momentum.rsi(
        df["close"],
        window=14
    )

    macd = ta.trend.MACD(
        df["close"],
        window_fast=12,
        window_slow=26,
        window_sign=9
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    return df


def _generar_senal_acciones(df):
    minimo_velas = config.EMA_TENDENCIA + 2

    if len(df) < minimo_velas:
        return "ESPERAR"

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

    if pd.isna(actual.get("ema_tendencia")) or pd.isna(
        anterior.get("ema_tendencia")
    ):
        return "ESPERAR"

    margen = config.MARGEN_SALIDA_PCT

    cruce_alcista = (
        anterior["close"] <= anterior["ema_tendencia"]
        and actual["close"] > actual["ema_tendencia"]
    )

    umbral_salida = actual["ema_tendencia"] * (1 - margen)
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


def _es_cripto_dataframe(df):
    try:
        if isinstance(df.index, pd.MultiIndex):
            for nivel in df.index.levels:
                for valor in nivel:
                    if "/" in str(valor):
                        return True
    except Exception:
        pass

    try:
        indice = pd.to_datetime(df.index)

        if len(indice) >= 3:
            diferencias = (
                indice.to_series()
                .diff()
                .dropna()
                .dt.total_seconds()
            )

            if not diferencias.empty:
                mediana = diferencias.median()

                if mediana <= 120:
                    return True
    except Exception:
        pass

    return False


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
    ]

    for columna in columnas:
        if pd.isna(actual.get(columna)):
            return "ESPERAR"

    tendencia_alcista = actual["close"] > actual["ema_tendencia"]

    emas_alcistas = (
        actual["ema_rapida"] > actual["ema_lenta"]
    )

    macd_alcista = (
        actual["macd"] > actual["macd_signal"]
    )

    rsi_valor = actual["rsi"]

    entrada = (
        tendencia_alcista
        and emas_alcistas
        and macd_alcista
        and 45 <= rsi_valor <= 68
        and actual["close"] > actual["ema_rapida"]
    )

    if entrada:
        return "COMPRAR"

    cruce_ema_bajista = (
        anterior["ema_rapida"] >= anterior["ema_lenta"]
        and actual["ema_rapida"] < actual["ema_lenta"]
    )

    salida_tendencia = (
        actual["close"] < actual["ema_tendencia"]
        and actual["macd"] < actual["macd_signal"]
        and rsi_valor < 45
    )

    if cruce_ema_bajista or salida_tendencia:
        return "VENDER"

    return "ESPERAR"


def generar_senal(df):
    if _es_cripto_dataframe(df):
        return _generar_senal_cripto(df)

    return _generar_senal_acciones(df)
