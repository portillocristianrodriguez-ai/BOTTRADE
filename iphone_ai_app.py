"""PWA wrapper that adds a read-only AI analyst and equity history table.

The underlying dashboard remains the source of truth for Alpaca data. This
wrapper adds presentation and an analysis endpoint without touching trading
or execution logic.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import ai_assistant
import dashboard

MANIFEST = r'''{
  "name": "BOTTRADE PRO TERMINAL",
  "short_name": "BOTTRADE",
  "description": "Read-only professional trading terminal for BOTTRADE",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#05080d",
  "theme_color": "#05080d",
  "icons": []
}'''

SERVICE_WORKER = r'''const CACHE = "bottrade-pwa-ai-v1";
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(["/"])));
  self.skipWaiting();
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request).then(r => r || caches.match("/"))));
});
'''

PWA_HEAD = r'''<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#05080d">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="BOTTRADE">
<style>
html { background:#05080d; }
body { padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom); }
button { -webkit-tap-highlight-color: transparent; }
.ai-grid{display:grid;grid-template-columns:1fr 1.35fr;gap:8px}
.ai-panel{min-height:280px}.ai-chat{height:215px;overflow:auto;padding:8px;border:1px solid #172333;border-radius:7px;background:#070c14}
.ai-msg{padding:8px 9px;margin:0 0 7px;border-radius:7px;font-size:11px;line-height:1.45;white-space:pre-wrap}.ai-user{background:#13233a;color:#dbe9ff}.ai-bot{background:#0b1716;color:#d7eee7}.ai-form{display:grid;grid-template-columns:1fr auto;gap:7px;margin-top:7px}.ai-form textarea{resize:vertical;min-height:54px;background:#080e17;border:1px solid #1c2838;border-radius:6px;color:#e9eef7;padding:8px;font:inherit;font-size:11px}.ai-suggestions{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}.ai-suggestions button{font-size:9px}.ai-table{max-height:280px}
@media(max-width:760px){.ai-grid{grid-template-columns:1fr}.ai-panel{min-height:0}}
</style>
'''

AI_UI = r'''
<div class="grid section ai-grid">
<div class="card ai-panel"><div class="sectionhead"><h2>AI ANALYST</h2><span class="muted">read-only · Alpaca + estrategia</span></div>
<div id="aiChat" class="ai-chat"><div class="ai-msg ai-bot">Soy el analista de BOTTRADE. Puedo revisar equity, drawdown, posiciones, ejecuciones y parámetros de estrategia. Puedo proponer cambios para probar, pero no ejecuto operaciones ni modifico la estrategia.</div></div>
<div class="ai-form"><textarea id="aiQuestion" placeholder="Ej.: ¿Qué está funcionando peor y qué probarías primero?"></textarea><button id="aiAsk">Analizar</button></div>
<div class="ai-suggestions"><button onclick="askAI('Analiza el rendimiento y el drawdown del periodo actual.')">Rendimiento</button><button onclick="askAI('Revisa las posiciones y la concentración de riesgo.')">Riesgo</button><button onclick="askAI('Compara SL, TP y trailing actuales y propone qué probar en backtest.')">SL/TP/trailing</button><button onclick="askAI('¿Qué cambio de estrategia probarías primero y por qué?')">Estrategia</button></div>
</div>
<div class="card ai-panel"><div class="sectionhead"><h2>EQUITY HISTORY</h2><span class="muted">tiempo · dinero · variación</span></div><div id="historyTable" class="table ai-table"><div class="empty">Cargando histórico…</div></div></div>
</div>
'''

AI_SCRIPT = r'''<script>
const aiHistory=[];
function aiAdd(role,text){const box=document.getElementById('aiChat');const d=document.createElement('div');d.className='ai-msg '+(role==='user'?'ai-user':'ai-bot');d.textContent=text;box.appendChild(d);box.scrollTop=box.scrollHeight;}
async function askAI(prefill){const input=document.getElementById('aiQuestion');if(prefill)input.value=prefill;const q=input.value.trim();if(!q)return;input.value='';aiAdd('user',q);const btn=document.getElementById('aiAsk');btn.disabled=true;btn.textContent='Analizando…';try{const r=await fetch('/api/ai/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,history:aiHistory.slice(-8),period:window.period||'1D'})});const d=await r.json();if(!r.ok)throw new Error(d.error||'No se pudo consultar la IA');aiHistory.push({role:'user',content:q},{role:'assistant',content:d.answer});aiAdd('assistant',d.answer)}catch(e){aiAdd('assistant','Error: '+e.message)}finally{btn.disabled=false;btn.textContent='Analizar'}}
document.getElementById('aiAsk').addEventListener('click',()=>askAI());document.getElementById('aiQuestion').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();askAI()}});
async function loadHistoryTable(){try{const p=window.period||'1D';const r=await fetch('/api/history?period='+encodeURIComponent(p),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'histórico no disponible');const pts=d.points||[];if(!pts.length){document.getElementById('historyTable').innerHTML='<div class="empty">No hay histórico.</div>';return}const first=Number(pts[0].equity)||0;const rows=pts.slice().reverse().map((x,i,a)=>{const prev=i<a.length-1?Number(a[i+1].equity):Number(x.equity);const eq=Number(x.equity)||0;const delta=eq-prev;const ret=first?((eq/first)-1)*100:null;return `<tr><td>${esc(x.label||'')}</td><td>${money(eq)}</td><td class="${cls(delta)}">${money(delta)}</td><td class="${cls(ret)}">${pct(ret)}</td></tr>`}).join('');document.getElementById('historyTable').innerHTML='<table><thead><tr><th>Tiempo</th><th>Equity</th><th>Variación</th><th>Retorno</th></tr></thead><tbody>'+rows+'</tbody></table>'}catch(e){document.getElementById('historyTable').innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
const oldLoad=window.load;window.load=async function(){await oldLoad();loadHistoryTable()};loadHistoryTable();
</script>'''

# Preserve the existing terminal and add only the analytics layer.
dashboard.HTML = dashboard.HTML.replace("<title>BOTTRADE · PRO TERMINAL</title>", "<title>BOTTRADE · PRO TERMINAL</title>" + PWA_HEAD)
dashboard.HTML = dashboard.HTML.replace('<div class="footer">', AI_UI + '<div class="footer">')
dashboard.HTML = dashboard.HTML.replace('</body>', AI_SCRIPT + '</body>')

BaseHandler = next(
    cls for cls in dashboard.__dict__.values()
    if isinstance(cls, type)
    and issubclass(cls, BaseHTTPRequestHandler)
    and cls is not BaseHTTPRequestHandler
)


class AIHandler(BaseHandler):
    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/manifest.json":
            data = MANIFEST.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/manifest+json; charset=utf-8"); self.send_header("Cache-Control", "public, max-age=3600"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if path == "/sw.js":
            data = SERVICE_WORKER.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/javascript; charset=utf-8"); self.send_header("Cache-Control", "no-cache"); self.send_header("Service-Worker-Allowed", "/"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if path == "/api/history":
            try:
                q=parse_qs(urlparse(self.path).query); period=(q.get("period") or ["1D"])[0]
                self._send_json(200, dashboard._history(period))
            except Exception as exc:
                self._send_json(503, {"error": str(exc)})
            return
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/ai/chat":
            self._send_json(404, {"error": "not found"}); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 12000:
                raise ValueError("Solicitud demasiado grande")
            payload=json.loads(self.rfile.read(length) or b"{}")
            question=str(payload.get("question") or "").strip()
            if not question:
                raise ValueError("Escribe una pregunta")
            if len(question)>3000:
                raise ValueError("La pregunta es demasiado larga")
            period=str(payload.get("period") or "1D")
            snapshot=dashboard.state(period)
            answer=ai_assistant.ask(snapshot, question, payload.get("history") or [])
            self._send_json(200, {"answer": answer, "model": ai_assistant.AI_MODEL})
        except Exception as exc:
            self._send_json(503, {"error": str(exc)})


if __name__ == "__main__":
    host=getattr(dashboard,"HOST","0.0.0.0")
    port=int(os.environ.get("PORT",getattr(dashboard,"PORT",8080)))
    server=ThreadingHTTPServer((host,port),AIHandler)
    print(f"BOTTRADE AI/PWA dashboard listening on {host}:{port}",flush=True)
    server.serve_forever()
