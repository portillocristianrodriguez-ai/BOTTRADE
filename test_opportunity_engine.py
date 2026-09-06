import unittest

from opportunity_engine import evaluate


class OpportunityEngineTests(unittest.TestCase):
    def test_bullish_high_quality_opportunity_is_eligible(self):
        result = evaluate(
            {"score": 82, "atr_pct": 0.02, "data_quality": 1.0},
            {"regimen": "alcista"},
            {"spread_pct": 0.10, "max_spread_pct": 0.90, "depth_ratio": 0.10},
            {"correlation": 0.10},
        )
        self.assertTrue(result["eligible"])
        self.assertFalse(result["blocked"])
        self.assertGreaterEqual(result["score"], 70)

    def test_bearish_regime_blocks_weak_signal(self):
        result = evaluate(
            {"score": 80, "atr_pct": 0.02},
            {"regimen": "bajista"},
        )
        self.assertTrue(result["blocked"])
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "hard_block")

    def test_execution_block_always_wins(self):
        result = evaluate(
            {"score": 99, "atr_pct": 0.01},
            {"regimen": "alcista"},
            {"blocked": True},
        )
        self.assertTrue(result["blocked"])
        self.assertFalse(result["eligible"])

    def test_missing_optional_execution_data_does_not_penalize(self):
        result = evaluate({"score": 75, "atr_pct": 0.02})
        self.assertFalse(result["blocked"])
        self.assertTrue(result["eligible"])

    def test_low_data_quality_reduces_score(self):
        clean = evaluate({"score": 80, "data_quality": 1.0})
        degraded = evaluate({"score": 80, "data_quality": 0.5})
        self.assertLess(degraded["score"], clean["score"])


if __name__ == "__main__":
    unittest.main()
