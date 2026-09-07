import unittest
from entry_quality import entry_allowed


class EntryQualityTests(unittest.TestCase):
    def test_fixed_filters_distinguish_trend_and_extension(self):
        row=dict(close=105,ema_tendencia=100,ema_rapida=104,ema_lenta=102,atr=2,rsi=60)
        previous={'ema_tendencia':99}
        self.assertTrue(entry_allowed(row,previous,'trend_not_extended'))
        row['rsi']=75
        self.assertTrue(entry_allowed(row,previous,'trend_confirmation'))
        self.assertFalse(entry_allowed(row,previous,'trend_not_extended'))
        self.assertFalse(entry_allowed(row,{'ema_tendencia':101},'trend_confirmation'))

    def test_invalid_indicators_and_unknown_candidate(self):
        self.assertFalse(entry_allowed({}, {},'trend_confirmation'))
        with self.assertRaises(ValueError):entry_allowed({}, {},'invented')
