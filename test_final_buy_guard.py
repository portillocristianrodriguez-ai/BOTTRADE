import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from unittest.mock import patch,Mock
import config
import execution_guard as guard
import execution_idempotency as execution


class Client:
    def __init__(self):
        self.positions=[]; self.orders=[]; self.sent=[]
    def get_order_by_client_id(self, value):
        return next((x for x in self.orders if x.client_order_id==value),None)
    def get_account(self):
        return NS(equity='10000',buying_power='10000')
    def get_all_positions(self): return self.positions
    def get_orders(self,filter=None): return self.orders
    def get_asset(self,symbol):
        return NS(min_order_size='0.000000001',min_trade_increment='0.000000001')
    def submit_order(self,order_data=None):
        time.sleep(.02)  # exercise overlap between portfolio check and submit
        order=NS(**vars(order_data),status='new',notional=order_data.qty*100)
        self.sent.append(order); self.orders.append(order)
        return order


def order(symbol='AAPL',qty=100,side='buy'):
    return NS(symbol=symbol,qty=qty,side=side,client_order_id=None)


class QuoteSourceTests(unittest.TestCase):
    def test_missing_ask_is_not_replaced_with_last_trade(self):
        client=Mock()
        client.get_crypto_latest_quote.return_value={'BTC/USD':NS(ask_price=0,timestamp=None)}
        with patch('alpaca.data.historical.CryptoHistoricalDataClient',return_value=client):
            price,reason=execution._latest_buy_price(None,'BTC/USD')
        self.assertIsNone(price)
        self.assertEqual(reason,'no_valid_price')
        client.get_crypto_latest_trade.assert_not_called()


class FinalBuyGuardTests(unittest.TestCase):
    def setUp(self):
        self.quote=patch.object(execution,'_latest_buy_price',return_value=(100.,'ok'))
        self.quote.start();self.addCleanup(self.quote.stop)

    def test_gap_reprices_stock_under_single_position_cap(self):
        result=execution._refresh_buy_quantity(Client(),order(qty=100))
        self.assertEqual(result.qty,20)

    def test_new_exposure_blocks_at_final_check_without_touching_holdings(self):
        c=Client();c.positions=[NS(symbol='NVDA',qty=443,market_value=102049.48)]
        with self.assertRaises(ValueError): execution.submit_order_idempotente(c,order())
        self.assertEqual(c.positions[0].qty,443);self.assertFalse(c.sent)

    def test_invalid_buy_and_pending_values_fail_closed(self):
        for value in (float('nan'),float('inf'),-1):
            with self.assertRaises(ValueError): execution._refresh_buy_quantity(Client(),order(qty=value))
            self.assertEqual(guard.orden_buy_notional(NS(qty=value,notional=None)),float('inf'))
        self.assertEqual(guard.orden_buy_notional(NS(qty=1,notional='NaN')),float('inf'))

    def test_crypto_uses_actual_increment_without_six_decimal_truncation(self):
        c=Client(); result=execution._refresh_buy_quantity(c,order('BTC/USD',.0000012349))
        self.assertAlmostEqual(result.qty,.000001234,places=12)
        c.get_asset=lambda _:NS(min_order_size='.01',min_trade_increment='.001')
        with self.assertRaises(ValueError):execution._refresh_buy_quantity(c,order('BTC/USD',.001))

    def test_missing_snapshot_blocks(self):
        c=Client();c.get_orders=lambda filter:None
        with self.assertRaises(ValueError):execution._refresh_buy_quantity(c,order())

    def test_concurrent_buys_cannot_both_consume_the_same_available_exposure(self):
        c=Client()
        def send(symbol):
            try:return execution.submit_order_idempotente(c,order(symbol,20))
            except ValueError:return None
        with patch.object(config,'MAX_TOTAL_EXPOSURE_PCT',.3),ThreadPoolExecutor(2) as pool:
            results=list(pool.map(send,['AAPL','MSFT']))
        self.assertEqual(sum(x is not None for x in results),1)
        self.assertEqual(len(c.sent),1)

    def test_sell_does_not_require_purchase_data(self):
        c=Client();c.get_account=lambda:(_ for _ in ()).throw(AssertionError('BUY check on SELL'))
        self.assertIsNotNone(execution.submit_order_idempotente(c,order(side='sell')))
