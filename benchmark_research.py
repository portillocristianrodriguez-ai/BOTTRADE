"""Reproducible recent-market benchmark; read-only and never promotes a strategy.

Three fixed baselines are references, not rankings of commercial bots. This
compares isolated signals under a common long-only simulator, not the complete
concurrent production scanner, portfolio selection or order-book exit manager.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import numpy as np
import estrategia
from portfolio_backtest import run_portfolio
from simulation_data import clean_ohlcv


def reference_signal(name, hist):
    close=hist['close']
    if name=='trend_20_50':
        if len(close)<50:return 'ESPERAR'
        return 'COMPRAR' if close.iloc[-20:].mean()>close.iloc[-50:].mean() else 'VENDER'
    if name=='mean_reversion_20_2pct':
        if len(close)<20:return 'ESPERAR'
        ratio=close.iloc[-1]/close.iloc[-20:].mean()
        return 'COMPRAR' if ratio<.98 else 'VENDER' if ratio>=1 else 'ESPERAR'
    raise ValueError(name)


def buy_hold(frame, initial_cash, allocation, fee_bps, slippage_bps):
    entry=float(frame.iloc[0].open)*(1+slippage_bps/10000)
    qty=initial_cash*allocation/(entry*(1+fee_bps/10000))
    cash=initial_cash-qty*entry*(1+fee_bps/10000)
    eq=cash+qty*frame.close
    eq.iloc[-1]=cash+qty*float(frame.iloc[-1].close)*(1-slippage_bps/10000)*(1-fee_bps/10000)
    path=pd.concat([pd.Series([initial_cash]),eq.reset_index(drop=True)],ignore_index=True)
    return {'total_return_pct':float(eq.iloc[-1]/initial_cash-1)*100,
            'max_drawdown_pct':float((path/path.cummax()-1).min())*100,'trades':1,
            'net_pnl':float(eq.iloc[-1]-initial_cash)}


def _json_safe(value):
    if isinstance(value,dict):return {k:_json_safe(v) for k,v in value.items()}
    if isinstance(value,list):return [_json_safe(v) for v in value]
    if isinstance(value,(float,np.floating)) and not np.isfinite(value):return None
    return value


def compare(data_dir, output, window_days=7, windows=3):
    root=Path(data_dir); manifest=json.loads((root/'manifest.json').read_text())
    end=pd.Timestamp(manifest['end_exclusive']); results=[]; failures=[]
    for filename,metadata in manifest['files'].items():
        path=root/filename
        if hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['sha256']:
            raise ValueError('Dataset checksum mismatch: '+filename)
        frame=clean_ohlcv(pd.read_csv(path,index_col='timestamp'))
        symbol=metadata['symbol']; crypto='/' in symbol
        # Causal indicators are computed once; only their prefix is exposed.
        indicators=estrategia.calcular_indicadores(frame)
        if indicators.empty:
            failures.append({'symbol':symbol,'reason':'invalid indicators'});continue
        def cached_indicators(hist):
            return indicators.iloc[:frame.index.get_loc(hist.index[-1])+1]
        signals={}
        with patch.object(estrategia,'calcular_indicadores',cached_indicators):
            for window in range(windows):
                start=end-pd.Timedelta(days=window_days*(windows-window))
                finish=start+pd.Timedelta(days=window_days)
                test=frame.loc[(frame.index>=start)&(frame.index<finish)]
                if len(test)<2:
                    failures.append({'symbol':symbol,'window':window,'reason':'insufficient bars'});continue
                names=['bottrade_signal','trend_20_50','mean_reversion_20_2pct','buy_hold_10pct']
                for cost_scenario in ['base','stress']:
                    # Conservative tier-1 crypto taker fee assumption, not the
                    # actual account tier; stock cost is a modelling allowance.
                    fee=25 if crypto else 1
                    slip=(10 if crypto else 5)*(2 if cost_scenario=='stress' else 1)
                    for name in names:
                        if name=='buy_hold_10pct':
                            stats=buy_hold(test,100000,.1,fee,slip)
                        else:
                            def signal(_symbol,hist):
                                timestamp=hist.index[-1]; key=(name,timestamp)
                                if key not in signals:
                                    context=frame.loc[:timestamp]
                                    if name=='bottrade_signal':
                                        fn=estrategia._generar_senal_cripto if crypto else estrategia.generar_senal
                                        signals[key]=fn(context)
                                    else: signals[key]=reference_signal(name,context)
                                return signals[key]
                            stats,_,trades=run_portfolio({symbol:test},initial_cash=100000,
                                risk_per_trade_pct=.01,stop_loss_pct=.02,take_profit_pct=.04,
                                trailing_stop_pct=.015,max_positions=1,max_single_position_pct=.1,
                                max_total_exposure_pct=.1,fee_bps=fee,slippage_bps=slip,signal_fn=signal)
                            stats={'total_return_pct':stats['total_return_pct'],'max_drawdown_pct':stats['max_drawdown_pct'],
                                   'trades':len(trades),'net_pnl':sum(t.pnl for t in trades)}
                        results.append(dict(symbol=symbol,strategy=name,start=str(start),end_exclusive=str(finish),
                            bars=len(test),cost_scenario=cost_scenario,fee_bps_per_side=fee,
                            slippage_bps_per_side=slip,**stats))
                        print(symbol,window,cost_scenario,name,round(stats['total_return_pct'],4),flush=True)
                Path(output).write_text(json.dumps(_json_safe({'status':'in_progress','results':results,'failures':failures}),indent=2,allow_nan=False))
    report={'status':'complete','data_manifest':manifest,'results':results,'failures':failures,
            'competitive_advantage_verified':False,
            'limitations':['Recent fixed windows are not evidence across market regimes.',
                           'Isolated long-only signals; no full live portfolio or order-book replay.',
                           '10% position cap per instrument; buy-and-hold is 10% initial allocation without rebalance.',
                           'Fees and slippage are assumptions, not measured future execution costs.',
                           'No commercial bot ranking; no automatic strategy promotion.']}
    Path(output).write_text(json.dumps(_json_safe(report),indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('data_dir');parser.add_argument('output')
    args=parser.parse_args();compare(args.data_dir,args.output)
