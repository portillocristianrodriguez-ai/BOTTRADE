"""Professional read-only dashboard for BOTTRADE.

This service never places, cancels, or modifies orders. It only reads the
Alpaca account configured for BOTTRADE and exposes operational/performance
observability for Paper Trading.
"""
from __future__ import annotations

import json
import math
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
<title>BOTTRADE · Command Center</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e8eef7;background:#070b12;--panel:#0d1420;--panel2:#111a28;--line:#202d40;--muted:#8493a8;--text:#e8eef7;--good:#54e39b;--bad:#ff6b7a;--warn:#f5c86b;--accent:#76a9ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 500px at 75% -10%,#142342 0%,transparent 65%),#070b12;min-height:100vh}.wrap{max-width:1500px;margin:auto;padding:24px}.top{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:18px}.brand{font-size:26px;font-weight:850;letter-spacing:.2px}.sub{color:var(--muted);font-size:13px;margin-top:4px}.actions{display:flex;align-items:center;gap:9px}.badge,.chip{border:1px solid var(--line);background:#0e1724;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:800}.badge{color:var(--good);border-color:#23563f;background:#0c2419}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:currentColor;margin-right:7px}.refresh{color:var(--muted)}button{border:1px solid var(--line);background:#111a28;color:var(--text);border-radius:9px;padding:8px 11px;cursor:pointer}button:hover{border-color:#38506e}.error{display:none;padding:11px 13px;margin:0 0 15px;border-radius:10px;background:#32151c;border:1px solid #66303b;color:#ffb5bf}.grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}.card{background:linear-gradient(180deg,rgba(17,26,40,.96),rgba(11,17,27,.96));border:1px solid var(--line);border-radius:14px;padding:15px;box-shadow:0 10px 30px #0004}.label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.value{font-size:23px;font-weight:800;margin-top:8px;white-space:nowrap}.meta{font-size:11px;color:var(--muted);margin-top:5px}.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.section{margin-top:12px}.sectionhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.section h2{font-size:15px;margin:0}.muted{color:var(--muted);font-size:12px}.wide{grid-column:span 4}.side{grid-column:span 2}.chart{height:245px;position:relative}.chart svg{width:100%;height:100%;overflow:visible}.chartline{fill:none;stroke:var(--accent);stroke-width:2.2;vector-effect:non-scaling-stroke}.chartarea{fill:rgba(118,169,255,.10)}.gridline{stroke:#1b2636;stroke-width:1}.axis{fill:#64748a;font-size:10px}.table{overflow:auto;max-height:420px}.table table{width:100%;border-collapse:collapse;min-width:720px}.table th,.table td{text-align:left;padding:10px 9px;border-bottom:1px solid #1c2736;font-size:12px}.table th{position:sticky;top:0;background:#0f1724;color:#718198;font-weight:700;text-transform:uppercase;letter-spacing:.05em}.pill{display:inline-block;padding:4px 7px;border-radius:7px;background:#172235;color:#a9b8cd;font-size:11px}.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}.metric{padding:12px;border:1px solid #1c2736;border-radius:10px;background:#0a111c}.metric b{display:block;font-size:17px;margin-top:4px}.footer{padding:14px 2px 4px;color:#56657a;font-size:11px}.tabs{display:flex;gap:6px}.tabs button.active{background:#1a2a42;border-color:#365276;color:#dce9ff}.empty{padding:25px;text-align:center;color:var(--muted);font-size:12px}@media(max-width:1150px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.wide{grid-column:span 2}.side{grid-column:span 1}}@media(max-width:700px){.wrap{padding:14px}.top{align-items:flex-start;flex-direction:column}.grid{grid-template-columns:1fr}.wide,.side{grid-column:span 1}.two{grid-template-columns:1fr}.actions{width:100%;justify-content:space-between}.chart{height:210px}}
</style></head><body><div class="wrap">
<header class="top"><div><div class="brand">BOTTRADE <span style="color:#6e8fbf">COMMAND CENTER</span></div><div class="sub">Trading operations · risk · performance · broker telemetry</div></div><div class="actions"><div id="mode" class="badge"><span class="dot"></span>PAPER</div><div id="health" class="chip">Broker: —</div><button onclick="load()">Actualizar</button></div></header>
<div id="error" class="error"></div>
<div class="grid">
<div class="card"><div class="label">Equity</div><div id="equity" class="value">—</div><div class="meta">Cuenta Alpaca</div></div>
<div class="card"><div class="label">Cash</div><div id="cash" class="value">—</div><div class="meta">Disponible</div></div>
<div class="card"><div class="label">Buying power</div><div id="bp" class="value">—</div><div class="meta">Capacidad de compra</div></div>
<div class="card"><div class="label">P&amp;L hoy</div><div id="pnl" class="value">—</div><div id="pnlMeta" class="meta">—</div></div>
<div class="card"><div class="label">Posiciones</div><div id="posCount" class="value">—</div><div class="meta">Abiertas ahora</div></div>
<div class="card"><div class="label">Órdenes activas</div><div id="openCount" class="value">—</div><div class="meta">Pendientes / abiertas</div></div>
</div>
<div class="grid section">
<div class="card wide"><div class="sectionhead"><h2>Equity curve</h2><div class="tabs"><button class="active" data-period="1D" onclick="setPeriod('1D',this)">1D</button><button data-period="1W" onclick="setPeriod('1W',this)">1W</button><button data-period="1M" onclick="setPeriod('1M',this)">1M</button><button data-period="1A" onclick="setPeriod('1A',this)">1A</button></div></div><div id="chart" class="chart"><div class="empty">Cargando histórico…</div></div></div>
<div class="card side"><div class="sectionhead"><h2>Performance</h2><span class="muted">calculada sobre historial disponible</span></div><div class="two"><div class="metric"><div class="label">Retorno periodo</div><b id="ret">—</b></div><div class="metric"><div class="label">Máx. drawdown</div><b id="dd">—</b></div><div class="metric"><div class="label">Mejor punto</div><b id="peak">—</b></div><div class="metric"><div class="label">Muestras</div><b id="samples">—</b></div></div><div style="height:10px"></div><div class="metric"><div class="label">Estado de datos</div><b id="dataStatus">—</b></div></div>
</div>
<div class="grid section">
<div class="card wide"><div class="sectionhead"><h2>Posiciones abiertas</h2><span id="posSummary" class="muted">—</span></div><div id="positions" class="table"><div class="empty">Cargando…</div></div></div>
<div class="card side"><div class="sectionhead"><h2>Riesgo visible</h2><span class="muted">cuenta actual</span></div><div class="two"><div class="metric"><div class="label">Valor invertido</div><b id="invested">—</b></div><div class="metric"><div class="label">P&amp;L abierto</div><b id="unrealized">—</b></div><div class="metric"><div class="label">Mayor posición</div><b id="largest">—</b></div><div class="metric"><div class="label">Concentración</div><b id="concentration">—</b></div></div></div>
</div>
<div class="section card"><div class="sectionhead"><h2>Órdenes recientes</h2><span id="ordersMeta" class="muted">—</span></div><div id="orders" class="table"><div class="empty">Cargando…</div></div></div>
<div class="section card"><div class="sectionhead"><h2>Actividad de fills</h2><span class="muted">últimas ejecuciones reportadas por Alpaca</span></div><div id="fills" class="table"><div class="empty">Cargando…</div></div></div>
<div class="footer">Solo lectura. BOTTRADE COMMAND CENTER no crea, cancela ni modifica órdenes. Actualización automática cada 15 s. Los indicadores de rendimiento requieren historial suficiente; no se presenta rentabilidad estimada como si fuera realizada.</div>
</div><script>
let period='1D';
const money=n=>n==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(Number(n));
const num=n=>n==null?'—':new Intl.NumberFormat('en-US',{maximumFractionDigits:4}).format(Number(n));
const pct=n=>n==null?'—':(Number(n)>=0?'+':'')+Number(n).toFixed(2)+'%';
const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
const cls=n=>Number(n)>=0?'good':'bad';
function renderPositions(items){if(!items?.length)return '<div class="empty">Sin posiciones abiertas.</div>';return '<table><thead><tr><th>Símbolo</th><th>Qty</th><th>Entrada</th><th>Actual</th><th>Valor</th><th>P&amp;L</th><th>P&amp;L %</th></tr></thead><tbody>'+items.map(x=>`<tr><td><b>${esc(x.symbol)}</b></td><td>${num(x.qty)}</td><td>${money(x.avg_entry_price)}</td><td>${money(x.current_price)}</td><td>${money(x.market_value)}</td><td class="${cls(x.unrealized_pl)}">${money(x.unrealized_pl)}</td><td class="${cls(x.unrealized_plpc)}">${pct(Number(x.unrealized_plpc)*100)}</td></tr>`).join('')+'</tbody></table>'}
function renderOrders(items){if(!items?.length)return '<div class="empty">Sin órdenes recientes.</div>';return '<table><thead><tr><th>Fecha</th><th>Símbolo</th><th>Side</th><th>Tipo</th><th>Qty</th><th>Status</th><th>Fill</th></tr></thead><tbody>'+items.map(x=>`<tr><td>${esc(x.created_at)}</td><td><b>${esc(x.symbol)}</b></td><td>${esc(x.side)}</td><td>${esc(x.type)}</td><td>${esc(x.qty)}</td><td><span class="pill">${esc(x.status)}</span></td><td>${x.filled_avg_price?money(x.filled_avg_price):'—'}</td></tr>`).join('')+'</tbody></table>'}
function renderFills(items){if(!items?.length)return '<div class="empty">Sin fills recientes.</div>';return '<table><thead><tr><th>Fecha</th><th>Símbolo</th><th>Side</th><th>Qty</th><th>Precio</th><th>Actividad</th></tr></thead><tbody>'+items.map(x=>`<tr><td>${esc(x.date)}</td><td><b>${esc(x.symbol)}</b></td><td>${esc(x.side)}</td><td>${esc(x.qty)}</td><td>${money(x.price)}</td><td><span class="pill">${esc(x.activity_type)}</span></td></tr>`).join('')+'</tbody></table>'}
function drawChart(points){const el=document.getElementById('chart');if(!points?.length){el.innerHTML='<div class="empty">No hay suficiente historial para este periodo.</div>';return}const w=900,h=220,p=22;const vals=points.map(x=>Number(x.equity)).filter(Number.isFinite);if(!vals.length){el.innerHTML='<div class="empty">Histórico no disponible.</div>';return}const min=Math.min(...vals),max=Math.max(...vals),span=max-min||1;const xy=vals.map((v,i)=>[p+(i/(Math.max(vals.length-1,1)))*(w-2*p),h-p-((v-min)/span)*(h-2*p)]);const path=xy.map((a,i)=>(i?'L':'M')+a[0].toFixed(1)+' '+a[1].toFixed(1)).join(' ');const area=path+' L '+xy.at(-1)[0].toFixed(1)+' '+(h-p)+' L '+xy[0][0].toFixed(1)+' '+(h-p)+' Z';el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><line class="gridline" x1="${p}" y1="${p}" x2="${w-p}" y2="${p}"/><line class="gridline" x1="${p}" y1="${h-p}" x2="${w-p}" y2="${h-p}"/><path class="chartarea" d="${area}"/><path class="chartline" d="${path}"/><text class="axis" x="${p}" y="14">${money(max)}</text><text class="axis" x="${p}" y="${h-3}">${money(min)}</text><text class="axis" x="${w-p-90}" y="14">${esc(points[points.length-1].label||'ahora')}</text></svg>`}
function setPeriod(p,btn){period=p;document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));btn.classList.add('active');load()}
async function load(){try{const r=await fetch('/api/state?period='+period,{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'No se pudo cargar el estado');document.getElementById('error').style.display='none';document.getElementById('mode').innerHTML='<span class="dot"></span>'+esc(d.mode);document.getElementById('health').textContent='Broker: '+(d.health?'OK':'ERROR');document.getElementById('equity').textContent=money(d.account.equity);document.getElementById('cash').textContent=money(d.account.cash);document.getElementById('bp').textContent=money(d.account.buying_power);const pnl=d.account.day_pnl;document.getElementById('pnl').textContent=money(pnl);document.getElementById('pnl').className='value '+cls(pnl);document.getElementById('pnlMeta').textContent=d.account.day_pnl_source;document.getElementById('posCount').textContent=d.positions.length;document.getElementById('openCount').textContent=d.open_orders;document.getElementById('positions').innerHTML=renderPositions(d.positions);document.getElementById('orders').innerHTML=renderOrders(d.orders);document.getElementById('fills').innerHTML=renderFills(d.fills);document.getElementById('ordersMeta').textContent=d.orders.length+' visibles · '+d.open_orders+' activas';document.getElementById('posSummary').textContent=money(d.risk.invested)+' invertido';document.getElementById('invested').textContent=money(d.risk.invested);document.getElementById('unrealized').textContent=money(d.risk.unrealized);document.getElementById('unrealized').className=Number(d.risk.unrealized)>=0?'good':'bad';document.getElementById('largest').textContent=d.risk.largest_symbol||'—';document.getElementById('concentration').textContent=d.risk.concentration==null?'—':d.risk.concentration.toFixed(1)+'%';drawChart(d.history.points);document.getElementById('ret').textContent=pct(d.history.return_pct);document.getElementById('ret').className=Number(d.history.return_pct)>=0?'good':'bad';document.getElementById('dd').textContent=pct(d.history.max_drawdown_pct);document.getElementById('dd').className=Number(d.history.max_drawdown_pct)>=0?'good':'bad';document.getElementById('peak').textContent=money(d.history.peak);document.getElementById('samples').textContent=d.history.points.length;document.getElementById('dataStatus').textContent=d.history.status;document.getElementById('dataStatus').className=d.history.status==='OK'?'good':'warn'}catch(e){const el=document.getElementById('error');el.textContent=e.message;el.style.display='block'}}load();setInterval(load,15000);
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
        eq = h.get("equity") or []
        ts = h.get("timestamp") or []
        points = []
        for i, value in enumerate(eq):
            if value is None:
                continue
            try:
                label = datetime.fromtimestamp(float(ts[i]), timezone.utc).strftime("%d/%m %H:%M") if i < len(ts) and ts[i] else ""
                points.append({"equity": float(value), "label": label})
            except (TypeError, ValueError):
                continue
        vals = [p["equity"] for p in points]
        if len(vals) < 2:
            return {"points": points, "return_pct": None, "max_drawdown_pct": None, "peak": max(vals) if vals else None, "status": "Historial insuficiente"}
        peak = vals[0]; max_dd = 0.0
        for v in vals:
            peak = max(peak, v)
            if peak:
                max_dd = min(max_dd, (v / peak - 1.0) * 100.0)
        ret = (vals[-1] / vals[0] - 1.0) * 100.0 if vals[0] else None
        return {"points": points, "return_pct": ret, "max_drawdown_pct": max_dd, "peak": max(vals), "status": "OK"}
    except requests.RequestException:
        return {"points": [], "return_pct": None, "max_drawdown_pct": None, "peak": None, "status": "No disponible"}


def state(period: str):
    account = alpaca_get("/v2/account")
    positions = alpaca_get("/v2/positions")
    orders = alpaca_get("/v2/orders", {"status":"all", "limit":50, "direction":"desc", "nested":"false"})
    open_orders = alpaca_get("/v2/orders", {"status":"open", "limit":50, "direction":"desc", "nested":"false"})
    fills = []
    try:
        activities = alpaca_get("/v2/account/activities/FILL", {"direction":"desc", "page_size":50})
        if isinstance(activities, list):
            for a in activities:
                fills.append({"date":a.get("transaction_time") or a.get("date"),"symbol":a.get("symbol"),"side":a.get("side"),"qty":a.get("qty"),"price":a.get("price"),"activity_type":a.get("activity_type") or "FILL"})
    except requests.RequestException:
        pass
    day_pnl = None; pnl_source = "No disponible"
    try:
        h = alpaca_get("/v2/account/portfolio/history", {"period":"1D", "timeframe":"5Min", "extended_hours":"true"})
        pl = h.get("profit_loss") or []
        eq = h.get("equity") or []
        if pl and pl[-1] is not None:
            day_pnl = float(pl[-1]); pnl_source = "Alpaca portfolio history · 1D"
        elif len(eq) >= 2 and eq[0] is not None and eq[-1] is not None:
            day_pnl = float(eq[-1])-float(eq[0]); pnl_source = "Alpaca equity history · 1D"
    except requests.RequestException:
        pass
    invested = sum(float(p.get("market_value") or 0) for p in positions)
    unrealized = sum(float(p.get("unrealized_pl") or 0) for p in positions)
    largest = max(positions, key=lambda p: abs(float(p.get("market_value") or 0)), default=None)
    equity = float(account.get("equity") or 0)
    concentration = abs(float(largest.get("market_value") or 0))/equity*100 if largest and equity else None
    clean_positions=[]
    for p in positions:
        clean_positions.append({k:p.get(k) for k in ("symbol","qty","avg_entry_price","current_price","market_value","unrealized_pl","unrealized_plpc")})
    clean_orders=[]
    for o in orders:
        clean_orders.append({k:o.get(k) for k in ("created_at","symbol","side","type","qty","status","filled_avg_price")})
    return {"mode":"PAPER" if PAPER else "LIVE", "health":True, "account":{"equity":account.get("equity"),"cash":account.get("cash"),"buying_power":account.get("buying_power"),"day_pnl":day_pnl,"day_pnl_source":pnl_source}, "positions":clean_positions, "orders":clean_orders, "fills":fills, "open_orders":len(open_orders), "risk":{"invested":invested,"unrealized":unrealized,"largest_symbol":largest.get("symbol") if largest else None,"concentration":concentration}, "history":_history(period), "timestamp":datetime.now(timezone.utc).isoformat()}


class Handler(BaseHTTPRequestHandler):
    def send(self, status: int, body: bytes, content_type: str):
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=urlparse(self.path).path
        if path in {"/","/index.html"}:
            self.send(200,HTML.encode(),"text/html; charset=utf-8"); return
        if path in {"/health","/healthz"}:
            self.send(200,b'{"ok":true,"service":"bottrade-dashboard","read_only":true}',"application/json"); return
        if path=="/api/state":
            try:
                q=parse_qs(urlparse(self.path).query); period=(q.get("period") or ["1D"])[0]
                self.send(200,json.dumps(state(period),separators=(",",":" )).encode(),"application/json; charset=utf-8")
            except Exception as exc:
                self.send(503,json.dumps({"error":str(exc)}).encode(),"application/json; charset=utf-8")
            return
        self.send(404,b'{"error":"not found"}',"application/json")
    def log_message(self,*_args): return

if __name__ == "__main__":
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
