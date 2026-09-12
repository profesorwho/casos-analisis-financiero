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


def _generar_partida_con_memoria(
    rng: np.random.Generator,
    valor_anterior: float,
    huber_9y: float,
    huber_scale_mad: float,
    peso_memoria: float,
    factor_reduccion_ruido: float,
    suelo: float | None = None,
    techo: float | None = None,
) -> tuple[float, str]:
    """Variante de `_generar_partida` con continuidad respecto al año anterior — para partidas
    que se vuelven a sortear cada año (p. ej. las primitivas de PyG no forzadas por ningún
    arquetipo, ver `motor.empresa_base._generar_pyg_hasta_baii`) en vez de fijarse "desde 2023"
    como el resto de perfiles del motor. `_generar_partida` trata cada año como una empresa
    NUEVA sorteada de cero contra el Huber/MAD del sector (una medida de variación TRANSVERSAL,
    entre empresas distintas en un momento dado) — year-to-year, eso genera más varianza
    acumulada de la que tendría la evolución real de UNA misma empresa. Ver
    decisiones_plausibilidad.md #75/#77/#78.

    `centro` mezcla el valor REAL del año anterior con el Huber del sector (reversión a la media,
    AR(1)) — ni pura continuidad (permitiría una deriva sin freno año a año) ni puro sorteo desde
    el Huber (el comportamiento actual). `escala` reduce el Huber_scale_mad — la variación DE UNA
    MISMA empresa de un año a otro es menor que la variación ENTRE empresas del sector."""
    centro = peso_memoria * valor_anterior + (1 - peso_memoria) * huber_9y
    escala = huber_scale_mad * factor_reduccion_ruido
    atipico = rng.random() < PROB_ATIPICO
    max_desviaciones = DESVIACIONES_ATIPICO if atipico else DESVIACIONES_TIPICO
    z = _normal_truncada(rng, max_desviaciones)
    valor = centro + z * escala
    # Techo/suelo blando frente al Huber del sector, mismo espíritu que el resto del motor
    # (p. ej. FRACCION_MINIMA/MAXIMA_VS_HUBER en evolucion_arquetipo.py): ni siquiera 2 años
    # seguidos de deriva correlacionada en la misma dirección pueden alejarse más de lo que ya
    # permitiría un único sorteo "atípico" fresco.
    valor = max(valor, huber_9y - DESVIACIONES_ATIPICO * huber_scale_mad)
    valor = min(valor, huber_9y + DESVIACIONES_ATIPICO * huber_scale_mad)
    if suelo is not None:
        valor = max(valor, suelo)
    if techo is not None:
        valor = min(valor, techo)
    return valor, ("atipico" if atipico else "tipico")


def _renormalizar_a_total(valores: dict[str, float], total_objetivo: float) -> dict[str, float]:
    suma = sum(valores.values())
    factor = total_objetivo / suma
    return {clave: valor * factor for clave, valor in valores.items()}
