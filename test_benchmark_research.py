import unittest
import pandas as pd
import numpy as np
import estrategia
from benchmark_research import reference_signal,buy_hold


class BenchmarkResearchTests(unittest.TestCase):
    def test_cached_indicator_prefix_does_not_see_future_prices(self):
        close = 100 + np.sin(np.arange(250) / 7) + np.arange(250) / 100
        frame = pd.DataFrame({'open':close, 'high':close+1, 'low':close-1,
                              'close':close, 'volume':100+np.arange(250)},
                             index=pd.date_range('2026-01-01', periods=250, freq='5min', tz='UTC'))
        full = estrategia.calcular_indicadores(frame)
        for length in (80, 150, 200):
            pd.testing.assert_frame_equal(full.iloc[:length],
                                          estrategia.calcular_indicadores(frame.iloc[:length]))

    def test_flat_hold_loses_only_costs(self):
        frame=pd.DataFrame({'open':[100]*3,'close':[100]*3})
        result=buy_hold(frame,100000,.1,25,10)
        self.assertLess(result['net_pnl'],0)
        self.assertGreater(result['net_pnl'],-100)

    def test_references_need_history_and_use_known_prices(self):
        self.assertEqual(reference_signal('trend_20_50',pd.DataFrame({'close':[1]*10})),'ESPERAR')
        self.assertEqual(reference_signal('trend_20_50',pd.DataFrame({'close':range(1,61)})),'COMPRAR')
        self.assertEqual(reference_signal('mean_reversion_20_2pct',pd.DataFrame({'close':[100]*19+[90]})),'COMPRAR')
