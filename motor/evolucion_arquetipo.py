"""Evolución de una empresa a lo largo de 3 ejercicios (2023-2025) aplicando UN arquetipo.

Motor GENÉRICO: qué arquetipo se aplica es un dato (`data/arquetipos.json`, cargado por
`motor.arquetipos`), no código hardcodeado por arquetipo. Este módulo separa dos cosas:

- **Mecanismo general** (reutilizable para cualquier arquetipo cuantitativo que encaje en una
  de las 4 formas de efecto soportadas): modelo de continuidad año a año de un ratio, cascada
  de PyG, enlace deuda-interés, contención de plausibilidad del endeudamiento, cuadre del
  balance. Vive en funciones de este módulo que no mencionan ningún arquetipo por su nombre.
- **Lo específico de cada arquetipo**: qué variable mueve, en qué dirección y contra qué
  ratio ancla — vive SOLO en `data/arquetipos.json`, no en código.

No todos los arquetipos cuantitativos de la sección 2.24 encajan en las 7 formas ya
implementadas (masa_circulante, pyg_primitiva, apalancamiento, tesoreria, reclasificacion_deuda,
evento_puntual, capex) — ver el informe de clasificación en el mensaje que acompaña a cada
commit para el detalle de cuáles sí y cuáles necesitarían una forma nueva (o no aplican al
motor en absoluto, como el arquetipo 13). Los arquetipos cualitativos puros (7, 19, 20, 21, 22)
no pasan por este mecanismo en absoluto.

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
    EfectoApalancamiento,
    EfectoCapex,
    EfectoEventoPuntual,
    EfectoMasaCirculante,
    EfectoPygPrimitiva,
    EfectoReclasificacionDeuda,
    EfectoTesoreria,
    cargar_arquetipos,
)
from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import (
    TOLERANCIA_CUADRE_EUR,
    EmpresaBase,
    EmpresaBaseError,
    generar_empresa_base,
    resolver_fila_sector,
)
from motor.empresa_base import _completar_pyg_con_deuda, _generar_pyg_hasta_baii  # reutiliza la cascada de PyG

AÑOS = (2023, 2024, 2025)
AÑO_BASE = 2023

# Trazabilidad (sección 2.15): única versión normativa en juego por ahora.
PGC_VERSION = "PGC RD 1514/2007"

INTENSIDADES_VALIDAS = frozenset({"leve", "moderado", "fuerte"})
INTENSIDAD_BASE = {"leve": 0.15, "moderado": 0.30, "fuerte": 0.50}
FRACCION_AÑO = {2024: 0.6, 2025: 1.0}

# Crecimiento de ventas para arquetipos que no definen su propio rango_crecimiento_pleno (ver
# docstring del módulo). Fijo, no escalado por intensidad ni por fracción del año.
RANGO_CRECIMIENTO_ORGANICO = (0.01, 0.04)

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
NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE = (
    "El incremento de los gastos de personal respecto al ejercicio anterior se explica por la "
    "actualización salarial derivada del convenio colectivo aplicable, que absorbió parte de la "
    "mejora de eficiencia operativa prevista para el ejercicio.",
    "Durante el ejercicio se incorporó personal cualificado adicional para sostener el "
    "crecimiento de la actividad, lo que elevó los gastos de personal por encima de lo "
    "inicialmente previsto, pese a la mejora del margen operativo en el resto de partidas.",
    "Los gastos de personal del ejercicio incluyen indemnizaciones puntuales asociadas a bajas "
    "voluntarias y ajustes de plantilla no recurrentes, que no se esperan repetir en próximos "
    "ejercicios.",
    "El aumento de los gastos de personal responde en parte al incremento de las cotizaciones "
    "sociales aplicable durante el ejercicio, un factor ajeno a la gestión operativa de la "
    "empresa.",
    "Se liquidaron durante el ejercicio complementos e incentivos variables ligados al "
    "cumplimiento de objetivos del ejercicio anterior, lo que elevó puntualmente los gastos de "
    "personal.",
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
NOTAS_MEMORIA_RIESGO_REFINANCIACION = (
    "Durante el ejercicio venció y se reclasificó a corto plazo una póliza de crédito sindicada "
    "que la sociedad tiene previsto renovar en los próximos meses, sin que a la fecha de "
    "formulación de las cuentas se haya formalizado la renovación.",
    "El endurecimiento de las condiciones de financiación bancaria ha llevado a la entidad a "
    "priorizar líneas de crédito a corto plazo frente a la refinanciación a largo, lo que "
    "concentra vencimientos relevantes en los próximos doce meses.",
    "Parte de la deuda a largo plazo se ha reclasificado a corto plazo al no cumplirse "
    "determinados ratios financieros (covenants) exigidos por las entidades acreedoras, que "
    "otorgan a estas el derecho a exigir el vencimiento anticipado.",
    "La sociedad ha optado por un mayor uso de financiación a corto plazo (pólizas y descuento "
    "comercial) para cubrir necesidades puntuales de circulante, en sustitución de la "
    "financiación a largo plazo históricamente empleada.",
    "Está en curso un proceso de refinanciación con el pool bancario que, a la fecha de cierre "
    "del ejercicio, aún no se ha formalizado, por lo que la deuda afectada permanece "
    "clasificada a corto plazo hasta la firma del nuevo acuerdo.",
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
    riesgo_plausibilidad_pyg: bool = False  # True si algún efecto pyg_primitiva topó el techo/suelo de su subtotal
    pyg_subtotales_sin_contener: dict[str, float] = field(default_factory=dict)  # {subtotal: valor antes de topar}
    pyg_contencion_al_limite: bool = False  # True si un efecto de "base dinámica" (baii) tuvo que invertir su
    # sentido para no rebasar el techo/suelo del sector — amortiguar su propia intensidad a cero no bastaba
    # (el desbordamiento venía del ruido de la base ese año, no del arquetipo). Ver docstring del módulo.
    nota_memoria: str | None = None  # cobertura narrativa de negocio cuando pyg_contencion_al_limite=True

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
        ratio_anterior = anterior.ventas / anterior.balance_eur[efecto.variable]
        nuevo_ratio = _mover_ratio_continuo(ratio_anterior, efecto.direccion, intensidad_efectiva, huber)
        return ventas / nuevo_ratio
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


def _evolucionar_un_año(
    año: int,
    anterior: EjercicioEmpresa,
    fila: pd.Series,
    rng_pyg: np.random.Generator,
    rng_nota: np.random.Generator,
    crecimiento_ventas: float,
    intensidad_efectiva: float,
    intensidad_base: float,
    año_evento_puntual: int | None,
    definicion: DefinicionArquetipo,
) -> EjercicioEmpresa:
    ventas = anterior.ventas * (1 + crecimiento_ventas)

    efectos_masa_circulante = [e for e in definicion.efectos if isinstance(e, EfectoMasaCirculante)]
    efectos_pyg = [e for e in definicion.efectos if isinstance(e, EfectoPygPrimitiva)]
    efectos_apalancamiento = [e for e in definicion.efectos if isinstance(e, EfectoApalancamiento)]
    efectos_tesoreria = [e for e in definicion.efectos if isinstance(e, EfectoTesoreria)]
    efecto_tesoreria = efectos_tesoreria[0] if efectos_tesoreria else None
    efectos_reclasificacion_deuda = [e for e in definicion.efectos if isinstance(e, EfectoReclasificacionDeuda)]
    efectos_evento_puntual = [e for e in definicion.efectos if isinstance(e, EfectoEventoPuntual)]
    efectos_capex = [e for e in definicion.efectos if isinstance(e, EfectoCapex)]
    nota_memoria: str | None = None

    # --- Masas de circulante: proporcional a ventas por defecto, desviadas si el arquetipo
    # las toca. Las tres variables soportadas (SIGNO_NOF_MASA_CIRCULANTE) se tratan siempre
    # igual, tocadas o no por el arquetipo: solo cambia si objetivos_circulante coincide o no
    # con proporcional_circulante para esa variable. ---
    variables_circulante = {variable: anterior.balance_eur[variable] for variable in SIGNO_NOF_MASA_CIRCULANTE}
    proporcional_circulante = {
        variable: valor * (1 + crecimiento_ventas) for variable, valor in variables_circulante.items()
    }
    objetivos_circulante = dict(proporcional_circulante)
    for efecto in efectos_masa_circulante:
        objetivos_circulante[efecto.variable] = _masa_circulante_objetivo(efecto, anterior, ventas, fila, intensidad_efectiva)
    existencias_eur = objetivos_circulante["existencias"]
    realizable_eur = objetivos_circulante["realizable"]
    acreedores_comerciales_eur = objetivos_circulante["acreedores_comerciales"]
    existencias_proporcional_eur = proporcional_circulante["existencias"]
    realizable_proporcional_eur = proporcional_circulante["realizable"]
    acreedores_comerciales_proporcional_eur = proporcional_circulante["acreedores_comerciales"]

    # --- Resto de masas: crecen en línea con las ventas (patrimonio neto se trata aparte) ---
    activo_no_corriente_proporcional_eur = anterior.balance_eur["activo_no_corriente"] * (1 + crecimiento_ventas)
    activo_no_corriente_eur = activo_no_corriente_proporcional_eur
    if efectos_capex:
        activo_no_corriente_eur = _activo_no_corriente_objetivo(
            efectos_capex[0], anterior, ventas, fila, intensidad_efectiva
        )
    deudas_fin_largo_proporcional_eur = anterior.balance_eur["deudas_fin_largo"] * (1 + crecimiento_ventas)
    otras_deudas_largo_eur = anterior.balance_eur["otras_deudas_largo"] * (1 + crecimiento_ventas)
    otras_deudas_corto_eur = anterior.balance_eur["otras_deudas_corto"] * (1 + crecimiento_ventas)
    deudas_fin_corto_proporcional_eur = anterior.balance_eur["deudas_fin_corto"] * (1 + crecimiento_ventas)
    disponible_proporcional_eur = _disponible_proporcional_con_efecto(
        efecto_tesoreria, anterior.balance_eur["disponible"] * (1 + crecimiento_ventas), intensidad_efectiva
    )
    deuda_financiera_inicio_eur = anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"]

    # --- Reclasificación de deuda (arquetipo 8 "refinanciación"): mueve deuda financiera entre
    # largo y corto plazo SIN alterar el total (una renegociación cambia el vencimiento, no el
    # importe) — reasigna deudas_fin_largo/corto_proporcional_eur antes de que se usen más
    # abajo. Ver EfectoReclasificacionDeuda en motor/arquetipos.py y el docstring del módulo. ---
    if efectos_reclasificacion_deuda:
        efecto_reclas = efectos_reclasificacion_deuda[0]
        deuda_financiera_total_proporcional_eur = deudas_fin_largo_proporcional_eur + deudas_fin_corto_proporcional_eur
        deuda_financiera_anterior_eur = anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"]
        calidad_deuda_anterior = (
            anterior.balance_eur["deudas_fin_largo"] / deuda_financiera_anterior_eur
            if deuda_financiera_anterior_eur > 0
            else 0.0
        )
        huber_calidad_deuda = fila[f"{efecto_reclas.ratio_catalogo}.huber_9y"]
        calidad_deuda_objetivo = _mover_ratio_continuo(
            calidad_deuda_anterior, efecto_reclas.direccion, intensidad_efectiva, huber_calidad_deuda
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
            nota_memoria = NOTAS_MEMORIA_RIESGO_REFINANCIACION[indice_nota]

    # --- Capex (arquetipo 17, "capex elevado"): el exceso de activo_no_corriente sobre su
    # crecimiento proporcional a ventas se financia con deuda a largo plazo NUEVA, no con el
    # circulante — a diferencia de una masa_circulante, invertir en inmovilizado no genera un
    # déficit de caja del ejercicio que haya que cubrir con tesorería o deuda a CORTO (esa es la
    # fuente típica de financiación de circulante, no de capex); la fuente típica de financiación
    # de capex es deuda a LARGO plazo (o ampliación de capital/autofinanciación, no modeladas
    # aquí). A diferencia del efecto "apalancamiento" (arquetipo 9), esta deuda nueva NO financia
    # una distribución a PN: financia la COMPRA del propio activo, así que no se resta nada de
    # patrimonio_neto — el activo y el pasivo suben exactamente lo mismo, sin romper el cuadre.
    if efectos_capex:
        exceso_capex_eur = max(0.0, activo_no_corriente_eur - activo_no_corriente_proporcional_eur)
        deudas_fin_largo_proporcional_eur += exceso_capex_eur

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
    for efecto in efectos_evento_puntual:
        if año == año_evento_puntual:
            primitivas_forzadas[efecto.primitiva] = _evento_puntual_valor(efecto, fila, intensidad_base)
    efectos_pyg_base_dinamica = []
    for efecto in efectos_pyg:
        objetivo = _pyg_primitiva_objetivo(efecto, anterior, fila, intensidad_efectiva)
        if efecto.primitiva in SUBTOTAL_PYG_BASE_DINAMICA_DE_PRIMITIVA:
            # No se puede topar aquí: el subtotal (baii) depende de otras primitivas que
            # todavía no se han sorteado. Se fuerza el objetivo sin contener y se corrige
            # después de generar la PyG completa (ver más abajo).
            primitivas_forzadas[efecto.primitiva] = objetivo
            efectos_pyg_base_dinamica.append(efecto)
            continue
        objetivo, subtotal_topado, subtotal_sin_contener = _limitar_por_subtotal(
            efecto.primitiva, objetivo, fila, efecto.direccion
        )
        primitivas_forzadas[efecto.primitiva] = objetivo
        if subtotal_topado is not None:
            riesgo_plausibilidad_pyg = True
            pyg_subtotales_sin_contener[subtotal_topado] = subtotal_sin_contener
    parcial_pyg = _generar_pyg_hasta_baii(rng_pyg, fila, ventas, primitivas_forzadas=primitivas_forzadas)
    for efecto in efectos_pyg_base_dinamica:
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
                nota_memoria = NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE[indice_nota]

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
        deudas_fin_largo_eur: float,
        patrimonio_neto_eur: float,
    ) -> tuple[dict[str, float], float]:
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
    ) -> tuple[dict[str, float], float, float, dict[str, float], dict[str, float]]:
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
        patrimonio_neto_eur = (
            anterior.balance_eur["patrimonio_neto"] + pyg_eur["resultado_ejercicio"] - extra_deuda_largo_eur
        )
        balance, ajuste_cuadre_eur = _construir_balance(
            existencias_eur,
            realizable_eur,
            acreedores_comerciales_eur,
            disponible_eur,
            deudas_fin_corto_eur,
            deudas_fin_largo_eur,
            patrimonio_neto_eur,
        )
        return balance, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur

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
        balance_base, _, _, _, _ = _evaluar(
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
        efecto_apalancamiento = efectos_apalancamiento[0]
        endeudamiento_objetivo = min(
            endeudamiento_anterior * (1 + efecto_apalancamiento.direccion * intensidad_efectiva), techo_endeudamiento
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

    balance_eur, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur = _evaluar(
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
            efecto.variable: max(
                0.0,
                objetivos_circulante[efecto.variable] - proporcional_circulante[efecto.variable],
            )
            for efecto in efectos_masa_circulante
            if SIGNO_NOF_MASA_CIRCULANTE[efecto.variable] == 1
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

            balance_eur, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur = _evaluar(
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
        riesgo_plausibilidad_pyg=riesgo_plausibilidad_pyg,
        pyg_subtotales_sin_contener=pyg_subtotales_sin_contener,
        pyg_contencion_al_limite=pyg_contencion_al_limite,
        nota_memoria=nota_memoria,
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
) -> EvolucionArquetipo:
    """Genera 3 ejercicios (2023 base, 2024 y 2025 con `arquetipo_id` aplicado de forma
    progresiva: 60% de la intensidad en 2024, 100% en 2025), encadenados entre sí.

    `arquetipo_id` es una clave de `data/arquetipos.json` (ver `motor.arquetipos`)."""
    if intensidad not in INTENSIDADES_VALIDAS:
        raise EvolucionArquetipoError(
            f"Intensidad '{intensidad}' no válida. Debe ser una de: {sorted(INTENSIDADES_VALIDAS)}"
        )

    if arquetipos is None:
        arquetipos = cargar_arquetipos()
    if arquetipo_id not in arquetipos:
        raise EvolucionArquetipoError(
            f"Arquetipo '{arquetipo_id}' no reconocido. Disponibles: {sorted(arquetipos)}"
        )
    definicion = arquetipos[arquetipo_id]

    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    fila = resolver_fila_sector(catalogo, sector, segmento)

    empresa_2023 = generar_empresa_base(sector, segmento, ventas_objetivo_2023, semilla, catalogo=catalogo)
    ejercicios: dict[int, EjercicioEmpresa] = {AÑO_BASE: _ejercicio_desde_empresa_base(empresa_2023)}

    # La semilla mezcla `semilla` con un hash estable (zlib.crc32, no `hash()` de Python) de
    # sector+segmento — NO de intensidad: por diseño, la misma semilla+sector+segmento con
    # distintas intensidades debe compartir el mismo "ruido de fondo" (crecimiento_pleno_objetivo
    # cuando el arquetipo no define rango propio, y la PyG de 2024/2025 para las primitivas que
    # el arquetipo no toca), y solo el empuje propio del arquetipo debe variar con la intensidad
    # (ver test_intensidad_fuerte_tiene_mas_efecto_que_moderado). Sin este mezclado, CUALQUIER
    # sector/segmento con la misma semilla partía del mismo estado de RNG: verificado que
    # crecimiento_pleno_objetivo salía bit a bit idéntico entre sectores distintos que
    # compartieran semilla, para cualquier arquetipo sin rango_crecimiento_pleno propio — mismo
    # patrón de bug que el corregido en el sorteo de `nota_memoria` (ver más abajo), auditado
    # explícitamente a raíz de aquel hallazgo.
    entropia_sector = zlib.crc32(f"{sector}|{segmento}".encode("utf-8"))
    semilla_secuencia = np.random.SeedSequence([semilla, entropia_sector])
    hijo_tendencia, hijo_2024, hijo_2025 = semilla_secuencia.spawn(3)
    rng_tendencia = np.random.default_rng(hijo_tendencia)
    rngs_pyg = {2024: np.random.default_rng(hijo_2024), 2025: np.random.default_rng(hijo_2025)}

    # RNG dedicado e independiente para `nota_memoria` (arquetipo 10): NO reutiliza rngs_pyg. Su
    # semilla mezcla `semilla` con un hash estable (zlib.crc32, no `hash()` de Python — este
    # último varía entre procesos por PYTHONHASHSEED, rompería la reproducibilidad) de
    # sector+segmento+intensidad, así que el sorteo es específico de cada caso, no solo de
    # `semilla`. Necesario porque `rngs_pyg[año]` llega al punto donde se sortearía la nota en EL
    # MISMO estado para cualquier sector/intensidad con la misma semilla (todos los draws previos
    # de `_generar_pyg_hasta_baii` — típico/atípico, z de la normal truncada — no dependen de
    # huber/mad ni de intensidad, solo su escalado posterior sí): detectado en pruebas de estrés,
    # el reparto observado entre las 5 redacciones en 143 casos (12/37/56/33/5) no era ruido de
    # muestra pequeña (chi-cuadrado ~58 con 4 g.l., p<0,001) sino que colapsaba a solo 6 sorteos
    # realmente distintos (uno por combinación semilla x año con algún caso activado), repetido
    # idéntico en todos los sectores/intensidades que compartían esa semilla y año.
    entropia_caso = zlib.crc32(f"{sector}|{segmento}|{intensidad}".encode("utf-8"))
    semilla_secuencia_notas = np.random.SeedSequence([semilla, entropia_caso])
    hijo_nota_2024, hijo_nota_2025 = semilla_secuencia_notas.spawn(2)
    rngs_nota = {2024: np.random.default_rng(hijo_nota_2024), 2025: np.random.default_rng(hijo_nota_2025)}

    if definicion.rango_crecimiento_pleno is not None:
        bajo, alto = definicion.rango_crecimiento_pleno[intensidad]
        crecimiento_pleno_objetivo = bajo + rng_tendencia.random() * (alto - bajo)
    else:
        bajo, alto = RANGO_CRECIMIENTO_ORGANICO
        crecimiento_pleno_objetivo = bajo + rng_tendencia.random() * (alto - bajo)

    # Año único del suceso puntual (arquetipo 12, "resultado extraordinario"): sorteado 50/50
    # entre 2024 y 2025 con rng_tendencia — mismo generador ya independiente por sector+segmento,
    # NO por intensidad (el año en que ocurrió el suceso es un hecho de la propia empresa: no
    # debe cambiar solo porque se pida una intensidad distinta del mismo caso, igual que
    # crecimiento_pleno_objetivo). Solo se consume si el arquetipo tiene un EfectoEventoPuntual,
    # así que no afecta al estado de rng_tendencia para el resto de arquetipos.
    año_evento_puntual: int | None = None
    if any(isinstance(e, EfectoEventoPuntual) for e in definicion.efectos):
        año_evento_puntual = 2024 if rng_tendencia.integers(2) == 0 else 2025

    intensidad_base = INTENSIDAD_BASE[intensidad]
    anterior = ejercicios[AÑO_BASE]
    for año in (2024, 2025):
        fraccion = FRACCION_AÑO[año]
        intensidad_efectiva = intensidad_base * fraccion
        crecimiento_ventas = (
            crecimiento_pleno_objetivo * fraccion if definicion.rango_crecimiento_pleno is not None else crecimiento_pleno_objetivo
        )
        ejercicio = _evolucionar_un_año(
            año,
            anterior,
            fila,
            rngs_pyg[año],
            rngs_nota[año],
            crecimiento_ventas,
            intensidad_efectiva,
            intensidad_base,
            año_evento_puntual,
            definicion,
        )
        ejercicios[año] = ejercicio
        anterior = ejercicio

    return EvolucionArquetipo(
        sector_codigo=sector,
        sector_nombre=fila["sector"],
        segmento=segmento,
        arquetipo=arquetipo_id,
        intensidad=intensidad,
        semilla=semilla,
        crecimiento_pleno_objetivo=crecimiento_pleno_objetivo,
        ejercicios=ejercicios,
        catalogo_version=catalogo.attrs.get("catalogo_version", "desconocida"),
    )
