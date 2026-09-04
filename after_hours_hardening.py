"""Refuerzo de observación fuera de mercado.

Fuera de mercado se utiliza el mismo universo dinámico completo de acciones
negociables que durante mercado abierto. No existe una lista de tickers
prioritarios ni se altera la lógica de órdenes, riesgo, SL/TP o exposición.
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

    def observar_universo():
        if not getattr(config, "STOCK_OBSERVATION_ENABLED", True):
            return

        sesion = main_module.obtener_sesion_mercado()
        if sesion == "REGULAR":
            return

        try:
            import stock_universe
            tickers = stock_universe.obtener_universo(broker, config)
        except Exception as exc:
            main_module.log.warning(
                "[acciones observación] No se pudo obtener el universo dinámico: %s",
                exc,
            )
            tickers = list(getattr(config, "TICKERS", []))

        tickers = sorted(set(ticker for ticker in tickers if ticker))

        if not tickers:
            return

        main_module.log.info(
            "[acciones observación] Sesión=%s. Observando %s acciones del universo completo.",
            sesion,
            len(tickers),
        )

        for ticker in tickers:
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

    main_module.observar_acciones_fuera_de_mercado = observar_universo
    main_module._bottrade_after_hours_hardening = True
    main_module.log.info(
        "[seguridad] Observación fuera de mercado usa el universo completo; sin prioridades."
    )
