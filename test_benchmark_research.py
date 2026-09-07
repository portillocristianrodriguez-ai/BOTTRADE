import unittest
import pandas as pd
import numpy as np
import estrategia
import tempfile
import hashlib
import json
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from benchmark_research import reference_signal,buy_hold


class BenchmarkResearchTests(unittest.TestCase):
    def test_offline_crypto_never_uses_live_portfolio_wrapper(self):
        from benchmark_research import compare
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            frame=pd.DataFrame({key:[100.0]*100 for key in ['open','high','low','close','volume']},
                index=pd.date_range('2026-01-01',periods=100,freq='5min',tz='UTC'))
            frame.to_csv(root/'BTC.csv',index_label='timestamp')
            manifest={'end_exclusive':'2026-01-02T00:00:00Z','files':{'BTC.csv':{
                'symbol':'BTC/USD','sha256':hashlib.sha256((root/'BTC.csv').read_bytes()).hexdigest()}}}
            (root/'manifest.json').write_text(json.dumps(manifest))
            with patch.object(estrategia,'analizar_impulso_crypto') as live, \
                 patch.object(estrategia,'_analizar_impulso',return_value={'comprar':False}) as pure, \
                 redirect_stdout(io.StringIO()):
                result=compare(root,root/'result.json',windows=1,strategy_names=['bottrade_signal'])
            live.assert_not_called()
            self.assertGreater(pure.call_count,0)
            self.assertEqual(result['status'],'complete')

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
