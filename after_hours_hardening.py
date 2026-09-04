"""Refuerzo de observación fuera de mercado.

El universo completo se reserva para el scanner durante mercado abierto.
Fuera de mercado solo se observan los tickers manuales/prioritarios, evitando
miles de consultas históricas inútiles cada ciclo y sin tocar la lógica de
órdenes, riesgo, SL/TP ni exposición.
"""
from __future__ import annotations


def instalar(main_module):
    if getattr(main_module, "_bottrade_after_hours_hardening", False):
        return

    original = getattr(main_module, "observar_acciones_fuera_de_mercado", None)
    if not callable(original):
        return

    config = main_module.config
    broker = main_module.broker
    estrategia = main_module.estrategia

    def observar_prioridades():
        if not getattr(config, "STOCK_OBSERVATION_ENABLED", True):
            return

        sesion = main_module.obtener_sesion_mercado()
        if sesion == "REGULAR":
            return

        tickers = list(getattr(config, "TICKERS", []))
        # El universo dinámico ya contiene los manuales al principio. Estos
        # son los únicos que necesitamos observar cuando el mercado está cerrado.
        manuales = []
        for ticker in tickers:
            if ticker not in manuales:
                manuales.append(ticker)
            if len(manuales) >= 5:
                break

        if not manuales:
            return

        main_module.log.info(
            "[acciones observación] Sesión=%s. Observando %s tickers prioritarios.",
            sesion,
            len(manuales),
        )

        for ticker in manuales:
            try:
                df = broker.obtener_datos(ticker)
                if df is None or df.empty:
                    continue
                df = estrategia.calcular_indicadores(df)
                senal = estrategia.generar_senal(df, ticker)
                main_module.registrar_observacion_pattern(ticker, df, None, senal)
            except Exception as exc:
                # Observación fuera de mercado: nunca debe bloquear el trading.
                main_module.log.warning(
                    "[acciones observación] %s: %s",
                    ticker,
                    exc,
                )

    main_module.observar_acciones_fuera_de_mercado = observar_prioridades
    main_module._bottrade_after_hours_hardening = True
    main_module.log.info(
        "[seguridad] Observación fuera de mercado limitada a tickers prioritarios."
    )
