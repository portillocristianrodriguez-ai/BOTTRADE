"""Capa de aprendizaje adaptativo y conservador para BOTTRADE.

Aprende de operaciones cerradas y del contexto de configuración con el que se
abrieron. Nunca modifica configuración ni broker: solo devuelve una propuesta
auditable para que el gate de autorización decida si aplicar.
"""
from __future__ import annotations
from dataclasses import asdict
from typing import Any, Mapping, Sequence
from ai_investment_analyst import Proposal, make_proposal

_STRATEGY_KEYS=("STOP_LOSS_PCT","TAKE_PROFIT_PCT","TRAILING_STOP_PCT","ATR_STOP_MULTIPLICADOR","ATR_TAKE_PROFIT_MULTIPLICADOR","EMA_RAPIDA","EMA_LENTA","EMA_TENDENCIA","RSI_PERIODO","RSI_SOBRECOMPRA","RSI_SOBREVENTA","CRYPTO_SCORE_MINIMO","CRYPTO_MIN_MOMENTUM_PCT","CRYPTO_VOLUME_MIN_MULTIPLICADOR","CRYPTO_RSI_MIN","CRYPTO_RSI_MAX")

def _num(value: Any, default: float | None = None) -> float | None:
    try:
        value=float(value); return value if value==value and abs(value)!=float("inf") else default
    except (TypeError,ValueError): return default

def _stats(trades: Sequence[Mapping[str,Any]]) -> dict[str,Any]:
    pnls=[_num(t.get("pnl")) for t in trades]; pnls=[x for x in pnls if x is not None]; wins=[x for x in pnls if x>0]; losses=[-x for x in pnls if x<0]; gross_loss=sum(losses)
    return {"trades":len(pnls),"win_rate":len(wins)/len(pnls) if pnls else None,"profit_factor":sum(wins)/gross_loss if gross_loss else (float("inf") if wins else None),"expectancy":sum(pnls)/len(pnls) if pnls else None,"total_pnl":sum(pnls)}

def _window(trades: Sequence[Mapping[str,Any]],size:int)->Sequence[Mapping[str,Any]]: return trades[-size:] if len(trades)>size else trades

def _group_stats(trades: Sequence[Mapping[str,Any]],key:str)->dict[str,dict[str,Any]]:
    groups:dict[str,list[Mapping[str,Any]]]={}
    for trade in trades:
        value=str(trade.get(key,"unknown")).lower(); groups.setdefault(value,[]).append(trade)
    return {name:_stats(items) for name,items in groups.items()}

def _simulate(metrics: Mapping[str,Any],current:float,proposed:float)->dict[str,Any]:
    ratio=proposed/current
    return {"method":"historical_linear_risk_scaling","validated":True,"sample_trades":int(metrics.get("trades",0) or 0),"risk_ratio":ratio,"estimated_total_pnl":(_num(metrics.get("total_pnl"),0.0) or 0.0)*ratio,"estimated_average_pnl":(_num(metrics.get("expectancy"),0.0) or 0.0)*ratio,"caveat":"Simulación proporcional; no predice mercado ni modela slippage, impacto o cambios de señal."}

def _parameter_candidates(trades: Sequence[Mapping[str,Any]],current_config: Mapping[str,Any]):
    best=None
    for key in _STRATEGY_KEYS:
        current=_num(current_config.get(key))
        if current is None: continue
        groups:dict[float,list[Mapping[str,Any]]]={}
        for trade in trades:
            context=trade.get("entry_config") or {}; value=_num(context.get(key)); pnl=_num(trade.get("pnl"))
            if value is None or pnl is None: continue
            groups.setdefault(round(value,8),[]).append(trade)
        current_group=groups.get(round(current,8),[])
        if len(current_group)<20: continue
        current_stats=_stats(current_group); current_exp=_num(current_stats.get("expectancy"))
        if current_exp is None: continue
        for candidate,items in groups.items():
            if candidate==round(current,8) or len(items)<20: continue
            candidate_stats=_stats(items); candidate_exp=_num(candidate_stats.get("expectancy")); candidate_pf=candidate_stats.get("profit_factor")
            if candidate_exp is None or candidate_pf is None: continue
            improvement=candidate_exp-current_exp; relative=improvement/max(abs(current_exp),0.01)
            if candidate_pf<1.20 or improvement<=0 or relative<0.15: continue
            score=(relative,float(candidate_pf),len(items))
            if best is None or score>best["score"]:best={"key":key,"current":current,"candidate":candidate,"current_stats":current_stats,"candidate_stats":candidate_stats,"score":score}
    return best

def learn(trades: Sequence[Mapping[str,Any]],metrics: Mapping[str,Any],current_config: Mapping[str,Any])->dict[str,Any]:
    sample=list(trades); overall=_stats(sample); recent=_stats(_window(sample,30)); prior=_stats(sample[-60:-30]) if len(sample)>=60 else None; by_asset=_group_stats(sample,"symbol"); by_type=_group_stats(sample,"asset_type"); observations=[]
    if len(sample)>=30 and recent["expectancy"] is not None and overall["expectancy"] is not None:
        drift=recent["expectancy"]-overall["expectancy"]; observations.append(f"La expectativa reciente está {abs(drift):.4f} por debajo de la media histórica." if drift<0 else f"La expectativa reciente mejora {drift:.4f} frente a la media histórica." if drift>0 else "")
        observations=[x for x in observations if x]
    if prior and recent["expectancy"] is not None and prior["expectancy"] is not None:observations.append(f"Cambio de expectativa último bloque vs. bloque anterior: {recent['expectancy']-prior['expectancy']:+.4f}.")
    for asset_type,stats in by_type.items():
        if stats["trades"]>=10 and stats["expectancy"] is not None:observations.append(f"{asset_type}: {stats['trades']} operaciones, PF={stats['profit_factor']}, expectativa={stats['expectancy']:+.4f}.")
    proposal:Proposal|None=None; stock_risk=_num(current_config.get("RISK_PER_TRADE_PCT"),0.02) or 0.02; crypto_risk=_num(current_config.get("CRYPTO_RISK_PER_TRADE_PCT"),0.01) or 0.01; max_dd=_num(metrics.get("max_drawdown"),0.0) or 0.0
    dominant_type=None
    if by_type:
        candidate,candidate_stats=max(by_type.items(),key=lambda item:item[1]["trades"])
        if candidate_stats["trades"]>=max(20,int(len(sample)*0.60)):dominant_type=candidate
    risk_key="CRYPTO_RISK_PER_TRADE_PCT" if dominant_type=="crypto" else "RISK_PER_TRADE_PCT"; current_risk=crypto_risk if risk_key=="CRYPTO_RISK_PER_TRADE_PCT" else stock_risk
    if len(sample)>=30 and (recent["expectancy"] or 0)<0 and max_dd<=-0.04:
        target=round(current_risk*0.80,6)
        if 0.0025<=target<current_risk:proposal=make_proposal("Aprendizaje adaptativo: deterioro reciente con drawdown confirma necesidad de reducir riesgo.",{risk_key:target},expected_impact="Reducir exposición al deterioro observado sin desactivar las protecciones existentes.",validation={**_simulate(metrics,current_risk,target),"learning_sample":len(sample),"recent_stats":recent,"dominant_asset_type":dominant_type})
    elif len(sample)>=60 and prior is not None and recent["profit_factor"] is not None and prior["profit_factor"] is not None and recent["profit_factor"]>=1.30 and prior["profit_factor"]>=1.10 and (recent["expectancy"] or 0)>0 and (prior["expectancy"] or 0)>0 and max_dd>-0.05:
        target=round(current_risk*1.10,6)
        if target>current_risk and target<=min(0.05,current_risk*1.10):proposal=make_proposal("Aprendizaje adaptativo: edge positivo y estable en dos bloques consecutivos.",{risk_key:target},expected_impact="Aumentar moderadamente el riesgo solo después de evidencia histórica consistente; no garantiza mayor rentabilidad futura.",validation={**_simulate(metrics,current_risk,target),"learning_sample":len(sample),"recent_stats":recent,"prior_stats":prior,"dominant_asset_type":dominant_type,"guardrail":"max 5% risk/trade and +10% step"})
    else:
        candidate=_parameter_candidates(sample,current_config)
        if candidate is not None:
            try:
                proposed_value=int(candidate["candidate"]) if candidate["key"] in {"EMA_RAPIDA","EMA_LENTA","EMA_TENDENCIA","RSI_PERIODO","RSI_SOBRECOMPRA","RSI_SOBREVENTA"} else candidate["candidate"]
                proposal=make_proposal("Aprendizaje adaptativo: un valor histórico alternativo supera al actual con evidencia suficiente.",{candidate["key"]:proposed_value},expected_impact="Probar de forma controlada un parámetro ya observado en operaciones reales; no se autoaplica ni garantiza rendimiento futuro.",validation={"method":"historical_context_comparison","validated":True,"current_value":candidate["current"],"candidate_value":candidate["candidate"],"current_stats":candidate["current_stats"],"candidate_stats":candidate["candidate_stats"],"minimum_trades_per_value":20,"relative_expectancy_improvement":candidate["score"][0],"guardrail":"solo valores previamente observados; una propuesta cada vez; aprobación explícita"})
                observations.append(f"{candidate['key']}: valor histórico {candidate['candidate']} supera al actual {candidate['current']} con muestra comparable.")
            except ValueError:pass
    return {"sample_size":len(sample),"overall":overall,"recent_30":recent,"prior_30":prior,"by_asset":by_asset,"by_asset_type":by_type,"observations":observations[:8],"proposal":asdict(proposal) if proposal else None,"policy":"rolling learning; asset-aware; historical parameter context; one small proposal at a time; explicit approval required"}
