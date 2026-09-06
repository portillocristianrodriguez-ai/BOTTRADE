"""Compatibility package that decorates the existing dashboard without changing trading logic.

Python resolves a regular package before a same-directory module, so the existing
``dashboard.py`` remains the source of truth while this package adds presentation
UX at import time. All dashboard functions/state are re-exported unchanged.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_BASE_PATH = Path(__file__).resolve().parent.parent / "dashboard.py"
_SPEC = importlib.util.spec_from_file_location("_bottrade_dashboard_base", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load dashboard base: {_BASE_PATH}")
_BASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASE)

# Re-export the complete original dashboard API.
for _name, _value in vars(_BASE).items():
    if _name not in {"__name__", "__package__", "__loader__", "__spec__"}:
        globals()[_name] = _value

_ENHANCEMENT_HEAD = r'''
<style>
:root{--glow:rgba(112,165,255,.18)}
body{background-attachment:fixed}
.top{position:sticky;top:8px;z-index:20;padding:8px 10px;border:1px solid rgba(45,62,84,.8);border-radius:12px;background:rgba(5,8,13,.82);backdrop-filter:blur(16px);box-shadow:0 12px 35px rgba(0,0,0,.28)}
.brand{font-size:22px;text-shadow:0 0 22px rgba(112,165,255,.14)}
.card{transition:border-color .18s ease,transform .18s ease,box-shadow .18s ease}.card:hover{border-color:#273a53;box-shadow:0 12px 32px rgba(0,0,0,.28)}
button{transition:all .15s ease}button:hover{border-color:#38577f;background:#15243a;color:#fff;transform:translateY(-1px)}button:active{transform:translateY(0)}
#uxbar{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:8px 0;color:#73839a;font-size:9px;text-transform:uppercase;letter-spacing:.08em}
#uxbar .left,#uxbar .right{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.ux-chip{border:1px solid #172333;background:#09111b;border-radius:6px;padding:5px 8px}.ux-live{color:#42d995!important;border-color:#20563d!important;background:#081a13!important}.ux-warn{color:#f2c463!important;border-color:#4b3e22!important;background:#171208!important}
#uxbar button{font-size:9px;padding:5px 8px}#liveDot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#42d995;box-shadow:0 0 9px #42d995;animation:uxpulse 1.8s infinite}@keyframes uxpulse{50%{opacity:.45;box-shadow:0 0 3px #42d995}}
#uxToast{position:fixed;right:16px;bottom:16px;z-index:50;opacity:0;transform:translateY(8px);pointer-events:none;padding:9px 11px;border:1px solid #2a405e;border-radius:8px;background:#0a121d;color:#cbd8e8;font-size:10px;box-shadow:0 10px 28px #0008;transition:.2s}#uxToast.show{opacity:1;transform:none}
@media(max-width:760px){.top{position:relative;top:0}.wrap{padding:8px}.top .actions{gap:5px}.brand{font-size:19px}#uxbar{align-items:flex-start;flex-direction:column}}
</style>
'''

_ENHANCEMENT_BODY = r'''
<div id="uxbar"><div class="left"><span class="ux-chip ux-live"><span id="liveDot"></span> LIVE DATA</span><span id="uxRefresh" class="ux-chip">Actualizando cada 20s</span><span id="uxConnection" class="ux-chip">Conexión: —</span></div><div class="right"><button id="uxAuto" onclick="toggleAuto()">Auto: ON</button><button onclick="document.documentElement.requestFullscreen?.()">⛶ Fullscreen</button><button onclick="window.scrollTo({top:0,behavior:'smooth'})">↑ Top</button></div></div><div id="uxToast">Datos actualizados</div>
'''

_ENHANCEMENT_SCRIPT = r'''
<script>
(()=>{const originalLoad=window.load;let auto=true,timer=null,busy=false;const toast=document.getElementById('uxToast'),conn=document.getElementById('uxConnection'),label=document.getElementById('uxRefresh'),btn=document.getElementById('uxAuto');const toastMsg=t=>{toast.textContent=t;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1500)};const connection=ok=>{conn.textContent=ok?'Conexión: OK':'Conexión: error';conn.classList.toggle('ux-live',ok);conn.classList.toggle('ux-warn',!ok)};window.load=async()=>{if(busy)return;busy=true;const t=performance.now();try{await originalLoad();connection(true);toastMsg('Datos actualizados · '+Math.round(performance.now()-t)+' ms')}catch(e){connection(false);toastMsg('Error actualizando datos')}finally{busy=false}};window.toggleAuto=()=>{auto=!auto;btn.textContent='Auto: '+(auto?'ON':'OFF');btn.classList.toggle('ux-live',auto);if(timer)clearInterval(timer);timer=auto?setInterval(()=>{if(!document.hidden)window.load()},20000):null;label.textContent=auto?'Actualizando cada 20s':'Actualización pausada'};document.addEventListener('visibilitychange',()=>{if(!document.hidden&&auto)window.load()});document.addEventListener('keydown',e=>{if((e.key==='r'||e.key==='R')&&!['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)){e.preventDefault();window.load()}if(e.key==='Escape'&&document.fullscreenElement)document.exitFullscreen?.();if(['1','2','3','4'].includes(e.key))document.querySelectorAll('.tabs button')[Number(e.key)-1]?.click()});toggleAuto();window.load()})();
</script>
'''

HTML = HTML.replace('</head>', _ENHANCEMENT_HEAD + '</head>', 1)
HTML = HTML.replace('<div class="grid">', _ENHANCEMENT_BODY + '<div class="grid">', 1)
HTML = HTML.replace('</body>', _ENHANCEMENT_SCRIPT + '</body>', 1)
