"""
Punto de entrada del bot. Pensado para correr como worker en Railway:
un proceso de larga duración, sin puerto HTTP, que se reinicia solo
si Railway lo mata (por eso el manejo de errores no deja que un fallo
puntual tire abajo todo el proceso).
"""

import time
import logging

import config
import broker
import estrategia
import notificaciones
import gestionar_alpaca

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def revisar_ticker(ticker: str):
    df = broker.obtener_datos(ticker)
    if df.empty:
        log.warning(f"{ticker}: sin datos, se omite.")
        return

    df = estrategia.calcular_indicadores(df)
    senal = estrategia.generar_senal(df)
    precio_actual = float(df.iloc[-1]["close"])
    posicion_abierta = broker.tiene_posicion_abierta(ticker)

    log.info(f"{ticker}: precio=${precio_actual:.2f} señal={senal} posición_abierta={posicion_abierta}")

    if senal == "COMPRAR" and not posicion_abierta:
        if broker.contar_posiciones_abiertas() >= config.MAX_POSICIONES_ABIERTAS:
            log.info("Máximo de posiciones abiertas alcanzado, se omite compra.")
            return
        mensaje = broker.comprar(ticker, precio_actual)
        if mensaje:
            notificaciones.notificar(mensaje)

    elif senal == "VENDER" and posicion_abierta:
        mensaje = broker.vender(ticker)
        if mensaje:
            notificaciones.notificar(mensaje)


def ciclo():
    gestionar_alpaca.revisar_posiciones
    for ticker in config.TICKERS:
        try:
            revisar_ticker(ticker)
        except Exception as e:
            # Un error en un ticker no debe tirar abajo el resto del ciclo.
            log.error(f"Error procesando {ticker}: {e}")


def main():
    config.validar()

    log.info(f"Iniciando bot — modo {'PAPER (simulado)' if config.PAPER else 'REAL'}")
    log.info(f"Tickers: {config.TICKERS} | Intervalo: {config.CHECK_INTERVAL_MINUTES} min")
    notificaciones.notificar(
        f"🤖 Bot iniciado ({'paper' if config.PAPER else 'REAL'}) — "
        f"tickers: {', '.join(config.TICKERS)}"
    )

    while True:
        try:
            if not broker.mercado_abierto():
                log.info("Mercado cerrado. Esperando apertura...")
                time.sleep(60 * 5)
                continue

            ciclo()
            time.sleep(60 * config.CHECK_INTERVAL_MINUTES)

        except Exception as e:
            # Nunca dejamos morir el proceso por un error de red/API puntual.
            # Railway solo reinicia si el proceso termina, así que preferimos
            # loguear, avisar, y reintentar tras una pausa.
            log.error(f"Error en el loop principal: {e}")
            notificaciones.notificar(f"⚠️ Error en el bot: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
