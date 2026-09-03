def cancelar_protecciones(
    ticker: str,
) -> bool:
    try:
        ordenes = obtener_ordenes_ticker(ticker)
        protecciones = []
        for orden in ordenes:
            side = str(
                getattr(
                    orden,
                    "side",
                    "",
                )
            ).lower()
            if "sell" not in side:
                continue
            tipo = str(
                getattr(
                    orden,
                    "type",
                    "",
                )
            ).lower()
            order_class = str(
                getattr(
                    orden,
                    "order_class",
                    "",
                )
            ).lower()
            stop_price = getattr(
                orden,
                "stop_price",
                None
            )
            limit_price = getattr(
                orden,
                "limit_price",
                None
            )
            stop_loss = getattr(
                orden,
                "stop_loss",
                None
            )
            take_profit = getattr(
                orden,
                "take_profit",
                None
            )
            legs = getattr(
                orden,
                "legs",
                None
            )
            es_proteccion = (
                "stop" in tipo
                or "oco" in order_class
                or "bracket" in order_class
                or stop_price is not None
                or limit_price is not None
                or stop_loss is not None
                or take_profit is not None
                or bool(legs)
            )
            if es_proteccion:
                protecciones.append(orden)
        # ----------------------------------------------------
        # NO HAY NADA QUE CANCELAR
        # ----------------------------------------------------
        if not protecciones:
            return True
        # ----------------------------------------------------
        # CANCELAR CADA ORDEN PRINCIPAL
        # ----------------------------------------------------
        for orden in protecciones:
            try:
                cliente_trading.cancel_order_by_id(
                    orden.id
                )
                log.info(
                    f"{ticker}: protección "
                    f"{orden.id} cancelada."
                )
            except Exception as e:
                mensaje_error = str(e).lower()
                # Si ya fue cancelada como consecuencia
                # de cancelar la otra pata de la OCO,
                # no lo consideramos un fallo real.
                if (
                    "not found" in mensaje_error
                    or "already canceled" in mensaje_error
                    or "already cancelled" in mensaje_error
                    or "cancelled" in mensaje_error
                    or "canceled" in mensaje_error
                ):
                    log.debug(
                        f"{ticker}: protección "
                        f"{orden.id} ya no estaba activa."
                    )
                    continue
                log.warning(
                    f"{ticker}: no se pudo "
                    f"cancelar protección "
                    f"{orden.id}: {e}"
                )
                return False
        return True
    except Exception as e:
        log.error(
            f"{ticker}: error cancelando "
            f"protecciones: {e}"
        )
        return False
