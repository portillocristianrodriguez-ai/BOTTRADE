"""Refuerzos de seguridad, universos y monitorización de BOTTRADE."""
from __future__ import annotations

import threading
import time


def instalar(main_module):
    if getattr(main_module, "_bottrade_safety_hardening", False):
        return
    main_module._bottrade_safety_hardening = True

    original_error = getattr(main_module, "registrar_error_operativo", None)
    if callable(original_error):
        def registrar_error_filtrado(origen, error):
            if str(origen or "").startswith("observacion_acciones_"):
                main_module.log.debug(
                    "[seguridad] Error de observación aislado: %s: %s",
                    origen,
                    error,
                )
                return
            return original_error(origen, error)
        main_module.registrar_error_operativo = registrar_error_filtrado

    original_callback = getattr(main_module, "procesar_comando_telegram", None)
    if callable(original_callback):
        def callback_con_universos(comando):
            # IMPORTANTE: /crypto ya existía y debe conservar su comportamiento.
            # El universo completo de crypto se expone con /universo_crypto.
            if comando == "/universo":
                return _resumen_universos(main_module)
            if comando in ("/acciones", "/stocks", "/universo_acciones"):
                return _resumen_acciones(main_module)
            if comando == "/universo_crypto":
                return _resumen_crypto(main_module)
            if comando in ("/help", "/start"):
                base = original_callback(comando) or ""
                extra = (
                    "🌐 UNIVERSOS\n"
                    "/universo — acciones + crypto\n"
                    "/acciones — universo completo de acciones\n"
                    "/stocks — alias de /acciones\n"
                    "/universo_acciones — universo completo de acciones\n"
                    "/universo_crypto — universo completo de crypto\n"
                    "ℹ️ /crypto conserva el comando original del bot."
                )
                return f"{base}\n\n{extra}" if base else extra
            # Todos los comandos originales pasan intactos al callback original.
            return original_callback(comando)
        main_module.procesar_comando_telegram = callback_con_universos

    threading.Thread(
        target=_watchdog_proteccion_universal,
        args=(main_module,),
        daemon=True,
        name="WatchdogProteccionUniversal",
    ).start()
    main_module.log.info(
        "[protección] Watchdog universal activo: "
        "todas las posiciones de acciones se verifican automáticamente."
    )


def _resumen_acciones(main_module):
    try:
        import stock_universe
        universo = stock_universe.obtener_universo(
            main_module.broker,
            main_module.config,
        )
        return (
            "📈 UNIVERSO ACCIONES\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"Total negociables: {len(universo):,}\n\n"
            f"Muestra (alfabético): {', '.join(universo[:80])}\n\n"
            f"Actualización: cada {main_module.config.STOCK_UNIVERSE_REFRESH_MINUTES} min"
        )
    except Exception as exc:
        return f"❌ No se pudo consultar acciones: {exc}"


def _resumen_crypto(main_module):
    try:
        activos = main_module.broker.cliente_trading.get_all_assets()
        estables = {
            "USDT", "USDC", "DAI", "USDG", "PYUSD", "USDS",
            "FDUSD", "TUSD", "USDP", "GUSD", "EURC",
        }
        universo = []
        for activo in activos:
            simbolo = str(
                getattr(activo, "symbol", "")
            ).upper().strip().replace("-", "/")
            tradable = bool(getattr(activo, "tradable", False))
            status = str(
                getattr(
                    getattr(activo, "status", ""),
                    "value",
                    getattr(activo, "status", ""),
                )
            ).lower()
            clase = str(
                getattr(
                    getattr(activo, "asset_class", ""),
                    "value",
                    getattr(activo, "asset_class", ""),
                )
            ).lower()
            if (
                not tradable
                or (status and "active" not in status)
                or "/" not in simbolo
                or not simbolo.endswith("/USD")
            ):
                continue
            if clase and "crypto" not in clase:
                continue
            if (
                main_module.config.CRYPTO_EXCLUIR_ESTABLES
                and simbolo.split("/")[0] in estables
            ):
                continue
            universo.append(simbolo)

        universo = sorted(set(universo))
        return (
            "₿ UNIVERSO CRYPTO\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"Total USD negociables: {len(universo):,}\n\n"
            f"{', '.join(universo)}\n\n"
            f"Actualización: cada {main_module.config.CRYPTO_UNIVERSE_REFRESH_MINUTES} min"
        )
    except Exception as exc:
        return f"❌ No se pudo consultar crypto: {exc}"


def _resumen_universos(main_module):
    return (
        "🤖 UNIVERSOS BOTTRADE\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{_resumen_acciones(main_module)}\n\n"
        f"{_resumen_crypto(main_module)}"
    )


def _watchdog_proteccion_universal(main_module):
    config = main_module.config
    broker = main_module.broker
    intervalo = max(
        10,
        int(getattr(config, "WATCHDOG_INTERVAL_SECONDS", 30)),
    )
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
                    if bool(analisis.get("tiene_proteccion", False)):
                        main_module.limpiar_posicion_sin_proteccion(ticker)
                        continue
                    main_module.log.warning(
                        "[protección] %s: posición sin protección completa; "
                        "intentando recuperarla.",
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
                    "[protección] Verificación universal: %s posiciones "
                    "(%s acciones, %s crypto).",
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
