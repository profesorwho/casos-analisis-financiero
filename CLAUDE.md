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
| `evolucion_arquetipo.py` | Motor genérico: evoluciona una empresa 3 ejercicios (2023 base + 2024/2025 con el arquetipo aplicado), interpretando cada tipo de `Efecto`. Contiene toda la lógica de mecanismo — **no releer para saber qué arquetipos toca cada mecanismo, ver tabla de mecanismos abajo**. | `generar_evolucion_arquetipo(sector, segmento, ventas_objetivo_2023, semilla, intensidad, arquetipo_id, catalogo=None, arquetipos=None) -> EvolucionArquetipo` | Todos los arquetipos de `clase="cuantitativo"` (ver `docs/indice_arquetipos.md`). |
| `memoria.py` | Genera notas de memoria puramente cualitativas — arquetipos de `clase="memoria_pura"` (sin efectos numéricos, `efectos: []` en el JSON). Una función por arquetipo + un despachador. | `generar_nota_memoria_pura(arquetipo_id, sector, segmento, intensidad, semilla, ejercicio) -> NotaMemoria` (o la función específica `generar_nota_<arquetipo>(...)`) | Arquetipos 7, 19, 20, 21, 22. `NotaMemoria` lleva `texto` + `etiquetas` (temas, para la futura lógica de coherencia entre notas, sección 2.12 — no implementada todavía). |

## Mecanismos reutilizables ya construidos (en `evolucion_arquetipo.py`, salvo que se indique)

| Mecanismo (tipo de efecto en JSON) | Qué hace, en una línea | Arquetipos que lo usan |
|---|---|---|
| `masa_circulante` (fórmula `rotacion`/`dias`) | Desvía existencias / realizable / acreedores_comerciales por continuidad respecto al año anterior, con signo NOF (`SIGNO_NOF_MASA_CIRCULANTE`: activo suma presión de caja, pasivo resta). | 1, 3, 4, 5, 6 |
| `pyg_primitiva` | Desvía una primitiva de PyG por continuidad; techo/suelo del subtotal que alimenta vía `SUBTOTAL_PYG_DE_PRIMITIVA` (base fija, margen_bruto) o `SUBTOTAL_PYG_BASE_DINAMICA_DE_PRIMITIVA` (base dinámica, baii). | 10, 11 |
| `apalancamiento` | Sube deuda a largo + baja PN en forma cerrada hasta un endeudamiento objetivo (topado al techo sectorial). | 9, 14 (14 = variante exacta de 9) |
| `tesoreria` | Desvía `disponible` con un factor simple `(1 ± intensidad)` — **no usa el Huber del `ratio_catalogo`**, es solo etiqueta de trazabilidad. | 2, 15 (2 = variante exacta de 15) |
| `reclasificacion_deuda` | Reasigna deuda largo↔corto SIN alterar el total (mejora o empeora `calidad_deuda`). | 8 (dirección +1), 16 (dirección −1, + `nota_memoria`) |
| `evento_puntual` | Fuerza una primitiva de PyG solo en UN año sorteado (no progresivo) — vuelve al ruido normal el año siguiente sin código adicional. | 12 |
| `capex` | `activo_no_corriente` por continuidad (ancla `rotacion_activo_no_corriente`), financiado con deuda a largo NUEVA (no toca PN, no toca circulante). | 17 |
| `adquisicion` | Salto DISCRETO (no continuo) de `activo_no_corriente` en un año FIJO (`AÑO_ADQUISICION=2024`, no sorteado), financiado con caja + deuda a largo; separa `ventas_organicas_eur`/`ventas_inorganicas_eur`; `nota_memoria` OBLIGATORIA (no opcional). | 18 |
| Contención de endeudamiento | Chequeo **incondicional** cada año: si el endeudamiento supera `huber+3·MAD` (techo absoluto 0,85), amortigua vía las masas de ACTIVO tocadas por el arquetipo, si las hay; si no, queda `contencion_al_limite=True` (señal sin corrección posible). | Todos (corre siempre, toque o no circulante) |
| Hash estable sector+segmento (`zlib.crc32`) | Siembra cada RNG (`generar_empresa_base`, `rng_tendencia`/`rngs_pyg`, `rngs_nota`) mezclando semilla+sector+segmento — **nunca intensidad** (mismo "ruido de fondo" entre intensidades del mismo caso, por diseño). | Todos — infraestructura, no arquetipo-específico |
| `nota_memoria` | Cobertura narrativa reproducible (RNG dedicado `rngs_nota`, redacciones alternativas por arquetipo). Opcional (10: caso límite; 16: huella habitual) u OBLIGATORIA (18). | 10, 16, 18 |
| `clase="memoria_pura"` (en `motor.memoria`, no `evolucion_arquetipo.py`) | Arquetipo SIN efectos numéricos (`efectos: []`) — la nota de memoria se genera con una función propia de `motor.memoria`, no pasa por `_evolucionar_un_año`. RNG dedicado por (sector, segmento, intensidad, **arquetipo_id**, semilla) — a diferencia del resto, mezcla también el arquetipo_id, para que varias notas de memoria puedan combinarse sobre el mismo caso sin compartir estado. | 7, 19, 20, 21, 22 |

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
