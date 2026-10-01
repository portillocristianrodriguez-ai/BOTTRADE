import unittest
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from alpaca.trading.enums import OrderClass, OrderSide, OrderStatus, OrderType
import dynamic_exit_manager_v2 as exits
import execution_idempotency

import review_safety_hardening as fix


def order(**overrides):
    values = dict(id="old-buy", symbol="SOL/USD", side=OrderSide.BUY,
                  type=OrderType.MARKET, order_class=OrderClass.SIMPLE,
                  status=OrderStatus.NEW, filled_qty="0",
                  created_at=datetime.now(timezone.utc) - timedelta(hours=1))
    values.update(overrides)
    return NS(**values)


def broker(orders=()):
    result = NS(
        obtener_ordenes_abiertas=Mock(return_value=list(orders)),
        obtener_ordenes_ticker=Mock(return_value=list(orders)),
        ticker_comparacion=lambda ticker: ticker.replace("/", "").upper(),
        es_cripto=lambda ticker: True,
        normalizar_ticker_crypto=lambda ticker: ticker,
        obtener_posicion=lambda ticker: NS(qty="10"),
        tiene_posicion_abierta=lambda ticker: True,
        _normalizar_qty_crypto=lambda ticker, qty: float(qty),
        cliente_trading=Mock(), vender=Mock(return_value="sold"),
    )
    result.obtener_ordenes_ticker._review_active_orders = False
    result.vender._review_sell_guard = False
    return result


def install(b, paper=False):
    bot = NS(broker=b, config=NS(PAPER=paper, DYNAMIC_EXIT_COOLDOWN_SECONDS=90))
    fix.instalar(bot, exits)
    return bot


class ReviewSafetyHardeningTests(unittest.TestCase):
    def test_cooldown_registry_no_borra_timestamp_con_pop(self):
        registry = fix._CooldownRegistry({"SOL/USD": 123.0})
        self.assertEqual(registry.pop("SOL/USD", None), 123.0)
        self.assertEqual(registry.get("SOL/USD"), 123.0)

    def test_held_es_estado_activo(self):
        order = type("Order", (), {"status": "held"})()
        self.assertTrue(fix._status_activo(order))

    def test_filled_no_es_estado_activo(self):
        order = type("Order", (), {"status": "filled"})()
        self.assertFalse(fix._status_activo(order))

    def test_sdk_and_serialized_statuses(self):
        for status in (OrderStatus.HELD, "OrderStatus.HELD", "pending_cancel", "pending_replace"):
            self.assertTrue(fix._status_activo(order(status=status)))
        for status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self.assertFalse(fix._status_activo(order(status=status)))

    def test_cooldown_blocks_repeat_after_success_cleanup_and_allows_expiry(self):
        b = broker(); original = b.vender
        with patch.object(exits, "_LAST_ACTION", {}), patch.object(exits, "_TIGHTENED_TRAIL", {}):
            bot = install(b)
            with patch.object(exits.time, "time", return_value=1000):
                self.assertTrue(exits._ejecutar_exit_si_corresponde(bot, b, "SOL/USD", None, "test"))
                exits.limpiar_trailing("SOL/USD")
                self.assertFalse(exits._ejecutar_exit_si_corresponde(bot, b, "SOL/USD", None, "test"))
            with patch.object(exits.time, "time", return_value=1090):
                self.assertTrue(exits._ejecutar_exit_si_corresponde(bot, b, "SOL/USD", None, "test"))
        self.assertEqual(original.call_count, 2)

    def test_full_and_partial_sell_block_active_orders(self):
        for status in (OrderStatus.HELD, OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED, OrderStatus.PENDING_CANCEL):
            with self.subTest(status=status):
                b = broker([order(side=OrderSide.SELL, status=status, symbol="SOLUSD")])
                original = b.vender; install(b)
                self.assertIsNone(b.vender("SOL/USD"))
                with patch.object(execution_idempotency, "submit_order_idempotente") as submit:
                    self.assertIsNone(exits._partial_sell(b, "SOL/USD", .5))
                    submit.assert_not_called()
                original.assert_not_called()

    def test_query_failure_does_not_fall_back_or_sell(self):
        b = broker(); original = b.vender; fallback = b.obtener_ordenes_ticker
        b.obtener_ordenes_abiertas.side_effect = TimeoutError("offline")
        install(b)
        self.assertIsNone(b.vender("SOL/USD"))
        with patch.object(execution_idempotency, "submit_order_idempotente") as submit:
            with self.assertRaises(TimeoutError):
                exits._partial_sell(b, "SOL/USD", .5)
            submit.assert_not_called()
        original.assert_not_called(); fallback.assert_not_called()
        b.obtener_ordenes_abiertas.assert_called_with(strict=True)

    def test_closed_sell_and_other_symbol_do_not_block(self):
        b = broker([order(side=OrderSide.SELL, status=OrderStatus.FILLED),
                    order(side=OrderSide.SELL, symbol="BTC/USD")])
        original = b.vender; install(b)
        self.assertEqual(b.vender("SOL/USD"), "sold")
        original.assert_called_once()
        with patch.object(execution_idempotency, "submit_order_idempotente", return_value="partial") as submit:
            self.assertEqual(exits._partial_sell(b, "SOL/USD", .5), "partial")
            self.assertEqual(submit.call_args.args[1].qty, 5)

    def test_concurrent_full_and_partial_sell_submit_only_once(self):
        orders = []; b = broker()
        b.obtener_ordenes_abiertas.side_effect = lambda **kwargs: list(orders)
        def sent(*args, **kwargs):
            orders.append(order(side=OrderSide.SELL, status=OrderStatus.HELD))
            return "sent"
        b.vender.side_effect = sent
        install(b)
        with patch.object(execution_idempotency, "submit_order_idempotente", side_effect=sent):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(b.vender, "SOL/USD"),
                           pool.submit(exits._partial_sell, b, "SOL/USD", .5)]
                results = [f.result() for f in futures]
        self.assertEqual(results.count("sent"), 1)
        self.assertEqual(len(orders), 1)

    def test_install_twice_does_not_wrap_sell_twice(self):
        b = broker(); install(b); first = b.vender
        install(b)
        self.assertIs(b.vender, first)

    def test_paper_cancels_only_old_unfilled_simple_market_buy(self):
        protected = [order(id="protected", **kw) for kw in (
            {"side": OrderSide.SELL}, {"type": OrderType.LIMIT}, {"type": OrderType.STOP},
            {"order_class": OrderClass.BRACKET}, {"order_class": OrderClass.OCO},
            {"order_class": OrderClass.OTO}, {"order_class": None},
            {"filled_qty": "1"}, {"filled_qty": "nan"}, {"filled_qty": "inf"},
            {"filled_qty": "-1"}, {"filled_qty": None}, {"filled_qty": "invalid"},
            {"created_at": None}, {"created_at": "invalid"},
            {"created_at": datetime.now(timezone.utc)}, {"status": OrderStatus.FILLED},
        )]
        b = broker(protected + [order()]); install(b, paper=True)
        b.cliente_trading.cancel_order_by_id.assert_called_once_with("old-buy")

    def test_live_or_ambiguous_paper_flag_never_cancels(self):
        for paper in (False, None, "false", "true", 1):
            b = broker([order()]); install(b, paper=paper)
            b.cliente_trading.cancel_order_by_id.assert_not_called()

    def test_cancel_failure_does_not_stop_other_eligible_orders(self):
        b = broker([order(id="first"), order(id="second")])
        b.cliente_trading.cancel_order_by_id.side_effect = [TimeoutError(), None]
        install(b, paper=True)
        self.assertEqual(b.cliente_trading.cancel_order_by_id.call_count, 2)

    def test_real_open_order_reader_propagates_strict_query_errors(self):
        # Execute the actual reader without constructing authenticated clients.
        tree = ast.parse(Path(__file__).with_name("broker.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "obtener_ordenes_abiertas")
        client = Mock(); client.get_orders.side_effect = TimeoutError("offline")
        scope = dict(cliente_trading=client, log=Mock(),
                     GetOrdersRequest=lambda **kw: NS(**kw), QueryOrderStatus=NS(OPEN="open"))
        exec(compile(ast.Module(body=[function], type_ignores=[]), "broker.py", "exec"), scope)
        reader = scope[function.name]
        with self.assertRaises(TimeoutError): reader(strict=True)
        self.assertEqual(reader(), [])


if __name__ == "__main__":
    unittest.main()
