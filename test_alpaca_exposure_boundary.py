import unittest

from execution_guard import validar_exposicion_compra


class FakeOrder:
    status = "new"
    notional = None
    qty = 20
    limit_price = 200
    side = "buy"


class ExposureBoundaryTests(unittest.TestCase):
    def test_order_over_total_exposure_limit_is_rejected(self):
        ok, reason = validar_exposicion_compra(
            equity=10000,
            proposed_notional=1001,
            positions=[],
            open_orders=[FakeOrder()],
            max_single_position_pct=0.20,
            max_total_exposure_pct=0.50,
        )
        self.assertFalse(ok, reason)


if __name__ == "__main__":
    unittest.main()
