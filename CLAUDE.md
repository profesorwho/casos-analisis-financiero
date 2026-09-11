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
| `empresa_base.py` | Genera balance + PyG de **una** empresa, **un** ejercicio, a partir del catálogo + ruido típico/atípico. Sin arquetipos, sin serie temporal. | `generar_empresa_base(sector, segmento, ventas_objetivo, semilla, catalogo=None) -> EmpresaBase`; `resolver_fila_sector(catalogo, sector_codigo, segmento) -> pd.Series` | Año base 2023 de **cualquier** caso, con o sin arquetipo. |
| `arquetipos.py` | Carga y valida `data/arquetipos.json` como dataclasses tipadas. **Sin lógica de generación.** | `cargar_arquetipos(ruta=...) -> dict[str, DefinicionArquetipo]` | Tipos de efecto: `EfectoMasaCirculante`, `EfectoPygPrimitiva`, `EfectoApalancamiento`, `EfectoTesoreria`, `EfectoReclasificacionDeuda`, `EfectoEventoPuntual`, `EfectoCapex`, `EfectoAdquisicion`. |
| `evolucion_arquetipo.py` | Motor genérico: evoluciona una empresa 3 ejercicios (2023 base + 2024/2025 con el/los arquetipo(s) aplicado(s)), interpretando cada tipo de `Efecto`. Contiene toda la lógica de mecanismo — **no releer para saber qué arquetipos toca cada mecanismo, ver tabla de mecanismos abajo**. `generar_evolucion_arquetipo` (un solo arquetipo) es un wrapper de una línea sobre `generar_evolucion_combinada` con un dict de 1 elemento — **garantía estructural**: cualquier test de un arquetipo en solitario que siga pasando prueba que la combinación no le cambió el comportamiento. | `generar_evolucion_combinada(sector, segmento, ventas_objetivo_2023, semilla, arquetipos_intensidades: dict[str,str], catalogo=None, arquetipos=None) -> EvolucionArquetipo` (motor general); `generar_evolucion_arquetipo(sector, segmento, ventas_objetivo_2023, semilla, intensidad, arquetipo_id, catalogo=None, arquetipos=None) -> EvolucionArquetipo` (caso de 1 arquetipo) | Todos los arquetipos de `clase="cuantitativo"` (ver `docs/indice_arquetipos.md`); rechaza `clase="memoria_pura"` con `EvolucionArquetipoError`. |
| `memoria.py` | Genera notas de memoria puramente cualitativas — arquetipos de `clase="memoria_pura"` (sin efectos numéricos, `efectos: []` en el JSON) — y orquesta el caso combinado completo (mezcla `clase="cuantitativo"` + `clase="memoria_pura"`). | `generar_nota_memoria_pura(arquetipo_id, sector, segmento, intensidad, semilla, ejercicio, etiquetas_ya_usadas=frozenset()) -> NotaMemoria` (o la función específica `generar_nota_<arquetipo>(...)`); `generar_caso_combinado(sector, segmento, ventas_objetivo_2023, semilla, arquetipos_intensidades, catalogo=None, arquetipos=None) -> EvolucionArquetipo` (punto de entrada general, cualquier mezcla de clases) | Arquetipos 7, 19, 20, 21, 22. `NotaMemoria` (definida en `evolucion_arquetipo.py`, no aquí — ver "Combinación de arquetipos" abajo) lleva `texto` + `etiquetas` (temas, usadas por el mecanismo de coherencia de la sección 2.12). |

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
