import unittest
import pandas as pd
from backtest_engine import run
from portfolio_backtest import run_portfolio
from simulation_data import clean_ohlcv


def bars(rows):
    return pd.DataFrame(rows, columns=['open','high','low','close','volume'],
                        index=pd.date_range('2024-01-01',periods=len(rows),tz='UTC'))


class SimulationIntegrityTests(unittest.TestCase):
    def engines(self, frame, signal, **kw):
        opts=dict(initial_cash=10000,risk_per_trade_pct=.01,stop_loss_pct=.1,
                  take_profit_pct=.5,trailing_stop_pct=0,**kw)
        yield run(frame,signal_fn=signal,**opts)
        yield run_portfolio({'A':frame},signal_fn=lambda _,h:signal(h),
                            max_positions=1,max_total_exposure_pct=1,max_single_position_pct=1,**opts)

    def test_fees_match_cash_and_net_pnl(self):
        frame=bars([[100,100,100,100,1000]]*4)
        for stats, eq, trades in self.engines(frame, lambda h:'COMPRAR' if len(h)==1 else 'ESPERAR',fee_bps=10):
            self.assertEqual(len(trades),1)
            self.assertAlmostEqual(stats['final_equity']-10000,sum(t.pnl for t in trades))
            self.assertAlmostEqual(trades[0].pnl,-2)
            self.assertLess(trades[0].return_pct,0)

    def test_close_signal_sells_at_next_open(self):
        frame=bars([[100,100,100,100,1000],[100,105,99,105,1000],[102,104,101,103,1000]])
        for _,_,trades in self.engines(frame,lambda h:'COMPRAR' if len(h)==1 else 'VENDER'):
            self.assertEqual(trades[0].exit,102)
            self.assertEqual(trades[0].exit_time,frame.index[2])

    def test_stop_gap_cannot_fill_at_unavailable_price(self):
        frame=bars([[100,100,100,100,1000],[100,100,99,100,1000],[70,80,60,75,1000]])
        for _,_,trades in self.engines(frame,lambda h:'COMPRAR' if len(h)==1 else 'ESPERAR'):
            self.assertEqual(trades[0].exit,70)

    def test_trailing_does_not_retroactively_use_close(self):
        frame=bars([[100,100,100,100,1000],[100,120,99,120,1000],[120,121,119,120,1000]])
        opts=dict(initial_cash=10000,risk_per_trade_pct=.01,stop_loss_pct=.1,take_profit_pct=.5,trailing_stop_pct=.05)
        for result in [run(frame,signal_fn=lambda h:'COMPRAR' if len(h)==1 else 'ESPERAR',**opts),run_portfolio({'A':frame},signal_fn=lambda _,h:'COMPRAR' if len(h)==1 else 'ESPERAR',**opts)]:
            self.assertEqual(result[2][0].exit_time,frame.index[-1])
            self.assertEqual(result[2][0].reason,'end_of_data')

    def test_invalid_bars_rejected(self):
        for values in [[100,90,99,100,1000],[100,101,99,float('inf'),1000],[100,101,99,100,-1]]:
            with self.assertRaises(ValueError):clean_ohlcv(bars([values]))
        df=bars([[100,100,100,100,1000]]*2);df.index=[df.index[0]]*2
        with self.assertRaises(ValueError):clean_ohlcv(df)

    def test_portfolio_entry_uses_current_open_exposure_after_gap(self):
        a=bars([[100,100,100,100,1000],[100,100,100,100,1000],
                [200,200,200,200,1000],[200,200,200,200,1000]])
        b=bars([[100,100,100,100,1000]]*4)
        def signal(symbol,h):
            return 'COMPRAR' if (symbol=='A' and len(h)==1) or (symbol=='B' and len(h)==2) else 'ESPERAR'
        _,_,trades=run_portfolio({'A':a,'B':b},initial_cash=10000,
            risk_per_trade_pct=1,stop_loss_pct=.5,take_profit_pct=2,
            trailing_stop_pct=0,max_positions=2,max_single_position_pct=.4,
            max_total_exposure_pct=.5,signal_fn=signal)
        self.assertEqual([t.symbol for t in trades],['A'])

    def test_oos_receives_warmup_without_future_bars(self):
        from research_lab import walk_forward
        frame=bars([[100,100,100,100,1000]]*12)
        seen=[]
        def signal(h):
            seen.append(h.index[-1]);self.assertEqual(h.index[0],frame.index[0]);return 'ESPERAR'
        windows=walk_forward(frame,signal_fn=signal,train_bars=8,test_bars=4)
        self.assertEqual(len(windows),1)
        self.assertTrue(all(frame.index[8]<=t<=frame.index[11] for t in seen))

    def test_monte_carlo_accounts_for_first_loss_and_position_size(self):
        from research_lab import monte_carlo
        from backtest_engine import Trade
        trades=[Trade(0,1,100,99,1,-1,-1,'stop')]*2
        result=monte_carlo(trades,initial_cash=10000,simulations=100,horizon_trades=1)
        self.assertGreater(result.median_return_pct,-.02)
        self.assertLess(result.median_max_drawdown_pct,0)

    def test_missing_train_evidence_is_unknown(self):
        from research_lab import summarize_walk_forward
        self.assertIsNone(summarize_walk_forward([])['oos_degradation_pct'])
