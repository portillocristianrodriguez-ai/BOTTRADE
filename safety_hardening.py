"""Refuerzos de seguridad de runtime para BOTTRADE.

No cambia señales ni sizing. Se limita a:
- evitar que fallos de observación de símbolos con pocos datos disparen el circuit breaker;
- verificar periódicamente que TODAS las posiciones de acciones tengan SL+TP;
- dejar constancia explícita de que las posiciones crypto se gestionan por el motor 24/7.
"""
from __future__ import annotations

import threading
import time


def instalar(main_module):
    """Instala refuerzos una sola vez y arranca el watchdog universal."""
    if getattr(main_module, "_bottrade_safety_hardening", False):
        return
    main_module._bottrade_safety_hardening = True

    original_error = getattr(main_module, "registrar_error_operativo", None)
    if callable(original_error):
        def registrar_error_filtrado(origen, error):
            # Una observación fuera de mercado con barras insuficientes
            # no es un fallo operativo del trading y no debe bloquear
            # nuevas entradas mediante el circuit breaker.
            origen_texto = str(origen or "")
            if origen_texto.startswith("observacion_acciones_"):
                main_module.log.debug(
                    "[seguridad] Error de observación aislado: %s: %s",
                    origen_texto,
                    error,
                )
                return
            return original_error(origen, error)

        registrar_error_filtrado._bottrade_safety_hardening = True
        main_module.registrar_error_operativo = registrar_error_filtrado

    thread = threading.Thread(
        target=_watchdog_proteccion_universal,
        args=(main_module,),
        daemon=True,
        name="WatchdogProteccionUniversal",
    )
    thread.start()
    main_module.log.info(
        "[protección] Watchdog universal activo: todas las posiciones de acciones se verifican automáticamente."
    )


def _watchdog_proteccion_universal(main_module):
    config = main_module.config
    broker = main_module.broker
    intervalo = max(10, int(getattr(config, "WATCHDOG_INTERVAL_SECONDS", 30)))

    while True:
        try:
            posiciones = broker.obtener_todas_las_posiciones()
            acciones = 0
            criptos = 0

            for posicion in posiciones:
                ticker = getattr(posicion, "symbol", None)
                if not ticker:
                    continue

                if broker.es_cripto(ticker):
                    criptos += 1
                    continue

                acciones += 1
                try:
                    analisis = broker.analizar_proteccion(ticker)
                    completa = bool(analisis.get("tiene_proteccion", False))
                    if completa:
                        main_module.limpiar_posicion_sin_proteccion(ticker)
                        main_module.log.debug(
                            "[protección] %s: SL + TP completos.", ticker
                        )
                        continue

                    main_module.log.warning(
                        "[protección] %s: posición sin protección completa; intentando recuperarla.",
                        ticker,
                    )
                    main_module.proteger_compra_ejecutada(ticker)
                except Exception as exc:
                    main_module.marcar_posicion_sin_proteccion(ticker)
                    main_module.log.error(
                        "[protección] %s: fallo en watchdog universal: %s",
                        ticker,
                        exc,
                    )

            if posiciones:
                main_module.log.info(
                    "[protección] Verificación universal: %s posiciones (%s acciones, %s crypto).",
                    len(posiciones),
                    acciones,
                    criptos,
                )

        except Exception as exc:
            main_module.log.warning(
                "[protección] Watchdog universal no pudo consultar posiciones: %s",
                exc,
            )

        time.sleep(intervalo)
