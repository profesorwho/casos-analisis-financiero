"""Mecanismo de ruido mixto típico/atípico (85%/15%, normal truncada) — extraído de
`motor/empresa_base.py` a su propio módulo para que otros generadores (`motor/amortizacion.py`)
puedan reutilizarlo sin crear una importación circular con `empresa_base.py`. Sin dependencias
de ningún otro módulo del motor — puramente funciones de ruido.

`empresa_base.py` reexporta estos tres nombres (`from motor.ruido import ...`), así que el resto
del código que ya los importaba como `motor.empresa_base._generar_partida` etc. sigue
funcionando sin cambios.
"""

from __future__ import annotations

import numpy as np

PROB_ATIPICO = 0.15
DESVIACIONES_TIPICO = 1.5
DESVIACIONES_ATIPICO = 3.0


def _normal_truncada(rng: np.random.Generator, max_desviaciones: float) -> float:
    while True:
        z = rng.normal()
        if abs(z) <= max_desviaciones:
            return float(z)


def _generar_partida(
    rng: np.random.Generator,
    huber_9y: float,
    huber_scale_mad: float,
    suelo: float | None = None,
    techo: float | None = None,
) -> tuple[float, str]:
    atipico = rng.random() < PROB_ATIPICO
    max_desviaciones = DESVIACIONES_ATIPICO if atipico else DESVIACIONES_TIPICO
    z = _normal_truncada(rng, max_desviaciones)
    valor = huber_9y + z * huber_scale_mad
    if suelo is not None:
        valor = max(valor, suelo)
    if techo is not None:
        valor = min(valor, techo)
    return valor, ("atipico" if atipico else "tipico")


def _renormalizar_a_total(valores: dict[str, float], total_objetivo: float) -> dict[str, float]:
    suma = sum(valores.values())
    factor = total_objetivo / suma
    return {clave: valor * factor for clave, valor in valores.items()}
