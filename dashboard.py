"""Read-only web dashboard for BOTTRADE.

This service never places, cancels, or modifies orders. It only reads the
Alpaca account configured for BOTTRADE and exposes a small browser dashboard.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import requests

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
API_KEY = os.environ.get("ALPACA_API_KEY", "")
API_SECRET = os.environ.get("ALPACA_API_SECRET", "")
PAPER = os.environ.get("ALPACA_PAPER", "true").strip().lower() in {"1", "true", "yes", "si", "sí", "on"}
BASE_URL = "https://paper-api.alpaca.markets" if PAPER else "https://api.alpaca.markets"

HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BOTTRADE APP</title>
<style>
:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0b1020;color:#edf2f7}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#17213b,#0b1020 55%);min-height:100vh}
main{max-width:1250px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;gap:18px;align-items:center;margin-bottom:24px}.brand{font-size:30px;font-weight:800;letter-spacing:.3px}.sub{color:#9aa8bd;margin-top:5px}.badge{padding:9px 13px;border-radius:999px;background:#12351f;color:#7ef0a6;font-weight:800;border:1px solid #245b38}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{background:rgba(20,29,50,.88);border:1px solid #26334e;border-radius:16px;padding:18px;box-shadow:0 12px 30px #0002}.label{color:#91a0b6;font-size:13px}.value{font-size:26px;font-weight:750;margin-top:7px}.small{font-size:13px;color:#8f9db2;margin-top:6px}
.section{margin-top:18px}.section h2{font-size:18px;margin:0 0 12px}.table{overflow:auto}.table table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;padding:11px 10px;border-bottom:1px solid #26334e;font-size:14px}.table th{color:#91a0b6;font-weight:600}.pill{padding:4px 8px;border-radius:8px;background:#18243b}.good{color:#7ef0a6}.warn{color:#ffd27d}.bad{color:#ff8f8f}.footer{color:#71809a;font-size:12px;margin-top:18px}.error{background:#3b1e25;color:#ffb4b4;border:1px solid #71333d;padding:12px;border-radius:12px;display:none;margin-bottom:14px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){main{padding:16px}.grid{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}
</style></head><body><main>
<div class="top"><div><div class="brand">BOTTRADE APP</div><div class="sub">Panel operativo y de rendimiento · solo lectura</div></div><div id="mode" class="badge">PAPER</div></div>
<div id="error" class="error"></div>
<div class="grid">
<div class="card"><div class="label">Equity</div><div id="equity" class="value">—</div><div id="equityMeta" class="small">—</div></div>
<div class="card"><div class="label">Cash</div><div id="cash" class="value">—</div><div class="small">Saldo disponible</div></div>
<div class="card"><div class="label">P&amp;L del día</div><div id="pnl" class="value">—</div><div id="pnlMeta" class="small">Dato de portfolio history</div></div>
<div class="card"><div class="label">Posiciones</div><div id="positionsCount" class="value">—</div><div id="lastUpdate" class="small">Actualizando…</div></div>
</div>
<div class="section card"><h2>Posiciones abiertas</h2><div id="positions" class="table">Cargando…</div></div>
<div class="section card"><h2>Órdenes recientes</h2><div id="orders" class="table">Cargando…</div></div>
<div class="footer">BOTTRADE APP no ejecuta órdenes. Los datos se consultan directamente desde la cuenta Alpaca configurada. Actualización automática cada 15 s.</div>
</main><script>
const money=n=>n==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(Number(n));
const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
function cls(n){return Number(n)>=0?'good':'bad'}
function renderRows(items, type){if(!items?.length)return '<div class="small">Sin datos.</div>'; if(type==='pos')return '<table><thead><tr><th>Símbolo</th><th>Cantidad</th><th>Precio medio</th><th>Precio actual</th><th>Valor</th><th>P&amp;L</th></tr></thead><tbody>'+items.map(x=>`<tr><td><b>${esc(x.symbol)}</b></td><td>${esc(x.qty)}</td><td>${money(x.avg_entry_price)}</td><td>${money(x.current_price)}</td><td>${money(x.market_value)}</td><td class="${cls(x.unrealized_pl)}">${money(x.unrealized_pl)}</td></tr>`).join('')+'</tbody></table>';return '<table><thead><tr><th>Fecha</th><th>Símbolo</th><th>Side</th><th>Tipo</th><th>Qty</th><th>Status</th></tr></thead><tbody>'+items.map(x=>`<tr><td>${esc(x.created_at)}</td><td><b>${esc(x.symbol)}</b></td><td>${esc(x.side)}</td><td>${esc(x.type)}</td><td>${esc(x.qty)}</td><td><span class="pill">${esc(x.status)}</span></td></tr>`).join('')+'</tbody></table>'}
async function load(){try{const r=await fetch('/api/state',{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'No se pudo cargar el estado');document.getElementById('error').style.display='none';document.getElementById('mode').textContent=d.mode;document.getElementById('equity').textContent=money(d.account.equity);document.getElementById('cash').textContent=money(d.account.cash);document.getElementById('pnl').textContent=money(d.account.day_pnl);document.getElementById('pnl').className='value '+cls(d.account.day_pnl);document.getElementById('pnlMeta').textContent=d.account.day_pnl_source;document.getElementById('positionsCount').textContent=d.positions.length;document.getElementById('lastUpdate').textContent='Última lectura: '+new Date().toLocaleTimeString();document.getElementById('positions').innerHTML=renderRows(d.positions,'pos');document.getElementById('orders').innerHTML=renderRows(d.orders,'ord')}catch(e){const el=document.getElementById('error');el.textContent=e.message;el.style.display='block'}}load();setInterval(load,15000);
</script></body></html>'''


def alpaca_get(path: str, params: dict | None = None):
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Faltan credenciales de Alpaca en el servicio dashboard")
    response = requests.get(
        f"{BASE_URL}{path}",
        headers={"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": API_SECRET},
        params=params,
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def state():
    account = alpaca_get("/v2/account")
    positions = alpaca_get("/v2/positions")
    orders = alpaca_get("/v2/orders", {"status": "all", "limit": 12, "direction": "desc", "nested": "false"})
    day_pnl = None
    pnl_source = "No disponible"
    try:
        history = alpaca_get("/v2/account/portfolio/history", {"period": "1D", "timeframe": "5Min", "extended_hours": "true"})
        equity = history.get("equity") or []
        profit = history.get("profit_loss") or []
        if profit and profit[-1] is not None:
            day_pnl = float(profit[-1])
            pnl_source = "Alpaca portfolio history · 1D"
        elif equity and equity[0] is not None and equity[-1] is not None:
            day_pnl = float(equity[-1]) - float(equity[0])
            pnl_source = "Alpaca equity history · 1D"
    except requests.RequestException:
        pnl_source = "Histórico no disponible ahora"
    return {
        "mode": "PAPER" if PAPER else "LIVE",
        "account": {
            "equity": account.get("equity"),
            "cash": account.get("cash"),
            "buying_power": account.get("buying_power"),
            "day_pnl": day_pnl,
            "day_pnl_source": pnl_source,
        },
        "positions": [
            {k: p.get(k) for k in ("symbol", "qty", "avg_entry_price", "current_price", "market_value", "unrealized_pl")}
            for p in positions
        ],
        "orders": [
            {k: o.get(k) for k in ("created_at", "symbol", "side", "type", "qty", "status")}
            for o in orders
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class Handler(BaseHTTPRequestHandler):
    def send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self.send(200, HTML.encode(), "text/html; charset=utf-8")
            return
        if path in {"/health", "/healthz"}:
            self.send(200, b'{"ok":true,"service":"bottrade-dashboard"}', "application/json")
            return
        if path == "/api/state":
            try:
                payload = json.dumps(state(), separators=(",", ":")).encode()
                self.send(200, payload, "application/json; charset=utf-8")
            except Exception as exc:
                self.send(503, json.dumps({"error": str(exc)}).encode(), "application/json; charset=utf-8")
            return
        self.send(404, b'{"error":"not found"}', "application/json")

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
