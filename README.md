# BOTTRADE

Bot de trading algorítmico para Alpaca, preparado para ejecutarse como **worker en Railway**.

> **Seguridad:** el valor por defecto es `ALPACA_PAPER=true`. No se habilita trading real desde el código sin `ALLOW_LIVE_TRADING=true` y `ALPACA_PAPER=false`.

## Arquitectura

- `config.py` — configuración y validación de parámetros.
- `broker.py` — única capa que habla con Alpaca y envía órdenes.
- `estrategia.py` — indicadores y señales de impulso.
- `execution_guard.py` — controles de exposición y órdenes pendientes.
- `execution_quality.py` — spread, profundidad e impacto estimado para crypto.
- `execution_idempotency.py` — `client_order_id` y reconciliación ante errores de submit.
- `market_regime.py` — régimen global de BTC para contextualizar crypto.
- `portfolio_selector.py` — utilidades de selección/diversificación de cartera.
- `sitecustomize.py` — capa de compatibilidad temporal para aplicar hardening sin reescribir todavía todo `broker.py`.
- `notificaciones.py` — Telegram opcional.
- `main.py` — coordinación de scanners, riesgo, protecciones, estado y Telegram.
- `Procfile` — arranque como worker de Railway.

## Operativa actual

### Acciones

El bot analiza los tickers configurados con EMA, RSI, MACD, ATR, volumen y estructura de tendencia. Las entradas pasan por controles de tamaño, buying power, exposición, posiciones y órdenes abiertas.

### Crypto

El scanner funciona de forma continua y analiza un universo de pares `/USD`. Las oportunidades se puntúan por impulso, breakout, volumen, volatilidad, confirmación multi-timeframe y régimen de BTC. También se penaliza la concentración/correlación entre oportunidades.

Antes de una compra crypto se comprueban spread y profundidad del order book. Si el libro es fino, el tamaño puede reducirse; si el spread o la liquidez son demasiado malos, la entrada se bloquea.

### Riesgo y ejecución

- límite de riesgo por operación;
- límite de exposición total e individual;
- límite de buying power;
- hard cap de notional crypto;
- circuit breaker;
- límite de pérdida diaria;
- bloqueo de nuevas entradas si existen posiciones sin protección;
- protección de posiciones de acciones;
- gestión de SL/TP/trailing de crypto por software;
- bloqueo de órdenes duplicadas;
- `client_order_id` por operación y reconciliación después de errores de red;
- sin reintentos ciegos de órdenes cuyo resultado sea incierto.

Alpaca documenta que `client_order_id` permite identificar y consultar una orden, y recomienda utilizar actualizaciones de órdenes en tiempo real para mantener el estado. También advierte que un timeout de envío no significa necesariamente que la orden no haya llegado, por lo que no debe reenviarse a ciegas.

## Railway

El proceso debe ejecutarse como **worker**, no como servicio web:

```text
worker: python main.py
```

Variables mínimas:

```text
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_PAPER=true
```

Telegram es opcional:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Para el listener de comandos mediante `getUpdates`, debe existir una sola instancia activa del bot de Telegram. Durante despliegues puede aparecer un 409 temporal; el listener actual reintenta con backoff.

## Pruebas

Las pruebas de seguridad no envían órdenes a Alpaca y pueden ejecutarse con:

```bash
python -m unittest test_alpaca.py
python -m unittest test_execution_quality.py
```

## Importante sobre PAPER

Paper Trading es una simulación. No reproduce perfectamente impacto de mercado, slippage por latencia, posición en cola ni otros efectos de ejecución real. Por ello, resultados positivos en PAPER no garantizan resultados positivos en live.

El objetivo de esta versión es **maximizar la calidad de selección y ejecución manteniendo controles de riesgo explícitos**, no garantizar beneficios.
