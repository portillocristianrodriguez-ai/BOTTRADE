import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import execution_costs
import execution_quality
import sitecustomize


class ExecutionCostsTests(unittest.TestCase):
    def evaluate(self,**kwargs):
        inputs=dict(target_fraction=.04,stop_fraction=.02,fee_bps=25,
                    entry_impact_pct=.05,exit_impact_pct=.10)
        inputs.update(kwargs)
        return execution_costs.planned_trade_economics(**inputs)

    def test_liquid_plan_passes_but_expensive_plan_is_blocked(self):
        self.assertTrue(self.evaluate()['ok'])
        expensive=self.evaluate(entry_impact_pct=.45,exit_impact_pct=.45)
        self.assertFalse(expensive['ok'])
        self.assertLess(expensive['net_reward_risk'],1)

    def test_fees_are_applied_on_both_sides(self):
        result=self.evaluate(entry_impact_pct=0,exit_impact_pct=0)
        self.assertAlmostEqual(result['net_target_pct'],(1.04*.9975/1.0025-1)*100)

    def test_invalid_costs_never_authorize_entry(self):
        for value in (None,float('nan'),float('inf'),-1):
            self.assertFalse(self.evaluate(fee_bps=value)['ok'])

    def test_cost_gate_reaches_actual_broker_notional_path(self):
        broker=NS(es_cripto=lambda _:True,normalizar_ticker_crypto=lambda x:x,
                  cliente_datos_crypto=object(),log=Mock())
        quality=dict(ok=True,estimated_impact_pct=.45,recommended_notional=1000,reason='ok')
        with patch.object(execution_quality,'evaluate_crypto_orderbook',return_value=quality):
            qty,reason=sitecustomize._execution_quality_notional(broker,'BTC/USD',1000)
        self.assertEqual(qty,0)
        self.assertEqual(reason,'costs_exceed_reward_risk_budget')
