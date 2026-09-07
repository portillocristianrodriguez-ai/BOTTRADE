import json
import unittest
from unittest.mock import patch

import requests
import dashboard
from dashboard_metrics import active_positions, stop_risk


class DashboardDataTests(unittest.TestCase):
    def position(self, symbol='NVDA', qty='10', value='1033', price='103.3'):
        return dict(symbol=symbol, qty=qty, market_value=value, current_price=price,
                    unrealized_pl='33', unrealized_plpc='.033')

    def stop(self, symbol='NVDA', qty='10', price='100', side='sell', **kwargs):
        return dict(symbol=symbol, qty=qty, stop_price=price, side=side,
                    type='stop', status='new', **kwargs)

    def test_zero_invalid_qty_removed_but_short_and_dust_preserved(self):
        rows = [self.position(qty=q) for q in ['0', '-0.0', 'NaN', 'inf', None, '-2', '0.00000000001']]
        self.assertEqual([p['qty'] for p in active_positions(rows)], ['-2', '0.00000000001'])

    def test_stop_loss_long_short_partial_and_missing(self):
        self.assertAlmostEqual(stop_risk([self.position()], [self.stop()])['max_loss_if_all_stops_hit'], 33)
        short = self.position('SHORT', '-2', '-200', '100')
        self.assertEqual(stop_risk([short], [self.stop('SHORT', '2', '110', 'buy')])['max_loss_if_all_stops_hit'], 20)
        partial = stop_risk([self.position()], [self.stop(qty='5')])
        self.assertIsNone(partial['max_loss_if_all_stops_hit'])
        self.assertAlmostEqual(partial['covered_stop_loss'], 16.5)
        self.assertIsNone(stop_risk([self.position()], [])['max_loss_if_all_stops_hit'])
        self.assertEqual(stop_risk([], [])['max_loss_if_all_stops_hit'], 0)

    def test_stop_nested_duplicates_canceled_and_overlap(self):
        leg = self.stop(id='s1')
        parent = dict(id='parent', legs=[leg])
        risk = stop_risk([self.position()], [parent, leg, self.stop(price='90')])
        self.assertAlmostEqual(risk['covered_stop_loss'], 133)
        canceled = self.stop(); canceled['status'] = 'canceled'
        self.assertIsNone(stop_risk([self.position()], [canceled])['max_loss_if_all_stops_hit'])
        self.assertIsNone(stop_risk([self.position()], [leg], complete=False)['max_loss_if_all_stops_hit'])

    def fake_api(self, path, params=None):
        if path == '/v2/account':
            return dict(equity='1000', cash='167', last_equity='900', long_market_value='1033', short_market_value='-200')
        if path == '/v2/positions':
            return [self.position(), self.position('SHORT', '-2', '-200', '100'), self.position('GHOST', '0', '99999')]
        if path == '/v2/orders':
            return [self.stop(id='stop')] if params['status'] == 'open' else [dict(status='filled', filled_qty='0')]
        if path == '/v2/account/activities/FILL':
            f = dict(id='fill1', order_id='o1', symbol='NVDA', side='buy', qty='2', price='100')
            return [f, f.copy(), dict(f, id='fill2', qty='3'), dict(f, id='zero', qty='0'), dict(f, id='bad', price='NaN')]
        if path == '/v2/clock':
            return dict(is_open=False)
        return dict(equity=[1000, 1010], timestamp=[1, 2])

    def test_state_reconciles_gross_net_nvda_and_execution_window(self):
        with patch.object(dashboard, 'alpaca_get', side_effect=self.fake_api):
            result = dashboard.state('1D')
        self.assertEqual(len(result['positions']), 2)
        self.assertEqual(result['risk']['invested'], 1233)
        self.assertEqual(result['risk']['net_exposure'], 833)
        self.assertEqual(result['risk']['position_value_delta'], 0)
        self.assertEqual(result['risk']['concentration'], 103.3)
        self.assertEqual(result['execution']['fills'], 2)
        self.assertEqual(result['execution']['filled_orders'], 1)
        self.assertEqual(result['execution']['buys'], 2)
        json.dumps(result, allow_nan=False)
        self.assertTrue(dashboard.PAPER)

    def test_missing_activity_is_unknown_not_zero(self):
        def unavailable(path, params=None):
            if path.endswith('/FILL'):
                raise requests.RequestException('offline')
            return self.fake_api(path, params)
        with patch.object(dashboard, 'alpaca_get', side_effect=unavailable):
            result = dashboard.state('1D')
        self.assertIsNone(result['execution']['fills'])
        self.assertIsNone(result['execution']['filled_orders'])
