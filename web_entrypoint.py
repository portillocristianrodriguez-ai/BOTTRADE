"""Polished read-only web entrypoint for BOTTRADE.

Keeps the existing dashboard and AI/PWA logic intact, adding presentation-only
UX enhancements: sticky navigation, auto-refresh controls, fullscreen mode,
connection telemetry, keyboard shortcuts, and responsive polish.
"""
from __future__ import annotations

import os
from http.server import ThreadingHTTPServer

import dashboard
import iphone_ai_app

ENHANCEMENT_HEAD = r'''
<style>
:root{--glow:rgba(112,165,255,.18)}
body{background-attachment:fixed}
.top{position:sticky;top:8px;z-index:20;padding:8px 10px;border:1px solid rgba(45,62,84,.8);border-radius:12px;background:rgba(5,8,13,.82);backdrop-filter:blur(16px);box-shadow:0 12px 35px rgba(0,0,0,.28)}
.top:after{content:"";position:absolute;inset:auto 12px -1px;height:1px;background:linear-gradient(90deg,transparent,var(--glow),transparent);pointer-events:none}
.brand{font-size:22px;text-shadow:0 0 22px rgba(112,165,255,.14)}
.card{transition:border-color .18s ease,transform .18s ease,box-shadow .18s ease}
.card:hover{border-color:#273a53;box-shadow:0 12px 32px rgba(0,0,0,.28)}
.kpi .value{letter-spacing:-.025em}
button{transition:all .15s ease}
button:hover{border-color:#38577f;background:#15243a;color:#fff;transform:translateY(-1px)}
button:active{transform:translateY(0)}
#uxbar{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:8px 0;color:#73839a;font-size:9px;text-transform:uppercase;letter-spacing:.08em}
#uxbar .left,#uxbar .right{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.ux-chip{border:1px solid #172333;background:#09111b;border-radius:6px;padding:5px 8px}
.ux-live{color:#42d995;border-color:#20563d;background:#081a13}.ux-warn{color:#f2c463;border-color:#4b3e22;background:#171208}
#uxbar button{font-size:9px;padding:5px 8px}
#liveDot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#42d995;box-shadow:0 0 9px #42d995;animation:uxpulse 1.8s infinite}
@keyframes uxpulse{50%{opacity:.45;box-shadow:0 0 3px #42d995}}
#uxToast{position:fixed;right:16px;bottom:16px;z-index:50;opacity:0;transform:translateY(8px);pointer-events:none;padding:9px 11px;border:1px solid #2a405e;border-radius:8px;background:#0a121d;color:#cbd8e8;font-size:10px;box-shadow:0 10px 28px #0008;transition:.2s}
#uxToast.show{opacity:1;transform:none}
@media(max-width:760px){.top{position:relative;top:0}.wrap{padding:8px}#uxbar{align-items:flex-start;flex-direction:column}.top .actions{gap:5px}.brand{font-size:19px}}
</style>
'''

ENHANCEMENT_BODY = r'''
<div id="uxbar">
  <div class="left">
    <span class="ux-chip ux-live"><span id="liveDot"></span> LIVE DATA</span>
    <span id="uxRefresh" class="ux-chip">Actualizando cada 20s</span>
    <span id="uxConnection" class="ux-chip">Conexión: —</span>
  </div>
  <div class="right">
    <button id="uxAuto" onclick="toggleAuto()">Auto: ON</button>
    <button onclick="document.documentElement.requestFullscreen?.()">⛶ Fullscreen</button>
    <button onclick="window.scrollTo({top:0,behavior:'smooth'})">↑ Top</button>
  </div>
</div>
<div id="uxToast">Datos actualizados</div>
'''

ENHANCEMENT_SCRIPT = r'''
<script>
(() => {
  const PERIODS = ['1D','1W','1M','1A'];
  let auto = true;
  let timer = null;
  let refreshing = false;
  const toast = document.getElementById('uxToast');
  const conn = document.getElementById('uxConnection');
  const refreshLabel = document.getElementById('uxRefresh');
  const autoBtn = document.getElementById('uxAuto');
  const originalLoad = window.load;
  const showToast = (text) => { toast.textContent=text; toast.classList.add('show'); setTimeout(()=>toast.classList.remove('show'),1500); };
  const setConn = (ok) => { conn.textContent = ok ? 'Conexión: OK' : 'Conexión: error'; conn.classList.toggle('ux-live', ok); conn.classList.toggle('ux-warn', !ok); };
  window.load = async function(){
    if (refreshing) return;
    refreshing = true;
    const started = performance.now();
    try { await originalLoad(); setConn(true); showToast('Datos actualizados · '+Math.round(performance.now()-started)+' ms'); }
    catch(e){ setConn(false); showToast('No se pudieron actualizar los datos'); throw e; }
    finally { refreshing=false; }
  };
  window.toggleAuto = function(){
    auto=!auto; autoBtn.textContent='Auto: '+(auto?'ON':'OFF');
    autoBtn.classList.toggle('ux-live',auto);
    if(timer) clearInterval(timer);
    timer=auto?setInterval(()=>{ if(!document.hidden) window.load().catch(()=>{}); },20000):null;
    refreshLabel.textContent=auto?'Actualizando cada 20s':'Actualización pausada';
  };
  document.addEventListener('visibilitychange',()=>{ if(!document.hidden && auto) window.load().catch(()=>{}); });
  document.addEventListener('keydown',(e)=>{
    if((e.key==='r'||e.key==='R') && !['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)){e.preventDefault();window.load().catch(()=>{});}
    if(e.key==='Escape' && document.fullscreenElement) document.exitFullscreen?.();
    if(e.key==='1') document.querySelectorAll('.tabs button')[0]?.click();
    if(e.key==='2') document.querySelectorAll('.tabs button')[1]?.click();
    if(e.key==='3') document.querySelectorAll('.tabs button')[2]?.click();
    if(e.key==='4') document.querySelectorAll('.tabs button')[3]?.click();
  });
  toggleAuto();
  window.load().catch(()=>{});
})();
</script>
'''

# iphone_ai_app has already composed the base dashboard, AI panel and PWA assets.
# Inject only presentation/UX changes; no trading code or order routes are added.
html = iphone_ai_app.dashboard.HTML
html = html.replace('</head>', ENHANCEMENT_HEAD + '</head>', 1)
html = html.replace('<div class="grid">', ENHANCEMENT_BODY + '<div class="grid">', 1)
html = html.replace('</body>', ENHANCEMENT_SCRIPT + '</body>', 1)
iphone_ai_app.dashboard.HTML = html

if __name__ == '__main__':
    host = getattr(dashboard, 'HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', getattr(dashboard, 'PORT', 8080)))
    server = ThreadingHTTPServer((host, port), iphone_ai_app.AIHandler)
    print(f'BOTTRADE polished dashboard listening on {host}:{port}', flush=True)
    server.serve_forever()
