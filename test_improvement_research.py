import unittest
from improvement_research import qualify


def study():
    rows=[]
    for symbol in ['AAPL','NVDA','SPY','BTC/USD','ETH/USD','SOL/USD']:
        for cost in ['base','stress']:
            for window in range(4):
                for strategy in ['bottrade_signal','trend_confirmation']:
                    rows.append(dict(symbol=symbol,cost_scenario=cost,strategy=strategy,
                        start=str(window),end_exclusive=str(window+1),trades=2,
                        total_return_pct=.2 if strategy=='trend_confirmation' else .1,
                        max_drawdown_pct=-.2))
    return {'status':'complete','failures':[],'results':rows}


class ImprovementResearchTests(unittest.TestCase):
    def test_nonfinite_result_cannot_be_silently_averaged_away(self):
        report=study();report['results'][0]['total_return_pct']=float('nan')
        self.assertFalse(qualify(report,'trend_confirmation')['passed'])

    def test_passing_requires_both_markets_and_cost_scenarios(self):
        report=study();self.assertTrue(qualify(report,'trend_confirmation')['passed'])
        for row in report['results']:
            if row['symbol']=='BTC/USD' and row['cost_scenario']=='stress' and row['strategy']=='trend_confirmation':
                row['total_return_pct']=-10
        self.assertFalse(qualify(report,'trend_confirmation')['passed'])

    def test_missing_or_duplicate_windows_cannot_pass(self):
        report=study();report['results'].pop()
        self.assertFalse(qualify(report,'trend_confirmation')['passed'])
        report=study();report['results'].append(report['results'][0])
        self.assertFalse(qualify(report,'trend_confirmation')['passed'])
