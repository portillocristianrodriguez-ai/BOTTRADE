import unittest

from strategy_lab import evaluate_candidate, rank_candidates


class StrategyLabTests(unittest.TestCase):
    def test_eligible_candidate_requires_review_not_auto_apply(self):
        gate = evaluate_candidate({
            "trades": 80,
            "windows": 4,
            "consistency_pct": 75,
            "profit_factor": 1.45,
            "score": 28,
            "worst_drawdown_pct": -12,
            "oos_degradation_pct": 20,
        })
        self.assertTrue(gate.eligible)
        self.assertEqual(gate.action, "REVIEW")

    def test_missing_evidence_does_not_promote(self):
        gate = evaluate_candidate({"trades": 100, "windows": 4, "score": 30})
        self.assertFalse(gate.eligible)
        self.assertEqual(gate.action, "HOLD")
        self.assertTrue(any("consistencia" in reason for reason in gate.reasons))

    def test_bad_drawdown_blocks_candidate(self):
        gate = evaluate_candidate({
            "trades": 100,
            "windows": 4,
            "consistency_pct": 80,
            "profit_factor": 1.5,
            "score": 35,
            "worst_drawdown_pct": -40,
            "oos_degradation_pct": 10,
        })
        self.assertFalse(gate.eligible)
        self.assertTrue(any("drawdown" in reason for reason in gate.reasons))

    def test_ranking_puts_eligible_candidates_first(self):
        ranked = rank_candidates([
            {"name": "weak", "trades": 20, "windows": 2, "score": 50},
            {"name": "strong", "trades": 60, "windows": 3, "consistency_pct": 70,
             "profit_factor": 1.3, "score": 20, "worst_drawdown_pct": -10,
             "oos_degradation_pct": 15},
        ])
        self.assertEqual(ranked[0]["name"], "strong")
        self.assertEqual(ranked[0]["promotion_gate"]["action"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
