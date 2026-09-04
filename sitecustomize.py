"""Execution hardening, portfolio-aware signals and dynamic position sizing."""
from __future__ import annotations

import builtins
import hashlib
import time

_INSTALLED_BROKER = False
_INSTALLED_STRATEGY = False
_ORIGINAL_IMPORT = builtins.__import__
_PORTFOLIO = {"bucket": None, "items": []}
_SIGNAL_SCORES = {}


def _client_id(order_data):
    symbol = str(getattr(order_data, "symbol", "ORDER") or "ORDER").upper().replace("/", "")
    side = str(getattr(order_data, "side", "NA") or "NA").upper()
    typ = str(getattr(order_data, "type", getattr(order_data, "order_type", "market")) or "market").lower()
    qty = str(getattr(order_data, "qty", "") or "")
    notional = str(getattr(order_data, "notional", "") or "")
    limit_price = str(getattr(order_data, "limit_price", "") or "")
    stop_price = str(getattr(order_data, "stop_price", "") or "")
    bucket = int(time.time() // 300)
    raw = "|".join((symbol, side, typ, qty, notional, limit_price, stop_price, str(bucket)))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"BT-MOM-{symbol[:12]}-{digest}"


def _disable_secondary_account(broker_module):
    """Desactiva cualquier soporte legado de segunda cuenta."""
    if hasattr(broker_module, "cliente_trading_secundaria"):
        broker_module.cliente_trading_secundaria = None

    def _sin_segunda_cuenta(*args, **kwargs):
        return None

    def _sin_posiciones_secundarias(*args, **kwargs):
        return []

    if hasattr(broker_module, "obtener_resumen_cuenta_secundaria"):
        broker_module.obtener_resumen_cuenta_secundaria = _sin_segunda_cuenta
    if hasattr(broker_module, "obtener_posiciones_secundaria"):
        broker_module.obtener_posiciones_secundaria = _sin_posiciones_secundarias


def _install_broker(broker_module):
    global _INSTALLED_BROKER
    if _INSTALLED_BROKER:
        return
    client = getattr(broker_module, "cliente_trading", None)
    submit = getattr(client, "submit_order", None) if client is not None else None
    validate = getattr(broker_module, "_validar_orden_compra_final", None)
    size_original = getattr(broker_module, "calcular_tamano_posicion", None)
    if client is None or not callable(submit) or not callable(validate) or not callable(size_original):
        return

    _disable_secondary_account(broker_module)

    def dynamic_size(ticker, precio, atr):
        """Ajusta el tamaño por volatilidad y calidad de señal sin saltarse límites."""
        qty = size_original(ticker, precio, atr)
        try:
            import config
            precio = float(precio)
            atr = float(atr)
            if qty <= 0 or precio <= 0 or atr <= 0:
                return qty

            atr_pct = atr / precio
            if atr_pct <= 0:
                return qty

            if broker_module.es_cripto(ticker):
                objetivo = float(getattr(config, "CRYPTO_TARGET_ATR_PCT", 0.020))
            else:
                objetivo = float(getattr(config, "STOCK_TARGET_ATR_PCT", 0.015))

            minimo = float(getattr(config, "DYNAMIC_RISK_MIN_MULTIPLIER", 0.60))
            maximo = float(getattr(config, "DYNAMIC_RISK_MAX_MULTIPLIER", 1.15))
            minimo = min(1.0, max(0.10, minimo))
            maximo = max(1.0, min(1.50, maximo))
            objetivo = max(0.0001, objetivo)

            # Menor ATR relativo => algo más de tamaño; mayor ATR => menos.
            vol_factor = objetivo / atr_pct
            vol_factor = min(maximo, max(minimo, vol_factor))

            # La señal manda dentro de un rango pequeño: calidad baja reduce
            # exposición; señal excelente permite usar algo más del presupuesto.
            score = float(_SIGNAL_SCORES.get(str(ticker).upper(), 70.0))
            score_factor = 0.75 + 0.40 * min(1.0, max(0.0, (score - 70.0) / 30.0))
            factor = min(maximo, max(minimo, vol_factor * score_factor))

            ajustada = float(qty) * factor

            if broker_module.es_cripto(ticker):
                ajustada = round(ajustada, 6)
            else:
                ajustada = int(ajustada)

            if ajustada <= 0:
                return 0

            if abs(factor - 1.0) >= 0.02:
                broker_module.log.info(
                    f"[SIZING] {ticker}: ATR%={atr_pct:.4%} objetivo={objetivo:.4%} "
                    f"score={score:.1f} vol_factor={vol_factor:.3f} "
                    f"factor={factor:.3f} qty={qty}->{ajustada}"
                )
            return ajustada
        except Exception as exc:
            broker_module.log.warning(f"[SIZING] {ticker}: sizing dinámico omitido: {exc}")
            return qty

    def risk_check(ticker, qty, price):
        if not validate(ticker, qty, price):
            return False
        try:
            import config
            import execution_guard
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest
            account = client.get_account()
            equity = float(getattr(account, "equity", 0) or 0)
            buying_power = float(getattr(account, "buying_power", 0) or 0)
            proposed = float(qty) * float(price)
            if equity <= 0 or buying_power <= 0 or proposed <= 0:
                return False
            bp_pct = min(0.99, max(0.10, float(getattr(config, "MAX_BUYING_POWER_USAGE_PCT", 0.90))))
            if proposed > buying_power * bp_pct + 0.01:
                broker_module.log.critical(f"[GUARDIA] {ticker}: buying power insuficiente para nueva orden")
                return False
            if broker_module.es_cripto(ticker):
                cap = float(getattr(config, "CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD", 100000.0))
                if cap > 0 and proposed > cap + 0.01:
                    broker_module.log.critical(f"[GUARDIA] {ticker}: supera cap interno crypto")
                    return False
            positions = client.get_all_positions()
            open_orders = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500, nested=True))
            if broker_module.tiene_posicion_abierta(ticker) or broker_module.obtener_ordenes_ticker(ticker):
                return False
            ok, reason = execution_guard.validar_exposicion_compra(
                equity=equity,
                proposed_notional=proposed,
                positions=positions,
                open_orders=open_orders,
                max_single_position_pct=float(getattr(config, "MAX_SINGLE_POSITION_PCT", 0.20)),
                max_total_exposure_pct=float(getattr(config, "MAX_TOTAL_EXPOSURE_PCT", 0.50)),
            )
            if not ok:
                broker_module.log.critical(f"[GUARDIA] {ticker}: exposición bloqueada: {reason}")
            return ok
        except Exception as exc:
            broker_module.log.critical(f"[GUARDIA] {ticker}: validación final fallida; orden bloqueada: {exc}")
            return False

    def guarded_submit(order_data=None, *args, **kwargs):
        if order_data is not None and not getattr(order_data, "client_order_id", None):
            cid = _client_id(order_data)
            try:
                order_data.client_order_id = cid
            except Exception:
                dumped = order_data.model_dump()
                dumped["client_order_id"] = cid
                order_data = type(order_data)(**dumped)
            broker_module.log.info(f"[GUARDIA] client_order_id={cid}")
        return submit(order_data=order_data, *args, **kwargs)

    broker_module.calcular_tamano_posicion = dynamic_size
    broker_module._validar_orden_compra_final = risk_check
    client.submit_order = guarded_submit
    _INSTALLED_BROKER = True


def _corr(a, b):
    try:
        import pandas as pd
        ra = pd.to_numeric(a["close"], errors="coerce").pct_change()
        rb = pd.to_numeric(b["close"], errors="coerce").pct_change()
        joined = pd.concat([ra, rb], axis=1, join="inner").dropna()
        if len(joined) < 12:
            return 0.0
        value = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
        return value if pd.notna(value) else 0.0
    except Exception:
        return 0.0


def _install_strategy(strategy_module):
    global _INSTALLED_STRATEGY
    if _INSTALLED_STRATEGY:
        return
    original = getattr(strategy_module, "analizar_impulso_crypto", None)
    if not callable(original):
        return

    def portfolio_crypto(df, ticker):
        result = original(df, ticker)
        if not isinstance(result, dict):
            return result
        try:
            bucket = int(time.time() // 180)
            if _PORTFOLIO["bucket"] != bucket:
                _PORTFOLIO["bucket"] = bucket
                _PORTFOLIO["items"] = []
            raw = float(result.get("score", 0) or 0)
            penalty = 0.0
            current_ticker = str(ticker).upper()
            for item in _PORTFOLIO["items"]:
                if item["ticker"] == current_ticker:
                    continue
                corr = abs(_corr(df, item["df"]))
                weight = min(1.0, max(0.0, item["score"] / 100.0))
                penalty = max(penalty, 8.0 * corr * weight)
            portfolio_score = max(0.0, min(100.0, raw - penalty))
            result = dict(result)
            result["raw_score"] = raw
            result["portfolio_score"] = portfolio_score
            result["correlation_penalty"] = penalty
            _SIGNAL_SCORES[current_ticker] = portfolio_score
            if result.get("comprar", False):
                result["score"] = portfolio_score
                _PORTFOLIO["items"].append({"ticker": current_ticker, "df": df, "score": raw})
                _PORTFOLIO["items"] = sorted(
                    _PORTFOLIO["items"], key=lambda x: x["score"], reverse=True
                )[:12]
            return result
        except Exception:
            return result

    strategy_module.analizar_impulso_crypto = portfolio_crypto
    _INSTALLED_STRATEGY = True


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    if name == "broker" or name.endswith(".broker"):
        try:
            _install_broker(module)
        except Exception:
            pass
    if name == "estrategia" or name.endswith(".estrategia"):
        try:
            _install_strategy(module)
        except Exception:
            pass
    return module

builtins.__import__ = _import
