"""Catálogo narrativo de los 20 arquetipos existentes (ids 1-22, sin el 13) — encargo #113.

Construido a partir de: (a) el campo `efectos` de cada `DefinicionArquetipo` (`motor/arquetipos.py`,
ratio_catalogo/dirección de cada efecto); (b) las entradas de `docs/decisiones_plausibilidad.md`
que documentan ese arquetipo (#10, #16, #17, #20, #35/#36/#44, #56, #66/#67/#99); (c) para los 3
arquetipos `memoria_pura` (7/19/22), el texto real de sus notas y su interacción documentada con
el resto del motor (7 -> `motor/insolvencias.py`).

**Verificación empírica obligatoria (script ad hoc, no permanente — ver docs/decisiones_
plausibilidad.md #113 para el detalle completo)**: para cada uno de los 18 arquetipos
`clase="cuantitativo"` (el encargo hablaba de "17"; el recuento real de `cargar_arquetipos()` da
18 — 1,2,3,4,5,6,8,9,10,11,12,14,15,16,17,18,20,21 — discrepancia declarada, no corregida en la
premisa del encargo, ver revision_113.txt), se generaron 2 casos de control (24.1/grandes_
medianas/semilla 5 y 47.1/pequeñas/semilla 11) con ESE arquetipo en solitario, comparando
intensidad "leve" vs. "fuerte" (2025) sobre los 23 ratios de `RATIOS_PLAUSIBILIDAD_SEÑALIZABLES` +
los 3 informativos. Para 16 de los 18, el ratio/los ratios descritos abajo como "anclas" se
mueven en la dirección esperada en AMBOS casos de control (algunos también con `SeñalRatio`
activa). **2 arquetipos (20 "operaciones_vinculadas", 21 "coberturas") NO superan la comprobación
de forma limpia** — declarados explícitamente como "efecto no claramente apreciable en los 23
ratios de esta sección", no forzados a una descripción que la comprobación no sostiene (ver sus
propias entradas abajo para el detalle numérico exacto)."""

CATALOGO_NARRATIVO_ARQUETIPOS: dict[str, str] = {
    "crecimiento_destruccion_caja": (
        "Simula una empresa que crece en ventas pero destruye caja por el camino: existencias y "
        "saldo de clientes (realizable) crecen más rápido de lo que justificaría la actividad, "
        "drenando tesorería. Verificado en los 2 casos de control (leve→fuerte): la rotación de "
        "existencias baja y el plazo de cobro sube de forma consistente; en el caso con NOF más "
        "tensionado, la disponibilidad cae a cero y aparece una espiral de deuda que erosiona la "
        "rentabilidad vía el interés de la deuda nueva contraída para financiar el déficit."
    ),
    "beneficio_sin_cash_flow": (
        "Un beneficio contable saludable que no se traduce en caja: reduce directamente el "
        "disponible de la empresa por continuidad, sin tocar existencias ni clientes. Verificado "
        "(ver decisiones_plausibilidad.md #17): el indicador correcto para medir su efecto es "
        "disponible/ventas (cae de forma monótona con la intensidad en el barrido de referencia "
        "del proyecto), NO `ratios.liquidez` ni la señal `riesgo_endeudamiento`, que apenas "
        "reaccionan porque el mecanismo no pasa por el circulante operativo — comprobado también "
        "en el caso de control 24.1 (disponibilidad −56% de leve a fuerte)."
    ),
    "aumento_nof": (
        "Variante de \"Crecimiento con destrucción de caja\" centrada en el aumento de las "
        "necesidades operativas de fondos, con su propio rango de intensidad — mismo mecanismo "
        "(existencias y clientes por encima de lo esperado). Verificado: mismo patrón que el "
        "arquetipo 1 en ambos casos de control — rotación de existencias a la baja, plazo de "
        "cobro al alza (con señal de plausibilidad activa en uno de los dos casos)."
    ),
    "deterioro_ciclo_caja": (
        "Deterioro simultáneo de dos palancas del ciclo de caja: el cliente tarda más en pagar "
        "(plazo de cobro sube) y la empresa paga antes a sus proveedores (plazo de pago baja) — "
        "exprime la tesorería por los dos lados a la vez. Verificado en ambos casos de control: "
        "el plazo de cobro sube ~56% y el plazo de pago baja ~55% de leve a fuerte; la "
        "disponibilidad cae a cero en los casos más intensos."
    ),
    "exceso_stock": (
        "Acumulación de existencias por encima del ritmo de ventas — un problema de gestión de "
        "inventario, no de ventas. Verificado: reduce la rotación de existencias y dispara el "
        "plazo medio de existencias (hasta +121% de leve a fuerte en uno de los casos de "
        "control, con señal de plausibilidad activa en ambos)."
    ),
    "aumento_clientes": (
        "Alargamiento del plazo de cobro a clientes — la venta se registra pero el cobro se "
        "retrasa. Verificado: el plazo de cobro sube de forma consistente (~56% de leve a "
        "fuerte, con señal de plausibilidad activa en uno de los dos casos de control)."
    ),
    "dependencia_pocos_clientes": (
        "Sin efecto numérico propio (arquetipo `memoria_pura`): nota de memoria que revela una "
        "concentración de la cifra de negocio en un número reducido de clientes. Interactúa con "
        "el motor de forma indirecta y ya documentada: activa un boost de +10 puntos de "
        "probabilidad y ×1,3 de magnitud sobre el deterioro de valor de créditos comerciales "
        "(`motor/insolvencias.py`) y sobre la partida \"Hacienda Pública pendiente\" a corto "
        "plazo — el único caso en que un arquetipo puramente narrativo influye en cifras del "
        "caso."
    ),
    "refinanciacion": (
        "Reclasificación de deuda financiera de corto a largo plazo sin alterar el importe "
        "total — una renegociación bancaria exitosa. Verificado: la calidad de la deuda mejora "
        "(baja, −6% a −8% de leve a fuerte) y la liquidez a corto sube ligeramente como "
        "consecuencia mecánica (menos pasivo corriente), con señal de plausibilidad activa en "
        "ambos casos de control."
    ),
    "apalancamiento": (
        "Recapitalización apalancada: sube la deuda financiera a largo plazo y financia con "
        "ella una distribución a los socios (el activo no cambia). Verificado: el endeudamiento "
        "sube (con señal de plausibilidad en uno de los dos casos de control) y bajan la "
        "cobertura de gastos financieros y la rentabilidad financiera por el mayor coste de la "
        "deuda nueva."
    ),
    "mejora_ebitda": (
        "Mejora sostenida del margen operativo vía reducción del peso de los gastos de personal "
        "sobre ventas. Verificado: el BAII sobre ventas sube con fuerza (+126%/+35% de leve a "
        "fuerte en los 2 casos de control), arrastrando también la rentabilidad económica y la "
        "cobertura de gastos financieros."
    ),
    "mejora_margen": (
        "Mejora del margen bruto vía reducción del peso de los consumos de explotación sobre "
        "ventas. Verificado: el BAII sobre ventas y la rentabilidad económica suben de forma "
        "marcada (+83%/+18% a +22% de leve a fuerte) en ambos casos de control."
    ),
    "resultado_extraordinario": (
        "Un resultado extraordinario (positivo) concentrado en un único ejercicio, que no se "
        "repite el año siguiente — a diferencia del resto de arquetipos, no es una tendencia "
        "progresiva sino un suceso puntual. Verificado: el efecto es real pero modesto y "
        "transitorio (variaciones de un solo dígito porcentual en liquidez/disponibilidad ese "
        "año), coherente con tratarse de un único ejercicio afectado."
    ),
    "roe_elevado_apalancamiento": (
        "Variante exacta de \"Apalancamiento\" (arquetipo 9), mismo mecanismo — sube deuda a "
        "largo para financiar una distribución. Verificado: mismos síntomas que el 9 "
        "(endeudamiento al alza, con señal de plausibilidad en uno de los dos casos de control; "
        "cobertura de gastos financieros y ROE a la baja) — pese al nombre, el mecanismo real "
        "(más gasto financiero sobre un PN menor) hace bajar el ROE en la mayoría de los casos "
        "del proyecto (ver decisiones_plausibilidad.md #10: solo el 53,3% de los casos suben el "
        "ROE de cierre, y típicamente en el año en que se contrae la deuda, no necesariamente en "
        "el último ejercicio del caso)."
    ),
    "riesgo_liquidez_pese_beneficio": (
        "Variante exacta de \"Beneficio sin cash flow suficiente\" (arquetipo 2), mismo "
        "mecanismo de tesorería — ver esa ficha para la verificación completa. El indicador "
        "correcto es disponible/ventas, no `ratios.liquidez` ni la señal de endeudamiento."
    ),
    "riesgo_refinanciacion": (
        "Reclasificación de deuda de largo a corto plazo — lo contrario de \"Refinanciación\" "
        "(8): un vencimiento cercano que la empresa aún no ha renegociado. Verificado: la "
        "calidad de la deuda empeora (sube, +15% a +19% de leve a fuerte en ambos casos de "
        "control) y el fondo de maniobra se resiente. Enlaza directamente con la Nota 7 de la "
        "Memoria (calendario de vencimientos, encargo #112): conviene revisar si hay "
        "concentración relevante en el tramo \"1 año\"."
    ),
    "capex_elevado": (
        "Inversión en inmovilizado por encima del ritmo de ventas, financiada con deuda a largo "
        "plazo nueva — sin tocar el circulante. Verificado: la rotación del activo no corriente "
        "cae con fuerza (−56% a −57% de leve a fuerte en ambos casos de control) y arrastra a la "
        "baja el ROI/ROE por el mayor gasto financiero y la base de activo más grande."
    ),
    "adquisicion": (
        "Salto discreto (no progresivo) del activo no corriente en 2024, financiado con caja "
        "disponible y deuda nueva, con una fracción de las ventas de ese año calificada de "
        "\"inorgánica\". Verificado: cae la rotación del activo no corriente y la cobertura de "
        "gastos financieros en ambos casos de control (−44% a −69%), con una caída marcada del "
        "ROE por el nuevo servicio de la deuda."
    ),
    "activo_mantenido_venta": (
        "Sin efecto numérico (arquetipo `memoria_pura`): nota de memoria que declara un activo "
        "no corriente clasificado como mantenido para la venta. No dispara ningún mecanismo del "
        "grupo 8/9 del PGC — la corrección de valor, si la hubiera, iría a PyG como deterioro, "
        "no a una reserva de patrimonio neto (NRV 7.ª)."
    ),
    "operaciones_vinculadas": (
        "Una de 5 operaciones posibles con partes vinculadas (préstamo a la matriz, "
        "financiación recibida del grupo, facturación de servicios de gestión, arrendamiento a "
        "un socio, o asistencia técnica recibida) — solo una está activa por caso, sorteada una "
        "única vez. **Efecto en los 23 ratios de esta sección NO GARANTIZADO**: verificado que, "
        "cuando se sortea una de las 3 operaciones comerciales/\"varios\", el efecto queda "
        "confinado a sub-partidas del desglose de deudores/acreedores que no forman parte de "
        "ningún ratio de plausibilidad (0,00% de diferencia observada entre intensidad leve y "
        "fuerte en el caso de control 47.1/pequeñas/semilla 11); solo las 2 operaciones "
        "financieras (préstamo a la matriz / financiación recibida de grupo) mueven magnitudes "
        "que sí pueden alterar tesorería o fondo de maniobra (observado en el caso de control "
        "24.1/grandes_medianas/semilla 5: disponibilidad a cero, fondo de maniobra −30%). "
        "Consulta la nota 10 de la Memoria para ver qué operación concreta se activó en este "
        "caso."
    ),
    "coberturas": (
        "Cobertura de flujos de efectivo (swap de tipo de interés) sobre deuda a tipo variable. "
        "**Efecto en los 23 ratios de esta sección NO CLARAMENTE APRECIABLE**: verificado en "
        "ambos casos de control que `ratios.endeudamiento` (el ratio de trazabilidad declarado "
        "del efecto) varía menos del 0,3% relativo entre intensidad leve y fuerte — el mecanismo "
        "real coloca un derivado (activo o pasivo, según el signo del valor razonable del swap) "
        "y una reserva de patrimonio neto que no está expuesta como ratio propio en esta "
        "sección; su efecto en PyG (ineficacia/transferencia por vencimiento) es pequeño frente "
        "al resto de la cuenta de resultados. Consulta la Nota 9 (situación fiscal) y la Nota 7 "
        "(el derivado, si es pasivo, aparece en la línea \"Derivados\" del calendario de "
        "vencimientos, encargo #112) para el detalle."
    ),
    "informacion_relevante_memoria": (
        "Arquetipo \"comodín\" (`memoria_pura`): una nota de memoria sobre una circunstancia "
        "relevante no cubierta por los demás arquetipos (p. ej. una contingencia legal), sin "
        "ningún efecto en balance, PyG ni ratios — introduce matices cualitativos sin forzar un "
        "mecanismo numérico donde no corresponde."
    ),
}
