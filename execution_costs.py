"""Conservative planned trade economics, not a forecast or an expected return.

Price targets/stops are fractional distances; impacts are percent; fees are
basis points per side. Exit impact is an explicit assumption, never a quote
from the future. A stop can lose more in a gap.
"""
import math


def planned_trade_economics(*, target_fraction, stop_fraction, fee_bps,
                            entry_impact_pct, exit_impact_pct, minimum_ratio=1.0):
    result={'ok':False,'reason':'invalid_cost_inputs'}
    try:
        target,stop,fee,entry,exit_,minimum=map(float,
            (target_fraction,stop_fraction,fee_bps,entry_impact_pct,exit_impact_pct,minimum_ratio))
        if not all(map(math.isfinite,(target,stop,fee,entry,exit_,minimum))):return result
        if not (0<target<1 and 0<stop<1 and 0<=fee<1000 and
                0<=entry<100 and 0<=exit_<100 and minimum>0):return result
        cost=(1+entry/100)*(1+fee/10000)
        proceeds=(1-exit_/100)*(1-fee/10000)
        reward=((1+target)*proceeds/cost-1)*100
        risk=(1-(1-stop)*proceeds/cost)*100
        ratio=reward/risk
        result.update(net_target_pct=reward,net_stop_loss_pct=risk,
                      net_reward_risk=ratio,
                      roundtrip_cost_pct=(1-proceeds/cost)*100,
                      assumed_fee_bps_per_side=fee,assumed_exit_impact_pct=exit_,
                      ok=reward>0 and ratio>=minimum,
                      reason='ok' if reward>0 and ratio>=minimum else 'costs_exceed_reward_risk_budget')
    except (ValueError,TypeError,OverflowError,ZeroDivisionError):
        pass
    return result
