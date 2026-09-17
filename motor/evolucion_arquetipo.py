"""Evolución de una empresa a lo largo de 3 ejercicios (2023-2025) aplicando UN arquetipo.

Motor GENÉRICO: qué arquetipo se aplica es un dato (`data/arquetipos.json`, cargado por
`motor.arquetipos`), no código hardcodeado por arquetipo. Este módulo separa dos cosas:

- **Mecanismo general** (reutilizable para cualquier arquetipo cuantitativo que encaje en una
  de las 4 formas de efecto soportadas): modelo de continuidad año a año de un ratio, cascada
  de PyG, enlace deuda-interés, contención de plausibilidad del endeudamiento, cuadre del
  balance. Vive en funciones de este módulo que no mencionan ningún arquetipo por su nombre.
- **Lo específico de cada arquetipo**: qué variable mueve, en qué dirección y contra qué
  ratio ancla — vive SOLO en `data/arquetipos.json`, no en código.

No todos los arquetipos cuantitativos de la sección 2.24 encajan en las 8 formas ya
implementadas (masa_circulante, pyg_primitiva, apalancamiento, tesoreria, reclasificacion_deuda,
evento_puntual, capex, adquisicion) — ver el informe de clasificación en el mensaje que acompaña
a cada commit para el detalle de cuáles sí y cuáles necesitarían una forma nueva (o no aplican
al motor en absoluto, como el arquetipo 13). Los arquetipos cualitativos puros (7, 19, 20, 21,
22) no pasan por este mecanismo en absoluto.

Sin matriz de compatibilidad (combinación de varios arquetipos a la vez), sin EFE/ECPN
completos, sin dividendos.

Diseño del mecanismo (decisiones no explícitas en la fórmula general de la sección 2.24, que
había que fijar para poder implementar):

- **2023 es el único ejercicio que usa el catálogo + ruido** (vía `motor.empresa_base` tal
  cual). 2024 y 2025 no vuelven a sortear existencias/clientes/tesorería desde el catálogo:
  se derivan del ejercicio anterior + el efecto del arquetipo ese año.
- **Ventas**: si el arquetipo define su propio `rango_crecimiento_pleno` (solo el arquetipo 1,
  por ahora — es el único cuya huella incluye "Ventas" en la sección 2.24), se sortea una vez
  por empresa dentro de ese rango (según intensidad) y se escala por la fracción del año (60%
  en 2024, 100% en 2025), exactamente como antes. Si el arquetipo NO define uno (5, 9, 11, 15:
  ninguno tiene "Ventas" en su huella), la empresa sigue necesitando alguna trayectoria de
  ventas para tener una historia de varios años — se usa un crecimiento orgánico modesto fijo
  (`RANGO_CRECIMIENTO_ORGANICO`), sorteado una vez, SIN escalar por intensidad ni por fracción
  del año (no es el efecto del arquetipo, es solo el telón de fondo sobre el que actúa).
- **Ratios de continuidad (masa_circulante, pyg_primitiva)**: se mueven cada año un
  `intensidad_base x fracción_año` respecto al propio valor del año anterior de la empresa (no
  respecto al valor Huber directamente): se descartó anclar directamente al Huber del sector
  como haría la fórmula general de la sección 2.24 (`Valor_simulado = Huber x
  (1+intensidad*dirección)`) porque, al ser 2023 ya un sorteo con ruido propio, la distancia
  entre el ratio real de 2023 y el Huber del sector puede ser grande por simple variabilidad
  estadística — anclar ahí habría provocado un salto brusco en 2024 dominado por "volver a la
  media del sector" y no por el arquetipo. El valor Huber del sector se conserva como
  referencia de plausibilidad (suelo/techo defensivo), no como objetivo al que saltar.
- **Tesorería y deuda a corto**: el resto de las masas del balance (inmovilizado, patrimonio
  neto vía resultado retenido, deuda a largo, otras partidas de pasivo corriente) crecen en
  línea con las ventas. La diferencia entre ese crecimiento "neutro" de existencias+clientes
  y el crecimiento real (mayor, si el arquetipo las toca) es la "NOF extra" del año: se resta
  primero de la tesorería; si la tesorería no basta, el resto se cubre con deuda a corto nueva.
- **Patrimonio neto**: PN(año) = PN(año-1) + resultado del ejercicio(año) − lo que financie el
  efecto "apalancamiento" ese año (ver más abajo), sin más dividendos (hasta que exista ECPN).
- **Cuadre final**: el ajuste sobre "otras deudas a corto plazo" es el mecanismo habitual de
  cuadre en 2024 y 2025 (no una excepción rara como en `empresa_base.py`): cada masa evoluciona
  con su propia regla y no hay renormalización conjunta, así que el plug absorbe la diferencia
  residual cada año — incluida la pequeña aproximación de segundo orden del efecto
  "apalancamiento" (ver abajo).

- **Control de plausibilidad del endeudamiento.** Cuando el déficit de caja se traslada a
  deudas financieras a corto plazo, se comprueba el endeudamiento resultante (pasivo
  total/activo total) contra `ratios.endeudamiento.huber_9y + 3 x huber_scale_mad` del sector.
  Si lo superaría, NO se deja crecer la deuda sin límite: se amortigua el propio exceso de las
  masas de circulante que el arquetipo haya tocado (en el orden en que aparecen en su
  definición), limitado como máximo a revertir el exceso por encima del crecimiento
  proporcional a ventas — nunca por debajo. El patrimonio neto no se toca como palanca de
  contención: con el activo fijado por el arquetipo, la identidad contable Activo = PN + Pasivo
  implica endeudamiento = 1 − PN/Activo — bajar el PN, con el activo fijo, exige MÁS pasivo, no
  menos (se verificó derivando la identidad a mano antes de implementar). Si el arquetipo no
  toca ninguna masa de circulante (9, 11, 15), no hay nada que amortiguar: el caso queda
  marcado igualmente (`riesgo_endeudamiento=True`, `contencion_al_limite=True`,
  `deterioro_aplicado_eur=0.0`) como señal, sin poder corregirse por esta vía.
  Es un punto fijo (menos deuda -> menos interés -> más PN -> hace falta amortiguar menos), no
  una fórmula cerrada de una sola pasada: se itera acotado (`MAX_ITERACIONES_CONTENCION`).

- **Gastos financieros = deuda financiera media x tipo de interés del sector**, no un % de PyG
  sorteado de forma independiente (ver `motor.empresa_base._generar_pyg_hasta_baii` /
  `_completar_pyg_con_deuda`). La deuda financiera media de un ejercicio es el promedio entre
  el saldo de deudas financieras (largo + corto plazo) al inicio y al final del propio
  ejercicio. Esto crea una dependencia circular con la contención de endeudamiento (la deuda
  financiera final depende de si hay contención, contener depende del PN, el PN depende de los
  gastos financieros, que dependen de la deuda financiera final): se resuelve evaluando primero
  el escenario sin contener (deuda, interés, resultado, PN, balance ya cuadrado) y, solo si
  hace falta contener, reevaluando el escenario completo con las cifras ya amortiguadas — sin
  reabrir la decisión de contención.

- **Arquetipo 9 (apalancamiento) — mecanismo específico, no una forma más del molde genérico
  de "ratio de continuidad".** Sube el endeudamiento objetivo (continuidad desde el propio
  endeudamiento del año anterior, topado al mismo techo de plausibilidad de la sección
  anterior) y resuelve en forma cerrada (sin iterar: ni el activo ni el pasivo "base" dependen
  del interés) cuánta deuda financiera a largo plazo extra (W) hace falta para llegar a ese
  endeudamiento objetivo, dado el activo y el resto del pasivo de ese ejercicio. Esa W se suma
  a deudas_fin_largo, y se resta de patrimonio neto — la deuda nueva financia una distribución,
  no una compra de activo (si no se restara del PN, el plug general de cuadre simplemente
  movería la misma W desde "otras deudas a corto" a "deudas a largo": el endeudamiento total no
  cambiaría nada, solo la composición de la deuda — se detectó exactamente así al derivar la
  identidad contable antes de implementar). La W calculada ignora el pequeño efecto de segundo
  orden de que la deuda nueva también sube el gasto financiero (y por tanto baja algo más el
  PN de lo que la fórmula asume): se deja que el plug de cuadre general absorba ese residuo,
  igual que ya hace con otras aproximaciones de este módulo. La distribución nunca reparte más
  PN del que hay ese ejercicio (`apalancamiento_extra_eur` se topa a `max(0, PN antes de
  distribuir)`), pero esto NO impide que el PN acabe en negativo en ejercicios posteriores por
  pérdidas normales: el interés de la deuda ya acumulada de un año sube el gasto financiero del
  siguiente, y si el resultado operativo de ese año es débil (sector volátil + sorteo de base
  ya débil), el PN puede erosionarse hasta negativo sin que haya una distribución nueva ese
  año. Verificado en pruebas de estrés: ocurre en 4 de 3.000 combinaciones (todas del mismo
  sector pequeño y volátil, Restaurantes). No se trata como valor absurdo — a diferencia de una
  masa físicamente imposible (existencias negativas), un patrimonio neto negativo es un estado
  contable real (empresa descapitalizada) — pero es una limitación a tener presente: este
  modelo mínimo no marca todavía una alerta de insolvencia/continuidad para ese caso.

  **Efecto de segundo año — "espiral de deuda" (detectado en pruebas, no buscado a propósito;
  SÍ se detecta y se señaliza, aunque no siempre se pueda corregir del todo).** El interés de
  la deuda YA acumulada de un año anterior sigue devengando en los siguientes: si ese interés
  es alto (deuda grande) y el resultado operativo del año es flojo, el PN crece poco o
  retrocede, mientras el resto del pasivo (que sí crece con ventas, incluida la propia deuda
  heredada) no se frena — el endeudamiento de un año puede acabar por encima del techo sin que
  se añada ni un euro de deuda nueva ESE año (`apalancamiento_extra_eur=0`). La comprobación de
  plausibilidad de endeudamiento (ver más arriba) se ejecuta SIEMPRE, no solo cuando hay
  déficit de NOF o deuda nueva de apalancamiento ese año concreto — así que este caso sí se
  detecta (`riesgo_endeudamiento=True`). Lo que NO puede es corregirlo por la vía habitual: el
  arquetipo "apalancamiento" no toca ninguna masa de circulante, así que no hay nada que
  amortiguar (`contencion_al_limite=True`, `deterioro_aplicado_eur=0`) — queda marcado como
  caso de riesgo, no arreglado en silencio. Corregirlo de verdad exigiría tocar el patrimonio
  neto como palanca, que ya se ha descartado por la misma razón de siempre (empeoraría el
  propio ratio que se quiere contener). Es una "espiral de deuda" real (el interés de la deuda
  existente erosiona el patrimonio, empeorando el ratio sin decisión nueva alguna) — coherente
  con lo que le pasa a una empresa realmente sobreapalancada, aunque no era el objetivo
  explícito de este arquetipo. Cuantificado en pruebas de estrés (1.296 combinaciones del
  arquetipo, sector x segmento x intensidad x semilla): 130 (10%) terminan 2025 con un
  patrimonio neto por debajo del 15% del activo partiendo de una base sana en 2023 (>=15% en
  2023) — los 130 quedan señalizados por esta vía, 0 pasan desapercibidos.

- **Techo/suelo de plausibilidad sectorial para subtotales de PyG (arquetipo 11 y cualquier
  otro efecto pyg_primitiva futuro).** El suelo/techo que ya tenía la propia primitiva
  (`FRACCION_MINIMA/MAXIMA_VS_HUBER`, frente al Huber de LA MISMA variable, p. ej.
  `pyg.consumos_explotacion_pct`) no acota de forma realista lo que le pasa al SUBTOTAL que esa
  primitiva alimenta (`pyg.margen_bruto_pct`): son columnas del catálogo distintas, con Huber y
  MAD propios — el margen bruto puede rebasar su propio techo sectorial mucho antes de que la
  primitiva llegue al suyo. Medido en pruebas de estrés (mismo método que con el arquetipo 9):
  de 2.592 ejercicios evaluados del arquetipo "mejora_margen" (1.296 combinaciones x 2 años),
  **1.796 (69%) superaban huber_9y + 3·MAD de `margen_bruto` del sector sin ninguna señal** — ya
  en intensidad "leve" (no hacía falta "fuerte" para desbordarlo). Corregido con
  `_limitar_por_subtotal`: además del suelo/techo de la propia primitiva, se calcula qué
  subtotal alimenta (`SUBTOTAL_PYG_DE_PRIMITIVA`, mapeo estructural de la cascada, no dato de
  arquetipo) y se topa el objetivo de la primitiva para que ESE subtotal no rebase su propio
  huber_9y +/- N·MAD. Solo válido hoy para relaciones "subtotal = 100 − primitiva" (la única
  que existe: margen_bruto = ingresos_explotacion(100) − consumos_explotacion) — no hacía falta
  ningún punto fijo ni iteración, a diferencia del endeudamiento: aquí no hay dependencia
  circular con la deuda/interés, así que se resuelve con una sola operación algebraica. El caso
  queda marcado (`riesgo_plausibilidad_pyg=True`, `pyg_subtotales_sin_contener` con el valor
  antes de topar) igual que el resto de contenciones de este módulo. Verificado tras el fix: 0
  de 2.592 ejercicios por encima del techo, y los 1.796 que antes pasaban desapercibidos quedan
  ahora señalizados exactamente.

- **Arquetipo 15 (riesgo de liquidez pese a beneficio) — limitación documentada.** Se decidió
  tras probarlo que SÍ encaja en el mecanismo general si se modela como "la tesorería (variable
  `disponible`) crece por debajo de lo proporcional a ventas, un intensidad_efectiva" —
  reutiliza el pipeline de déficit/deuda ya existente sin cambios (la tesorería más baja de lo
  normal simplemente hace más probable que aparezca déficit, financiado con deuda a corto,
  exactamente el mecanismo que ya había). El resultado del ejercicio no se toca en absoluto
  (sigue la cascada de PyG normal), lo que produce justo la divergencia "beneficio sano, caja
  tensa" de la huella del arquetipo. La limitación real: `ratios.tesoreria` del catálogo es
  (realizable+disponible)/pasivo_corriente (se comprobó numéricamente contra las masas del
  balance), no disponible/ventas — que es la unidad que usa esta implementación, por
  consistencia con existencias/realizable y para no tener que mover realizable también (lo que
  reabriría el problema de "dos variables a la vez"). Por eso este efecto NO usa el Huber de
  `ratios.tesoreria` como suelo/techo de plausibilidad (las unidades no son comparables): solo
  el suelo genérico de "disponible no puede ser negativo" que ya tenía el pipeline general.

- **Segundo lote (arquetipos 3, 4, 6, 8, 10) — generalización de masa_circulante a variables de
  pasivo, con signo NOF.** 3 y 6 reutilizan tal cual el mecanismo `masa_circulante` (6 es un
  subconjunto de 1: solo `realizable`; 3 es idéntico a la huella de circulante de 1). 4
  ("deterioro del ciclo de caja") es el primero en tocar a la vez una masa de ACTIVO
  (`realizable`, sube la NOF) y una de PASIVO (`acreedores_comerciales`, sube => BAJA la NOF: más
  financiación de proveedores, menos caja necesaria) — confirmado que el mecanismo genérico SÍ
  soporta direcciones opuestas dentro de un mismo arquetipo, con dos cambios: (a) el déficit de
  caja del año (`_deficit_y_deuda_corto`) se calcula como un único `max(0, suma con signo de los
  excesos de cada masa frente a su crecimiento proporcional)` (`SIGNO_NOF_MASA_CIRCULANTE`), no
  como una suma de `max(0, exceso)` por variable — así una masa de pasivo puede compensar a una
  de activo dentro del mismo año; (b) la contención de endeudamiento, cuando amortigua el exceso
  de las masas tocadas, solo usa las de signo ACTIVO como palanca (`excesos_eur` filtra por
  `SIGNO_NOF_MASA_CIRCULANTE == 1`): se derivó a mano que dampear una masa de PASIVO no reduce el
  pasivo total (lo que se gana en `acreedores_comerciales` se pierde en exactamente la misma
  cantidad de `deudas_fin_corto` nueva, ambas dentro de `pasivo_corriente` — efecto neto cero
  sobre el endeudamiento), así que incluirla como palanca sería una amortiguación sin efecto
  real. Verificado en pruebas de estrés (27 sectores x 3 intensidades x 4 semillas = 324
  combinaciones, 648 ejercicios): 0 casos sin señalizar por encima del techo de endeudamiento
  para el arquetipo 4, igual que para 3 y 6 (ambos con una sola masa de activo, sin nada nuevo
  que probar).

- **Arquetipo 8 (refinanciación) — mecanismo nuevo `reclasificacion_deuda`, no una forma más de
  "ratio de continuidad" reutilizada tal cual.** Reasigna `deudas_fin_largo`/`deudas_fin_corto`
  para mover `ratios.calidad_deuda` (deudas_fin_largo / deuda financiera total) hacia el objetivo
  de continuidad, manteniendo la deuda financiera TOTAL exactamente igual a su crecimiento
  proporcional a ventas (una renegociación cambia el vencimiento, no el importe) — se aplica
  ANTES de que `deudas_fin_largo/corto_proporcional_eur` se usen en el resto de la función, así
  que el resto del mecanismo (déficit de NOF, apalancamiento, cuadre, enlace deuda-interés) no
  necesita saber que este efecto existe. Por construcción no puede disparar
  `riesgo_endeudamiento` por sí mismo (el endeudamiento total no se mueve): verificado en pruebas
  de estrés (648 ejercicios) que la deuda financiera total nunca se desvía de lo proporcional
  (0 casos) y que las pocas activaciones de `riesgo_endeudamiento` que sí aparecen (15/648, ruido
  de fondo del crecimiento orgánico normal, el mismo tipo de comprobación que corre siempre para
  cualquier arquetipo) quedan siempre señalizadas y con `contencion_al_limite=True` — el
  arquetipo no toca circulante, así que no tiene nada que amortiguar por esa vía, igual que 9/11/
  15.

- **Arquetipo 10 (mejora de EBITDA) — techo de plausibilidad de "base dinámica" para baii, con
  amortiguación de intensidad antes de invertir el sentido.** A diferencia de `margen_bruto`
  (base = ingresos_explotacion = 100 fijo), `baii = valor_añadido − gastos_personal −
  amortizaciones + resultado_extraordinario` depende de partidas que se sortean de nuevo CADA
  AÑO, con su propio ruido, independiente del arquetipo. Se corrige en dos tiempos
  (`_limitar_gastos_personal_por_baii`): se sortea la PyG con el objetivo de continuidad sin
  contener de `gastos_personal`, y SOLO si el `baii_pct` resultante rebasa `pyg.baii_pct.huber_9y
  +/- N·MAD` del sector, se recalcula `gastos_personal` de forma analítica (coeficiente −1 en la
  fórmula de baii) para que `baii_pct` quede exactamente en el techo/suelo — sin volver a tocar
  el generador aleatorio. Verificado en pruebas de estrés (648 ejercicios): sin este mecanismo,
  316 (48,8%) habrían superado el techo sin ninguna señal; con él, 0.
  **Amortiguación de intensidad antes de invertir el sentido (igual que la contención de
  masa_circulante en 1/3/4/6 nunca amortigua por debajo del crecimiento proporcional a
  ventas).** Como la base de baii cambia cada año por causas ajenas al arquetipo, el objetivo de
  continuidad puede pedir una bajada de `gastos_personal` que, dada la base de ESE año, deje
  baii muy por encima del techo. Al resolver "baii = techo" de forma directa (baii es lineal en
  `gastos_personal`, la solución es única), la corrección aterriza automáticamente entre el
  objetivo sin contener y `gastos_personal_pct` sin ningún empuje del arquetipo (el valor del
  año anterior) — una amortiguación pura de la intensidad, sin invertir el sentido — SALVO que
  incluso con la intensidad amortiguada a cero (`gastos_personal_pct` del año anterior tal cual)
  ya se rebasara el techo: entonces el desbordamiento viene del ruido propio de la base ese año
  (valor_añadido, amortizaciones, resultado_extraordinario), no del arquetipo, y no hay forma de
  evitar invertir el sentido — se señaliza aparte (`pyg_contencion_al_limite=True`), igual que
  la limitación documentada y aceptada del arquetipo 15. Cuantificado en pruebas de estrés (648
  transiciones año a año, 316 activaciones de `riesgo_plausibilidad_pyg`): 173 (54,7% de las
  activaciones) se resuelven amortiguando la intensidad sin invertir el sentido; 143 (45,3%) sí
  lo invierten (magnitud 0,07 a 18,3 puntos porcentuales, media 2,7) — y las 143 coinciden
  EXACTAMENTE con `pyg_contencion_al_limite=True`, sin ni una discrepancia en las 648
  evaluaciones (ver test
  `test_mejora_ebitda_las_subidas_de_gastos_personal_siempre_coinciden_con_el_limite_por_ruido`).
  Se deja documentado como límite aceptado, sin intervenir más allá: no hay forma de mantener
  gastos_personal_pct por debajo del valor del año anterior Y respetar el techo sectorial de
  baii a la vez cuando el propio ruido de la base ya lo rebasa sin ayuda del arquetipo —
  `pyg_contencion_al_limite` señaliza con precisión quién queda en ese caso.

- **Tercer lote (arquetipos 2, 12, 14, 16, 17).**

  **Arquetipo 2 (beneficio sin cash flow suficiente)** reutiliza EXACTAMENTE el mecanismo del
  arquetipo 15 (`EfectoTesoreria`): comprobado en el código que este efecto NO consume el Huber
  de `ratio_catalogo` para nada (`_disponible_proporcional_con_efecto` es un simple factor
  `(1 ± intensidad)` sobre la tesorería proporcional, sin referencia al catálogo) — así que
  declarar un `ratio_catalogo` distinto (`ratios.flujo_caja_activo`, el más directo de los dos
  anclas de la sección 2.24 para este arquetipo; `roe` queda implícito porque la PyG no se toca)
  es puramente una etiqueta de trazabilidad, no cambia el comportamiento. Mismo mecanismo, sin
  código nuevo — verificado en pruebas de estrés (972 ejercicios): 0 descuadres, disponible
  nunca negativo, igual que el 15.

  **Arquetipo 12 (resultado extraordinario) — mecanismo nuevo, `EfectoEventoPuntual`, porque su
  naturaleza (suceso puntual y no recurrente, por definición) es incompatible con el patrón de
  intensidad progresiva (leve en 2024 → fuerte en 2025) de todos los demás efectos.** Decisiones:
  (a) el año del suceso se sortea 50/50 entre 2024 y 2025 con `rng_tendencia` (ya independiente
  por sector+segmento, NO por intensidad — el año en que ocurrió el suceso es un hecho de la
  empresa, no debe variar solo por pedir una intensidad distinta del mismo caso); (b) la
  magnitud NO se ancla al Huber de la propia primitiva (`pyg.resultado_extraordinario_pct` es
  ~0 con MAD pequeño en casi todos los sectores del catálogo — un techo/suelo ahí daría un
  "extraordinario" imperceptible, lo contrario de lo que pide el arquetipo): se ancla en su
  lugar al Huber de `pyg.baii_pct` (siempre positivo en los 27 sectores, representa la escala
  de "beneficio operativo típico" del sector) — decisión estructural del mecanismo
  (`_evento_puntual_valor`), no un dato de arquetipo; (c) deliberadamente SIN techo/suelo de
  plausibilidad sectorial sobre baii/resultado ese año — la propia esencia del arquetipo es que
  ESE año se salga de lo plausible, limitarlo anularía el efecto. El año SIN suceso vuelve solo
  al ruido normal de sector (huber~0): no hace falta código adicional, basta con no forzar la
  primitiva ese año. Verificado en pruebas de estrés (972 ejercicios, 324 casos): 0 descuadres;
  distribución del año 138/186 (42,6%/57,4% — comprobado que no es sesgo tipo nota_memoria: solo
  hay 108 sorteos realmente independientes, uno por sector×semilla, ya que no depende de la
  intensidad; 138/186 replicado x3 por intensidad da 46/62 sobre 108, a 1,5 desviaciones típicas
  de 54/54, dentro de la variabilidad normal de muestra); magnitud de
  |resultado_extraordinario_pct| entre 0,03 y 9,45 puntos (media 2,59); riesgo_endeudamiento se
  activó solo 3 veces de 972, las 3 correctamente señalizadas por el chequeo incondicional ya
  existente (sin necesidad de ningún mecanismo de contención propio para este arquetipo).

  **Arquetipo 13 (diferencias EBITDA/EBIT/beneficio/caja) — NO IMPLEMENTADO, no aplica al
  motor.** Confirmado por inspección: su huella (BAII, BAII+amortizaciones ≈ EBITDA, BAI,
  resultado del ejercicio, caja) son magnitudes que CUALQUIER empresa generada ya tiene en
  `pyg_eur` sin necesidad de ningún efecto — es una comparación de síntesis para el análisis
  posterior, no una desviación que generar. Pertenece a la futura capa de análisis/diagnóstico,
  no a este motor de generación (backlog de esa fase).

  **Arquetipo 14 (ROE elevado por apalancamiento) — declarado como variante exacta del
  arquetipo 9 (`EfectoApalancamiento`, mismo `ratio_catalogo` y `direccion`), sin lógica nueva.**
  Confirmado que la reducción de PN que ya hace el mecanismo de apalancamiento sube el ROE de
  forma mecánica (ROE = resultado/PN, denominador menor). Verificado en pruebas de estrés (972
  ejercicios, 324 casos): 0 descuadres; deuda y endeudamiento IDÉNTICOS a los del arquetipo 9
  para el mismo caso (mismo efecto, mismos parámetros). **Matiz honesto sobre el "+ROE" de la
  huella, investigado a fondo antes de aceptarlo:** el ROE HEADLINE (no descompuesto) solo sale
  más alto en 2025 que en el 2023 base en el 53,3% de los 324 casos — apenas por encima del azar.

  Se probó primero la hipótesis de que el ruido operativo (ajeno al arquetipo) enmascaraba el
  efecto de apalancamiento: se implementó un factor de amortiguación del MAD de las primitivas
  de PyG NO forzadas (`tipo_interes` excluido, por ser parte de la propia huella) y se midió en
  varios niveles (1,0 / 0,5 / 0,3 / 0,15 / 0,0). **La hipótesis quedó descartada**: incluso
  eliminando el ruido operativo por completo (factor 0,0 — todas las primitivas no forzadas
  exactamente en su Huber sectorial, sin varianza) el porcentaje NO mejoró (49,7%, dentro del
  mismo rango). El cambio se revirtió — no queda ningún `factor_ruido_operativo` en el motor.

  **La causa real: el efecto se diluye en el segundo año por el propio coste de la deuda
  acumulada — la misma dinámica de "espiral de deuda" ya documentada más arriba para el
  arquetipo 9, aplicada aquí al ROE.** Medido por transición: ROE 2024 vs. 2023 (año en que se
  añade la deuda; el interés nuevo solo pesa "media dosis" ese ejercicio, por la media
  inicio/fin) sube en el **61,7%** de los 324 casos; ROE 2025 vs. 2024 (el interés ya pesa el año
  completo sobre la deuda ya acumulada, y la contención de endeudamiento limita cuánta deuda
  nueva cabe ese año) sube solo en el **35,0%** — baja la mayoría de las veces. ROE por encima de
  la base 2023 en **al menos uno** de los dos años (2024 o 2025) — el criterio que de verdad
  importa para un caso leído como un arco de 3 ejercicios, no solo comparado en el punto final —:
  **78,1%**, consistente entre las tres intensidades (76,9% leve, 78,7% moderado, 78,7% fuerte).

  **Decisión (discutida y acordada): no se toca el motor.** Forzar la monotonía del ROE habría
  exigido tocar la rentabilidad operativa, ajena a la huella declarada del arquetipo (deuda, ROE,
  ROI) — confundiría dos arquetipos distintos, y ya se comprobó que ni siquiera con ruido cero se
  resuelve, porque la causa no es el ruido. El 78,1% de casos con el efecto visible en al menos un
  año ya es claramente mayoritario y consistente por intensidad: la ficha docente de este
  arquetipo es la que debe matizarse (pendiente, fuera del motor) para dejar explícito que el ROE
  elevado se observa típicamente en el ejercicio en que se contrae la deuda nueva, y que puede
  diluirse el año siguiente por el coste financiero acumulado sobre la deuda ya existente —
  coherente con la "espiral de deuda" del arquetipo 9, no un defecto de haber reutilizado su
  mecanismo tal cual.

  **Arquetipo 16 (riesgo de refinanciación) — mismo mecanismo `reclasificacion_deuda` del
  arquetipo 8, con `direccion=-1` (en vez de +1: concentra a corto en vez de reequilibrar a
  largo), más `nota_memoria` (redactada directamente para este arquetipo, sin partir de texto
  dado — ver `NOTAS_MEMORIA_RIESGO_REFINANCIACION`).** A diferencia del caso límite raro del
  arquetipo 10, la nota se activa cada año en que el efecto actúa (es la huella habitual del
  propio arquetipo, no una excepción) — reutiliza `rngs_nota` (ya independiente por
  sector+segmento+intensidad+año, sin necesidad de una secuencia dedicada nueva: los arquetipos
  10 y 16 nunca coinciden en el mismo caso, sin riesgo de colisión). Verificado en pruebas de
  estrés (648 transiciones, 324 casos): 0 descuadres, deuda financiera TOTAL nunca desviada de
  lo proporcional (confirma que el mecanismo es "seguro" por construcción, igual que el 8),
  `nota_memoria` presente en el 100% de los casos, las 5 redacciones aparecen todas, reproducible
  por semilla.

  **Arquetipo 17 (capex elevado) — mecanismo nuevo, `EfectoCapex`, estructuralmente el
  equivalente en el lado del activo de `masa_circulante`, pero NO reutiliza ese tipo de efecto.**
  Objetivo de `activo_no_corriente` vía el mismo patrón de continuidad "rotación" que
  `_masa_circulante_objetivo` (ancla `ratios.rotacion_activo_no_corriente`, no circular: se
  calcula solo a partir de ventas, sin depender de ningún total de balance aún sin construir) —
  pero NO se declara como una variable más de `masa_circulante` porque esa vía alimenta el
  mecanismo de déficit de NOF/circulante (financiaría el exceso con tesorería y DEUDA A CORTO,
  la fuente típica de financiación de circulante) y capex no es circulante: la fuente típica de
  financiación de una inversión en inmovilizado es DEUDA A LARGO plazo (decisión razonada, no
  dato de la sección 2.24, que no especifica la fuente). El exceso de activo_no_corriente sobre
  su crecimiento proporcional a ventas se añade directamente a `deudas_fin_largo_proporcional_eur`
  — a diferencia de "apalancamiento", esta deuda nueva NO resta nada de patrimonio_neto (financia
  la compra del propio activo, no una distribución: activo y pasivo suben lo mismo, sin romper
  el cuadre ni necesitar ningún cálculo en forma cerrada). Verificado en pruebas de estrés (972
  ejercicios, 324 casos): 0 descuadres, 0 valores negativos indebidos, exceso de
  activo_no_corriente financiado exactamente por el exceso de deudas_fin_largo (dentro de
  tolerancia). El chequeo incondicional de endeudamiento se activó en 152/972 ejercicios (15,6%)
  — todas correctamente señalizadas (0 sin señalizar) — y el 100% de esas activaciones quedan en
  `contencion_al_limite=True`: el arquetipo no toca circulante, así que no tiene ninguna palanca
  de amortiguación disponible, exactamente el mismo patrón ya aceptado para 9/11/15/16 (señal
  honesta sin corrección posible, no un intento fallido de arreglarlo en silencio) — no se ha
  añadido ninguna palanca de autofinanciación parcial (capex financiado en parte con caja propia)
  porque no estaba pedida y añadiría una capa de ingeniería no solicitada; queda como posible
  mejora futura si el caso de uso lo requiere.

- **Arquetipo 18 (Adquisición) — el más distinto de todos los implementados: un salto
  DISCRETO y EXÓGENO en un único ejercicio, no una desviación de continuidad.** Mecanismo nuevo
  (`EfectoAdquisicion`), con varias decisiones deliberadamente distintas del resto:

  **Año fijo, no sorteado (`AÑO_ADQUISICION = 2024`), a diferencia del arquetipo 12.** El
  arquetipo 12 (resultado extraordinario) sortea el año 50/50 porque no importa cuál de los dos
  elija: el suceso solo necesita desaparecer al año siguiente. El 18 SÍ tiene un requisito
  temporal explícito de la guía docente (ficha 18): el alumnado debe poder leer 2025 como un
  ejercicio completo con la unidad YA integrada. Eso solo es posible si la operación ocurre en el
  PRIMER año del arquetipo — sorteada, la mitad de los casos caerían en 2025 y nunca se vería un
  año post-integración dentro de la ventana de 3 ejercicios. Por eso es una constante fija, no un
  sorteo: no hace falta ningún RNG dedicado para el año (a diferencia del 12).

  **Magnitud del salto de activo_no_corriente**: `intensidad_base × activo total de 2023`
  (antes de la operación) — sin escalar por fracción del año (`intensidad_base`, no
  `intensidad_efectiva`: es un suceso puntual, mismo criterio que el arquetipo 12). Interpretar
  directamente `INTENSIDAD_BASE` (0,15/0,30/0,50) como fracción del activo total previo es fiel
  a la escala real de una operación de M&A "significativa" (15-50% del balance no es descabellado
  para una adquisición relevante) y evita anclar a un ratio del catálogo cuyo Huber no representa
  nada parecido a "tamaño típico de una compra" — no existe tal ratio en la sección 2.23.
  `ratio_catalogo` (`balance.activo_no_corriente`) queda solo como trazabilidad, igual que en
  `tesoreria` y `evento_puntual` — no se usa su Huber en la fórmula. El modelo no desglosa un
  fondo de comercio como partida de balance separada (no existe esa categoría en `MASAS_BALANCE`
  ni en el resto del motor): el fondo de comercio, si procede, queda implícito dentro del propio
  incremento de `activo_no_corriente` — añadir una partida nueva solo para esto habría exigido
  tocar `empresa_base.py` y cada consumidor del balance, ingeniería desproporcionada para lo que
  pide la sección 2.24 (que no exige desglosarlo como cifra, solo mencionarlo "si procede" en la
  memoria — ver más abajo).

  **Financiación: caja primero, deuda a largo el resto** — mismo orden de prioridad que
  `_deficit_y_deuda_corto` para el déficit de NOF, pero la deuda nueva va a LARGO plazo (una
  compra de inmovilizado, no un déficit de circulante), igual que la decisión ya tomada para el
  arquetipo 17 ("capex"). Sin restar nada de patrimonio_neto (a diferencia de "apalancamiento"):
  financia la compra del propio activo, no una distribución — el cuadre no necesita ningún
  cálculo en forma cerrada, activo y pasivo/caja se mueven exactamente lo mismo. La contención de
  endeudamiento (chequeo incondicional ya existente) se aplica sin cambios: verificado en pruebas
  de estrés (972 ejercicios, 324 casos) que se activa en 70 casos (7,2%), el 100% correctamente
  señalizado, y el 100% de esas activaciones queda en `contencion_al_limite=True` (sin palanca de
  circulante que amortiguar) — mismo patrón ya aceptado para 9/11/15/16/17, no una corrección
  fallida.

  **Ventas — orgánicas vs. inorgánicas, expuestas por separado (`EjercicioEmpresa.
  ventas_organicas_eur`/`ventas_inorganicas_eur`, `None` salvo en AÑO_ADQUISICION).** La guía
  docente (ficha 18) pide explícitamente poder separar "cuánto ha crecido el negocio que ya
  existía" de "cuánto aporta la pieza adquirida" — así que no basta con una cifra combinada.
  `ventas_organicas_eur` es exactamente lo que habrían sido las ventas SIN el arquetipo (mismo
  `crecimiento_ventas` de fondo que ya usa cualquier otro arquetipo sin huella de ventas propia).
  `ventas_inorganicas_eur` se ancla a `ratios.rotacion_activo` del sector (ventas/activo total
  típico) aplicado sobre el propio importe adquirido — asume que la unidad comprada opera con una
  eficiencia de activo similar a la del sector, en vez de un número de ventas arbitrario y
  desconectado del tamaño de la operación. El resto del circulante (existencias, realizable,
  acreedores_comerciales) crece proporcional a las ventas YA COMBINADAS (orgánicas + inorgánicas),
  sin distinguir de dónde viene cada venta — decisión deliberada: la huella de la sección 2.24
  para este arquetipo no pide separar el circulante de la unidad adquirida, y una empresa
  combinada más grande necesita más circulante en conjunto, venga la venta de donde venga.
  2025 no repite la inyección: crece de forma puramente proporcional desde la base YA ampliada de
  2024 (sin código adicional, automático — mismo mecanismo que cualquier año sin efecto activo).

  **Memoria OBLIGATORIA, no opcional** (a diferencia de `nota_memoria` en el resto de usos:
  10 la activa solo en un caso límite raro, 16 cada año que su efecto actúa) — aquí se genera
  SIEMPRE que el arquetipo esté activo, en AÑO_ADQUISICION, porque el arquetipo consiste
  precisamente en una operación que la memoria debe explicar: no es una señal de plausibilidad,
  es parte de la propia huella (sección 2.24: "Memoria obligatoria"). Reutiliza `rngs_nota` (ya
  independiente por sector+segmento+intensidad+año) con un pool propio de 5 redacciones
  (`NOTAS_MEMORIA_ADQUISICION`, escritas para este arquetipo) — verificado en pruebas de estrés:
  presente en el 100% de los 324 casos, nunca fuera de AÑO_ADQUISICION, las 5 redacciones
  aparecen todas, reproducible por semilla.

  **Plausibilidad general**: 0 descuadres en 972 ejercicios evaluados; el incremento de
  activo_no_corriente coincide exactamente (rel=1e-6) con `intensidad_base × activo total 2023`
  en los 324 casos, confirmando que la magnitud no se ve alterada por ningún otro mecanismo. En 3
  de los 324 casos (sector con `disponible` alto y `otras_deudas_corto` bajo de partida) el
  drenaje de caja de la operación hizo que el plug general de cuadre (ya existente, "red de
  seguridad barata" para cuando `otras_deudas_corto` pediría quedar negativo) redirigiera un
  remanente hacia `disponible` — comportamiento del mecanismo de cuadre PRE-EXISTENTE, no algo
  nuevo de este arquetipo; el balance sigue cuadrando exacto en los 3 casos, no es un error, solo
  una interacción más visible aquí por la magnitud del salto.

- **Trazabilidad (sección 2.15).** `EvolucionArquetipo` guarda `arquetipo`, `intensidad`,
  `semilla`, `catalogo_version` (hash del CSV del catálogo usado — se deriva del propio
  archivo, no de un número mantenido a mano) y `pgc_version` (fijo por ahora: solo hay una
  versión normativa en juego). Falta la versión normativa "de verdad" variable y el ID del
  caso/variante — se añadirán cuando exista un repositorio de casos.

- **Auditoría de sesgo en la semilla del RNG (a raíz del hallazgo en `nota_memoria`).** El
  mismo patrón de bug (un generador aleatorio que llega a un punto de sorteo en el MISMO estado
  para combinaciones que deberían ser independientes) se encontró también en los DOS puntos
  donde este módulo siembra un `np.random.Generator`/`SeedSequence` a partir de `semilla` —
  `semilla_secuencia` (de la que salen `rng_tendencia` y `rngs_pyg`, aquí) y `rng` dentro de
  `motor.empresa_base.generar_empresa_base` (usado para el año base 2023 de cualquier caso).
  Ambos se sembraban SOLO con `semilla`, sin mezclar sector/segmento: como el modo típico/
  atípico y el valor z de cada partida no dependen de huber/mad (solo su escalado posterior sí),
  cualquier sector/segmento con la misma semilla consumía la secuencia de sorteos IDÉNTICA —
  verificado numéricamente (z de `rotacion_activo` y de `gastos_personal_pct` en 2024
  coincidiendo hasta 1e-9 entre sectores distintos con la misma semilla; `crecimiento_pleno_
  objetivo` bit a bit idéntico entre los 27 sectores del catálogo para cualquier semilla, en
  arquetipos sin `rango_crecimiento_pleno` propio). Corregido mezclando un hash estable
  (`zlib.crc32`, no `hash()` de Python — varía entre procesos por PYTHONHASHSEED) de
  sector+segmento en ambas semillas. Verificado tras el fix, en el barrido de los 27 sectores x
  4 semillas: 0 valores duplicados entre sectores (antes, 27/27 idénticos por semilla en ambos
  puntos). La intensidad NO se mezcla en ninguna de las dos: por diseño, la misma
  semilla+sector+segmento con intensidades distintas debe seguir compartiendo el mismo "ruido de
  fondo" de la empresa (verificado que se preserva tras el fix), y solo el empuje propio del
  arquetipo debe variar con la intensidad. La corrección forzó a re-pinnear los valores exactos
  de `test_reimplementacion_generica_reproduce_los_valores_de_referencia` (el mecanismo del
  arquetipo 1 no cambió, solo el ruido de fondo que recibe).
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from motor.arquetipos import (
    DefinicionArquetipo,
    EfectoAdquisicion,
    EfectoApalancamiento,
    EfectoCapex,
    EfectoEventoPuntual,
    EfectoMasaCirculante,
    EfectoPygPrimitiva,
    EfectoReclasificacionDeuda,
    EfectoTesoreria,
    cargar_arquetipos,
)
from motor.amortizacion import (
    amortizacion_eur_del_año,
    excluir_bajas,
    generar_cohortes_adquisicion,
    generar_cohortes_capex,
    resultado_bajas_eur,
    sortear_bajas_del_año,
    valor_en_libros_bajas_eur,
    valor_venta_bajas_eur,
)
from motor.coberturas_subvenciones import (
    TIPO_IMPOSITIVO_GENERAL,
    activo_por_impuesto_diferido_eur,
    ajuste_gastos_financieros_cobertura_eur,
    capex_subvencionable_baseline_eur,
    evolucionar_cobertura,
    evolucionar_subvencion,
    generar_activo_subvencionado,
    pasivo_por_impuesto_diferido_eur,
    presentacion_neta_eur,
    sortear_parametros_cobertura,
    sortear_pct_cofinanciacion,
    sortear_subvencion_baseline,
)
from motor.catalogo import cargar_y_validar_catalogo
from motor.clasificacion_legal import estimar_plantilla, estimar_ventas_por_empleado
from motor.empresa_base import (
    TOLERANCIA_CUADRE_EUR,
    EmpresaBase,
    EmpresaBaseError,
    calcular_desglose_deudas_fin,
    calcular_desglose_gastos_personal,
    calcular_desglose_ingresos_financieros,
    calcular_desglose_otros_gastos_explot,
    calcular_desglose_otras_deudas,
    categoria_de_sector,
    generar_empresa_base,
    resolver_fila_sector,
    sortear_aapp_pendiente_corto_pct,
    tier_existencias_de_sector,
)
from motor.provisiones import (
    ParametrosProvision,
    evolucionar_provision,
    sortear_importe_provision_eur,
    sortear_provision_baseline,
)
from motor.insolvencias import (
    ParametrosInsolvencia,
    evolucionar_insolvencia,
    sortear_importe_insolvencia_eur,
    sortear_insolvencia_baseline,
)
from motor.empresa_base import _completar_pyg_con_deuda, _generar_pyg_hasta_baii  # reutiliza la cascada de PyG
from motor.ruido import _generar_partida, activar_modo_generacion, desactivar_modo_generacion

AÑOS = (2023, 2024, 2025)
AÑO_BASE = 2023

# Año FIJO (no sorteado, a diferencia de EfectoEventoPuntual) del suceso del arquetipo 18
# ("Adquisición"): siempre 2024, nunca 2025. Decisión deliberada, distinta del criterio del
# arquetipo 12 — ver docstring del módulo, sección "Arquetipo 18", para el porqué (la guía
# docente exige que 2025 se pueda leer como un año completo con la unidad ya integrada, lo que
# solo es posible si la operación ocurre en el primer año del arquetipo, no en el segundo).
AÑO_ADQUISICION = 2024

# Trazabilidad (sección 2.15): única versión normativa en juego por ahora.
PGC_VERSION = "PGC RD 1514/2007"

INTENSIDADES_VALIDAS = frozenset({"leve", "moderado", "fuerte"})
INTENSIDAD_BASE = {"leve": 0.15, "moderado": 0.30, "fuerte": 0.50}

# Escalas de intensidad específicas para los 3 arquetipos cuyo chequeo de plausibilidad actúa
# sobre un umbral MUCHO más estrecho que el resto (ver decisiones_plausibilidad.md #19): 9/14
# (apalancamiento) topan el objetivo directamente contra el mismo techo de endeudamiento que
# dispara `riesgo_endeudamiento`; 11 y 10 (pyg_primitiva) mueven una primitiva grande cuyo
# subtotal derivado (margen_bruto, baii) tiene una banda de plausibilidad estrecha en puntos
# porcentuales — la escala genérica (arriba) hacía saturar su señal ya en "leve" (~30-42%, frente
# al ~1-7% de los arquetipos bien calibrados). Calibradas empíricamente con el mismo método de
# siempre (barrido 27 sectores x 4 semillas), aprobadas por el usuario tras revisión. 10 tiene un
# suelo estructural propio (~6,9%, ruido de la base sin ningún arquetipo — ver decisiones_
# plausibilidad.md #18) que ninguna escala puede bajar más.
INTENSIDAD_BASE_APALANCAMIENTO = {"leve": 0.02, "moderado": 0.08, "fuerte": 0.25}
INTENSIDAD_BASE_MEJORA_MARGEN = {"leve": 0.02, "moderado": 0.07, "fuerte": 0.22}
INTENSIDAD_BASE_MEJORA_EBITDA = {"leve": 0.015, "moderado": 0.06, "fuerte": 0.22}

# 8/16 (reclasificacion_deuda) — intento de recalibración (#76) PENDIENTE, no aplicado todavía:
# al corregir el ancla a la definición ACCID de `ratios.calidad_deuda` (Pasivo corriente/Deudas
# totales — ver #71/#74), CUALQUIER intensidad saturaba el reparto largo/corto al límite
# estructural, incluida "leve" cerca de cero — se descubrió que `ratios.calidad_deuda` ya tiene un
# suelo de ruido de base (~24-25%) idéntico al hallazgo mayor de #73/#75 (acumulación de ruido
# entre años, independiente de cualquier arquetipo): no se puede calibrar esta escala de forma
# aislada hasta que se decida el abordaje de #75. Ver decisiones_plausibilidad.md #76.

# 14 (roe_elevado_apalancamiento) es una variante exacta de 9 (mismo EfectoApalancamiento, mismo
# ratio_catalogo y dirección — ver docstring del módulo) y comparte su escala automáticamente.
INTENSIDAD_BASE_POR_ARQUETIPO: dict[str, dict[str, float]] = {
    "apalancamiento": INTENSIDAD_BASE_APALANCAMIENTO,
    "roe_elevado_apalancamiento": INTENSIDAD_BASE_APALANCAMIENTO,
    "mejora_margen": INTENSIDAD_BASE_MEJORA_MARGEN,
    "mejora_ebitda": INTENSIDAD_BASE_MEJORA_EBITDA,
}

FRACCION_AÑO = {2024: 0.6, 2025: 1.0}

# Crecimiento de ventas para arquetipos que no definen su propio rango_crecimiento_pleno (ver
# docstring del módulo). Fijo, no escalado por intensidad ni por fracción del año.
RANGO_CRECIMIENTO_ORGANICO = (0.01, 0.04)

# Payout de dividendos (decisiones_plausibilidad.md #79-#80) — cota matemática, no un número
# elegido a ojo: con g>0 y ROE_caso>0, payout_necesario=1-g/ROE_caso nunca la alcanza (ver
# docstring de `generar_evolucion_combinada`, sección del sorteo de payout_caso).
TECHO_PAYOUT_DIVIDENDOS = 1.0

DIAS_AÑO = 365.0

# Suelo/techo defensivo frente al valor Huber del sector para cualquier ratio de continuidad
# (masa_circulante, pyg_primitiva). Evita valores absurdos en casos extremos; en escenarios
# moderado/fuerte normales no debería llegar a activarse casi nunca.
FRACCION_MINIMA_VS_HUBER = 0.10
FRACCION_MAXIMA_VS_HUBER = 3.0

# Techo de plausibilidad del endeudamiento: huber_9y + N desviaciones (huber_scale_mad) del
# sector, recortado a este tope absoluto. Además de evitar que la fórmula de contención (que
# divide por 1-techo_endeudamiento) degenere si un sector tuviera huber+N*mad >= 1, es un
# límite de capitalización mínima razonable: 0.85 de endeudamiento equivale a un patrimonio
# neto de solo el 15% del activo. Se bajó de 0,95 (un valor puesto solo por la razón numérica
# de arriba, sin calibrar como límite económico) tras comprobar en pruebas de estrés que 26 de
# 1.296 combinaciones del arquetipo "apalancamiento" quedaban con PN/Activo por debajo del 15%
# en 2025 sin que el mecanismo de contención llegara a activarse — precisamente porque, para
# los sectores cuyo huber+3mad ya supera 0,95, el endeudamiento real (0,85-0,95) quedaba
# "dentro" de ese techo tan laxo.
N_DESVIACIONES_TECHO_ENDEUDAMIENTO = 3.0
TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO = 0.85

# La contención de endeudamiento es un punto fijo (menos deuda -> menos interés -> más PN ->
# hace falta amortiguar menos), no una fórmula cerrada de una sola pasada: se itera acotado.
MAX_ITERACIONES_CONTENCION = 50
TOLERANCIA_CONVERGENCIA_DETERIORO_EUR = 1.0

# Techo/suelo de plausibilidad sectorial para subtotales de la PyG que un efecto pyg_primitiva
# pueda empujar de forma acumulativa (mismo método que el techo de endeudamiento: huber_9y +/-
# N desviaciones del catálogo). Se añadió tras comprobar en pruebas de estrés que, sin él, el
# suelo/techo de FRACCION_MINIMA/MAXIMA_VS_HUBER sobre la propia primitiva (consumos_explotacion)
# no acota de forma realista el subtotal derivado (margen_bruto): 1.796 de 2.592 ejercicios
# evaluados del arquetipo "mejora_margen" (69%) superaban huber+3*MAD de margen_bruto del
# sector sin ninguna señal — ya en intensidad "leve".
N_DESVIACIONES_TECHO_PYG = 3.0

# Mapeo ESTRUCTURAL (no específico de ningún arquetipo, no es dato de data/arquetipos.json): a
# qué subtotal de la cascada de PyG (motor.empresa_base._completar_pyg_con_deuda) alimenta de
# forma directa cada primitiva, para poder acotar ESE subtotal a su propio techo/suelo
# sectorial — no solo el de la propia primitiva. Vive en el motor, no en los datos, porque es
# una propiedad fija de la fórmula de la cascada (margen_bruto = ingresos_explotacion -
# consumos_explotacion), no una elección del arquetipo. Solo válido para relaciones "subtotal =
# 100 - primitiva" (base fija) — para primitivas cuyo subtotal depende de otras partidas que se
# sortean cada año (base dinámica, p. ej. gastos_personal -> baii, arquetipo 10), ver el mapeo
# paralelo SUBTOTAL_PYG_BASE_DINAMICA_DE_PRIMITIVA más abajo, que necesita su propia lógica de
# corrección (_limitar_gastos_personal_por_baii) en vez de _limitar_por_subtotal.
SUBTOTAL_PYG_DE_PRIMITIVA = {
    "consumos_explotacion": "margen_bruto",
}

# Segunda relación estructural, de "base dinámica": a diferencia de margen_bruto (base
# ingresos_explotacion=100, siempre igual, se resuelve con una resta directa en
# _limitar_por_subtotal), baii depende TAMBIÉN de valor_añadido, amortizaciones y
# resultado_extraordinario — primitivas que no se conocen hasta después de sortear la PyG, no
# son un 100 fijo. Se resuelve en dos tiempos, sin iterar ni volver a tocar el generador
# aleatorio: se sortea la PyG con el objetivo sin contener del arquetipo, y SOLO si baii rebasa
# su techo/suelo se corrige gastos_personal de forma analítica (baii = valor_añadido -
# gastos_personal - amortizaciones + resultado_extraordinario es lineal en gastos_personal,
# coeficiente -1) usando los valores YA sorteados de las demás partidas — ver
# _limitar_gastos_personal_por_baii.
SUBTOTAL_PYG_BASE_DINAMICA_DE_PRIMITIVA = {
    "gastos_personal": "baii",
}

# Redacciones alternativas para `nota_memoria` cuando pyg_contencion_al_limite=True (arquetipo
# 10): cobertura narrativa de negocio para el dato técnico "gastos_personal_pct sube respecto al
# año anterior porque el techo de plausibilidad de baii lo exige", NO una explicación del
# mecanismo del motor. Cada una apunta a una causa de negocio distinta y verificable (convenio
# colectivo, contratación, indemnizaciones no recurrentes, cotizaciones sociales, variable ligado
# a objetivos) — primer ensayo, en pequeño, del patrón que hará falta a mayor escala en la futura
# fase de memoria cualitativa: varias redacciones alternativas para una misma señal técnica, no
# una plantilla única repetida. Selección aleatoria reproducible con un RNG DEDICADO
# (`rngs_nota` en generar_evolucion_arquetipo, independiente de rngs_pyg — ver ahí por qué:
# reutilizar rng_pyg sesgaba el sorteo, colapsándolo a un puñado de valores repetidos por
# semilla+año en vez de una elección uniforme por caso) — mismo caso (sector, segmento,
# intensidad, semilla, año), siempre la misma redacción; entre casos distintos, variedad
# uniforme entre las 5.
# Formato (texto, etiquetas) — igual que _NOTAS_COMODIN en motor.memoria, desde la combinación
# de arquetipos (sección 2.12): etiquetas FIJAS para las 5 (no varían plantilla a plantilla,
# a diferencia del arquetipo 22) — "gastos_personal", no "resultado" o "pyg" a secas, para no
# colisionar innecesariamente con otros arquetipos que toquen la PyG por otras vías.
NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE = (
    (
        "El incremento de los gastos de personal respecto al ejercicio anterior se explica por la "
        "actualización salarial derivada del convenio colectivo aplicable, que absorbió parte de la "
        "mejora de eficiencia operativa prevista para el ejercicio.",
        ("gastos_personal", "calidad_resultado"),
    ),
    (
        "Durante el ejercicio se incorporó personal cualificado adicional para sostener el "
        "crecimiento de la actividad, lo que elevó los gastos de personal por encima de lo "
        "inicialmente previsto, pese a la mejora del margen operativo en el resto de partidas.",
        ("gastos_personal", "calidad_resultado"),
    ),
    (
        "Los gastos de personal del ejercicio incluyen indemnizaciones puntuales asociadas a bajas "
        "voluntarias y ajustes de plantilla no recurrentes, que no se esperan repetir en próximos "
        "ejercicios.",
        ("gastos_personal", "calidad_resultado"),
    ),
    (
        "El aumento de los gastos de personal responde en parte al incremento de las cotizaciones "
        "sociales aplicable durante el ejercicio, un factor ajeno a la gestión operativa de la "
        "empresa.",
        ("gastos_personal", "calidad_resultado"),
    ),
    (
        "Se liquidaron durante el ejercicio complementos e incentivos variables ligados al "
        "cumplimiento de objetivos del ejercicio anterior, lo que elevó puntualmente los gastos de "
        "personal.",
        ("gastos_personal", "calidad_resultado"),
    ),
)

# Redacciones alternativas para `nota_memoria` del arquetipo 16 ("Riesgo de refinanciación"):
# se activan cada año en que el efecto reclasificacion_deuda empeora la calidad de la deuda
# (dirección -1, más concentración a corto plazo) — a diferencia del arquetipo 10, no es un caso
# límite raro, es la huella habitual del propio arquetipo cada año que actúa. Mismo patrón que
# NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE (selección reproducible con `rngs_nota`, redactadas
# aquí — a diferencia de las del arquetipo 10, no las dio el usuario, se escribieron directamente
# para este arquetipo): cada una apunta a una causa de negocio distinta y verificable para tener
# deuda relevante con vencimiento próximo (póliza sindicada pendiente de renovar, endurecimiento
# de condiciones de financiación, incumplimiento de covenants, sustitución de financiación a
# largo por líneas a corto, refinanciación en curso no formalizada).
# Etiquetas FIJAS — deliberadamente "deuda_corto_plazo" + "riesgo_refinanciacion", no "deuda" a
# secas, para no colisionar innecesariamente con el arquetipo 21 (coberturas) si algún día se
# combinan: son dos ángulos distintos de la deuda (riesgo de vencimiento vs. cobertura de tipo
# de interés), no la misma historia repetida.
NOTAS_MEMORIA_RIESGO_REFINANCIACION = (
    (
        "Durante el ejercicio venció y se reclasificó a corto plazo una póliza de crédito sindicada "
        "que la sociedad tiene previsto renovar en los próximos meses, sin que a la fecha de "
        "formulación de las cuentas se haya formalizado la renovación.",
        ("deuda_corto_plazo", "riesgo_refinanciacion"),
    ),
    (
        "El endurecimiento de las condiciones de financiación bancaria ha llevado a la entidad a "
        "priorizar líneas de crédito a corto plazo frente a la refinanciación a largo, lo que "
        "concentra vencimientos relevantes en los próximos doce meses.",
        ("deuda_corto_plazo", "riesgo_refinanciacion"),
    ),
    (
        "Parte de la deuda a largo plazo se ha reclasificado a corto plazo al no cumplirse "
        "determinados ratios financieros (covenants) exigidos por las entidades acreedoras, que "
        "otorgan a estas el derecho a exigir el vencimiento anticipado.",
        ("deuda_corto_plazo", "riesgo_refinanciacion"),
    ),
    (
        "La sociedad ha optado por un mayor uso de financiación a corto plazo (pólizas y descuento "
        "comercial) para cubrir necesidades puntuales de circulante, en sustitución de la "
        "financiación a largo plazo históricamente empleada.",
        ("deuda_corto_plazo", "riesgo_refinanciacion"),
    ),
    (
        "Está en curso un proceso de refinanciación con el pool bancario que, a la fecha de cierre "
        "del ejercicio, aún no se ha formalizado, por lo que la deuda afectada permanece "
        "clasificada a corto plazo hasta la firma del nuevo acuerdo.",
        ("deuda_corto_plazo", "riesgo_refinanciacion"),
    ),
)

# Redacciones alternativas para `nota_memoria` del arquetipo 18 ("Adquisición") — a diferencia de
# las anteriores (10: caso límite raro; 16: huella habitual pero condicionada a que el efecto
# actúe ese año), esta nota es OBLIGATORIA: se genera SIEMPRE que el arquetipo esté activo, en el
# año de la operación (AÑO_ADQUISICION), porque el arquetipo consiste precisamente en una
# operación que la memoria debe explicar — no es una señal de plausibilidad, es parte de la
# propia huella. Mismo patrón de selección reproducible (`rngs_nota`), redactadas directamente
# para este arquetipo: cada una apunta a un aspecto distinto y verificable de una combinación de
# negocios (fecha de toma de control, fondo de comercio, compra de activos/cartera a un
# competidor, estrategia de crecimiento inorgánico, forma de financiación).
# Etiquetas FIJAS — deliberadamente "adquisicion"/"combinacion_negocios", NO "activo": el
# arquetipo 19 ("activo mantenido para la venta") usa "activo" como etiqueta, y comprar una
# unidad de negocio (18) mientras se vende un activo no estratégico distinto (19) es una
# historia legítima y no redundante (Combo E los combina) — colisionarían en falso si ambos
# compartieran la etiqueta genérica "activo".
NOTAS_MEMORIA_ADQUISICION = (
    (
        "Durante el ejercicio la sociedad formalizó la adquisición de una unidad de negocio "
        "complementaria a su actividad principal, integrada en el perímetro de consolidación desde "
        "la fecha de toma de control.",
        ("adquisicion", "combinacion_negocios"),
    ),
    (
        "La operación de adquisición realizada en el ejercicio incluye el reconocimiento de un "
        "fondo de comercio derivado del exceso del precio pagado sobre el valor razonable de los "
        "activos netos identificables adquiridos.",
        ("adquisicion", "combinacion_negocios"),
    ),
    (
        "La sociedad adquirió durante el ejercicio los activos y la cartera de clientes de un "
        "competidor local, ampliando su capacidad productiva e instalada sin necesidad de "
        "inversión orgánica adicional.",
        ("adquisicion", "combinacion_negocios"),
    ),
    (
        "En el marco de su estrategia de crecimiento inorgánico, la sociedad culminó en el "
        "ejercicio la compra de una compañía del sector, cuyos activos y resultados se incorporan "
        "a las cuentas anuales desde la fecha de adquisición.",
        ("adquisicion", "combinacion_negocios"),
    ),
    (
        "La combinación de negocios formalizada en el ejercicio se financió mediante una "
        "combinación de recursos propios y nueva financiación bancaria a largo plazo, conforme al "
        "acuerdo de compraventa suscrito.",
        ("adquisicion", "combinacion_negocios"),
    ),
)

# Mapeo ESTRUCTURAL (no específico de ningún arquetipo): qué masas de circulante puede tocar un
# efecto masa_circulante son activo (su aumento incrementa la NOF: existencias, clientes) y
# cuáles son pasivo (su aumento la REDUCE: más financiación de proveedores, menos caja
# necesaria — acreedores_comerciales). El signo determina (a) cómo contribuye cada una al
# déficit de caja del año (ver _deficit_y_deuda_corto) y (b) si sirve como palanca de
# contención de endeudamiento: dampear una masa de PASIVO no reduce el pasivo total (lo que se
# gana en acreedores_comerciales se pierde en menos deuda a corto necesaria — son ambas
# componentes de pasivo_corriente, el efecto neto sobre el endeudamiento es CERO), así que solo
# las masas de ACTIVO (signo +1) participan en la contención — ver más abajo.
SIGNO_NOF_MASA_CIRCULANTE = {
    "existencias": 1,
    "realizable": 1,
    "acreedores_comerciales": -1,
}


class EvolucionArquetipoError(ValueError):
    """Parámetros de entrada inválidos."""


# --------------------------------------------------------------------------------------------
# Validación de plausibilidad del caso completo (sección 2.13) — pasada FINAL, independiente de
# qué arquetipos estén activos, sobre el caso YA generado (3 años, con toda la desagregación).
# Complementa (no sustituye) las contenciones ya existentes atadas a un arquetipo concreto
# (endeudamiento, `_limitar_por_subtotal`, `_limitar_gastos_personal_por_baii`, masa_circulante):
# esta pasada es DIAGNÓSTICO puro — nunca fuerza ningún valor — porque la mayoría de los 25
# ratios del catálogo (`ratios.*`) no tienen ninguna palanca de amortiguación natural atada a
# un mecanismo de arquetipo (ver CLAUDE.md, sección "Validación de plausibilidad del caso
# completo", y decisiones_plausibilidad.md #70 en adelante para el diseño completo, aprobado por
# el usuario antes de implementar). Cubre los 25 `ratios.*` + `pyg.baii_pct`/`pyg.margen_bruto_
# pct` (para cerrar el hallazgo original que motivó este encargo — un caso sin arquetipo activo
# puede salir implausible en esos dos SIN que nada lo detectara, ver decisiones #18/#39).
#
# Mismo criterio Huber±3·MAD ya usado en todo el proyecto (N_DESVIACIONES_TECHO_PYG/
# _ENDEUDAMIENTO). Una señal NO es un error: el propio diseño de ruido (85% típico/15% atípico)
# espera atípicos reales — el objetivo es que queden correctamente etiquetados, no eliminarlos.
N_DESVIACIONES_PLAUSIBILIDAD_CASO = 3.0

# Ensanchamiento de la banda de plausibilidad para 2024/2025 (decisiones_plausibilidad.md
# #81-#82) — el año base (2023) es una comparación válida contra el Huber transversal del sector
# (una única fotografía). 2024/2025 son la evolución de la MISMA empresa simulada — incluso con
# el ruido de PyG corregido (#78) y la retención de beneficios corregida (#80), queda un residuo
# de deriva pequeño pero real (PN crece unas décimas de punto por encima de ventas en años
# típicos) que el plug de cuadre absorbe año a año — para sectores con MAD real ya estrecho, eso
# basta para disparar muchas "desviaciones" aunque la magnitud económica sea modesta (correlación
# MAD/huber↔tasa de señal = -0,454 en el barrido de #81). MAD efectivo = mad·√(1+k·FACTOR), con
# k=años desde el año base (0 en 2023 → sin cambio, 1 en 2024, 2 en 2025) — la forma funcional
# (varianza acumulada ≈ lineal en k) refleja el propio diagnóstico de "paseo aleatorio" de #75/
# #77, no es arbitraria, aunque con solo 2 puntos (k=1,2) no se puede confirmar la forma exacta.
# Calibrado empíricamente (mismo método de siempre) para que 2025 se acerque a la tasa de señal
# del propio año base bajo un control limpio (`aumento_clientes:leve`, `ratios.liquidez`/
# `tesoreria`/`fm_activo`) — a `factor=3,0`, 2025 coincide EXACTO con el año base (16,2%);
# 2024 queda más laxo de lo que necesitaría en solitario (8,3% frente al 16,2% objetivo) — una
# única constante para k=1 y k=2 no puede calibrar ambos años de forma independiente, y el
# encargo pidió priorizar 2025 explícitamente. Ver #82.
FACTOR_ACUMULACION_VARIANZA_PLAUSIBILIDAD = 3.0

# Tolerancia mínima frente al techo/suelo — hallazgo del stress test: las contenciones ya
# existentes (`_endeudamiento`, `_limitar_por_subtotal`, `_limitar_gastos_personal_por_baii`)
# corrigen hasta dejar el valor EXACTO en su propio techo/suelo, pero la convergencia iterativa
# de `_endeudamiento` (tolerancia en euros, `TOLERANCIA_CONVERGENCIA_DETERIORO_EUR`) y la propia
# aritmética de coma flotante ("100.0 - techo_subtotal") dejan el valor final una fracción
# ínfima (1e-11 a 1e-13 observado) por DEBAJO del techo exacto — sin esta tolerancia, un caso ya
# corregido con éxito hasta el límite quedaba sin señalizar aquí, rompiendo el superconjunto del
# punto 4. `1e-6` (en unidades de "número de MAD") es varios órdenes de magnitud mayor que el
# ruido observado, pero sigue siendo perceptualmente cero frente al umbral de 3,0.
EPSILON_DESVIACIONES_PLAUSIBILIDAD_CASO = 1e-6

# Ratios con ancla de catálogo YA diagnosticada como contaminada en encargos anteriores —
# incluirlos generaría ruido masivo sin decir nada nuevo (mismo hallazgo, no se re-investiga):
#   - coste_deuda: denominador "Préstamos" distorsionado (decisiones #41-44).
#   - pago_dias: mismo patrón, denominador de compras minúsculo en servicios (#55).
#   - cobertura_gastos_fin: hereda la contaminación de "gastos financieros" (#45).
# Se calculan igual (quedan expuestos en `PlausibilidadCaso.valores_por_año` para quien quiera
# consultarlos) pero NUNCA generan una `SeñalRatio` — no cuentan como "caso implausible".
RATIOS_ANCLA_CONTAMINADA_INFORMATIVOS = ("ratios.coste_deuda", "ratios.pago_dias", "ratios.cobertura_gastos_fin")

# Circularidad — revisión sistemática de los 27 pedida explícitamente (no solo el caso que se
# detectó por casualidad): ¿hay algún punto del motor que sortee un valor usando LITERALMENTE
# el mismo huber_9y/huber_scale_mad que esta pasada comprobaría? Encontrados 2 (el resto solo
# combina sorteos de columnas DISTINTAS — masa_circulante/calidad_deuda/capex anclan su
# continuidad a una columna ratios.* distinta de la que sortea la masa en sí, balance.*, así que
# no son circulares, son combinaciones genuinamente emergentes):
#   - ventas_empleado: `motor.clasificacion_legal.estimar_plantilla` define
#     `plantilla = cifra_negocio / ventas_empleado_sorteado` — recalcular ventas/plantilla
#     reproduce EXACTO el valor sorteado, en los 3 años (la plantilla se deriva de él, no al
#     revés). Excluido de señal siempre.
#   - rotacion_activo: SOLO en el año base (2023) — `generar_empresa_base` sortea
#     `rotacion_activo` y calcula `activo_total = ventas/rotacion_activo_sorteado` (el plug de
#     cuadre solo toca `otras_deudas_corto`, nunca activo, así que no lo desvía) — recalcularlo
#     en 2023 reproduce el mismo valor. En 2024/2025 NO es circular: no se vuelve a sortear, el
#     activo evoluciona por ventas + efectos de arquetipo (capex/adquisición), así que la ratio
#     derivada esos años sí puede desviarse de verdad. Excluido de señal solo en el año base.
RATIO_CIRCULAR_SIEMPRE = "ratios.ventas_empleado"
RATIO_CIRCULAR_SOLO_AÑO_BASE = "ratios.rotacion_activo"

# Los 25 `ratios.*` (menos los 3 de ancla contaminada, informativos-sin-señal arriba, y menos
# ventas_empleado, circular puro) + los 2 `pyg.*` que cierran el hallazgo original — 23 en total,
# CADA UNO comprobado con Huber±3·MAD sobre el valor YA generado del caso (nunca sorteado aquí).
RATIOS_PLAUSIBILIDAD_SEÑALIZABLES = (
    "ratios.liquidez", "ratios.tesoreria", "ratios.disponibilidad_ratio",
    "ratios.fm_ventas", "ratios.fm_activo", "ratios.endeudamiento",
    "ratios.calidad_deuda", "ratios.capacidad_devolucion",
    "ratios.rotacion_activo", "ratios.rotacion_activo_no_corriente", "ratios.rotacion_activo_corriente",
    "ratios.rotacion_existencias", "ratios.plazo_existencias", "ratios.cobro_dias",
    "ratios.financiacion_clientes", "ratios.roi", "ratios.roe",
    "ratios.flujo_caja_activo", "ratios.flujo_caja_ventas",
    "ratios.beneficio_empleado", "ratios.gastos_personal_empleado",
    "pyg.baii_pct", "pyg.margen_bruto_pct",
)


def _ratios_derivados_del_caso(ejercicio: "EjercicioEmpresa", plantilla_estimada: float) -> dict[str, float | None]:
    """Calcula TODOS los ratios de esta pasada (señalizables + informativos + circular) a partir
    de cifras YA generadas del ejercicio — ninguno se sortea aquí. `None` si el denominador es
    0 (caso degenerado, sin sentido comprobar). Fórmulas estándar del análisis de estados
    financieros. Fórmulas verificadas contra el texto literal del PDF ACCID (`docs/ratios2024.
    pdf`, secciones 4.2-4.6), no de memoria — mismo estándar ya aplicado a `coste_deuda` en su
    momento (#41). Documenta 2 discrepancias encontradas al verificar, sobre mecanismos YA
    existentes y cerrados (`rotacion_existencias` en `masa_circulante`, `calidad_deuda` en
    `reclasificacion_deuda`) — ver decisiones_plausibilidad.md #71: esta función usa la fórmula
    CORRECTA del PDF (necesario para que la comprobación contra el Huber del catálogo tenga
    sentido), aunque difiera de la que usan esos mecanismos internos — no se tocó su código."""
    b = ejercicio.balance_eur
    p = ejercicio.pyg_eur
    ventas = ejercicio.ventas
    consumos_eur = p["consumos_explotacion"]
    activo_total_eur = b["activo_no_corriente"] + b["activo_corriente"]
    pasivo_total_eur = b["pasivo_no_corriente"] + b["pasivo_corriente"]
    deuda_financiera_eur = b["deudas_fin_largo"] + b["deudas_fin_corto"]
    fondo_maniobra_eur = b["activo_corriente"] - b["pasivo_corriente"]
    flujo_caja_eur = p["resultado_ejercicio"] + p["amortizaciones"]

    def _div(numerador: float, denominador: float) -> float | None:
        return numerador / denominador if denominador else None

    return {
        "ratios.liquidez": _div(b["activo_corriente"], b["pasivo_corriente"]),
        "ratios.tesoreria": _div(b["realizable"] + b["disponible"], b["pasivo_corriente"]),
        "ratios.disponibilidad_ratio": _div(b["disponible"], b["pasivo_corriente"]),
        "ratios.fm_ventas": _div(fondo_maniobra_eur, ventas),
        "ratios.fm_activo": _div(fondo_maniobra_eur, activo_total_eur),
        "ratios.endeudamiento": _div(pasivo_total_eur, activo_total_eur),
        # PDF: "Calidad de la deuda = Pasivo corriente / Deudas totales" — proporción de deuda a
        # CORTO sobre el TOTAL de pasivo (financiero + no financiero), cuanto más bajo mejor
        # calidad. Distinto del que usa `reclasificacion_deuda` (deudas_fin_largo/deuda_
        # financiera — solo deuda CON coste, polaridad inversa) — ver decisiones #71.
        "ratios.calidad_deuda": _div(b["pasivo_corriente"], pasivo_total_eur),
        # PDF: "Capacidad de devolución = (Resultado neto+Amortizaciones) / Deudas totales" (el
        # propio texto explica que sustituye "Préstamos" por "total de deudas" al no poder
        # aislar los préstamos en un balance abreviado real).
        "ratios.capacidad_devolucion": _div(flujo_caja_eur, pasivo_total_eur),
        "ratios.cobertura_gastos_fin": _div(p["baii"], p["gastos_financieros"]),
        "ratios.coste_deuda": _div(p["gastos_financieros"], deuda_financiera_eur),
        "ratios.rotacion_activo": _div(ventas, activo_total_eur),
        "ratios.rotacion_activo_no_corriente": _div(ventas, b["activo_no_corriente"]),
        "ratios.rotacion_activo_corriente": _div(ventas, b["activo_corriente"]),
        # PDF: "Rotación de stocks = Consumos / Existencias" — NO ventas. Distinto del ancla que
        # usa `masa_circulante` (arquetipos 1/5) para este mismo ratio, ver decisiones #71.
        "ratios.rotacion_existencias": _div(consumos_eur, b["existencias"]),
        # PDF: "Plazo de existencias = Existencias / Consumos de explotación × 365" — NO ventas
        # (a diferencia de cobro_dias, que SÍ usa ventas).
        "ratios.plazo_existencias": _div(b["existencias"], consumos_eur) * DIAS_AÑO if consumos_eur else None,
        "ratios.cobro_dias": _div(b["realizable"], ventas) * DIAS_AÑO if ventas else None,
        # PDF: "Plazo de pago = Acreedores comerciales / Compras × 365" — el motor no modela
        # "Compras" como línea propia; se aproxima con consumos_explotacion (mismo denominador
        # que plazo_existencias) — MISMA distorsión ya diagnosticada para pago_dias (#55), por
        # eso queda excluido de señal dura de todos modos (RATIOS_ANCLA_CONTAMINADA_INFORMATIVOS).
        "ratios.pago_dias": _div(b["acreedores_comerciales"], consumos_eur) * DIAS_AÑO if consumos_eur else None,
        # PDF: "Financiación de la inversión en clientes por acreedores comerciales = Acreedores
        # comerciales / Clientes" — un ratio directo, NO una cifra en días (mi primer borrador lo
        # trataba como "días", fórmula equivocada — Clientes aproximado por `realizable`, mismo
        # criterio ya establecido en el lote 2, cobro_dias ≈ realizable).
        "ratios.financiacion_clientes": _div(b["acreedores_comerciales"], b["realizable"]),
        "ratios.roi": _div(p["baii"], activo_total_eur),
        "ratios.roe": _div(p["resultado_ejercicio"], b["patrimonio_neto"]),
        "ratios.flujo_caja_activo": _div(flujo_caja_eur, activo_total_eur),
        "ratios.flujo_caja_ventas": _div(flujo_caja_eur, ventas),
        # Las 3 ratios "por empleado" del catálogo están en MILES de € (confirmado: huber_9y de
        # ventas_empleado ronda 300-900, imposible en € crudos para una cifra "por empleado" —
        # ya documentado así en motor.clasificacion_legal). Mi primer borrador devolvía € crudos
        # — error de unidades, corregido (÷1000).
        "ratios.ventas_empleado": _div(ventas, plantilla_estimada * 1000) if plantilla_estimada else None,
        "ratios.beneficio_empleado": _div(p["resultado_ejercicio"], plantilla_estimada * 1000) if plantilla_estimada else None,
        "ratios.gastos_personal_empleado": _div(p["gastos_personal"], plantilla_estimada * 1000) if plantilla_estimada else None,
        "pyg.baii_pct": ejercicio.pyg_pct["baii"],
        "pyg.margen_bruto_pct": ejercicio.pyg_pct["margen_bruto"],
    }


@dataclass(frozen=True)
class SeñalRatio:
    """Un ratio, en un año concreto, fuera de `huber_9y ± N_DESVIACIONES_PLAUSIBILIDAD_CASO ×
    huber_scale_mad` del sector — diagnóstico, nunca una corrección: el valor citado aquí es el
    mismo que ya quedó en `balance_eur`/`pyg_eur`, sin modificar."""

    ratio: str
    año: int
    valor: float
    huber_9y: float
    huber_scale_mad: float
    desviaciones: float  # (valor - huber_9y) / huber_scale_mad, CON signo
    direccion: str  # "por_encima" | "por_debajo"


@dataclass(frozen=True)
class PlausibilidadCaso:
    """Resultado de la pasada final de plausibilidad (sección 2.13) sobre un caso completo (los
    3 años). Superconjunto de las señales ya existentes (`riesgo_endeudamiento`, `riesgo_
    plausibilidad_pyg`, etc.) — nunca las sustituye ni las contradice: cuando esas ya están
    activas, las señales de este informe para el mismo ratio/año deben coincidir siempre (
    verificado en el stress test, no solo asumido)."""

    señales: tuple[SeñalRatio, ...]
    # TODOS los ratios calculados por año, señalizables o no (incluye los de ancla contaminada y
    # el circular) — para quien quiera inspeccionar el detalle completo, no solo las señales.
    valores_por_año: dict[int, dict[str, float | None]]

    @property
    def tiene_señales(self) -> bool:
        return len(self.señales) > 0

    def señales_de(self, ratio: str) -> tuple[SeñalRatio, ...]:
        return tuple(s for s in self.señales if s.ratio == ratio)


def _evaluar_plausibilidad_caso(
    ejercicios: dict[int, "EjercicioEmpresa"], fila: pd.Series, plantilla_por_año: dict[int, float]
) -> PlausibilidadCaso:
    """Ejecuta la pasada sobre los 3 años ya generados — ver constantes/docstring arriba para el
    diseño completo. Llamada UNA vez, al final de `generar_evolucion_combinada`, después de que
    todos los arquetipos ya se aplicaron."""
    señales: list[SeñalRatio] = []
    valores_por_año: dict[int, dict[str, float | None]] = {}
    for año, ejercicio in ejercicios.items():
        valores = _ratios_derivados_del_caso(ejercicio, plantilla_por_año[año])
        valores_por_año[año] = valores
        # Ensanchamiento por año evolucionado (#81-#82) — k=0 en el año base (factor=1, sin
        # cambio: sigue siendo una comparación transversal válida), k=1/2 en 2024/2025.
        k_año = año - AÑO_BASE
        factor_ensanchamiento = (1 + k_año * FACTOR_ACUMULACION_VARIANZA_PLAUSIBILIDAD) ** 0.5
        for ratio in RATIOS_PLAUSIBILIDAD_SEÑALIZABLES:
            if ratio == RATIO_CIRCULAR_SOLO_AÑO_BASE and año == AÑO_BASE:
                continue
            valor = valores[ratio]
            if valor is None:
                continue
            huber = fila[f"{ratio}.huber_9y"]
            mad = fila[f"{ratio}.huber_scale_mad"]
            if mad < 0:
                continue  # dato de catálogo inválido (no debería ocurrir, defensivo)
            # `ratios.endeudamiento` NUNCA se ensancha — su techo es el MISMO límite absoluto
            # que ya usa la contención de endeudamiento (ver más abajo), no una banda estadística
            # que deba ampliarse con los años: TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO es un límite
            # económico duro, no un percentil de una distribución transversal.
            mad_efectivo = mad if ratio == "ratios.endeudamiento" else mad * factor_ensanchamiento
            # `huber_scale_mad == 0` (varianza histórica nula en la muestra del sector) NO se
            # salta — mismo criterio que ya usa `_endeudamiento` (huber + 3·0 = huber, degenera
            # a un techo exacto): CUALQUIER desviación de `huber` es, por definición, un caso sin
            # precedente en la muestra. `desviaciones` se reporta como +-inf en ese caso (no hay
            # escala con la que medir "cuántas MAD", pero SÍ hay una dirección clara). Un
            # `mad` original igual a 0 sigue dando `mad_efectivo=0` (0 × cualquier factor = 0),
            # así que este caso degenera igual de bien ensanchado o sin ensanchar.
            if mad_efectivo == 0:
                desviaciones = float("inf") if valor > huber else (float("-inf") if valor < huber else 0.0)
            else:
                desviaciones = (valor - huber) / mad_efectivo
            # Comparación INCLUSIVA (>=/<=), no estricta — hallazgo del stress test: las
            # contenciones ya existentes (`_endeudamiento`, `_limitar_por_subtotal`,
            # `_limitar_gastos_personal_por_baii`) corrigen ANALÍTICAMENTE hasta dejar el valor
            # EXACTO en su propio techo/suelo (huber±3·MAD), nunca por debajo — con `>` estricto,
            # un caso "corregido con éxito hasta el límite exacto" no quedaba señalizado aquí,
            # rompiendo la garantía de superconjunto del punto 4 (`riesgo_endeudamiento`/
            # `riesgo_plausibilidad_pyg` a True sin señal nueva correspondiente). Verificado
            # también que degenera correctamente para las 8 desviaciones = 0 (mad=0, valor=huber).
            tolerancia = (
                EPSILON_DESVIACIONES_PLAUSIBILIDAD_CASO * mad_efectivo
                if mad_efectivo > 0
                else EPSILON_DESVIACIONES_PLAUSIBILIDAD_CASO
            )
            if ratio == "ratios.endeudamiento":
                # Mismo techo EXACTO que ya usa la contención de endeudamiento (huber+3·MAD
                # recortado a TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO=0,85) — sin este ajuste, un
                # caso con `riesgo_endeudamiento=True` por haber tocado el techo absoluto
                # (huber+3·MAD de ese sector > 0,85) podría NO quedar señalizado aquí (huber+
                # 3·MAD sin recortar es más laxo). El suelo (endeudamiento inusualmente BAJO) no
                # tiene ningún recorte absoluto ya establecido, usa el criterio genérico.
                techo = min(huber + N_DESVIACIONES_PLAUSIBILIDAD_CASO * mad, TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO)
                suelo = huber - N_DESVIACIONES_PLAUSIBILIDAD_CASO * mad
                fuera_de_rango = valor >= techo - tolerancia or valor <= suelo + tolerancia
            else:
                fuera_de_rango = abs(desviaciones) >= N_DESVIACIONES_PLAUSIBILIDAD_CASO - EPSILON_DESVIACIONES_PLAUSIBILIDAD_CASO
            if fuera_de_rango:
                señales.append(
                    SeñalRatio(
                        ratio=ratio, año=año, valor=valor, huber_9y=huber, huber_scale_mad=mad,
                        desviaciones=desviaciones, direccion="por_encima" if desviaciones > 0 else "por_debajo",
                    )
                )
    return PlausibilidadCaso(señales=tuple(señales), valores_por_año=valores_por_año)


@dataclass(frozen=True)
class NotaMemoria:
    """Una nota de memoria, con sus etiquetas temáticas — vive aquí (no en motor.memoria) porque
    la generan tanto motor.memoria (arquetipos 7/19/20/21/22) como este módulo (10/16/18);
    motor.memoria importa esta clase de aquí para evitar una dependencia circular (este módulo
    no depende de motor.memoria)."""

    arquetipo_id: str
    numero: int
    texto: str
    etiquetas: tuple[str, ...]


@dataclass(frozen=True)
class EfectoActivo:
    """Un `Efecto` ya emparejado con la intensidad de SU PROPIO arquetipo de origen — necesario
    para combinar varios arquetipos con intensidades distintas en el mismo caso (sección 2.12).
    `numero` viene de `DefinicionArquetipo.numero`, para poder generar notas sin necesitar el
    diccionario completo de arquetipos dentro de `_evolucionar_un_año`. Ver
    `generar_evolucion_combinada` y la sección "Combinación de arquetipos" del docstring del
    módulo."""

    efecto: Efecto
    arquetipo_id: str
    numero: int
    intensidad_efectiva: float
    intensidad_base: float


@dataclass(frozen=True)
class EjercicioEmpresa:
    año: int
    ventas: float
    crecimiento_ventas: float | None  # None en el año base (2023)
    balance_eur: dict[str, float]
    pyg_eur: dict[str, float]
    pyg_pct: dict[str, float]
    modos: dict[str, str]
    ajuste_cuadre_eur: float
    deuda_extra_por_nof_eur: float  # 0.0 salvo cuando la tesorería no basta para absorber la NOF
    endeudamiento: float  # pasivo total / activo total, ya con cualquier contención aplicada
    cobertura_gastos_financieros: float  # BAII / gastos financieros
    riesgo_endeudamiento: bool = False
    endeudamiento_sin_contener: float | None = None  # solo si riesgo_endeudamiento=True
    deterioro_aplicado_eur: float = 0.0  # exceso de circulante amortiguado por plausibilidad
    contencion_al_limite: bool = False  # True si no se pudo llegar al techo (nada que amortiguar, o se agotó)
    apalancamiento_extra_eur: float = 0.0  # deuda a largo extra por el efecto "apalancamiento", si lo hay
    payout_dividendos_eur: float = 0.0  # dividendo con cargo a resultado retenido (payout de fondo, ver #79-#80)
    payout_deuda_extra_eur: float = 0.0  # deuda a corto NUEVA que financia el payout cuando la caja no basta (#82)
    riesgo_plausibilidad_pyg: bool = False  # True si algún efecto pyg_primitiva topó el techo/suelo de su subtotal
    pyg_subtotales_sin_contener: dict[str, float] = field(default_factory=dict)  # {subtotal: valor antes de topar}
    pyg_contencion_al_limite: bool = False  # True si un efecto de "base dinámica" (baii) tuvo que invertir su
    # sentido para no rebasar el techo/suelo del sector — amortiguar su propia intensidad a cero no bastaba
    # (el desbordamiento venía del ruido de la base ese año, no del arquetipo). Ver docstring del módulo.
    notas_memoria: tuple[NotaMemoria, ...] = ()  # cobertura narrativa de negocio — caso límite raro (10), huella
    # habitual del propio arquetipo (16), u OBLIGATORIA siempre que el arquetipo esté activo (18). Lista (no un
    # único valor) desde la combinación de arquetipos (sección 2.12): un caso combinado puede tener varias.
    ventas_organicas_eur: float | None = None  # solo en AÑO_ADQUISICION (18): ventas sin la operación
    ventas_inorganicas_eur: float | None = None  # solo en AÑO_ADQUISICION (18): aportación de la unidad adquirida
    capital_social_eur: float = 0.0  # fijo desde el año base (2023), constante en 2024/2025 — ver empresa_base.py
    reservas_eur: float = 0.0  # = patrimonio_neto - capital_social_eur - pyg_eur["resultado_ejercicio"], por resta
    activo_no_corriente_perfil_pct: dict[str, float] = field(default_factory=dict)  # fijo desde 2023, ver empresa_base.py
    activo_no_corriente_desglose_eur: dict[str, float] = field(default_factory=dict)  # SIN el salto de adquisición (18)
    incremento_activo_adquisicion_eur: float = 0.0  # solo en AÑO_ADQUISICION (18) — mantenido aparte del desglose
    # Amortización derivada de una colección real de activos (motor/amortizacion.py) — la
    # colección de ESTE año (base + cualquier cohorte nueva de capex/adquisición ya incorporada),
    # más los perfiles de sub-tipo (constantes, igual que el perfil de nivel superior) para que
    # una adquisición en 2025 pueda seguir generando cohortes sin re-sortear "el perfil completo".
    coleccion_activos_amortizables: tuple = ()
    perfil_subtipos_material_pct: dict[str, float] = field(default_factory=dict)
    perfil_subtipos_intangible_pct: dict[str, float] = field(default_factory=dict)
    tipo_interes: float = 0.0  # ver empresa_base.EmpresaBase.tipo_interes — expuesto para el Δr de la cobertura

    # --- Bajas anticipadas de sub-lotes (línea 11 PGC, "Deterioro y resultado por enajenaciones
    # del inmovilizado", ver motor/amortizacion.py) — () en el año base y en cualquier año sin
    # baja. `baja_valor_en_libros_eur`/`..._valor_venta_eur` son las sumas de ESTE año (ya
    # restadas/sumadas en `balance_eur["activo_no_corriente"]`/`disponible`): expuestas aparte
    # para que `motor/efe.py` pueda excluir el valor en libros del delta "orgánico" de B) e
    # incluir el precio de venta como cobro real, mismo patrón que `incremento_activo_
    # adquisicion_eur` (18). ---
    bajas_inmovilizado: tuple = ()
    baja_valor_en_libros_eur: float = 0.0
    baja_valor_venta_eur: float = 0.0

    # --- Cobertura de flujos de efectivo (arquetipo 21) — ver motor/coberturas_subvenciones.py.
    # Estado bruto (antes de impuesto) que se traslada año a año; los importes NETOS de PN y las
    # cuentas de impuesto diferido son propiedades derivadas más abajo, no se guardan aparte. ---
    cobertura_activa: bool = False
    cobertura_pct_deuda: float = 0.0  # % de la deuda financiera cubierta, fijo por caso
    cobertura_eficacia_pct: float = 0.0  # fijo por caso
    cobertura_nocional_vivo_eur: float = 0.0
    cobertura_plazo_residual_años: float = 0.0
    cobertura_valor_swap_eur: float = 0.0  # V(t): valor razonable BRUTO del derivado (con signo)
    cobertura_saldo_1340_bruto_eur: float = 0.0  # B(t): reserva de PN bruta (con signo)
    cobertura_eficaz_bruto_eur: float = 0.0  # flujo de ESTE año (Documento A, fila B.2)
    cobertura_transferencia_bruto_eur: float = 0.0  # flujo de ESTE año (Documento A, fila C.2)
    cobertura_ineficaz_bruto_eur: float = 0.0  # flujo de ESTE año, directo a PyG, informativo

    # --- Subvención de capital (transversal, disparada por el arquetipo 17) — mismo módulo. ---
    subvencion_activo_asociado: tuple = ()  # sub-lotes de motor.amortizacion ligados a esta subvención
    subvencion_pct_cofinanciacion: float = 0.0
    subvencion_saldo_130_bruto_eur: float = 0.0
    subvencion_importe_concedido_eur: float = 0.0  # flujo de ESTE año (Documento A, fila B.7) — 0 salvo el año de concesión
    subvencion_transferencia_bruto_eur: float = 0.0  # flujo de ESTE año (Documento A, fila C.7)

    # --- Primer lote de desglose de balance (existencias + periodificaciones) — perfil (%) fijo
    # desde 2023, desglose (€) recalculado cada año sobre la masa agregada de ESE año, mismo
    # patrón que activo_no_corriente. Ver motor/empresa_base.py. ---
    existencias_perfil_pct: dict[str, float] = field(default_factory=dict)
    existencias_desglose_eur: dict[str, float] = field(default_factory=dict)
    periodificacion_activo_pct: float = 0.0
    periodificacion_pasivo_corto_pct: float = 0.0
    periodificacion_pasivo_largo_pct: float = 0.0

    # --- Segundo lote de desglose de balance (deudores/acreedores comerciales) — perfil (%)
    # fijo desde 2023 (arquetipo-agnóstico salvo que el 20 fuerce una sub-partida de grupo/
    # varios, ver ParametrosOperacionVinculada), desglose (€) recalculado cada año sobre la masa
    # ya cuadrada de ese año, mismo patrón que existencias. ---
    deudores_perfil_pct: dict[str, float] = field(default_factory=dict)
    deudores_desglose_eur: dict[str, float] = field(default_factory=dict)
    acreedores_perfil_pct: dict[str, float] = field(default_factory=dict)
    acreedores_desglose_eur: dict[str, float] = field(default_factory=dict)

    # --- Operaciones vinculadas (arquetipo 20) — ver ParametrosOperacionVinculada. Las 2 masas
    # financieras ("préstamo a matriz"/"financiación recibida de grupo") NO son carve-out de
    # nada existente: son líneas propias nuevas ("Inversiones en empresas del grupo y asociadas
    # a l/p" / "Deudas con empresas del grupo y asociadas a l/p"), en 0.0 salvo que esa operación
    # concreta esté activa. `operacion_vinculada_importe_eur`/`_pct_mostrado` son el importe YA
    # aterrizado en el balance de este año (el mismo que cita la nota de memoria — ver
    # motor/memoria.py — nunca un número sorteado aparte). ---
    operacion_vinculada_activa: bool = False
    operacion_vinculada_indice: int = -1
    operacion_vinculada_tipo: str = ""
    operacion_vinculada_importe_eur: float = 0.0
    operacion_vinculada_pct_mostrado: float = 0.0
    inversion_grupo_largo_eur: float = 0.0
    deuda_grupo_largo_eur: float = 0.0

    # --- Provisiones a largo/corto plazo (tercer lote de desglose de balance, ver
    # motor/provisiones.py) — probabilidad de fondo independiente de cualquier arquetipo (puede
    # aparecer con el 6, "línea base sana"). `provision_importe_dotado_eur` es el importe TOTAL
    # dotado (fijo desde el año de dotación); `..._saldo_largo_eur`/`..._saldo_corto_eur` son el
    # saldo de ESTE año, reclasificado íntegro según el horizonte restante (nunca ambos > 0 a la
    # vez). `..._dotacion_eur`/`..._aplicacion_eur`/`..._exceso_eur` son los FLUJOS de ESTE año
    # (0.0 salvo el año que corresponda) — movimiento anual completo, ver PasoProvision. Distinto
    # del arquetipo 22 (contingencia, puramente textual, sin huella de balance) — no confundir. ---
    provision_activa: bool = False
    provision_categoria: str = ""
    provision_naturaleza_pyg: str = ""
    provision_importe_dotado_eur: float = 0.0
    provision_saldo_largo_eur: float = 0.0
    provision_saldo_corto_eur: float = 0.0
    provision_dotacion_eur: float = 0.0
    provision_aplicacion_eur: float = 0.0
    provision_exceso_eur: float = 0.0

    # --- Deterioro de valor de créditos por operaciones comerciales (cuenta 490, ver
    # motor/insolvencias.py) — DETERIORO DE ACTIVO (resta de `realizable`), a diferencia de las
    # provisiones de arriba (pasivo). Probabilidad de fondo independiente de cualquier arquetipo,
    # anclada a `ratios.cobro_dias`, con boost de probabilidad/magnitud si el arquetipo 4
    # (deterioro del ciclo de caja) o el 7 (dependencia de pocos clientes) están activos.
    # `insolvencia_saldo_eur`/`..._dotacion_eur`/`..._aplicacion_eur`/`..._exceso_eur` son el
    # movimiento anual completo (mismo criterio que provisiones); `insolvencia_deduccion_
    # realizable_eur` es lo que de verdad se resta de `balance_eur["realizable"]` este año — NO
    # coincide con `saldo_eur` (ver docstring del módulo: la aplicación no recupera realizable,
    # solo la reversión). ---
    insolvencia_activa: bool = False
    insolvencia_importe_dotado_eur: float = 0.0
    insolvencia_saldo_eur: float = 0.0
    insolvencia_exceso_acumulado_eur: float = 0.0
    insolvencia_dotacion_eur: float = 0.0
    insolvencia_aplicacion_eur: float = 0.0
    insolvencia_exceso_eur: float = 0.0
    insolvencia_deduccion_realizable_eur: float = 0.0

    # --- Cuarto y último lote de desglose de balance (deudas financieras largo/corto plazo,
    # ver motor/empresa_base.py y motor/coberturas_subvenciones.py) — `deudas_fin_fraccion_total`/
    # `..._fraccion_largo` son el perfil FIJO del caso (leasing/obligaciones/otros pasivos
    # financieros); `deudas_fin_largo_desglose_eur`/`..._corto_desglose_eur` son las 5 categorías
    # ya resueltas de ESTE año (Entidades de crédito como residual, Derivados driven por el
    # arquetipo 21), cada uno sumando exacto a `balance_eur["deudas_fin_largo"]`/
    # `["deudas_fin_corto"]`. ---
    deudas_fin_fraccion_total: dict[str, float] = field(default_factory=dict)
    deudas_fin_fraccion_largo: dict[str, float] = field(default_factory=dict)
    deudas_fin_largo_desglose_eur: dict[str, float] = field(default_factory=dict)
    deudas_fin_corto_desglose_eur: dict[str, float] = field(default_factory=dict)

    # --- Desglose de PyG en líneas oficiales del PGC (encargo 1/2 de este lote, ver
    # motor/empresa_base.py) — perfiles (%) fijos desde 2023 para cifra_negocios/consumos_
    # explotacion/otros_gastos_explot, desglose (€) recalculado cada año sobre el agregado ya
    # generado de ese año. gastos_personal/ingresos_financieros son fórmula derivada (sin perfil
    # propio ni ruido) — ver calcular_desglose_gastos_personal/calcular_desglose_ingresos_
    # financieros en motor.empresa_base. ---
    pyg_cifra_negocios_perfil_pct: dict[str, float] = field(default_factory=dict)
    pyg_cifra_negocios_desglose_eur: dict[str, float] = field(default_factory=dict)
    pyg_consumos_explotacion_perfil_pct: dict[str, float] = field(default_factory=dict)
    pyg_consumos_explotacion_desglose_eur: dict[str, float] = field(default_factory=dict)
    pyg_otros_gastos_explot_perfil_pct: dict[str, float] = field(default_factory=dict)
    pyg_otros_gastos_explot_desglose_eur: dict[str, float] = field(default_factory=dict)
    pyg_gastos_personal_desglose_eur: dict[str, float] = field(default_factory=dict)
    pyg_ingresos_financieros_desglose_eur: dict[str, float] = field(default_factory=dict)

    # --- Quinto lote de desglose de balance ("Otras deudas" largo/corto plazo, ver motor/
    # empresa_base.py) — `otras_deudas_largo_perfil_pct`/`..._corto_resto_perfil_pct` son el
    # perfil FIJO del caso (arquetipo-agnóstico salvo `deudas_socios_activa`, decidida una única
    # vez, sin ancla a ningún arquetipo); `otras_deudas_largo_desglose_eur`/`..._corto_desglose_
    # eur` son las 4 sub-partidas ya resueltas de ESTE año (con la reclasificación anual de
    # `acreedores_inmovilizado` de largo a corto ya aplicada), sumando exacto al residuo de cada
    # plazo tras excluir provisiones/deudas del grupo/pasivos por impuesto diferido.
    # `aapp_pendiente_corto_pct` es la ÚNICA pieza que NO es fija desde 2023 (re-invocada cada
    # año, con el boost de arquetipo 4/7 ya aplicado si procede) — pero DETERMINISTA para
    # semilla/sector/segmento/boost dados: como el boost es una propiedad del caso completo (un
    # arquetipo activo lo está en 2024 Y 2025 por igual), el resultado nunca "parpadea" entre
    # esos dos años, verificado — ver docstring de `sortear_aapp_pendiente_corto_pct` en
    # motor.empresa_base para la propiedad completa. ---
    deudas_socios_activa: bool = False
    otras_deudas_largo_perfil_pct: dict[str, float] = field(default_factory=dict)
    otras_deudas_corto_resto_perfil_pct: dict[str, float] = field(default_factory=dict)
    otras_deudas_largo_desglose_eur: dict[str, float] = field(default_factory=dict)
    otras_deudas_corto_desglose_eur: dict[str, float] = field(default_factory=dict)
    aapp_pendiente_corto_pct: float = 0.0

    @property
    def pyg_linea_11_deterioro_resultado_enajenacion_inmovilizado_eur(self) -> float:
        """Línea oficial "11. Deterioro y resultado por enajenaciones del inmovilizado" del
        modelo PGC de PyG — alias de `pyg_eur["deterioro_enajenacion_inmovilizado"]`, ya sumado
        dentro de `baii` en `_generar_pyg_hasta_baii` (motor.empresa_base). SIEMPRE derivado de
        las bajas anticipadas de sub-lotes de este año (`bajas_inmovilizado`), nunca sorteado
        desde el catálogo — ver motor/amortizacion.py."""
        return self.pyg_eur["deterioro_enajenacion_inmovilizado"]

    @property
    def pyg_linea_13_otros_resultados_eur(self) -> float:
        """Línea oficial "13. Otros resultados" del modelo PGC (dentro del resultado de
        explotación) — el PGC 2007 no tiene categoría "extraordinarios". Alias de `pyg_eur[
        "resultado_extraordinario"]`, ya sumado dentro de `baii` en `_generar_pyg_hasta_baii`
        (motor.empresa_base): no hay ningún cambio numérico, solo de nomenclatura/ubicación
        oficial — la partida interna `resultado_extraordinario` sigue existiendo sin cambios
        para el análisis y los arquetipos (12, "evento puntual") que la usan."""
        return self.pyg_eur["resultado_extraordinario"]

    @property
    def pyg_linea_10_excesos_provisiones_eur(self) -> float:
        """Línea oficial "10. Excesos de provisiones" del modelo PGC — suma de las reversiones de
        ESTE año de provisiones (subgrupo 14, `motor.provisiones`) e insolvencias de clientes
        (cuenta 490, `motor.insolvencias`), ya incluidas dentro de `pyg_eur["otros_ingresos_
        explot"]` (ver `_evaluar` en este módulo): expuesta aparte solo como referencia a la
        línea oficial, sin ningún importe nuevo ni sorteo adicional."""
        return self.provision_exceso_eur + self.insolvencia_exceso_eur

    @property
    def periodificacion_activo_eur(self) -> float:
        return self.periodificacion_activo_pct * self.balance_eur["realizable"]

    @property
    def periodificacion_pasivo_corto_eur(self) -> float:
        return self.periodificacion_pasivo_corto_pct * self.balance_eur["otras_deudas_corto"]

    @property
    def periodificacion_pasivo_largo_eur(self) -> float:
        return self.periodificacion_pasivo_largo_pct * self.balance_eur["otras_deudas_largo"]

    @property
    def ajustes_cambio_valor_pn_eur(self) -> float:
        """A-2 del balance — saldo de la cobertura NETO de su efecto impositivo."""
        return presentacion_neta_eur(self.cobertura_saldo_1340_bruto_eur)

    @property
    def subvenciones_pn_eur(self) -> float:
        """A-3 del balance — saldo de la subvención NETO de su efecto impositivo."""
        return presentacion_neta_eur(self.subvencion_saldo_130_bruto_eur)

    @property
    def activos_por_impuesto_diferido_eur(self) -> float:
        return activo_por_impuesto_diferido_eur(self.cobertura_saldo_1340_bruto_eur)

    @property
    def pasivos_por_impuesto_diferido_eur(self) -> float:
        return pasivo_por_impuesto_diferido_eur(self.cobertura_saldo_1340_bruto_eur) + pasivo_por_impuesto_diferido_eur(
            self.subvencion_saldo_130_bruto_eur
        )

    @property
    def rotacion_existencias(self) -> float:
        return self.ventas / self.balance_eur["existencias"]

    @property
    def cobro_dias(self) -> float:
        return self.balance_eur["realizable"] / self.ventas * DIAS_AÑO


@dataclass(frozen=True)
class EvolucionArquetipo:
    sector_codigo: str
    sector_nombre: str
    segmento: str
    arquetipo: str
    intensidad: str
    semilla: int
    crecimiento_pleno_objetivo: float
    ejercicios: dict[int, EjercicioEmpresa]
    catalogo_version: str  # hash del CSV del catálogo usado para generar el caso (sección 2.15)
    pgc_version: str = PGC_VERSION
    notas_memoria_pura: tuple[NotaMemoria, ...] = ()  # notas de arquetipos clase="memoria_pura" (7/19/20/21/22)
    # activos en el caso, si los hay — no van por año (no son de un ejercicio concreto), las genera y
    # resuelve motor.memoria.generar_caso_combinado, no este módulo (que no depende de motor.memoria).
    plausibilidad: PlausibilidadCaso | None = None  # pasada final de plausibilidad (sección 2.13) — ver ese bloque arriba
    modo_generacion: str = "aleatorio"  # "tipico"|"atipico"|"aleatorio" — sección 2.15/2.16, ver motor.ruido


def _endeudamiento(balance_eur: dict[str, float]) -> float:
    activo_total = balance_eur["activo_no_corriente"] + balance_eur["activo_corriente"]
    pasivo_total = balance_eur["pasivo_no_corriente"] + balance_eur["pasivo_corriente"]
    return pasivo_total / activo_total


def _cobertura_gastos_financieros(pyg_eur: dict[str, float]) -> float:
    gastos_financieros_eur = pyg_eur["gastos_financieros"]
    if gastos_financieros_eur <= 0:
        return float("inf")
    return pyg_eur["baii"] / gastos_financieros_eur


def _ejercicio_desde_empresa_base(empresa: EmpresaBase) -> EjercicioEmpresa:
    return EjercicioEmpresa(
        año=AÑO_BASE,
        ventas=empresa.ventas_objetivo,
        crecimiento_ventas=None,
        balance_eur=dict(empresa.balance_eur),
        pyg_eur=dict(empresa.pyg_eur),
        pyg_pct=dict(empresa.pyg_pct),
        modos=dict(empresa.modos),
        ajuste_cuadre_eur=empresa.ajuste_cuadre_eur,
        deuda_extra_por_nof_eur=0.0,
        endeudamiento=_endeudamiento(empresa.balance_eur),
        cobertura_gastos_financieros=_cobertura_gastos_financieros(empresa.pyg_eur),
        capital_social_eur=empresa.capital_social_eur,
        reservas_eur=empresa.reservas_eur,
        activo_no_corriente_perfil_pct=dict(empresa.activo_no_corriente_perfil_pct),
        activo_no_corriente_desglose_eur=dict(empresa.activo_no_corriente_desglose_eur),
        coleccion_activos_amortizables=empresa.coleccion_activos_amortizables,
        perfil_subtipos_material_pct=dict(empresa.perfil_subtipos_material_pct),
        perfil_subtipos_intangible_pct=dict(empresa.perfil_subtipos_intangible_pct),
        tipo_interes=empresa.tipo_interes,
        existencias_perfil_pct=dict(empresa.existencias_perfil_pct),
        existencias_desglose_eur=dict(empresa.existencias_desglose_eur),
        periodificacion_activo_pct=empresa.periodificacion_activo_pct,
        periodificacion_pasivo_corto_pct=empresa.periodificacion_pasivo_corto_pct,
        periodificacion_pasivo_largo_pct=empresa.periodificacion_pasivo_largo_pct,
        deudores_perfil_pct=dict(empresa.deudores_perfil_pct),
        deudores_desglose_eur=dict(empresa.deudores_desglose_eur),
        acreedores_perfil_pct=dict(empresa.acreedores_perfil_pct),
        acreedores_desglose_eur=dict(empresa.acreedores_desglose_eur),
        deudas_fin_fraccion_total=dict(empresa.deudas_fin_fraccion_total),
        deudas_fin_fraccion_largo=dict(empresa.deudas_fin_fraccion_largo),
        deudas_fin_largo_desglose_eur=dict(empresa.deudas_fin_largo_desglose_eur),
        deudas_fin_corto_desglose_eur=dict(empresa.deudas_fin_corto_desglose_eur),
        deudas_socios_activa=empresa.deudas_socios_activa,
        otras_deudas_largo_perfil_pct=dict(empresa.otras_deudas_largo_perfil_pct),
        otras_deudas_corto_resto_perfil_pct=dict(empresa.otras_deudas_corto_resto_perfil_pct),
        otras_deudas_largo_desglose_eur=dict(empresa.otras_deudas_largo_desglose_eur),
        otras_deudas_corto_desglose_eur=dict(empresa.otras_deudas_corto_desglose_eur),
        aapp_pendiente_corto_pct=empresa.aapp_pendiente_corto_pct,
        pyg_cifra_negocios_perfil_pct=dict(empresa.pyg_cifra_negocios_perfil_pct),
        pyg_cifra_negocios_desglose_eur=dict(empresa.pyg_cifra_negocios_desglose_eur),
        pyg_consumos_explotacion_perfil_pct=dict(empresa.pyg_consumos_explotacion_perfil_pct),
        pyg_consumos_explotacion_desglose_eur=dict(empresa.pyg_consumos_explotacion_desglose_eur),
        pyg_otros_gastos_explot_perfil_pct=dict(empresa.pyg_otros_gastos_explot_perfil_pct),
        pyg_otros_gastos_explot_desglose_eur=dict(empresa.pyg_otros_gastos_explot_desglose_eur),
        pyg_gastos_personal_desglose_eur=dict(empresa.pyg_gastos_personal_desglose_eur),
        pyg_ingresos_financieros_desglose_eur=dict(empresa.pyg_ingresos_financieros_desglose_eur),
        # Cobertura/subvención: en el año base (2023) todo el estado parte de cero — Δr no
        # existe todavía (no hay "año anterior" dentro de la serie) y la subvención nunca se
        # concede en 2023 (año_concesion siempre 2024 o 2025, ver
        # motor.coberturas_subvenciones) — los valores por defecto de EjercicioEmpresa ya son
        # correctos, no hace falta pasarlos aquí explícitamente.
    )


# --------------------------------------------------------------------------------------------
# Mecanismo general: mover un ratio un intensidad_efectiva respecto a su propio valor anterior.
# --------------------------------------------------------------------------------------------


def _mover_ratio_continuo(valor_anterior: float, direccion: int, intensidad_efectiva: float, huber: float) -> float:
    """Desplaza un ratio un `intensidad_efectiva` respecto a su propio valor del año anterior,
    con suelo/techo de plausibilidad frente al Huber del sector (nunca el objetivo en sí — ver
    docstring del módulo)."""
    nuevo = valor_anterior * (1 + direccion * intensidad_efectiva)
    if direccion < 0:
        return max(nuevo, FRACCION_MINIMA_VS_HUBER * huber)
    return min(nuevo, FRACCION_MAXIMA_VS_HUBER * huber)


def _masa_circulante_objetivo(
    efecto: EfectoMasaCirculante, anterior: EjercicioEmpresa, ventas: float, fila: pd.Series, intensidad_efectiva: float
) -> float:
    huber = fila[f"{efecto.ratio_catalogo}.huber_9y"]
    if efecto.formula == "rotacion":
        if efecto.ratio_catalogo == "ratios.rotacion_existencias":
            # ACCID (docs/ratios2024.pdf) define la rotación de existencias como Consumos de
            # explotación / Existencias, NO Ventas/Existencias — el Huber/MAD del catálogo se
            # calculó sobre esa definición, así que el ancla debe moverse en ese mismo espacio
            # (ver decisiones_plausibilidad.md #71/#74: usar ventas aquí comparaba una magnitud
            # contra el Huber de otra). Los consumos de ESTE año todavía no existen en este punto
            # del pipeline (se generan después, en `_evaluar`) — se estiman proporcionales al
            # mismo crecimiento que ya se aplicó a `ventas` (incluida cualquier inorgánica de
            # adquisición), igual criterio que el resto de masas no tocadas por el arquetipo.
            base_anterior_eur = anterior.pyg_eur["consumos_explotacion"]
            base_actual_eur = base_anterior_eur * (ventas / anterior.ventas)
        else:
            base_anterior_eur = anterior.ventas
            base_actual_eur = ventas
        ratio_anterior = base_anterior_eur / anterior.balance_eur[efecto.variable]
        nuevo_ratio = _mover_ratio_continuo(ratio_anterior, efecto.direccion, intensidad_efectiva, huber)
        return base_actual_eur / nuevo_ratio
    ratio_anterior = anterior.balance_eur[efecto.variable] / anterior.ventas * DIAS_AÑO
    nuevo_ratio = _mover_ratio_continuo(ratio_anterior, efecto.direccion, intensidad_efectiva, huber)
    return nuevo_ratio / DIAS_AÑO * ventas


def _activo_no_corriente_objetivo(
    efecto: EfectoCapex, anterior: EjercicioEmpresa, ventas: float, fila: pd.Series, intensidad_efectiva: float
) -> float:
    """Mismo mecanismo que `_masa_circulante_objetivo` con formula="rotacion" (continuidad sobre
    ventas/activo_no_corriente, ancla ratios.rotacion_activo_no_corriente, no circular: no
    depende de ningún total de balance todavía sin construir) — pero es una función aparte, no
    una reutilización de EfectoMasaCirculante, porque activo_no_corriente NO participa en el
    mecanismo de déficit de NOF/circulante (ver docstring del módulo, sección "Arquetipo 17")."""
    huber = fila[f"{efecto.ratio_catalogo}.huber_9y"]
    ratio_anterior = anterior.ventas / anterior.balance_eur["activo_no_corriente"]
    nuevo_ratio = _mover_ratio_continuo(ratio_anterior, efecto.direccion, intensidad_efectiva, huber)
    return ventas / nuevo_ratio


def _evento_puntual_valor(efecto: EfectoEventoPuntual, fila: pd.Series, intensidad_base: float) -> float:
    """Magnitud del suceso puntual (arquetipo 12, "Resultado extraordinario"): NO se ancla al
    Huber de la propia primitiva (`pyg.resultado_extraordinario_pct` es ~0 con MAD pequeño en
    casi todos los sectores del catálogo — anclar ahí daría un "extraordinario" imperceptible,
    justo lo contrario de lo que pide el arquetipo). Se ancla en su lugar al Huber de
    `pyg.baii_pct` (siempre positivo en los 27 sectores del catálogo, y representa la escala de
    "beneficio operativo típico" de ese sector) — decisión estructural del mecanismo, no un dato
    de arquetipo, documentada aquí igual que SUBTOTAL_PYG_DE_PRIMITIVA. `intensidad_base` (NO
    intensidad_efectiva: sin escalar por fracción del año — ver docstring del módulo) determina
    qué fracción del BAII típico del sector representa el suceso puntual."""
    huber_baii = fila["pyg.baii_pct.huber_9y"]
    return efecto.direccion * intensidad_base * huber_baii


def _pyg_primitiva_objetivo(
    efecto: EfectoPygPrimitiva, anterior: EjercicioEmpresa, fila: pd.Series, intensidad_efectiva: float
) -> float:
    huber = fila[f"{efecto.ratio_catalogo}.huber_9y"]
    valor_anterior = anterior.pyg_pct[efecto.primitiva]
    return _mover_ratio_continuo(valor_anterior, efecto.direccion, intensidad_efectiva, huber)


def _limitar_por_subtotal(
    primitiva: str, valor_objetivo: float, fila: pd.Series, direccion: int
) -> tuple[float, str | None, float | None]:
    """Si `primitiva` alimenta un subtotal de la cascada de PyG (SUBTOTAL_PYG_DE_PRIMITIVA),
    topa `valor_objetivo` para que ESE subtotal no rebase su propio techo/suelo de
    plausibilidad sectorial (huber_9y +/- N desviaciones) — no solo el de la propia primitiva
    (que usa el Huber de otra variable del catálogo y en la práctica no acota nada realista:
    ver docstring del módulo). Solo válido para relaciones "subtotal = 100 - primitiva"
    (la única que existe hoy: margen_bruto = ingresos_explotacion(100) - consumos_explotacion).

    Devuelve (valor_final, nombre_subtotal_si_se_activó, valor_sin_contener_del_subtotal)."""
    subtotal = SUBTOTAL_PYG_DE_PRIMITIVA.get(primitiva)
    if subtotal is None:
        return valor_objetivo, None, None

    huber_subtotal = fila[f"pyg.{subtotal}_pct.huber_9y"]
    mad_subtotal = fila[f"pyg.{subtotal}_pct.huber_scale_mad"]
    subtotal_sin_contener = 100.0 - valor_objetivo

    if direccion < 0:
        # La primitiva baja => el subtotal (100 - primitiva) sube: topar el subtotal a su
        # techo equivale a ponerle un SUELO a la propia primitiva.
        techo_subtotal = huber_subtotal + N_DESVIACIONES_TECHO_PYG * mad_subtotal
        if subtotal_sin_contener <= techo_subtotal:
            return valor_objetivo, None, None
        return 100.0 - techo_subtotal, subtotal, subtotal_sin_contener
    else:
        suelo_subtotal = huber_subtotal - N_DESVIACIONES_TECHO_PYG * mad_subtotal
        if subtotal_sin_contener >= suelo_subtotal:
            return valor_objetivo, None, None
        return 100.0 - suelo_subtotal, subtotal, subtotal_sin_contener


def _limitar_gastos_personal_por_baii(
    parcial: "_PygParcial", gastos_personal_pct_sin_empuje: float, fila: pd.Series, direccion: int
) -> tuple["_PygParcial", bool, float | None, bool]:
    """Equivalente de `_limitar_por_subtotal` para la relación de "base dinámica"
    gastos_personal -> baii (arquetipo 10, "mejora de EBITDA"): a diferencia de margen_bruto,
    baii no es "100 - primitiva" (depende también de valor_añadido, amortizaciones y
    resultado_extraordinario, ya sorteados en `parcial`, con ruido propio cada año e
    independiente del arquetipo), así que no se puede topar antes de generar la PyG — se corrige
    DESPUÉS, de forma analítica (baii es lineal en gastos_personal, coeficiente -1).

    Amortigua la intensidad del propio arquetipo antes de invertir su sentido — igual que la
    contención de masa_circulante en los arquetipos 1/3/4/6 nunca amortigua por debajo del
    crecimiento proporcional a ventas. `gastos_personal_pct_sin_empuje` es el equivalente aquí a
    "intensidad cero": el valor que tendría gastos_personal_pct SIN ningún empuje del arquetipo
    ese año (igual al del año anterior). Al resolver directamente "baii = techo/suelo" (baii es
    lineal en gastos_personal, la solución es única), el resultado cae automáticamente entre el
    objetivo sin contener y `gastos_personal_pct_sin_empuje` — una amortiguación pura, sin
    invertir el sentido — SALVO que incluso con la intensidad amortiguada a cero
    (`gastos_personal_pct_sin_empuje` tal cual) ya se rebasara el techo/suelo: en ese caso el
    desbordamiento viene del ruido propio de la base ese año (valor_añadido, amortizaciones,
    resultado_extraordinario), no del arquetipo, y no hay forma de resolverlo sin invertir el
    sentido — se señaliza aparte (`limite_por_ruido_base=True`), igual que la limitación
    documentada y aceptada del arquetipo 15. Verificado en pruebas de estrés (648 ejercicios,
    316 activaciones): 173 (54,7%) se resuelven amortiguando sin invertir el sentido, 143
    (45,3%) sí lo invierten — y en las 648 evaluaciones, la predicción de qué grupo le toca a
    cada caso comprobando solo si `gastos_personal_pct_sin_empuje` ya rebasa el techo/suelo
    coincide EXACTAMENTE con el resultado real de la corrección — 0 discrepancias.

    Devuelve (parcial corregido o el mismo si no hacía falta, si se activó el techo/suelo, valor
    de baii_pct sin contener, si el límite vino del ruido de base -> invirtió el sentido)."""
    huber_baii = fila["pyg.baii_pct.huber_9y"]
    mad_baii = fila["pyg.baii_pct.huber_scale_mad"]
    baii_pct_sin_contener = parcial.baii_eur / parcial.ingresos_explotacion_eur * 100

    if direccion < 0:
        # gastos_personal baja => baii sube: el riesgo es rebasar el TECHO de baii_pct.
        limite_baii_pct = huber_baii + N_DESVIACIONES_TECHO_PYG * mad_baii
        if baii_pct_sin_contener <= limite_baii_pct:
            return parcial, False, None, False
    else:
        # gastos_personal sube => baii baja: el riesgo es perforar el SUELO de baii_pct.
        limite_baii_pct = huber_baii - N_DESVIACIONES_TECHO_PYG * mad_baii
        if baii_pct_sin_contener >= limite_baii_pct:
            return parcial, False, None, False

    baii_eur_corregido = limite_baii_pct / 100 * parcial.ingresos_explotacion_eur
    gastos_personal_eur_corregido = (
        parcial.valor_añadido_eur - baii_eur_corregido - parcial.amortizaciones_eur + parcial.resultado_extraordinario_eur
    )

    gastos_personal_eur_sin_empuje = gastos_personal_pct_sin_empuje / 100 * parcial.ingresos_explotacion_eur
    if direccion < 0:
        limite_por_ruido_base = gastos_personal_eur_corregido > gastos_personal_eur_sin_empuje
    else:
        limite_por_ruido_base = gastos_personal_eur_corregido < gastos_personal_eur_sin_empuje

    parcial_corregido = replace(parcial, gastos_personal_eur=gastos_personal_eur_corregido, baii_eur=baii_eur_corregido)
    return parcial_corregido, True, baii_pct_sin_contener, limite_por_ruido_base


def _disponible_proporcional_con_efecto(
    efecto: EfectoTesoreria | None, disponible_proporcional_eur: float, intensidad_efectiva: float
) -> float:
    if efecto is None:
        return disponible_proporcional_eur
    factor = max(0.0, 1 + efecto.direccion * intensidad_efectiva)
    return disponible_proporcional_eur * factor


@dataclass(frozen=True)
class ParametrosGrupo89:
    """Parámetros de cobertura/subvención sorteados UNA vez por caso (no por año) — ver
    `generar_evolucion_combinada`, que los calcula, y `motor/coberturas_subvenciones.py`, que
    define los rangos. `subvencion_via_capex17` y `subvencion_baseline_activa` son mutuamente
    excluyentes por diseño (ver docstring de `_evolucionar_un_año`, sección subvención): nunca
    ambas ni ninguna "por suerte" si el arquetipo 17 está activo en el caso."""

    cobertura_activa: bool = False
    cobertura_pct_deuda: float = 0.0
    cobertura_plazo_residual_inicial_años: float = 0.0
    cobertura_eficacia_pct: float = 0.0
    subvencion_via_capex17: bool = False
    subvencion_baseline_activa: bool = False
    subvencion_baseline_año_concesion: int | None = None
    subvencion_pct_cofinanciacion: float = 0.0


PARAMETROS_GRUPO89_INACTIVOS = ParametrosGrupo89()


# --------------------------------------------------------------------------------------------
# Operaciones vinculadas (arquetipo 20) — segundo lote de desglose de balance. Las constantes de
# rango/suelo vivían antes en motor/memoria.py; se trasladan aquí (única fuente de verdad) porque
# motor.memoria NO puede importarse desde este módulo (importaría en círculo: motor.memoria ya
# importa EjercicioEmpresa/NotaMemoria de aquí) y el sorteo ahora tiene que alimentar el balance,
# no solo el texto de la nota — motor.memoria importa estas constantes DE AQUÍ.
# --------------------------------------------------------------------------------------------
RANGOS_IMPORTE_VINCULADAS_PCT: dict[str, tuple[float, float]] = {"leve": (2, 5), "moderado": (5, 10), "fuerte": (10, 18)}
SUELO_IMPORTE_VINCULADAS_EUR = 30_000.0

# Las 5 operaciones del arquetipo 20 (mismo orden que `_OPERACIONES_VINCULADAS` en
# motor/memoria.py — el índice sorteado aquí selecciona la misma plantilla de texto allí, ver
# `_sortear_operacion_vinculada`), clasificadas comercial/financiera/"no es realmente grupo" tras
# revisar los 5 textos uno a uno (clasificación aprobada por el usuario antes de implementar):
#   0. "Préstamo intragrupo A la matriz" (la sociedad presta, no toma prestado) — FINANCIERA,
#      lado ACTIVO: "Inversiones en empresas del grupo y asociadas a largo plazo" (masa nueva).
#   1. "Facturación de servicios de gestión a una sociedad del grupo" — COMERCIAL, lado ACTIVO:
#      "Clientes, empresas del grupo y asociadas" (sub-partida de deudores comerciales).
#   2. "Arrendamiento pagado a un socio/administrador" — NO es "empresas del grupo" en sentido
#      PGC (un socio/administrador no lo es necesariamente): "Acreedores varios" (sub-partida de
#      acreedores comerciales, no la línea de grupo).
#   3. "Financiación recibida de una sociedad del grupo" — FINANCIERA, lado PASIVO: "Deudas con
#      empresas del grupo y asociadas a largo plazo" (masa nueva) — el propio texto de la nota
#      excluye gastos financieros adicionales, así que esta masa NUNCA entra en deudas_fin_largo/
#      corto (las únicas que alimentan gastos_financieros = deuda_financiera_media x tipo_interes).
#   4. "Asistencia técnica y administrativa prestada POR la matriz" (la sociedad recibe el
#      servicio, lo debe) — COMERCIAL, lado PASIVO: "Proveedores, empresas del grupo y
#      asociadas" (sub-partida de acreedores comerciales).
TIPO_OPERACION_POR_INDICE: tuple[str, ...] = (
    "prestamo_matriz",
    "facturacion_servicios_grupo",
    "arrendamiento_socio",
    "financiacion_recibida_grupo",
    "asistencia_tecnica_matriz",
)
# Magnitud de referencia de cada tipo — ventas, patrimonio neto o deuda financiera total.
MAGNITUD_REFERENCIA_POR_TIPO: dict[str, str] = {
    "prestamo_matriz": "patrimonio_neto",
    "facturacion_servicios_grupo": "ventas",
    "arrendamiento_socio": "ventas",
    "financiacion_recibida_grupo": "deuda_financiera",
    "asistencia_tecnica_matriz": "ventas",
}
# A qué componente del desglose de deudores/acreedores aterriza cada tipo COMERCIAL/"varios" (los
# 2 tipos FINANCIEROS no tocan ningún desglose existente, son masas propias nuevas).
COMPONENTE_DESGLOSE_POR_TIPO: dict[str, tuple[str, str]] = {
    "facturacion_servicios_grupo": ("deudores", "clientes_empresas_grupo"),
    "arrendamiento_socio": ("acreedores", "acreedores_varios"),
    "asistencia_tecnica_matriz": ("acreedores", "proveedores_empresas_grupo"),
}
# Techos defensivos — protegen el cuadre (ningún componente queda negativo), rara vez activos en
# la práctica: RANGOS_IMPORTE_VINCULADAS_PCT topa en 18% de la magnitud de REFERENCIA (ventas/PN/
# deuda financiera), que normalmente es una fracción moderada de la masa/caja que la contiene.
TECHO_FRACCION_MASA_OPERACION_VINCULADA = 0.6
TECHO_FRACCION_DISPONIBLE_PRESTAMO_MATRIZ = 0.9


@dataclass(frozen=True)
class ParametrosOperacionVinculada:
    """Parámetros de la operación vinculada (arquetipo 20) sorteados UNA vez por caso (no por
    año) — mismo criterio que `ParametrosGrupo89`. `indice`/`pct_objetivo` se sortean con la
    MISMA secuencia de `rng` (misma entropía, mismos dos draws en el mismo orden) que usaba antes
    `motor.memoria.generar_nota_operaciones_vinculadas` — ver `_sortear_operacion_vinculada` — así
    que el resultado es IDÉNTICO al que esa función elegía, sin sortear nada dos veces (la nota,
    ahora en motor.memoria, se limita a formatear el importe ya aterrizado en el balance, ver
    `EjercicioEmpresa.operacion_vinculada_importe_eur`)."""

    activa: bool = False
    indice: int = -1
    tipo_operacion: str = ""
    pct_objetivo: float = 0.0  # fracción (NO %) de la magnitud de referencia de `tipo_operacion`


PARAMETROS_OPERACION_VINCULADA_INACTIVOS = ParametrosOperacionVinculada()
PARAMETROS_PROVISION_INACTIVA = ParametrosProvision()
PARAMETROS_INSOLVENCIA_INACTIVA = ParametrosInsolvencia()


def _sortear_operacion_vinculada(sector: str, segmento: str, semilla: int, intensidad: str) -> ParametrosOperacionVinculada:
    """Réplica EXACTA de la secuencia de sorteo que usaba `motor.memoria.
    generar_nota_operaciones_vinculadas` antes de este encargo (mismo hash de entropía, mismo
    `rng.permutation` para el índice, mismo `rng.uniform` para el %) — no es un sorteo nuevo, es
    el mismo trasladado aquí para que la magnitud pueda alimentar el balance, no solo el texto de
    la nota. El índice no depende de `etiquetas_ya_usadas`: las 5 plantillas de
    operaciones_vinculadas llevan la MISMA etiqueta fija (ver `_elegir_indice_evitando_colision`
    en motor/memoria.py), así que la resolución de colisiones nunca cambia cuál se elige —
    siempre el primero del `rng.permutation` barajado, verificado en el propio código de esa
    función (bucle que, con etiquetas idénticas para las 5, siempre devuelve `orden[0]`)."""
    entropia = zlib.crc32(f"{sector}|{segmento}|{intensidad}|operaciones_vinculadas".encode("utf-8"))
    rng = np.random.default_rng([semilla, entropia])
    indice = int(rng.permutation(len(TIPO_OPERACION_POR_INDICE))[0])
    pct_objetivo = rng.uniform(*RANGOS_IMPORTE_VINCULADAS_PCT[intensidad]) / 100
    return ParametrosOperacionVinculada(
        activa=True, indice=indice, tipo_operacion=TIPO_OPERACION_POR_INDICE[indice], pct_objetivo=pct_objetivo,
    )


def _magnitud_operacion_vinculada(ventas: float, balance_eur: dict[str, float], tipo_operacion: str) -> float:
    """Magnitud de referencia de `tipo_operacion` — ventas, patrimonio neto o deuda financiera
    total —, leída de un `ventas`/`balance_eur` YA resueltos (de cualquier año, propio o
    anterior según el llamador)."""
    nombre = MAGNITUD_REFERENCIA_POR_TIPO[tipo_operacion]
    if nombre == "ventas":
        return ventas
    if nombre == "patrimonio_neto":
        return balance_eur["patrimonio_neto"]
    return balance_eur["deudas_fin_largo"] + balance_eur["deudas_fin_corto"]


def _perfil_con_componente_forzado(perfil_base: dict[str, float], componente: str, fraccion_objetivo: float) -> dict[str, float]:
    """Fuerza `componente` de `perfil_base` (que suma 1.0) a `fraccion_objetivo` (topada a
    `TECHO_FRACCION_MASA_OPERACION_VINCULADA`) y reescala el RESTO proporcionalmente entre sí
    para que la suma siga siendo exactamente 1.0 — usado UNA vez, en el año base, para fijar
    "desde 2023" el perfil de deudores/acreedores cuando el arquetipo 20 activa una operación
    comercial concreta (ver `generar_evolucion_combinada`); a partir de ahí sigue el mismo
    patrón que cualquier otro perfil de este bloque (fijo, desglose recalculado cada año)."""
    fraccion_objetivo = min(fraccion_objetivo, TECHO_FRACCION_MASA_OPERACION_VINCULADA)
    resto_objetivo = 1.0 - fraccion_objetivo
    resto_base = 1.0 - perfil_base[componente]
    factor = resto_objetivo / resto_base if resto_base > 0 else 0.0
    return {clave: (fraccion_objetivo if clave == componente else valor * factor) for clave, valor in perfil_base.items()}


def _importe_operacion_vinculada_eur(
    tipo_operacion: str,
    deudores_desglose_eur: dict[str, float],
    acreedores_desglose_eur: dict[str, float],
    inversion_grupo_largo_eur: float,
    deuda_grupo_largo_eur: float,
) -> float:
    """El importe YA aterrizado en el balance de este año para `tipo_operacion` — el mismo que
    debe citar la nota de memoria (motor/memoria.py), nunca un número sorteado aparte."""
    if tipo_operacion == "prestamo_matriz":
        return inversion_grupo_largo_eur
    if tipo_operacion == "financiacion_recibida_grupo":
        return deuda_grupo_largo_eur
    if tipo_operacion in COMPONENTE_DESGLOSE_POR_TIPO:
        desglose_nombre, componente = COMPONENTE_DESGLOSE_POR_TIPO[tipo_operacion]
        desglose = deudores_desglose_eur if desglose_nombre == "deudores" else acreedores_desglose_eur
        return desglose[componente]
    return 0.0


def _evolucionar_un_año(
    año: int,
    anterior: EjercicioEmpresa,
    fila: pd.Series,
    rng_pyg: np.random.Generator,
    rng_nota: np.random.Generator,
    crecimiento_ventas: float,
    año_evento_puntual: int | None,
    efectos_activos: tuple[EfectoActivo, ...],
    sector: str,
    segmento: str,
    semilla: int,
    parametros_grupo89: ParametrosGrupo89 = PARAMETROS_GRUPO89_INACTIVOS,
    parametros_operacion_vinculada: ParametrosOperacionVinculada = PARAMETROS_OPERACION_VINCULADA_INACTIVOS,
    parametros_provision: ParametrosProvision = PARAMETROS_PROVISION_INACTIVA,
    parametros_insolvencia: ParametrosInsolvencia = PARAMETROS_INSOLVENCIA_INACTIVA,
    payout_caso: float = 0.0,
    deterioro_ciclo_caja_activo: bool = False,
    dependencia_pocos_clientes_activo: bool = False,
) -> EjercicioEmpresa:
    """`efectos_activos` ya viene fusionado (uno o varios arquetipos combinados, cada `Efecto`
    emparejado con la intensidad de SU PROPIO arquetipo de origen, y los `masa_circulante` que
    comparten variable+dirección ya sumados en uno solo) — ver `generar_evolucion_combinada` y
    la sección "Combinación de arquetipos" del docstring del módulo. El caso de un único
    arquetipo es, literalmente, una lista de un elemento: esta función no distingue los dos
    casos en ningún punto."""
    ventas = anterior.ventas * (1 + crecimiento_ventas)

    efectos_masa_circulante = [ea for ea in efectos_activos if isinstance(ea.efecto, EfectoMasaCirculante)]
    efectos_pyg = [ea for ea in efectos_activos if isinstance(ea.efecto, EfectoPygPrimitiva)]
    efectos_apalancamiento = [ea for ea in efectos_activos if isinstance(ea.efecto, EfectoApalancamiento)]
    efectos_tesoreria = [ea for ea in efectos_activos if isinstance(ea.efecto, EfectoTesoreria)]
    ea_tesoreria = efectos_tesoreria[0] if efectos_tesoreria else None
    efectos_reclasificacion_deuda = [ea for ea in efectos_activos if isinstance(ea.efecto, EfectoReclasificacionDeuda)]
    efectos_evento_puntual = [ea for ea in efectos_activos if isinstance(ea.efecto, EfectoEventoPuntual)]
    efectos_capex = [ea for ea in efectos_activos if isinstance(ea.efecto, EfectoCapex)]
    efectos_adquisicion = [ea for ea in efectos_activos if isinstance(ea.efecto, EfectoAdquisicion)]
    notas_memoria: list[NotaMemoria] = []

    # --- Adquisición (arquetipo 18): inyección exógena de activo_no_corriente Y de ventas
    # "inorgánicas", ambas SOLO en AÑO_ADQUISICION (2024, fijo — ver constante). La magnitud se
    # calcula ANTES de que `ventas` se use en el resto de la función (masas de circulante, PyG),
    # así que todo lo que crece "proporcional a ventas" ya incluye la aportación de la unidad
    # adquirida — decisión deliberada: el modelo no separa el circulante propio de la unidad
    # adquirida (la huella de la sección 2.24 no lo pide), una empresa combinada más grande
    # necesita más circulante en conjunto, venga la venta de donde venga. `ventas_organicas_eur`
    # (lo que habrían sido las ventas SIN la operación) queda registrado aparte para que el
    # resultado exponga el desglose que pide la guía docente (ficha 18). ---
    incremento_activo_adquisicion_eur = 0.0
    ventas_organicas_eur: float | None = None
    ventas_inorganicas_eur: float | None = None
    ea_adquisicion = efectos_adquisicion[0] if efectos_adquisicion else None
    if ea_adquisicion is not None and año == AÑO_ADQUISICION:
        activo_total_previo_eur = anterior.balance_eur["activo_no_corriente"] + anterior.balance_eur["activo_corriente"]
        incremento_activo_adquisicion_eur = ea_adquisicion.intensidad_base * activo_total_previo_eur
        # La aportación de ventas de la unidad adquirida se ancla a ratios.rotacion_activo del
        # sector (ventas/activo total típico) sobre el propio importe adquirido — asume que la
        # unidad comprada opera con una eficiencia de activo similar a la del sector, en vez de
        # un número de ventas arbitrario y desconectado del tamaño de la operación.
        huber_rotacion_activo = fila["ratios.rotacion_activo.huber_9y"]
        ventas_organicas_eur = ventas
        ventas_inorganicas_eur = incremento_activo_adquisicion_eur * huber_rotacion_activo
        ventas = ventas_organicas_eur + ventas_inorganicas_eur

    # --- Masas de circulante: proporcional a ventas por defecto, desviadas si el arquetipo
    # las toca. Las tres variables soportadas (SIGNO_NOF_MASA_CIRCULANTE) se tratan siempre
    # igual, tocadas o no por el arquetipo: solo cambia si objetivos_circulante coincide o no
    # con proporcional_circulante para esa variable. ---
    variables_circulante = {variable: anterior.balance_eur[variable] for variable in SIGNO_NOF_MASA_CIRCULANTE}
    proporcional_circulante = {
        variable: valor * (1 + crecimiento_ventas) for variable, valor in variables_circulante.items()
    }
    objetivos_circulante = dict(proporcional_circulante)
    for ea in efectos_masa_circulante:
        objetivos_circulante[ea.efecto.variable] = _masa_circulante_objetivo(
            ea.efecto, anterior, ventas, fila, ea.intensidad_efectiva
        )
    existencias_eur = objetivos_circulante["existencias"]
    realizable_eur = objetivos_circulante["realizable"]
    acreedores_comerciales_eur = objetivos_circulante["acreedores_comerciales"]
    existencias_proporcional_eur = proporcional_circulante["existencias"]
    realizable_proporcional_eur = proporcional_circulante["realizable"]
    acreedores_comerciales_proporcional_eur = proporcional_circulante["acreedores_comerciales"]

    # --- Resto de masas: crecen en línea con las ventas (patrimonio neto se trata aparte) ---
    # Cobertura/subvención (grupo 8/9, ver motor/coberturas_subvenciones.py): el derivado de la
    # cobertura (si es activo) y el activo por impuesto diferido son valoraciones a mercado, no
    # partidas que deban crecer proporcional a ventas de un año a otro — se excluyen de la base
    # proporcional y se añaden después como un NIVEL ya recalculado de este año (igual criterio
    # en el lado del pasivo con `otras_deudas_largo_eur`). Si no hay grupo89 activo, esto es 0 y
    # no cambia nada del comportamiento anterior. El derivado, cuando es PASIVO, ya NO vive en
    # `otras_deudas_largo` desde el cuarto lote de desglose de balance (ver más abajo, "Deudas
    # financieras") — así que `anterior_pasivo_grupo89_eur` deja de excluirlo aquí; su exclusión
    # equivalente para la base de `deudas_fin_largo_proporcional_eur` está justo debajo.
    anterior_activo_grupo89_eur = max(0.0, anterior.cobertura_valor_swap_eur) + anterior.activos_por_impuesto_diferido_eur
    anterior_pasivo_grupo89_eur = anterior.pasivos_por_impuesto_diferido_eur

    activo_no_corriente_proporcional_eur = (
        anterior.balance_eur["activo_no_corriente"] - anterior_activo_grupo89_eur
    ) * (1 + crecimiento_ventas)
    activo_no_corriente_eur = activo_no_corriente_proporcional_eur
    if efectos_capex:
        ea_capex = efectos_capex[0]
        activo_no_corriente_eur = _activo_no_corriente_objetivo(
            ea_capex.efecto, anterior, ventas, fila, ea_capex.intensidad_efectiva
        )
    # Excluye el derivado del año anterior (si era pasivo) de la base CON COSTE — mismo criterio
    # que `deuda_financiera_inicio_eur` más abajo: una valoración a mercado no debe componerse
    # como si fuera principal prestado. Se pliega de nuevo al año, ya recalculado, en
    # `_construir_balance` (ver bloque "Deudas financieras" más abajo).
    deudas_fin_largo_proporcional_eur = (
        anterior.balance_eur["deudas_fin_largo"] - max(0.0, -anterior.cobertura_valor_swap_eur)
    ) * (1 + crecimiento_ventas)
    # Provisiones (tercer lote de desglose de balance): excluidas de la base proporcional, igual
    # criterio que grupo89 — no crecen con ventas, se recalculan cada año desde su propio saldo
    # (ver bloque "Provisiones" más abajo, que las vuelve a sumar tras este punto).
    otras_deudas_largo_eur = (
        anterior.balance_eur["otras_deudas_largo"] - anterior_pasivo_grupo89_eur - anterior.provision_saldo_largo_eur
    ) * (1 + crecimiento_ventas)
    otras_deudas_corto_eur = (anterior.balance_eur["otras_deudas_corto"] - anterior.provision_saldo_corto_eur) * (
        1 + crecimiento_ventas
    )
    deudas_fin_corto_proporcional_eur = anterior.balance_eur["deudas_fin_corto"] * (1 + crecimiento_ventas)
    disponible_proporcional_eur = _disponible_proporcional_con_efecto(
        ea_tesoreria.efecto if ea_tesoreria else None,
        anterior.balance_eur["disponible"] * (1 + crecimiento_ventas),
        ea_tesoreria.intensidad_efectiva if ea_tesoreria else 0.0,
    )
    # Excluye el derivado del año anterior (si era pasivo) de la base "con coste" — desde el
    # cuarto lote de desglose de balance, `anterior.balance_eur["deudas_fin_largo"]` YA incluye
    # el derivado (ver `_construir_balance`, bloque "Deudas financieras" más abajo): sin esta
    # exclusión, `deuda_financiera_inicio_eur` cargaría interés sobre una valoración a mercado
    # que no es principal prestado.
    deuda_financiera_inicio_eur = (
        anterior.balance_eur["deudas_fin_largo"] - max(0.0, -anterior.cobertura_valor_swap_eur) + anterior.balance_eur["deudas_fin_corto"]
    )

    # --- Reclasificación de deuda (arquetipo 8 "refinanciación"): mueve deuda financiera entre
    # largo y corto plazo SIN alterar el total (una renegociación cambia el vencimiento, no el
    # importe) — reasigna deudas_fin_largo/corto_proporcional_eur antes de que se usen más
    # abajo. Ver EfectoReclasificacionDeuda en motor/arquetipos.py y el docstring del módulo. ---
    if efectos_reclasificacion_deuda:
        ea_reclas = efectos_reclasificacion_deuda[0]
        efecto_reclas = ea_reclas.efecto
        deuda_financiera_total_proporcional_eur = deudas_fin_largo_proporcional_eur + deudas_fin_corto_proporcional_eur
        # NOTA (decisiones_plausibilidad.md #71/#74/#76): este ancla usa deudas_fin_largo/deuda_
        # financiera_total, que NO es la definición ACCID de `ratios.calidad_deuda` (Pasivo
        # corriente/Deudas totales) contra la que se compara su Huber/MAD — discrepancia conocida,
        # documentada, NO corregida todavía. La versión fiel a ACCID (#74) se descartó por
        # saturación estructural; el intento de recalibrar su intensidad (#76) reveló que
        # `ratios.calidad_deuda` YA tiene un suelo estructural de ruido de base (~24-25% incluso
        # con intensidad de arquetipo ≈0, confirmado idéntico bajo un arquetipo que no la toca en
        # absoluto — mismo fenómeno del hallazgo mayor de #73/#75, "paseo aleatorio" del PN vía el
        # plug de cuadre) — no se puede calibrar "leve" a un rango razonable de forma aislada
        # mientras ese hallazgo siga sin resolver. Revertido de nuevo a la fórmula anterior;
        # pendiente de retomar #76 una vez decidido el abordaje de #75.
        deuda_financiera_anterior_eur = anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"]
        calidad_deuda_anterior = (
            anterior.balance_eur["deudas_fin_largo"] / deuda_financiera_anterior_eur
            if deuda_financiera_anterior_eur > 0
            else 0.0
        )
        huber_calidad_deuda = fila[f"{efecto_reclas.ratio_catalogo}.huber_9y"]
        calidad_deuda_objetivo = _mover_ratio_continuo(
            calidad_deuda_anterior, efecto_reclas.direccion, ea_reclas.intensidad_efectiva, huber_calidad_deuda
        )
        calidad_deuda_objetivo = min(max(calidad_deuda_objetivo, 0.0), 1.0)  # calidad_deuda es un ratio en [0,1]
        deudas_fin_largo_proporcional_eur = calidad_deuda_objetivo * deuda_financiera_total_proporcional_eur
        deudas_fin_corto_proporcional_eur = deuda_financiera_total_proporcional_eur - deudas_fin_largo_proporcional_eur

        if efecto_reclas.direccion < 0:
            # Arquetipo 16 ("riesgo de refinanciación"): empeora la calidad de la deuda cada año
            # que actúa (no es un caso límite raro como en el arquetipo 10 — es la huella
            # habitual del propio arquetipo) — cobertura narrativa reproducible, mismo patrón que
            # NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE (rng_nota dedicado, ver ahí por qué no
            # basta con reutilizar rng_pyg).
            indice_nota = rng_nota.integers(len(NOTAS_MEMORIA_RIESGO_REFINANCIACION))
            texto, etiquetas = NOTAS_MEMORIA_RIESGO_REFINANCIACION[indice_nota]
            notas_memoria.append(NotaMemoria(arquetipo_id=ea_reclas.arquetipo_id, numero=ea_reclas.numero, texto=texto, etiquetas=etiquetas))

    # --- Capex (arquetipo 17, "capex elevado"): el exceso de activo_no_corriente sobre su
    # crecimiento proporcional a ventas se financia con deuda a largo plazo NUEVA, no con el
    # circulante — a diferencia de una masa_circulante, invertir en inmovilizado no genera un
    # déficit de caja del ejercicio que haya que cubrir con tesorería o deuda a CORTO (esa es la
    # fuente típica de financiación de circulante, no de capex); la fuente típica de financiación
    # de capex es deuda a LARGO plazo (o ampliación de capital/autofinanciación, no modeladas
    # aquí). A diferencia del efecto "apalancamiento" (arquetipo 9), esta deuda nueva NO financia
    # una distribución a PN: financia la COMPRA del propio activo, así que no se resta nada de
    # patrimonio_neto — el activo y el pasivo suben exactamente lo mismo, sin romper el cuadre.
    exceso_capex_eur = 0.0
    if efectos_capex:
        exceso_capex_eur = max(0.0, activo_no_corriente_eur - activo_no_corriente_proporcional_eur)
        deudas_fin_largo_proporcional_eur += exceso_capex_eur

    # --- Adquisición (arquetipo 18): el importe adquirido (incremento_activo_adquisicion_eur,
    # calculado al principio de la función) se suma a activo_no_corriente y se financia primero
    # con la caja disponible ese año y, lo que no cubra, con deuda a largo plazo NUEVA — mismo
    # orden de prioridad ("caja primero, deuda después") que ya usa _deficit_y_deuda_corto para
    # el déficit de NOF, pero aquí la deuda va a LARGO (una compra de inmovilizado, no un déficit
    # de circulante) en vez de a corto. Igual que en "capex", no se resta nada de patrimonio_neto
    # (financia la compra del propio activo, no una distribución) — el activo y el pasivo (o la
    # caja) se mueven exactamente lo mismo, sin romper el cuadre. La nota de memoria es
    # OBLIGATORIA aquí (a diferencia del resto de usos de `nota_memoria`): se genera siempre que
    # el efecto esté activo ese año, porque el arquetipo consiste precisamente en una operación
    # que la memoria debe explicar.
    if incremento_activo_adquisicion_eur > 0:
        activo_no_corriente_eur += incremento_activo_adquisicion_eur
        aportacion_caja_adquisicion_eur = min(disponible_proporcional_eur, incremento_activo_adquisicion_eur)
        disponible_proporcional_eur -= aportacion_caja_adquisicion_eur
        deuda_nueva_adquisicion_eur = incremento_activo_adquisicion_eur - aportacion_caja_adquisicion_eur
        deudas_fin_largo_proporcional_eur += deuda_nueva_adquisicion_eur
        indice_nota = rng_nota.integers(len(NOTAS_MEMORIA_ADQUISICION))
        texto, etiquetas = NOTAS_MEMORIA_ADQUISICION[indice_nota]
        notas_memoria.append(NotaMemoria(arquetipo_id=ea_adquisicion.arquetipo_id, numero=ea_adquisicion.numero, texto=texto, etiquetas=etiquetas))

    # --- Amortización derivada de una colección real de activos (motor/amortizacion.py) —
    # arreglo de raíz, no un parche: el gasto de la PyG ya no se sortea como % independiente. La
    # colección de ESTE año es la del año anterior (las cohortes del año base no cambian de
    # valor — solo se reevalúa la misma fórmula continua en un año distinto, ver `SubLoteActivo.
    # acumulada_en`) más las cohortes NUEVAS que genere el capex (17) o la adquisición (18) de
    # ESTE año concreto, si los hay — con `año_ancla` = este año, sin sorteo de fecha/ya-
    # amortizado (activos recién comprados). ---
    # --- Bajas anticipadas de sub-lotes (línea 11 PGC, "Deterioro y resultado por
    # enajenaciones del inmovilizado") — motor/amortizacion.py, mecanismo aprobado explícitamente
    # por el usuario. Se sortean sobre la colección YA EXISTENTE al empezar el año (nunca sobre
    # las cohortes nuevas de capex/adquisición de este mismo año, añadidas más abajo) para que un
    # activo recién comprado no pueda darse de baja el mismo año en que se compra. ---
    bajas_este_año = sortear_bajas_del_año(sector, segmento, semilla, anterior.coleccion_activos_amortizables, año)

    coleccion_activos_amortizables = anterior.coleccion_activos_amortizables
    cohortes_capex_este_año: tuple = ()
    if exceso_capex_eur > 0:
        cohortes_capex_este_año = generar_cohortes_capex(sector, segmento, semilla, año, exceso_capex_eur)
        coleccion_activos_amortizables += cohortes_capex_este_año
    if incremento_activo_adquisicion_eur > 0:
        categoria = categoria_de_sector(sector)
        coleccion_activos_amortizables += generar_cohortes_adquisicion(
            sector, segmento, semilla, año, incremento_activo_adquisicion_eur, categoria,
            anterior.activo_no_corriente_perfil_pct, anterior.perfil_subtipos_material_pct, anterior.perfil_subtipos_intangible_pct,
        )

    # --- Subvención de capital pendiente de imputar (transversal, ver
    # motor/coberturas_subvenciones.py) — disparada por el arquetipo 17 ("capex elevado") como
    # vía principal, ligada a la MISMA cohorte que ya genera el capex de este año (no se crea
    # una cohorte duplicada): se concede una única vez, en 2024, sobre el primer exceso de
    # capex del caso (simplificación deliberada y documentada — un capex_elevado que siga
    # generando exceso en 2025 no genera una segunda subvención). Si el caso NO tiene el 17
    # activo, se evalúa en su lugar la probabilidad de fondo (sorteada una única vez por caso en
    # `generar_evolucion_combinada`, mutuamente excluyente con la vía "17" — ver
    # ParametrosGrupo89). ---
    subvencion_activo_asociado = anterior.subvencion_activo_asociado
    subvencion_importe_concedido_eur = 0.0
    subvencion_pct_cofinanciacion = anterior.subvencion_pct_cofinanciacion
    if parametros_grupo89.subvencion_via_capex17 and año == 2024 and exceso_capex_eur > 0:
        subvencion_pct_cofinanciacion = sortear_pct_cofinanciacion(sector, segmento, semilla)
        subvencion_activo_asociado = cohortes_capex_este_año
        subvencion_importe_concedido_eur = subvencion_pct_cofinanciacion * exceso_capex_eur
    elif (
        parametros_grupo89.subvencion_baseline_activa
        and not parametros_grupo89.subvencion_via_capex17
        and año == parametros_grupo89.subvencion_baseline_año_concesion
    ):
        subvencion_pct_cofinanciacion = sortear_pct_cofinanciacion(sector, segmento, semilla)
        capex_baseline_eur = capex_subvencionable_baseline_eur(
            sector, segmento, semilla, anterior.balance_eur["activo_no_corriente"]
        )
        subvencion_activo_asociado = generar_activo_subvencionado(sector, segmento, semilla, año, capex_baseline_eur)
        coleccion_activos_amortizables += subvencion_activo_asociado
        subvencion_importe_concedido_eur = subvencion_pct_cofinanciacion * capex_baseline_eur

    paso_subvencion = evolucionar_subvencion(anterior.subvencion_saldo_130_bruto_eur, subvencion_activo_asociado, año)
    subvencion_saldo_130_bruto_eur = paso_subvencion.saldo_130_bruto_eur + subvencion_importe_concedido_eur
    subvencion_transferencia_bruto_eur = paso_subvencion.transferencia_bruto_eur

    amortizacion_eur_año = amortizacion_eur_del_año(coleccion_activos_amortizables, año)
    # Las bajas de este año ya cargaron su cuota completa en `amortizacion_eur_año` de arriba
    # (colección todavía sin excluir) — se retiran AHORA, de cara al año SIGUIENTE, ver
    # docstring de `excluir_bajas`.
    coleccion_activos_amortizables = excluir_bajas(coleccion_activos_amortizables, bajas_este_año)

    # --- Efecto de las bajas sobre balance y caja (Restricciones del encargo): el valor en
    # libros de las bajas reduce `activo_no_corriente` (deja de existir como activo); el precio
    # de venta de las que fueron enajenación (0.0 si fue deterioro puro) entra como caja real —
    # mismo patrón que adquisición (18) en reversa (allí la caja se USA, aquí se RECIBE). El
    # `max(0.0, ...)` es una salvaguarda estructural (ver verificación en tests/test_
    # amortizacion.py: el valor en libros de una baja nunca puede superar lo que queda de
    # activo_no_corriente, cada sub-lote resta como mucho su propio valor en libros real, nunca
    # sorteado por separado). ---
    baja_valor_en_libros_eur = valor_en_libros_bajas_eur(bajas_este_año)
    baja_valor_venta_eur = valor_venta_bajas_eur(bajas_este_año)
    deterioro_enajenacion_inmovilizado_eur = resultado_bajas_eur(bajas_este_año)
    activo_no_corriente_eur = max(0.0, activo_no_corriente_eur - baja_valor_en_libros_eur)
    disponible_proporcional_eur += baja_valor_venta_eur

    # --- PyG: primitivas no financieras + tipo de interés, sorteadas UNA sola vez. Las que el
    # arquetipo toca (efecto pyg_primitiva) se fuerzan por continuidad en vez de sortearse, y
    # además se topan para que el subtotal que alimentan no rebase su propio techo/suelo de
    # plausibilidad sectorial (ver _limitar_por_subtotal). ---
    primitivas_forzadas: dict[str, float] = {}
    riesgo_plausibilidad_pyg = False
    pyg_contencion_al_limite = False
    pyg_subtotales_sin_contener: dict[str, float] = {}
    # --- Suceso puntual (arquetipo 12, "resultado extraordinario"): SOLO se fuerza en el año
    # sorteado como año_evento_puntual — el otro año (y 2023) no se toca, así que
    # resultado_extraordinario vuelve a su ruido de sector normal (huber ~0) automáticamente, sin
    # código adicional. No pasa por _limitar_por_subtotal (sin techo/suelo de plausibilidad): la
    # propia naturaleza del arquetipo es que ESE año se salga de lo plausible — limitarlo
    # anularía el efecto que se pide generar. Ver _evento_puntual_valor y docstring del módulo. ---
    for ea in efectos_evento_puntual:
        if año == año_evento_puntual:
            primitivas_forzadas[ea.efecto.primitiva] = _evento_puntual_valor(ea.efecto, fila, ea.intensidad_base)
    efectos_pyg_base_dinamica: list[EfectoActivo] = []
    for ea in efectos_pyg:
        efecto = ea.efecto
        objetivo = _pyg_primitiva_objetivo(efecto, anterior, fila, ea.intensidad_efectiva)
        if efecto.primitiva in SUBTOTAL_PYG_BASE_DINAMICA_DE_PRIMITIVA:
            # No se puede topar aquí: el subtotal (baii) depende de otras primitivas que
            # todavía no se han sorteado. Se fuerza el objetivo sin contener y se corrige
            # después de generar la PyG completa (ver más abajo).
            primitivas_forzadas[efecto.primitiva] = objetivo
            efectos_pyg_base_dinamica.append(ea)
            continue
        objetivo, subtotal_topado, subtotal_sin_contener = _limitar_por_subtotal(
            efecto.primitiva, objetivo, fila, efecto.direccion
        )
        primitivas_forzadas[efecto.primitiva] = objetivo
        if subtotal_topado is not None:
            riesgo_plausibilidad_pyg = True
            pyg_subtotales_sin_contener[subtotal_topado] = subtotal_sin_contener
    parcial_pyg = _generar_pyg_hasta_baii(
        rng_pyg, fila, ventas, año, primitivas_forzadas=primitivas_forzadas, amortizaciones_eur=amortizacion_eur_año,
        deterioro_enajenacion_inmovilizado_eur=deterioro_enajenacion_inmovilizado_eur,
        anterior_pyg_pct=anterior.pyg_pct, anterior_tipo_interes=anterior.tipo_interes,
    )
    for ea in efectos_pyg_base_dinamica:
        efecto = ea.efecto
        subtotal = SUBTOTAL_PYG_BASE_DINAMICA_DE_PRIMITIVA[efecto.primitiva]
        gastos_personal_pct_sin_empuje = anterior.pyg_pct[efecto.primitiva]
        parcial_pyg, topado, valor_sin_contener, limite_por_ruido_base = _limitar_gastos_personal_por_baii(
            parcial_pyg, gastos_personal_pct_sin_empuje, fila, efecto.direccion
        )
        if topado:
            riesgo_plausibilidad_pyg = True
            pyg_subtotales_sin_contener[subtotal] = valor_sin_contener
            if limite_por_ruido_base:
                pyg_contencion_al_limite = True
                # Cobertura narrativa de negocio para el dato técnico (ver docstring del módulo,
                # sección "Arquetipo 10"): usa `rng_nota`, un generador INDEPENDIENTE de rng_pyg,
                # sembrado con semilla + sector + segmento + intensidad (ver
                # generar_evolucion_arquetipo) — no basta con reutilizar rng_pyg: llega al punto
                # del sorteo en el MISMO estado para cualquier sector/intensidad con la misma
                # semilla (los draws previos de la PyG no dependen de huber/mad, solo su
                # escalado), lo que colapsaba el sorteo a un puñado de valores repetidos en vez
                # de una elección uniforme por caso (detectado por sesgo estadístico real, no
                # ruido de muestra pequeña — ver docstring del módulo).
                indice_nota = rng_nota.integers(len(NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE))
                texto, etiquetas = NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE[indice_nota]
                notas_memoria.append(NotaMemoria(arquetipo_id=ea.arquetipo_id, numero=ea.numero, texto=texto, etiquetas=etiquetas))

    # --- Cobertura de flujos de efectivo (arquetipo 21, ver motor/coberturas_subvenciones.py):
    # necesita el tipo de interés YA sorteado de este año (parcial_pyg.tipo_interes) para el
    # Δr, así que se calcula aquí, después de la PyG hasta BAII y antes del enlace deuda-interés
    # (que no depende de esto: la cobertura no participa en la contención de endeudamiento ni en
    # el bucle de apalancamiento, se añade como un nivel ya resuelto sobre el balance final). El
    # nocional de CIERRE de este año usa la deuda financiera PROPORCIONAL (no la ya cuadrada tras
    # el déficit de NOF/apalancamiento): aproximación deliberada y documentada — el nocional de
    # cierre solo alimenta el Δr del año SIGUIENTE, no el cuadre de este año. ---
    deuda_financiera_actual_grupo89_eur = deudas_fin_largo_proporcional_eur + deudas_fin_corto_proporcional_eur
    if parametros_grupo89.cobertura_activa:
        plazo_residual_anterior = (
            anterior.cobertura_plazo_residual_años
            if anterior.cobertura_activa
            else parametros_grupo89.cobertura_plazo_residual_inicial_años
        )
        paso_cobertura = evolucionar_cobertura(
            año,
            deuda_financiera_actual_grupo89_eur,
            parcial_pyg.tipo_interes,
            anterior.tipo_interes,
            anterior.cobertura_nocional_vivo_eur,
            plazo_residual_anterior,
            anterior.cobertura_valor_swap_eur,
            anterior.cobertura_saldo_1340_bruto_eur,
            parametros_grupo89.cobertura_pct_deuda,
            parametros_grupo89.cobertura_eficacia_pct,
        )
        cobertura_nocional_vivo_eur = paso_cobertura.nocional_vivo_eur
        cobertura_plazo_residual_años = paso_cobertura.plazo_residual_años
        cobertura_valor_swap_eur = paso_cobertura.valor_swap_eur
        cobertura_saldo_1340_bruto_eur = paso_cobertura.saldo_1340_bruto_eur
        cobertura_eficaz_bruto_eur = paso_cobertura.eficaz_bruto_eur
        cobertura_transferencia_bruto_eur = paso_cobertura.transferencia_bruto_eur
        cobertura_ineficaz_bruto_eur = paso_cobertura.ineficaz_bruto_eur
        ajuste_gastos_financieros_grupo89_eur = ajuste_gastos_financieros_cobertura_eur(paso_cobertura)
    else:
        cobertura_nocional_vivo_eur = 0.0
        cobertura_plazo_residual_años = 0.0
        cobertura_valor_swap_eur = 0.0
        cobertura_saldo_1340_bruto_eur = 0.0
        cobertura_eficaz_bruto_eur = 0.0
        cobertura_transferencia_bruto_eur = 0.0
        cobertura_ineficaz_bruto_eur = 0.0
        ajuste_gastos_financieros_grupo89_eur = 0.0

    ajuste_otros_ingresos_explot_grupo89_eur = subvencion_transferencia_bruto_eur

    # Colocación en balance del grupo89 de ESTE año (nivel, no delta — ver más arriba por qué
    # se excluyó del crecimiento proporcional): el activo por impuesto diferido (si procede) suma
    # a activo_no_corriente; AMBOS pasivos por impuesto diferido (cobertura + subvención) suman a
    # otras_deudas_largo (pasivo_no_corriente). El derivado, si es activo (valor razonable
    # positivo), sigue sumando a activo_no_corriente (lado activo — fuera del alcance de este
    # cuarto lote, que solo desglosa el lado de "Deudas financieras"; sigue identificable de
    # forma distinta vía `cobertura_valor_swap_eur`). Si es PASIVO, desde el cuarto lote de
    # desglose de balance ya NO va a `otras_deudas_largo` (aproximación anterior) — tiene su
    # línea propia "IV. Derivados" dentro de "Deudas financieras a largo plazo", plegada más
    # abajo en `deudas_fin_largo_eur` dentro de `_construir_balance` (nunca en la base que
    # alimenta gastos_financieros — ver bloque de deudas financieras más abajo, y CLAUDE.md
    # "Deudas financieras — cuarto lote" para el porqué completo).
    activos_por_impuesto_diferido_eur = activo_por_impuesto_diferido_eur(cobertura_saldo_1340_bruto_eur)
    pasivos_por_impuesto_diferido_eur = pasivo_por_impuesto_diferido_eur(cobertura_saldo_1340_bruto_eur) + pasivo_por_impuesto_diferido_eur(
        subvencion_saldo_130_bruto_eur
    )
    activo_no_corriente_eur += max(0.0, cobertura_valor_swap_eur) + activos_por_impuesto_diferido_eur
    otras_deudas_largo_eur += pasivos_por_impuesto_diferido_eur
    derivados_pasivo_largo_eur = max(0.0, -cobertura_valor_swap_eur)

    # Subvención: el cobro de la ayuda es caja real, entra en el ejercicio de concesión y se
    # queda (la imputación posterior a la PyG es un reciclaje de PN -> resultado, no una salida
    # de caja) — ver docstring del módulo `motor.coberturas_subvenciones`.
    disponible_proporcional_eur += subvencion_importe_concedido_eur

    # --- Operaciones vinculadas (arquetipo 20) financieras: "préstamo a matriz" (activo nuevo,
    # canje con caja) y "financiación recibida de grupo" (pasivo nuevo, canje con caja) — perfil
    # fijo (% de patrimonio_neto/deuda financiera) desde que el arquetipo se activa, recalculado
    # cada año sobre la magnitud de referencia YA cuadrada del año ANTERIOR (evita la
    # circularidad de depender de un patrimonio_neto/deuda financiera que este mismo año
    # todavía no existe — mismo criterio que el resto de bases "proporcionales" de esta función,
    # todas ancladas en `anterior`). Se pliega en `activo_no_corriente_eur`/`otras_deudas_largo_
    # eur`/`disponible_proporcional_eur` ANTES de `_construir_balance`/`_evaluar` (como el resto
    # de grupo89, más arriba) para que la contención de endeudamiento (más abajo) la vea SIEMPRE
    # — punto 1 de la confirmación del usuario para este lote: "financiación recibida" debe pasar
    # por el MISMO chequeo que ya protege a 9/14/17/18, no un mecanismo de deuda nueva sin
    # control (queda señalizada pero sin palanca de amortiguación propia, igual que 9/14/17/18:
    # el arquetipo 20 no toca ninguna masa de circulante). ---
    inversion_grupo_largo_eur = 0.0
    deuda_grupo_largo_eur = 0.0
    if parametros_operacion_vinculada.tipo_operacion == "prestamo_matriz":
        importe_bruto_eur = max(
            parametros_operacion_vinculada.pct_objetivo * anterior.balance_eur["patrimonio_neto"],
            SUELO_IMPORTE_VINCULADAS_EUR,
        )
        inversion_grupo_largo_eur = min(
            importe_bruto_eur, max(0.0, disponible_proporcional_eur) * TECHO_FRACCION_DISPONIBLE_PRESTAMO_MATRIZ
        )
        activo_no_corriente_eur += inversion_grupo_largo_eur
        disponible_proporcional_eur -= inversion_grupo_largo_eur
    elif parametros_operacion_vinculada.tipo_operacion == "financiacion_recibida_grupo":
        deuda_financiera_referencia_eur = anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"]
        deuda_grupo_largo_eur = max(
            parametros_operacion_vinculada.pct_objetivo * deuda_financiera_referencia_eur,
            SUELO_IMPORTE_VINCULADAS_EUR,
        )
        otras_deudas_largo_eur += deuda_grupo_largo_eur
        disponible_proporcional_eur += deuda_grupo_largo_eur

    # --- Provisiones a largo/corto plazo (tercer lote de desglose de balance, motor/
    # provisiones.py) — probabilidad de fondo independiente de cualquier arquetipo. La magnitud
    # (importe_dotado_eur) se sortea UNA vez, el año de la dotación, sobre el patrimonio_neto YA
    # resuelto del año anterior (mismo criterio "anclado en `anterior`" que el resto de esta
    # función) y se lleva sin cambios de ahí en adelante (`anterior.provision_importe_dotado_eur`
    # una vez fijado). El saldo se reclasifica ÍNTEGRO largo/corto cada año según el horizonte
    # restante — se pliega en `otras_deudas_largo_eur`/`otras_deudas_corto_eur` ANTES de
    # `_construir_balance`/`_evaluar`, igual que grupo89/operaciones vinculadas. La dotación
    # (gasto) y el exceso (ingreso) se inyectan en la PyG más abajo, junto al resto de ajustes
    # grupo89 — ver ese bloque. La aplicación es caja real, se resta de disponible aquí mismo. ---
    provision_importe_dotado_eur = anterior.provision_importe_dotado_eur
    if parametros_provision.activa and año == parametros_provision.año_dotacion:
        provision_importe_dotado_eur = sortear_importe_provision_eur(
            sector, segmento, semilla, anterior.balance_eur["patrimonio_neto"]
        )
    saldo_anterior_provision_eur = anterior.provision_saldo_largo_eur + anterior.provision_saldo_corto_eur
    paso_provision = evolucionar_provision(parametros_provision, provision_importe_dotado_eur, saldo_anterior_provision_eur, año)
    provision_saldo_largo_eur = paso_provision.saldo_eur if paso_provision.es_largo else 0.0
    provision_saldo_corto_eur = 0.0 if paso_provision.es_largo else paso_provision.saldo_eur
    otras_deudas_largo_eur += provision_saldo_largo_eur
    otras_deudas_corto_eur += provision_saldo_corto_eur
    disponible_proporcional_eur -= paso_provision.aplicacion_eur
    ajuste_gastos_personal_provision_eur = paso_provision.dotacion_eur if parametros_provision.naturaleza_pyg == "gastos_personal" else 0.0
    ajuste_otros_gastos_explot_provision_eur = (
        paso_provision.dotacion_eur if parametros_provision.naturaleza_pyg == "otros_gastos_explot" else 0.0
    )
    ajuste_otros_ingresos_explot_provision_eur = paso_provision.exceso_eur

    # --- Deterioro de valor de créditos por operaciones comerciales (cuenta 490, motor/
    # insolvencias.py) — probabilidad de fondo independiente de cualquier arquetipo, anclada a
    # `ratios.cobro_dias` + boost si el arquetipo 4/7 están activos. La magnitud se sortea UNA
    # vez, el año de la dotación, sobre "Clientes" YA resuelto del año anterior (mismo criterio
    # "anclado en `anterior`" de toda esta función) y se lleva sin cambios de ahí en adelante. A
    # diferencia de provisiones, la deducción sobre `realizable_eur` NO se pliega aquí (esa masa
    # sí alimenta `_deficit_y_deuda_corto` — hacerlo aquí contaminaría el cálculo de NOF con un
    # deterioro que no es un evento de ciclo de caja): se aplica más abajo, dentro de `_evaluar`,
    # solo para el balance final — ver docstring de motor.insolvencias. ---
    cobro_dias_huber = fila["ratios.cobro_dias.huber_9y"]
    insolvencia_importe_dotado_eur = anterior.insolvencia_importe_dotado_eur
    if parametros_insolvencia.activa and año == parametros_insolvencia.año_dotacion:
        clientes_referencia_eur = anterior.deudores_perfil_pct.get("clientes", 0.0) * anterior.balance_eur["realizable"]
        boost_magnitud_insolvencia_activo = deterioro_ciclo_caja_activo or dependencia_pocos_clientes_activo
        insolvencia_importe_dotado_eur = sortear_importe_insolvencia_eur(
            sector, segmento, semilla, clientes_referencia_eur, cobro_dias_huber, boost_magnitud_insolvencia_activo
        )
    paso_insolvencia = evolucionar_insolvencia(
        parametros_insolvencia,
        insolvencia_importe_dotado_eur,
        anterior.insolvencia_saldo_eur,
        anterior.insolvencia_exceso_acumulado_eur,
        año,
    )
    ajuste_otros_gastos_explot_insolvencia_eur = paso_insolvencia.dotacion_eur
    ajuste_otros_ingresos_explot_insolvencia_eur = paso_insolvencia.exceso_eur

    ajustes_cambio_valor_pn_eur = presentacion_neta_eur(cobertura_saldo_1340_bruto_eur)
    subvenciones_pn_eur = presentacion_neta_eur(subvencion_saldo_130_bruto_eur)
    delta_pn_grupo89_eur = (
        (ajustes_cambio_valor_pn_eur - anterior.ajustes_cambio_valor_pn_eur)
        + (subvenciones_pn_eur - anterior.subvenciones_pn_eur)
    )

    def _deficit_y_deuda_corto(existencias_eur: float, realizable_eur: float, acreedores_comerciales_eur: float) -> tuple[float, float, float]:
        # Presión neta sobre la NOF: las masas de ACTIVO (existencias, realizable) la suben
        # cuando crecen más de lo proporcional; las de PASIVO (acreedores_comerciales) la BAJAN
        # cuando crecen más de lo proporcional (más financiación de proveedores, menos caja
        # necesaria) — ver SIGNO_NOF_MASA_CIRCULANTE. Un único max(0, suma con signo), no una
        # suma de max(0, ...) por variable: si una masa de pasivo compensa a una de activo, el
        # déficit real es menor que la suma de los excesos por separado.
        presion_nof_eur = (
            SIGNO_NOF_MASA_CIRCULANTE["existencias"] * (existencias_eur - existencias_proporcional_eur)
            + SIGNO_NOF_MASA_CIRCULANTE["realizable"] * (realizable_eur - realizable_proporcional_eur)
            + SIGNO_NOF_MASA_CIRCULANTE["acreedores_comerciales"]
            * (acreedores_comerciales_eur - acreedores_comerciales_proporcional_eur)
        )
        nof_extra_eur = max(0.0, presion_nof_eur)
        disponible_bruto_eur = disponible_proporcional_eur - nof_extra_eur
        if disponible_bruto_eur >= 0:
            disponible_eur = disponible_bruto_eur
            deuda_extra_por_nof_eur = 0.0
        else:
            disponible_eur = 0.0
            deuda_extra_por_nof_eur = -disponible_bruto_eur
        deudas_fin_corto_eur = deudas_fin_corto_proporcional_eur + deuda_extra_por_nof_eur
        return disponible_eur, deudas_fin_corto_eur, deuda_extra_por_nof_eur

    def _construir_balance(
        existencias_eur: float,
        realizable_eur: float,
        acreedores_comerciales_eur: float,
        disponible_eur: float,
        deudas_fin_corto_eur: float,
        deudas_fin_largo_con_coste_eur: float,
        patrimonio_neto_eur: float,
    ) -> tuple[dict[str, float], float]:
        # `deudas_fin_largo_con_coste_eur` es la base CON coste (alimenta gastos_financieros,
        # ver `_evaluar` más abajo) — el derivado (IV. Derivados, cuarto lote de desglose de
        # balance) se añade AQUÍ, solo para el balance reportado, nunca antes: una valoración a
        # mercado del swap no es principal prestado, no debe generar "interés" a la tasa media
        # del sector. Ver CLAUDE.md, "Deudas financieras — cuarto lote".
        deudas_fin_largo_eur = deudas_fin_largo_con_coste_eur + derivados_pasivo_largo_eur
        balance = {
            "activo_no_corriente": activo_no_corriente_eur,
            "activo_corriente": existencias_eur + realizable_eur + disponible_eur,
            "existencias": existencias_eur,
            "realizable": realizable_eur,
            "disponible": disponible_eur,
            "patrimonio_neto": patrimonio_neto_eur,
            "pasivo_no_corriente": deudas_fin_largo_eur + otras_deudas_largo_eur,
            "deudas_fin_largo": deudas_fin_largo_eur,
            "otras_deudas_largo": otras_deudas_largo_eur,
            "pasivo_corriente": acreedores_comerciales_eur + deudas_fin_corto_eur + otras_deudas_corto_eur,
            "acreedores_comerciales": acreedores_comerciales_eur,
            "deudas_fin_corto": deudas_fin_corto_eur,
            "otras_deudas_corto": otras_deudas_corto_eur,
        }

        activo_total_eur = balance["activo_no_corriente"] + balance["activo_corriente"]
        pn_pasivo_total_eur = balance["patrimonio_neto"] + balance["pasivo_no_corriente"] + balance["pasivo_corriente"]
        diferencia_cuadre = activo_total_eur - pn_pasivo_total_eur
        ajuste_cuadre_eur = 0.0
        if abs(diferencia_cuadre) > TOLERANCIA_CUADRE_EUR:
            ajuste_cuadre_eur = diferencia_cuadre
            otras_deudas_corto_ajustado = balance["otras_deudas_corto"] + diferencia_cuadre
            if otras_deudas_corto_ajustado < 0:
                # El cuadre pediría dejar "otras deudas a corto" en negativo (valor absurdo):
                # el exceso de patrimonio neto + pasivo sobre el activo se trata como caja de
                # más en vez de como una deuda negativa. Red de seguridad barata.
                remanente = -otras_deudas_corto_ajustado
                balance["otras_deudas_corto"] = 0.0
                balance["disponible"] += remanente
                balance["activo_corriente"] += remanente
            else:
                balance["otras_deudas_corto"] = otras_deudas_corto_ajustado
            balance["pasivo_corriente"] = (
                balance["acreedores_comerciales"] + balance["deudas_fin_corto"] + balance["otras_deudas_corto"]
            )

        return balance, ajuste_cuadre_eur

    def _evaluar(
        existencias_eur: float,
        realizable_eur: float,
        acreedores_comerciales_eur: float,
        extra_deuda_largo_eur: float = 0.0,
    ) -> tuple[dict[str, float], float, float, dict[str, float], dict[str, float], float, float]:
        """Evalúa un escenario de forma autoconsistente: la deuda financiera final de ESE
        escenario (incluida la extra por apalancamiento, si la hay) determina sus propios
        gastos financieros. `extra_deuda_largo_eur` financia una distribución a PN por el
        mismo importe (ver docstring del módulo, sección "Arquetipo 9")."""
        disponible_eur, deudas_fin_corto_eur, deuda_extra_por_nof_eur = _deficit_y_deuda_corto(
            existencias_eur, realizable_eur, acreedores_comerciales_eur
        )
        deudas_fin_largo_eur = deudas_fin_largo_proporcional_eur + extra_deuda_largo_eur
        deuda_financiera_fin_eur = deudas_fin_largo_eur + deudas_fin_corto_eur
        deuda_financiera_media_eur = (deuda_financiera_inicio_eur + deuda_financiera_fin_eur) / 2
        pyg_pct, pyg_eur = _completar_pyg_con_deuda(parcial_pyg, deuda_financiera_media_eur)

        # Ajuste de grupo89 (cobertura/subvención), provisiones (dotación/exceso, tercer lote) e
        # insolvencia de clientes (dotación/exceso, cuenta 490) — importe BRUTO completo,
        # desacoplado del `impuesto_beneficios` ya sorteado (que no debe gravar dos veces estas
        # partidas ni dejarlas sin gravar del todo): ver docstring de motor.coberturas_
        # subvenciones (punto 1 del diseño de cuadre), motor.provisiones y motor.insolvencias.
        # Se aplica DESPUÉS de `_completar_pyg_con_deuda` para no alterar la base sobre la que se
        # sorteó `impuesto_beneficios_pct`. El exceso de provisión/insolvencia se pliega en
        # `otros_ingresos_explot` (línea "Excesos de provisiones" del modelo oficial, no
        # desglosada como línea propia en `pyg_eur` — mismo criterio de simplificación ya usado
        # para la imputación de subvenciones, ver arriba: el importe distinto SÍ queda expuesto
        # aparte, en `EjercicioEmpresa.provision_exceso_eur`/`.insolvencia_exceso_eur`); la
        # dotación de provisión resta de `gastos_personal` u `otros_gastos_explot` según su
        # categoría; la de insolvencia resta siempre de `otros_gastos_explot` (cuenta 490, nunca
        # gasto de personal).
        ajuste_otros_gastos_explot_total_provision_eur = (
            ajuste_otros_gastos_explot_provision_eur + ajuste_otros_gastos_explot_insolvencia_eur
        )
        if (
            ajuste_gastos_financieros_grupo89_eur != 0.0
            or ajuste_otros_ingresos_explot_grupo89_eur != 0.0
            or ajuste_gastos_personal_provision_eur != 0.0
            or ajuste_otros_gastos_explot_total_provision_eur != 0.0
            or ajuste_otros_ingresos_explot_provision_eur != 0.0
            or ajuste_otros_ingresos_explot_insolvencia_eur != 0.0
        ):
            pyg_eur = dict(pyg_eur)
            ajuste_otros_ingresos_explot_total_eur = (
                ajuste_otros_ingresos_explot_grupo89_eur
                + ajuste_otros_ingresos_explot_provision_eur
                + ajuste_otros_ingresos_explot_insolvencia_eur
            )
            pyg_eur["otros_ingresos_explot"] += ajuste_otros_ingresos_explot_total_eur
            pyg_eur["ingresos_explotacion"] += ajuste_otros_ingresos_explot_total_eur
            pyg_eur["margen_bruto"] += ajuste_otros_ingresos_explot_total_eur
            pyg_eur["otros_gastos_explot"] += ajuste_otros_gastos_explot_total_provision_eur
            valor_añadido_delta_eur = (
                ajuste_otros_ingresos_explot_total_eur - ajuste_otros_gastos_explot_total_provision_eur
            )
            pyg_eur["valor_añadido"] += valor_añadido_delta_eur
            pyg_eur["gastos_personal"] += ajuste_gastos_personal_provision_eur
            baii_delta_eur = valor_añadido_delta_eur - ajuste_gastos_personal_provision_eur
            pyg_eur["baii"] += baii_delta_eur
            pyg_eur["gastos_financieros"] -= ajuste_gastos_financieros_grupo89_eur
            bai_delta_eur = baii_delta_eur + ajuste_gastos_financieros_grupo89_eur
            pyg_eur["bai"] += bai_delta_eur
            pyg_eur["resultado_ejercicio"] += bai_delta_eur
            pyg_pct = {k: v / pyg_eur["ingresos_explotacion"] * 100 for k, v in pyg_eur.items()}

        # Payout de dividendos (sección "Retención de beneficios/distribución a PN" —
        # decisiones_plausibilidad.md #79-#80): a diferencia de la distribución de apalancamiento
        # (financiada con deuda nueva, sin impacto de caja — ver más abajo), esta SÍ sale de caja
        # real, así que se resta de `disponible_eur` aquí, sobre el resultado YA final (después
        # del ajuste de grupo89/provisión de arriba). Nunca sobre un ejercicio en pérdidas
        # (`max(0.0, ...)`).
        #
        # Hallazgo #82: topar el payout a `disponible_eur` (versión anterior) dejaba, en los
        # casos donde la NOF ya había consumido la caja disponible, el beneficio de más RETENIDO
        # en PN en vez de repartido — justo en los años en que el circulante ya estaba tenso,
        # componiendo la distorsión de liquidez que #80 intentaba corregir (3,2% de los casos en
        # el barrido de control, con el doble de tasa de señal residual). Corregido: el payout
        # objetivo se financia con deuda a corto NUEVA cuando la caja no basta — mismo criterio
        # que ya usa `_deficit_y_deuda_corto` para el déficit de NOF (líneas arriba), no un
        # mecanismo nuevo. No retroalimenta `gastos_financieros` de ESTE año (misma aproximación
        # ya aceptada para los ajustes post-hoc de grupo89/provisión — la deuda extra sí acumula
        # interés a partir del año siguiente, vía `deuda_financiera_inicio_eur`).
        payout_dividendos_eur = max(0.0, pyg_eur["resultado_ejercicio"]) * payout_caso
        disponible_tras_payout_eur = disponible_eur - payout_dividendos_eur
        payout_deuda_extra_eur = 0.0
        if disponible_tras_payout_eur < 0:
            payout_deuda_extra_eur = -disponible_tras_payout_eur
            deudas_fin_corto_eur += payout_deuda_extra_eur
            disponible_tras_payout_eur = 0.0

        patrimonio_neto_eur = (
            anterior.balance_eur["patrimonio_neto"]
            + pyg_eur["resultado_ejercicio"]
            - extra_deuda_largo_eur
            - payout_dividendos_eur
            + delta_pn_grupo89_eur
        )
        # Insolvencia de clientes (cuenta 490): resta de `realizable_eur` solo AQUÍ, para el
        # balance final — nunca antes de `_deficit_y_deuda_corto` (arriba), que debe seguir
        # viendo el `realizable_eur` bruto (ver docstring de motor.insolvencias y el comentario
        # de más arriba, junto al sorteo de `paso_insolvencia`).
        realizable_neto_insolvencia_eur = realizable_eur - paso_insolvencia.deduccion_realizable_eur
        balance, ajuste_cuadre_eur = _construir_balance(
            existencias_eur,
            realizable_neto_insolvencia_eur,
            acreedores_comerciales_eur,
            disponible_tras_payout_eur,
            deudas_fin_corto_eur,
            deudas_fin_largo_eur,
            patrimonio_neto_eur,
        )
        return balance, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur, payout_dividendos_eur, payout_deuda_extra_eur

    huber_endeudamiento = fila["ratios.endeudamiento.huber_9y"]
    mad_endeudamiento = fila["ratios.endeudamiento.huber_scale_mad"]
    techo_endeudamiento = min(
        huber_endeudamiento + N_DESVIACIONES_TECHO_ENDEUDAMIENTO * mad_endeudamiento,
        TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    )

    # --- Apalancamiento: sube la deuda a largo hasta un endeudamiento objetivo (topado al
    # techo de plausibilidad), resuelto en forma cerrada sobre el balance SIN este efecto. ---
    apalancamiento_extra_eur = 0.0
    if efectos_apalancamiento:
        balance_base, _, _, _, _, _, _ = _evaluar(
            existencias_eur, realizable_eur, acreedores_comerciales_eur, extra_deuda_largo_eur=0.0
        )
        # Topado al techo ANTES de aplicar la intensidad (no solo el objetivo final): si el año
        # anterior ya quedó por encima del techo por el residuo habitual del plug de cuadre
        # (una fracción de euro, normalmente), partir de ese valor ya excedido para multiplicar
        # por (1+intensidad) podía compensarse mal al recortar después, dejando el endeudamiento
        # de este año por DEBAJO del anterior (detectado en pruebas: TIC, Siderurgia). Al topar
        # la propia base, el objetivo de cada año queda siempre <= techo, sin depender de cuánto
        # se hubiera desviado el año anterior.
        endeudamiento_anterior = min(_endeudamiento(anterior.balance_eur), techo_endeudamiento)
        ea_apalancamiento = efectos_apalancamiento[0]
        efecto_apalancamiento = ea_apalancamiento.efecto
        endeudamiento_objetivo = min(
            endeudamiento_anterior * (1 + efecto_apalancamiento.direccion * ea_apalancamiento.intensidad_efectiva),
            techo_endeudamiento,
        )
        activo_base_eur = balance_base["activo_no_corriente"] + balance_base["activo_corriente"]
        pasivo_base_eur = balance_base["pasivo_no_corriente"] + balance_base["pasivo_corriente"]
        extra_deuda_objetivo_eur = max(0.0, endeudamiento_objetivo * activo_base_eur - pasivo_base_eur)
        # La deuda nueva financia una distribución a PN (ver docstring): no se puede repartir
        # más patrimonio neto del que hay. Sin este tope, en sectores con PN de partida bajo
        # (poco margen entre PN y el endeudamiento objetivo) la distribución podía dejar el PN
        # en negativo — detectado en pruebas de estrés (Restaurantes y puestos de comidas,
        # 4 de 3.000 combinaciones). Techo defensivo, no el mecanismo habitual.
        apalancamiento_extra_eur = min(extra_deuda_objetivo_eur, max(0.0, balance_base["patrimonio_neto"]))

    balance_eur, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur, payout_dividendos_eur, payout_deuda_extra_eur = _evaluar(
        existencias_eur, realizable_eur, acreedores_comerciales_eur, extra_deuda_largo_eur=apalancamiento_extra_eur
    )

    deterioro_aplicado_eur = 0.0
    riesgo_endeudamiento = False
    endeudamiento_sin_contener: float | None = None
    contencion_al_limite = False

    # OJO: se comprueba SIEMPRE, no solo "if deuda_extra_por_nof_eur > 0". La primera versión
    # de este mecanismo solo miraba el endeudamiento cuando el déficit de NOF del propio año
    # forzaba deuda nueva — pero un arquetipo como "apalancamiento" nunca genera ese déficit
    # (no toca existencias/realizable) y aun así puede dejar un endeudamiento disparatado por
    # la "espiral de deuda" (ver docstring): la deuda de un año sigue devengando interés en el
    # siguiente, erosiona el PN, y el ratio empeora sin que se añada deuda nueva ESE año. Con
    # el chequeo condicionado a `deuda_extra_por_nof_eur`, esos casos pasaban completamente
    # desapercibidos: verificado en una pasada de estrés de 1.296 combinaciones del arquetipo
    # 9, 130 (10%) terminaban 2025 con patrimonio neto por debajo del 15% del activo (partiendo
    # de una base sana en 2023) sin que `riesgo_endeudamiento` se activase ni una vez.
    deficit_bruto_inicial_eur = deuda_extra_por_nof_eur  # = umbral de autofinanciación, ver más abajo
    endeudamiento_candidato = _endeudamiento(balance_eur)

    if endeudamiento_candidato > techo_endeudamiento:
        # El endeudamiento (YA con el cuadre general incluido) supera el techo de
        # plausibilidad del sector: se amortigua el exceso de las masas de circulante que el
        # arquetipo haya tocado (en el orden de su definición) en vez de seguir cargando todo
        # a deuda sin límite. Nunca se reduce por debajo del crecimiento proporcional a
        # ventas. Si el arquetipo no toca ninguna masa de circulante (9, 11, 15) — o si el
        # exceso disponible no basta, como en la "espiral de deuda" — no hay nada (o no hay
        # suficiente) que amortiguar por esta vía (deterioro máximo = 0 o insuficiente): el
        # caso queda marcado igualmente (`contencion_al_limite=True`), sin poder corregirse
        # del todo — es la señal honesta de que el caso es económicamente implausible, no un
        # intento fallido de arreglarlo silenciosamente.
        riesgo_endeudamiento = True
        endeudamiento_sin_contener = endeudamiento_candidato

        existencias_bruta_eur, realizable_bruta_eur = existencias_eur, realizable_eur
        activo_bruto_sin_amortiguar_eur = activo_no_corriente_eur + existencias_bruta_eur + realizable_bruta_eur
        # Solo las masas de ACTIVO (signo +1) son palancas de contención eficaces: dampear una
        # masa de PASIVO (acreedores_comerciales) no reduce el pasivo total — lo que se gana ahí
        # se pierde en más deuda a corto necesaria (ambas son pasivo_corriente), efecto neto
        # cero sobre el endeudamiento. Ver SIGNO_NOF_MASA_CIRCULANTE y docstring del módulo.
        excesos_eur = {
            ea.efecto.variable: max(
                0.0,
                objetivos_circulante[ea.efecto.variable] - proporcional_circulante[ea.efecto.variable],
            )
            for ea in efectos_masa_circulante
            if SIGNO_NOF_MASA_CIRCULANTE[ea.efecto.variable] == 1
        }
        # Tope real de amortiguación: el menor entre (a) el exceso del propio arquetipo y
        # (b) el punto en el que el déficit de caja llega a cero (más allá, amortiguar más
        # no cambia ni el activo ni el pasivo: solo mueve valor a tesorería — ver docstring).
        # Si no hubo déficit de NOF este año (deficit_bruto_inicial_eur=0, caso apalancamiento/
        # mejora_margen/tesorería), el tope queda en 0: no hay margen de amortiguación por esta
        # vía y el bucle lo detecta y marca contencion_al_limite en su primera iteración.
        deterioro_maximo_eur = min(sum(excesos_eur.values()), deficit_bruto_inicial_eur)

        for _ in range(MAX_ITERACIONES_CONTENCION):
            patrimonio_neto_actual_eur = balance_eur["patrimonio_neto"]
            deterioro_objetivo_eur = activo_bruto_sin_amortiguar_eur - patrimonio_neto_actual_eur / (
                1 - techo_endeudamiento
            )
            nuevo_deterioro_aplicado_eur = min(max(deterioro_objetivo_eur, 0.0), deterioro_maximo_eur)
            cambio_eur = abs(nuevo_deterioro_aplicado_eur - deterioro_aplicado_eur)
            al_limite = nuevo_deterioro_aplicado_eur >= deterioro_maximo_eur
            deterioro_aplicado_eur = nuevo_deterioro_aplicado_eur

            # Reparte el deterioro entre las variables tocadas, en el orden de la
            # definición, agotando cada una antes de pasar a la siguiente.
            restante = deterioro_aplicado_eur
            objetivos_circulante_amortiguados = dict(objetivos_circulante)
            for variable, exceso in excesos_eur.items():
                aplicado = min(restante, exceso)
                objetivos_circulante_amortiguados[variable] = objetivos_circulante[variable] - aplicado
                restante -= aplicado
            existencias_eur = objetivos_circulante_amortiguados["existencias"]
            realizable_eur = objetivos_circulante_amortiguados["realizable"]

            balance_eur, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur, payout_dividendos_eur, payout_deuda_extra_eur = _evaluar(
                existencias_eur,
                realizable_eur,
                acreedores_comerciales_eur,
                extra_deuda_largo_eur=apalancamiento_extra_eur,
            )

            if al_limite:
                contencion_al_limite = True
                break  # se agotó el margen de amortiguación posible sin llegar al techo
            if cambio_eur < TOLERANCIA_CONVERGENCIA_DETERIORO_EUR:
                break  # convergido al techo

    # Desglose del TOTAL de deudores/acreedores comerciales de ESTE año — mismo criterio que
    # existencias: perfil (%) constante (ya fijado "desde 2023", incluida cualquier sub-partida
    # de grupo/varios forzada por el arquetipo 20 en el año base), aplicado al agregado YA
    # cuadrado de este año.
    deudores_desglose_eur_año = {
        componente: fraccion * balance_eur["realizable"] for componente, fraccion in anterior.deudores_perfil_pct.items()
    }
    acreedores_desglose_eur_año = {
        componente: fraccion * balance_eur["acreedores_comerciales"]
        for componente, fraccion in anterior.acreedores_perfil_pct.items()
    }
    magnitud_operacion_vinculada_eur = _magnitud_operacion_vinculada(
        ventas, balance_eur, parametros_operacion_vinculada.tipo_operacion
    ) if parametros_operacion_vinculada.activa else 0.0
    operacion_vinculada_importe_eur = _importe_operacion_vinculada_eur(
        parametros_operacion_vinculada.tipo_operacion,
        deudores_desglose_eur_año,
        acreedores_desglose_eur_año,
        inversion_grupo_largo_eur,
        deuda_grupo_largo_eur,
    ) if parametros_operacion_vinculada.activa else 0.0
    operacion_vinculada_pct_mostrado = (
        operacion_vinculada_importe_eur / magnitud_operacion_vinculada_eur * 100
        if parametros_operacion_vinculada.activa and magnitud_operacion_vinculada_eur > 0
        else 0.0
    )

    # Desglose de deudas financieras (cuarto y último lote de desglose de balance) — calculado
    # DESPUÉS de la contención de endeudamiento, sobre el balance YA final de este año:
    # "Entidades de crédito" es el residual (absorbe lo que `reclasificacion_deuda`, capex o
    # adquisición hayan movido), "Derivados" es el nivel ya plegado en `balance_eur[
    # "deudas_fin_largo"]` dentro de `_construir_balance` — se resta aquí para aislar la base
    # CON COSTE que sí reparten los perfiles fijos de arrendamiento financiero/obligaciones/
    # otros pasivos financieros. Ver `motor.empresa_base.calcular_desglose_deudas_fin`.
    deudas_fin_largo_con_coste_año_eur = balance_eur["deudas_fin_largo"] - derivados_pasivo_largo_eur
    deudas_fin_largo_desglose_eur_año, deudas_fin_corto_desglose_eur_año = calcular_desglose_deudas_fin(
        anterior.deudas_fin_fraccion_total, anterior.deudas_fin_fraccion_largo,
        deudas_fin_largo_con_coste_año_eur, balance_eur["deudas_fin_corto"], derivados_pasivo_largo_eur,
    )

    # Desglose de "otras deudas" (quinto lote de desglose de balance) — calculado, igual que el
    # de deudas financieras, DESPUÉS de la contención de endeudamiento, sobre el balance YA final
    # de este año. El residuo de cada plazo excluye provisiones (tercer lote)/deudas con el grupo
    # (arquetipo 20)/pasivos por impuesto diferido (grupo 8/9) — ya sumados sobre `otras_deudas_
    # largo_eur`/`..._corto_eur` más arriba en esta función, antes de `_construir_balance` — para
    # no re-etiquetar el mismo euro bajo dos epígrafes oficiales distintos (ver motor.empresa_
    # base.calcular_desglose_otras_deudas). El residuo de corto se defiende con `max(0.0, ...)`:
    # a diferencia de largo, el plug de cuadre de `_construir_balance` SÍ puede tocar `otras_
    # deudas_corto` (nunca `otras_deudas_largo`). `aapp_pendiente` se sortea FRESCO cada año (no
    # forma parte del perfil fijo desde 2023, ver docstring de `sortear_aapp_pendiente_corto_pct`)
    # con el boost real de arquetipo 4/7 de ESTE año — a diferencia del año base, donde ambos son
    # siempre False.
    otras_deudas_largo_residual_año_eur = balance_eur["otras_deudas_largo"] - pasivos_por_impuesto_diferido_eur - deuda_grupo_largo_eur - provision_saldo_largo_eur
    otras_deudas_corto_residual_año_eur = max(0.0, balance_eur["otras_deudas_corto"] - provision_saldo_corto_eur)
    aapp_pendiente_corto_pct_año, _modo_aapp_pendiente_año = sortear_aapp_pendiente_corto_pct(
        sector, segmento, semilla,
        deterioro_ciclo_caja_activo=deterioro_ciclo_caja_activo,
        dependencia_clientes_activo=dependencia_pocos_clientes_activo,
    )
    otras_deudas_largo_desglose_eur_año, otras_deudas_corto_desglose_eur_año = calcular_desglose_otras_deudas(
        anterior.otras_deudas_largo_perfil_pct, anterior.otras_deudas_corto_resto_perfil_pct,
        aapp_pendiente_corto_pct_año, otras_deudas_largo_residual_año_eur, otras_deudas_corto_residual_año_eur,
        acreedores_inmovilizado_largo_anterior_eur=anterior.otras_deudas_largo_desglose_eur.get("acreedores_inmovilizado", 0.0),
    )

    # Desglose de PyG en líneas oficiales del PGC (encargo 1/2 de este lote) — perfiles (%)
    # constantes ya fijados "desde 2023" para cifra_negocios/consumos_explotacion/otros_gastos_
    # explot, aplicados al agregado YA final de este año (`pyg_eur`, después de cualquier ajuste
    # de arquetipo/grupo89/provisión/insolvencia — mismo criterio que existencias/deudores).
    # "Pérdidas por operaciones comerciales" y "Provisiones" (gastos_personal) enlazan la
    # dotación de ESTE año de insolvencias/provisiones, nunca un sorteo nuevo. "De empresas del
    # grupo" (ingresos_financieros) enlaza `inversion_grupo_largo_eur` de ESTE año (0.0 salvo que
    # el arquetipo 20 haya activado esa operación concreta).
    categoria_pyg_oficial = categoria_de_sector(sector)
    pyg_cifra_negocios_desglose_eur_año = {
        componente: fraccion * pyg_eur["cifra_negocios"]
        for componente, fraccion in anterior.pyg_cifra_negocios_perfil_pct.items()
    }
    pyg_consumos_explotacion_desglose_eur_año = {
        componente: fraccion * pyg_eur["consumos_explotacion"]
        for componente, fraccion in anterior.pyg_consumos_explotacion_perfil_pct.items()
    }
    pyg_otros_gastos_explot_desglose_eur_año = calcular_desglose_otros_gastos_explot(
        anterior.pyg_otros_gastos_explot_perfil_pct, pyg_eur["otros_gastos_explot"], paso_insolvencia.dotacion_eur,
    )
    provision_dotacion_gastos_personal_eur = (
        paso_provision.dotacion_eur if parametros_provision.naturaleza_pyg == "gastos_personal" else 0.0
    )
    pyg_gastos_personal_desglose_eur_año = calcular_desglose_gastos_personal(
        año, categoria_pyg_oficial, pyg_eur["gastos_personal"], provision_dotacion_gastos_personal_eur,
    )
    pyg_ingresos_financieros_desglose_eur_año = calcular_desglose_ingresos_financieros(
        pyg_eur["ingresos_financieros"], inversion_grupo_largo_eur, parcial_pyg.tipo_interes,
    )

    return EjercicioEmpresa(
        año=año,
        ventas=ventas,
        crecimiento_ventas=crecimiento_ventas,
        balance_eur=balance_eur,
        pyg_eur=pyg_eur,
        pyg_pct=pyg_pct,
        modos=parcial_pyg.modos,
        ajuste_cuadre_eur=ajuste_cuadre_eur,
        deuda_extra_por_nof_eur=deuda_extra_por_nof_eur,
        endeudamiento=_endeudamiento(balance_eur),
        cobertura_gastos_financieros=_cobertura_gastos_financieros(pyg_eur),
        riesgo_endeudamiento=riesgo_endeudamiento,
        endeudamiento_sin_contener=endeudamiento_sin_contener,
        deterioro_aplicado_eur=deterioro_aplicado_eur,
        contencion_al_limite=contencion_al_limite,
        apalancamiento_extra_eur=apalancamiento_extra_eur,
        payout_dividendos_eur=payout_dividendos_eur,
        payout_deuda_extra_eur=payout_deuda_extra_eur,
        riesgo_plausibilidad_pyg=riesgo_plausibilidad_pyg,
        pyg_subtotales_sin_contener=pyg_subtotales_sin_contener,
        pyg_contencion_al_limite=pyg_contencion_al_limite,
        notas_memoria=tuple(notas_memoria),
        ventas_organicas_eur=ventas_organicas_eur,
        ventas_inorganicas_eur=ventas_inorganicas_eur,
        capital_social_eur=anterior.capital_social_eur,
        # Reservas por resta, igual criterio que siempre — ahora también se excluyen las dos
        # líneas nuevas de PN (ajustes por cambio de valor, subvenciones): son masas propias,
        # no deben quedar absorbidas dentro de reservas.
        reservas_eur=(
            balance_eur["patrimonio_neto"]
            - anterior.capital_social_eur
            - pyg_eur["resultado_ejercicio"]
            - ajustes_cambio_valor_pn_eur
            - subvenciones_pn_eur
        ),
        activo_no_corriente_perfil_pct=anterior.activo_no_corriente_perfil_pct,
        # Desglose del TOTAL de activo_no_corriente de ESTE año (incluye cualquier salto de
        # adquisición ya absorbido, de este año o de años anteriores) — instantánea informativa.
        # `motor/efe.py` calcula el flujo de inversión "orgánico" restando `incremento_activo_
        # adquisicion_eur` del cambio total, con el perfil (constante) aplicado a ESE delta, no a
        # la diferencia entre dos desgloses ya guardados — evita duplicar el salto de un año en
        # el "crecimiento orgánico" del año siguiente.
        activo_no_corriente_desglose_eur={
            componente: fraccion * balance_eur["activo_no_corriente"]
            for componente, fraccion in anterior.activo_no_corriente_perfil_pct.items()
        },
        incremento_activo_adquisicion_eur=incremento_activo_adquisicion_eur,
        coleccion_activos_amortizables=coleccion_activos_amortizables,
        perfil_subtipos_material_pct=anterior.perfil_subtipos_material_pct,
        perfil_subtipos_intangible_pct=anterior.perfil_subtipos_intangible_pct,
        tipo_interes=parcial_pyg.tipo_interes,
        bajas_inmovilizado=bajas_este_año,
        baja_valor_en_libros_eur=baja_valor_en_libros_eur,
        baja_valor_venta_eur=baja_valor_venta_eur,
        cobertura_activa=parametros_grupo89.cobertura_activa,
        cobertura_pct_deuda=parametros_grupo89.cobertura_pct_deuda,
        cobertura_eficacia_pct=parametros_grupo89.cobertura_eficacia_pct,
        cobertura_nocional_vivo_eur=cobertura_nocional_vivo_eur,
        cobertura_plazo_residual_años=cobertura_plazo_residual_años,
        cobertura_valor_swap_eur=cobertura_valor_swap_eur,
        cobertura_saldo_1340_bruto_eur=cobertura_saldo_1340_bruto_eur,
        cobertura_eficaz_bruto_eur=cobertura_eficaz_bruto_eur,
        cobertura_transferencia_bruto_eur=cobertura_transferencia_bruto_eur,
        cobertura_ineficaz_bruto_eur=cobertura_ineficaz_bruto_eur,
        subvencion_activo_asociado=subvencion_activo_asociado,
        subvencion_pct_cofinanciacion=subvencion_pct_cofinanciacion,
        subvencion_saldo_130_bruto_eur=subvencion_saldo_130_bruto_eur,
        subvencion_importe_concedido_eur=subvencion_importe_concedido_eur,
        subvencion_transferencia_bruto_eur=subvencion_transferencia_bruto_eur,
        existencias_perfil_pct=anterior.existencias_perfil_pct,
        # Desglose del TOTAL de existencias de ESTE año — mismo criterio que activo_no_corriente:
        # perfil (%) constante, aplicado al agregado YA cuadrado de este año (incluye el efecto
        # de cualquier arquetipo que toque `existencias`, p. ej. 5 "exceso de stock": el exceso
        # se reparte automáticamente según el perfil fijo del sector, sin código especial).
        existencias_desglose_eur={
            componente: fraccion * balance_eur["existencias"]
            for componente, fraccion in anterior.existencias_perfil_pct.items()
        },
        periodificacion_activo_pct=anterior.periodificacion_activo_pct,
        periodificacion_pasivo_corto_pct=anterior.periodificacion_pasivo_corto_pct,
        periodificacion_pasivo_largo_pct=anterior.periodificacion_pasivo_largo_pct,
        deudores_perfil_pct=anterior.deudores_perfil_pct,
        deudores_desglose_eur=deudores_desglose_eur_año,
        acreedores_perfil_pct=anterior.acreedores_perfil_pct,
        acreedores_desglose_eur=acreedores_desglose_eur_año,
        operacion_vinculada_activa=parametros_operacion_vinculada.activa,
        operacion_vinculada_indice=parametros_operacion_vinculada.indice,
        operacion_vinculada_tipo=parametros_operacion_vinculada.tipo_operacion,
        operacion_vinculada_importe_eur=operacion_vinculada_importe_eur,
        operacion_vinculada_pct_mostrado=operacion_vinculada_pct_mostrado,
        inversion_grupo_largo_eur=inversion_grupo_largo_eur,
        deuda_grupo_largo_eur=deuda_grupo_largo_eur,
        provision_activa=parametros_provision.activa,
        provision_categoria=parametros_provision.categoria,
        provision_naturaleza_pyg=parametros_provision.naturaleza_pyg,
        provision_importe_dotado_eur=provision_importe_dotado_eur,
        provision_saldo_largo_eur=provision_saldo_largo_eur,
        provision_saldo_corto_eur=provision_saldo_corto_eur,
        provision_dotacion_eur=paso_provision.dotacion_eur,
        provision_aplicacion_eur=paso_provision.aplicacion_eur,
        provision_exceso_eur=paso_provision.exceso_eur,
        insolvencia_activa=parametros_insolvencia.activa,
        insolvencia_importe_dotado_eur=insolvencia_importe_dotado_eur,
        insolvencia_saldo_eur=paso_insolvencia.saldo_eur,
        insolvencia_exceso_acumulado_eur=paso_insolvencia.exceso_acumulado_eur,
        insolvencia_dotacion_eur=paso_insolvencia.dotacion_eur,
        insolvencia_aplicacion_eur=paso_insolvencia.aplicacion_eur,
        insolvencia_exceso_eur=paso_insolvencia.exceso_eur,
        insolvencia_deduccion_realizable_eur=paso_insolvencia.deduccion_realizable_eur,
        pyg_cifra_negocios_perfil_pct=anterior.pyg_cifra_negocios_perfil_pct,
        pyg_cifra_negocios_desglose_eur=pyg_cifra_negocios_desglose_eur_año,
        pyg_consumos_explotacion_perfil_pct=anterior.pyg_consumos_explotacion_perfil_pct,
        pyg_consumos_explotacion_desglose_eur=pyg_consumos_explotacion_desglose_eur_año,
        pyg_otros_gastos_explot_perfil_pct=anterior.pyg_otros_gastos_explot_perfil_pct,
        pyg_otros_gastos_explot_desglose_eur=pyg_otros_gastos_explot_desglose_eur_año,
        pyg_gastos_personal_desglose_eur=pyg_gastos_personal_desglose_eur_año,
        pyg_ingresos_financieros_desglose_eur=pyg_ingresos_financieros_desglose_eur_año,
        deudas_fin_fraccion_total=anterior.deudas_fin_fraccion_total,
        deudas_fin_fraccion_largo=anterior.deudas_fin_fraccion_largo,
        deudas_fin_largo_desglose_eur=deudas_fin_largo_desglose_eur_año,
        deudas_fin_corto_desglose_eur=deudas_fin_corto_desglose_eur_año,
        deudas_socios_activa=anterior.deudas_socios_activa,
        otras_deudas_largo_perfil_pct=anterior.otras_deudas_largo_perfil_pct,
        otras_deudas_corto_resto_perfil_pct=anterior.otras_deudas_corto_resto_perfil_pct,
        otras_deudas_largo_desglose_eur=otras_deudas_largo_desglose_eur_año,
        otras_deudas_corto_desglose_eur=otras_deudas_corto_desglose_eur_año,
        aapp_pendiente_corto_pct=aapp_pendiente_corto_pct_año,
    )


def _fusionar_masa_circulante(efectos_activos: tuple[EfectoActivo, ...]) -> tuple[EfectoActivo, ...]:
    """Regla de composición para la combinación de arquetipos (sección 2.12) cuando dos o más
    arquetipos activos declaran un `EfectoMasaCirculante` sobre la MISMA variable (único caso
    real entre las 6 combinaciones recomendadas de la sección 2.26: arquetipos 1 y 5, ambos
    sobre `existencias`, Combo F): se combinan en un único `EfectoActivo`, sumando sus
    `intensidad_efectiva`/`intensidad_base` individuales, y se aplica la fórmula de continuidad
    (`_masa_circulante_objetivo`) UNA sola vez con la intensidad combinada — no se encadenan dos
    aplicaciones sucesivas (que sería multiplicativo y dependiente de un orden arbitrario entre
    arquetipos). El suelo/techo de plausibilidad (`FRACCION_MINIMA/MAXIMA_VS_HUBER`) actúa igual
    que siempre, como límite conjunto, sin cambios de código: ya protege una intensidad
    combinada extrema (p. ej. 0,50+0,50 en "fuerte"+"fuerte").

    Requiere que las variables coincidentes compartan también `formula` y `ratio_catalogo` (es
    el caso de 1 y 5: ambos anclan a `ratios.rotacion_existencias` con `formula="rotacion"`) y
    la MISMA `direccion` — direcciones opuestas sobre la misma variable no están soportadas
    (no ocurre en los 6 combos recomendados): se lanza `EvolucionArquetipoError` explícito en
    vez de elegir una en silencio."""
    por_variable: dict[str, list[EfectoActivo]] = {}
    resto: list[EfectoActivo] = []
    for ea in efectos_activos:
        if isinstance(ea.efecto, EfectoMasaCirculante):
            por_variable.setdefault(ea.efecto.variable, []).append(ea)
        else:
            resto.append(ea)

    fusionados: list[EfectoActivo] = []
    for variable, grupo in por_variable.items():
        if len(grupo) == 1:
            fusionados.append(grupo[0])
            continue
        direcciones = {ea.efecto.direccion for ea in grupo}
        formulas = {ea.efecto.formula for ea in grupo}
        ratios = {ea.efecto.ratio_catalogo for ea in grupo}
        if len(direcciones) > 1:
            raise EvolucionArquetipoError(
                f"Combinación no soportada: efectos de masa_circulante con direcciones opuestas "
                f"sobre '{variable}' ({sorted(ea.arquetipo_id for ea in grupo)})"
            )
        if len(formulas) > 1 or len(ratios) > 1:
            raise EvolucionArquetipoError(
                f"Combinación no soportada: efectos de masa_circulante sobre '{variable}' con "
                f"formula/ratio_catalogo distintos ({sorted(ea.arquetipo_id for ea in grupo)})"
            )
        base = grupo[0]
        fusionados.append(
            EfectoActivo(
                efecto=base.efecto,
                arquetipo_id="+".join(sorted(ea.arquetipo_id for ea in grupo)),
                numero=base.numero,
                intensidad_efectiva=sum(ea.intensidad_efectiva for ea in grupo),
                intensidad_base=sum(ea.intensidad_base for ea in grupo),
            )
        )
    return tuple(resto) + tuple(fusionados)


def generar_evolucion_combinada(
    sector: str,
    segmento: str,
    ventas_objetivo_2023: float,
    semilla: int,
    arquetipos_intensidades: dict[str, str],
    catalogo: pd.DataFrame | None = None,
    arquetipos: dict[str, DefinicionArquetipo] | None = None,
    dependencia_pocos_clientes_activo: bool = False,
    modo_generacion: str = "aleatorio",
) -> EvolucionArquetipo:
    """Genera 3 ejercicios combinando los arquetipos CUANTITATIVOS de `arquetipos_intensidades`
    ({arquetipo_id: intensidad} — una intensidad por arquetipo, sección 2.12), fusionando sus
    `efectos`. `generar_evolucion_arquetipo` (un único arquetipo) es un envoltorio de esta
    función con un diccionario de un solo elemento — el caso individual ES, literalmente, una
    combinación de tamaño 1, no una implementación paralela: cualquier test que siga pasando
    para el caso individual lo demuestra directamente, no por diseño solamente.

    Solo acepta arquetipos de `clase="cuantitativo"` — los de `clase="memoria_pura"` (7, 19, 20,
    21, 22) no tienen nada que evolucionar aquí, ver `motor.memoria` y `generar_caso_combinado`,
    que sí orquesta ambas clases juntas.

    `modo_generacion` ("tipico"/"atipico"/"aleatorio", por defecto — Fase 4 Ronda 2 punto 2):
    fuerza la rama típica/atípica (y, en los mecanismos transversales binarios — provisión/
    insolvencia/subvención de fondo — la rama activa/inactiva) para TODO el caso, los 3 años,
    sin tocar ningún helper interno — ver docstring de `motor.ruido`. Las "variantes de examen"
    (sección 2.16) son, simplemente, llamar a esta función varias veces con `modo_generacion=
    "tipico"` y semillas distintas — no hay un mecanismo aparte."""
    _token_modo_generacion = activar_modo_generacion(modo_generacion)
    try:
        return _generar_evolucion_combinada_interno(
            sector, segmento, ventas_objetivo_2023, semilla, arquetipos_intensidades,
            catalogo, arquetipos, dependencia_pocos_clientes_activo, modo_generacion,
        )
    finally:
        desactivar_modo_generacion(_token_modo_generacion)


def _generar_evolucion_combinada_interno(
    sector: str,
    segmento: str,
    ventas_objetivo_2023: float,
    semilla: int,
    arquetipos_intensidades: dict[str, str],
    catalogo: pd.DataFrame | None,
    arquetipos: dict[str, DefinicionArquetipo] | None,
    dependencia_pocos_clientes_activo: bool,
    modo_generacion: str,
) -> EvolucionArquetipo:
    """Cuerpo real de `generar_evolucion_combinada` — aislado en su propia función para que el
    `try/finally` de activación de `modo_generacion` no tenga que reindentar el resto del cuerpo
    (~380 líneas). No debe llamarse directamente."""
    if not arquetipos_intensidades:
        raise EvolucionArquetipoError("No se ha indicado ningún arquetipo")
    for arquetipo_id, intensidad in arquetipos_intensidades.items():
        if intensidad not in INTENSIDADES_VALIDAS:
            raise EvolucionArquetipoError(
                f"Intensidad '{intensidad}' no válida para '{arquetipo_id}'. Debe ser una de: {sorted(INTENSIDADES_VALIDAS)}"
            )

    if arquetipos is None:
        arquetipos = cargar_arquetipos()
    for arquetipo_id in arquetipos_intensidades:
        if arquetipo_id not in arquetipos:
            raise EvolucionArquetipoError(
                f"Arquetipo '{arquetipo_id}' no reconocido. Disponibles: {sorted(arquetipos)}"
            )
        if arquetipos[arquetipo_id].clase != "cuantitativo":
            raise EvolucionArquetipoError(
                f"'{arquetipo_id}' no es un arquetipo cuantitativo (clase='{arquetipos[arquetipo_id].clase}') "
                "— no genera evolución numérica, ver motor.memoria / generar_caso_combinado"
            )
    definiciones = {aid: arquetipos[aid] for aid in arquetipos_intensidades}

    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    fila = resolver_fila_sector(catalogo, sector, segmento)

    # NO se pasa `modo_generacion` aquí a propósito: `generar_empresa_base` ya hereda el modo
    # activado justo arriba, por defecto `None` — ver su docstring para el porqué (un valor por
    # defecto concreto habría hecho que el año base volviera siempre a "aleatorio", bug real
    # detectado y corregido antes de comitear, ver motor/empresa_base.py).
    empresa_2023 = generar_empresa_base(sector, segmento, ventas_objetivo_2023, semilla, catalogo=catalogo)
    ejercicios: dict[int, EjercicioEmpresa] = {AÑO_BASE: _ejercicio_desde_empresa_base(empresa_2023)}

    # La semilla mezcla `semilla` con un hash estable (zlib.crc32, no `hash()` de Python) de
    # sector+segmento — NO de intensidad NI del conjunto de arquetipos activos: por diseño, la
    # misma semilla+sector+segmento debe compartir el mismo "ruido de fondo" (crecimiento_pleno_
    # objetivo cuando ningún arquetipo activo define rango propio, y la PyG de 2024/2025 para las
    # primitivas que nadie toca) sea cual sea el arquetipo o la COMBINACIÓN de arquetipos que se
    # le aplique encima — es la propiedad, ya validada para el caso individual, que permite
    # comparar "la misma empresa" bajo distintas historias (un arquetipo, u otro, o una
    # combinación); se preserva sin tocar la fórmula al extenderla a combinaciones. (Se consideró
    # mezclar también el conjunto de arquetipos activos, como en el sorteo de `nota_memoria` más
    # abajo, pero se descartó explícitamente: cambiaría el ruido de fondo del caso individual —
    # que es un caso particular de esta misma función — y rompería los valores de referencia ya
    # fijados en los tests de regresión, sin ninguna necesidad real: el "ruido de fondo" no es un
    # sorteo nuevo que arriesgue sesgo por combinación, es el mismo sorteo de siempre.)
    entropia_sector = zlib.crc32(f"{sector}|{segmento}".encode("utf-8"))
    semilla_secuencia = np.random.SeedSequence([semilla, entropia_sector])
    hijo_tendencia, hijo_2024, hijo_2025 = semilla_secuencia.spawn(3)
    rng_tendencia = np.random.default_rng(hijo_tendencia)
    rngs_pyg = {2024: np.random.default_rng(hijo_2024), 2025: np.random.default_rng(hijo_2025)}

    # RNG dedicado e independiente para `notas_memoria` (arquetipos 10/16/18): NO reutiliza
    # rngs_pyg (ver hallazgo de sesgo documentado en docs/decisiones_plausibilidad.md). Uno por
    # arquetipo activo (cada uno con su propia intensidad) — ya generaliza sin cambios a
    # combinaciones: cada arquetipo sortea su nota de forma independiente de los demás, mismo
    # patrón que motor.memoria._rng_memoria (que también mezcla arquetipo_id).
    rngs_nota_por_arquetipo: dict[str, dict[int, np.random.Generator]] = {}
    for arquetipo_id, intensidad in arquetipos_intensidades.items():
        entropia_caso = zlib.crc32(f"{sector}|{segmento}|{intensidad}|{arquetipo_id}".encode("utf-8"))
        secuencia_notas = np.random.SeedSequence([semilla, entropia_caso])
        hijo_nota_2024, hijo_nota_2025 = secuencia_notas.spawn(2)
        rngs_nota_por_arquetipo[arquetipo_id] = {
            2024: np.random.default_rng(hijo_nota_2024),
            2025: np.random.default_rng(hijo_nota_2025),
        }

    def _rng_nota_del_año(año: int) -> np.random.Generator:
        # El arquetipo (de menor número) cuyo propio efecto puede generar una nota_memoria en
        # evolucion_arquetipo.py (10 base dinámica, 16 reclasificación con dirección<0, 18
        # adquisición) recibe SU rng — en los 6 combos recomendados nunca coinciden dos de estos
        # tres a la vez. Si ninguno de los activos genera nota, se devuelve cualquiera (no se
        # consumirá).
        for arquetipo_id in sorted(definiciones, key=lambda aid: definiciones[aid].numero):
            genera_nota = any(
                isinstance(e, EfectoAdquisicion)
                or (isinstance(e, EfectoReclasificacionDeuda) and e.direccion < 0)
                or (isinstance(e, EfectoPygPrimitiva) and e.primitiva in SUBTOTAL_PYG_BASE_DINAMICA_DE_PRIMITIVA)
                for e in definiciones[arquetipo_id].efectos
            )
            if genera_nota:
                return rngs_nota_por_arquetipo[arquetipo_id][año]
        return next(iter(rngs_nota_por_arquetipo.values()))[año]

    # rango_crecimiento_pleno: si algún arquetipo activo define uno propio (hoy, solo el 1), se
    # usa el de menor número (orden determinista) con SU PROPIA intensidad para escalar por
    # fracción de año — no hay más de uno en los 6 combos recomendados, así que no hace falta una
    # regla de desempate más allá de "el de menor número", documentada por si algún día aplica.
    arquetipo_con_rango = next(
        (
            aid
            for aid in sorted(definiciones, key=lambda a: definiciones[a].numero)
            if definiciones[aid].rango_crecimiento_pleno is not None
        ),
        None,
    )
    if arquetipo_con_rango is not None:
        bajo, alto = definiciones[arquetipo_con_rango].rango_crecimiento_pleno[arquetipos_intensidades[arquetipo_con_rango]]
    else:
        bajo, alto = RANGO_CRECIMIENTO_ORGANICO
    crecimiento_pleno_objetivo = bajo + rng_tendencia.random() * (alto - bajo)

    # Payout de dividendos (sección "Retención de beneficios/distribución a PN", decisiones_
    # plausibilidad.md #79-#80): sorteo ÚNICO por caso (mismo criterio que capital_social/
    # ventas_por_empleado/rotacion_activo — rasgo estructural de la empresa, no de un año
    # concreto; redibujarlo cada año reintroduciría el mismo tipo de acumulación de ruido que
    # #78 acaba de corregir), con `rng_tendencia` justo después de crecimiento_pleno_objetivo
    # (antes del sorteo CONDICIONAL de año_evento_puntual, para que su posición en la secuencia
    # no dependa de qué arquetipo esté activo). ROE_caso se sortea con el mismo ruido mixto
    # típico/atípico de siempre, centrado en `ratios.roe` real del sector (ninguna dispersión
    # inventada) — payout_caso = 1 − g/ROE_caso, recortado a [0, TECHO_PAYOUT_DIVIDENDOS]: nunca
    # negativo (sin sentido económico, "repartir negativo" sería una aportación de capital no
    # pedida) y el techo (100%) es una cota matemática, no un número elegido a ojo — con g>0 y
    # ROE_caso>0 el payout objetivo nunca lo alcanza (verificado: máximo 94,2% en los 27
    # sectores reales). Sectores/sorteos de ROE_caso <= g (payout objetivo negativo, clampado a
    # 0%) quedan sin efecto del mecanismo — limitación conocida y documentada, no forzada (mismo
    # criterio que el aviso de fiabilidad muestral del sector 30.3 en `coste_deuda`).
    huber_roe = fila["ratios.roe.huber_9y"]
    mad_roe = fila["ratios.roe.huber_scale_mad"]
    roe_caso, modo_roe_caso = _generar_partida(rng_tendencia, huber_roe, mad_roe)
    payout_caso = 0.0 if roe_caso <= 0 else min(max(1 - crecimiento_pleno_objetivo / roe_caso, 0.0), TECHO_PAYOUT_DIVIDENDOS)
    # Hallazgo de auditoría de trazabilidad: el modo típico/atípico de ROE_caso (rasgo
    # estructural del caso, sorteado una vez — mismo criterio que `rotacion_activo`) se
    # descartaba con `_`. Se expone en `modos["caso.roe"]` del año base — mismo "cajón" donde ya
    # vive `rotacion_activo` (otro rasgo de caso sorteado una vez, no por año) — para que
    # `resumen_particularidades_caso` (motor/resumen_caso.py) no tenga que buscarlo aparte.
    ejercicios[AÑO_BASE] = replace(
        ejercicios[AÑO_BASE], modos={**ejercicios[AÑO_BASE].modos, "caso.roe": modo_roe_caso}
    )

    # Año único del suceso puntual (arquetipo 12, "resultado extraordinario"): sorteado 50/50
    # entre 2024 y 2025 con rng_tendencia — mismo generador ya independiente por sector+segmento,
    # NO por intensidad (el año en que ocurrió el suceso es un hecho de la propia empresa: no
    # debe cambiar solo porque se pida una intensidad distinta del mismo caso, igual que
    # crecimiento_pleno_objetivo). Solo se consume si algún arquetipo activo tiene un
    # EfectoEventoPuntual (en los 6 combos, como mucho uno), así que no afecta al estado de
    # rng_tendencia para el resto de combinaciones.
    año_evento_puntual: int | None = None
    if any(isinstance(e, EfectoEventoPuntual) for definicion in definiciones.values() for e in definicion.efectos):
        año_evento_puntual = 2024 if rng_tendencia.integers(2) == 0 else 2025

    # --- Cobertura/subvención (grupo 8/9, ver motor/coberturas_subvenciones.py) — parámetros
    # sorteados UNA vez por caso (no por año), igual criterio que crecimiento_pleno_objetivo/
    # año_evento_puntual: son rasgos estructurales del caso, no algo que deba re-sortearse cada
    # ejercicio. ---
    cobertura_activa = "coberturas" in definiciones
    if cobertura_activa:
        cobertura_pct_deuda, cobertura_plazo_residual_inicial_años, cobertura_eficacia_pct = sortear_parametros_cobertura(
            sector, segmento, semilla, arquetipos_intensidades["coberturas"]
        )
    else:
        cobertura_pct_deuda = cobertura_plazo_residual_inicial_años = cobertura_eficacia_pct = 0.0

    # Subvención: vía "17" (capex_elevado activo en el caso) y vía "de fondo" (propensión por
    # categoría de sector, evaluada solo si el 17 NO está activo) son mutuamente excluyentes —
    # ver docstring de `_evolucionar_un_año`.
    subvencion_via_capex17 = "capex_elevado" in definiciones
    if subvencion_via_capex17:
        subvencion_baseline_activa = False
        subvencion_baseline_año_concesion = None
    else:
        categoria_sector_caso = categoria_de_sector(sector)
        subvencion_baseline_activa, subvencion_baseline_año_concesion = sortear_subvencion_baseline(
            sector, segmento, semilla, categoria_sector_caso
        )

    parametros_grupo89 = ParametrosGrupo89(
        cobertura_activa=cobertura_activa,
        cobertura_pct_deuda=cobertura_pct_deuda,
        cobertura_plazo_residual_inicial_años=cobertura_plazo_residual_inicial_años,
        cobertura_eficacia_pct=cobertura_eficacia_pct,
        subvencion_via_capex17=subvencion_via_capex17,
        subvencion_baseline_activa=subvencion_baseline_activa,
        subvencion_baseline_año_concesion=subvencion_baseline_año_concesion,
    )
    if cobertura_activa:
        # El nocional (y el plazo residual) de la cobertura se establecen YA en el año base
        # (2023) — si se dejaran en su valor por defecto (0.0), el primer Δr real (2024) se
        # multiplicaría por un nocional nulo y la cobertura quedaría inerte un año entero. El
        # valor razonable del swap (`cobertura_valor_swap_eur`/`..._saldo_1340_bruto_eur`) SÍ
        # se queda en 0 en 2023: no hay Δr que computar contra un año anterior a la serie (se
        # trata 2023 como el origen de medición, hipótesis de diseño ya documentada).
        deuda_financiera_2023_eur = (
            ejercicios[AÑO_BASE].balance_eur["deudas_fin_largo"] + ejercicios[AÑO_BASE].balance_eur["deudas_fin_corto"]
        )
        ejercicios[AÑO_BASE] = replace(
            ejercicios[AÑO_BASE],
            cobertura_activa=True,
            cobertura_pct_deuda=cobertura_pct_deuda,
            cobertura_eficacia_pct=cobertura_eficacia_pct,
            cobertura_nocional_vivo_eur=cobertura_pct_deuda * deuda_financiera_2023_eur,
            cobertura_plazo_residual_años=cobertura_plazo_residual_inicial_años,
        )

    # --- Operaciones vinculadas (arquetipo 20) — parámetros sorteados UNA vez por caso, mismo
    # criterio que cobertura/subvención. Igual que cobertura, la magnitud del año base (2023) se
    # fija YA aquí (no en `_evolucionar_un_año`, que solo procesa 2024/2025): para los 2 tipos
    # COMERCIALES (facturación/arrendamiento/asistencia técnica), se fuerza "desde 2023" la
    # sub-partida correspondiente del perfil de deudores/acreedores (mismo criterio "perfil fijo,
    # desglose recalculado cada año" que el resto de este bloque); para los 2 tipos FINANCIEROS
    # (préstamo a matriz/financiación recibida), se inyecta directamente sobre el balance YA
    # cuadrado de 2023 (auto-referencial: usa el propio patrimonio_neto/deuda financiera de 2023,
    # no hay "año anterior" dentro de la serie) — sin pasar por la contención de endeudamiento
    # (2023 nunca se contiene, igual que el resto de masas del año base). ---
    operacion_vinculada_activa = "operaciones_vinculadas" in definiciones
    if operacion_vinculada_activa:
        parametros_operacion_vinculada = _sortear_operacion_vinculada(
            sector, segmento, semilla, arquetipos_intensidades["operaciones_vinculadas"]
        )
    else:
        parametros_operacion_vinculada = PARAMETROS_OPERACION_VINCULADA_INACTIVOS

    if parametros_operacion_vinculada.tipo_operacion in COMPONENTE_DESGLOSE_POR_TIPO:
        desglose_nombre, componente = COMPONENTE_DESGLOSE_POR_TIPO[parametros_operacion_vinculada.tipo_operacion]
        magnitud_2023_eur = _magnitud_operacion_vinculada(
            ejercicios[AÑO_BASE].ventas, ejercicios[AÑO_BASE].balance_eur, parametros_operacion_vinculada.tipo_operacion
        )
        importe_2023_eur = max(
            parametros_operacion_vinculada.pct_objetivo * magnitud_2023_eur, SUELO_IMPORTE_VINCULADAS_EUR
        )
        masa_nombre = "realizable" if desglose_nombre == "deudores" else "acreedores_comerciales"
        masa_2023_eur = ejercicios[AÑO_BASE].balance_eur[masa_nombre]
        fraccion_objetivo = importe_2023_eur / masa_2023_eur if masa_2023_eur > 0 else 0.0
        perfil_base = (
            ejercicios[AÑO_BASE].deudores_perfil_pct if desglose_nombre == "deudores" else ejercicios[AÑO_BASE].acreedores_perfil_pct
        )
        nuevo_perfil = _perfil_con_componente_forzado(perfil_base, componente, fraccion_objetivo)
        nuevo_desglose = {clave: fraccion * masa_2023_eur for clave, fraccion in nuevo_perfil.items()}
        if desglose_nombre == "deudores":
            ejercicios[AÑO_BASE] = replace(
                ejercicios[AÑO_BASE], deudores_perfil_pct=nuevo_perfil, deudores_desglose_eur=nuevo_desglose,
            )
        else:
            ejercicios[AÑO_BASE] = replace(
                ejercicios[AÑO_BASE], acreedores_perfil_pct=nuevo_perfil, acreedores_desglose_eur=nuevo_desglose,
            )
    elif parametros_operacion_vinculada.tipo_operacion == "prestamo_matriz":
        importe_bruto_2023_eur = max(
            parametros_operacion_vinculada.pct_objetivo * ejercicios[AÑO_BASE].balance_eur["patrimonio_neto"],
            SUELO_IMPORTE_VINCULADAS_EUR,
        )
        disponible_2023_eur = ejercicios[AÑO_BASE].balance_eur["disponible"]
        inversion_grupo_largo_2023_eur = min(
            importe_bruto_2023_eur, max(0.0, disponible_2023_eur) * TECHO_FRACCION_DISPONIBLE_PRESTAMO_MATRIZ
        )
        balance_2023 = dict(ejercicios[AÑO_BASE].balance_eur)
        balance_2023["activo_no_corriente"] += inversion_grupo_largo_2023_eur
        balance_2023["disponible"] -= inversion_grupo_largo_2023_eur
        balance_2023["activo_corriente"] -= inversion_grupo_largo_2023_eur
        ejercicios[AÑO_BASE] = replace(
            ejercicios[AÑO_BASE], balance_eur=balance_2023, inversion_grupo_largo_eur=inversion_grupo_largo_2023_eur,
        )
    elif parametros_operacion_vinculada.tipo_operacion == "financiacion_recibida_grupo":
        deuda_fin_2023_eur = (
            ejercicios[AÑO_BASE].balance_eur["deudas_fin_largo"] + ejercicios[AÑO_BASE].balance_eur["deudas_fin_corto"]
        )
        deuda_grupo_largo_2023_eur = max(
            parametros_operacion_vinculada.pct_objetivo * deuda_fin_2023_eur, SUELO_IMPORTE_VINCULADAS_EUR
        )
        balance_2023 = dict(ejercicios[AÑO_BASE].balance_eur)
        balance_2023["otras_deudas_largo"] += deuda_grupo_largo_2023_eur
        balance_2023["pasivo_no_corriente"] += deuda_grupo_largo_2023_eur
        balance_2023["disponible"] += deuda_grupo_largo_2023_eur
        balance_2023["activo_corriente"] += deuda_grupo_largo_2023_eur
        ejercicios[AÑO_BASE] = replace(
            ejercicios[AÑO_BASE], balance_eur=balance_2023, deuda_grupo_largo_eur=deuda_grupo_largo_2023_eur,
        )
    if operacion_vinculada_activa:
        magnitud_2023_mostrado_eur = _magnitud_operacion_vinculada(
            ejercicios[AÑO_BASE].ventas, ejercicios[AÑO_BASE].balance_eur, parametros_operacion_vinculada.tipo_operacion
        )
        importe_2023_mostrado_eur = _importe_operacion_vinculada_eur(
            parametros_operacion_vinculada.tipo_operacion,
            ejercicios[AÑO_BASE].deudores_desglose_eur,
            ejercicios[AÑO_BASE].acreedores_desglose_eur,
            ejercicios[AÑO_BASE].inversion_grupo_largo_eur,
            ejercicios[AÑO_BASE].deuda_grupo_largo_eur,
        )
        ejercicios[AÑO_BASE] = replace(
            ejercicios[AÑO_BASE],
            operacion_vinculada_activa=True,
            operacion_vinculada_indice=parametros_operacion_vinculada.indice,
            operacion_vinculada_tipo=parametros_operacion_vinculada.tipo_operacion,
            operacion_vinculada_importe_eur=importe_2023_mostrado_eur,
            operacion_vinculada_pct_mostrado=(
                importe_2023_mostrado_eur / magnitud_2023_mostrado_eur * 100 if magnitud_2023_mostrado_eur > 0 else 0.0
            ),
        )

    # --- Provisiones a largo/corto plazo (tercer lote, motor/provisiones.py) — probabilidad de
    # fondo INDEPENDIENTE de cualquier arquetipo activo (a diferencia de grupo89/operaciones
    # vinculadas, que solo se evalúan si su propio arquetipo está en `definiciones`): sorteada
    # SIEMPRE, para que pueda aparecer también con el arquetipo 6 ("línea base sana") o con
    # cualquier otro, tal como pide el encargo. Nunca dotada en el año base (2023) — el año de
    # dotación siempre es 2024 o 2025 (ver `sortear_provision_baseline`), así que no hace falta
    # ningún override de `ejercicios[AÑO_BASE]` (a diferencia de cobertura/operaciones
    # vinculadas, que sí pueden empezar ya en 2023). ---
    parametros_provision = sortear_provision_baseline(
        sector, segmento, semilla, categoria_de_sector(sector), tier_existencias_de_sector(sector)
    )

    # --- Deterioro de valor de créditos por operaciones comerciales (cuenta 490, motor/
    # insolvencias.py) — probabilidad de fondo INDEPENDIENTE de cualquier arquetipo activo (mismo
    # criterio que provisiones), anclada a `ratios.cobro_dias` del propio sector/segmento. Boost
    # de probabilidad/magnitud si el arquetipo 4 ("deterioro_ciclo_caja", `clase="cuantitativo"`,
    # detectable directamente en `definiciones`) o el 7 ("dependencia_pocos_clientes",
    # `clase="memoria_pura"`, sin efectos numéricos propios — no puede detectarse aquí, así que lo
    # señala quien orquesta ambas clases, `motor.memoria.generar_caso_combinado`, vía el parámetro
    # `dependencia_pocos_clientes_activo`) están activos. ---
    deterioro_ciclo_caja_activo = "deterioro_ciclo_caja" in definiciones
    parametros_insolvencia = sortear_insolvencia_baseline(
        sector,
        segmento,
        semilla,
        fila["ratios.cobro_dias.huber_9y"],
        deterioro_ciclo_caja_activo,
        dependencia_pocos_clientes_activo,
    )

    anterior = ejercicios[AÑO_BASE]
    for año in (2024, 2025):
        fraccion = FRACCION_AÑO[año]
        crecimiento_ventas = (
            crecimiento_pleno_objetivo * fraccion if arquetipo_con_rango is not None else crecimiento_pleno_objetivo
        )

        efectos_activos: list[EfectoActivo] = []
        for arquetipo_id, definicion in definiciones.items():
            escala_intensidad = INTENSIDAD_BASE_POR_ARQUETIPO.get(arquetipo_id, INTENSIDAD_BASE)
            intensidad_base_arq = escala_intensidad[arquetipos_intensidades[arquetipo_id]]
            intensidad_efectiva_arq = intensidad_base_arq * fraccion
            for efecto in definicion.efectos:
                efectos_activos.append(
                    EfectoActivo(
                        efecto=efecto,
                        arquetipo_id=arquetipo_id,
                        numero=definicion.numero,
                        intensidad_efectiva=intensidad_efectiva_arq,
                        intensidad_base=intensidad_base_arq,
                    )
                )
        efectos_activos = list(_fusionar_masa_circulante(tuple(efectos_activos)))

        ejercicio = _evolucionar_un_año(
            año,
            anterior,
            fila,
            rngs_pyg[año],
            _rng_nota_del_año(año),
            crecimiento_ventas,
            año_evento_puntual,
            tuple(efectos_activos),
            sector,
            segmento,
            semilla,
            parametros_grupo89,
            parametros_operacion_vinculada,
            parametros_provision,
            parametros_insolvencia,
            payout_caso=payout_caso,
            deterioro_ciclo_caja_activo=deterioro_ciclo_caja_activo,
            dependencia_pocos_clientes_activo=dependencia_pocos_clientes_activo,
        )
        ejercicios[año] = ejercicio
        anterior = ejercicio

    if len(arquetipos_intensidades) == 1:
        # Formato idéntico al histórico (un solo id, una sola intensidad) — no el formato "id:
        # intensidad" de las combinaciones — para que EvolucionArquetipo.arquetipo/.intensidad
        # no cambien para ningún caso individual ya existente.
        (arquetipo_str,) = arquetipos_intensidades.keys()
        (intensidad_str,) = arquetipos_intensidades.values()
    else:
        arquetipo_str = "+".join(sorted(arquetipos_intensidades))
        intensidad_str = "+".join(f"{aid}:{arquetipos_intensidades[aid]}" for aid in sorted(arquetipos_intensidades))

    # Validación de plausibilidad del caso completo (sección 2.13) — pasada FINAL, después de
    # aplicar todos los arquetipos, sobre los 3 años ya generados. `plantilla_estimada` reutiliza
    # el mismo mecanismo ya construido para la clasificación legal (`motor.clasificacion_legal`)
    # — sorteo único por caso (sector+segmento+semilla, no por año), escalado por la cifra de
    # negocio YA generada de cada año — no un sorteo nuevo.
    ventas_empleado_miles_eur, _ = estimar_ventas_por_empleado(sector, segmento, semilla, catalogo)
    plantilla_por_año = {
        año: estimar_plantilla(ejercicio.pyg_eur["cifra_negocios"], ventas_empleado_miles_eur)
        for año, ejercicio in ejercicios.items()
    }
    plausibilidad = _evaluar_plausibilidad_caso(ejercicios, fila, plantilla_por_año)

    return EvolucionArquetipo(
        sector_codigo=sector,
        sector_nombre=fila["sector"],
        segmento=segmento,
        arquetipo=arquetipo_str,
        intensidad=intensidad_str,
        semilla=semilla,
        crecimiento_pleno_objetivo=crecimiento_pleno_objetivo,
        ejercicios=ejercicios,
        catalogo_version=catalogo.attrs.get("catalogo_version", "desconocida"),
        plausibilidad=plausibilidad,
        modo_generacion=modo_generacion,
    )


def generar_evolucion_arquetipo(
    sector: str,
    segmento: str,
    ventas_objetivo_2023: float,
    semilla: int,
    intensidad: str,
    arquetipo_id: str,
    catalogo: pd.DataFrame | None = None,
    arquetipos: dict[str, DefinicionArquetipo] | None = None,
    modo_generacion: str = "aleatorio",
) -> EvolucionArquetipo:
    """Genera 3 ejercicios (2023 base, 2024 y 2025 con `arquetipo_id` aplicado de forma
    progresiva: 60% de la intensidad en 2024, 100% en 2025), encadenados entre sí.

    `arquetipo_id` es una clave de `data/arquetipos.json` (ver `motor.arquetipos`). Envoltorio
    de `generar_evolucion_combinada` con un único arquetipo — ver docstring de esa función y la
    sección "Combinación de arquetipos" del docstring del módulo. `modo_generacion` se reenvía
    tal cual — ver docstring de `generar_evolucion_combinada` (Fase 4 Ronda 2 punto 2)."""
    return generar_evolucion_combinada(
        sector, segmento, ventas_objetivo_2023, semilla, {arquetipo_id: intensidad},
        catalogo=catalogo, arquetipos=arquetipos, modo_generacion=modo_generacion,
    )
