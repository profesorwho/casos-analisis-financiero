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
| `arquetipos.py` | Carga y valida `data/arquetipos.json` como dataclasses tipadas. **Sin lógica de generación.** | `cargar_arquetipos(ruta=...) -> dict[str, DefinicionArquetipo]` | Tipos de efecto: `EfectoMasaCirculante`, `EfectoPygPrimitiva`, `EfectoApalancamiento`, `EfectoTesoreria`, `EfectoReclasificacionDeuda`, `EfectoEventoPuntual`, `EfectoCapex`, `EfectoAdquisicion`, `EfectoCobertura`, `EfectoOperacionVinculada`. |
| `evolucion_arquetipo.py` | Motor genérico: evoluciona una empresa 3 ejercicios (2023 base + 2024/2025 con el/los arquetipo(s) aplicado(s)), interpretando cada tipo de `Efecto`. Contiene toda la lógica de mecanismo — **no releer para saber qué arquetipos toca cada mecanismo, ver tabla de mecanismos abajo**. `generar_evolucion_arquetipo` (un solo arquetipo) es un wrapper de una línea sobre `generar_evolucion_combinada` con un dict de 1 elemento — **garantía estructural**: cualquier test de un arquetipo en solitario que siga pasando prueba que la combinación no le cambió el comportamiento. | `generar_evolucion_combinada(sector, segmento, ventas_objetivo_2023, semilla, arquetipos_intensidades: dict[str,str], catalogo=None, arquetipos=None) -> EvolucionArquetipo` (motor general); `generar_evolucion_arquetipo(sector, segmento, ventas_objetivo_2023, semilla, intensidad, arquetipo_id, catalogo=None, arquetipos=None) -> EvolucionArquetipo` (caso de 1 arquetipo) | Todos los arquetipos de `clase="cuantitativo"` (18 — "coberturas" (21) y "operaciones_vinculadas" (20) pasaron de `memoria_pura` a `cuantitativo`, ver `docs/indice_arquetipos.md`); rechaza `clase="memoria_pura"` con `EvolucionArquetipoError`. |
| `coberturas_subvenciones.py` | Coberturas de flujos de efectivo (arquetipo 21, `EfectoCobertura`) y subvenciones de capital (transversal, disparada por el arquetipo 17 o por una probabilidad de fondo por categoría de sector) — grupo 8/9 del PGC + efecto impositivo (subgrupo 83). Ver sección "Coberturas y subvenciones" abajo para el diseño completo del cuadre. | `evolucionar_cobertura(...)`/`evolucionar_subvencion(...)` (paso anual, llamados desde `_evolucionar_un_año`); `sortear_parametros_cobertura(...)`/`sortear_subvencion_baseline(...)`/`sortear_pct_cofinanciacion(...)` (sorteos únicos por caso); `presentacion_neta_eur`/`activo_por_impuesto_diferido_eur`/`pasivo_por_impuesto_diferido_eur` (helpers puros del efecto impositivo) | `evolucion_arquetipo.py` (balance/PyG, todos los años) y `ecpn.py`/`efe.py` (consumen los campos ya expuestos en `EjercicioEmpresa`, no llaman a este módulo directamente). |
| `memoria.py` | Genera notas de memoria puramente cualitativas — arquetipos de `clase="memoria_pura"` (sin efectos numéricos, `efectos: []` en el JSON) — y orquesta el caso combinado completo (mezcla `clase="cuantitativo"` + `clase="memoria_pura"`). | `generar_nota_memoria_pura(arquetipo_id, sector, segmento, intensidad, semilla, ejercicio, etiquetas_ya_usadas=frozenset()) -> NotaMemoria` (o la función específica `generar_nota_<arquetipo>(...)`); `generar_caso_combinado(sector, segmento, ventas_objetivo_2023, semilla, arquetipos_intensidades, catalogo=None, arquetipos=None) -> EvolucionArquetipo` (punto de entrada general, cualquier mezcla de clases) | Arquetipos 7, 19, 22 (3, desde que "coberturas" -21- y "operaciones_vinculadas" -20- pasaron a `cuantitativo` — ambos siguen generando su nota cualitativa como caso especial dentro de `generar_caso_combinado`; a diferencia de 21, la de 20 ya NO sortea nada — solo formatea el importe ya calculado en `evolucion_arquetipo.py`, ver sección "Desglose de balance — segundo lote" abajo). `NotaMemoria` (definida en `evolucion_arquetipo.py`, no aquí — ver "Combinación de arquetipos" abajo) lleva `texto` + `etiquetas` (temas, usadas por el mecanismo de coherencia de la sección 2.12). Desde el encargo de insolvencias de clientes, `generar_caso_combinado` también detecta si el 7 ("dependencia_pocos_clientes") está activo y lo pasa como booleano a `generar_evolucion_combinada` — el único caso en que un arquetipo `memoria_pura` influye en la evolución NUMÉRICA, ver `motor/insolvencias.py` y la sección "Deterioro de valor de créditos por operaciones comerciales" abajo. |
| `clasificacion_legal.py` | Clasifica cada caso como modelo abreviado/normal (Art. 257 LSC) — capa de cálculo pura sobre datos que el motor YA genera (activo, cifra de negocio) más una plantilla ESTIMADA (no generada) a partir de `ratios.ventas_empleado` del catálogo. No genera balance/PyG, no toca `empresa_base.py`/`evolucion_arquetipo.py`. Ver sección "Clasificación legal" abajo. | `estimar_ventas_por_empleado(sector, segmento, semilla, catalogo=None) -> (float, str)`; `estimar_plantilla(cifra_negocio_eur, ventas_empleado_miles_eur) -> float`; `clasificar_ejercicio(año, activo_eur, cifra_negocio_eur, plantilla_estimada) -> ResultadoClasificacionLegal`; `clasificar_par_ejercicios(resultado_anterior, resultado_actual) -> "abreviado"\|"normal"` | Cualquier caso ya generado (empresa_base o evolución completa) — consume su balance/PyG, no interviene en su generación. |
| `efe.py` | Estado de Flujos de Efectivo, método indirecto, modelo NORMAL del PGC — capa de cálculo pura sobre dos `EjercicioEmpresa` consecutivos. Ver sección "EFE y ECPN" abajo para el mapeo completo y la corrección sobre la amortización. C.9 (subvenciones) y A.2.k (reverso no-cash de cobertura/subvención) desde el encargo de coberturas/subvenciones. | `generar_efe(anterior, actual, obligatorio: bool) -> EstadoFlujosEfectivo` (con propiedad `.cuadra`) | Ningún módulo de generación — solo lee `balance_eur`/`pyg_eur` ya generados, incluida la desagregación de PN/activo_no_corriente. |
| `ecpn.py` | Estado de Cambios en el Patrimonio Neto — Documento B ("Estado total de cambios en el patrimonio neto") Y Documento A ("Estado de ingresos y gastos reconocidos", EIGR, ya NO aparcado desde el encargo de coberturas/subvenciones — ver sección "Coberturas y subvenciones" abajo) del modelo NORMAL del PGC. Capa de cálculo pura sobre `EjercicioEmpresa`. | `generar_ecpn(anterior, actual, obligatorio: bool) -> EstadoCambiosPatrimonioNeto` (Documento B, con propiedad `.cuadra`); `generar_eigr(actual, obligatorio: bool) -> EstadoIngresosGastosReconocidos` (Documento A — fotografía de UN ejercicio, no de dos) | Igual que `efe.py` — ninguno de generación. |
| `provisiones.py` | Provisiones a largo/corto plazo (subgrupo 14 del PGC + 4994/4999) — tercer lote de desglose de balance, probabilidad de fondo INDEPENDIENTE de cualquier arquetipo (mismo patrón que la subvención de fondo). Ver sección "Provisiones a largo/corto plazo" abajo para el diseño completo. **No confundir con el arquetipo 22** (contingencia, puramente textual, sin tocar balance — sin cambios en este lote). | `sortear_provision_baseline(sector, segmento, semilla, categoria_sector, tier_existencias_sector) -> ParametrosProvision` (sorteo único por caso: activa/categoría/naturaleza PyG/año de dotación/plazo); `sortear_importe_provision_eur(...)`; `evolucionar_provision(parametros, importe_dotado_eur, saldo_anterior_eur, año) -> PasoProvision` (paso anual, llamado desde `_evolucionar_un_año`) | `evolucion_arquetipo.py` (balance/PyG, todos los años) — `efe.py` NO necesita ningún cambio (ver sección abajo, la dotación/exceso se reconcilia con las líneas A.3.e/f ya existentes). |
| `insolvencias.py` | Deterioro de valor de créditos por operaciones comerciales (cuenta 490 del PGC) — DETERIORO DE ACTIVO (resta de "Clientes"/`realizable`, no añade pasivo — a diferencia de `provisiones.py`). Probabilidad de fondo INDEPENDIENTE de cualquier arquetipo, anclada a `ratios.cobro_dias`, con boost si el arquetipo 4 o el 7 están activos. Ver sección "Deterioro de valor de créditos por operaciones comerciales" abajo para el diseño completo. | `factor_riesgo_cobro_dias(cobro_dias_huber) -> float`; `probabilidad_insolvencia(cobro_dias_huber, deterioro_ciclo_caja_activo, dependencia_clientes_activo) -> float`; `sortear_insolvencia_baseline(sector, segmento, semilla, cobro_dias_huber, deterioro_ciclo_caja_activo, dependencia_clientes_activo) -> ParametrosInsolvencia` (sorteo único por caso); `sortear_importe_insolvencia_eur(...)`; `evolucionar_insolvencia(parametros, importe_dotado_eur, saldo_anterior_eur, exceso_acumulado_anterior_eur, año) -> PasoInsolvencia` (paso anual, llamado desde `_evolucionar_un_año`) | `evolucion_arquetipo.py` (balance/PyG, todos los años; resta de `realizable_eur` SOLO dentro de `_evaluar`, nunca antes de `_deficit_y_deuda_corto`) y `memoria.py` (`generar_caso_combinado` detecta el arquetipo 7 y lo pasa como booleano) — `efe.py` NO necesita ningún cambio (ver sección abajo, `a3b_deudores` ya existente la reconcilia). |
| `resumen_caso.py` | Resumen consolidado de particularidades de un caso YA generado (sección 2.15/2.9) — capa de AGREGACIÓN pura, NO genera ni corrige ningún dato. Ver sección "Resumen consolidado de particularidades del caso" abajo. | `resumen_particularidades_caso(evolucion: EvolucionArquetipo) -> ResumenParticularidadesCaso` | Nada de generación — solo lee `EvolucionArquetipo`/`EjercicioEmpresa` ya generados. |
| `rubrica_diagnostico.py` | Carga y valida `data/rubrica_diagnostico.json` (sección 2.19) como dataclasses tipadas — mismo patrón que `motor.arquetipos`, sin lógica de generación ni de cálculo. | `cargar_rubrica_diagnostico(ruta=...) -> RubricaDiagnostico` | Nada del motor — contenido estructurado puro. |
| `similitud_casos.py` | Función de comparación entre dos casos ya generados (sección 2.20, pieza PARCIAL — sin aplicarla todavía sobre ningún repositorio, que es Fase 5). Ver sección "Función de similitud entre casos" abajo. | `similitud_entre_casos(caso_a, caso_b, catalogo=None) -> SimilitudCasos` | Nada de generación — capa de cálculo pura sobre dos `EvolucionArquetipo` ya generados + el catálogo (para normalizar el perfil numérico). |

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
| `operacion_vinculada` | Tampoco sigue el molde genérico de continuidad — igual que `cobertura`, la magnitud real vive en `ParametrosOperacionVinculada` (sorteo único por caso, `_sortear_operacion_vinculada`), no en el `Efecto` del JSON (solo trazabilidad). Selecciona UNA de 5 operaciones; las 2 financieras (préstamo a matriz/financiación recibida de grupo) se pliegan en `activo_no_corriente_eur`/`otras_deudas_largo_eur`/`disponible_proporcional_eur` ANTES del chequeo de endeudamiento, igual que grupo89; las 3 comerciales/"varios" fuerzan una sub-partida del desglose de deudores/acreedores en el año base. Ver sección "Desglose de balance — segundo lote" abajo. | 20 (también genera su nota de memoria cualitativa, como caso especial en `motor.memoria.generar_caso_combinado` — a diferencia de 21, ya NO sortea nada allí) |
| Contención de endeudamiento | Chequeo **incondicional** cada año: si el endeudamiento supera `huber+3·MAD` (techo absoluto 0,85), amortigua vía las masas de ACTIVO tocadas por el arquetipo, si las hay; si no, queda `contencion_al_limite=True` (señal sin corrección posible). | Todos (corre siempre, toque o no circulante) |
| Hash estable sector+segmento (`zlib.crc32`) | Siembra cada RNG (`generar_empresa_base`, `rng_tendencia`/`rngs_pyg`, `rngs_nota`) mezclando semilla+sector+segmento — **nunca intensidad** (mismo "ruido de fondo" entre intensidades del mismo caso, por diseño). | Todos — infraestructura, no arquetipo-específico |
| `nota_memoria` (campo `EjercicioEmpresa.notas_memoria: tuple[NotaMemoria,...]`, plural — antes `str \| None` singular) | Cobertura narrativa reproducible (RNG dedicado `rngs_nota`/`rngs_nota_por_arquetipo`, redacciones alternativas por arquetipo). Opcional (10: caso límite; 16: huella habitual) u OBLIGATORIA (18). El paso a tupla (en vez de campo único) es lo que permite que 2+ arquetipos con nota numérica activos a la vez no se pisen entre sí. | 10, 16, 18 |
| `clase="memoria_pura"` (en `motor.memoria`, no `evolucion_arquetipo.py`) | Arquetipo SIN efectos numéricos (`efectos: []`) — la nota de memoria se genera con una función propia de `motor.memoria`, no pasa por `_evolucionar_un_año`. RNG dedicado por (sector, segmento, intensidad, **arquetipo_id**, semilla) — a diferencia del resto, mezcla también el arquetipo_id, para que varias notas de memoria puedan combinarse sobre el mismo caso sin compartir estado. | 7, 19, 22 (20 y 21 son `cuantitativo`, pero siguen generando su nota cualitativa como caso especial — ver filas `cobertura`/`operacion_vinculada` arriba) |

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
  0, documentado, no inventado): correcciones valorativas, bajas de inmovilizado, diferencias de
  cambio, valor razonable, dividendos de terceros, "otros activos corrientes" (A.3.c). **Las
  provisiones (tercer lote) SÍ tienen mecanismo desde ese encargo — fluyen por A.3.e/A.3.f, sin
  ninguna línea nueva, ver sección "Provisiones" abajo.** **C.9 ("Instrumentos de patrimonio...
  subvenciones") ya NO es siempre 0** desde el encargo de coberturas/subvenciones: = cobro de
  caja de la subvención en su año de concesión (ver sección "Coberturas y subvenciones" abajo).
  **B.6.c "Préstamo a empresas del grupo" y C.10.c "Empresas del grupo"** (variación de
  `inversion_grupo_largo_eur`/`deuda_grupo_largo_eur`, ambas siempre 0 salvo que el arquetipo 20
  active esa operación concreta) desde el segundo lote de desglose de balance — ver sección
  "Desglose de balance — segundo lote" más abajo. `c10` (deuda con entidades de crédito) queda
  estrictamente separado de `c10c` (deuda con el grupo, sin coste financiero): mezclarlos
  confundiría deuda que sí genera `gastos_financieros` con deuda que no. **`c10` excluye el
  derivado del arquetipo 21 cuando es PASIVO** (cuarto y último lote de desglose de balance,
  `max(0.0, -cobertura_valor_swap_eur)`, en ambos años) — desde ese lote vive dentro de
  `deudas_fin_largo` en vez de `otras_deudas_largo` (aproximación anterior, donde SÍ se excluía
  de `a3f`); mismo tratamiento de siempre (sin flujo de caja propio), solo cambió qué línea lo
  excluye — ver sección "Deudas financieras — cuarto lote" más abajo.
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
  completo del derivado (`cobertura_valor_swap_eur`, con signo: activo si positivo → sigue en
  `activo_no_corriente`; pasivo si negativo → desde el cuarto lote de desglose de balance,
  línea propia "IV. Derivados" dentro de `deudas_fin_largo`, NUNCA dentro de la base que alimenta
  `gastos_financieros`, ver sección "Deudas financieras — cuarto lote" más abajo); la subvención
  coloca un cobro de caja FIJO en `disponible` (el importe concedido, una sola vez, que no "se
  devuelve" al imputarse) — asimetría real entre ambas operaciones, no arbitraria.
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
  impuesto diferido de grupo89 y el derivado-si-es-ACTIVO alojados en `otras_deudas_largo`/
  `activo_no_corriente` — sin flujo de caja, se duplicaría si se tratara como fuente/uso
  operativo u orgánico. **El derivado-si-es-PASIVO ya NO se excluye aquí** (desde el cuarto lote
  de desglose de balance ya no vive en `otras_deudas_largo`) — su exclusión equivalente está
  ahora en `c10`, ver arriba.
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

## Desglose de balance según el PGC — primer lote: existencias y periodificaciones (`motor/empresa_base.py`)

Primer lote de un plan más amplio (pendiente de más lotes futuros) para reflejar el mapeo
oficial de partidas del PGC dentro de las masas agregadas que ya genera el motor. Mismo patrón
que `activo_no_corriente` (perfil % fijo desde 2023 por categoría de sector, ruido mixto,
desglose en € recalculado cada año sobre la masa agregada YA cuadrada — el balance sigue
mostrando solo el total, el detalle queda expuesto internamente, no se muestra todavía al
usuario final). RNG propio e independiente (`rng_desglose_balance`, entropía
`"desglose_balance_lote1"`), no desplaza ningún sorteo existente — 0 re-pins en la regresión.

- **Existencias** (`PERFIL_EXISTENCIAS_POR_TIER`, `TIER_EXISTENCIAS_POR_SECTOR`,
  `generar_perfil_existencias`) — 6 sub-partidas oficiales (comerciales, materias primas,
  productos en curso, productos terminados, subproductos/residuos, anticipos a proveedores).
  Clasificación por SECTOR (no por `categoria_de_sector`): verificado contra el dato real de
  `balance.existencias_pct` del catálogo que varios sectores de una misma categoría de
  `activo_no_corriente` tienen un carácter de existencias radicalmente distinto (55.1 Hoteles al
  0,84% del activo frente a 47.1 Supermercados al 10,75%, ambos en "comercio_hosteleria"; 68
  Inmobiliario al 13,79%, de los más altos del catálogo). 8 tiers: `industria`/
  `servicios_industriales`/`comercio_hosteleria`/`construccion` (existencias reales, sin
  cambios); `producto_en_curso` (69.2/70.2/62/71/72 — servicios "por proyecto/encargo" sin
  producto físico, concentrado ~85% en `productos_curso` reinterpretado como trabajos en curso
  no facturados); `cero_total` (85/52/55.1/4941 — dato real ya marginal, <1,1% del activo,
  reparto neutro 1/6 sin pretensión de significado de negocio); `inmobiliario_mixto` (68 — el
  CNAE agregado mezcla promoción, con existencias reales, y arrendamiento puro; dominado por
  `productos_curso`+`productos_terminados`, misma lógica que construcción); `sanidad_consumibles`
  (86.1, separado de 85 Educación pese a compartir categoría de `activo_no_corriente` — el dato
  real diverge ~4x; dominado por `materias_primas`, consumibles/material sanitario fungible).
  Conectado automáticamente con el arquetipo 5 ("exceso de stock"): el desglose se recalcula
  cada año aplicando el perfil FIJO al `existencias` total de ese año, así que el exceso se
  reparte solo según la mezcla habitual del sector, sin código especial.
- **Periodificaciones** — NO son una masa nueva del balance: se tallan como fracción de una masa
  YA existente. Activo (`PERIODIFICACION_ACTIVO_PCT_POR_CATEGORIA`) como fracción de
  `realizable` (el modelo oficial solo tiene periodificaciones de activo a CORTO plazo). Pasivo
  (`PERIODIFICACION_PASIVO_PCT_POR_CATEGORIA`) como fracción de `otras_deudas_corto` Y de
  `otras_deudas_largo` por separado (dos sorteos independientes, mismo centro por categoría —
  el modelo oficial SÍ tiene periodificaciones de pasivo a ambos plazos). Expuestas como
  propiedades (`EjercicioEmpresa.periodificacion_activo_eur`/`..._pasivo_corto_eur`/
  `..._pasivo_largo_eur`), no como campos almacenados — se derivan de `pct × masa` en cada
  acceso, sin necesidad de recalcularlas explícitamente en el `return` de `_evolucionar_un_año`.
- **FM/NOF**: el motor NO calcula ningún "fondo de maniobra"/NOF como magnitud reportada aparte
  — solo existe el mecanismo interno de déficit de NOF (`_deficit_y_deuda_corto`, sección
  "Mecanismos reutilizables" más abajo), que opera sobre las masas AGREGADAS
  (`existencias`/`realizable`/`acreedores_comerciales`). Como este lote talla sub-detalle DENTRO
  de masas ya existentes sin cambiar ningún total agregado, ese mecanismo queda automáticamente
  intacto (verificado: el diff de este lote no toca `_deficit_y_deuda_corto`/`presion_nof_eur`
  en absoluto) — el detalle nuevo es coherente con lo que ese cálculo ya usaba, no una entrada
  nueva que haya que enchufarle.
- **Verificación de "combinaciones ilógicas"**: NO es "el componente dominante nunca cambia"
  (varias categorías tienen 2-3 componentes deliberadamente próximos — p. ej. industria
  28%/27%/30% entre materias primas/curso/terminados, donde el ruido SÍ puede alterar cuál
  queda primero sin que sea ilógico) — son parejas semánticas concretas por tier, una por cada
  uno de los 8 (comercio: `comerciales` > cualquier partida de producción; construcción/
  inmobiliario_mixto: `productos_curso` > `comerciales`; industria: `comerciales` nunca es la
  partida mayor; producto_en_curso: `productos_curso` > el resto combinado; sanidad_consumibles:
  `materias_primas` > `comerciales`/`productos_terminados`; cero_total: el TOTAL de existencias
  sigue siendo marginal en el año base 2023, sin pretensión sobre su composición interna).

## Desglose de balance según el PGC — segundo lote: deudores/acreedores comerciales y empresas del grupo (`motor/empresa_base.py`, `motor/evolucion_arquetipo.py`, `motor/memoria.py`, `motor/efe.py`)

Segundo lote del mismo plan que el primero (existencias/periodificaciones, arriba). Cubre
"Deudores comerciales y otras cuentas a cobrar" / "Acreedores comerciales y otras cuentas a
pagar" (7 sub-partidas oficiales cada uno, carve-out de `realizable`/`acreedores_comerciales`,
mismo patrón "perfil % fijo, desglose recalculado cada año") y las 2 masas de "Empresas del
grupo y asociadas" que el arquetipo 20 puede activar — ver decisiones #54-59.

- **Deudores** (`PERFIL_DEUDORES_BASE`, `generar_perfil_deudores`) — perfil ÚNICO, sin excepción
  sectorial (a diferencia de existencias): `ratios.cobro_dias` del catálogo confirma que
  "Clientes" ES, esencialmente, la totalidad de `realizable` en los 27 sectores (ratio cobro_dias
  real / días implícitos de `realizable_pct` entre 0,89 y 1,13, sin excepción). `clientes=88%`,
  resto marginal, `clientes_empresas_grupo=0%` salvo arquetipo 20.
- **Acreedores** (`PERFIL_ACREEDORES_POR_CATEGORIA`, `generar_perfil_acreedores`) — perfil por las
  9 categorías de `CATEGORIA_SECTOR` (no un perfil único: `ratios.pago_dias` del catálogo tiene el
  MISMO problema ya diagnosticado en `ratios.coste_deuda`, #41 — denominador minúsculo en
  servicios, divergencia 1,1x-10,2x frente a los días implícitos — se usa solo su dirección
  cualitativa, nunca como ancla literal, ver #55). `proveedores` dominante en las 9 (52-82%), con
  peso relativo mayor de "Personal (remuneraciones pendientes)" en categorías intensivas en mano
  de obra (servicios profesionales/TIC, administración/educación/sanidad — dato SÍ fiable:
  `gastos_personal_pct`). `proveedores_empresas_grupo=0%` salvo arquetipo 20.
- **Arquetipo 20 ("Operaciones vinculadas") promovido a `clase="cuantitativo"`** (mismo criterio
  que "coberturas", ver #34 y sección de abajo) — sus 5 operaciones se clasifican comercial/
  financiera/"no es realmente grupo" (texto literal de cada plantilla, ver #56 y docstring de
  `motor/evolucion_arquetipo.py`, bloque "Operaciones vinculadas"):
  - **0 "préstamo a matriz"** (la sociedad PRESTA) — financiera, ACTIVO → masa nueva
    `inversion_grupo_largo_eur` ("Inversiones en empresas del grupo y asociadas a l/p").
  - **1 "facturación de servicios de gestión al grupo"** — comercial, ACTIVO → sub-partida
    `clientes_empresas_grupo` de deudores.
  - **2 "arrendamiento pagado a socio/administrador"** — NO es "empresas del grupo" en sentido
    PGC → `acreedores_varios` de acreedores, nunca la línea de grupo.
  - **3 "financiación recibida de grupo"** — financiera, PASIVO → masa nueva
    `deuda_grupo_largo_eur` ("Deudas con empresas del grupo y asociadas a l/p"); el propio texto
    de la nota excluye gastos financieros adicionales, así que esta masa NUNCA entra en
    `deudas_fin_largo/corto` (las únicas que alimentan `gastos_financieros`).
  - **4 "asistencia técnica prestada por la matriz"** — comercial, PASIVO → sub-partida
    `proveedores_empresas_grupo` de acreedores.
  - Solo UNA de las 5 está activa por caso (índice sorteado una vez, `ParametrosOperacionVinculada`
    en `motor/evolucion_arquetipo.py`). Las 4 no seleccionadas quedan en 0 (Tipo 2 puro, SIN
    probabilidad de fondo — a diferencia de provisiones, arquetipo 6).
- **Mecánica temporal de las 2 masas financieras (0 y 3)** — perfil continuo desde que el
  arquetipo se activa, NO un evento discreto en un año fijo (a diferencia de la adquisición del
  18): `% fijo de la magnitud de referencia (patrimonio_neto/deuda financiera) del año ANTERIOR
  ya resuelto`, recalculado cada año — mismo patrón "perfil fijo, € recalculado" que el resto de
  este bloque, sin mecanismo nuevo. Se pliega en `activo_no_corriente_eur`/`otras_deudas_largo_
  eur`/`disponible_proporcional_eur` ANTES de `_construir_balance`/`_evaluar`, igual que grupo89,
  así que el chequeo de endeudamiento (incondicional, sección "Mecanismos reutilizables") la ve
  SIEMPRE — "financiación recibida de grupo" pasa por la MISMA contención que ya protege a
  9/14/17/18 (señalizada, sin palanca de amortiguación propia: el arquetipo 20 no toca circulante,
  ver #57). Techo defensivo `TECHO_FRACCION_DISPONIBLE_PRESTAMO_MATRIZ=0,9` sobre "préstamo a
  matriz" (nunca deja `disponible` negativo) — interactúa raramente (2/324 en el barrido de
  plausibilidad) con `SUELO_IMPORTE_VINCULADAS_EUR`, documentado como excepción aceptada.
- **Nota de memoria del arquetipo 20 ya NO sortea nada** (`motor/memoria.py`,
  `generar_nota_operaciones_vinculadas`): el sorteo (índice de plantilla + % objetivo) se movió a
  `motor.evolucion_arquetipo._sortear_operacion_vinculada` — MISMA secuencia exacta de rng que
  usaba antes `motor.memoria` (mismo hash de entropía, mismo `rng.permutation`/`rng.uniform`), así
  que el resultado es idéntico, pero ahora el importe alimenta el balance directamente y la nota
  se limita a formatear ese mismo número — "no generar un número nuevo independiente", a
  diferencia de "coberturas" (21), donde el % del nocional citado en la nota SÍ es independiente
  del nocional modelado en el balance (ver #35, decisión distinta y documentada como tal).
- **EFE** — 2 líneas nuevas: `b6c_prestamo_empresas_grupo` (Sección B, junto a
  `b6a_empresas_grupo_adquisicion`) y `c10c_empresas_grupo` (Sección C, letra (c) del desglose
  oficial de la línea 10, SIEMPRE separada de `c10` — ver sección EFE arriba y #58: la premisa de
  que ya existía una línea C.10 propia para el grupo no era correcta, corregida antes de
  implementar, no asumida).
- **Verificación de "combinaciones ilógicas" reforzada** (lección explícita del lote 1, #48): no
  solo "la categoría dominante tiene sentido" (proveedores/clientes dominan siempre), también qué
  sub-partidas deben quedar en CERO para qué tipo de caso — `clientes_empresas_grupo`/
  `proveedores_empresas_grupo`/las 2 masas financieras en 0 exacto sin arquetipo 20 activo,
  verificado en el barrido, no solo asumido por construcción.

## Provisiones a largo/corto plazo — tercer lote de desglose de balance (`motor/provisiones.py`)

Epígrafes propios del balance oficial (B.I "Provisiones a largo plazo", C.II "Provisiones a
corto plazo"), hoy ausentes del motor. Ver decisiones #60-64.

- **Provisión vs. contingencia — NO confundir.** Una PROVISIÓN (este lote) es una obligación
  probable Y estimable con fiabilidad, SÍ se reconoce en balance. Una CONTINGENCIA (arquetipo 22,
  `motor/memoria.py`, tema "contingencia legal" — **sin ningún cambio en este lote**) es posible o
  no estimable, NO se reconoce en balance, solo se menciona en memoria. Verificado que coexisten
  sin relación causal (combinado con el 22, el saldo/movimiento de la provisión es idéntico al del
  mismo caso en solitario — ver #63).
- **8 categorías** (subgrupo 14 + 4994/4999): 140 (retribuciones al personal, →`gastos_personal`),
  141/142/143/145/146/4994/4999 (→`otros_gastos_explot`). **147 descartada explícitamente**
  (pagos basados en instrumentos de patrimonio propio — mecanismo de cotizadas/startups, ajeno al
  perfil PYME de los 27 sectores).
- **Probabilidad de fondo PLANA, INDEPENDIENTE de cualquier arquetipo** (`PROBABILIDAD_PROVISION
  = 0.25`, mismo patrón ya construido para `sortear_subvencion_baseline` en
  `coberturas_subvenciones.py`) — puede aparecer con el arquetipo 6 ("línea base sana") o
  cualquier otro. Verificado 26,4% observado en barrido, dentro del 20%-30% pedido (#61). Qué
  categoría sale, ponderado por sector/tier (143 desmantelamiento × industria/construcción; 4994
  contratos onerosos × tier `producto_en_curso` del lote 1 + construcción; 4999 garantías ×
  industria/comercio — todos verificados cuantitativamente, no solo por construcción del peso).
- **Magnitud**: 1-6% de `patrimonio_neto` del año anterior a la dotación (sin dato de catálogo que
  lo ancle, mismo criterio que "préstamo a matriz" del arquetipo 20 pero un rango menor), suelo
  15.000€. Año de dotación 2024 o 2025 (50/50, mismo patrón que `año_concesion` de la subvención
  de fondo) — NUNCA en el año base 2023.
- **Largo↔corto: reclasificación, no dos catálogos** (confirmado contra el PGC, subgrupo 529 =
  mismo catálogo reclasificado). Cada provisión sortea un `plazo_total_años` (1,5-4,0) UNA vez;
  cada año se reclasifica ÍNTEGRA (nunca repartida) según si el horizonte restante supera 1 año —
  mismo ESPÍRITU que `EfectoReclasificacionDeuda` (mover saldo entre plazos sin alterar el total),
  mecanismo distinto por necesidad (sin ratio de catálogo al que anclar el vencimiento). Se pliega
  en `otras_deudas_largo_eur`/`otras_deudas_corto_eur` ANTES de `_construir_balance`, EXCLUIDA de
  su propia base proporcional al año siguiente — mismo patrón que grupo89/operaciones vinculadas.
- **Movimiento anual** (saldo inicial/dotación/aplicación/exceso/saldo final, expuesto en
  `EjercicioEmpresa.provision_saldo_largo_eur`/`..._corto_eur`/`..._dotacion_eur`/
  `..._aplicacion_eur`/`..._exceso_eur`) — dotación ÍNTEGRA el año de dotación; a partir de ahí,
  liberación LINEAL (tasa anual = importe dotado / plazo) repartida `FRACCION_APLICACION=0.70`
  aplicación (uso real, sale de `disponible`) / 0.30 exceso (reversión a resultados, sin caja).
- **Conexión con PyG**: dotación resta de `gastos_personal` (140) u `otros_gastos_explot` (resto);
  exceso suma a `otros_ingresos_explot` (línea oficial "Excesos de provisiones" NO desglosada como
  línea propia en `pyg_eur` — mismo criterio de simplificación ya usado para la imputación de
  subvenciones; el importe distinto sigue expuesto aparte en `provision_exceso_eur`). Inyectado
  POST-HOC (mismo patrón que grupo89, dentro de `_evaluar`) — puede empujar `margen_bruto_pct`/
  `baii_pct`/`gastos_personal_pct` unos puntos-base fuera de una contención de plausibilidad YA
  calculada sin la provisión (misma interacción que #39, 3 tests existentes ampliaron su exclusión,
  0 re-pins — ver #60).
- **EFE: SIN líneas nuevas** — a diferencia de grupo89 (valoración pura, sin caja detrás), la
  dotación/exceso de provisión SIEMPRE tiene contrapartida real en `otras_deudas_largo`/
  `otras_deudas_corto`, así que A.3.e/A.3.f (ya existentes) la reconcilian exactamente sin ningún
  cambio en `motor/efe.py` — verificado, no asumido (0 descuadres en 200 EFE con provisión activa).

## Deterioro de valor de créditos por operaciones comerciales (`motor/insolvencias.py`)

Cuenta 490 del PGC — DETERIORO DE ACTIVO: resta directamente de "Clientes" dentro de
`realizable` (Deudores comerciales y otras cuentas a cobrar), a diferencia de las provisiones de
arriba (subgrupo 14, pasivo, no añade ninguna deuda nueva). Ver decisiones #86.

- **Probabilidad de fondo, independiente de cualquier arquetipo** (mismo patrón que provisiones/
  subvención de fondo) — puede aparecer con el arquetipo 6 ("Aumento de clientes (base)"), sin
  depender de que haya un arquetipo de riesgo activo. Verificado: 26,4% observado en un barrido
  de 216 casos (27 sectores × 8 semillas) con el 6, dentro del 20%-40% de base pedido.
- **Magnitud (probabilidad Y importe) anclada a `ratios.cobro_dias` del catálogo, no un sorteo
  independiente**: rampa lineal (`factor_riesgo_cobro_dias`) entre 60 días (`UMBRAL_COBRO_DIAS_
  INSOLVENCIA`, sin riesgo adicional sobre el suelo) y 150 días (`TECHO_COBRO_DIAS_INSOLVENCIA`,
  riesgo máximo) — ambos anclados a la distribución real de `ratios.cobro_dias.huber_9y` de los
  27 sectores (9,6-186,3 días, media≈86,3, mediana≈84,0). Probabilidad 20%-40%
  (`PROBABILIDAD_INSOLVENCIA_SUELO/TECHO`); importe 2%-5% de "Clientes" en el extremo sin riesgo,
  4%-10% en el extremo de mayor riesgo (`RANGO_IMPORTE_PCT_CLIENTES_SUELO/TECHO`), suelo
  defensivo 5.000€. Verificado empíricamente (no solo por construcción de la rampa): sector de
  cobro largo (30.2, 186,3 días) con tasa de activación Y magnitud media mayores que sector de
  cobro corto (47.1, 9,6 días) en barridos de 25 semillas cada uno.
- **Boost de arquetipo 4 (deterioro del ciclo de caja) y 7 (dependencia de pocos clientes)**:
  +10pp de probabilidad cada uno (acumulables, tope absoluto `TECHO_PROBABILIDAD_INSOLVENCIA_
  ABSOLUTO=60%`), ×1,3 de magnitud si cualquiera de los dos está activo (no acumulable entre
  ambos — misma razón económica "esto es más arriesgado de lo normal", no dos riesgos
  independientes que se sumen). El 4 es `clase="cuantitativo"`, se detecta directamente en
  `generar_evolucion_combinada`. **El 7 es `clase="memoria_pura"` — caso especial, único
  arquetipo de esa clase que influye en la evolución NUMÉRICA**: `motor.memoria.generar_caso_
  combinado` detecta `"dependencia_pocos_clientes" in ids_memoria_pura` y lo pasa como booleano
  (`dependencia_pocos_clientes_activo`) a `generar_evolucion_combinada` — el único puente que
  existe hoy entre ambas clases (`generar_evolucion_combinada` en solitario sigue sin aceptar
  ningún arquetipo `memoria_pura`, solo este booleano aislado). **Verificado EN LA PRÁCTICA, no
  solo a nivel de fórmula** (pedido explícitamente): vía `generar_caso_combinado`, sector de
  cobro corto (47.1, probabilidad de base en su suelo 20%), 40 semillas — tasa de activación
  20,0% sin el 7 → 27,5% con el 7; semilla 23 es un caso "flip" completo (sin el 7 no activa, con
  el 7 sí); en los casos donde ambos activan, el importe dotado con el 7 escala EXACTAMENTE
  ×1,3000 (mismo draw de magnitud, RNG independiente del boost — solo cambia el multiplicador
  final).
- **Movimiento anual** (saldo inicial/dotación/aplicación/reversión/saldo final,
  `EjercicioEmpresa.insolvencia_saldo_eur`/`..._dotacion_eur`/`..._aplicacion_eur`/`..._exceso_
  eur`) — mismo patrón que provisiones: dotación ÍNTEGRA el año de dotación (2024 o 2025, 50/50,
  nunca en el año base), liberación LINEAL a partir de ahí (tasa anual = importe dotado / plazo,
  `RANGO_PLAZO_TOTAL_AÑOS_INSOLVENCIA=(0,5, 2,0)`, horizonte más corto que provisiones — un
  cliente concreto se resuelve más rápido que una provisión genérica), `FRACCION_APLICACION=0,70`
  aplicación / 0,30 exceso.
- **Aplicación vs. reversión — asimetría deliberada, DISTINTA de provisiones**: en provisiones
  (pasivo), tanto la aplicación (uso real) como el exceso (reversión) liberan el pasivo por
  igual. Aquí NO: la aplicación es la baja DEFINITIVA del derecho de cobro — retira a la vez, por
  el mismo importe, "Clientes" bruto y el deterioro que lo cubría, efecto NETO cero sobre
  `realizable` (la pérdida ya se reconoció íntegra en PyG el año de la dotación, no se revierte).
  La reversión SÍ es una mejora económica real (el cliente pagó después de todo) — libera
  `realizable` de verdad. Por eso `EjercicioEmpresa.insolvencia_deduccion_realizable_eur` (lo que
  de verdad se resta de `realizable_eur`, `= importe_dotado_eur − exceso_acumulado_eur`) es
  DISTINTO de `insolvencia_saldo_eur` (el deterioro vivo, expuesto para la memoria/futura
  incidencia didáctica, que decrece con aplicación Y reversión como en provisiones) — verificado
  con un test dedicado, no solo documentado.
- **Dónde se aplica la deducción — NO donde se sortea**: `realizable_eur` es una de las 3 masas
  de circulante que alimentan `_deficit_y_deuda_corto` (déficit de NOF) — restar ahí el deterioro
  lo contaminaría con un evento que no es de ciclo de caja. La deducción se aplica SOLO dentro de
  `_evaluar`, justo antes de `_construir_balance` (`realizable_neto_insolvencia_eur`), después de
  que `_deficit_y_deuda_corto` ya vio el `realizable_eur` bruto — mismo criterio que evitar que el
  payout (deuda extra) retroalimente su propio año. El endeudamiento (chequeo incondicional, ver
  "Mecanismos reutilizables") SÍ ve el `realizable` ya neto (activo total menor, correcto: un
  deterioro real reduce el activo que respalda la deuda).
- **Conexión con PyG**: dotación resta SIEMPRE de `otros_gastos_explot` (cuenta 490, nunca gasto
  de personal, a diferencia de la categoría 140 de provisiones); exceso suma a `otros_ingresos_
  explot` ("Excesos de provisiones", misma línea que provisiones). Inyectado POST-HOC en el MISMO
  bloque compartido que grupo89/provisión, dentro de `_evaluar` — misma interacción ya aceptada
  con la contención de plausibilidad de PyG (#39/#60), extendida aquí a `insolvencia_dotacion_
  eur`/`..._exceso_eur` en los tests de `margen_bruto`/`baii` (0 re-pins).
- **Desglose de deudores** (`deudores_desglose_eur`, segundo lote) — sin código especial: el
  perfil % fijo se aplica al `realizable` YA neto de insolvencia, así que "Clientes" (~88% del
  total) y el resto de sub-partidas reflejan el deterioro proporcionalmente, igual que ya ocurre
  con el exceso de stock del arquetipo 5 sobre existencias. Suma exacta verificada (no asumida).
- **EFE: SIN líneas nuevas, verificado EMPÍRICAMENTE** (no solo algebraico) — `a3b_deudores`
  (`motor/efe.py`, `= -(actual.balance_eur["realizable"] - anterior.balance_eur["realizable"])`)
  ya absorbe el efecto exacto, sin ningún cambio en `motor/efe.py` (0 descuadres, `a3b_deudores`
  comprobado contra la fórmula esperada caso a caso).
- **Preparación para el futuro sistema de incidencias didácticas** (aplazado, no forma parte de
  este encargo): `insolvencia_activa`/`insolvencia_categoria` (no aplica, cuenta única)/
  `insolvencia_importe_dotado_eur`/`insolvencia_saldo_eur`/movimiento anual completo quedan
  expuestos en `EjercicioEmpresa`, mismo criterio que amortización/provisiones, para que la
  incidencia "cliente deteriorado no provisionado" pueda identificar y suprimir esta provisión
  sobre un caso ya generado cuando se construya esa capa.

## Deudas financieras — cuarto y último lote de desglose de balance (`motor/empresa_base.py`)

Completa el desglose granular de balance/PyG según el PGC — 5 categorías oficiales de "Deudas
financieras" (largo y corto plazo, carve-out de `deudas_fin_largo`/`deudas_fin_corto`), con
Derivados como línea propia para la cobertura del arquetipo 21. Ver decisiones #66-69.

- **Clasificación por Tipo** (`PERFIL_DEUDAS_FIN_POR_CATEGORIA`, `calcular_desglose_deudas_fin` en
  `motor/empresa_base.py`): **Entidades de crédito** — Tipo 1, NUNCA sorteado, es el RESIDUAL tras
  restar las otras 3 al total con coste (dominante por defecto). **Arrendamiento financiero** —
  Tipo 1, perfil por categoría de sector (mayor en transporte_logistica 30%/construcción
  22%/industria 18% — activo material pesado, conecta con las cohortes de `motor/amortizacion.py`;
  menor en servicios de oficina 4-6%), sin ancla de catálogo (hipótesis de diseño, verificado que
  ninguna de las 218 columnas distingue esta financiación). **Obligaciones y valores negociables**
  — Tipo 1, casi cero salvo industria (4%, incluye energía/siderurgia). **Otros pasivos
  financieros** — Tipo 1, residual plano 3%. **Derivados** — Tipo 2 puro, sin probabilidad de
  fondo, disparado exclusivamente por `cobertura_valor_swap_eur < 0` (arquetipo 21).
- **`reclasificacion_deuda` (8/16) opera SOLO sobre "Entidades de crédito"** — decisión del
  usuario, corregida ANTES de implementar (ver #67): el mismo argumento que justifica el Tipo
  propio del leasing ("calendario fijo por contrato, no se renegocia como un préstamo bancario")
  es el argumento contra dejar que 8/16 lo mueva. El mecanismo en sí (`_mover_ratio_continuo`
  sobre `deudas_fin_largo/corto_proporcional_eur`) NO se tocó — la exclusión se logra enteramente
  en el desglose posterior: arrendamiento financiero/obligaciones/otros mantienen su propio
  reparto largo/corto FIJO por caso (`FRACCION_LARGO_POR_TIPO_DEUDA_FIN`, por TIPO de
  instrumento, no por sector), y "Entidades de crédito" absorbe como residual lo que 8/16 mueva.
  Verificado cuantitativamente (no asumido): con 16 activo, la fracción largo/total de
  leasing/obligaciones/otros se mantiene estable (Δ<0,03) mientras la de entidades de crédito se
  mueve con fuerza (Δ>0,05). **Techo defensivo**: si el reparto fijo de esas 3 categorías pidiera
  más "largo" del que existe ese año (sectores/semillas con un draw atípico del catálogo,
  `deudas_fin_largo` ya casi nulo por el ruido 85%/15% — no relacionado con la reclasificación en
  sí), se reescala proporcionalmente ENTRE ELLAS (nunca a costa de "Entidades de crédito", que ya
  es 0 en ese caso) para que la suma nunca supere el total real — verificado en 648 ejercicios de
  estrés: 0 casos negativos, 0 descuadres.
- **Endeudamiento (9/14/17/18/20) sin cambios** — `_endeudamiento` opera sobre `pasivo_no_
  corriente`/`pasivo_corriente` ya agregados; el desglose interno (una partición de esos mismos
  euros) no puede, por construcción, alterar ese total — confirmado, no solo argumentado.
- **Migración del derivado del arquetipo 21** — desde la aproximación anterior ("otros activos
  financieros" si es activo / "otras deudas" si es pasivo) a su línea propia "IV. Derivados"
  dentro de "Deudas financieras a largo plazo" (solo el lado PASIVO — el lado activo queda fuera
  del alcance de este lote, sigue en `activo_no_corriente`, identificable vía `cobertura_valor_
  swap_eur`). El riesgo real: `deudas_fin_largo_eur`/`corto_eur` alimentan `gastos_financieros =
  deuda_financiera_media × tipo_interés` — plegar ahí el derivado sin más generaría "interés"
  sobre una valoración a mercado. **Solución**: el derivado se añade DENTRO de
  `_construir_balance` (para el balance reportado), nunca antes de `deuda_financiera_media_eur`
  (que sigue usando solo la base "con coste") — misma exclusión aplicada en cascada donde
  `anterior.balance_eur["deudas_fin_largo"]` se usaba como base proporcional/de inicio. **0
  cambios en ningún total de EFE/ECPN/interés ya validado** (los 602 tests preexistentes
  siguieron en verde sin modificar ni un valor de referencia tras la migración) — solo cambió QUÉ
  fórmula excluye el derivado (`a3f`→`c10`, ver sección EFE arriba). **EIGR no necesitó ningún
  cambio** (no referencia `balance_eur` ni la colocación del derivado en absoluto).

## Validación de plausibilidad del caso completo — sección 2.13 (`motor/evolucion_arquetipo.py`)

Pasada FINAL, independiente de qué arquetipos estén activos, sobre el caso YA generado (3 años,
con toda la desagregación de los 4 lotes) — cierra el hueco de que cada mecanismo de arquetipo
tenía su propia contención (endeudamiento, baii/margen_bruto...) pero ningún caso sin ese
arquetipo concreto activo quedaba comprobado. Ver decisiones #70-73.

- **Alcance**: los 25 `ratios.*` del catálogo + `pyg.baii_pct`/`pyg.margen_bruto_pct` (para cerrar
  el hallazgo original que motivó el encargo, #18/#39 — un caso sin arquetipo activo podía salir
  implausible ahí sin que nada lo detectara). 3 ratios (`coste_deuda`, `pago_dias`,
  `cobertura_gastos_fin`) quedan como **informativos, sin señal dura** — ancla de catálogo YA
  diagnosticada como contaminada en encargos anteriores (#41-44, #55, #45), incluirlos generaría
  ruido sin decir nada nuevo. 2 ratios son **circulares** (revisión sistemática de los 27, pedida
  explícitamente — no solo el caso detectado por casualidad, ver #70): `ventas_empleado`
  (excluido siempre — se sortea directamente, recalcularlo solo reproduce el sorteo) y
  `rotacion_activo` (excluido SOLO en el año base 2023 — se sortea ahí para fijar `activo_total`;
  en 2024/2025 no se vuelve a sortear, así que sí es comprobable de verdad).
- **`SeñalRatio`/`PlausibilidadCaso`** (`motor/evolucion_arquetipo.py`) — diagnóstico PURO, nunca
  corrige ningún valor. `EvolucionArquetipo.plausibilidad` se calcula al final de
  `generar_evolucion_combinada` (cubre también `generar_caso_combinado`, que la envuelve, sin
  ningún hook adicional en `motor/memoria.py`), después de aplicar todos los arquetipos, sobre
  los 3 años. Una señal NO es un error — el propio diseño de ruido (85% típico/15% atípico)
  espera atípicos reales.
- **Ninguna palanca de corrección nueva** (decisión explícita, ver #70): revisados los 25 uno a
  uno, ninguno tiene una vía de amortiguación natural fuera de las ya existentes (masa_circulante,
  `_limitar_por_subtotal`, `_limitar_gastos_personal_por_baii`, contención de endeudamiento) — el
  catálogo no tiene ratios granulares por tipo (existencias/deudores por sub-partida), así que los
  4 lotes de desglose no aportan ninguna palanca nueva sobre estos 25 ratios agregados.
- **Fórmulas verificadas contra el PDF ACCID** (`docs/ratios2024.pdf`, no de memoria — mismo
  estándar que `coste_deuda`, #41), no derivadas de la lógica interna del motor. Encontró y
  corrigió **3 errores propios** antes del stress test (unidades de los ratios "por empleado" en
  miles de €, `financiacion_clientes` como ratio directo no "días", `capacidad_devolucion` con
  "deudas totales" no solo deuda financiera) — y reveló **2 discrepancias sobre mecanismos YA
  existentes y cerrados**, documentadas como hallazgo, NO corregidas en este encargo (ver #71):
  `rotacion_existencias` (el catálogo la define como Consumos/Existencias; el ancla de
  `masa_circulante` para los arquetipos 1/5 usa Ventas/Existencias) y `calidad_deuda` (el catálogo
  la define como Pasivo corriente/Deudas totales; `reclasificacion_deuda` — arquetipos 8/16 — usa
  deudas_fin_largo/deuda_financiera, ámbito y polaridad distintos).
- **Superconjunto de las señales ya existentes, con 2 ajustes necesarios encontrados en el stress
  test** (ver #72): (1) `ratios.endeudamiento` usa el MISMO techo exacto que la contención
  existente (huber+3·MAD recortado a `TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO=0,85`), no el genérico
  sin recortar. (2) La comparación es **inclusiva** (`>=`/`<=`, no `>`/`<`): las contenciones ya
  existentes corrigen ANALÍTICAMENTE hasta dejar el valor EXACTO en su propio techo/suelo — con
  comparación estricta, un caso "corregido con éxito hasta el límite" no quedaba señalizado aquí.
  Tolerancia `EPSILON_DESVIACIONES_PLAUSIBILIDAD_CASO=1e-6` (en unidades de MAD) absorbe el ruido
  de coma flotante de esa corrección (1e-11 a 1e-13 observado — convergencia iterativa del
  endeudamiento, aritmética "100−techo" de la PyG). **Excepción documentada, no un fallo**: cuando
  una provisión (tercer lote) dota/libera el MISMO año que `mejora_ebitda`/`mejora_margen` actúan,
  la dotación se inyecta DESPUÉS de que la contención de PyG ya fijó baii/margen_bruto en su
  límite — puede devolver el valor final a un rango plausible, mismo patrón ya aceptado en #39/#60.
- **Segunda excepción de superconjunto, encontrada en el stress test cuantificado de las 6
  combinaciones (#73, NO cubierta por los 2 ajustes de #72)**: en combos con varios arquetipos
  'fuerte' apilados (p. ej. combo F), `riesgo_endeudamiento=True` con `contencion_al_limite=True`
  **y** `deterioro_aplicado_eur>0` puede no tener señal nueva — la amortiguación de circulante se
  agota en una sola pasada del bucle sin reevaluar si el efecto secundario de esa pasada (menos
  deuda nueva → menos gasto financiero → más PN) deja el endeudamiento FINAL por debajo del techo.
  Mismo patrón que la excepción de provisión/PyG: señal sobre el proceso, no sobre el valor final.
  NO aplica cuando el arquetipo no tiene palanca de circulante (`deterioro_aplicado_eur==0` —
  apalancamiento/capex/adquisición en solitario): ahí el balance final coincide con el candidato
  sin corregir y la señal SÍ debe (y sigue) coincidiendo.
- **Stress test cuantificado (27 sectores × 2 segmentos × 4 semillas × 60 configuraciones,
  12.960 casos, ver #73 para el detalle completo)**: 99,3% de los casos tienen al menos 1 ratio
  señalizado; por ratio, entre el 3,3% y el 59,5%. Confirma el cierre del hallazgo original de
  #18 de forma limpia (proxy `aumento_clientes:leve` aislado): la señal antigua nunca se activaba
  (0,00%), la nueva detecta un 20,8% de esos mismos ejercicios. **Hallazgo mayor, traído sin
  arreglar (mismo criterio que `coste_deuda`)**: esa tasa alta no es específica de baii/margen
  bruto — se repite con arquetipos que no tocan en absoluto la magnitud comprobada (p. ej.
  `apalancamiento:leve` sobre `ratios.liquidez`: 18,75%).
- **De los 2 hallazgos de fórmula de #71, antes de aceptar el hallazgo mayor como estructural
  (ver #74)**: `rotacion_existencias` corregido (`_masa_circulante_objetivo`, arquetipos 1/3/5,
  usa ahora Consumos de explotación/Existencias como ACCID, no Ventas/Existencias — sin efectos
  secundarios). `calidad_deuda` — intentado y **revertido**: la versión fiel a ACCID (Pasivo
  corriente/Deudas totales) satura el mecanismo de `reclasificacion_deuda` (8/16) al límite
  estructural (deuda financiera es una palanca demasiado pequeña frente al pasivo total en los
  sectores probados) en 14-15 de 15 casos de prueba, con CUALQUIER intensidad — pendiente de
  recalibrar antes de reintentarlo, sigue documentado sin corregir.
- **Diagnóstico del hallazgo mayor (#75, NO un arreglo)**: la cola extrema y la tasa alta son
  **predominantemente acumulación de ruido entre los 3 años de evolución, no combinación de
  primitivas independientes dentro de un mismo año** — confirmado descomponiendo por año con
  arquetipos que no tocan la magnitud comprobada: año base 2023 (un único sorteo, sin posible
  acumulación) da tasas de señalización mucho más bajas (p. ej. 7,9% en `ratios.liquidez`) que
  2024 (29,6%) y 2025 (55,6%) — y el mismo patrón aparece IDÉNTICO bajo un arquetipo que no toca
  ni circulante ni deuda/PN (`resultado_extraordinario`), descartando que sea un efecto de "espiral
  de deuda" filtrándose por otra vía. Mecanismo identificado: el patrimonio neto lleva ruido
  independiente NUEVO cada año (vía las primitivas de PyG) mientras el resto del balance crece
  proporcional a ventas; el plug de cuadre (`ajuste_cuadre_eur` en `_construir_balance`) absorbe
  esa diferencia encogiendo `otras_deudas_corto` (o `disponible`) cada año — un patrón tipo "paseo
  aleatorio" que crece con cada año adicional frente a un Huber/MAD sectorial que es un punto de
  referencia ESTÁTICO. Mismo tipo de causa que la ya corregida en su día para los sub-lotes de
  amortización. No se ha tocado ningún código de generación — pendiente de decisión conjunta sobre
  el abordaje.
- **Intento de recalibrar `reclasificacion_deuda` (8/16) con la fórmula ACCID — bloqueado (#76)**:
  `ratios.calidad_deuda` resultó tener el MISMO suelo estructural (~24-25%) del hallazgo de #75,
  confirmado idéntico con intensidad de arquetipo ≈0 y bajo un arquetipo que no la toca en
  absoluto — no se puede calibrar "leve" a un rango razonable hasta resolver #75. Revertido de
  nuevo a la fórmula anterior (ninguna de las dos versiones de calidad_deuda está aplicada).
- **Diagnóstico de precisión sobre #75, PN vs. resto del balance (#77)**: predominantemente "el
  PN varía de más" — `_generar_pyg_hasta_baii` sorteaba CADA AÑO, con ruido típico/atípico
  completo contra el Huber/MAD (medida transversal entre empresas), cada primitiva de PyG no
  forzada por un arquetipo — un sorteo independiente de 2023, no anclado al año anterior.
- **Implementado y calibrado (#78) — continuidad del sorteo anual de PyG**: `_generar_partida_
  con_memoria` (`motor/ruido.py`, reversión a la media AR(1) + escala reducida), usada por
  `_generar_pyg_hasta_baii` en 2024/2025 (año base sin cambios) para las 8 primitivas + tipo_
  interes. `PESO_MEMORIA_PYG_ANUAL=0,6`, `FACTOR_REDUCCION_RUIDO_PYG_ANUAL=0,3`
  (`motor/empresa_base.py`). **Mejora real pero limitada**: `pyg.baii_pct`/`margen_bruto_pct`
  bajan de forma medible (2025: 16,7%→10,6% bajo `aumento_clientes:leve`) — pero `ratios.
  liquidez`/`tesoreria`/`fm_activo` (los que dominan el hallazgo mayor de #73) apenas se mueven
  (2025: 65,7%→64,8%), incluso con memoria casi extrema. **#77 estaba incompleto**: la causa
  dominante del lado de circulante/liquidez NO es el ruido de PyG (una causa real pero menor,
  ya corregida aquí) — es que el patrimonio neto retiene el 100% del resultado cada año (sin
  dividendos/distribución modelada) y crece a un ritmo (~ROE, 8-16%/año) muy superior al del
  resto del balance (proporcional a ventas, ~1-4%/año); el plug de cuadre absorbe esa brecha
  DETERMINISTA (no aleatoria) cada año, encogiendo `otras_deudas_corto`. Comiteado (13da6c8).
- **Payout de dividendos — mecanismo transversal implementado (#79-#80)**: el catálogo/PDFs ACCID
  no tienen ningún dato de payout/dividendos (verificado, no asumido) — la fórmula se deriva
  matemáticamente de `ratios.roe` real: `payout_caso = clamp(1 − g_caso/ROE_caso, 0, 1)`, con
  `ROE_caso` sorteado UNA vez por caso (mismo criterio que `capital_social` — no redibujado cada
  año, para no reintroducir ruido) con el mismo ruido mixto de siempre sobre `ratios.roe.huber_9y`
  /`huber_scale_mad`. El techo (100%) es una cota matemática que nunca se alcanza; el suelo (0%,
  sin efecto) se activa para sectores/sorteos de ROE bajo — limitación documentada, no forzada,
  mismo criterio que el aviso de fiabilidad del sector 30.3. `EjercicioEmpresa.payout_dividendos_
  eur` resta de PN y de `disponible` (caja real — a diferencia de la distribución de apalancamiento,
  financiada con deuda nueva sin impacto de caja). **Comparte línea con el dividendo de
  apalancamiento** (`c11a_dividendos` en EFE, `operaciones_con_socios` en ECPN — verificado en
  código antes de decidir que `apalancamiento_extra_eur` es una variable aislada, sumable sin
  romper nada; el modelo oficial PGC solo tiene una línea de "Dividendos", sin distinguir fuente
  de financiación). **Verificación de no-conflicto** (27 sectores × 4 semillas, `apalancamiento:
  fuerte` + payout, 216 ejercicios): 183 con ambos mecanismos activos a la vez, 0 descuadres de
  balance/EFE/ECPN, importes independientemente distinguibles. **Mejora sustancial confirmada**
  (mismo método de control que #78): `ratios.liquidez`/`tesoreria`/`fm_activo` en 2025 — 65,7%
  (original) → 64,8% (#78, solo ruido) → **39,8% (con payout)** — 25 puntos de caída real, no
  marginal. **Mejora real y validada — el residuo frente al ~16% del año base NO es el suelo de
  payout=0% en sectores de ROE bajo, descartado cuantitativamente (#81, hallazgo abierto): la
  correlación ROE↔tasa de señal es prácticamente nula (0,01), y los sectores donde el payout está
  SIEMPRE activo tienen tasa media de señal MAYOR (44,1%) que los que a veces se clampan a 0
  (32,5%) — causa real sin investigar todavía, pendiente de la siguiente sesión.** **Stress test
  completo repetido** (27×2×4×60, 12.960 casos): casos con
  señal 99,3%→97,9%; `liquidez` 59,5%→40,9%, `tesoreria` 57,7%→39,4%, `fm_activo` 48,6%→30,8%,
  `disponibilidad_ratio` 51,0%→45,1%; total señales >8 desviaciones 56.826→48.601 (-14,5%). Nuevas
  discrepancias de `riesgo_endeudamiento` (sectores distintos, por el desplazamiento de `rng_
  tendencia`) verificadas una a una — encajan en la excepción ya documentada de #73, no son
  nuevas. Ver `docs/decisiones_plausibilidad.md` #80-#81.
- **Diagnóstico desde cero del residuo de #81 y arreglo del criterio de plausibilidad (#82-#83)**:
  4 causas encontradas, la dominante y cuantificada es que el criterio Huber±3·MAD (variación
  TRANSVERSAL entre empresas) sigue penalizando con fuerza un residuo YA pequeño (PN creciendo
  ~1-2pp/año por encima de `g`, no las decenas de antes) en sectores con MAD real estrecho —
  correlación `mad/huber`↔tasa de señal = -0,454. Otras 2 causas menores confirmadas: el control
  `resultado_extraordinario` usado en #75/#77/#78/#81 estaba parcialmente contaminado (el propio
  arquetipo SÍ inyecta un pico de PN en un año, por diseño); el tope defensivo `min(payout,
  disponible)` de #80 se activa en 3,2% de los casos. Los 4 lotes de desglose granular quedaron
  descartados (sin correlación con el residuo). **Implementado (#83)**: `mad_efectivo = mad·
  √(1+k·FACTOR_ACUMULACION_VARIANZA_PLAUSIBILIDAD)` en `_evaluar_plausibilidad_caso`, `k=años
  desde el año base` (0 en 2023, sin cambio — comparación transversal válida), aplicado a TODOS
  los ratios EXCEPTO `ratios.endeudamiento` (su techo es un límite absoluto, no una banda
  estadística). `FACTOR=3,0`, calibrado para que 2025 coincida con la tasa del año base en el
  control limpio (16,2%→16,2%, exacto). Stress test completo: casos con señal 97,9%→94,5%;
  `liquidez` 40,9%→20,3%, `tesoreria` 39,4%→21,6%, `fm_activo` 30,8%→14,4%; hallazgo original
  18,56%→9,65% (ya cerca del 6,9% de #18); señales >8 desviaciones 48.601→28.237 (-41,9%). Suite
  completa verde SIN re-pinear ningún valor (cambio puro de criterio, no toca generación). Ver
  `docs/decisiones_plausibilidad.md` #82-#83.
- **Corregida la causa (2) de #82 — el payout ya no se recorta por falta de caja (#84)**: el
  déficit se financia con deuda a corto NUEVA (mismo criterio que `_deficit_y_deuda_corto` para
  el déficit de NOF), no un mecanismo nuevo. Nuevo campo `EjercicioEmpresa.payout_deuda_extra_eur`
  (mismo patrón que `deuda_extra_por_nof_eur`). 4 tests corregidos para aislar esta deuda de la
  que generan los propios arquetipos (`refinanciacion`/`riesgo_refinanciacion`, ECPN). Tasa de
  señal 2025 en el control limpio: 16,2%→**13,0%**, ya por debajo del propio año base. Ver
  `docs/decisiones_plausibilidad.md` #84.
- **Verificada la calibración de intensidad de 9/14/10/11 (#20) tras #78/#80/#82-83 — SIN
  cambios (#85)**: comprobado con el mismo método (barrido 27×4×2 segmentos), el gradiente
  leve/moderado/fuerte sigue dentro del objetivo en los 3 arquetipos — `mejora_margen`
  prácticamente idéntico a #20; `apalancamiento` ligeramente más bajo en "leve" pero dentro de
  rango; `mejora_ebitda` mejora (su "leve" pasa de 8,8% —por encima del objetivo por el suelo
  estructural de #18— a 3,2%, ya dentro de rango, sin tocar la escala). Ninguno se acerca a
  saturar en "fuerte". No se tocó ninguna constante de intensidad. Ver
  `docs/decisiones_plausibilidad.md` #85.

## Trazabilidad, resumen de particularidades, rúbrica de diagnóstico y similitud entre casos — Fase 4, Ronda 1 (`motor/resumen_caso.py`, `motor/rubrica_diagnostico.py`, `motor/similitud_casos.py`)

Primera ronda de piezas de la Fase 4 que NO tocan la generación de casos ni el manejo de
semillas — auditoría, contenido estructurado y una función de comparación. La Ronda 2 (nombres
ficticios + variantes de examen, secciones 2.16/2.17) queda para más adelante.

### Auditoría de trazabilidad (sección 2.15) — Parte A: los 5 campos exigidos

Confirmados presentes y poblados en cualquier caso (`EvolucionArquetipo.arquetipo`/`.intensidad`/
`.semilla`/`.catalogo_version`/`.pgc_version`) — con UN hallazgo real, corregido:
`arquetipo`/`.intensidad` solo reflejaban los arquetipos `clase="cuantitativo"` (así los calcula
`generar_evolucion_combinada`, que no conoce la clase `memoria_pura` en absoluto) — un caso
combinado con algún arquetipo de memoria pura activo (7/19/22) dejaba esos 2 campos
INCOMPLETOS como registro de "qué arquetipos están activos en el caso" (p. ej. un caso con 6+7
solo mostraba "aumento_clientes", perdiendo el 7). **Corregido en `motor.memoria.generar_caso_
combinado`** (el único punto que conoce ambas clases a la vez): recalcula ambos campos sobre el
diccionario COMPLETO de arquetipos activos cuando hay alguno de memoria pura, con el MISMO
formato ya establecido para combinaciones ("id1+id2", "id1:intensidad1+id2:intensidad2", orden
alfabético de id). Si no hay ningún arquetipo de memoria pura activo, los campos quedan
EXACTAMENTE igual que antes (0 casos ya existentes cambian, verificado en la regresión completa).

### Auditoría del modo típico/atípico — Parte B, hallazgo real (no solo ausencia de agregación)

Pedido explícitamente: comprobar si el modo típico/atípico por partida se mantuvo expuesto de
forma consistente en TODOS los mecanismos añadidos después del diseño original (existencias,
deudores/acreedores, provisiones, deudas financieras, insolvencias, payout). **Resultado: SÍ
faltaba en varios sitios — corregido en origen (no es un rediseño, es exponer un dato ya
calculado internamente en cada sorteo).**

- **Con el problema, corregido — 8 sitios en total**: los perfiles de los lotes de desglose de
  balance (`generar_perfil_existencias`/`generar_perfil_deudores`/`generar_perfil_acreedores`/
  `generar_perfil_deudas_fin`, todos en `motor/empresa_base.py`) descartaban el modo de cada
  componente con `_generar_partida(...) -> valor, _` — a diferencia de las masas de nivel
  superior (diseño original, `_generar_balance_pct`) y de las primitivas de PyG, que sí lo
  exponían en `modos` desde siempre. Ahora las 4 funciones devuelven también el modo por
  componente, plegado en `EmpresaBase.modos` con prefijo por lote (`existencias.<componente>`,
  `deudores.<componente>`, `acreedores.<componente>`, `deudas_fin_fraccion_total.<tipo>`,
  `deudas_fin_fraccion_largo.<tipo>`). `ROE_caso` (payout de dividendos, #79-80) descartaba su
  modo pese a sortear con el mismo mecanismo Huber/MAD que `rotacion_activo` (que sí lo
  exponía) — corregido, expuesto en `ejercicios[AÑO_BASE].modos["caso.roe"]`, mismo "cajón" que
  `rotacion_activo` (rasgos de caso sorteados una vez, no por año). **Encontrados de paso y
  corregidos también** (mismo patrón exacto, pero ANTERIORES a los "lotes" — decisiones #24-25,
  antes del primer lote de desglose de balance, pedido explícitamente completar tras el hallazgo
  inicial): `generar_perfil_activo_no_corriente` (prefijo `activo_no_corriente.<componente>`),
  `generar_periodificaciones_pct` (claves planas `periodificacion_activo`/`..._pasivo_corto`/
  `..._pasivo_largo` — 3 escalares, no un dict de componentes) y `_generar_capital_social` (clave
  plana `capital_social`) — las 3 en `motor/empresa_base.py`, mismo namespace de `EmpresaBase.
  modos` que el resto.
- **Sin el problema, verificado y documentado por qué NO aplica** — provisiones, insolvencias y
  la subvención de fondo (`motor/provisiones.py`, `motor/insolvencias.py`,
  `motor/coberturas_subvenciones.py`) sortean con `rng.uniform`/`rng.choice` DIRECTOS, sin pasar
  nunca por `_generar_partida` — no hay ancla de catálogo Huber/MAD detrás de esos importes (ver
  sus propios docstrings, "sin dato de catálogo que lo ancle"), así que el concepto "modo
  típico/atípico" no existe para ellos, no es una ausencia que corregir.
- **Verificado empíricamente, no solo por la forma del dato**: barridos de 30 semillas por cada
  corrección confirman que SÍ aparecen atípicos reales (no quedó expuesto pero siempre en
  `"tipico"` por algún fallo de fontanería de la semilla) — ver los tests dedicados en
  `tests/test_desglose_existencias_periodificaciones.py`, `tests/test_desglose_deudores_
  acreedores_grupo.py`, `tests/test_desglose_deudas_financieras.py`, `tests/test_evolucion_
  arquetipo.py::test_roe_caso_expone_su_modo_tipico_atipico`, `tests/test_desagregacion_pn_y_
  activo.py` (los 3 sitios encontrados de paso) — y que `motor/resumen_caso.py` los recoge
  correctamente con `año=None` (`tests/test_resumen_caso.py::test_atipicos_de_activo_no_
  corriente_periodificaciones_y_capital_social_llegan_al_resumen`).

### Resumen consolidado de particularidades del caso (`motor/resumen_caso.py`)

Objeto único por caso (`resumen_particularidades_caso(evolucion) -> ResumenParticularidadesCaso`)
que consolida TODO lo de arriba en un solo sitio, para que el formador no tenga que saber dónde
busca cada dato por separado — capa de AGREGACIÓN pura, no rediseña nada de lo ya construido.

- **Atípicos** (`ItemModoAtipico`, tupla `(partida, año)`) — solo las entradas `modo=="atipico"`
  de `EjercicioEmpresa.modos` de los 3 años, NUNCA las forzadas por arquetipo (`"arquetipo"`) ni
  las derivadas (`"derivado"`, amortización): esas ya son visibles a través del propio arquetipo
  activo o del cálculo derivado, listarlas aquí sería ruido. `año=None` para los rasgos "fijos
  desde 2023" (masas de balance de nivel superior, los perfiles de los 4 lotes, `rotacion_
  activo`, `caso.roe`) — etiquetarlos con un año concreto sugeriría un fenómeno de ESE año,
  cuando describen a la empresa entera; `año=<el año>` solo para las primitivas de PyG (`pyg.*`,
  prefijo usado para distinguir ambos casos), que SÍ se vuelven a sortear cada ejercicio.
- **Señales de riesgo** (`SeñalRiesgoCaso`) — únicamente los 2 tipos "padre" auditados
  explícitamente (`riesgo_endeudamiento`, `riesgo_plausibilidad_pyg`): `contencion_al_limite`/
  `pyg_contencion_al_limite` NUNCA aparecen sin su señal padre (verificado en el propio código de
  `_evolucionar_un_año`/`_evaluar_plausibilidad_caso`, no asumido) — se representan como contexto
  (`detalle`) de la señal padre, no como señales independientes.
- **Plausibilidad, notas de memoria, movimiento anual** — expuestos tal cual (`PlausibilidadCaso`
  sin reprocesar; `notas_memoria` combina `EjercicioEmpresa.notas_memoria` por año +
  `EvolucionArquetipo.notas_memoria_pura` case-level, ordenadas por año y número; movimiento de
  provisión/insolvencia SOLO si el caso realmente tiene el mecanismo activo, filas 2024+2025 —
  nunca 2023, nunca dotada ahí; bienes totalmente amortizados filtrados a "nuevos ese año", no
  repetidos año tras año pese a que `bienes_totalmente_amortizados_en` es acumulativo).
- **Base de datos para la futura ficha de solución del formador** (sección 2.9, NO construida en
  este encargo): esa ficha necesitará exactamente esta consolidación — este módulo es la capa
  que la alimentará cuando se construya, documentado explícitamente en su propio docstring.

### Rúbrica de corrección del diagnóstico (sección 2.19, `data/rubrica_diagnostico.json` + `motor/rubrica_diagnostico.py`)

Contenido estructurado — NO código de generación, no toca el motor de cálculo. Puntúa la ficha de
diagnóstico ya existente (HECHO → CÁLCULO → HIPÓTESIS → EVIDENCIA NECESARIA → IMPACTO →
PRIORIDAD → RECOMENDACIÓN, sección 2.10), diseño GENÉRICO (una única rúbrica, no 22 — la
conexión con el arquetipo concreto de cada caso vive en la sección HIPÓTESIS, que remite a
`docs/guia_docente_arquetipos.md` en vez de duplicar su contenido).

- **100 puntos, 7 secciones, 3 niveles cada una** (completo/parcial/insuficiente — sin más
  granularidad deliberadamente, para mantener la corrección rápida y consistente entre
  correctores). Peso por sección: HECHO 10, CÁLCULO 15, HIPÓTESIS 25 (la de MAYOR peso — la que
  de verdad mide capacidad de diagnóstico, no solo cálculo), EVIDENCIA NECESARIA 10, IMPACTO 15,
  PRIORIDAD 10, RECOMENDACIÓN 15.
- **Conexión con la "Conclusión esperada"** (campo ya presente en `guia_docente_arquetipos.md`
  para cada uno de los 22 arquetipos): la sección HIPÓTESIS se evalúa por CONVERGENCIA de fondo
  con la Conclusión esperada del arquetipo (o arquetipos, en un caso combinado) activo del caso —
  nunca por coincidencia literal de redacción. El campo `conexion_conclusion_esperada` del JSON
  documenta el criterio exacto; `error_habitual_como_penalizacion` conecta además con el campo
  "Error habitual a evitar" de la misma guía (reproducirlo penaliza HIPÓTESIS a "insuficiente").
- **`motor/rubrica_diagnostico.py`** solo carga y valida (mismo patrón que `motor.arquetipos`):
  comprueba que están las 7 secciones exactas, en orden 1-7, sin duplicados, y que la suma de
  `puntos_maximos` cuadra EXACTO con `puntuacion_total` — un error de diseño de la rúbrica que
  debe detectarse al cargarla, no descubrirse corrigiendo exámenes.

### Función de similitud entre casos (sección 2.20, pieza PARCIAL, `motor/similitud_casos.py`)

Solo la función de comparación — **NO se aplica sobre ningún repositorio** (el repositorio de
casos es Fase 5, no existe todavía); queda lista para cuando exista.

- **4 dimensiones comparadas** (pedidas explícitamente: sector+combo de arquetipos+intensidad+
  perfil numérico resultante): (1) sector/segmento, categórico (1.0 ambos coinciden, 0.5 solo
  sector, 0.0 ninguno); (2) combinación de arquetipos activos, índice de Jaccard sobre el
  conjunto de ids (AMBAS clases, gracias a la corrección de trazabilidad de arriba); (3)
  intensidad, SOLO sobre los arquetipos en común (si no comparten ninguno, no es comparable,
  0.0) — distancia normalizada leve/moderado/fuerte; (4) perfil numérico, los 23 `ratios.
  RATIOS_PLAUSIBILIDAD_SEÑALIZABLES` del año 2025, normalizados como desviaciones respecto al
  Huber del sector de CADA caso (`(valor−huber)/mad`) — válido incluso entre sectores DISTINTOS
  (dos casos "igual de atípicos para su sector" salen numéricamente parecidos), mapeado a
  similitud con `1/(1+distancia_cuadrática_media)`.
- **Ponderación documentada**: sector/segmento 15%, arquetipos 30%, intensidad 15%, numérico 40%
  — el perfil numérico pesa más porque es, en última instancia, lo que de verdad importaría para
  el problema real de la sección 2.20 (copia entre alumnos con cifras casi idénticas); la
  combinación de arquetipos pesa el doble que sector/intensidad por separado por ser la señal más
  "de diseño" de que dos casos representan la MISMA situación didáctica.
- **Verificado con ejemplos concretos** (no solo unitarios aislados): mismo caso consigo mismo →
  1.0 exacto; mismo sector/arquetipo/intensidad, distinta semilla → puntuación alta pero
  `similitud_numerica<1.0` (las cifras SÍ difieren entre semillas, correcto); sector/arquetipo
  distintos → puntuación baja; función simétrica (`similitud(a,b) == similitud(b,a)`).

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
