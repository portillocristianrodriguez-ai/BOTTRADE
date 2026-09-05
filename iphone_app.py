"""iPhone/PWA shell for the existing read-only BOTTRADE dashboard.

Keeps the dashboard logic unchanged while adding installable-web-app metadata,
a service worker, and mobile safe-area polish for iPhone Safari.
"""
from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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

SERVICE_WORKER = r'''const CACHE = "bottrade-pwa-v1";
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
</style>
'''

PWA_SCRIPT = r'''<script>
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
</script>'''

dashboard.HTML = dashboard.HTML.replace("<title>BOTTRADE · PRO TERMINAL</title>", "<title>BOTTRADE · PRO TERMINAL</title>" + PWA_HEAD)
dashboard.HTML = dashboard.HTML.replace("</body>", PWA_SCRIPT + "</body>")

BaseHandler = next(
    cls for cls in dashboard.__dict__.values()
    if isinstance(cls, type)
    and issubclass(cls, BaseHTTPRequestHandler)
    and cls is not BaseHTTPRequestHandler
)

class PWAHandler(BaseHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/manifest.json":
            data = MANIFEST.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/sw.js":
            data = SERVICE_WORKER.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Service-Worker-Allowed", "/")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

if __name__ == "__main__":
    host = getattr(dashboard, "HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", getattr(dashboard, "PORT", 8080)))
    server = ThreadingHTTPServer((host, port), PWAHandler)
    print(f"BOTTRADE iPhone/PWA dashboard listening on {host}:{port}", flush=True)
    server.serve_forever()
