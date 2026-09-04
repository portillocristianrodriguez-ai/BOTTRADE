"""Entrypoint de Render para ejecutar BOTTRADE como Web Service.

Render espera que el proceso escuche en PORT. BOTTRADE es un worker continuo,
por lo que este proceso expone health y hace de proxy seguro para el webhook
Telegram hacia el proceso worker interno.
"""
from __future__ import annotations

import http.client
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


_WEBHOOK_PREFIX = "/telegram/"
_WORKER_HOST = "127.0.0.1"
_WORKER_PORT = int(os.environ.get("BOTTRADE_TELEGRAM_WEBHOOK_INTERNAL_PORT", "18080"))


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"BOTTRADE OK\n")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith(_WEBHOOK_PREFIX):
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            connection = http.client.HTTPConnection(_WORKER_HOST, _WORKER_PORT, timeout=20)
            headers = {
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Content-Length": str(len(body)),
            }
            secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if secret:
                headers["X-Telegram-Bot-Api-Secret-Token"] = secret
            connection.request("POST", self.path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read()
            connection.close()
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type", "text/plain"))
            self.end_headers()
            self.wfile.write(response_body)
        except Exception:
            self.send_response(503)
            self.end_headers()

    def log_message(self, format, *args):
        return


def main() -> int:
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    process = subprocess.Popen([sys.executable, "worker_entrypoint.py"])
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return process.wait(timeout=15)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
