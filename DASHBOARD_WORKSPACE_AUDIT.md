# BOTTRADE: comparación de interfaces y mejoras — 7 septiembre 2026

Las referencias de rentabilidad anteriores eran estrategias, no aplicaciones comerciales. Para esta revisión se han usado documentación y páginas oficiales de tres productos actuales; no se presenta un ranking de calidad ni se afirma haber probado sus cuentas privadas.

| Referencia | Qué se aprende | Aplicación en BOTTRADE |
|---|---|---|
| TradingView | Búsqueda, clasificación y seguimiento de activos mediante listas | Búsqueda de posiciones, filtros de acciones/crypto, favoritos locales y orden por valor, ganancia, pérdida o nombre |
| IBKR PortfolioAnalyst | Separar resumen, rendimiento, posiciones relevantes, distribución y riesgo | Navegación por secciones, jerarquía de cifras, mayores/menores G/P pendientes, exposición y avisos de cobertura de stops |
| Coinbase Advanced | Espacio de trabajo organizado y preferencias persistentes | Densidad de tabla guardada, panel de detalle, exploración del histórico y adaptación del listado a pantallas pequeñas |

Fuentes: [listas de TradingView](https://www.tradingview.com/support/solutions/43000745825-mastering-the-tradingview-watchlists/), [widgets de PortfolioAnalyst](https://www.interactivebrokers.com/campus/trading-lessons/portfolioanalyst-widgets/), [Coinbase Advanced](https://www.coinbase.com/advanced-trade). Se han adaptado patrones de uso; no se copian marcas, pantallas o activos gráficos.

## Funciones entregadas

- Interfaz más legible, contraste mejorado, navegación por secciones y vocabulario en español.
- Filtros por nombre y mercado, favoritos de las posiciones actuales, ordenación y ocultación opcional de residuos. Los filtros nunca cambian los totales financieros.
- Detalle de posición con cantidad, precios, G/P y retorno, más escenario de precio de −10% a +10%. Considera el signo de posiciones cortas. Es una instantánea identificada por su hora, antes de costes, no una previsión.
- Exploración del histórico mediante deslizador accesible con teclado y lectura exacta de cada muestra.
- Búsqueda y filtros de compras/ventas en órdenes y ejecuciones. Exportación CSV de posiciones filtradas y ejecuciones filtradas, con protección frente a fórmulas en campos de texto. Una venta se muestra como dinero recibido, no como beneficio verificado.
- Avisos de cobertura incompleta de stops, ejecuciones no disponibles e histórico insuficiente. Efectivo negativo conserva el signo en importe y porcentaje; concentración NVDA mantiene su fórmula.
- Actualización cada 20 segundos, pausa/reanudación, tiempo desde la última lectura, cancelación de respuestas antiguas y conservación explícita de la última lectura ante error. La conexión fallida no aparece como correcta.
- Corrección de la ruta principal: ahora sirve la página enriquecida real, incluyendo analista e histórico. Se eliminan temporizadores superpuestos y consultas duplicadas al histórico.
- App web con manifiesto e icono, y pantalla sin conexión explícita. No guarda respuestas financieras para presentarlas como actuales estando offline.
- Teclado, enlace de salto, etiquetas de controles, diálogo nativo y respeto a movimiento reducido. En pantallas pequeñas, las posiciones pasan a tarjetas y el detalle contiene las columnas secundarias.

## Alcance y límites

La app sigue siendo de consulta y respeta PAPER. No se han añadido botones para comprar, vender o modificar el bot; no se altera la cartera NVDA. Los favoritos solo siguen posiciones que llegan del broker, no un nuevo feed de cotizaciones. Los avisos son locales en la página, no notificaciones en segundo plano. No se ha añadido un libro de órdenes ni velas ficticias. El beneficio realizado continúa sin afirmarse cuando no hay coste histórico completo verificable.

Validación local: 74 pruebas, incluida ejecución de las funciones JavaScript, ordenación/filtrado, escenarios para cortos, exportación, respuestas fuera de orden y errores de red, más comprobación de la ruta que realmente sirve el HTML y del comportamiento offline. Se completará la comprobación visual y de despliegue sobre Railway.
