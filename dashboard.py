"""Read-only web dashboard for BOTTRADE.

This service never places, cancels, or modifies orders. It only reads the
Alpaca account configured for BOTTRADE and exposes a professional read-only
browser dashboard with account metrics, P&L, positions, orders, and system health.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from threading import Lock

import requests

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
API_KEY = os.environ.get("ALPACA_API_KEY", "")
API_SECRET = os.environ.get("ALPACA_API_SECRET", "")
PAPER = os.environ.get("ALPACA_PAPER", "true").strip().lower() in {"1", "true", "yes", "si", "sí", "on"}
BASE_URL = "https://paper-api.alpaca.markets" if PAPER else "https://api.alpaca.markets"

# Cache state to avoid hammering Alpaca API
_cache_lock = Lock()
_cache = {"state": None, "ts": None, "ttl": 10}


HTML = r'''<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BOTTRADE Dashboard</title>
  <style>
    :root {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      background: #0a0e27;
      color: #e8eef7;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: linear-gradient(135deg, #0f1535 0%, #0a0e27 100%); min-height: 100vh; }
    main { max-width: 1400px; margin: 0 auto; padding: 32px 20px; }
    
    .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 32px; border-bottom: 1px solid #2a3254; padding-bottom: 20px; }
    .header-left h1 { margin: 0; font-size: 32px; font-weight: 800; letter-spacing: -0.5px; }
    .header-left .sub { color: #9aadbe; font-size: 14px; margin-top: 6px; }
    .header-right { display: flex; gap: 12px; align-items: flex-start; }
    
    .badge { padding: 8px 14px; border-radius: 8px; font-weight: 700; font-size: 12px; letter-spacing: 0.5px; text-transform: uppercase; }
    .badge.paper { background: #0f5934; color: #5ef3aa; border: 1px solid #1a7d4a; }
    .badge.live { background: #663b3b; color: #ff9999; border: 1px solid #8b5555; }
    .badge.ok { background: #1a4d2e; color: #6ee394; border: 1px solid #2d6f47; }
    .badge.warn { background: #664d1f; color: #ffc66d; border: 1px solid #8b6b39; }
    
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { 
      background: linear-gradient(135deg, rgba(30, 41, 73, 0.6) 0%, rgba(20, 28, 54, 0.8) 100%);
      border: 1px solid #2a3f6f;
      border-radius: 12px;
      padding: 20px;
      backdrop-filter: blur(4px);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    }
    .card.highlight { border-color: #4a7fff; background: linear-gradient(135deg, rgba(40, 60, 100, 0.7) 0%, rgba(25, 38, 70, 0.9) 100%); }
    
    .metric-label { color: #9aadbe; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
    .metric-value { font-size: 28px; font-weight: 800; line-height: 1; }
    .metric-sub { color: #7a8ab0; font-size: 12px; margin-top: 8px; }
    .metric-positive { color: #6ee394; }
    .metric-negative { color: #ff9999; }
    .metric-neutral { color: #b8c5dd; }
    
    .section { margin-bottom: 32px; }
    .section-title { font-size: 16px; font-weight: 700; letter-spacing: -0.3px; margin-bottom: 12px; color: #e8eef7; }
    .section-content { background: linear-gradient(135deg, rgba(30, 41, 73, 0.5) 0%, rgba(20, 28, 54, 0.7) 100%); border: 1px solid #2a3f6f; border-radius: 12px; padding: 20px; backdrop-filter: blur(4px); }
    
    .table { overflow-x: auto; }
    .table table { width: 100%; border-collapse: collapse; }
    .table th { background: rgba(0, 0, 0, 0.2); color: #9aadbe; font-size: 12px; font-weight: 600; text-align: left; padding: 12px; border-bottom: 1px solid #2a3f6f; text-transform: uppercase; letter-spacing: 0.5px; }
    .table td { padding: 12px; border-bottom: 1px solid rgba(42, 63, 111, 0.5); font-size: 13px; }
    .table tr:hover { background: rgba(74, 127, 255, 0.05); }
    .table-empty { text-align: center; color: #7a8ab0; padding: 24px; }
    
    .pill { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
    .pill-filled { background: #1a7d4a; color: #6ee394; }
    .pill-pending { background: #664d1f; color: #ffc66d; }
    .pill-canceled { background: #3b2a2a; color: #ccc; }
    
    .health { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .health-item { background: rgba(0, 0, 0, 0.2); border-radius: 8px; padding: 12px; border-left: 3px solid #4a7fff; }
    .health-item.good { border-left-color: #6ee394; }
    .health-item.warn { border-left-color: #ffc66d; }
    .health-label { font-size: 11px; color: #9aadbe; text-transform: uppercase; font-weight: 600; }
    .health-value { font-size: 14px; font-weight: 700; margin-top: 4px; }
    
    .error { 
      background: linear-gradient(135deg, rgba(100, 30, 30, 0.6) 0%, rgba(60, 20, 20, 0.8) 100%);
      color: #ff9999;
      border: 1px solid #6b3a3a;
      padding: 14px;
      border-radius: 8px;
      margin-bottom: 20px;
      display: none;
    }
    
    .footer { color: #7a8ab0; font-size: 12px; margin-top: 32px; padding-top: 20px; border-top: 1px solid #2a3f6f; text-align: center; }
    
    @media (max-width: 768px) {
      main { padding: 20px 12px; }
      .grid { grid-template-columns: 1fr; }
      .header { flex-direction: column; }
      .metric-value { font-size: 24px; }
    }
  </style>
</head>
<body>
<main>
  <div class="header">
    <div class="header-left">
      <h1>BOTTRADE</h1>
      <div class="sub">Panel de operaciones · Solo lectura</div>
    </div>
    <div class="header-right">
      <div id="mode-badge" class="badge paper">PAPER</div>
      <div id="health-badge" class="badge ok">OK</div>
    </div>
  </div>

  <div id="error" class="error"></div>

  <div class="grid">
    <div class="card highlight">
      <div class="metric-label">Equity</div>
      <div id="equity" class="metric-value">—</div>
      <div class="metric-sub">Valor total de la cuenta</div>
    </div>
    
    <div class="card">
      <div class="metric-label">Cash</div>
      <div id="cash" class="metric-value">—</div>
      <div class="metric-sub">Saldo disponible</div>
    </div>
    
    <div class="card">
      <div class="metric-label">Buying Power</div>
      <div id="buying-power" class="metric-value">—</div>
      <div class="metric-sub">Poder de compra</div>
    </div>
    
    <div class="card">
      <div class="metric-label">P&L Día</div>
      <div id="pnl" class="metric-value">—</div>
      <div id="pnl-meta" class="metric-sub">—</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Posiciones Abiertas</div>
    <div class="section-content">
      <div id="positions" class="table">
        <div class="table-empty">Cargando posiciones…</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Órdenes Recientes</div>
    <div class="section-content">
      <div id="orders" class="table">
        <div class="table-empty">Cargando órdenes…</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Salud del Sistema</div>
    <div class="section-content">
      <div class="health">
        <div id="health-alpaca" class="health-item good">
          <div class="health-label">Conexión Alpaca</div>
          <div class="health-value">—</div>
        </div>
        <div id="health-sync" class="health-item">
          <div class="health-label">Sincronización</div>
          <div class="health-value">—</div>
        </div>
        <div id="health-updated" class="health-item">
          <div class="health-label">Última Lectura</div>
          <div class="health-value">—</div>
        </div>
        <div id="health-interval" class="health-item">
          <div class="health-label">Intervalo</div>
          <div class="health-value">15 s</div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    <strong>BOTTRADE Dashboard</strong> — Panel operativo de solo lectura. No ejecuta órdenes, no modifica posiciones.
    Los datos se consultan directamente desde Alpaca. Actualización automática cada 15 segundos.
  </div>
</main>

<script>
const money = (n, opts = {}) => {
  if (n == null) return '—';
  const num = Number(n);
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    ...opts
  }).format(num);
};

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

const cls = (n) => (Number(n) >= 0 ? 'metric-positive' : 'metric-negative');

function renderPositions(items) {
  if (!items || items.length === 0) {
    return '<div class="table-empty">Sin posiciones abiertas</div>';
  }
  return '<table><thead><tr><th>Símbolo</th><th>Cantidad</th><th>Precio Promedio</th><th>Precio Actual</th><th>Valor de Mercado</th><th>P&L Unrealizado</th></tr></thead><tbody>' +
    items.map(p => `<tr>
      <td><strong>${esc(p.symbol)}</strong></td>
      <td>${Number(p.qty || 0).toFixed(0)}</td>
      <td>${money(p.avg_entry_price)}</td>
      <td>${money(p.current_price)}</td>
      <td>${money(p.market_value)}</td>
      <td class="${cls(p.unrealized_pl)}"><strong>${money(p.unrealized_pl)}</strong></td>
    </tr>`).join('') +
    '</tbody></table>';
}

function renderOrders(items) {
  if (!items || items.length === 0) {
    return '<div class="table-empty">Sin órdenes registradas</div>';
  }
  return '<table><thead><tr><th>Fecha</th><th>Símbolo</th><th>Lado</th><th>Tipo</th><th>Cantidad</th><th>Precio</th><th>Status</th></tr></thead><tbody>' +
    items.map(o => {
      const status = (o.status || '').toLowerCase();
      let pillClass = 'pill-pending';
      if (status.includes('filled')) pillClass = 'pill-filled';
      else if (status.includes('cancel')) pillClass = 'pill-canceled';
      return `<tr>
        <td>${esc(o.created_at ? o.created_at.substring(0, 16) : '—')}</td>
        <td><strong>${esc(o.symbol)}</strong></td>
        <td>${esc(o.side ? o.side.toUpperCase() : '—')}</td>
        <td>${esc(o.type ? o.type.toUpperCase() : '—')}</td>
        <td>${Number(o.qty || 0).toFixed(0)}</td>
        <td>${money(o.limit_price) || money(o.filled_avg_price) || '—'}</td>
        <td><span class="pill ${pillClass}">${esc(status)}</span></td>
      </tr>`;
    }).join('') +
    '</tbody></table>';
}

async function load() {
  const startTs = Date.now();
  try {
    const r = await fetch('/api/state', { cache: 'no-store' });
    const d = await r.json();
    
    if (!r.ok) throw new Error(d.error || 'Error al cargar estado');
    
    document.getElementById('error').style.display = 'none';
    
    // Mode badge
    const modeBadge = document.getElementById('mode-badge');
    modeBadge.textContent = d.mode || 'PAPER';
    modeBadge.className = `badge ${(d.mode || 'PAPER').toLowerCase()}`;
    
    // Metrics
    document.getElementById('equity').textContent = money(d.account.equity);
    document.getElementById('cash').textContent = money(d.account.cash);
    document.getElementById('buying-power').textContent = money(d.account.buying_power);
    
    const pnlEl = document.getElementById('pnl');
    const pnlVal = d.account.day_pnl;
    pnlEl.textContent = money(pnlVal);
    pnlEl.className = `metric-value ${cls(pnlVal)}`;
    document.getElementById('pnl-meta').textContent = d.account.day_pnl_source || 'Sin datos';
    
    // Positions and orders
    document.getElementById('positions').innerHTML = renderPositions(d.positions);
    document.getElementById('orders').innerHTML = renderOrders(d.orders);
    
    // Health
    const elapsed = Date.now() - startTs;
    document.getElementById('health-alpaca').className = d.health?.alpaca_ok ? 'health-item good' : 'health-item warn';
    document.getElementById('health-alpaca').querySelector('.health-value').textContent = d.health?.alpaca_ok ? '✓ OK' : '⚠ Error';
    
    document.getElementById('health-sync').className = 'health-item good';
    document.getElementById('health-sync').querySelector('.health-value').textContent = `${elapsed}ms`;
    
    const now = new Date();
    document.getElementById('health-updated').querySelector('.health-value').textContent = 
      now.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    const healthBadge = document.getElementById('health-badge');
    healthBadge.className = d.health?.alpaca_ok ? 'badge ok' : 'badge warn';
    healthBadge.textContent = d.health?.alpaca_ok ? 'OK' : 'WARN';
    
  } catch (e) {
    const el = document.getElementById('error');
    el.textContent = '❌ Error: ' + e.message;
    el.style.display = 'block';
    document.getElementById('mode-badge').className = 'badge warn';
  }
}

load();
setInterval(load, 15000);
</script>
</body>
</html>
'''


def alpaca_get(path: str, params: dict | None = None):
    """Make authenticated GET request to Alpaca API."""
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Missing Alpaca credentials")
    response = requests.get(
        f"{BASE_URL}{path}",
        headers={"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": API_SECRET},
        params=params,
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def state():
    """Fetch and return current account state from Alpaca."""
    try:
        account = alpaca_get("/v2/account")
        positions = alpaca_get("/v2/positions")
        orders = alpaca_get(
            "/v2/orders",
            {
                "status": "all",
                "limit": 20,
                "direction": "desc",
                "nested": "false",
            },
        )

        # Calculate P&L for the day
        day_pnl = None
        pnl_source = "No disponible"
        try:
            history = alpaca_get(
                "/v2/account/portfolio/history",
                {
                    "period": "1D",
                    "timeframe": "5Min",
                    "extended_hours": "true",
                },
            )
            equity = history.get("equity") or []
            profit = history.get("profit_loss") or []

            if profit and profit[-1] is not None:
                day_pnl = float(profit[-1])
                pnl_source = "Alpaca Portfolio History (1D)"
            elif equity and len(equity) >= 2:
                first = next((e for e in equity if e is not None), None)
                last = next((e for e in reversed(equity) if e is not None), None)
                if first is not None and last is not None:
                    day_pnl = float(last) - float(first)
                    pnl_source = "Equity Snapshots (1D)"
        except requests.RequestException:
            pnl_source = "Histórico no disponible"

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
                {
                    k: p.get(k)
                    for k in (
                        "symbol",
                        "qty",
                        "avg_entry_price",
                        "current_price",
                        "market_value",
                        "unrealized_pl",
                    )
                }
                for p in positions
            ],
            "orders": [
                {
                    k: o.get(k)
                    for k in (
                        "created_at",
                        "symbol",
                        "side",
                        "type",
                        "qty",
                        "status",
                        "limit_price",
                        "filled_avg_price",
                    )
                }
                for o in orders
            ],
            "health": {
                "alpaca_ok": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
    except Exception as e:
        return {
            "mode": "PAPER" if PAPER else "LIVE",
            "account": {
                "equity": None,
                "cash": None,
                "buying_power": None,
                "day_pnl": None,
                "day_pnl_source": f"Error: {str(e)}",
            },
            "positions": [],
            "orders": [],
            "error": str(e),
            "health": {
                "alpaca_ok": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif path == "/api/state":
            try:
                with _cache_lock:
                    now = datetime.now(timezone.utc)
                    if (
                        _cache["state"] is None
                        or _cache["ts"] is None
                        or (now - _cache["ts"]).total_seconds() > _cache["ttl"]
                    ):
                        _cache["state"] = state()
                        _cache["ts"] = now

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(
                    json.dumps(_cache["state"], default=str, indent=2).encode()
                )
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": str(e)}, indent=2).encode()
                )
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")

    def log_message(self, format, *args):
        # Suppress server logs
        pass


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Dashboard running at http://{HOST}:{PORT}")
    print(f"Mode: {'PAPER' if PAPER else 'LIVE'}")
    print(f"Read-only dashboard - No trading operations")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")
        server.shutdown()


if __name__ == "__main__":
    main()

