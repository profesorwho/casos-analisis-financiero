# Casos de análisis financiero

Generador de casos empresariales ficticios pero financieramente realistas y coherentes, para un curso profesional de análisis económico-financiero de cuentas anuales españolas (PGC). Cada caso combina un modelo económico interno coherente (ventas → márgenes → resultado → NOF → deuda → caja → patrimonio neto), estados financieros cuadrados contablemente, y pistas analíticas en la memoria para que el alumnado descubra riesgos no evidentes a simple vista.

Especificación completa del proyecto: [`docs/especificaciones_proyecto_casos_balances.md`](docs/especificaciones_proyecto_casos_balances.md).

Documentación relacionada:
- [`docs/guia_docente_arquetipos.md`](docs/guia_docente_arquetipos.md) — ficha didáctica de los 22 arquetipos de situación económica.
- [`docs/matriz_compatibilidad_arquetipos.csv`](docs/matriz_compatibilidad_arquetipos.csv) — compatibilidad y complejidad al combinar arquetipos.
- [`docs/catalogo_ratios_masas_27sectores_huber9y (1).csv`](<docs/catalogo_ratios_masas_27sectores_huber9y (1).csv>) — catálogo de ratios sectoriales reales (27 sectores × 2 segmentos, fuente ACCID).

## Estructura del repositorio

```
motor/     Lógica de generación (Python) — motor de datos económico-financiero
data/      Catálogos fuente (copia de trabajo de los CSV de docs/)
tests/     Tests del motor
docs/      Especificación y catálogos originales
renderer/  Renderizador de PDF (Balance/PyG/EFE/ECPN/Memoria) a partir de un caso ya generado
```

## Entorno de desarrollo

```bash
pip install -e ".[dev]"
```

## Renderizador de PDF (`renderer/`)

Genera las cuentas anuales completas (Balance, PyG, EFE, ECPN, Memoria) de un caso ya producido
por el motor como un PDF con formato PGC. Es una capa de presentación pura: no genera datos, solo
lee un `EvolucionArquetipo`/`EjercicioEmpresa` ya calculado y lo maqueta con reportlab.

```bash
pip install -e ".[renderer]"
python renderer/generar_caso_completo.py
```

El PDF se escribe en `renderer/output/` (no versionado). Los scripts `generar_caso_completo.py`
(caso completo con memoria), `generar_pdf_caso.py` y `generar_casos_pedidos.py` son ejecutables
directamente y sirven de ejemplo de uso; `generar_caso1_ajustado.py`/`generar_caso2_mecanizado*.py`
son casos manuales de exploración (cifras codificadas a mano, sin pasar por el motor).

## Estado actual

Solo está construida la estructura inicial del proyecto y la carga/validación del catálogo de sectores (`motor/catalogo.py`). Aún no hay generación de empresas ni validador de cuadre contable — ver el plan de fases en la especificación (sección 5).
