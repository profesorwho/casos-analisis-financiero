"""Clasificación legal (Art. 257 LSC) de cada caso generado: balance/ECPN/EFE abreviados o
normales — capa de cálculo sobre datos que el motor YA genera (activo total, cifra de
negocios), más una estimación de plantilla derivada del catálogo. No genera ningún dato
nuevo de balance/PyG ni toca `motor.empresa_base`/`motor.evolucion_arquetipo`.

Marco normativo (verificado externamente, BOE/ICAC, no asumido de memoria — sección 3 del
documento de especificaciones):

- Art. 257.1 LSC: una sociedad puede formular balance y ECPN ABREVIADOS si, durante DOS
  ejercicios consecutivos, cumple al menos 2 de estas 3 circunstancias: (a) activo total no
  superior a `UMBRAL_ACTIVO_EUR`; (b) importe neto de la cifra anual de negocios no superior a
  `UMBRAL_CIFRA_NEGOCIO_EUR`; (c) número medio de trabajadores no superior a
  `UMBRAL_EMPLEADOS`.
- Art. 257.3 LSC: cuando puede formularse balance abreviado, el ECPN y el EFE NO son
  obligatorios.
- Los umbrales usados aquí (4.000.000 € / 8.000.000 € / 50 trabajadores) son los VIGENTES a
  fecha de este módulo. Existe un Proyecto de Ley (121/000075, BOCG 21-nov-2025, transposición
  de la Directiva Delegada UE 2023/2775) que los subiría a 7.500.000 €/15.000.000 €/50 — sigue
  en trámite parlamentario, sin rango de ley, y aunque se apruebe se prevé que solo aplique a
  ejercicios iniciados desde el 1-1-2026 — los ejercicios que genera este motor (2023-2025)
  quedan siempre bajo los umbrales actuales, así que no hace falta anticipar la reforma. Si en
  el futuro el motor genera ejercicios 2026+, este punto habría que revisarlo.

Estimación de plantilla (número medio de trabajadores): el motor no genera plantilla como
dato propio (no hay ningún mecanismo de recursos humanos). Se estima con el MISMO mecanismo
de ruido mixto típico/atípico que usa el resto del motor (`_generar_partida` de
`motor.empresa_base`: 85% de los casos ±1,5 MAD, 15% "atípico" ±3 MAD) aplicado directamente
sobre `ratios.ventas_empleado` del catálogo (en miles de € por empleado), con su propio
`huber_scale_mad` — no se inventa ningún intervalo de corrección nuevo. La plantilla estimada
se deriva dividiendo la cifra de negocio YA generada entre ese ratio con ruido. Es un sorteo
ÚNICO por caso (sector+segmento+semilla), no por año: se trata como un rasgo estructural de la
empresa (productividad por empleado), igual que `rotacion_activo` en `generar_empresa_base` —
la plantilla estimada de cada año se deriva escalando esa productividad fija por la cifra de
negocio de ESE año, que sí varía año a año con el arquetipo.

**Advertencia epistémica, no un dato "real":** a diferencia del activo o la cifra de negocio
(que el motor genera directamente, con su propia variabilidad independiente), la plantilla es
una estimación de SEGUNDO ORDEN — se deriva de dos números ya generados (ventas) y un ratio
sectorial con ruido, no observada de forma independiente. Cualquier resultado del test legal
que dependa del criterio de empleados hereda esa incertidumbre adicional; los resultados que
dependen de activo o cifra de negocio son tan sólidos como el resto del motor.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from motor.empresa_base import (
    SEGMENTOS_VALIDOS,
    _generar_partida,
    cargar_y_validar_catalogo,
    resolver_fila_sector,
)

# Umbrales VIGENTES del Art. 257 LSC (ver docstring del módulo) — no los del Proyecto de Ley
# en trámite, que no aplicaría a los ejercicios 2023-2025 que genera este motor.
UMBRAL_ACTIVO_EUR = 4_000_000.0
UMBRAL_CIFRA_NEGOCIO_EUR = 8_000_000.0
UMBRAL_EMPLEADOS = 50.0

# Suelo defensivo sobre el ratio ventas_empleado con ruido (miles de € por empleado) — mismo
# criterio ya usado en el resto del motor (p. ej. SUELO_ROTACION_ACTIVO): evita un ratio
# absurdamente bajo o negativo que dispararía una plantilla estimada irreal.
SUELO_VENTAS_EMPLEADO_MILES_EUR = 10.0


class ClasificacionLegalError(Exception):
    pass


def _entropia_plantilla(sector: str, segmento: str) -> int:
    return zlib.crc32(f"{sector}|{segmento}|plantilla".encode("utf-8"))


def estimar_ventas_por_empleado(
    sector: str, segmento: str, semilla: int, catalogo: pd.DataFrame | None = None
) -> tuple[float, str]:
    """Ventas por empleado (miles de €), con el ruido mixto típico/atípico ya existente en el
    motor, sobre `ratios.ventas_empleado` del catálogo. Sorteo único por (sector, segmento,
    semilla) — no depende del año ni del arquetipo. Devuelve (valor, modo) igual que
    `_generar_partida`."""
    if segmento not in SEGMENTOS_VALIDOS:
        raise ClasificacionLegalError(f"Segmento '{segmento}' no válido. Debe ser uno de: {sorted(SEGMENTOS_VALIDOS)}")
    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()
    fila = resolver_fila_sector(catalogo, sector, segmento)
    rng = np.random.default_rng([semilla, _entropia_plantilla(sector, segmento)])
    return _generar_partida(
        rng,
        fila["ratios.ventas_empleado.huber_9y"],
        fila["ratios.ventas_empleado.huber_scale_mad"],
        suelo=SUELO_VENTAS_EMPLEADO_MILES_EUR,
    )


def estimar_plantilla(cifra_negocio_eur: float, ventas_empleado_miles_eur: float) -> float:
    """Plantilla media estimada = cifra de negocio del año / productividad por empleado
    (fija para el caso, ver docstring del módulo) — escala con la cifra de negocio real de
    cada año, no es un valor fijo repetido en los 3 ejercicios."""
    return cifra_negocio_eur / (ventas_empleado_miles_eur * 1000.0)


@dataclass(frozen=True)
class ResultadoClasificacionLegal:
    """Resultado del test de 2-de-3 (Art. 257.1 LSC) para UN ejercicio."""

    año: int
    activo_eur: float
    cifra_negocio_eur: float
    plantilla_estimada: float
    cumple_activo: bool
    cumple_cifra_negocio: bool
    cumple_empleados: bool
    n_criterios_cumplidos: int
    modelo: str  # "abreviado" | "normal"


def clasificar_ejercicio(
    año: int, activo_eur: float, cifra_negocio_eur: float, plantilla_estimada: float
) -> ResultadoClasificacionLegal:
    """Test de 2-de-3 del Art. 257.1 LSC para un único ejercicio (la estabilidad de 2
    ejercicios consecutivos se resuelve aparte, con `clasificar_caso`)."""
    cumple_activo = activo_eur <= UMBRAL_ACTIVO_EUR
    cumple_cifra = cifra_negocio_eur <= UMBRAL_CIFRA_NEGOCIO_EUR
    cumple_empleados = plantilla_estimada <= UMBRAL_EMPLEADOS
    n = sum((cumple_activo, cumple_cifra, cumple_empleados))
    return ResultadoClasificacionLegal(
        año=año,
        activo_eur=activo_eur,
        cifra_negocio_eur=cifra_negocio_eur,
        plantilla_estimada=plantilla_estimada,
        cumple_activo=cumple_activo,
        cumple_cifra_negocio=cumple_cifra,
        cumple_empleados=cumple_empleados,
        n_criterios_cumplidos=n,
        modelo="abreviado" if n >= 2 else "normal",
    )


def clasificar_par_ejercicios(
    resultado_anterior: ResultadoClasificacionLegal, resultado_actual: ResultadoClasificacionLegal
) -> str:
    """Art. 257.2 LSC: la facultad de formular en abreviado exige cumplir la condición durante
    DOS ejercicios consecutivos — "abreviado" solo si AMBOS ejercicios del par lo son por
    separado; si cualquiera de los dos no lo es, el par se clasifica "normal" (interpretación
    conservadora: sin un tercer ejercicio de referencia anterior a 2023, no hay forma de saber
    si la empresa ya venía cumpliendo antes — un único ejercicio que cumple no basta para
    ejercer la facultad)."""
    if resultado_anterior.modelo == "abreviado" and resultado_actual.modelo == "abreviado":
        return "abreviado"
    return "normal"
