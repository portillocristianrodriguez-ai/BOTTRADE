import math
import os
import tempfile
import unittest

from ai_investment_analyst import AnalystMemory, analyze_performance, apply_proposal, authorize_proposal, make_proposal


class TestAIInvestmentAnalyst(unittest.TestCase):
    def test_performance_metrics(self):
        trades = [
            {"symbol": "AAPL", "asset_type": "stock", "pnl": 100, "risk_amount": 50},
            {"symbol": "AAPL", "asset_type": "stock", "pnl": -50, "risk_amount": 50},
            {"symbol": "BTC/USD", "asset_type": "crypto", "pnl": 150, "risk_amount": 75},
        ]
        result = analyze_performance(trades, [10000, 10100, 10050, 10200])
        self.assertEqual(result["trades"], 3)
        self.assertAlmostEqual(result["win_rate"], 2 / 3)
        self.assertAlmostEqual(result["profit_factor"], 5.0)
        self.assertAlmostEqual(result["expectancy"], 200 / 3)
        self.assertAlmostEqual(result["max_drawdown"], -50 / 10100)
        self.assertAlmostEqual(result["average_r_multiple"], (2 - 1 + 2) / 3)
        self.assertEqual(result["by_asset"]["AAPL"]["trades"], 2)
        self.assertEqual(result["by_asset_type"]["crypto"]["trades"], 1)

    def test_empty_and_infinite_profit_factor(self):
        empty = analyze_performance()
        self.assertEqual(empty["trades"], 0)
        self.assertIsNone(empty["profit_factor"])
        winners = analyze_performance([{"symbol": "MSFT", "pnl": 10}])
        self.assertTrue(math.isinf(winners["profit_factor"]))

    def test_proposal_allowlist_and_permission(self):
        proposal = make_proposal(
            "Reducir riesgo tras drawdown",
            {"RISK_PER_TRADE_PCT": 0.01, "STOP_LOSS_PCT": 0.015},
            expected_impact="Menor pérdida por operación",
            validation={"validated": True},
        )
        with self.assertRaises(PermissionError):
            authorize_proposal(proposal, "sí")
        token = authorize_proposal(proposal, "APLICAR")
        applied = apply_proposal(proposal, token, {"RISK_PER_TRADE_PCT": 0.02, "STOP_LOSS_PCT": 0.02})
        self.assertEqual(applied["config"]["RISK_PER_TRADE_PCT"], 0.01)
        self.assertEqual(applied["rollback"]["STOP_LOSS_PCT"], 0.02)
        with self.assertRaises(ValueError):
            make_proposal("salir del perímetro", {"API_KEY": "leak"}, expected_impact="n/a")

    def test_memory_append_and_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "memory.jsonl")
            memory = AnalystMemory(path)
            memory.append("trade", {"symbol": "AAPL", "pnl": 10})
            memory.append("decision", {"reason": "drawdown"})
            self.assertEqual(len(memory.recent()), 2)
            self.assertEqual(memory.recent(kind="trade")[0]["payload"]["symbol"], "AAPL")
            self.assertEqual(memory.recent(limit=1)[0]["kind"], "decision")


if __name__ == "__main__":
    unittest.main()
