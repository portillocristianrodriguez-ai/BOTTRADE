import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import pandas as pd
import config
import estrategia
import execution_guard
import opportunity_engine


class PretradeDataIntegrityTests(unittest.TestCase):
    def test_unknown_exposure_blocks_new_buy(self):
        ok,_=execution_guard.validar_exposicion_compra(equity=10000,proposed_notional=100,
            positions=[NS(qty=1,market_value='nan')],open_orders=[],max_single_position_pct=.2,max_total_exposure_pct=.5)
        self.assertFalse(ok)

    def test_nonfinite_config_rejected(self):
        for val in ['nan','inf','-inf']:
            with patch.dict('os.environ',{'SAMPLE_RISK':val}):
                with self.assertRaises(RuntimeError):config._float('SAMPLE_RISK',1)

    def test_old_volume_bar_cannot_generate_current_signal(self):
        frame=pd.DataFrame({'volume':[100,0,0,0,0]})
        self.assertIsNone(estrategia._obtener_indice_barra_crypto(frame))
        self.assertEqual(estrategia._obtener_indice_barra_crypto(frame.iloc[:3]),0)

    def test_failed_execution_gate_blocks_opportunity(self):
        self.assertFalse(opportunity_engine.evaluate({'score':100},execution={'ok':False})['eligible'])
        self.assertFalse(opportunity_engine.evaluate({'score':float('inf')})['eligible'])

    def test_bad_ohlc_returns_no_indicators(self):
        frame=pd.DataFrame({'open':[100]*250,'high':[90]*250,'low':[99]*250,'close':[100]*250,'volume':[10]*250})
        self.assertTrue(estrategia.calcular_indicadores(frame).empty)
