# Índice de orientación rápida

Este archivo (y `docs/indice_arquetipos.md`, `docs/decisiones_plausibilidad.md`) es un atajo de
**arranque de sesión**, no una especificación. Sirve para no tener que releer `motor/*.py`,
`data/arquetipos.json` y los tests completos solo para recordar qué existe. **No sustituye**:
leer el código cuando la tarea lo exige, la comprobación cuantificada de plausibilidad sobre el
stress test completo, ni los tests de regresión — eso se mantiene igual en cada lote, sin
excepciones. Si algo aquí no coincide con el código, **el código manda**: actualiza este índice,
no al revés.

Especificación funcional completa: `docs/especificaciones_proyecto_casos_balances.md` (sección
2.24 = tabla de los 22 arquetipos; 2.25 = matriz de compatibilidad). Guía docente por arquetipo:
`docs/guia_docente_arquetipos.md`.

## Módulos de `motor/`

| Archivo | Responsabilidad | Función(es) pública(s) | Toca |
|---|---|---|---|
| `catalogo.py` | Carga y valida el catálogo de ratios sectoriales (CSV, 27 sectores × 2 segmentos, `huber_9y`/`huber_scale_mad` por ratio). | `cargar_y_validar_catalogo(ruta=...) -> DataFrame`; `version_catalogo(ruta=...) -> str` (hash usado como `catalogo_version`, sección 2.15). | Base de todo — sin arquetipos. |
| `ruido.py` | Mecanismo de ruido mixto típico/atípico (85%/15%, normal truncada) — extraído de `empresa_base.py` a su propio módulo para que `amortizacion.py` pueda reutilizarlo sin crear una importación circular. Sin dependencias de otros módulos del motor. | `_generar_partida(rng, huber_9y, huber_scale_mad, suelo=None, techo=None) -> (float, str)`; `_normal_truncada`; `_renormalizar_a_total` | Nada de generación — `empresa_base.py` los reexporta (`from motor.ruido import ...`), así que el resto del código sigue importándolos como `motor.empresa_base.<nombre>` sin cambios. |
| `empresa_base.py` | Genera balance + PyG de **una** empresa, **un** ejercicio, a partir del catálogo + ruido típico/atípico. Sin arquetipos, sin serie temporal. `tipo_interes` (para `gastos_financieros`) ya NO sale de `ratios.coste_deuda` del catálogo — ver "Tipo de interés de mercado" abajo. | `generar_empresa_base(sector, segmento, ventas_objetivo, semilla, catalogo=None) -> EmpresaBase`; `resolver_fila_sector(catalogo, sector_codigo, segmento) -> pd.Series`; `categoria_de_sector(sector_codigo) -> str` | Año base 2023 de **cualquier** caso, con o sin arquetipo. Desde el arreglo de raíz de la amortización, importa `motor.amortizacion` para derivar `pyg_eur["amortizaciones"]` — ver "Amortización derivada" abajo. |
| `amortizacion.py` | Deriva el gasto de amortización de la PyG a partir de una colección REAL de activos (sub-lotes con vida fiscal, fecha de compra sorteada, posible "ya totalmente amortizado") — sustituye el antiguo sorteo independiente de `amortizaciones_pct`. Ver sección "Amortización derivada" abajo para el diseño completo. | `generar_coleccion_y_perfiles_base(sector, segmento, semilla, categoria, activo_no_corriente_desglose_eur) -> (coleccion, perfil_material, perfil_intangible)`; `generar_cohortes_capex(...)`/`generar_cohortes_adquisicion(...)` (cohortes nuevas de los arquetipos 17/18); `amortizacion_eur_del_año(coleccion, año) -> float`; `bienes_totalmente_amortizados_en(coleccion, año) -> tuple[BienTotalmenteAmortizado,...]` | `empresa_base.py` (año base) y `evolucion_arquetipo.py` (2024/2025, cohortes nuevas de capex/adquisición) — consume el desglose de `activo_no_corriente` ya generado, no genera balance por sí mismo. |
| `arquetipos.py` | Carga y valida `data/arquetipos.json` como dataclasses tipadas. **Sin lógica de generación.** | `cargar_arquetipos(ruta=...) -> dict[str, DefinicionArquetipo]` | Tipos de efecto: `EfectoMasaCirculante`, `EfectoPygPrimitiva`, `EfectoApalancamiento`, `EfectoTesoreria`, `EfectoReclasificacionDeuda`, `EfectoEventoPuntual`, `EfectoCapex`, `EfectoAdquisicion`, `EfectoCobertura`. |
| `evolucion_arquetipo.py` | Motor genérico: evoluciona una empresa 3 ejercicios (2023 base + 2024/2025 con el/los arquetipo(s) aplicado(s)), interpretando cada tipo de `Efecto`. Contiene toda la lógica de mecanismo — **no releer para saber qué arquetipos toca cada mecanismo, ver tabla de mecanismos abajo**. `generar_evolucion_arquetipo` (un solo arquetipo) es un wrapper de una línea sobre `generar_evolucion_combinada` con un dict de 1 elemento — **garantía estructural**: cualquier test de un arquetipo en solitario que siga pasando prueba que la combinación no le cambió el comportamiento. | `generar_evolucion_combinada(sector, segmento, ventas_objetivo_2023, semilla, arquetipos_intensidades: dict[str,str], catalogo=None, arquetipos=None) -> EvolucionArquetipo` (motor general); `generar_evolucion_arquetipo(sector, segmento, ventas_objetivo_2023, semilla, intensidad, arquetipo_id, catalogo=None, arquetipos=None) -> EvolucionArquetipo` (caso de 1 arquetipo) | Todos los arquetipos de `clase="cuantitativo"` (17 desde el encargo de coberturas/subvenciones — "coberturas", 21, pasó de `memoria_pura` a `cuantitativo`, ver `docs/indice_arquetipos.md`); rechaza `clase="memoria_pura"` con `EvolucionArquetipoError`. |
| `coberturas_subvenciones.py` | Coberturas de flujos de efectivo (arquetipo 21, `EfectoCobertura`) y subvenciones de capital (transversal, disparada por el arquetipo 17 o por una probabilidad de fondo por categoría de sector) — grupo 8/9 del PGC + efecto impositivo (subgrupo 83). Ver sección "Coberturas y subvenciones" abajo para el diseño completo del cuadre. | `evolucionar_cobertura(...)`/`evolucionar_subvencion(...)` (paso anual, llamados desde `_evolucionar_un_año`); `sortear_parametros_cobertura(...)`/`sortear_subvencion_baseline(...)`/`sortear_pct_cofinanciacion(...)` (sorteos únicos por caso); `presentacion_neta_eur`/`activo_por_impuesto_diferido_eur`/`pasivo_por_impuesto_diferido_eur` (helpers puros del efecto impositivo) | `evolucion_arquetipo.py` (balance/PyG, todos los años) y `ecpn.py`/`efe.py` (consumen los campos ya expuestos en `EjercicioEmpresa`, no llaman a este módulo directamente). |
| `memoria.py` | Genera notas de memoria puramente cualitativas — arquetipos de `clase="memoria_pura"` (sin efectos numéricos, `efectos: []` en el JSON) — y orquesta el caso combinado completo (mezcla `clase="cuantitativo"` + `clase="memoria_pura"`). | `generar_nota_memoria_pura(arquetipo_id, sector, segmento, intensidad, semilla, ejercicio, etiquetas_ya_usadas=frozenset()) -> NotaMemoria` (o la función específica `generar_nota_<arquetipo>(...)`); `generar_caso_combinado(sector, segmento, ventas_objetivo_2023, semilla, arquetipos_intensidades, catalogo=None, arquetipos=None) -> EvolucionArquetipo` (punto de entrada general, cualquier mezcla de clases) | Arquetipos 7, 19, 20, 22 (4, desde que "coberturas" -21- pasó a `cuantitativo` — sigue generando su nota cualitativa como caso especial dentro de `generar_caso_combinado`, ver el propio código). `NotaMemoria` (definida en `evolucion_arquetipo.py`, no aquí — ver "Combinación de arquetipos" abajo) lleva `texto` + `etiquetas` (temas, usadas por el mecanismo de coherencia de la sección 2.12). |
| `clasificacion_legal.py` | Clasifica cada caso como modelo abreviado/normal (Art. 257 LSC) — capa de cálculo pura sobre datos que el motor YA genera (activo, cifra de negocio) más una plantilla ESTIMADA (no generada) a partir de `ratios.ventas_empleado` del catálogo. No genera balance/PyG, no toca `empresa_base.py`/`evolucion_arquetipo.py`. Ver sección "Clasificación legal" abajo. | `estimar_ventas_por_empleado(sector, segmento, semilla, catalogo=None) -> (float, str)`; `estimar_plantilla(cifra_negocio_eur, ventas_empleado_miles_eur) -> float`; `clasificar_ejercicio(año, activo_eur, cifra_negocio_eur, plantilla_estimada) -> ResultadoClasificacionLegal`; `clasificar_par_ejercicios(resultado_anterior, resultado_actual) -> "abreviado"\|"normal"` | Cualquier caso ya generado (empresa_base o evolución completa) — consume su balance/PyG, no interviene en su generación. |
| `efe.py` | Estado de Flujos de Efectivo, método indirecto, modelo NORMAL del PGC — capa de cálculo pura sobre dos `EjercicioEmpresa` consecutivos. Ver sección "EFE y ECPN" abajo para el mapeo completo y la corrección sobre la amortización. C.9 (subvenciones) y A.2.k (reverso no-cash de cobertura/subvención) desde el encargo de coberturas/subvenciones. | `generar_efe(anterior, actual, obligatorio: bool) -> EstadoFlujosEfectivo` (con propiedad `.cuadra`) | Ningún módulo de generación — solo lee `balance_eur`/`pyg_eur` ya generados, incluida la desagregación de PN/activo_no_corriente. |
| `ecpn.py` | Estado de Cambios en el Patrimonio Neto — Documento B ("Estado total de cambios en el patrimonio neto") Y Documento A ("Estado de ingresos y gastos reconocidos", EIGR, ya NO aparcado desde el encargo de coberturas/subvenciones — ver sección "Coberturas y subvenciones" abajo) del modelo NORMAL del PGC. Capa de cálculo pura sobre `EjercicioEmpresa`. | `generar_ecpn(anterior, actual, obligatorio: bool) -> EstadoCambiosPatrimonioNeto` (Documento B, con propiedad `.cuadra`); `generar_eigr(actual, obligatorio: bool) -> EstadoIngresosGastosReconocidos` (Documento A — fotografía de UN ejercicio, no de dos) | Igual que `efe.py` — ninguno de generación. |

## Mecanismos reutilizables ya construidos (en `evolucion_arquetipo.py`, salvo que se indique)

| Mecanismo (tipo de efecto en JSON) | Qué hace, en una línea | Arquetipos que lo usan |
|---|---|---|
| `masa_circulante` (fórmula `rotacion`/`dias`) | Desvía existencias / realizable / acreedores_comerciales por continuidad respecto al año anterior, con signo NOF (`SIGNO_NOF_MASA_CIRCULANTE`: activo suma presión de caja, pasivo resta). | 1, 3, 4, 5, 6 |
| `pyg_primitiva` | Desvía una primitiva de PyG por continuidad; techo/suelo del subtotal que alimenta vía `SUBTOTAL_PYG_DE_PRIMITIVA` (base fija, margen_bruto) o `SUBTOTAL_PYG_BASE_DINAMICA_DE_PRIMITIVA` (base dinámica, baii). | 10, 11 |
| `apalancamiento` | Sube deuda a largo + baja PN en forma cerrada hasta un endeudamiento objetivo (topado al techo sectorial). | 9, 14 (14 = variante exacta de 9) |
| Escalas de intensidad ESPECÍFICAS por mecanismo (`INTENSIDAD_BASE_POR_ARQUETIPO`, reemplaza la `INTENSIDAD_BASE` genérica 0,15/0,30/0,50 solo para estos 3) | 9/14 (`apalancamiento`) y 11/10 (`pyg_primitiva`) topan su señal de plausibilidad contra un umbral mucho más estrecho que el resto — con la escala genérica saturaban ya en "leve" (30-42%, ver `decisiones_plausibilidad.md` #20). Recalibradas: apalancamiento `0,02/0,08/0,25`; mejora_margen `0,02/0,07/0,22`; mejora_ebitda `0,015/0,06/0,22` (10 tiene además un suelo estructural ~6,9% de ruido de base sin ningún arquetipo, ver #18 — no baja más). | 9, 14, 11, 10 |
| `tesoreria` | Desvía `disponible` con un factor simple `(1 ± intensidad)` — **no usa el Huber del `ratio_catalogo`**, es solo etiqueta de trazabilidad. | 2, 15 (2 = variante exacta de 15) |
| `reclasificacion_deuda` | Reasigna deuda largo↔corto SIN alterar el total (mejora o empeora `calidad_deuda`). | 8 (dirección +1), 16 (dirección −1, + `nota_memoria`) |
| `evento_puntual` | Fuerza una primitiva de PyG solo en UN año sorteado (no progresivo) — vuelve al ruido normal el año siguiente sin código adicional. | 12 |
| `capex` | `activo_no_corriente` por continuidad (ancla `rotacion_activo_no_corriente`), financiado con deuda a largo NUEVA (no toca PN, no toca circulante). | 17 |
| `adquisicion` | Salto DISCRETO (no continuo) de `activo_no_corriente` en un año FIJO (`AÑO_ADQUISICION=2024`, no sorteado), financiado con caja + deuda a largo; separa `ventas_organicas_eur`/`ventas_inorganicas_eur`; `nota_memoria` OBLIGATORIA (no opcional). | 18 |
| `cobertura` | NO es una forma más del molde genérico de continuidad — la magnitud se deriva cada año de la sensibilidad de un swap (nocional × duración modificada × Δtipo de interés del sector, acotado por `TECHO_DELTA_R_ANUAL`) contra una reserva de PN (1340) y su efecto impositivo. Ver `motor/coberturas_subvenciones.py` y sección "Coberturas y subvenciones" abajo. | 21 (también genera su nota de memoria cualitativa habitual, como caso especial en `motor.memoria.generar_caso_combinado`) |
| Contención de endeudamiento | Chequeo **incondicional** cada año: si el endeudamiento supera `huber+3·MAD` (techo absoluto 0,85), amortigua vía las masas de ACTIVO tocadas por el arquetipo, si las hay; si no, queda `contencion_al_limite=True` (señal sin corrección posible). | Todos (corre siempre, toque o no circulante) |
| Hash estable sector+segmento (`zlib.crc32`) | Siembra cada RNG (`generar_empresa_base`, `rng_tendencia`/`rngs_pyg`, `rngs_nota`) mezclando semilla+sector+segmento — **nunca intensidad** (mismo "ruido de fondo" entre intensidades del mismo caso, por diseño). | Todos — infraestructura, no arquetipo-específico |
| `nota_memoria` (campo `EjercicioEmpresa.notas_memoria: tuple[NotaMemoria,...]`, plural — antes `str \| None` singular) | Cobertura narrativa reproducible (RNG dedicado `rngs_nota`/`rngs_nota_por_arquetipo`, redacciones alternativas por arquetipo). Opcional (10: caso límite; 16: huella habitual) u OBLIGATORIA (18). El paso a tupla (en vez de campo único) es lo que permite que 2+ arquetipos con nota numérica activos a la vez no se pisen entre sí. | 10, 16, 18 |
| `clase="memoria_pura"` (en `motor.memoria`, no `evolucion_arquetipo.py`) | Arquetipo SIN efectos numéricos (`efectos: []`) — la nota de memoria se genera con una función propia de `motor.memoria`, no pasa por `_evolucionar_un_año`. RNG dedicado por (sector, segmento, intensidad, **arquetipo_id**, semilla) — a diferencia del resto, mezcla también el arquetipo_id, para que varias notas de memoria puedan combinarse sobre el mismo caso sin compartir estado. | 7, 19, 20, 21, 22 |

## Combinación de arquetipos (sección 2.12 — varios arquetipos activos a la vez)

Acotado deliberadamente a lo que requieren las 6 combinaciones recomendadas de la sección 2.26
(no las 231 parejas de la matriz de compatibilidad completa, sección 2.25). Detalle completo del
hallazgo de saturación del Combo F: `docs/decisiones_plausibilidad.md` #16.

- **Fusión de efectos del mismo mecanismo/variable/dirección** (`masa_circulante` únicamente, por
  ahora — único caso real entre las 6 combos, Combo F 1+5 sobre `existencias`): se SUMAN las
  intensidades (`intensidad_efectiva`/`intensidad_base`) de los arquetipos implicados y se aplica
  la fórmula de continuidad UNA sola vez (no encadenado, que sería dependiente del orden); el
  techo/suelo sectorial (`FRACCION_MINIMA/MAXIMA_VS_HUBER`) actúa igual, como límite conjunto. Ver
  `_fusionar_masa_circulante`.
- **Intensidad por arquetipo, no por caso**: cada `Efecto` va emparejado con la intensidad DE SU
  PROPIO arquetipo de origen (`EfectoActivo`, en `evolucion_arquetipo.py`) — dos arquetipos
  combinados pueden llevar intensidades distintas (p. ej. uno "fuerte", otro "leve").
- **RNG de fondo SIN cambios para combinaciones**: la entropía de fondo (`crc32(sector|segmento)`,
  usada por `generar_empresa_base`/`rng_tendencia`/`rngs_pyg`) sigue sin mezclar ni la intensidad
  ni el conjunto de arquetipos activos — deliberado, para que (a) la misma empresa sea comparable
  entre historias distintas y (b) los valores de referencia ya fijados en los tests de los 21
  arquetipos cerrados no se movieran ni un dígito al añadir la combinación (confirmado: suite
  completa sin cambiar ninguna aserción numérica). Las notas de memoria SÍ mezclan el
  `arquetipo_id` en su RNG (ya lo hacían) — `rngs_nota_por_arquetipo` da un stream independiente
  por arquetipo activo.
- **Colisión temática entre notas** (10/16/18 vía `EjercicioEmpresa.notas_memoria`, más
  7/19/20/21/22 vía `motor.memoria`): un único mecanismo genérico y sin casos especiales,
  `_elegir_indice_evitando_colision` (definida en `motor/memoria.py`, reusada también desde
  `evolucion_arquetipo.py`) — baraja las plantillas posibles con el RNG del propio arquetipo y
  devuelve la primera cuyas etiquetas no choquen con las ya usadas por OTRO arquetipo en el mismo
  caso; si ninguna libra la colisión, devuelve la primera del orden barajado (nota redundante en
  vez de bloquear la generación). Solo tiene efecto observable en el arquetipo 22 (único con
  variación de etiqueta por plantilla — los otros 7 arquetipos tienen etiqueta FIJA sea cual sea
  la plantilla de texto elegida, así que para ellos o colisionan todas las opciones o ninguna).
  `generar_caso_combinado` aplica esto sobre el conjunto COMPLETO de notas del caso, en orden de
  número de arquetipo, no solo por parejas.
- Etiquetas deliberadamente ESPECÍFICAS (no genéricas) para minimizar falsos positivos de colisión
  en combinaciones futuras — p. ej. `("deuda_corto_plazo","riesgo_refinanciacion")` en el 16 en vez
  de `"deuda"` a secas (no choca con el `("deuda","cobertura_riesgo")` del 21); `("adquisicion",
  "combinacion_negocios")` en el 18 en vez de `"activo"` (no choca con `("activo","desinversion")`
  del 19 — el Combo E combina legítimamente ambos: adquirir un negocio y desinvertir en un activo
  no relacionado son dos hilos narrativos distintos, no redundantes).

## Clasificación legal (Art. 257 LSC) — modelo abreviado vs. normal, y el EFE

Ver `docs/decisiones_plausibilidad.md` #21 y #22 para el detalle cuantificado completo.

- **El segmento del catálogo y la clasificación legal son DOS COSAS DISTINTAS, tratadas como
  independientes por diseño — no se fuerza que coincidan.** El segmento (`"pequeñas"` /
  `"grandes_medianas"`) solo decide de qué fila de Huber parte la generación (productividad,
  rotación de activo, etc. típicas de ese tamaño de empresa en el sector). La clasificación
  legal (`motor.clasificacion_legal`) se calcula APARTE, sobre los números YA generados de cada
  caso concreto (activo total, cifra de negocio, más una plantilla estimada) — puede no coincidir
  con el segmento solicitado, y eso es correcto, no un error a corregir.
- **Test legal**: Art. 257.1 LSC, 2-de-3 sobre activo ≤4.000.000€, cifra de negocio ≤8.000.000€,
  plantilla ≤50 — umbrales VIGENTES (verificado externamente, BOE/ICAC; hay un Proyecto de Ley
  que los subiría a 7,5M/15M/50, sin rango de ley todavía, y aunque se apruebe no aplicaría a los
  ejercicios 2023-2025 que genera este motor — ver decisiones #21). Art. 257.2: exige el
  cumplimiento durante 2 ejercicios CONSECUTIVOS — `clasificar_par_ejercicios` solo da
  "abreviado" si ambos años del par lo son por separado.
- **Plantilla estimada, no generada**: el motor no modela recursos humanos. Se estima con el
  MISMO mecanismo de ruido mixto típico/atípico ya usado en todo el motor
  (`_generar_partida`/`_normal_truncada` de `empresa_base.py`, reutilizado sin cambios) aplicado
  sobre `ratios.ventas_empleado` del catálogo — un sorteo ÚNICO por caso (sector+segmento+semilla,
  no por año ni por arquetipo: es un rasgo estructural, como `rotacion_activo`). Cada año escala
  esa productividad fija por la cifra de negocio real de ese año. Es una estimación de SEGUNDO
  ORDEN (depende de dos números ya generados + un ratio con ruido), no un dato tan sólido como
  activo o cifra de negocio — cualquier resultado del test legal que dependa del criterio de
  empleados hereda esa incertidumbre añadida.
- **`ventas_objetivo` representativa del segmento, no un valor plano compartido**: la convención
  de usar 8.000.000€ para cualquier segmento (heredada de los primeros lotes de arquetipos, antes
  de que existiera esta clasificación) resultaba invertida la mayoría de las veces al comprobar el
  test legal (65,7%/68,5% incoherente — ver decisiones #21). Convención nueva: **5.000.000€ para
  "pequeñas"** (dentro del ≤10M€ de ACCID), **15.000.000€ para "grandes_medianas"** (por encima
  del >10M€ de ACCID). Verificado que ningún hallazgo de calibración de intensidad anterior
  dependía del nivel absoluto de ventas (el motor es escala-invariante por diseño, todo ancla a
  ratios/% del catálogo) — la única excepción real son los suelos defensivos en EUROS ABSOLUTOS de
  los arquetipos 20/21 (`SUELO_IMPORTE_VINCULADAS_EUR`/`SUELO_NOCIONAL_COBERTURA_EUR`), que por
  diseño SÍ dependen de la escala — sus tests siguen fijos a 8M€ sin tocar.
- **Incluso con `ventas_objetivo` representativa, "pequeñas" no siempre clasifica "abreviado"**:
  10 de 27 sectores tienen algún caso que clasifica "normal" pese a facturación modesta (5M€), 6 de
  forma consistente (sectores intensivos en personal — I+D, consultoría, auditoría, educación,
  sanidad — o con baja rotación de activo) — reflejo económico real del propio catálogo ACCID, no
  un defecto de la estimación de plantilla ni del motor.
- **Consecuencia para el EFE/ECPN**: ambos se generan SIEMPRE, para todo caso — nunca se omiten.
  Lo que decide la clasificación legal real (`clasificar_par_ejercicios`), NUNCA el segmento
  solicitado, es el campo `obligatorio: bool` de `EstadoFlujosEfectivo`/`EstadoCambiosPatrimonioNeto`
  — con fines didácticos el alumnado debe poder ver el estado igual en modelo abreviado, sabiendo
  que en una presentación real no sería exigible.

## EFE y ECPN (sección 2.2/2.5) — modelo normal PGC, método indirecto

Capas de cálculo puras (`motor/efe.py`, `motor/ecpn.py`) sobre el balance/PyG que el motor ya
genera para dos `EjercicioEmpresa` consecutivos — no generan ningún dato nuevo. La comprobación
central de ambos es la reconciliación exacta (no que "tengan buena pinta"): EFE con
`disponible`, ECPN con `patrimonio_neto`, tolerancia 0,01€. Verificado exhaustivamente: **4.968
EFE y 4.968 ECPN generados (21 arquetipos solos + 6 combinaciones + 1 caso de intensidad ≈0, 27
sectores, 4 semillas, 2024 y 2025), 0 descuadres en ambos** — ver decisiones #26.

- **Desagregación de PN** (`EjercicioEmpresa.capital_social_eur`/`.reservas_eur`, expuesta en
  CUALQUIER balance, no solo el ECPN): capital social fijo desde 2023 (fracción de PN2023,
  redondeado a cifra vistosa — ver `empresa_base._generar_capital_social`), constante en
  2024/2025; reservas = PN(t) − capital − resultado_ejercicio(t), por resta, no por ruido propio.
  Ver decisiones #24 (criterio + comprobación de que "Reservas" no sale absurdamente negativa).
- **Desagregación de `activo_no_corriente`** (`.activo_no_corriente_perfil_pct`/
  `.activo_no_corriente_desglose_eur`, también en cualquier balance): perfil FIJO por caso
  (sorteo único), por CATEGORÍA de sector (9 categorías de PERFIL sobre los 8 bloques de la
  sección 2.22 — "servicios profesionales/TIC" se sub-divide en "servicios_profesionales"
  69.2/70.2 y "servicios_tic" 62, ver decisiones #33; el catálogo de sectores en sí sigue en 8
  bloques, es solo un refinamiento interno de este perfil), aplicado cada año al total
  de ese año — el salto del arquetipo 18 (`.incremento_activo_adquisicion_eur`) se mantiene
  aparte del perfil, nunca mezclado en él. Ver decisiones #25.
- **Mapeo de mecanismos a líneas del EFE** (detalle completo en decisiones #26): `masa_circulante`
  → A.3 (existencias/deudores/acreedores); `otras_deudas_corto` (el parche de cuadre general,
  presente cada año) → A.3.e "Otros pasivos corrientes" — absorbe de forma natural el residuo de
  `tesoreria` (2/15) y cualquier ajuste de segundo orden; `otras_deudas_largo` → A.3.f; deuda
  financiera total (`deudas_fin_largo+corto`) → C.10, variación NETA (el motor no distingue
  emisión/devolución bruta dentro del año, solo la posición neta); `apalancamiento` (9/14) →
  DOS líneas de financiación que se cancelan, C.10 (deuda nueva, ya incluida en la variación neta
  de arriba) + C.11.a "Dividendos" (=`-apalancamiento_extra_eur`, la distribución que esa deuda
  financia); `reclasificacion_deuda` (8/16) → NINGUNA línea, correctamente invisible (no mueve
  deuda total, no es un flujo real); perfil de `activo_no_corriente` → B.6/7 por componente,
  aplicado al cambio ORGÁNICO (excluyendo el salto de adquisición del año); adquisición (18) →
  B.6.a "Empresas del grupo y asociadas", aparte. Líneas sin mecanismo que las alimente (siempre
  0, documentado, no inventado): correcciones valorativas, provisiones, bajas de inmovilizado,
  diferencias de cambio, valor razonable, dividendos de terceros, "otros activos corrientes"
  (A.3.c). **C.9 ("Instrumentos de patrimonio... subvenciones") ya NO es siempre 0** desde el
  encargo de coberturas/subvenciones: = cobro de caja de la subvención en su año de concesión
  (ver sección "Coberturas y subvenciones" abajo).
- **Amortización (A.2.a) — sigue en 0,0 en el EFE, por una razón que YA NO es "no hay ningún
  activo real detrás"** (eso se arregló, ver "Amortización derivada" abajo y decisiones #27-#32)
  **sino que el `activo_no_corriente` del BALANCE todavía no se neta de la amortización
  acumulada** — el gasto de PyG ya es real y deriva de una colección de activos, pero esa
  colección hoy solo alimenta la PyG, no reduce el `activo_no_corriente` que ve el balance (eso
  queda para el encargo que reabra `motor/efe.py`, deliberadamente aplazado, ver decisiones #26).
  Mientras el balance no neta, añadir la amortización en A.2.a duplicaría el efecto que sigue
  absorbiendo `otras_deudas_corto` — la conclusión práctica (0,0) no cambia todavía, pero la
  RAZÓN sí: antes era "el motor no modela esto en absoluto", ahora es "el motor ya lo modela, pero
  el balance no lo refleja aún".
- **ECPN Documento B**: filas (saldo inicio, total ingresos y gastos reconocidos, operaciones con
  socios = la distribución de apalancamiento si la hay, otras variaciones = siempre 0, saldo
  final) × columnas (Capital, Reservas y resultados de ejercicios anteriores, Ajustes por cambios
  de valor, Subvenciones/donaciones/legados, Resultado del ejercicio, Total) — el resultado del
  ejercicio ANTERIOR se reclasifica a reservas al abrir el nuevo ejercicio, consistente por
  construcción con cómo se deriva `reservas_eur`. **"Total de ingresos y gastos reconocidos" ya
  NO es siempre = resultado del ejercicio** (eso era así solo mientras el Documento A estaba
  aparcado): ahora es resultado del ejercicio + el movimiento neto de las dos columnas nuevas —
  y coincide EXACTAMENTE con la fila D del Documento A (EIGR), ver sección siguiente.

## Coberturas y subvenciones — grupo 8/9 y Documento A (`motor/coberturas_subvenciones.py`)

Alcance APROBADO explícitamente: 2 operaciones de las 6 familias del PGC de grupo 8/9 —
coberturas de flujos de efectivo (arquetipo 21, ahora `clase="cuantitativo"`, antes
`memoria_pura`) y subvenciones de capital pendientes de imputar (transversal, disparada por el
arquetipo 17 "capex elevado" o por una probabilidad de fondo por categoría de sector) — más el
efecto impositivo (subgrupo 83) que ambas comparten. El resto (valoración de instrumentos
financieros, diferencias de conversión, actuariales, coberturas de inversión neta en el
extranjero) queda fuera de alcance por decisión, documentado en el Documento A como
`b_resto_fuera_de_alcance`/`c_resto_fuera_de_alcance` (siempre 0.0) — **activo mantenido para la
venta (19) reconfirmado que NO dispara grupo 8/9** (NRV 7.ª: la corrección va a PyG como
deterioro, no a una reserva de PN).

- **Diseño de cuadre exacto (Activo=Pasivo+PN), derivado por álgebra antes de escribir código —
  ver decisiones #35.** Cada mecanismo mantiene un saldo BRUTO propio de su reserva de PN (1340
  para cobertura, 130 para subvención). Los importes que se reciclan a la PyG (ineficacia +
  transferencia por vencimiento de la cobertura, vía `gastos_financieros`; imputación anual de
  la subvención, vía `otros_ingresos_explot`) se inyectan en la cascada de PyG por su importe
  BRUTO íntegro, DESACOPLADOS del `impuesto_beneficios_pct` genérico ya sorteado (aplicado
  después de `_completar_pyg_con_deuda`, en `_evaluar`) — de lo contrario el balance deja de
  cuadrar por una fracción de euro. La cobertura coloca en balance el valor razonable BRUTO
  completo del derivado (`cobertura_valor_swap_eur`, con signo: activo si positivo, pasivo si
  negativo); la subvención coloca un cobro de caja FIJO en `disponible` (el importe concedido,
  una sola vez, que no "se devuelve" al imputarse) — asimetría real entre ambas operaciones, no
  arbitraria.
- **Tipo impositivo**: `TIPO_IMPOSITIVO_GENERAL = 0.25` (Ley 27/2014), plano, sin distinguir por
  segmento — el motor no tiene ya construido ningún mecanismo de tipo reducido en ningún otro
  punto, así que introducir uno aquí sería una hipótesis nueva no pedida por el encargo.
- **Presentación neta de impuesto**: `EjercicioEmpresa.ajustes_cambio_valor_pn_eur` (A-2) y
  `.subvenciones_pn_eur` (A-3) son propiedades derivadas (`saldo_bruto × (1−tipo)`), no estado
  propio — igual que `.activos_por_impuesto_diferido_eur`/`.pasivos_por_impuesto_diferido_eur`
  (activo/pasivo no corriente, netos dentro del total agregado — mismo patrón que
  `activo_no_corriente_desglose_eur`: detalle expuesto, no una línea nueva en `balance_eur`).
  `reservas_eur` se calcula ahora restando también estas dos líneas (antes solo capital +
  resultado).
- **Plausibilidad de la cobertura — verificación OBLIGATORIA que SÍ hacía falta** (ver
  decisiones #36): con la fuente de `tipo_interes` de ENTONCES (`ratios.coste_deuda` del
  catálogo, contaminada — ya sustituida, ver sección "Tipo de interés de mercado" más abajo), el
  peor caso de un barrido de 27×4×3 llegaba al 13,7% del balance total. `TECHO_DELTA_R_ANUAL =
  0.03` lo bajó al 2,1% en su momento. Con la fuente de mercado actual, el techo directamente NO
  se activa nunca en el mismo barrido (0/972, ver decisiones #44) — se mantiene como salvaguarda
  residual, no como límite que haga falta recalibrar.
- **EFE**: `c9_instrumentos_patrimonio` = cobro de la subvención en su año de concesión (antes
  siempre 0). `a2k_otros_ingresos_gastos` (antes siempre 0) reversa el importe bruto que la
  cobertura/subvención inyectó en `a1` vía PyG — es una reclasificación contable pura sin caja
  detrás, mismo motivo que `a2a` (amortización). `a3f` y el cálculo de B (inversión) EXCLUYEN el
  grupo89 alojado dentro de `otras_deudas_largo`/`activo_no_corriente` — sin flujo de caja, se
  duplicaría si se tratara como fuente/uso operativo u orgánico.
- **Documento A (EIGR, `generar_eigr`)** — estructura mínima: A (resultado), B.2/B.7/B.9
  (cobertura/subvención/efecto impositivo, ORIGINACIÓN de este año), C.2/C.7/C.9 (mismas 3,
  RECLASIFICACIÓN a PyG de este año, signo negativo salvo que el saldo bruto de origen ya fuera
  negativo — ver decisiones #37 sobre por qué C.2 puede salir positivo), D = A+B+C. **D coincide
  EXACTAMENTE con la fila "Total de ingresos y gastos reconocidos" del Documento B** (verificado
  numérica y algebraicamente).
- **Obligatoriedad del Documento A — corrección respecto a la versión anterior de este índice**:
  NO existe un umbral "gran empresa" distinto de modelo normal/abreviado (Art. 257 LSC) — ambos
  documentos comparten el mismo flag `obligatorio`. Ver decisiones #37 para la verificación
  externa que corrige la afirmación previa.

## Tipo de interés de mercado (`motor/empresa_base.py`, sustituye `ratios.coste_deuda`)

`gastos_financieros = deuda_financiera_media × tipo_interes` (sección "EFE y ECPN" y
"Coberturas y subvenciones" arriba) ya NO sortea `tipo_interes` desde `ratios.coste_deuda` del
catálogo ACCID — diagnóstico cerrado: ese ratio (`Gastos financieros / Préstamos`) mezcla en el
numerador partidas ajenas a intereses reales (deterioros de activos financieros, diferencias de
cambio, pérdidas en enajenación de instrumentos financieros) y su denominador puede ser una
fracción minúscula del pasivo en sectores financiados mayoritariamente con pasivo no financiero
— produce valores reales de hasta 110% (verificado a mano contra el PDF de ACCID, sector
Construcción aeronáutica, ver decisiones #38-40). Fuente nueva, en `_generar_pyg_hasta_baii`,
MISMA posición en la secuencia de `rng` (no desplaza ningún otro sorteo de la PyG):

`tipo_interes = Euríbor_12M[año] + prima_riesgo[categoría_sector] + recargo_pequeñas(si aplica) + ruido_mixto(±0,50pp)`

- **Euríbor 12M por año** (`REFERENCIA_EURIBOR_12M_POR_AÑO`), verificado externamente (Banco de
  España / fuentes agregadas, no de memoria): 2023=3,87%, 2024=3,27%, 2025=2,22% — refleja la
  forma real (pico post-subidas BCE en 2023, primeros recortes en 2024, estabilización más baja
  en 2025).
- **Prima de riesgo por categoría** (`PRIMA_RIESGO_POR_CATEGORIA`, las mismas 9 categorías de
  perfil de `activo_no_corriente`/propensión de subvención) — hipótesis de diseño razonada
  (colateral/estabilidad de demanda más alto → prima menor), pero con el NIVEL MEDIO anclado a
  una fuente externa independiente de ACCID: Banco de España, Boletín Estadístico, tabla 19.6
  (tipos TAE de nuevas operaciones a sociedades no financieras POR TRAMO DE IMPORTE del
  préstamo) — tramo >1M€ (correlaciona con "grandes_medianas") implica una prima media real de
  ~1,20pp sobre Euríbor; tramo <250k€ (correlaciona con "pequeñas") implica ~1,87pp. Las 9
  primas y el recargo plano de "pequeñas" (`RECARGO_TIPO_INTERES_PEQUEÑAS_PP=0,75pp`) se
  calibraron para que su media coincida con esos anclajes, conservando el orden relativo
  cualitativo entre categorías.
- **Ruido entre empresas**: mismo mecanismo mixto típico/atípico de siempre, dispersión de
  diseño `DISPERSION_TIPO_INTERES_PP=0,50pp` (sin MAD de catálogo detrás — no hay fuente limpia
  de la que derivarla). `SUELO_TIPO_INTERES=1,5%`/`TECHO_TIPO_INTERES=12%` (antes 1%/40%: el
  40% se alcanzaba rutinariamente con la fuente contaminada, ahora es un techo que casi nunca se
  toca).
- **Validación** (decisiones #44-46): tipo medio generado vs. tabla 19.6 de BdE, por segmento y
  año — desviación ≤0,4pp en los 6 puntos comprobados (3 años × 2 segmentos). `gastos_financieros
  / deuda_financiera` (el cálculo exacto de ACCID) recalculado sobre 8.262 ejercicios generados
  (17 arquetipos cuantitativos × 27 sectores × 3 semillas × 2 segmentos): máximo 6,81% — el
  hallazgo original (74%-110%) no se reproduce. Cross-check contra `ratios.cobertura_gastos_fin`
  del catálogo (BAII/Gastos financieros) NO es una validación limpia — ese ratio comparte el
  MISMO denominador contaminado que `coste_deuda`, así que diverge más cuanto más contaminado
  estaba `coste_deuda` para ese sector (correlación 0,375, confirmando la explicación, no un
  fallo nuevo de calibración) — tratado como evidencia débil/consistente, no como confirmación
  fuerte.
- **Re-pin necesario**: 1 solo test (`test_reimplementacion_generica_reproduce_los_valores_de_
  referencia`, endeudamiento 2024/2025 del arquetipo 1 sector 24.1 semilla 5 — 2023 y existencias
  sin cambios), por el mismo tipo de cascada legítima ya vista con la amortización
  (tipo_interes → gastos_financieros → resultado_ejercicio → PN → endeudamiento → contención).
  2 tests que comparaban contra `ratios.coste_deuda.huber_9y`/`MAD` se REESCRIBIERON (no solo
  re-pinnearon) para validar contra la fuente nueva — con la vieja referencia habían quedado
  vacíos de contenido real (el techo/suelo absoluto dominaba la cota, no el huber contaminado).

## Amortización derivada de una colección real de activos (`motor/amortizacion.py`)

Arreglo de RAÍZ, no un parche del síntoma detectado en el EFE (`a2a_amortizacion` siempre a 0€
porque no había ningún activo real detrás del gasto). Antes: `amortizaciones_pct` se sorteaba
como % independiente de PyG, sin ninguna conexión con `activo_no_corriente`. Ahora: se DERIVA
sumando las cuotas de una colección de activos generada a partir del desglose de `activo_no_
corriente` ya existente. Ver decisiones #27-#32 para el detalle completo, verificaciones y
hallazgos.

- **Qué es amortizable, verificado contra PGC (no asumido)**: terrenos NUNCA (ni en material ni
  en inversiones inmobiliarias); otros activos financieros NUNCA (instrumentos financieros,
  sujetos a deterioro, no a amortización); **fondo de comercio SÍ, desde 2016** (corrección sobre
  la premisa inicial del encargo — PGC norma 6ª, 10 años presuntos, Ley 22/2015 + RD 602/2016 —
  particularidad española, IFRS para cotizadas sigue sin amortizarlo). Prácticamente todo lo
  demás de intangible/material/construcción de inversiones inmobiliarias, sí.
- **Tabla de coeficientes fiscales**: Agencia Tributaria, tabla vigente desde 2015 (Ley 27/2014
  IS). "Vida fiscal" = `100/coeficiente MÁXIMO` (la más corta) — NO el "período máximo" de la
  tabla oficial, que corresponde al coeficiente MÍNIMO (velocidad más lenta permitida).
- **Cohorte por sub-tipo, 3 sub-lotes cada una** (no activos individuales, no una única cohorte
  por bucket): 7 sub-tipos de material (terrenos_construcciones, instalaciones_maquinaria,
  equipos_informaticos, elementos_transporte, mobiliario, otro_inmovilizado_material) + 2 de
  intangible (aplicaciones_informaticas, fondo_comercio_y_otro_intangible) + construcción de
  inversiones inmobiliarias = 9 buckets amortizables por caso, cada uno con 3 sub-lotes
  independientes (fecha de compra + "ya totalmente amortizado" sorteados por separado cada uno —
  corrección aprobada tras detectar que un único sorteo por bucket implicaba comprar toda una
  categoría el mismo día). Perfiles de sub-tipo por las 9 categorías de PERFIL (ver arriba) — HIPÓTESIS DE
  DISEÑO razonada (el catálogo ACCID no llega a este nivel), documentada como tal.
- **`SubLoteActivo.año_compra` es FRACCIONAL** (no un año entero + una instantánea de acumulada)
  — `acumulada_en(año) = min(valor_bruto, cuota_anual × (año − año_compra))`, una única fórmula
  continua válida para cualquier año — el "gasto del año" sale de la diferencia entre dos
  evaluaciones consecutivas, incluido el propio año base 2023 (bug real detectado y corregido
  durante la implementación: una primera versión con "año_ancla entero + acumulada ya
  instantánea" confundía "acumulada total desde la compra" con "gasto del año 2023" — daba un
  gasto del 54% del valor bruto en un solo año).
- **RNG propio e independiente** (`sector|segmento|amortizacion[_sufijo]`) — no desplaza ningún
  sorteo de `balance_pct`/`rotacion_activo`/PyG ya existente. La única posición que SÍ se quitó
  del bucle de primitivas de PyG es "amortizaciones" en sí (ya no se sortea) — desplaza
  `resultado_extraordinario`/`ingresos_financieros`/`impuesto_beneficios` una posición, y por
  cascada (PN distinto → endeudamiento distinto → contención distinta) puede desplazar
  existencias/realizable de 2024/2025 en los casos donde la contención se activa — el año base
  2023 (balance) nunca se ve afectado.
- **Capex (17) y adquisición (18) generan cohortes NUEVAS** con `año_compra` = el propio año del
  suceso (tratado como comprado al inicio de ese año, un año completo de cuota ya ese año —
  mismo criterio que `ventas_inorganicas_eur` del 18, sin prorratear). 17 usa el 100% del
  incremento como `instalaciones_maquinaria`; 18 usa el perfil COMPLETO de la categoría (los
  mismos perfiles ya generados para el caso, sin volver a sortear).
- **Balance sigue mostrando `activo_no_corriente` NETO tal cual ya se calculaba** (sin restar la
  amortización acumulada todavía) — la colección de cohortes queda expuesta internamente
  (`EjercicioEmpresa.coleccion_activos_amortizables`) para cuando se reabra el EFE y se decida
  netear de verdad.
- **Bienes totalmente amortizados** (`bienes_totalmente_amortizados_en`): preparado para la
  futura nota de memoria PGC punto 2.l (bienes totalmente amortizados en uso, distinguiendo
  construcciones de resto de elementos) — tipo, `es_construccion`, valor bruto, año en que se
  agotó, expuesto pero sin redactar la nota todavía.
- **Reconexión con `amortizaciones_pct` calibrado — resuelto, ver decisiones #29/#33**: la
  mayoría de sectores caen en 0,7x-2,5x el huber (variabilidad razonable). Contabilidad/auditoría
  (69.2) y Consultoría (70.2) se desviaban 8-10x — causa raíz: `rotacion_activo` inusualmente
  bajo de esos 2 sectores en el catálogo (activo_no_corriente = 2,5-2,8x los ingresos), combinado
  con tratarlos como la misma categoría de nivel superior que TIC (62), con 55% de `activo_no_
  corriente` asignado a intangible. **Corregido separando "servicios_profesionales_tic" en dos
  categorías**: "servicios_profesionales" (69.2/70.2 — `otros_financieros` dominante, 65%,
  bajo la hipótesis de estructuras de holding/participaciones, no oficinas ni software) y
  "servicios_tic" (62 — mantiene intangible alto, 50%, sin cambios sustanciales). Resultado:
  69.2 10,1x→3,9x, 70.2 7,8x→3,3x — mismo orden de magnitud que otros sectores capital-intensivos
  ya aceptados (construcción 41.2 en 4,1x); 62 sin cambio (1,0x, nunca tuvo el problema).

## Otros documentos de este índice

- **`docs/indice_arquetipos.md`** — una línea por arquetipo (1-22): mecanismo, estado, dependencias.
- **`docs/decisiones_plausibilidad.md`** — hallazgos de plausibilidad ya investigados y cerrados (no repetir la investigación).

## Dónde insertar la actualización de este índice en el flujo de cierre de lote

Después de "tests de regresión" (ya verde) y **antes** de presentar la clasificación de encaje al
usuario / comitear: 1) JSON, 2) stress test cuantificado, 3) fixes si hacen falta, 4) tests de
regresión, **5) actualizar CLAUDE.md + docs/indice_arquetipos.md + docs/decisiones_plausibilidad.md
(si hay hallazgo nuevo)**, 6) clasificación de encaje + ejemplos al usuario, 7) commit. Se coloca
al final porque el estado (mecanismo definitivo, hallazgos, si algo quedó "pendiente de revisión")
solo se conoce con certeza una vez el stress test y los fixes ya están cerrados — actualizarlo
antes arriesga tener que reescribirlo si la implementación cambia a medio lote (pasó varias veces
en este proyecto, p. ej. arquetipo 10).
