"""Integración segura del analista de inversión con el runtime de BOTTRADE."""
from __future__ import annotations
import json, os, tempfile
from datetime import datetime, timezone
from typing import Any, Mapping
from ai_investment_analyst import AnalystMemory, Proposal, analyze_performance, audit_proposal, make_proposal
from ai_adaptive_learning import learn
DEFAULT_MEMORY_FILE=os.environ.get("AI_ANALYST_MEMORY_FILE","ai_analyst_memory.jsonl")
DEFAULT_OVERRIDE_FILE=os.environ.get("AI_ANALYST_OVERRIDE_FILE","ai_analyst_overrides.json")
def _now():return datetime.now(timezone.utc).isoformat()
def _num(value):
    try:
        value=float(value);return value if value==value and abs(value)!=float("inf") else None
    except (TypeError,ValueError):return None
def portfolio_risk(positions,equity):
    values=[]
    for raw in positions:
        value=_num(raw.get("market_value",raw.get("value",raw.get("notional"))))
        if value is None:
            qty=_num(raw.get("qty",raw.get("quantity")));price=_num(raw.get("current_price",raw.get("price")))
            if qty is not None and price is not None:value=qty*price
        if value is not None:values.append((str(raw.get("symbol",raw.get("ticker","UNKNOWN"))).upper(),value,raw))
    gross=sum(abs(v) for _,v,_ in values);concentration=[]
    for symbol,value,raw in sorted(values,key=lambda x:abs(x[1]),reverse=True):concentration.append({"symbol":symbol,"market_value":value,"portfolio_pct":abs(value)/equity if equity and equity>0 else None,"asset_type":str(raw.get("asset_type",raw.get("type","unknown"))).lower()})
    by_type={}
    for _,value,raw in values:
        kind=str(raw.get("asset_type",raw.get("type","unknown"))).lower();by_type[kind]=by_type.get(kind,0)+abs(value)
    return {"gross_exposure":gross,"gross_exposure_pct":gross/equity if equity and equity>0 else None,"largest_position":concentration[0] if concentration else None,"concentration":concentration,"by_asset_type":{k:{"market_value":v,"portfolio_pct":v/equity if equity and equity>0 else None} for k,v in by_type.items()}}
def diagnose(metrics,risk=None):
    findings=[];trades=int(metrics.get("trades",0) or 0)
    if trades==0:return [{"severity":"info","code":"NO_TRADES","message":"No hay suficientes operaciones cerradas para evaluar rendimiento."}]
    pf=_num(metrics.get("profit_factor"));wr=_num(metrics.get("win_rate"));dd=_num(metrics.get("max_drawdown"));ex=_num(metrics.get("expectancy"))
    if pf is not None and pf<1:findings.append({"severity":"critical","code":"NEGATIVE_EDGE","message":"El profit factor está por debajo de 1; las pérdidas brutas superan a las ganancias brutas."})
    if ex is not None and ex<0:findings.append({"severity":"critical","code":"NEGATIVE_EXPECTANCY","message":"La esperanza matemática por operación es negativa en la muestra analizada."})
    if dd is not None and dd<=-.05:findings.append({"severity":"warning","code":"DRAWDOWN","message":f"Drawdown máximo de {dd:.2%} en la curva de equity suministrada."})
    if wr is not None and wr<.40:findings.append({"severity":"warning","code":"LOW_WIN_RATE","message":f"Win rate de {wr:.2%}; debe interpretarse junto con payoff y profit factor."})
    if risk:
        gp=_num(risk.get("gross_exposure_pct"));largest=risk.get("largest_position") or {};lp=_num(largest.get("portfolio_pct")) if isinstance(largest,Mapping) else None
        if gp is not None and gp>.80:findings.append({"severity":"warning","code":"HIGH_EXPOSURE","message":f"Exposición bruta de {gp:.2%} del equity."})
        if lp is not None and lp>.25:findings.append({"severity":"warning","code":"CONCENTRATION","message":f"La posición mayor representa {lp:.2%} del equity."})
    if not findings:findings.append({"severity":"info","code":"NO_MAJOR_ALERT","message":"No se detectó una anomalía de riesgo principal con los datos suministrados."})
    return findings
def simulate_risk_change(metrics,current_risk_pct,proposed_risk_pct):
    current=float(current_risk_pct);proposed=float(proposed_risk_pct)
    if current<=0 or proposed<=0:raise ValueError("Los riesgos deben ser positivos.")
    ratio=proposed/current;total=_num(metrics.get("total_pnl")) or 0
    return {"method":"historical_linear_risk_scaling","validated":True,"sample_trades":int(metrics.get("trades",0) or 0),"risk_ratio":ratio,"estimated_total_pnl":total*ratio,"estimated_average_pnl":(_num(metrics.get("expectancy")) or 0)*ratio,"caveat":"Simulación proporcional; no modela slippage, fills, impacto, cambios de señal ni no linealidades."}
def propose_risk_reduction(metrics,current_risk_pct,*,target_risk_pct=None):
    trades=int(metrics.get("trades",0) or 0);dd=_num(metrics.get("max_drawdown"));ex=_num(metrics.get("expectancy"))
    if trades<20 or dd is None or dd>-.05 or (ex is not None and ex>=0):return None
    current=float(current_risk_pct);target=float(target_risk_pct if target_risk_pct is not None else current*.75)
    if not 0<target<current:return None
    return make_proposal("Reducir riesgo después de drawdown y expectativa negativa observados.",{"RISK_PER_TRADE_PCT":target},expected_impact="Reducir proporcionalmente el tamaño de pérdidas y ganancias por operación, preservando los límites de seguridad existentes.",validation=simulate_risk_change(metrics,current,target))
def read_overrides(path=DEFAULT_OVERRIDE_FILE):
    if not os.path.exists(path):return {}
    try:
        with open(path,"r",encoding="utf-8") as h:data=json.load(h)
        return dict(data) if isinstance(data,dict) else {}
    except (OSError,json.JSONDecodeError,TypeError):return {}
def write_overrides(changes,path=DEFAULT_OVERRIDE_FILE):
    current=read_overrides(path);current.update(dict(changes));directory=os.path.dirname(os.path.abspath(path));os.makedirs(directory,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=".ai_overrides_",dir=directory,text=True)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as h:json.dump(current,h,indent=2,ensure_ascii=False,sort_keys=True)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.remove(tmp)
    return current
class AIAnalystRuntime:
    def __init__(self,memory_path=DEFAULT_MEMORY_FILE,override_path=DEFAULT_OVERRIDE_FILE):self.memory=AnalystMemory(memory_path);self.override_path=override_path
    def analyze(self,trades,equity=(),positions=()):
        metrics=analyze_performance(trades,equity);equity_now=None
        if equity:
            last=equity[-1];equity_now=_num(last if isinstance(last,(int,float)) else last.get("equity"))
        risk=portfolio_risk(positions,equity_now);findings=diagnose(metrics,risk)
        import config
        current_config={k:getattr(config,k,None) for k in ("RISK_PER_TRADE_PCT","CRYPTO_RISK_PER_TRADE_PCT","STOP_LOSS_PCT","TAKE_PROFIT_PCT","TRAILING_STOP_PCT","ATR_STOP_MULTIPLICADOR","ATR_TAKE_PROFIT_MULTIPLICADOR","EMA_RAPIDA","EMA_LENTA","EMA_TENDENCIA","RSI_PERIODO","RSI_SOBRECOMPRA","RSI_SOBREVENTA","CRYPTO_SCORE_MINIMO","CRYPTO_MIN_MOMENTUM_PCT","CRYPTO_VOLUME_MIN_MULTIPLICADOR","CRYPTO_RSI_MIN","CRYPTO_RSI_MAX")}
        learning=learn(trades,metrics,current_config)
        report={"generated_at":_now(),"metrics":metrics,"risk":risk,"findings":findings,"learning":learning}
        self.memory.append("analysis",report)
        if learning.get("proposal"):self.memory.append("learning_proposal",learning["proposal"])
        return report
    def apply(self,proposal,token,current_config):
        from ai_investment_analyst import apply_proposal
        result=apply_proposal(proposal,token,current_config);write_overrides(proposal.changes,self.override_path);audit_proposal(self.memory,proposal,result);return result
