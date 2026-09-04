"""Deterministic regression tests for BOTTRADE safety helpers.

These tests do not submit orders and do not require Alpaca credentials.
Run with: python -m unittest test_alpaca.py
"""

import unittest

import execution_guard
import execution_idempotency


class FakeOrder:
    def __init__(self, status="new", notional=None, qty=None, limit_price=None, side="buy"):
        self.status = status
        self.notional = notional
        self.qty = qty
        self.limit_price = limit_price
        self.side = side


class FakeClient:
    def __init__(self):
        self.orders = {}
        self.submit_calls = 0

    def get_order_by_client_id(self, client_order_id):
        return self.orders.get(client_order_id)

    def submit_order(self, order_data=None):
        self.submit_calls += 1
        order = FakeOrder(status="new")
        self.orders[order_data.client_order_id] = order
        return order


class SafetyTests(unittest.TestCase):
    def test_unknown_pending_market_buy_fails_closed(self):
        ok, reason = execution_guard.validar_exposicion_compra(
            equity=10000,
            proposed_notional=1000,
            positions=[],
            open_orders=[FakeOrder(status="new", qty=10, limit_price=None)],
            max_single_position_pct=0.20,
            max_total_exposure_pct=0.50,
        )
        self.assertFalse(ok)
        self.assertIn("notional", reason)

    def test_pending_limit_buy_counts_toward_exposure(self):
        ok, _ = execution_guard.validar_exposicion_compra(
            equity=10000,
            proposed_notional=1000,
            positions=[],
            open_orders=[FakeOrder(status="new", qty=20, limit_price=200)],
            max_single_position_pct=0.20,
            max_total_exposure_pct=0.50,
        )
        self.assertFalse(ok)

    def test_idempotent_submit_reconciles_existing_order(self):
        client = FakeClient()
        order_data = type("Order", (), {
            "symbol": "BTC/USD",
            "side": "buy",
            "qty": 0.01,
            "notional": None,
            "client_order_id": None,
        })()

        first = execution_idempotency.submit_order_idempotente(
            client, order_data, submit_callable=client.submit_order
        )
        second = execution_idempotency.submit_order_idempotente(
            client, order_data, submit_callable=client.submit_order
        )

        self.assertEqual(client.submit_calls, 1)
        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
