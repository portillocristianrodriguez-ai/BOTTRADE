import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import nvda_take_profit_once as change


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return copy.deepcopy(self.data)


class PaperAPI:
    def __init__(self):
        self.calls = []
        self.position = {'symbol': 'NVDA', 'side': 'long', 'qty': '443'}
        self.stop = dict(id='stop', symbol='NVDA', side='sell', type='stop',
                         status='held', qty='443', filled_qty='0',
                         created_at='2026-09-07T10:00:00Z', stop_price='228.99')
        self.tp = dict(id='tp', symbol='NVDA', side='sell', type='limit',
                       status='new', qty='443', filled_qty='0', order_class='oco',
                       created_at='2026-09-07T10:00:00Z', limit_price='243.01',
                       time_in_force='gtc', legs=[self.stop])
        self.patch_error = False
        self.stop_changed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not url.startswith(change.BASE_URL):
            raise AssertionError('Non-PAPER host')
        if method == 'PATCH':
            if self.patch_error:
                raise TimeoutError('uncertain response')
            self.replacement = dict(self.tp, id='replacement', replaces='tp',
                                    limit_price='231.75')
            return Response(self.replacement)
        if url.endswith('/positions/NVDA'):
            return Response(self.position)
        if url.endswith('/orders'):
            return Response([self.tp])
        if url.endswith('/orders/tp'):
            return Response(self.tp)
        if url.endswith('/orders/replacement'):
            return Response(self.replacement)
        if url.endswith('/orders/stop'):
            return Response(dict(self.stop, stop_price='220')
                            if self.stop_changed else self.stop)
        raise AssertionError('Unexpected request')


class NVDAOneTimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = patch.dict(os.environ, {
            'RAILWAY_SERVICE_ID': change.SERVICE_ID,
            'RAILWAY_ENVIRONMENT_ID': change.ENVIRONMENT_ID,
            'ALPACA_PAPER': 'true', 'ALPACA_API_KEY': 'fake',
            'ALPACA_API_SECRET': 'fake'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.api = PaperAPI()
        self.now = change.REQUESTED_AT + timedelta(minutes=1)

    def run_change(self):
        change.apply_once(self.folder.name, self.api, self.now, wait=lambda _: None)

    def marker(self):
        return json.loads(Path(self.folder.name, change.MARKER).read_text())

    def mutations(self):
        return [x for x in self.api.calls if x[0] != 'GET']

    def test_changes_only_price_of_original_order_and_preserves_stop(self):
        self.run_change()
        mutation, = self.mutations()
        self.assertEqual(mutation[0], 'PATCH')
        self.assertTrue(mutation[1].endswith('/orders/tp'))
        self.assertEqual(mutation[2]['json'], {'limit_price': '231.75'})
        self.assertFalse(mutation[2]['allow_redirects'])
        self.assertEqual(self.marker()['status'], 'verified')
        self.assertEqual(self.marker()['stop_price'], '228.99')

    def test_restart_does_not_change_future_position(self):
        self.run_change()
        count = len(self.api.calls)
        self.api.tp['id'] = 'future-entry'
        self.run_change()
        self.assertEqual(len(self.api.calls), count)
        self.assertEqual(len(self.mutations()), 1)

    def test_timeout_is_never_retried(self):
        self.api.patch_error = True
        self.run_change()
        self.run_change()
        self.assertEqual(len(self.mutations()), 1)
        self.assertEqual(self.marker()['status'], 'needs_review')

    def test_live_wrong_service_and_missing_paper_are_inert(self):
        for variable, value in [('ALPACA_PAPER', 'false'),
                                ('ALPACA_PAPER', ''),
                                ('RAILWAY_SERVICE_ID', 'other'),
                                ('RAILWAY_ENVIRONMENT_ID', 'other')]:
            with self.subTest(variable=variable, value=value):
                with patch.dict(os.environ, {variable: value}):
                    self.run_change()
                self.assertEqual(self.api.calls, [])

    def test_expired_request_cannot_target_later_holdings(self):
        self.now = change.EXPIRES_AT
        self.run_change()
        self.assertEqual(self.api.calls, [])

    def test_new_order_after_request_is_ineligible(self):
        self.api.tp['created_at'] = self.now.isoformat()
        self.run_change()
        self.assertEqual(self.mutations(), [])

    def test_wrong_symbol_short_partial_and_mismatched_quantity_are_ineligible(self):
        for obj, field, value in [
            ('position', 'symbol', 'AAPL'), ('position', 'side', 'short'),
            ('position', 'qty', '442'), ('tp', 'filled_qty', '1'),
            ('tp', 'status', 'pending_replace'), ('tp', 'replaced_by', 'new-id'),
            ('stop', 'stop_price', '232'), ('stop', 'qty', '1'),
            ('tp', 'symbol', 'MSFT'), ('tp', 'order_class', 'simple'),
        ]:
            with self.subTest(obj=obj, field=field, value=value):
                self.api = PaperAPI()
                getattr(self.api, obj)[field] = value
                self.run_change()
                self.assertEqual(self.mutations(), [])

    def test_stop_verification_failure_does_not_claim_success_or_retry(self):
        self.api.stop_changed = True
        self.run_change()
        self.assertEqual(self.marker()['status'], 'needs_review')
        self.run_change()
        self.assertEqual(len(self.mutations()), 1)

    def test_already_at_target_makes_no_mutation(self):
        self.api.tp['limit_price'] = '231.75'
        self.run_change()
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.marker()['status'], 'already_at_target')

    def test_multiple_orders_rejected(self):
        with self.assertRaises(ValueError):
            change.validate(self.api.position, [self.api.tp, self.api.tp])


if __name__ == '__main__':
    unittest.main()
