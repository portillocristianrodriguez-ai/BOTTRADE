"""Motor seguro de análisis, memoria y propuestas para BOTTRADE."""
from __future__ import annotations
import hashlib, json, math, os, tempfile, uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

ALLOWED_PARAMETER_GROUPS = {
    "strategy": {"EMA_RAPIDA", "EMA_LENTA", "EMA_TENDENCIA", "RSI_PERIODO", "RSI_SOBRECOMPRA", "RSI_SOBREVENTA", "CRYPTO_SCORE_MINIMO"},
    "risk": {"RISK_PER_TRADE_PCT", "CRYPTO_RISK_PER_TRADE_PCT", "MAX_TOTAL_EXPOSURE_PCT", "MAX_SINGLE_POSITION_PCT"},
    "exit": {"STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "TRAILING_STOP_PCT", "ATR_STOP_MULTIPLICADOR", "ATR_TAKE_PROFIT_MULTIPLICADOR"},
    "exposure": {"MAX_POSICIONES_ABIERTAS", "CRYPTO_MAX_NOTIONAL_PCT", "CRYPTO_MAX_ORDER_NOTIONAL_USD"},
    "filters": {"CRYPTO_MIN_MOMENTUM_PCT", "CRYPTO_VOLUME_MIN_MULTIPLICADOR", "CRYPTO_RSI_MIN", "CRYPTO_RSI_MAX"},
}
ALLOWED_PARAMETERS = frozenset().union(*ALLOWED_PARAMETER_GROUPS.values())

# Límites absolutos del AI gate. El aprendizaje nunca puede convertir una
# propuesta en una configuración absurda o más permisiva que los controles base.
PARAMETER_BOUNDS = {
    "EMA_RAPIDA": (2, 50), "EMA_LENTA": (5, 100), "EMA_TENDENCIA": (50, 400),
    "RSI_PERIODO": (5, 50), "RSI_SOBRECOMPRA": (55, 90), "RSI_SOBREVENTA": (10, 45),
    "CRYPTO_SCORE_MINIMO": (50, 100),
    "RISK_PER_TRADE_PCT": (0.0025, 0.05), "CRYPTO_RISK_PER_TRADE_PCT": (0.0025, 0.05),
    "MAX_TOTAL_EXPOSURE_PCT": (0.10, 0.75), "MAX_SINGLE_POSITION_PCT": (0.02, 0.30),
    "STOP_LOSS_PCT": (0.002, 0.15), "TAKE_PROFIT_PCT": (0.003, 0.30), "TRAILING_STOP_PCT": (0.002, 0.15),
    "ATR_STOP_MULTIPLICADOR": (0.50, 5.0), "ATR_TAKE_PROFIT_MULTIPLICADOR": (0.75, 8.0),
    "MAX_POSICIONES_ABIERTAS": (1, 20), "CRYPTO_MAX_NOTIONAL_PCT": (0.01, 0.50),
    "CRYPTO_MAX_ORDER_NOTIONAL_USD": (25, 100000),
    "CRYPTO_MIN_MOMENTUM_PCT": (0.01, 10.0), "CRYPTO_VOLUME_MIN_MULTIPLICADOR": (0.50, 5.0),
    "CRYPTO_RSI_MIN": (20, 70), "CRYPTO_RSI_MAX": (50, 90),
}


def _num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError): return None

def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None: return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")); return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError): return None

def _pct(numerator: float, denominator: float) -> float | None: return numerator / denominator if denominator else None

def _max_drawdown(equity: Sequence[float]) -> float:
    if not equity: return 0.0
    peak=float(equity[0]); worst=0.0
    for value in equity:
        value=float(value)
        if value>peak: peak=value
        if peak>0: worst=min(worst,(value-peak)/peak)
    return worst

def _profit_factor(pnls: Sequence[float]) -> float | None:
    gains=sum(x for x in pnls if x>0); losses=-sum(x for x in pnls if x<0)
    if losses==0:return math.inf if gains>0 else None
    return gains/losses

def analyze_performance(trades: Iterable[Mapping[str, Any]]=(), equity: Iterable[Mapping[str, Any]|float]=(), *, risk_per_trade: float|None=None)->dict[str,Any]:
    normalized=[]
    for raw in trades:
        pnl=_num(raw.get("pnl",raw.get("profit_loss",raw.get("realized_pnl"))))
        if pnl is None: continue
        item=dict(raw); item["pnl"]=pnl; item["symbol"]=str(raw.get("symbol",raw.get("ticker","UNKNOWN"))).upper(); item["asset_type"]=str(raw.get("asset_type",raw.get("type","unknown"))).lower(); normalized.append(item)
    pnls=[x["pnl"] for x in normalized]; wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]; total=sum(pnls); avg=mean(pnls) if pnls else 0.0
    eq_values=[]
    for point in equity:
        value=point if isinstance(point,(int,float)) else point.get("equity"); value=_num(value)
        if value is not None:eq_values.append(value)
    by_asset={}; groups=defaultdict(list)
    for trade in normalized:groups[trade["symbol"]].append(trade["pnl"])
    for symbol,values in groups.items():by_asset[symbol]={"trades":len(values),"pnl":round(sum(values),8),"win_rate":_pct(sum(x>0 for x in values),len(values)),"profit_factor":_profit_factor(values),"expectancy":mean(values)}
    by_type={}; type_groups=defaultdict(list)
    for trade in normalized:type_groups[trade["asset_type"]].append(trade["pnl"])
    for asset_type,values in type_groups.items():by_type[asset_type]={"trades":len(values),"pnl":round(sum(values),8),"win_rate":_pct(sum(x>0 for x in values),len(values)),"profit_factor":_profit_factor(values),"expectancy":mean(values)}
    risk_values=[_num(x.get("risk_amount",x.get("risk"))) for x in normalized]; risk_values=[x for x in risk_values if x is not None and x>0]
    realized_risk=mean(risk_values) if risk_values else risk_per_trade
    r_multiples=[t["pnl"]/t["risk_amount"] for t in normalized if _num(t.get("risk_amount")) not in (None,0)]
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"trades":len(pnls),"wins":len(wins),"losses":len(losses),"win_rate":_pct(len(wins),len(pnls)),"total_pnl":total,"gross_profit":sum(wins),"gross_loss":sum(losses),"profit_factor":_profit_factor(pnls),"expectancy":avg,"average_win":mean(wins) if wins else None,"average_loss":mean(losses) if losses else None,"max_drawdown":_max_drawdown(eq_values),"risk_per_trade":realized_risk,"average_r_multiple":mean(r_multiples) if r_multiples else None,"by_asset":by_asset,"by_asset_type":by_type}

@dataclass(frozen=True)
class Proposal:
    proposal_id:str; created_at:str; reason:str; expected_impact:str; validation:dict[str,Any]; changes:dict[str,Any]; reversible:bool=True; status:str="PENDING_APPROVAL"

def _validate_change(key: str, value: Any) -> Any:
    if key not in ALLOWED_PARAMETERS: raise ValueError(f"Parámetro no permitido por el AI gate: {key}")
    bounds=PARAMETER_BOUNDS.get(key)
    if bounds is None: return value
    number=_num(value)
    if number is None: raise ValueError(f"Valor inválido para {key}: {value!r}")
    lo,hi=bounds
    if not lo<=number<=hi: raise ValueError(f"Valor fuera de límites para {key}: {number} no está entre {lo} y {hi}")
    if key in {"EMA_RAPIDA","EMA_LENTA","EMA_TENDENCIA","RSI_PERIODO","RSI_SOBRECOMPRA","RSI_SOBREVENTA","MAX_POSICIONES_ABIERTAS"}:
        if number!=int(number): raise ValueError(f"{key} debe ser entero")
        return int(number)
    return number

def make_proposal(reason:str, changes:Mapping[str,Any], *, expected_impact:str, validation:Mapping[str,Any]|None=None)->Proposal:
    if not changes: raise ValueError("Una propuesta debe contener al menos un cambio.")
    validated={key:_validate_change(key,value) for key,value in changes.items()}
    # Evita configuraciones internas incoherentes en filtros RSI y medias.
    if "RSI_RSI_MIN" in validated: raise ValueError("Parámetro RSI inválido")
    if validated.get("RSI_SOBREVENTA",0)>=validated.get("RSI_SOBRECOMPRA",999): raise ValueError("RSI sobreventa debe ser menor que sobrecompra")
    if validated.get("EMA_RAPIDA",0)>=validated.get("EMA_LENTA",999): raise ValueError("EMA rápida debe ser menor que EMA lenta")
    return Proposal(str(uuid.uuid4()),datetime.now(timezone.utc).isoformat(),str(reason),str(expected_impact),dict(validation or {}),validated)

def authorize_proposal(proposal:Proposal, approval_phrase:str)->str:
    if proposal.status!="PENDING_APPROVAL":raise ValueError("La propuesta ya no está pendiente de aprobación.")
    if str(approval_phrase).strip().upper()!="APLICAR":raise PermissionError("Se requiere aprobación explícita con la palabra APLICAR.")
    return hashlib.sha256(f"{proposal.proposal_id}|{proposal.created_at}|{proposal.changes}".encode()).hexdigest()

def apply_proposal(proposal:Proposal, token:str, current_config:Mapping[str,Any])->dict[str,Any]:
    expected=authorize_proposal(proposal,"APLICAR")
    if not token or not __import__("hmac").compare_digest(expected,token):raise PermissionError("Token de autorización inválido.")
    updated=dict(current_config); before={key:updated.get(key) for key in proposal.changes}; updated.update(proposal.changes)
    return {"config":updated,"rollback":before,"proposal_id":proposal.proposal_id}

class AnalystMemory:
    def __init__(self,path:str):self.path=path
    def append(self,kind:str,payload:Mapping[str,Any])->dict[str,Any]:
        record={"timestamp":datetime.now(timezone.utc).isoformat(),"kind":str(kind),"payload":dict(payload)}; directory=os.path.dirname(os.path.abspath(self.path)); os.makedirs(directory,exist_ok=True)
        with open(self.path,"a",encoding="utf-8") as handle:handle.write(json.dumps(record,ensure_ascii=False,sort_keys=True)+"\n")
        return record
    def recent(self,*,kind:str|None=None,limit:int=100)->list[dict[str,Any]]:
        if limit<1 or not os.path.exists(self.path):return []
        records=[]
        with open(self.path,"r",encoding="utf-8") as handle:
            for line in handle:
                try:record=json.loads(line)
                except json.JSONDecodeError:continue
                if kind is None or record.get("kind")==kind:records.append(record)
        return records[-limit:]

def audit_proposal(memory:AnalystMemory,proposal:Proposal,result:Mapping[str,Any])->dict[str,Any]:return memory.append("proposal_audit",{"proposal":asdict(proposal),"result":dict(result)})
