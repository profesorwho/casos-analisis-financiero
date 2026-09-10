# Índice compacto de arquetipos

Atajo de arranque de sesión — ver `CLAUDE.md` para las restricciones de uso. Fuente de verdad:
`data/arquetipos.json` (definiciones) + `motor/evolucion_arquetipo.py` (mecanismo). Estado
`IMPLEMENTADO (sin comitear)` refleja el árbol de trabajo en el momento de escribir este índice —
si ya se comiteó, es simplemente `CERRADO`; comprobar `git log`/`git status` si hay duda.

| # | Nombre corto | `id` en JSON | Mecanismo | Estado | Dependencias / notas |
|---|---|---|---|---|---|
| 1 | Crecimiento con destrucción de caja | `crecimiento_destruccion_caja` | `masa_circulante` (existencias+realizable) + `rango_crecimiento_pleno` propio | CERRADO | Único arquetipo con rango de crecimiento propio en el JSON |
| 2 | Beneficio sin cash flow suficiente | `beneficio_sin_cash_flow` | `tesoreria` (= mecanismo exacto del 15) | CERRADO | — |
| 3 | Aumento de NOF | `aumento_nof` | `masa_circulante` (existencias+realizable) | CERRADO | Huella idéntica a la de circulante del 1 |
| 4 | Deterioro del ciclo de caja | `deterioro_ciclo_caja` | `masa_circulante` (realizable +, acreedores −) | CERRADO | Primer uso de `SIGNO_NOF_MASA_CIRCULANTE` con signos opuestos |
| 5 | Exceso de stock | `exceso_stock` | `masa_circulante` (solo existencias) | CERRADO | Caso base, una sola variable |
| 6 | Aumento de clientes (base) | `aumento_clientes` | `masa_circulante` (solo realizable) | CERRADO | — |
| 7 | Dependencia de pocos clientes | `dependencia_pocos_clientes` | `memoria_pura` (`motor/memoria.py`) | IMPLEMENTADO (sin comitear) | nº clientes + % ventas por intensidad (leve 3-4/35-45%, moderado 2-3/45-60%, fuerte 1-2/60-75%); etiquetas `("clientes","concentracion")` |
| 8 | Refinanciación | `refinanciacion` | `reclasificacion_deuda` (dirección +1) | CERRADO | No altera deuda financiera total; sin efecto en endeudamiento |
| 9 | Apalancamiento | `apalancamiento` | `apalancamiento` | CERRADO | Requiere deuda_media → gastos financieros (enlace deuda-interés); "espiral de deuda" documentada (ver decisiones) |
| 10 | Mejora de EBITDA | `mejora_ebitda` | `pyg_primitiva` (gastos_personal, base dinámica baii) | CERRADO | `pyg_contencion_al_limite` + `nota_memoria` en el caso límite (ruido de base) |
| 11 | Mejora de margen | `mejora_margen` | `pyg_primitiva` (consumos_explotacion, base fija margen_bruto) | CERRADO | Techo de plausibilidad de margen_bruto (ver decisiones) |
| 12 | Resultado extraordinario | `resultado_extraordinario` | `evento_puntual` (nuevo) | CERRADO | Único año sorteado (2024/2025), sin patrón de intensidad progresiva |
| 13 | Diferencias EBITDA/EBIT/beneficio/caja | — | — | NO APLICA AL MOTOR | Comparación de síntesis sobre magnitudes ya generadas (baii/bai/resultado/amortizaciones) — capa de análisis futura |
| 14 | ROE elevado por apalancamiento | `roe_elevado_apalancamiento` | `apalancamiento` (= variante exacta del 9) | CERRADO | ROE headline sube solo 53,3% vs. base 2023, pero 78,1% en al menos un año (2024 o 2025) — se diluye en el 2º año por coste financiero acumulado (ver decisiones). Ficha docente pendiente de matizar (fuera del motor) |
| 15 | Riesgo de liquidez pese a beneficio | `riesgo_liquidez_pese_beneficio` | `tesoreria` | CERRADO | Sin techo/suelo de plausibilidad sectorial (limitación documentada) |
| 16 | Riesgo de refinanciación | `riesgo_refinanciacion` | `reclasificacion_deuda` (dirección −1) + `nota_memoria` | CERRADO | Nota de memoria activa cada año que el efecto actúa (no es caso límite, es la huella habitual) |
| 17 | Capex elevado | `capex_elevado` | `capex` (nuevo) | CERRADO | Financiado con deuda a largo nueva; 15,6% de activaciones de `riesgo_endeudamiento` en stress test, 100% `contencion_al_limite` (sin palanca de circulante) |
| 18 | Adquisición | `adquisicion` | `adquisicion` (nuevo) | CERRADO | Salto discreto de `activo_no_corriente` en año FIJO (2024, no sorteado), financiado con caja+deuda a largo; separa `ventas_organicas_eur`/`ventas_inorganicas_eur`; `nota_memoria` obligatoria (no opcional, a diferencia de 10/16); 70/972 activaciones de `riesgo_endeudamiento` (7,2%), 100% señalizadas, 100% `contencion_al_limite` |
| 19 | Activo mantenido para la venta | `activo_mantenido_venta` | `memoria_pura` (`motor/memoria.py`) | IMPLEMENTADO (sin comitear) | 5 plantillas fijas (tipo de activo + motivo ya combinados); no usa datos de la empresa; etiquetas `("activo","desinversion")` |
| 20 | Operaciones vinculadas | `operaciones_vinculadas` | `memoria_pura` (`motor/memoria.py`) | IMPLEMENTADO (sin comitear) | Importe = %(2-5/5-10/10-18 según intensidad) de ventas/PN/deuda financiera real según el tipo de operación; suelo `SUELO_IMPORTE_VINCULADAS_EUR=30.000€` (ver decisiones #14); etiquetas `("vinculadas","partes_relacionadas")` |
| 21 | Coberturas | `coberturas` | `memoria_pura` (`motor/memoria.py`) | IMPLEMENTADO (sin comitear) | Nocional = %(30-45/45-65/65-90 según intensidad) de la deuda financiera real; suelo `SUELO_NOCIONAL_COBERTURA_EUR=50.000€` (ver decisiones #14); Euríbor 3/6/12 meses sorteado; etiquetas `("deuda","cobertura_riesgo")` |
| 22 | Información relevante en memoria | `informacion_relevante_memoria` | `memoria_pura` (`motor/memoria.py`) | IMPLEMENTADO (sin comitear) | Comodín: 10 temas distintos (no variaciones de uno), cada uno con su propia etiqueta — tema "proveedor clave" señalado como solapado con el 7 para la futura lógica de coherencia (ver decisiones #15) |
