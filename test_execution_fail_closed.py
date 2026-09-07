from datetime import datetime,timezone,timedelta
from types import SimpleNamespace as NS
import unittest
from execution_quality import evaluate_crypto_orderbook


class ExecutionFailClosedTests(unittest.TestCase):
    def evaluate(self, book):
        return evaluate_crypto_orderbook(NS(get_crypto_latest_orderbook=lambda request:{'BTC/USD':book}),'BTC/USD',100)

    def book(self, **kw):
        return dict(timestamp=datetime.now(timezone.utc),asks=[{'price':100.1,'size':100}],bids=[{'price':99.9,'size':100}],**kw)

    def test_missing_and_stale_book(self):
        self.assertFalse(self.evaluate(None)['ok'])
        b=self.book();b['timestamp']=datetime.now(timezone.utc)-timedelta(minutes=10)
        self.assertEqual(self.evaluate(b)['reason'],'stale_orderbook')
        del b['timestamp'];self.assertFalse(self.evaluate(b)['ok'])

    def test_invalid_and_crossed_book(self):
        b=self.book();b['asks'][0]['size']=float('nan');self.assertFalse(self.evaluate(b)['ok'])
        b=self.book();b['bids'][0]['price']=102;self.assertFalse(self.evaluate(b)['ok'])

    def test_sorted_book_and_finite_recommendation(self):
        b=self.book();b['asks'].insert(0,{'price':105,'size':100})
        r=self.evaluate(b);self.assertTrue(r['ok']);self.assertGreater(r['recommended_notional'],0)

    def test_network_failure_blocks(self):
        def fail(_):raise TimeoutError()
        self.assertFalse(evaluate_crypto_orderbook(NS(get_crypto_latest_orderbook=fail),'BTC/USD',100)['ok'])
