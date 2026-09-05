import unittest

from ai_adaptive_learning import learn
from ai_investment_analyst import make_proposal


class TestAdaptiveLearning(unittest.TestCase):
    def _trades(self, values, asset_type="stock"):
        return [{"symbol": "BTC/USD" if asset_type == "crypto" else "AAPL", "asset_type": asset_type, "pnl": value} for value in values]

    def test_no_proposal_with_small_sample(self):
        result = learn(self._trades([1, -1] * 10), {"trades": 20, "total_pnl": 0, "expectancy": 0, "max_drawdown": -0.10}, {"RISK_PER_TRADE_PCT": 0.02})
        self.assertIsNone(result["proposal"])

    def test_reduces_risk_on_recent_deterioration(self):
        values = [1.0] * 30
        values[-30:] = [-1.0] * 30
        result = learn(self._trades(values), {"trades": 30, "total_pnl": -30, "expectancy": -1, "max_drawdown": -0.10}, {"RISK_PER_TRADE_PCT": 0.02})
        self.assertIsNotNone(result["proposal"])
        self.assertEqual(result["proposal"]["changes"]["RISK_PER_TRADE_PCT"], 0.016)

    def test_positive_edge_only_allows_small_step(self):
        result = learn(self._trades([2.0] * 60), {"trades": 60, "total_pnl": 120, "expectancy": 2, "max_drawdown": 0}, {"RISK_PER_TRADE_PCT": 0.02})
        self.assertIsNotNone(result["proposal"])
        self.assertEqual(result["proposal"]["changes"]["RISK_PER_TRADE_PCT"], 0.022)
        self.assertIn("guardrail", result["proposal"]["validation"])

    def test_crypto_uses_crypto_risk_when_dominant(self):
        result = learn(self._trades([2.0] * 60, "crypto"), {"trades": 60, "total_pnl": 120, "expectancy": 2, "max_drawdown": 0}, {"RISK_PER_TRADE_PCT": 0.02, "CRYPTO_RISK_PER_TRADE_PCT": 0.01})
        self.assertEqual(result["proposal"]["changes"], {"CRYPTO_RISK_PER_TRADE_PCT": 0.011})

    def test_bounds_reject_unsafe_value(self):
        with self.assertRaises(ValueError):
            make_proposal("bad", {"RISK_PER_TRADE_PCT": 0.50}, expected_impact="none")


if __name__ == "__main__":
    unittest.main()
