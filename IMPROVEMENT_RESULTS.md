# Mejoras verificadas de BOTTRADE — 7 septiembre 2026

Se mantienen PAPER, acciones y criptomonedas, el histórico persistente y la posición NVDA. Estas mejoras reducen fallos de ejecución y establecen un presupuesto de costes para nuevas compras; no acreditan rentabilidad futura.

## Cambios que se activan

- Revisión final de exposición usando el precio ask actual, posiciones y órdenes pendientes. Una subida del precio reduce la cantidad permitida; una exposición excesiva bloquea la compra. Nunca se modifica una posición existente.
- Las comprobaciones y envíos de compras quedan serializados dentro del proceso. Las ventas no esperan este bloqueo. No es un bloqueo distribuido ni garantiza exclusión frente a operaciones externas o retrasos del broker.
- Cantidades crypto redondeadas hacia abajo según el incremento y mínimo que informa el activo, en lugar de truncar siempre a seis decimales. Datos de tamaño ausentes o inválidos bloquean la compra.
- Una operación histórica ya no sustituye a una cotización ask ausente. Datos pendientes no finitos y snapshots incompletos bloquean nuevas compras.
- Presupuesto de costes crypto: hipótesis de 25 puntos básicos de comisión por lado; impacto de entrada estimado con el libro, e impacto de salida supuesto igual al mayor entre ese impacto y 0,10%. Se exige relación objetivo/riesgo neta de al menos 1. El cálculo usa las distancias configuradas de objetivo y stop: no estima probabilidad de acierto ni reproduce cada salida dinámica. Un salto de precio puede superar la pérdida modelada.

La hipótesis de costes no está ajustada para conseguir un backtest favorable y el impacto futuro no se conoce. El control actúa sobre nuevas compras cuando el control de calidad crypto está habilitado. Los parámetros quedan explícitos: `CRYPTO_ASSUMED_TAKER_FEE_BPS`, `CRYPTO_ASSUMED_EXIT_IMPACT_PCT` y `CRYPTO_MIN_NET_REWARD_RISK`.

## Ejemplo del presupuesto de costes

Con objetivo 4%, stop 2% y comisión 0,25% por lado:

| Impacto entrada / salida supuesto | Objetivo neto | Pérdida al stop modelada | Objetivo / riesgo | Decisión |
|---|---:|---:|---:|---|
| 0.05% / 0.10% | 3.326% | 2.635% | 1.262 | Permitir |
| 0.45% / 0.45% | 2.554% | 3.362% | 0.760 | Bloquear |

## Investigación de señales: resultados y rechazo

Se fijaron dos filtros antes de abrir resultados: confirmación de tendencia y confirmación más un límite a la extensión de la subida. Las ventas y salidas se conservan. El protocolo está en `IMPROVEMENT_PROTOCOL.md` y se puede repetir con `python improvement_research.py RUTA_DATOS RUTA_SALIDA`.

Se completaron 192 combinaciones con datos Alpaca: 6 activos, 4 semanas del 22 junio al 20 julio exclusivo, 4 estrategias y 2 escenarios de costes. El historial desde el 1 de junio sirve de contexto. Ningún fallo de datos. Se excluyen explícitamente los ajustes de cartera y consultas al mercado en vivo del cálculo offline; un test verifica ese aislamiento.

Rentabilidad media semanal por activo sobre $100.000 de capital total, con posición máxima del 10%. No es rentabilidad de una cartera simultánea ni rentabilidad acumulada. El escenario adverso duplica el deslizamiento.

| Mercado | Costes | Estrategia | Media neta | Peor caída | Operaciones |
|---|---|---|---:|---:|---:|
| Acciones | base | BOTTRADE base | -0.0220% | -0.3921% | 18 |
| Acciones | base | Mantener 10% | +0.0418% | -1.0101% | 12 |
| Acciones | base | Confirmación | -0.0089% | -0.3911% | 17 |
| Acciones | base | Confirmación + extensión | +0.0148% | -0.3911% | 15 |
| Acciones | stress | BOTTRADE base | -0.0353% | -0.4118% | 18 |
| Acciones | stress | Mantener 10% | +0.0317% | -1.0142% | 12 |
| Acciones | stress | Confirmación | -0.0217% | -0.4109% | 17 |
| Acciones | stress | Confirmación + extensión | +0.0036% | -0.4109% | 15 |
| Crypto | base | BOTTRADE base | -0.3080% | -1.6352% | 56 |
| Crypto | base | Mantener 10% | +0.0936% | -1.4839% | 12 |
| Crypto | base | Confirmación | -0.3080% | -1.6352% | 56 |
| Crypto | base | Confirmación + extensión | -0.2714% | -1.4060% | 51 |
| Crypto | stress | BOTTRADE base | -0.4302% | -1.9084% | 58 |
| Crypto | stress | Mantener 10% | +0.0735% | -1.4826% | 12 |
| Crypto | stress | Confirmación | -0.4302% | -1.9084% | 58 |
| Crypto | stress | Confirmación + extensión | -0.3679% | -1.6702% | 52 |

Ningún candidato supera los mínimos fijados. El filtro de extensión mejora algunas cifras, pero crypto sigue perdiendo en promedio y acciones solo produce 15 operaciones por escenario, por debajo del mínimo de 20. No se activan los filtros ni se retocan umbrales para forzar la aprobación. El periodo reservado del 20 julio al 17 agosto permanece sin abrir para esta selección. Incluso superarlo habría requerido evaluación prospectiva PAPER; estos datos históricos no demuestran independencia frente al desarrollo original de la estrategia.

## Validación

158 pruebas pytest y 6 subpruebas aprobadas; unittest: 144 pruebas aprobadas. Compilación y revisión de diferencias sin errores. La validación remota y el despliegue se verifican después del push.

Fuentes oficiales: [modelo de activo y campos de tamaños](https://alpaca.markets/sdks/python/api_reference/trading/models.html), [operativa crypto](https://docs.alpaca.markets/us/docs/crypto-trading-1), [comisiones crypto](https://docs.alpaca.markets/us/docs/crypto-fees). Las tarifas utilizadas son hipótesis del primer nivel, no una consulta del nivel efectivo de esta cuenta.
