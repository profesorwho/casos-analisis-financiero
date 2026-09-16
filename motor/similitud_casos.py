"""Función de comparación entre dos casos ya generados — pieza PARCIAL de la sección 2.20
("Control de diversidad en el repositorio de casos"). Solo la función de similitud en sí: cuánto
se parecen dos casos dados su sector, combinación de arquetipos, intensidades y perfil numérico
resultante. NO se aplica todavía sobre ningún repositorio (el repositorio de casos es Fase 5, no
existe hoy) — queda lista para cuando exista, como capa de cálculo pura sobre `EvolucionArquetipo`
(mismo criterio que `motor.clasificacion_legal`/`motor.efe`/`motor.resumen_caso`: no genera ni
corrige ningún dato del motor, solo lee lo que dos casos ya generados exponen).

**Las 4 dimensiones comparadas** (pedidas explícitamente: "sector+combo de arquetipos+intensidad+
perfil numérico resultante"):

1. **Sector/segmento** — coincidencia categórica (mismo sector Y segmento, solo mismo sector, o
   ninguno de los dos).
2. **Combinación de arquetipos activos** — índice de Jaccard sobre el conjunto de ids activos
   (AMBAS clases, `cuantitativo` y `memoria_pura` — usa `EvolucionArquetipo.arquetipo`, que desde
   la corrección de trazabilidad de esta misma ronda ya incluye los de memoria pura cuando el
   caso se generó con `motor.memoria.generar_caso_combinado`, ver `motor/memoria.py`).
3. **Intensidad** — sobre los arquetipos que SÍ tienen ambos casos en común (si no comparten
   ningún arquetipo, la intensidad no es comparable, se define como 0): distancia normalizada
   entre `leve`/`moderado`/`fuerte` (0=misma intensidad, 1=extremos opuestos), promediada.
4. **Perfil numérico resultante** — vector de los 23 ratios `RATIOS_PLAUSIBILIDAD_SEÑALIZABLES`
   (sección 2.13, ya validados como no-circulares y no-contaminados) del año 2025, normalizado
   como desviaciones respecto al Huber del sector de CADA caso (`(valor − huber) / mad`) — esto
   hace la comparación válida incluso entre sectores DISTINTOS (dos casos "igual de atípicos para
   su sector" salen numéricamente parecidos, aunque el sector no coincida), que es precisamente
   lo que sección 2.20 pide poder detectar (cifras resultantes parecidas, no solo metadatos
   idénticos). Distancia euclídea cuadrática media sobre los ratios que ambos casos tienen
   calculables (`None` se excluye, p. ej. un caso con `pasivo_total=0` degenerado), mapeada a
   similitud con `1 / (1 + distancia)` (acotada en (0, 1], 1.0 = perfiles idénticos).

**Ponderación de la puntuación combinada** (documentada, no arbitraria): sector/segmento 15%,
combinación de arquetipos 30%, intensidad 15%, perfil numérico 40% — el perfil numérico pesa más
porque es, en última instancia, lo que de verdad importaría para el problema que motiva la
sección 2.20 (dos alumnos con cifras casi idénticas, aunque el metadato de arquetipos no
coincidiera exactamente); la combinación de arquetipos pesa el doble que sector/intensidad por
separado porque es la señal más "de diseño" de que dos casos representan la MISMA situación
didáctica."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import resolver_fila_sector
from motor.evolucion_arquetipo import RATIOS_PLAUSIBILIDAD_SEÑALIZABLES, EvolucionArquetipo

AÑO_PERFIL_NUMERICO = 2025

PESO_SECTOR_SEGMENTO = 0.15
PESO_ARQUETIPOS = 0.30
PESO_INTENSIDAD = 0.15
PESO_NUMERICO = 0.40

_ORDEN_INTENSIDAD = {"leve": 1, "moderado": 2, "fuerte": 3}
_MAX_DIFERENCIA_INTENSIDAD = max(_ORDEN_INTENSIDAD.values()) - min(_ORDEN_INTENSIDAD.values())  # 2


class SimilitudCasosError(ValueError):
    """Alguno de los dos casos no tiene los datos necesarios para compararlo (p. ej. sin
    `plausibilidad` calculada, o sin el año 2025 entre sus ejercicios)."""


@dataclass(frozen=True)
class SimilitudCasos:
    """Resultado de comparar dos casos — `puntuacion` es la combinación ponderada de las 4
    componentes (0.0 = completamente distintos en todo, 1.0 = idénticos en las 4 dimensiones).
    Cada componente se expone por separado para que quien use esto (la futura Fase 5) pueda
    aplicar su propio umbral o pesos distintos sin tener que recalcular nada."""

    puntuacion: float
    mismo_sector: bool
    mismo_segmento: bool
    similitud_sector_segmento: float
    similitud_arquetipos: float  # Jaccard sobre el conjunto de ids activos (ambas clases)
    similitud_intensidad: float
    similitud_numerica: float
    arquetipos_en_comun: tuple[str, ...]
    ratios_comparados: int  # cuántos de los 23 ratios tenían valor calculable en AMBOS casos


def _arquetipos_intensidades_de(evolucion: EvolucionArquetipo) -> dict[str, str]:
    """Reconstruye {arquetipo_id: intensidad} a partir de `evolucion.arquetipo`/`.intensidad` —
    formato plano ("aumento_clientes"/"fuerte") para un único arquetipo, o combinado
    ("id1+id2"/"id1:intensidad1+id2:intensidad2") para varios — mismo formato que ya construyen
    `generar_evolucion_combinada`/`motor.memoria.generar_caso_combinado`."""
    ids = evolucion.arquetipo.split("+")
    if len(ids) == 1:
        return {ids[0]: evolucion.intensidad}
    resultado: dict[str, str] = {}
    for par in evolucion.intensidad.split("+"):
        arquetipo_id, intensidad = par.split(":", 1)
        resultado[arquetipo_id] = intensidad
    return resultado


def _perfil_numerico(evolucion: EvolucionArquetipo, catalogo: pd.DataFrame) -> dict[str, float]:
    if evolucion.plausibilidad is None:
        raise SimilitudCasosError(
            f"El caso {evolucion.sector_codigo}/{evolucion.arquetipo}/semilla={evolucion.semilla} "
            "no tiene `plausibilidad` calculada (sección 2.13) — no se puede construir su perfil numérico."
        )
    if AÑO_PERFIL_NUMERICO not in evolucion.plausibilidad.valores_por_año:
        raise SimilitudCasosError(f"El caso no tiene el año {AÑO_PERFIL_NUMERICO} entre sus ejercicios.")

    valores = evolucion.plausibilidad.valores_por_año[AÑO_PERFIL_NUMERICO]
    fila = resolver_fila_sector(catalogo, evolucion.sector_codigo, evolucion.segmento)

    z_scores: dict[str, float] = {}
    for ratio in RATIOS_PLAUSIBILIDAD_SEÑALIZABLES:
        valor = valores.get(ratio)
        if valor is None:
            continue
        huber = fila[f"{ratio}.huber_9y"]
        mad = fila[f"{ratio}.huber_scale_mad"]
        if mad <= 0:
            continue  # sin escala con la que normalizar (dato de catálogo degenerado, defensivo)
        z_scores[ratio] = (valor - huber) / mad
    return z_scores


def similitud_entre_casos(
    caso_a: EvolucionArquetipo, caso_b: EvolucionArquetipo, catalogo: pd.DataFrame | None = None
) -> SimilitudCasos:
    """Compara dos casos ya generados en las 4 dimensiones del docstring del módulo. `catalogo`
    es opcional (se carga una vez si no se pasa) — quien compare muchos pares (futura Fase 5)
    debería cargarlo una sola vez y pasarlo, para no releer el CSV en cada llamada."""
    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    mismo_sector = caso_a.sector_codigo == caso_b.sector_codigo
    mismo_segmento = caso_a.segmento == caso_b.segmento
    similitud_sector_segmento = 1.0 if (mismo_sector and mismo_segmento) else (0.5 if mismo_sector else 0.0)

    dict_a = _arquetipos_intensidades_de(caso_a)
    dict_b = _arquetipos_intensidades_de(caso_b)
    arquetipos_a, arquetipos_b = set(dict_a), set(dict_b)
    union = arquetipos_a | arquetipos_b
    interseccion = arquetipos_a & arquetipos_b
    similitud_arquetipos = len(interseccion) / len(union) if union else 1.0

    if interseccion:
        diferencias = [
            abs(_ORDEN_INTENSIDAD[dict_a[aid]] - _ORDEN_INTENSIDAD[dict_b[aid]]) for aid in interseccion
        ]
        similitud_intensidad = 1.0 - (sum(diferencias) / len(diferencias)) / _MAX_DIFERENCIA_INTENSIDAD
    else:
        similitud_intensidad = 0.0  # nada en común sobre lo que comparar intensidad

    z_a = _perfil_numerico(caso_a, catalogo)
    z_b = _perfil_numerico(caso_b, catalogo)
    ratios_comunes = set(z_a) & set(z_b)
    if ratios_comunes:
        distancia_cuadratica_media = math.sqrt(
            sum((z_a[r] - z_b[r]) ** 2 for r in ratios_comunes) / len(ratios_comunes)
        )
        similitud_numerica = 1.0 / (1.0 + distancia_cuadratica_media)
    else:
        similitud_numerica = 0.0  # ningún ratio comparable en ambos casos (degenerado, defensivo)

    puntuacion = (
        PESO_SECTOR_SEGMENTO * similitud_sector_segmento
        + PESO_ARQUETIPOS * similitud_arquetipos
        + PESO_INTENSIDAD * similitud_intensidad
        + PESO_NUMERICO * similitud_numerica
    )

    return SimilitudCasos(
        puntuacion=puntuacion,
        mismo_sector=mismo_sector,
        mismo_segmento=mismo_segmento,
        similitud_sector_segmento=similitud_sector_segmento,
        similitud_arquetipos=similitud_arquetipos,
        similitud_intensidad=similitud_intensidad,
        similitud_numerica=similitud_numerica,
        arquetipos_en_comun=tuple(sorted(interseccion)),
        ratios_comparados=len(ratios_comunes),
    )
