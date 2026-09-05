import os
import tempfile
import types
import unittest

import ai_analyst_live as live
from ai_analyst_runtime import AIAnalystRuntime


class FakeBroker:
    def __init__(self):
        self.account = {"equity": 10000, "cash": 9000, "buying_power": 9000}
        self.positions = []

    def obtener_resumen_cuenta(self):
        return self.account

    def obtener_todas_las_posiciones(self):
        return self.positions


class TestAIAnalystLive(unittest.TestCase):
    def setUp(self):
        live._LOCK.acquire()
        try:
            live._LOTS.clear()
            live._FILLED_BY_ORDER.clear()
            live._PENDING.clear()
            live._RUNTIME = None
        finally:
            live._LOCK.release()

    def test_fifo_realized_trade_from_fills(self):
        with tempfile.TemporaryDirectory() as tmp:
            live._RUNTIME = AIAnalystRuntime(os.path.join(tmp, "memory.jsonl"), os.path.join(tmp, "overrides.json"))
            buy = types.SimpleNamespace(event="fill", price="100", order=types.SimpleNamespace(id="b1", symbol="AAPL", side="buy", filled_qty="2"))
            sell = types.SimpleNamespace(event="fill", price="110", order=types.SimpleNamespace(id="s1", symbol="AAPL", side="sell", filled_qty="2"))
            live.record_trade_update(buy)
            live.record_trade_update(sell)
            trades = live._RUNTIME.memory.recent(kind="trade")
            self.assertEqual(len(trades), 1)
            self.assertAlmostEqual(trades[0]["payload"]["pnl"], 20.0)
            self.assertEqual(trades[0]["payload"]["qty"], 2.0)

    def test_partial_fill_is_delta_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            live._RUNTIME = AIAnalystRuntime(os.path.join(tmp, "memory.jsonl"), os.path.join(tmp, "overrides.json"))
            p1 = types.SimpleNamespace(event="partial_fill", price="100", order=types.SimpleNamespace(id="b1", symbol="AAPL", side="buy", filled_qty="1"))
            p2 = types.SimpleNamespace(event="partial_fill", price="101", order=types.SimpleNamespace(id="b1", symbol="AAPL", side="buy", filled_qty="2"))
            live.record_trade_update(p1)
            live.record_trade_update(p2)
            fills = live._RUNTIME.memory.recent(kind="fill")
            self.assertEqual(len(fills), 2)
            self.assertAlmostEqual(fills[0]["payload"]["qty"], 1.0)
            self.assertAlmostEqual(fills[1]["payload"]["qty"], 1.0)
            self.assertEqual(sum(x["payload"]["qty"] for x in fills), 2.0)

    def test_analyze_now_persists_equity_and_open_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            live._RUNTIME = AIAnalystRuntime(os.path.join(tmp, "memory.jsonl"), os.path.join(tmp, "overrides.json"))
            broker = FakeBroker()
            broker.positions = [types.SimpleNamespace(symbol="AAPL", qty="10", current_price="200", market_value="2000")]
            report = live.analyze_now(broker)
            self.assertEqual(report["metrics"]["trades"], 0)
            self.assertAlmostEqual(report["risk"]["gross_exposure_pct"], 0.2)
            self.assertEqual(len(live._RUNTIME.memory.recent(kind="equity_snapshot")), 1)

    def test_command_requires_existing_pending_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            live._RUNTIME = AIAnalystRuntime(os.path.join(tmp, "memory.jsonl"), os.path.join(tmp, "overrides.json"))
            response = live.command("/ia aplicar missing", FakeBroker())
            self.assertIn("inexistente", response)


if __name__ == "__main__":
    unittest.main()
