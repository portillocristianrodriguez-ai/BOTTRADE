import pandas as pd
import ta
import config


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_tendencia"] = ta.trend.ema_indicator(df["close"], window=config.EMA_TENDENCIA)
    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=config.ATR_PERIODO
    )
    return df


def generar_senal(df: pd.DataFrame) -> str:
    """Seguimiento de tendencia con margen de confirmación:
    - COMPRAR: el precio cruza por encima de la EMA de tendencia (igual que v2).
    - VENDER: el precio cae MARGEN_SALIDA_PCT por debajo de la EMA de
      tendencia (no basta con cruzarla apenas) — filtra caídas de corto
      plazo que se recuperan solas, y solo sale en caídas de tendencia real.
    - ESPERAR: en cualquier otro caso.

    Esto reduce operaciones y deja correr más las ganancias, a cambio de
    aceptar una caída algo mayor antes de salir (más riesgo por operación,
    menos operaciones fallidas por ruido)."""
    minimo_velas = config.EMA_TENDENCIA + 2
    if len(df) < minimo_velas:
        return "ESPERAR"

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

    if pd.isna(actual.get("ema_tendencia")) or pd.isna(anterior.get("ema_tendencia")):
        return "ESPERAR"

    margen = config.MARGEN_SALIDA_PCT

    cruce_alcista = (
        anterior["close"] <= anterior["ema_tendencia"]
        and actual["close"] > actual["ema_tendencia"]
    )

    # Salida con margen: el precio debe estar MARGEN_SALIDA_PCT por debajo
    # de la EMA, no solo cruzarla. anterior no estaba ya tan por debajo
    # (para detectar el momento en que se cruza ese umbral, no cada vela
    # mientras siga por debajo).
    umbral_salida = actual["ema_tendencia"] * (1 - margen)
    umbral_salida_anterior = anterior["ema_tendencia"] * (1 - margen)
    cruce_bajista_confirmado = (
        anterior["close"] >= umbral_salida_anterior
        and actual["close"] < umbral_salida
    )

    if cruce_bajista_confirmado:
        return "VENDER"
    if cruce_alcista:
        return "COMPRAR"

    return "ESPERAR"

