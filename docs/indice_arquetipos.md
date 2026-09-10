# Índice compacto de arquetipos

Atajo de arranque de sesión — ver `CLAUDE.md` para las restricciones de uso. Fuente de verdad:
`data/arquetipos.json` (definiciones) + `motor/evolucion_arquetipo.py` (mecanismo). Estado
`IMPLEMENTADO (sin comitear)` refleja el árbol de trabajo en el momento de escribir este índice —
si ya se comiteó, es simplemente `CERRADO`; comprobar `git log`/`git status` si hay duda.

| # | Nombre corto | `id` en JSON | Mecanismo | Estado | Dependencias / notas |
|---|---|---|---|---|---|
| 1 | Crecimiento con destrucción de caja | `crecimiento_destruccion_caja` | `masa_circulante` (existencias+realizable) + `rango_crecimiento_pleno` propio | CERRADO | Único arquetipo con rango de crecimiento propio en el JSON |
| 2 | Beneficio sin cash flow suficiente | `beneficio_sin_cash_flow` | `tesoreria` (= mecanismo exacto del 15) | IMPLEMENTADO (sin comitear) | — |
| 3 | Aumento de NOF | `aumento_nof` | `masa_circulante` (existencias+realizable) | CERRADO | Huella idéntica a la de circulante del 1 |
| 4 | Deterioro del ciclo de caja | `deterioro_ciclo_caja` | `masa_circulante` (realizable +, acreedores −) | CERRADO | Primer uso de `SIGNO_NOF_MASA_CIRCULANTE` con signos opuestos |
| 5 | Exceso de stock | `exceso_stock` | `masa_circulante` (solo existencias) | CERRADO | Caso base, una sola variable |
| 6 | Aumento de clientes (base) | `aumento_clientes` | `masa_circulante` (solo realizable) | CERRADO | — |
| 7 | Dependencia de pocos clientes | — | cualitativo puro | PENDIENTE | No pasa por el motor de generación |
| 8 | Refinanciación | `refinanciacion` | `reclasificacion_deuda` (dirección +1) | CERRADO | No altera deuda financiera total; sin efecto en endeudamiento |
| 9 | Apalancamiento | `apalancamiento` | `apalancamiento` | CERRADO | Requiere deuda_media → gastos financieros (enlace deuda-interés); "espiral de deuda" documentada (ver decisiones) |
| 10 | Mejora de EBITDA | `mejora_ebitda` | `pyg_primitiva` (gastos_personal, base dinámica baii) | CERRADO | `pyg_contencion_al_limite` + `nota_memoria` en el caso límite (ruido de base) |
| 11 | Mejora de margen | `mejora_margen` | `pyg_primitiva` (consumos_explotacion, base fija margen_bruto) | CERRADO | Techo de plausibilidad de margen_bruto (ver decisiones) |
| 12 | Resultado extraordinario | `resultado_extraordinario` | `evento_puntual` (nuevo) | IMPLEMENTADO (sin comitear) | Único año sorteado (2024/2025), sin patrón de intensidad progresiva |
| 13 | Diferencias EBITDA/EBIT/beneficio/caja | — | — | NO APLICA AL MOTOR | Comparación de síntesis sobre magnitudes ya generadas (baii/bai/resultado/amortizaciones) — capa de análisis futura |
| 14 | ROE elevado por apalancamiento | `roe_elevado_apalancamiento` | `apalancamiento` (= variante exacta del 9) | IMPLEMENTADO (sin comitear) | ROE *headline* sube solo ~53% de los casos vs. base (ver decisiones — no es bug) |
| 15 | Riesgo de liquidez pese a beneficio | `riesgo_liquidez_pese_beneficio` | `tesoreria` | CERRADO | Sin techo/suelo de plausibilidad sectorial (limitación documentada) |
| 16 | Riesgo de refinanciación | `riesgo_refinanciacion` | `reclasificacion_deuda` (dirección −1) + `nota_memoria` | IMPLEMENTADO (sin comitear) | Nota de memoria activa cada año que el efecto actúa (no es caso límite, es la huella habitual) |
| 17 | Capex elevado | `capex_elevado` | `capex` (nuevo) | IMPLEMENTADO (sin comitear) | Financiado con deuda a largo nueva; 15,6% de activaciones de `riesgo_endeudamiento` en stress test, 100% `contencion_al_limite` (sin palanca de circulante) |
| 18 | Adquisición | — | — | PENDIENTE (sesión propia) | Salto discreto no orgánico + fondo de comercio + memoria específica — el más distinto de todos, deliberadamente fuera de los lotes anteriores |
| 19 | Activo mantenido para la venta | — | — | PENDIENTE | Reclasificación de un activo específico, no un ratio |
| 20 | Operaciones vinculadas | — | — | PENDIENTE | Cualitativo puro (solo memoria) |
| 21 | Coberturas | — | — | PENDIENTE | Cualitativo + PN |
| 22 | Información relevante en memoria | — | — | PENDIENTE | Comodín narrativo, no modifica cifras |
