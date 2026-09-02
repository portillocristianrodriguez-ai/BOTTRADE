"""
Punto de entrada del bot. Pensado para correr como worker en Railway:
un proceso de larga duración, sin puerto HTTP, que se reinicia solo
si Railway lo mata (por eso el manejo de errores no deja que un fallo
puntual tire abajo todo el proceso).

Corre dos loops independientes en paralelo (hilos), cada uno con su
propio intervalo:
- Acciones (config.TICKERS): cada CHECK_INTERVAL_MINUTES, solo si el
  mercado está abierto.
- Cripto (config.CRYPTO_TICKERS): cada CRYPTO_CHECK_INTERVAL_MINUTES,
  siempre (mercado 24/7).
"""

import time
import logging
import threading

import config
import broker
import estrategia
import notificaciones

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

    # Stop-loss manual para cripto: Alpaca no soporta bracket orders en
    # cripto, así que aquí forzamos la venta si la pérdida ya supera
    # STOP_LOSS_PCT, sin esperar a que la estrategia genere señal VENDER.
    if posicion_abierta and broker.es_cripto(ticker):
        perdida_pct = broker.perdida_pct_no_realizada(ticker)
        if perdida_pct is not None and perdida_pct <= -config.STOP_LOSS_PCT:
            log.warning(f"{ticker}: stop-loss manual disparado ({perdida_pct:.2%}). Vendiendo.")
            mensaje = broker.vender(ticker)
            if mensaje:
                notificaciones.notificar(f"🛑 STOP-LOSS manual — {mensaje} (pérdida: {perdida_pct:.2%})")
            return

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


def loop_acciones():
    if not config.TICKERS:
        return
    while True:
        try:
            if broker.mercado_abierto():
                for ticker in config.TICKERS:
                    try:
                        revisar_ticker(ticker)
                    except Exception as e:
                        log.error(f"[acciones] Error procesando {ticker}: {e}")
            else:
                log.info("[acciones] Mercado cerrado, se omite este ciclo.")
        except Exception as e:
            log.error(f"[acciones] Error en el loop: {e}")
            notificaciones.notificar(f"⚠️ Error en el loop de acciones: {e}")
        time.sleep(60 * config.CHECK_INTERVAL_MINUTES)


def loop_cripto():
    if not config.CRYPTO_TICKERS:
        return
    while True:
        try:
            for ticker in config.CRYPTO_TICKERS:
                try:
                    revisar_ticker(ticker)
                except Exception as e:
                    log.error(f"[cripto] Error procesando {ticker}: {e}")
        except Exception as e:
            log.error(f"[cripto] Error en el loop: {e}")
            notificaciones.notificar(f"⚠️ Error en el loop de cripto: {e}")
        time.sleep(60 * config.CRYPTO_CHECK_INTERVAL_MINUTES)


def main():
    config.validar()

    log.info(f"Iniciando bot — modo {'PAPER (simulado)' if config.PAPER else 'REAL'}")
    log.info(
        f"Acciones: {config.TICKERS} (cada {config.CHECK_INTERVAL_MINUTES} min) | "
        f"Cripto: {config.CRYPTO_TICKERS} (cada {config.CRYPTO_CHECK_INTERVAL_MINUTES} min)"
    )
    notificaciones.notificar(
        f"🤖 Bot iniciado ({'paper' if config.PAPER else 'REAL'}) — "
        f"acciones: {', '.join(config.TICKERS) or '(ninguna)'} — "
        f"cripto: {', '.join(config.CRYPTO_TICKERS) or '(ninguna)'}"
    )

    hilos = []
    if config.TICKERS:
        hilos.append(threading.Thread(target=loop_acciones, daemon=True))
    if config.CRYPTO_TICKERS:
        hilos.append(threading.Thread(target=loop_cripto, daemon=True))

    if not hilos:
        log.error("No hay TICKERS ni CRYPTO_TICKERS configurados. Nada que hacer.")
        return

    for hilo in hilos:
        hilo.start()

    # El hilo principal se queda vivo mientras los loops corren en segundo plano.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
