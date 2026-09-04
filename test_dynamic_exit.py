import unittest

from dynamic_exit import evaluar_salida


class DynamicExitTests(unittest.TestCase):
    def test_hard_loss_negative_momentum_exits(self):
        decision = evaluar_salida(
            pnl_pct=-0.04,
            atr_pct=0.015,
            momentum_pct=-0.5,
            rsi=38,
            adx=25,
            regimen="bajista",
        )
        self.assertEqual(decision["action"], "exit")
        self.assertEqual(decision["reduce_fraction"], 1.0)

    def test_profitable_deterioration_reduces(self):
        decision = evaluar_salida(
            pnl_pct=0.03,
            atr_pct=0.015,
            momentum_pct=-0.3,
            rsi=39,
            adx=25,
            regimen="bajista",
            orderbook_imbalance=-0.4,
        )
        self.assertEqual(decision["action"], "reduce")
        self.assertEqual(decision["reduce_fraction"], 0.50)

    def test_profitable_bullish_position_tightens(self):
        decision = evaluar_salida(
            pnl_pct=0.02,
            atr_pct=0.015,
            momentum_pct=0.2,
            rsi=58,
            adx=28,
            regimen="alcista",
            breakout=True,
            trailing_stop_pct=0.015,
        )
        self.assertEqual(decision["action"], "tighten")
        self.assertGreaterEqual(decision["recommended_stop_pct"], 0.0025)
        self.assertLessEqual(decision["recommended_stop_pct"], 0.015)

    def test_healthy_position_holds(self):
        decision = evaluar_salida(
            pnl_pct=0.005,
            atr_pct=0.015,
            momentum_pct=0.1,
            rsi=55,
            adx=15,
            regimen="neutral",
        )
        self.assertEqual(decision["action"], "hold")


if __name__ == "__main__":
    unittest.main()
