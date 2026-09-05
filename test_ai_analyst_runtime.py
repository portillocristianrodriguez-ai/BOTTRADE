import os
import tempfile
import unittest

from ai_analyst_runtime import AIAnalystRuntime, diagnose, portfolio_risk, propose_risk_reduction, read_overrides, simulate_risk_change


class TestAIAnalystRuntime(unittest.TestCase):
    def test_portfolio_risk_and_concentration(self):
        risk = portfolio_risk(
            [
                {"symbol": "AAPL", "market_value": 3000, "asset_type": "stock"},
                {"symbol": "BTC/USD", "market_value": 1000, "asset_type": "crypto"},
            ],
            10000,
        )
        self.assertEqual(risk["gross_exposure"], 4000)
        self.assertAlmostEqual(risk["gross_exposure_pct"], 0.4)
        self.assertEqual(risk["largest_position"]["symbol"], "AAPL")
        self.assertAlmostEqual(risk["largest_position"]["portfolio_pct"], 0.3)

    def test_diagnosis_is_conservative(self):
        findings = diagnose({"trades": 30, "profit_factor": 0.8, "expectancy": -2, "max_drawdown": -0.08, "win_rate": 0.35})
        codes = {item["code"] for item in findings}
        self.assertTrue({"NEGATIVE_EDGE", "NEGATIVE_EXPECTANCY", "DRAWDOWN", "LOW_WIN_RATE"}.issubset(codes))

    def test_risk_simulation_and_proposal(self):
        metrics = {"trades": 50, "total_pnl": -100, "expectancy": -2, "max_drawdown": -0.10}
        simulation = simulate_risk_change(metrics, 0.02, 0.01)
        self.assertEqual(simulation["risk_ratio"], 0.5)
        self.assertEqual(simulation["estimated_total_pnl"], -50)
        proposal = propose_risk_reduction(metrics, 0.02, target_risk_pct=0.01)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.changes["RISK_PER_TRADE_PCT"], 0.01)

    def test_runtime_persists_analysis_and_override_only_after_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = os.path.join(tmp, "memory.jsonl")
            overrides = os.path.join(tmp, "overrides.json")
            runtime = AIAnalystRuntime(memory, overrides)
            report = runtime.analyze(
                [{"symbol": "AAPL", "asset_type": "stock", "pnl": -10}],
                [10000, 9990],
                [{"symbol": "AAPL", "market_value": 3000, "asset_type": "stock"}],
            )
            self.assertIn("metrics", report)
            self.assertFalse(os.path.exists(overrides))
            self.assertEqual(read_overrides(overrides), {})


if __name__ == "__main__":
    unittest.main()
