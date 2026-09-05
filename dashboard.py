"""Read-only professional trading terminal for BOTTRADE.

The dashboard only reads Alpaca data. It never places, cancels, or modifies
orders and does not alter BOTTRADE strategy or execution logic.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
API_KEY = os.environ.get("ALPACA_API_KEY", "")
API_SECRET = os.environ.get("ALPACA_API_SECRET", "")
PAPER = os.environ.get("ALPACA_PAPER", "true").strip().lower() in {"1", "true", "yes", "si", "sí", "on"}
BASE_URL = "https://paper-api.alpaca.markets" if PAPER else "https://api.alpaca.markets"

HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BOTTRADE · PRO TERMINAL</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e9eef7;background:#05080d;--panel:#0b111a;--panel2:#0e1622;--line:#1c2838;--muted:#74839a;--text:#e9eef7;--good:#42d995;--bad:#ff6575;--warn:#f2c463;--accent:#70a5ff;--cyan:#62d9e8}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1000px 520px at 70% -15%,#152a4d 0%,transparent 62%),#05080d;min-height:100vh}.wrap{max-width:1700px;margin:auto;padding:16px}.top{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:12px}.brand{font-size:21px;font-weight:900;letter-spacing:.04em}.brand span{color:#6d8ebc}.sub{color:var(--muted);font-size:11px;margin-top:3px}.actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.badge,.chip,.clock{border:1px solid var(--line);background:#0b131e;border-radius:7px;padding:7px 10px;font-size:11px;font-weight:800}.badge{color:var(--good);border-color:#23583f;background:#0a2118}.dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:currentColor;margin-right:6px}.clock{font-variant-numeric:tabular-nums;color:#aebbd0}.error{display:none;padding:10px 12px;margin-bottom:10px;border-radius:8px;background:#32151c;border:1px solid #66303b;color:#ffb5bf;font-size:12px}.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:8px}.card{background:linear-gradient(180deg,rgba(14,22,34,.98),rgba(8,13,21,.98));border:1px solid var(--line);border-radius:9px;padding:12px;box-shadow:0 8px 24px #0005}.kpi{grid-column:span 2;min-height:88px}.label{font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}.value{font-size:21px;font-weight:850;margin-top:7px;white-space:nowrap;font-variant-numeric:tabular-nums}.meta{font-size:10px;color:var(--muted);margin-top:4px}.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.cyan{color:var(--cyan)}.wide8{grid-column:span 8}.wide7{grid-column:span 7}.side5{grid-column:span 5}.side4{grid-column:span 4}.section{margin-top:8px}.sectionhead{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:9px}.section h2{font-size:12px;margin:0;letter-spacing:.03em}.muted{color:var(--muted);font-size:10px}.tabs{display:flex;gap:4px}.tabs button,button{border:1px solid var(--line);background:#0d1622;color:#b9c7d9;border-radius:6px;padding:6px 8px;font-size:10px;cursor:pointer}.tabs button.active{background:#172844;border-color:#35547e;color:#e7f0ff}.chart{height:255px;position:relative}.chart svg{width:100%;height:100%;overflow:visible}.chartline{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}.chartarea{fill:rgba(112,165,255,.08)}.gridline{stroke:#172333;stroke-width:1}.axis{fill:#5e6f87;font-size:9px}.table{overflow:auto;max-height:330px}.table table{width:100%;border-collapse:collapse;min-width:650px}.table th,.table td{text-align:left;padding:8px 7px;border-bottom:1px solid #172333;font-size:10px;white-space:nowrap}.table th{position:sticky;top:0;background:#0d1520;color:#6f7f96;font-weight:800;text-transform:uppercase;letter-spacing:.07em;z-index:1}.pill{display:inline-block;padding:3px 6px;border-radius:5px;background:#152033;color:#b2c0d3;font-size:9px}.pill.good{background:#0b251b;color:var(--good)}.pill.bad{background:#2b141a;color:var(--bad)}.two{display:grid;grid-template-columns:1fr 1fr;gap:7px}.metric{padding:10px;border:1px solid #172333;border-radius:7px;background:#080e17}.metric b{display:block;font-size:15px;margin-top:4px}.bars{display:grid;gap:8px}.barrow{display:grid;grid-template-columns:72px 1fr 48px;gap:7px;align-items:center;font-size:10px}.bar{height:7px;background:#111d2c;border-radius:99px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);border-radius:99px}.health{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.health .metric{min-height:68px}.status{display:flex;align-items:center;gap:6px;margin-top:7px;font-size:11px}.statusdot{width:7px;height:7px;border-radius:50%;background:var(--good)}.empty{padding:24px;text-align:center;color:var(--muted);font-size:10px}.footer{padding:12px 2px 3px;color:#4d5c71;font-size:9px}.notice{padding:8px 10px;border:1px solid #3e3420;background:#17140c;color:#cdbb88;border-radius:7px;font-size:10px;line-height:1.4}
@media(max-width:1200px){.kpi{grid-column:span 3}.wide8,.wide7{grid-column:span 8}.side5,.side4{grid-column:span 4}}@media(max-width:760px){.wrap{padding:10px}.top{align-items:flex-start;flex-direction:column}.grid{grid-template-columns:1fr}.kpi,.wide8,.wide7,.side5,.side4{grid-column:span 1}.health{grid-template-columns:1fr 1fr}.chart{height:210px}.actions{width:100%}}
</style></head><body><div class="wrap">
<header class="top"><div><div class="brand">BOTTRADE <span>PRO TERMINAL</span></div><div class="sub">Portfolio · execution · risk · performance · broker telemetry</div></div><div class="actions"><div id="mode" class="badge"><span class="dot"></span>PAPER</div><div id="broker" class="chip">Broker: —</div><div id="market" class="chip">Market: —</div><div id="updated" class="clock">—</div><button onclick="load()">↻ Refresh</button></div></header>
<div id="error" class="error"></div>
<div class="grid">
<div class="card kpi"><div class="label">Net liquidation</div><div id="equity" class="value">—</div><div class="meta">Equity / cuenta</div></div>
<div class="card kpi"><div class="label">Cash</div><div id="cash" class="value">—</div><div class="meta">Efectivo</div></div>
<div class="card kpi"><div class="label">Buying power</div><div id="bp" class="value">—</div><div class="meta">Poder de compra</div></div>
<div class="card kpi"><div class="label">P&amp;L hoy</div><div id="pnl" class="value">—</div><div id="pnlmeta" class="meta">—</div></div>
<div class="card kpi"><div class="label">Posiciones</div><div id="poscount" class="value">—</div><div class="meta">Abiertas</div></div>
<div class="card kpi"><div class="label">Open orders</div><div id="opencount" class="value">—</div><div class="meta">Pendientes</div></div>
</div>
<div class="grid section">
<div class="card wide8"><div class="sectionhead"><h2>EQUITY CURVE</h2><div class="tabs"><button class="active" onclick="setPeriod('1D',this)">1D</button><button onclick="setPeriod('1W',this)">1W</button><button onclick="setPeriod('1M',this)">1M</button><button onclick="setPeriod('1A',this)">1A</button></div></div><div id="chart" class="chart"><div class="empty">Cargando histórico…</div></div></div>
<div class="card side4"><div class="sectionhead"><h2>PERFORMANCE</h2><span class="muted">historial Alpaca</span></div><div class="two"><div class="metric"><div class="label">Retorno</div><b id="ret">—</b></div><div class="metric"><div class="label">Max drawdown</div><b id="dd">—</b></div><div class="metric"><div class="label">Peak equity</div><b id="peak">—</b></div><div class="metric"><div class="label">Muestras</div><b id="samples">—</b></div></div><div style="height:7px"></div><div class="notice" id="datastatus">Estado: —</div></div>
</div>
<div class="grid section">
<div class="card wide7"><div class="sectionhead"><h2>OPEN POSITIONS</h2><span id="possummary" class="muted">—</span></div><div id="positions" class="table"><div class="empty">Cargando…</div></div></div>
<div class="card side5"><div class="sectionhead"><h2>RISK &amp; EXPOSURE</h2><span class="muted">visible desde cuenta</span></div><div class="two"><div class="metric"><div class="label">Gross exposure</div><b id="invested">—</b></div><div class="metric"><div class="label">Unrealized P&amp;L</div><b id="unrealized">—</b></div><div class="metric"><div class="label">Largest position</div><b id="largest">—</b></div><div class="metric"><div class="label">Concentration</div><b id="concentration">—</b></div></div><div style="height:9px"></div><div class="bars"><div class="barrow"><span>Stocks</span><div class="bar"><i id="stockbar" style="width:0%"></i></div><b id="stockpct">—</b></div><div class="barrow"><span>Crypto</span><div class="bar"><i id="cryptobar" style="width:0%"></i></div><b id="cryptopct">—</b></div><div class="barrow"><span>Cash</span><div class="bar"><i id="cashbar" style="width:0%"></i></div><b id="cashpct">—</b></div></div></div>
</div>
<div class="grid section">
<div class="card side5"><div class="sectionhead"><h2>EXECUTION CENTER</h2><span id="execmeta" class="muted">—</span></div><div class="two"><div class="metric"><div class="label">Fills</div><b id="fillsn">—</b></div><div class="metric"><div class="label">Buy / Sell</div><b id="buysell">—</b></div><div class="metric"><div class="label">Filled orders</div><b id="filledorders">—</b></div><div class="metric"><div class="label">Open orders</div><b id="execopen">—</b></div></div></div>
<div class="card side5"><div class="sectionhead"><h2>ACCOUNT TELEMETRY</h2><span class="muted">Alpaca</span></div><div class="health"><div class="metric"><div class="label">Broker API</div><div id="apihealth" class="status"><i class="statusdot"></i>—</div></div><div class="metric"><div class="label">Trading mode</div><div id="modehealth" class="status"><i class="statusdot"></i>—</div></div><div class="metric"><div class="label">Market clock</div><div id="clockhealth" class="status"><i class="statusdot"></i>—</div></div><div class="metric"><div class="label">Data history</div><div id="historyhealth" class="status"><i class="statusdot"></i>—</div></div></div></div>
</div>
<div class="section card"><div class="sectionhead"><h2>RECENT ORDERS</h2><span id="ordersmeta" class="muted">—</span></div><div id="orders" class="table"><div class="empty">Cargando…</div></div></div>
<div class="section card"><div class="sectionhead"><h2>FILL ACTIVITY</h2><span class="muted">últimas ejecuciones reportadas por Alpaca</span></div><div id="fills" class="table"><div class="empty">Cargando…</div></div></div>
<div class="footer">READ-ONLY TERMINAL · No crea, cancela ni modifica órdenes. No cambia estrategia ni ejecución de BOTTRADE. Las métricas de rendimiento se muestran solo sobre datos disponibles y no convierten señales en rentabilidad realizada.</div>
</div><script>
let period='1D';
const money=n=>n==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(Number(n));
const num=n=>n==null?'—':new Intl.NumberFormat('en-US',{maximumFractionDigits:4}).format(Number(n));
const pct=n=>n==null?'—':(Number(n)>=0?'+':'')+Number(n).toFixed(2)+'%';
const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
const cls=n=>Number(n)>=0?'good':'bad';
function pill(v){const s=String(v??'');const c=/filled|fill|open|accepted|new/i.test(s)?'good':/rejected|canceled|expired/i.test(s)?'bad':'';return `<span class="pill ${c}">${esc(s)}</span>`}
function renderPositions(items){if(!items?.length)return '<div class="empty">Sin posiciones abiertas.</div>';return '<table><thead><tr><th>Symbol</th><th>Qty</th><th>Avg entry</th><th>Last</th><th>Market value</th><th>Unrealized</th><th>Return</th></tr></thead><tbody>'+items.map(x=>`<tr><td><b>${esc(x.symbol)}</b></td><td>${num(x.qty)}</td><td>${money(x.avg_entry_price)}</td><td>${money(x.current_price)}</td><td>${money(x.market_value)}</td><td class="${cls(x.unrealized_pl)}">${money(x.unrealized_pl)}</td><td class="${cls(x.unrealized_plpc)}">${pct(Number(x.unrealized_plpc)*100)}</td></tr>`).join('')+'</tbody></table>'}
function renderOrders(items){if(!items?.length)return '<div class="empty">Sin órdenes recientes.</div>';return '<table><thead><tr><th>Created</th><th>Symbol</th><th>Side</th><th>Type</th><th>Qty</th><th>Status</th><th>Filled qty</th><th>Avg fill</th></tr></thead><tbody>'+items.map(x=>`<tr><td>${esc(x.created_at)}</td><td><b>${esc(x.symbol)}</b></td><td>${esc(x.side)}</td><td>${esc(x.type)}</td><td>${esc(x.qty)}</td><td>${pill(x.status)}</td><td>${esc(x.filled_qty??'—')}</td><td>${x.filled_avg_price?money(x.filled_avg_price):'—'}</td></tr>`).join('')+'</tbody></table>'}
function renderFills(items){if(!items?.length)return '<div class="empty">Sin fills recientes.</div>';return '<table><thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Activity</th></tr></thead><tbody>'+items.map(x=>`<tr><td>${esc(x.date)}</td><td><b>${esc(x.symbol)}</b></td><td>${esc(x.side)}</td><td>${esc(x.qty)}</td><td>${money(x.price)}</td><td>${pill(x.activity_type||'FILL')}</td></tr>`).join('')+'</tbody></table>'}
function drawChart(points){const el=document.getElementById('chart');if(!points?.length){el.innerHTML='<div class="empty">No hay suficiente historial para este periodo.</div>';return}const vals=points.map(x=>Number(x.equity)).filter(Number.isFinite);if(vals.length<2){el.innerHTML='<div class="empty">Historial insuficiente.</div>';return}const w=1000,h=235,p=24,min=Math.min(...vals),max=Math.max(...vals),span=max-min||1;const xy=vals.map((v,i)=>[p+(i/(vals.length-1))*(w-2*p),h-p-((v-min)/span)*(h-2*p)]);const path=xy.map((a,i)=>(i?'L':'M')+a[0].toFixed(1)+' '+a[1].toFixed(1)).join(' ');const area=path+' L '+xy.at(-1)[0].toFixed(1)+' '+(h-p)+' L '+xy[0][0].toFixed(1)+' '+(h-p)+' Z';el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><line class="gridline" x1="${p}" y1="${p}" x2="${w-p}" y2="${p}"/><line class="gridline" x1="${p}" y1="${h/2}" x2="${w-p}" y2="${h/2}"/><line class="gridline" x1="${p}" y1="${h-p}" x2="${w-p}" y2="${h-p}"/><path class="chartarea" d="${area}"/><path class="chartline" d="${path}"/><text class="axis" x="${p}" y="14">${money(max)}</text><text class="axis" x="${p}" y="${h/2-4}">${money((max+min)/2)}</text><text class="axis" x="${p}" y="${h-3}">${money(min)}</text><text class="axis" x="${w-p-110}" y="14">${esc(points.at(-1).label||'now')}</text></svg>`}
function setPeriod(p,btn){period=p;document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));btn.classList.add('active');load()}
function setHealth(id,ok,text){const el=document.getElementById(id);el.innerHTML=`<i class="statusdot" style="background:${ok?'var(--good)':'var(--bad)'}"></i>${esc(text)}`}
async function load(){try{const r=await fetch('/api/state?period='+period,{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'No se pudo cargar el estado');document.getElementById('error').style.display='none';document.getElementById('mode').innerHTML='<span class="dot"></span>'+esc(d.mode);document.getElementById('broker').textContent='Broker: '+(d.health?'OK':'ERROR');document.getElementById('market').textContent='Market: '+esc(d.clock.status);document.getElementById('updated').textContent=new Date(d.timestamp).toLocaleTimeString();document.getElementById('equity').textContent=money(d.account.equity);document.getElementById('cash').textContent=money(d.account.cash);document.getElementById('bp').textContent=money(d.account.buying_power);document.getElementById('pnl').textContent=money(d.account.day_pnl);document.getElementById('pnl').className='value '+cls(d.account.day_pnl);document.getElementById('pnlmeta').textContent=d.account.day_pnl_source;document.getElementById('poscount').textContent=d.positions.length;document.getElementById('opencount').textContent=d.open_orders;document.getElementById('positions').innerHTML=renderPositions(d.positions);document.getElementById('orders').innerHTML=renderOrders(d.orders);document.getElementById('fills').innerHTML=renderFills(d.fills);document.getElementById('ordersmeta').textContent=d.orders.length+' visibles · '+d.open_orders+' abiertas';document.getElementById('possummary').textContent=money(d.risk.invested)+' gross exposure';document.getElementById('invested').textContent=money(d.risk.invested);document.getElementById('unrealized').textContent=money(d.risk.unrealized);document.getElementById('unrealized').className=Number(d.risk.unrealized)>=0?'good':'bad';document.getElementById('largest').textContent=d.risk.largest_symbol||'—';document.getElementById('concentration').textContent=d.risk.concentration==null?'—':d.risk.concentration.toFixed(1)+'%';['stock','crypto','cash'].forEach(k=>{document.getElementById(k+'bar').style.width=Math.min(100,d.risk[k+'pct']||0)+'%';document.getElementById(k+'pct').textContent=(d.risk[k+'pct']??0).toFixed(1)+'%' });document.getElementById('fillsn').textContent=d.execution.fills;document.getElementById('buysell').textContent=d.execution.buys+' / '+d.execution.sells;document.getElementById('filledorders').textContent=d.execution.filled_orders;document.getElementById('execopen').textContent=d.open_orders;document.getElementById('execmeta').textContent=d.execution.window;setHealth('apihealth',d.health,'Connected');setHealth('modehealth',true,d.mode);setHealth('clockhealth',true,d.clock.status+(d.clock.is_open?' · open':' · closed'));setHealth('historyhealth',d.history.status==='OK',d.history.status);drawChart(d.history.points);document.getElementById('ret').textContent=pct(d.history.return_pct);document.getElementById('ret').className=Number(d.history.return_pct)>=0?'good':'bad';document.getElementById('dd').textContent=pct(d.history.max_drawdown_pct);document.getElementById('dd').className=Number(d.history.max_drawdown_pct)>=0?'good':'bad';document.getElementById('peak').textContent=money(d.history.peak);document.getElementById('samples').textContent=d.history.points.length;document.getElementById('datastatus').textContent='Estado de datos: '+d.history.status}catch(e){const el=document.getElementById('error');el.textContent=e.message;el.style.display='block'}}load();setInterval(load,15000);
</script></body></html>'''


def alpaca_get(path: str, params: dict | None = None):
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Faltan credenciales de Alpaca en el servicio dashboard")
    response = requests.get(f"{BASE_URL}{path}", headers={"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": API_SECRET}, params=params, timeout=12)
    response.raise_for_status()
    return response.json()


def _history(period: str):
    period = period if period in {"1D", "1W", "1M", "1A"} else "1D"
    timeframe = {"1D":"5Min","1W":"15Min","1M":"1H","1A":"1D"}[period]
    try:
        h = alpaca_get("/v2/account/portfolio/history", {"period": period, "timeframe": timeframe, "extended_hours": "true"})
        eq, ts = h.get("equity") or [], h.get("timestamp") or []
        points=[]
        for i,value in enumerate(eq):
            if value is None: continue
            try:
                label=datetime.fromtimestamp(float(ts[i]),timezone.utc).strftime("%d/%m %H:%M") if i<len(ts) and ts[i] else ""
                points.append({"equity":float(value),"label":label})
            except (TypeError,ValueError): pass
        vals=[p["equity"] for p in points]
        if len(vals)<2: return {"points":points,"return_pct":None,"max_drawdown_pct":None,"peak":max(vals) if vals else None,"status":"Historial insuficiente"}
        peak=vals[0]; max_dd=0.0
        for v in vals:
            peak=max(peak,v)
            if peak: max_dd=min(max_dd,(v/peak-1)*100)
        ret=(vals[-1]/vals[0]-1)*100 if vals[0] else None
        return {"points":points,"return_pct":ret,"max_drawdown_pct":max_dd,"peak":max(vals),"status":"OK"}
    except requests.RequestException:
        return {"points":[],"return_pct":None,"max_drawdown_pct":None,"peak":None,"status":"No disponible"}


def state(period: str):
    account=alpaca_get("/v2/account")
    positions=alpaca_get("/v2/positions")
    orders=alpaca_get("/v2/orders",{"status":"all","limit":50,"direction":"desc","nested":"false"})
    open_orders=alpaca_get("/v2/orders",{"status":"open","limit":50,"direction":"desc","nested":"false"})
    fills=[]
    try:
        activities=alpaca_get("/v2/account/activities/FILL",{"direction":"desc","page_size":50})
        if isinstance(activities,list):
            for a in activities:
                fills.append({"date":a.get("transaction_time") or a.get("date"),"symbol":a.get("symbol"),"side":a.get("side"),"qty":a.get("qty"),"price":a.get("price"),"activity_type":a.get("activity_type") or "FILL"})
    except requests.RequestException: pass
    day_pnl=None; pnl_source="No disponible"
    try:
        h=alpaca_get("/v2/account/portfolio/history",{"period":"1D","timeframe":"5Min","extended_hours":"true"})
        pl=h.get("profit_loss") or []; eq=h.get("equity") or []
        if pl and pl[-1] is not None: day_pnl=float(pl[-1]); pnl_source="Alpaca portfolio history · 1D"
        elif len(eq)>=2 and eq[0] is not None and eq[-1] is not None: day_pnl=float(eq[-1])-float(eq[0]); pnl_source="Alpaca equity history · 1D"
    except requests.RequestException: pass
    invested=sum(float(p.get("market_value") or 0) for p in positions)
    unrealized=sum(float(p.get("unrealized_pl") or 0) for p in positions)
    largest=max(positions,key=lambda p:abs(float(p.get("market_value") or 0)),default=None)
    equity=float(account.get("equity") or 0); cash=float(account.get("cash") or 0)
    concentration=abs(float(largest.get("market_value") or 0))/equity*100 if largest and equity else None
    stock_value=sum(abs(float(p.get("market_value") or 0)) for p in positions if "/" not in str(p.get("symbol") or ""))
    crypto_value=sum(abs(float(p.get("market_value") or 0)) for p in positions if "/" in str(p.get("symbol") or ""))
    denom=equity or (stock_value+crypto_value+abs(cash)) or 1
    clean_positions=[{k:p.get(k) for k in ("symbol","qty","avg_entry_price","current_price","market_value","unrealized_pl","unrealized_plpc")} for p in positions]
    clean_orders=[{k:o.get(k) for k in ("created_at","symbol","side","type","qty","status","filled_qty","filled_avg_price")} for o in orders]
    buys=sum(1 for f in fills if str(f.get("side")).lower()=="buy"); sells=sum(1 for f in fills if str(f.get("side")).lower()=="sell")
    filled_orders=sum(1 for o in orders if str(o.get("status")).lower()=="filled")
    try:
        clock=alpaca_get("/v2/clock")
        clock_status="OPEN" if clock.get("is_open") else "CLOSED"
        clock_info={"status":clock_status,"is_open":bool(clock.get("is_open")),"next_open":clock.get("next_open"),"next_close":clock.get("next_close")}
    except requests.RequestException:
        clock_info={"status":"UNKNOWN","is_open":False,"next_open":None,"next_close":None}
    return {"mode":"PAPER" if PAPER else "LIVE","health":True,"account":{"equity":account.get("equity"),"cash":account.get("cash"),"buying_power":account.get("buying_power"),"day_pnl":day_pnl,"day_pnl_source":pnl_source},"positions":clean_positions,"orders":clean_orders,"fills":fills,"open_orders":len(open_orders),"risk":{"invested":invested,"unrealized":unrealized,"largest_symbol":largest.get("symbol") if largest else None,"concentration":concentration,"stockpct":stock_value/denom*100,"cryptopct":crypto_value/denom*100,"cashpct":abs(cash)/denom*100},"execution":{"fills":len(fills),"buys":buys,"sells":sells,"filled_orders":filled_orders,"window":"últimos 50 fills"},"clock":clock_info,"history":_history(period),"timestamp":datetime.now(timezone.utc).isoformat()}


class Handler(BaseHTTPRequestHandler):
    def send(self,status:int,body:bytes,content_type:str):
        self.send_response(status); self.send_header("Content-Type",content_type); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=urlparse(self.path).path
        if path in {"/","/index.html"}: self.send(200,HTML.encode(),"text/html; charset=utf-8"); return
        if path in {"/health","/healthz"}: self.send(200,b'{"ok":true,"service":"bottrade-dashboard","read_only":true}',"application/json"); return
        if path=="/api/state":
            try:
                q=parse_qs(urlparse(self.path).query); period=(q.get("period") or ["1D"])[0]
                self.send(200,json.dumps(state(period),separators=(",",":")).encode(),"application/json; charset=utf-8")
            except Exception as exc:
                self.send(503,json.dumps({"error":str(exc)}).encode(),"application/json; charset=utf-8")
            return
        self.send(404,b'{"error":"not found"}',"application/json")
    def log_message(self,*_args): return


if __name__ == "__main__":
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
