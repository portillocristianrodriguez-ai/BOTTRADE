"""Compatibility hardening layer for BOTTRADE.

Applies scoped safeguards to the existing broker/strategy modules until the
same controls are moved directly into broker.py. It must never enable live
trading or bypass the broker's own checks.
"""
from __future__ import annotations

import builtins
import math
import time

_INSTALLED_BROKER = False
_INSTALLED_STRATEGY = False
_ORIGINAL_IMPORT = builtins.__import__
_PORTFOLIO = {"bucket": None, "items": []}
_REGIME_CACHE = {"ts": 0.0, "data": None}


def _disable_secondary_account(broker_module):
    """Keep the secondary account strictly read-only/inactive for execution."""
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


def _execution_quality_notional(broker_module, ticker, proposed):
    """Return a smaller crypto notional when the book is thin; never enlarge it."""
    try:
        import config
        import execution_quality
        if not bool(getattr(config, "CRYPTO_EXECUTION_QUALITY_ENABLED", True)):
            return proposed, "disabled"
        if not broker_module.es_cripto(ticker) or proposed <= 0:
            return proposed, "not_applicable"
        quality = execution_quality.evaluate_crypto_orderbook(
            getattr(broker_module, "cliente_datos_crypto", None),
            broker_module.normalizar_ticker_crypto(ticker),
            proposed_notional=proposed,
            max_spread_pct=float(getattr(config, "CRYPTO_MAX_SPREAD_PCT", 0.90)),
            min_top_depth_usd=float(getattr(config, "CRYPTO_MIN_TOP_BOOK_NOTIONAL_USD", 1500.0)),
            max_depth_ratio=float(getattr(config, "CRYPTO_MAX_TOP_BOOK_ORDER_RATIO", 0.60)),
            min_execution_notional_usd=float(getattr(config, "CRYPTO_MIN_EXECUTION_NOTIONAL_USD", 25.0)),
        )
        broker_module.log.info(
            f"[EXEC] {ticker}: spread={quality.get('spread_pct')}% "
            f"top_depth=${quality.get('top_ask_depth_usd')} "
            f"ratio={quality.get('depth_ratio')} "
            f"impact={quality.get('estimated_impact_pct')} "
            f"reason={quality.get('reason')}"
        )
        if not quality.get("ok", True):
            return 0.0, str(quality.get("reason", "blocked"))
        recommended = float(quality.get("recommended_notional", proposed) or proposed)
        recommended = max(0.0, min(proposed, recommended))
        return recommended, str(quality.get("reason", "ok"))
    except Exception as exc:
        broker_module.log.warning(f"[EXEC] {ticker}: control de calidad no disponible: {exc}")
        return proposed, "unavailable"


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
        """Ajusta tamaño por volatilidad y, en crypto, por liquidez real."""
        qty = size_original(ticker, precio, atr)
        try:
            import config
            precio = float(precio)
            atr = float(atr)
            if qty <= 0 or precio <= 0 or atr <= 0:
                return qty

            atr_pct = atr / precio
            objetivo = float(getattr(
                config,
                "CRYPTO_TARGET_ATR_PCT" if broker_module.es_cripto(ticker) else "STOCK_TARGET_ATR_PCT",
                0.020 if broker_module.es_cripto(ticker) else 0.015,
            ))
            minimo = min(1.0, max(0.10, float(getattr(config, "DYNAMIC_RISK_MIN_MULTIPLIER", 0.60))))
            maximo = max(1.0, min(1.50, float(getattr(config, "DYNAMIC_RISK_MAX_MULTIPLIER", 1.15))))
            objetivo = max(0.0001, objetivo)
            factor = min(maximo, max(minimo, objetivo / atr_pct))
            ajustada = float(qty) * factor

            if broker_module.es_cripto(ticker):
                # Liquidity adjustment is applied before the final risk check.
                propuesta = ajustada * precio
                recomendada, razon = _execution_quality_notional(broker_module, ticker, propuesta)
                if recomendada <= 0:
                    return 0
                if recomendada < propuesta:
                    ajustada = recomendada / precio
                    razon_txt = f" liquidez={razon}"
                else:
                    razon_txt = ""
                ajustada = round(ajustada, 6)
            else:
                ajustada = int(ajustada)
                razon_txt = ""

            if ajustada <= 0:
                return 0
            if abs(factor - 1.0) >= 0.02 or razon_txt:
                broker_module.log.info(
                    f"[SIZING] {ticker}: ATR%={atr_pct:.4%} objetivo={objetivo:.4%} "
                    f"factor={factor:.3f} qty={qty}->{ajustada}{razon_txt}"
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

            equity = float(getattr(client.get_account(), "equity", 0) or 0)
            buying_power = float(getattr(client.get_account(), "buying_power", 0) or 0)
            proposed = float(qty) * float(price)
            if equity <= 0 or buying_power <= 0 or proposed <= 0 or not math.isfinite(proposed):
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
                # The quality module may reduce the size in dynamic_size. The
                # final check only hard-blocks a genuinely bad market, rather
                # than rejecting a valid reduced order.
                if bool(getattr(config, "CRYPTO_EXECUTION_QUALITY_ENABLED", True)):
                    recommended, reason = _execution_quality_notional(broker_module, ticker, proposed)
                    if recommended <= 0:
                        broker_module.log.warning(f"[EXEC] {ticker}: entrada bloqueada: {reason}")
                        return False
                    if recommended < proposed * 0.98:
                        broker_module.log.warning(
                            f"[EXEC] {ticker}: sizing no coincide con profundidad; "
                            f"propuesto=${proposed:.2f}, recomendado=${recommended:.2f}"
                        )
                        return False

            positions = client.get_all_positions()
            open_orders = client.get_orders(
                filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500, nested=True)
            )
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
        import execution_idempotency
        return execution_idempotency.submit_order_idempotente(
            client,
            order_data,
            submit_callable=submit,
        )

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


def _clamp(value, low, high):
    return min(high, max(low, value))


def _obtener_regimen_global(broker_module):
    now = time.time()
    if _REGIME_CACHE["data"] is not None and now - _REGIME_CACHE["ts"] < 180:
        return _REGIME_CACHE["data"]
    try:
        import market_regime
        datos = broker_module.obtener_datos_crypto_lote(["BTC/USD"], dias=3)
        btc = datos.get("BTC/USD") or datos.get("BTCUSD")
        regime = market_regime.evaluar_regimen_btc(btc)
        _REGIME_CACHE["ts"] = now
        _REGIME_CACHE["data"] = regime
        broker_module.log.info(
            f"[REGIMEN] BTC={regime.get('regimen')} score={regime.get('score', 50):.1f} "
            f"confidence={regime.get('confidence', 0):.2f}"
        )
        return regime
    except Exception as exc:
        broker_module.log.warning(f"[REGIMEN] no disponible; se usa neutral: {exc}")
        return {"regimen": "neutral", "score": 50.0, "confidence": 0.0}


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
            raw = _clamp(float(result.get("score", 0) or 0), 0.0, 100.0)
            momentum = max(0.0, float(result.get("momentum_pct", 0) or 0))
            volume_ratio = max(0.0, float(result.get("volumen_ratio", 1) or 1))
            atr_pct = max(0.0, float(result.get("atr_pct", 0) or 0))
            breakout = bool(result.get("breakout", False))
            quality_bonus = _clamp(momentum, 0.0, 4.0) * 1.25
            quality_bonus += _clamp(volume_ratio - 1.0, 0.0, 3.0)
            quality_bonus += 2.5 if breakout else 0.0
            volatility_penalty = max(0.0, atr_pct - 0.06) * 35.0
            correlation_penalty = 0.0
            current_ticker = str(ticker).upper()
            for item in _PORTFOLIO["items"]:
                if item["ticker"] == current_ticker:
                    continue
                corr = abs(_corr(df, item["df"]))
                weight = _clamp(item["score"] / 100.0, 0.0, 1.0)
                correlation_penalty += 10.0 * corr * weight
            correlation_penalty = _clamp(correlation_penalty, 0.0, 20.0)
            broker_module = __import__("broker")
            regime = _obtener_regimen_global(broker_module)
            regime_name = str(regime.get("regimen", "neutral"))
            regime_score = float(regime.get("score", 50.0) or 50.0)
            regime_adjustment = {
                "alcista": 6.0,
                "transicion_alcista": 2.0,
                "neutral": 0.0,
                "transicion_bajista": -6.0,
                "bajista": -14.0,
            }.get(regime_name, 0.0)
            portfolio_score = _clamp(
                raw + quality_bonus - volatility_penalty - correlation_penalty + regime_adjustment,
                0.0,
                100.0,
            )
            result = dict(result)
            result["raw_score"] = raw
            result["quality_bonus"] = quality_bonus
            result["volatility_penalty"] = volatility_penalty
            result["portfolio_score"] = portfolio_score
            result["correlation_penalty"] = correlation_penalty
            result["market_regime"] = regime_name
            result["market_regime_score"] = regime_score
            result["market_regime_adjustment"] = regime_adjustment
            hard_block_bear = regime_name == "bajista" and raw < 84.0
            if hard_block_bear:
                result["comprar"] = False
                result.setdefault("motivo", []).append("BTC en régimen bajista")
            result["score"] = portfolio_score
            if result.get("comprar", False):
                _PORTFOLIO["items"].append({"ticker": current_ticker, "df": df, "score": portfolio_score})
                _PORTFOLIO["items"] = sorted(_PORTFOLIO["items"], key=lambda x: x["score"], reverse=True)[:12]
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
