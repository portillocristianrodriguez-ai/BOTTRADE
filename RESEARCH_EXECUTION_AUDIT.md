# Auditoría de ejecución y comparación reproducible — 7 septiembre 2026

El estudio NO acredita ventaja competitiva de BOTTRADE ni identifica los mejores bots comerciales. Mantener el activo obtuvo la mayor rentabilidad media en esta muestra. No se han optimizado parámetros ni promocionado estrategias con estos resultados. Se mantiene PAPER, acciones y criptomonedas, el histórico persistente y la posición/concentración NVDA aceptada por el usuario.

## Correcciones verificadas

- Comisiones de entrada y salida contabilizadas una sola vez, conciliando efectivo final con beneficios/pérdidas netos.
- Señales al cierre ejecutadas en la apertura siguiente, sin utilizar precios futuros para dimensionar órdenes.
- Stops con saltos de precio ejecutados a la apertura desfavorable; trailing actualizado para la siguiente vela. Si stop y objetivo coinciden en una vela, se asume primero el stop.
- Límites de exposición de la simulación basados en patrimonio actual y precios disponibles en la apertura, incluyendo saltos de posiciones existentes.
- Rechazo de OHLCV inválidos, duplicados y precios incoherentes. Sin rellenar ni borrar silenciosamente barras inválidas.
- Compras crypto bloqueadas si falta liquidez verificable, el libro tiene más de 30 segundos, cotizaciones inválidas o el tamaño reducido sigue siendo inseguro.
- Exposición desconocida, configuración no finita y señales de volumen antiguas no pueden autorizar nuevas compras.
- Validación temporal con contexto exclusivamente anterior; simulación Monte Carlo basada en impacto monetario sobre el capital, incluyendo la primera pérdida.

## Datos y método

Datos descargados directamente de Alpaca el 7/9/2026, desde el 1/6/2026 hasta el 7/9/2026 exclusivo. SPY, AAPL y NVDA: velas de 15 minutos, feed IEX, ajuste por splits. BTC/USD, ETH/USD y SOL/USD: velas de 5 minutos. Cada archivo conserva su SHA-256, recuento y límites temporales en el manifiesto del resultado. Los originales quedan conservados localmente, sin publicar históricos de mercado en el repositorio.

Tres ventanas semanales fijas: 17–24 agosto, 24–31 agosto y 31 agosto–7 septiembre. El historial previo sirve únicamente para indicadores; no se opera durante ese contexto. Se comprueban 144 combinaciones: 6 activos × 3 ventanas × 4 estrategias × 2 escenarios de costes. Cero fallos de validación.

Capital inicial por prueba: $100.000. Simulación larga, una posición por activo, límite del 10% del patrimonio, stop 2%, objetivo 4%, trailing 1,5%. Comprar y mantener invierte el 10% inicial, sin rebalanceo ni esos stops. Las referencias activas usan medias 20/50 y reversión de 2% frente a media de 20 barras, parámetros fijados antes de consultar resultados.

Costes por lado: crypto 25 puntos básicos de comisión y 10 de deslizamiento; acciones 1 punto básico como provisión de costes y 5 de deslizamiento. El escenario adverso duplica el deslizamiento. Son hipótesis, no costes reales medidos de esta cuenta. La comisión crypto corresponde a la tarifa taker de primer nivel publicada; el nivel efectivo puede ser distinto.

## Resultados

La rentabilidad es sobre TODO el capital de cada prueba. La media es aritmética entre las 18 combinaciones activo/semana; no representa una cartera simultánea, una rentabilidad acumulada ni una predicción. La peor caída es la mayor caída desde un máximo dentro de una prueba.

| Escenario | Estrategia | Rentabilidad media | Peor caída | Operaciones cerradas |
|---|---|---:|---:|---:|
| base | Señal BOTTRADE | -0.110% | -0.875% | 65 |
| base | Comprar y mantener 10% | +0.538% | -1.377% | 18 |
| base | Reversión a la media | -0.042% | -0.558% | 19 |
| base | Tendencia 20/50 | -0.906% | -3.212% | 336 |
| stress | Señal BOTTRADE | -0.179% | -1.003% | 66 |
| stress | Comprar y mantener 10% | +0.522% | -1.376% | 18 |
| stress | Reversión a la media | -0.058% | -0.597% | 19 |
| stress | Tendencia 20/50 | -1.236% | -4.000% | 335 |

## Límites y decisión

Estas ventanas son recientes, cortas y correlacionadas. No son una validación independiente de todos los regímenes de mercado; tampoco existe separación histórica demostrable respecto al desarrollo original de la estrategia. No permiten afirmar significación estadística ni superioridad futura. El feed IEX no representa todo el mercado y no se rellenan intervalos sin barras. El estudio compara señales aisladas; no reproduce toda la selección concurrente de cartera, colas de ejecución, profundidad histórica ni salidas dinámicas de producción. La exposición del 10% pertenece solo al estudio y no modifica NVDA.

El ganador de esta muestra es comprar y mantener, pero no se convierte automáticamente en estrategia de producción. La señal BOTTRADE pierde dinero de media con costes. Para declarar una mejora económica harían falta pruebas prospectivas PAPER y datos de otros regímenes, con criterios fijados antes de observar resultados. Las mejoras entregadas corrigen la fiabilidad técnica; no demuestran todavía una ventaja de trading.

## Reproducción y validación

`python benchmark_research.py RUTA_DATOS resultado.json`

La carpeta debe contener `manifest.json` y los CSV con los hashes originales. El programa no coloca órdenes, no descarga credenciales y no cambia la configuración de producción. El test de causalidad contrasta los indicadores calculados por prefijos contra el cálculo completo.

Validación local: 140 pruebas pytest y 6 subtests; unittest y compilación también verificados. La validación remota y el despliegue se comprueban después del push.

Fuentes oficiales consultadas: [limitaciones de PAPER](https://docs.alpaca.markets/us/docs/paper-trading), [tarifas crypto](https://docs.alpaca.markets/us/docs/crypto-fees), [barras históricas](https://docs.alpaca.markets/us/reference/stockbars).
