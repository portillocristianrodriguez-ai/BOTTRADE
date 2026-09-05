"""Capa viva del AI Chief Investment Analyst de BOTTRADE."""
from __future__ import annotations
import os, threading, time
from dataclasses import asdict
from typing import Any
import config
from ai_investment_analyst import Proposal, authorize_proposal
from ai_analyst_runtime import AIAnalystRuntime, read_overrides
_LOCK=threading.RLock(); _RUNTIME=None; _PENDING={}; _LOTS={}; _FILLED_BY_ORDER={}; _STARTED=False

def _runtime():
    global _RUNTIME
    if _RUNTIME is None:_RUNTIME=AIAnalystRuntime()
    return _RUNTIME

def _text(v):return str(v) if v is not None else ""
def _float(v,default=0.0):
    try:return float(v)
    except (TypeError,ValueError):return default

def _event_payload(data):
    event=_text(getattr(data,"event","unknown")).lower(); order=getattr(data,"order",None); symbol=_text(getattr(order,"symbol","")).upper(); side=_text(getattr(order,"side","")).lower(); cumulative=_float(getattr(order,"filled_qty",0)); price=_float(getattr(data,"price",None),_float(getattr(order,"filled_avg_price",0))); return event,order,symbol,cumulative,price,side

def _consume_fifo(symbol,quantity,sell_price):
    realized=[]; remaining=quantity; lots=_LOTS.setdefault(symbol,[])
    while remaining>1e-12 and lots:
        lot=lots[0]; matched=min(remaining,lot["qty"]); pnl=matched*(sell_price-lot["price"])
        realized.append({"symbol":symbol,"asset_type":"crypto" if "/" in symbol else "stock","qty":matched,"entry_price":lot["price"],"exit_price":sell_price,"risk_amount":lot.get("risk_amount",0.0),"pnl":pnl,"entry_order_id":lot.get("order_id","")}); lot["qty"]-=matched; remaining-=matched
        if lot["qty"]<=1e-12:lots.pop(0)
    return realized

def record_trade_update(data):
    event,order,symbol,cumulative,price,side=_event_payload(data)
    if event not in {"fill","partial_fill"} or not symbol or cumulative<=0 or price<=0:return
    order_id=_text(getattr(order,"id",""))
    with _LOCK:
        previous=_FILLED_BY_ORDER.get(order_id,0.0); delta=max(0.0,cumulative-previous); _FILLED_BY_ORDER[order_id]=max(previous,cumulative)
        if delta<=0:return
        _runtime().memory.append("fill",{"event":event,"order_id":order_id,"symbol":symbol,"side":side,"qty":delta,"price":price})
        if "buy" in side:_LOTS.setdefault(symbol,[]).append({"qty":delta,"price":price,"order_id":order_id,"risk_amount":0.0}); return
        if "sell" in side:
            for trade in _consume_fifo(symbol,delta,price):_runtime().memory.append("trade",trade)

def _positions(broker):
    result=[]
    for position in broker.obtener_todas_las_posiciones():
        symbol=_text(getattr(position,"symbol","")); qty=_float(getattr(position,"qty",0)); price=_float(getattr(position,"current_price",0)); value=_float(getattr(position,"market_value",0))
        if not value and qty and price:value=qty*price
        result.append({"symbol":symbol,"qty":qty,"current_price":price,"market_value":value,"asset_type":"crypto" if "/" in symbol else "stock"})
    return result

def analyze_now(broker):
    account=broker.obtener_resumen_cuenta() or {}; equity=_float(account.get("equity"))
    with _LOCK:
        _runtime().memory.append("equity_snapshot",{"equity":equity,"cash":_float(account.get("cash")),"buying_power":_float(account.get("buying_power"))})
        trades_records=_runtime().memory.recent(kind="trade",limit=1000); equity_records=_runtime().memory.recent(kind="equity_snapshot",limit=1000)
    trades=[dict(r.get("payload",{})) for r in trades_records]; equity_curve=[dict(r.get("payload",{})) for r in equity_records]
    report=_runtime().analyze(trades,equity_curve,_positions(broker))
    raw=report.get("learning",{}).get("proposal"); proposal=None
    if raw:
        try:proposal=Proposal(**raw)
        except (TypeError,ValueError):proposal=None
    if proposal is not None:
        with _LOCK:_PENDING[proposal.proposal_id]=proposal
        report["proposal"]=asdict(proposal); _runtime().memory.append("proposal",asdict(proposal))
    return report

def format_report(report):
    metrics=report.get("metrics",{}); risk=report.get("risk",{}); findings=report.get("findings",[]); learning=report.get("learning",{})
    lines=["🤖 AI CHIEF INVESTMENT ANALYST","━━━━━━━━━━━━━━━━━━",f"Operaciones cerradas: {metrics.get('trades',0)}",f"Win rate: {_float(metrics.get('win_rate')):.1%}",f"Profit factor: {metrics.get('profit_factor')}",f"Expectancy: ${_float(metrics.get('expectancy')):+,.2f}",f"Drawdown máximo: {_float(metrics.get('max_drawdown')):.2%}",f"Exposición bruta: {_float(risk.get('gross_exposure_pct')):.2%}"]
    for finding in findings[:4]:lines.append(f"• {finding.get('severity','info').upper()}: {finding.get('message','')}")
    for observation in learning.get("observations",[])[:3]:lines.append(f"🧠 APRENDIZAJE: {observation}")
    proposal=report.get("proposal")
    if proposal:lines += ["","🧪 PROPUESTA PENDIENTE",f"ID: {proposal['proposal_id']}",f"Cambio: {proposal['changes']}",f"Motivo: {proposal['reason']}","Para aplicar: /ia aplicar <ID>"]
    return "\n".join(lines)

def command(command,broker):
    parts=str(command).strip().split()
    if not parts or parts[0].lower() not in {"/ia","/analista"}:return None
    if len(parts)==1 or parts[1].lower() in {"analiza","analizar","status"}:
        try:return format_report(analyze_now(broker))
        except Exception as exc:return f"❌ AI Analyst no pudo analizar: {exc}"
    if parts[1].lower() in {"aplicar","apply"}:
        if len(parts)!=3:return "Uso: /ia aplicar <ID_DE_PROPUESTA>"
        proposal_id=parts[2]
        with _LOCK:proposal=_PENDING.get(proposal_id)
        if proposal is None:return "❌ Propuesta inexistente, ya aplicada o caducada. Ejecuta /ia para obtener una nueva."
        try:
            token=authorize_proposal(proposal,"APLICAR"); current={key:getattr(config,key,None) for key in proposal.changes}; result=_runtime().apply(proposal,token,current)
            for key,value in result["config"].items():
                if key in proposal.changes:setattr(config,key,value)
            with _LOCK:_PENDING.pop(proposal_id,None)
            return f"✅ Propuesta {proposal_id} aplicada. Cambios: {proposal.changes}\n↩️ Rollback disponible en la auditoría/memoria."
        except Exception as exc:return f"❌ No se aplicó la propuesta: {exc}"
    return "Uso: /ia | /ia analizar | /ia aplicar <ID_DE_PROPUESTA>"

def _load_persisted_overrides():
    overrides=read_overrides(_runtime().override_path)
    if not overrides:return
    applied={}
    for key,value in overrides.items():
        if hasattr(config,key):
            setattr(config,key,value); applied[key]=value
    if applied:config.validar()

def _loop(broker):
    interval=max(60,int(os.environ.get("AI_ANALYST_INTERVAL_SECONDS","900")))
    while True:
        try:
            report=analyze_now(broker); critical=[x for x in report.get("findings",[]) if x.get("severity")=="critical"]
            if critical:
                import logging; logging.getLogger(__name__).warning("[AI] %s"," | ".join(x.get("message","") for x in critical))
        except Exception as exc:
            import logging; logging.getLogger(__name__).warning("[AI] análisis periódico omitido: %s",exc)
        time.sleep(interval)

def install(bot):
    global _STARTED
    if _STARTED:return
    _STARTED=True
    try:_load_persisted_overrides()
    except Exception as exc:bot.log.warning("[AI] overrides persistidos no cargados: %s",exc)
    original=getattr(bot,"procesar_comando_telegram",None)
    if callable(original):
        def wrapped(command_text):
            result=command(command_text,bot.broker); return original(command_text) if result is None else result
        bot.procesar_comando_telegram=wrapped
    enabled=os.environ.get("AI_ANALYST_ENABLED","true").strip().lower() in {"1","true","yes","si","sí"}
    if enabled:
        threading.Thread(target=_loop,args=(bot.broker,),daemon=True,name="AIInvestmentAnalyst").start(); bot.log.info("[AI] Chief Investment Analyst iniciado; intervalo=%ss",os.environ.get("AI_ANALYST_INTERVAL_SECONDS","900"))
