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
- `microstructure_memory.py` — memoria temporal del deterioro de order book.
- `microstructure_score.py` — scoring de microestructura.
- `dynamic_exit.py` — decisión pura de hold/tighten/reduce/exit.
- `dynamic_exit_manager_v2.py` — ejecución de salidas crypto con trailing y microestructura configurable.
- `backtest_engine.py` — backtest determinista offline con costes y supuestos conservadores.
- `research_lab.py` — validación walk-forward OOS y Monte Carlo; la selección de parámetros es solo investigación.
- `ai_adaptive_learning.py` — propuestas conservadoras de aprendizaje y parámetros históricos, nunca auto-aplicadas.
- `sitecustomize.py` — capa de compatibilidad temporal para aplicar hardening sin reescribir todavía todo `broker.py`.
- `notificaciones.py` — Telegram opcional.
- `main.py` — coordinación de scanners, riesgo, protecciones, estado y Telegram.
- `worker.py` — entrypoint que conecta hardening, ranking, sizing, salidas adaptativas y stream de ejecuciones.
- `Procfile` — arranque como worker de Railway.

## Investigación y promoción segura

El laboratorio de investigación funciona completamente offline y no puede enviar órdenes ni modificar parámetros activos.

### Walk-forward OOS

`research_lab.walk_forward()` puede recibir una rejilla de candidatos y una `signal_factory`. En cada ventana:

1. los candidatos se evalúan únicamente sobre el tramo **train**;
2. se elige el mejor candidato con una puntuación que penaliza drawdown;
3. el candidato elegido se prueba una sola vez sobre el tramo **test**, que permanece fuera de muestra;
4. se registran los parámetros y métricas train/OOS para auditoría.

La selección no promociona ni aplica cambios al bot. `summarize_walk_forward()` informa consistencia, retorno OOS y degradación frente al train cuando existe evidencia comparable.

### Monte Carlo

`research_lab.monte_carlo()` hace bootstrap de retornos de trades realizados para medir sensibilidad al orden de operaciones, probabilidad de terminar en pérdida y distribución de drawdown. Es un estrés estadístico, no una predicción de rentabilidad.

### Strategy Lab

Las candidaturas de estrategias pasan por gates conservadores de evidencia, drawdown y muestras suficientes. Una candidatura puede quedar marcada como elegible para revisión, pero **no se auto-aplica**. Los cambios sensibles requieren aprobación explícita.

## Operativa actual

### Acciones

El bot analiza los tickers configurados con EMA, RSI, MACD, ATR, volumen y estructura de tendencia. Las entradas pasan por controles de tamaño, buying power, exposición, posiciones y órdenes abiertas. Las protecciones de acciones se recuperan tras reinicios y se validan antes de permitir nuevas entradas cuando corresponde.

### Crypto

El scanner funciona 24/7 y analiza un universo de pares `/USD`. Las oportunidades se puntúan por impulso, breakout, volumen, volatilidad, confirmación multi-timeframe y régimen de BTC. El ranking de cartera modula la selección y el tamaño sin saltarse los límites del broker.

Las observaciones crypto solo se guardan cuando los indicadores principales son válidos; no se almacenan muestras con ATR/RSI/EMA todavía sin calcular. Las observaciones crypto se etiquetan como `CRYPTO_24_7`, independientemente del horario bursátil.

Antes de una compra crypto se comprueban spread y profundidad del order book. Si el libro es fino, el tamaño puede reducirse; si el spread o la liquidez son demasiado malos, la entrada se bloquea.

### Salidas adaptativas

Las posiciones crypto se gestionan con:

- trailing por software;
- detección de deterioro por momentum, RSI, ADX y régimen;
- spread e imbalance del order book;
- memoria temporal para exigir persistencia antes de reaccionar a ruido aislado;
- score acumulativo de microestructura que puede escalar `tighten` → `reduce` → `exit` solo cuando el deterioro está confirmado;
- cooldown configurable entre acciones de salida.

## Riesgo y ejecución

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
- sin reintentos ciegos de órdenes cuyo resultado sea incierto;
- WebSocket `trade_updates` para recibir estados de órdenes en tiempo real.

Alpaca documenta que `client_order_id` permite identificar y consultar una orden, y recomienda utilizar actualizaciones de órdenes en tiempo real para mantener el estado. También advierte que un timeout de envío no significa necesariamente que la orden no haya llegado, por lo que no debe reenviarse a ciegas.

Los parámetros de persistencia de microestructura se pueden ajustar mediante `DYNAMIC_EXIT_MICROSTRUCTURE_MIN_SAMPLES`, `DYNAMIC_EXIT_MICROSTRUCTURE_WINDOW_SECONDS`, `DYNAMIC_EXIT_MICROSTRUCTURE_IMBALANCE_THRESHOLD`, `DYNAMIC_EXIT_MICROSTRUCTURE_SPREAD_THRESHOLD_PCT`, `DYNAMIC_EXIT_MICROSTRUCTURE_SCORE_REDUCE` y `DYNAMIC_EXIT_MICROSTRUCTURE_SCORE_EXIT`.

## Railway

El proceso debe ejecutarse como **worker**, no como servicio web:

```text
worker: python worker.py
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

Las pruebas de seguridad no envían órdenes a Alpaca. El CI ejecuta compilación y la batería completa con `unittest`.

```bash
python -m compileall -q .
python -m unittest discover -s . -p 'test_*.py' -v
```

La investigación walk-forward y Monte Carlo también está cubierta con pruebas deterministas y de validación de entradas.

## Importante sobre PAPER

Paper Trading es una simulación. No reproduce perfectamente impacto de mercado, slippage por latencia, posición en cola ni otros efectos de ejecución real. Por ello, resultados positivos en PAPER no garantizan resultados positivos en live.

El objetivo de esta versión es **maximizar la calidad de selección y ejecución manteniendo controles de riesgo explícitos**, no garantizar beneficios.
