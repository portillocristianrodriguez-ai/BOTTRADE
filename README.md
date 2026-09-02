# Bot de trading intradía — Alpaca (para Railway)

## Estructura
```
config.py          # lee toda la configuración de variables de entorno
broker.py           # todo lo que habla con la API de Alpaca
estrategia.py        # indicadores (EMA, RSI, MACD) y lógica de señales
notificaciones.py    # avisos por Telegram (opcional)
main.py              # loop principal
Procfile              # le dice a Railway cómo correr el bot (worker)
```

## 1. Probar en local primero

```bash
pip install -r requirements.txt
export ALPACA_API_KEY="tu_key"
export ALPACA_API_SECRET="tu_secret"
export ALPACA_PAPER=true
python main.py
```

Sacá tus keys gratis en https://alpaca.markets — asegurate de generarlas
en modo **paper trading** (dinero simulado), no real.

## 2. Deploy en Railway

1. Subí esta carpeta a un repo nuevo en GitHub (ej. `trading-bot`).
2. En Railway: **New Project -> Deploy from GitHub repo** -> elegí el repo.
3. Railway va a detectar el `Procfile` y correrlo como **worker** (no
   necesita puerto HTTP, así que no uses "web service").
4. En **Settings -> Variables**, agregá:

   | Variable | Valor |
   |---|---|
   | `ALPACA_API_KEY` | tu key de Alpaca |
   | `ALPACA_API_SECRET` | tu secret de Alpaca |
   | `ALPACA_PAPER` | `true` (dejalo así hasta confiar en el bot) |
   | `TICKERS` | `AAPL,MSFT,NVDA,TSLA,AMZN` (o los que quieras) |
   | `CHECK_INTERVAL_MINUTES` | `5` |
   | `TELEGRAM_BOT_TOKEN` | opcional, si querés notificaciones |
   | `TELEGRAM_CHAT_ID` | opcional, si querés notificaciones |

5. Deploy. Mirá los **Logs** en Railway para ver cada ciclo: precio,
   señal, y si compró/vendió.

## Cómo decide comprar o vender
- **COMPRAR**: la EMA rápida (9) cruza por encima de la lenta (21) —
  señal de tendencia alcista arrancando — con RSI fuera de sobrecompra
  y MACD confirmando momentum positivo.
- **VENDER**: la EMA rápida cruza por debajo de la lenta, o el RSI entra
  en sobrecompra (posible techo del movimiento).
- Cada compra lleva stop-loss (-2%) y take-profit (+4%) automáticos.
- El tamaño de cada operación se calcula para arriesgar solo el 2% del
  capital total por trade — así una racha de pérdidas no te destruye
  la cuenta.

## Antes de usar plata real — leelo
- Dejalo corriendo en `ALPACA_PAPER=true` (simulado) varias semanas.
  Revisá los logs, entendé cada decisión, confirmá que el resultado
  neto sea positivo.
- Ningún indicador técnico predice el futuro con certeza. En mercados
  sin tendencia clara (choppy) esta estrategia puede dar señales falsas
  seguidas y perder en varias operaciones antes de acertar una.
- Si es para una cuenta de fondeo (prop firm), revisá antes las reglas
  de esa firma (drawdown máximo diario, tamaño de posición permitido)
  — pueden no coincidir con los límites de este bot.
- No es asesoramiento financiero.

## Próximos pasos posibles
- Backtesting contra datos históricos antes de ir a producción.
- Trailing stop-loss en vez de fijo.
- Filtro de volumen mínimo para evitar señales en momentos ilíquidos.
