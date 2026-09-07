"""Predefined development/validation rejection screen; never activates trading."""
import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np
from benchmark_research import compare


CANDIDATES=('trend_confirmation','trend_not_extended')


def qualify(report,candidate):
    if report.get('status')!='complete' or report.get('failures'):
        return {'passed':False,'reasons':['incomplete_or_invalid_study']}
    data=pd.DataFrame(report.get('results',[]))
    if data.empty:return {'passed':False,'reasons':['missing_results']}
    required={'symbol','cost_scenario','strategy','start','end_exclusive','total_return_pct','max_drawdown_pct','trades'}
    if not required.issubset(data.columns):return {'passed':False,'reasons':['missing_fields']}
    metrics=data[['total_return_pct','max_drawdown_pct','trades']].apply(pd.to_numeric,errors='coerce')
    if not np.isfinite(metrics.to_numpy()).all() or (metrics.trades<0).any():
        return {'passed':False,'reasons':['invalid_metrics']}
    reasons=[]
    data['market']=data.symbol.map(lambda s:'crypto' if '/' in s else 'stocks')
    for market in ('stocks','crypto'):
        for cost in ('base','stress'):
            subset=data[(data.market==market)&(data.cost_scenario==cost)]
            base=subset[subset.strategy=='bottrade_signal']; new=subset[subset.strategy==candidate]
            label=f'{market}/{cost}'
            # Three instruments and four windows, with identical observations.
            key=['symbol','start','end_exclusive']
            if (len(base)!=12 or len(new)!=12 or base.duplicated(key).any() or new.duplicated(key).any()
                or set(map(tuple,base[key].values))!=set(map(tuple,new[key].values))):
                reasons.append(label+':incomplete_or_mismatched_windows');continue
            if not new.total_return_pct.mean()>0:reasons.append(label+':nonpositive_net_return')
            if not new.total_return_pct.mean()>base.total_return_pct.mean():reasons.append(label+':no_improvement')
            if new.max_drawdown_pct.min()<base.max_drawdown_pct.min():reasons.append(label+':worse_drawdown')
            if new.trades.sum()<20:reasons.append(label+':insufficient_trades')
    return {'passed':not reasons,'reasons':reasons}


def run_study(data_dir,output_dir):
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    development=compare(data_dir,output/'improvement-development-20260907.json',windows=4,
        end_exclusive='2026-07-20T00:00:00Z',
        strategy_names=['bottrade_signal',*CANDIDATES,'buy_hold_10pct'])
    decisions={name:qualify(development,name) for name in CANDIDATES}
    eligible=[name for name in CANDIDATES if decisions[name]['passed']]
    selected=None;validation=None
    if eligible:
        rows=pd.DataFrame(development['results'])
        selected=max(eligible,key=lambda name:rows[(rows.strategy==name)&(rows.cost_scenario=='stress')].total_return_pct.mean())
        test=compare(data_dir,output/'improvement-validation-20260907.json',windows=4,
            end_exclusive='2026-08-17T00:00:00Z',strategy_names=['bottrade_signal',selected,'buy_hold_10pct'])
        validation=qualify(test,selected)
    result={'development':decisions,'selected':selected,'validation':validation,
            'validation_opened':validation is not None,'automatic_activation':False,
            'eligible_for_prospective_paper_review':bool(validation and validation['passed'])}
    (output/'improvement-decision-20260907.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('data_dir');parser.add_argument('output_dir')
    args=parser.parse_args();run_study(args.data_dir,args.output_dir)
