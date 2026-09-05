"""Motor seguro de análisis, memoria y propuestas para BOTTRADE."""
from __future__ import annotations
import hashlib, json, math, os, uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

ALLOWED_PARAMETER_GROUPS={"strategy":{"EMA_RAPIDA","EMA_LENTA","EMA_TENDENCIA","RSI_PERIODO","RSI_SOBRECOMPRA","RSI_SOBREVENTA","CRYPTO_SCORE_MINIMO"},"risk":{"RISK_PER_TRADE_PCT","CRYPTO_RISK_PER_TRADE_PCT","MAX_TOTAL_EXPOSURE_PCT","MAX_SINGLE_POSITION_PCT"},"exit":{"STOP_LOSS_PCT","TAKE_PROFIT_PCT","TRAILING_STOP_PCT","ATR_STOP_MULTIPLICADOR","ATR_TAKE_PROFIT_MULTIPLICADOR"},"exposure":{"MAX_POSICIONES_ABIERTAS","CRYPTO_MAX_NOTIONAL_PCT","CRYPTO_MAX_ORDER_NOTIONAL_USD"},"filters":{"CRYPTO_MIN_MOMENTUM_PCT","CRYPTO_VOLUME_MIN_MULTIPLICADOR","CRYPTO_RSI_MIN","CRYPTO_RSI_MAX"}}
ALLOWED_PARAMETERS=frozenset().union(*ALLOWED_PARAMETER_GROUPS.values())
PARAMETER_BOUNDS={"EMA_RAPIDA":(2,50),"EMA_LENTA":(5,100),"EMA_TENDENCIA":(50,400),"RSI_PERIODO":(5,50),"RSI_SOBRECOMPRA":(55,90),"RSI_SOBREVENTA":(10,45),"CRYPTO_SCORE_MINIMO":(50,100),"RISK_PER_TRADE_PCT":(0.0025,0.05),"CRYPTO_RISK_PER_TRADE_PCT":(0.0025,0.05),"MAX_TOTAL_EXPOSURE_PCT":(0.10,0.75),"MAX_SINGLE_POSITION_PCT":(0.02,0.30),"STOP_LOSS_PCT":(0.002,0.15),"TAKE_PROFIT_PCT":(0.003,0.30),"TRAILING_STOP_PCT":(0.002,0.15),"ATR_STOP_MULTIPLICADOR":(0.50,5.0),"ATR_TAKE_PROFIT_MULTIPLICADOR":(0.75,8.0),"MAX_POSICIONES_ABIERTAS":(1,20),"CRYPTO_MAX_NOTIONAL_PCT":(0.01,0.50),"CRYPTO_MAX_ORDER_NOTIONAL_USD":(25,100000),"CRYPTO_MIN_MOMENTUM_PCT":(0.01,10.0),"CRYPTO_VOLUME_MIN_MULTIPLICADOR":(0.50,5.0),"CRYPTO_RSI_MIN":(20,70),"CRYPTO_RSI_MAX":(50,90)}

def _num(v):
    try:
        v=float(v); return v if math.isfinite(v) else None
    except (TypeError,ValueError): return None

def _pct(n,d):return n/d if d else None

def _max_drawdown(equity):
    if not equity:return 0.0
    peak=float(equity[0]); worst=0.0
    for value in equity:
        value=float(value)
        if value>peak:peak=value
        if peak>0:worst=min(worst,(value-peak)/peak)
    return worst

def _profit_factor(pnls):
    gains=sum(x for x in pnls if x>0); losses=-sum(x for x in pnls if x<0)
    if losses==0:return math.inf if gains>0 else None
    return gains/losses

def analyze_performance(trades=(),equity=(),*,risk_per_trade=None):
    normalized=[]
    for raw in trades:
        pnl=_num(raw.get("pnl",raw.get("profit_loss",raw.get("realized_pnl"))))
        if pnl is None:continue
        item=dict(raw);item["pnl"]=pnl;item["symbol"]=str(raw.get("symbol",raw.get("ticker","UNKNOWN"))).upper();item["asset_type"]=str(raw.get("asset_type",raw.get("type","unknown"))).lower();normalized.append(item)
    pnls=[x["pnl"] for x in normalized];wins=[x for x in pnls if x>0];losses=[x for x in pnls if x<0];eq_values=[]
    for point in equity:
        value=point if isinstance(point,(int,float)) else point.get("equity");value=_num(value)
        if value is not None:eq_values.append(value)
    groups=defaultdict(list);type_groups=defaultdict(list)
    for trade in normalized:groups[trade["symbol"]].append(trade["pnl"]);type_groups[trade["asset_type"]].append(trade["pnl"])
    by_asset={s:{"trades":len(v),"pnl":round(sum(v),8),"win_rate":_pct(sum(x>0 for x in v),len(v)),"profit_factor":_profit_factor(v),"expectancy":mean(v)} for s,v in groups.items()}
    by_type={s:{"trades":len(v),"pnl":round(sum(v),8),"win_rate":_pct(sum(x>0 for x in v),len(v)),"profit_factor":_profit_factor(v),"expectancy":mean(v)} for s,v in type_groups.items()}
    risk_values=[_num(x.get("risk_amount",x.get("risk"))) for x in normalized];risk_values=[x for x in risk_values if x is not None and x>0]
    r=[t["pnl"]/t["risk_amount"] for t in normalized if _num(t.get("risk_amount")) not in (None,0)]
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"trades":len(pnls),"wins":len(wins),"losses":len(losses),"win_rate":_pct(len(wins),len(pnls)),"total_pnl":sum(pnls),"gross_profit":sum(wins),"gross_loss":sum(losses),"profit_factor":_profit_factor(pnls),"expectancy":mean(pnls) if pnls else 0.0,"average_win":mean(wins) if wins else None,"average_loss":mean(losses) if losses else None,"max_drawdown":_max_drawdown(eq_values),"risk_per_trade":mean(risk_values) if risk_values else risk_per_trade,"average_r_multiple":mean(r) if r else None,"by_asset":by_asset,"by_asset_type":by_type}

@dataclass(frozen=True)
class Proposal:
    proposal_id:str;created_at:str;reason:str;expected_impact:str;validation:dict[str,Any];changes:dict[str,Any];reversible:bool=True;status:str="PENDING_APPROVAL"

def _validate_change(key,value):
    if key not in ALLOWED_PARAMETERS:raise ValueError(f"Parámetro no permitido por el AI gate: {key}")
    lo,hi=PARAMETER_BOUNDS[key];number=_num(value)
    if number is None or not lo<=number<=hi:raise ValueError(f"Valor fuera de límites para {key}: {value!r}")
    integer_keys={"EMA_RAPIDA","EMA_LENTA","EMA_TENDENCIA","RSI_PERIODO","RSI_SOBRECOMPRA","RSI_SOBREVENTA","MAX_POSICIONES_ABIERTAS"}
    if key in integer_keys and number!=int(number):raise ValueError(f"{key} debe ser entero")
    return int(number) if key in integer_keys else number

def make_proposal(reason,changes,*,expected_impact,validation=None):
    if not changes:raise ValueError("Una propuesta debe contener al menos un cambio.")
    validated={key:_validate_change(key,value) for key,value in changes.items()}
    return Proposal(str(uuid.uuid4()),datetime.now(timezone.utc).isoformat(),str(reason),str(expected_impact),dict(validation or {}),validated)

def authorize_proposal(proposal,approval_phrase):
    if proposal.status!="PENDING_APPROVAL":raise ValueError("La propuesta ya no está pendiente de aprobación.")
    if str(approval_phrase).strip().upper()!="APLICAR":raise PermissionError("Se requiere aprobación explícita con la palabra APLICAR.")
    return hashlib.sha256(f"{proposal.proposal_id}|{proposal.created_at}|{proposal.changes}".encode()).hexdigest()

def apply_proposal(proposal,token,current_config):
    expected=authorize_proposal(proposal,"APLICAR")
    if not token or not __import__("hmac").compare_digest(expected,token):raise PermissionError("Token de autorización inválido.")
    updated=dict(current_config);before={key:updated.get(key) for key in proposal.changes};updated.update(proposal.changes)
    return {"config":updated,"rollback":before,"proposal_id":proposal.proposal_id}

class AnalystMemory:
    def __init__(self,path):self.path=path
    def append(self,kind,payload):
        record={"timestamp":datetime.now(timezone.utc).isoformat(),"kind":str(kind),"payload":dict(payload)};directory=os.path.dirname(os.path.abspath(self.path));os.makedirs(directory,exist_ok=True)
        with open(self.path,"a",encoding="utf-8") as handle:handle.write(json.dumps(record,ensure_ascii=False,sort_keys=True)+"\n")
        return record
    def recent(self,*,kind=None,limit=100):
        if limit<1 or not os.path.exists(self.path):return []
        records=[]
        with open(self.path,"r",encoding="utf-8") as handle:
            for line in handle:
                try:record=json.loads(line)
                except json.JSONDecodeError:continue
                if kind is None or record.get("kind")==kind:records.append(record)
        return records[-limit:]

def audit_proposal(memory,proposal,result):return memory.append("proposal_audit",{"proposal":asdict(proposal),"result":dict(result)})
