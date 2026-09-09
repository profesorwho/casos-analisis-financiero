# Casos de análisis financiero

Generador de casos empresariales ficticios pero financieramente realistas y coherentes, para un curso profesional de análisis económico-financiero de cuentas anuales españolas (PGC). Cada caso combina un modelo económico interno coherente (ventas → márgenes → resultado → NOF → deuda → caja → patrimonio neto), estados financieros cuadrados contablemente, y pistas analíticas en la memoria para que el alumnado descubra riesgos no evidentes a simple vista.

Especificación completa del proyecto: [`docs/especificaciones_proyecto_casos_balances.md`](docs/especificaciones_proyecto_casos_balances.md).

Documentación relacionada:
- [`docs/guia_docente_arquetipos.md`](docs/guia_docente_arquetipos.md) — ficha didáctica de los 22 arquetipos de situación económica.
- [`docs/matriz_compatibilidad_arquetipos.csv`](docs/matriz_compatibilidad_arquetipos.csv) — compatibilidad y complejidad al combinar arquetipos.
- [`docs/catalogo_ratios_masas_27sectores_huber9y (1).csv`](<docs/catalogo_ratios_masas_27sectores_huber9y (1).csv>) — catálogo de ratios sectoriales reales (27 sectores × 2 segmentos, fuente ACCID).

## Estructura del repositorio

```
motor/    Lógica de generación (Python) — motor de datos económico-financiero
data/     Catálogos fuente (copia de trabajo de los CSV de docs/)
tests/    Tests del motor
docs/     Especificación y catálogos originales
```

## Entorno de desarrollo

```bash
pip install -e ".[dev]"
```

## Estado actual

Solo está construida la estructura inicial del proyecto y la carga/validación del catálogo de sectores (`motor/catalogo.py`). Aún no hay generación de empresas ni validador de cuadre contable — ver el plan de fases en la especificación (sección 5).
