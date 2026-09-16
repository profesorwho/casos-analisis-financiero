"""Mecanismo de ruido mixto típico/atípico (85%/15%, normal truncada) — extraído de
`motor/empresa_base.py` a su propio módulo para que otros generadores (`motor/amortizacion.py`)
puedan reutilizarlo sin crear una importación circular con `empresa_base.py`. Sin dependencias
de ningún otro módulo del motor — puramente funciones de ruido.

`empresa_base.py` reexporta estos tres nombres (`from motor.ruido import ...`), así que el resto
del código que ya los importaba como `motor.empresa_base._generar_partida` etc. sigue
funcionando sin cambios.

**Selector de modo de generación (`modo_generacion`, sección 2.17/2.16, Fase 4 Ronda 2 punto 2)**
— único punto de control de TODO el motor para forzar la rama típica/atípica de cualquier
sorteo, en vez de dejarlo al 85%/15% habitual. Vive aquí porque `PROB_ATIPICO` se usa en
exactamente 2 sitios de todo `motor/` (`_generar_partida`/`_generar_partida_con_memoria`, ambas
en este módulo — auditado con grep sobre todo el paquete, no asumido) y los 8+ sitios auditados
en la Ronda 1 pasan, sin excepción, por una de las dos. Un cambio aquí basta para cubrirlos
todos, sin tocar ni un solo helper de `empresa_base.py`/`evolucion_arquetipo.py`.

**Por qué `contextvars` y no un parámetro `modo_generacion` en cada función intermedia**: la
alternativa (threading explícito) obligaría a añadir el parámetro a ~9 helpers de
`empresa_base.py` más las llamadas de `_evolucionar_un_año` — exactamente el tipo de cambio de
alto riesgo que este proyecto ya sufrió una vez (el sesgo de RNG compartido, varias sesiones para
encontrarlo). Con `contextvars`, los ~3 puntos de entrada públicos (`generar_empresa_base`,
`generar_evolucion_combinada`, `motor.memoria.generar_caso_combinado`) activan el modo al
ENTRAR y lo restauran al SALIR (`activar_modo_generacion`/`desactivar_modo_generacion`, o el
gestor de contexto `modo_generacion_activo`) — todo lo que hay DEBAJO (año base, PyG, los 4
lotes de desglose, `ROE_caso`, provisiones/insolvencias/subvención de fondo) hereda el modo de
forma transparente, sin ningún cambio de firma.

**Decisiones binarias transversales (provisión/insolvencia/subvención de fondo)**: NO tienen un
concepto de magnitud continua (no pasan por `_generar_partida`), pero SÍ comparten la misma idea
de fondo que típico/atípico — "tipico" = el caso más común/aburrido en todas las dimensiones,
"atipico" = el caso raro/notable en todas las dimensiones. `_resolver_binario_por_modo`
generaliza la misma decisión a cualquier probabilidad base, reutilizada por `motor.provisiones`/
`motor.insolvencias`/`motor.coberturas_subvenciones` para sus propios sorteos de "activa".
**Polaridad AUTO-ADAPTATIVA, no asumida fija** (hallazgo real durante la implementación, no solo
un riesgo hipotético documentado de antemano): la probabilidad de provisión (25%) y de
subvención de fondo (2%-20% por categoría) son siempre <50%, pero la de insolvencia
(`motor.insolvencias.probabilidad_insolvencia`) puede llegar a 60% con los boosts de arquetipo
4+7 apilados — ahí `True` ("activa") sería la rama MAYORITARIA, no la minoritaria. Si
`_resolver_binario_por_modo` fijara ciegamente `atipico→True`, en ese caso concreto "atípico"
forzaría precisamente el resultado más común, al revés de lo que su nombre promete. Corregido
antes de aplicarlo: la función compara `probabilidad_base` contra 0,5 en cada llamada y fuerza
la rama mayoritaria/minoritaria real, no un booleano fijo — "tipico"/"atipico" significan
siempre "caso común"/"caso raro", cualquiera que sea `probabilidad_base`. Con esta corrección, un
mecanismo binario nuevo puede reutilizar el helper sin tener que verificar su propia polaridad de
antemano — la función ya se adapta sola.

**El RNG se consume SIEMPRE, cambie o no el modo** (`_resolver_binario_por_modo` calcula el
sorteo real antes de mirar el modo) — mismo patrón defensivo ya validado en provisiones/
insolvencias ("se consumen los mismos draws se active la rama o no"): la posición de la
secuencia de `rng` no debe depender de qué modo esté activo, para que cualquier sorteo posterior
que comparta el mismo `rng` no se desincronice entre modos."""

from __future__ import annotations

import contextlib
import contextvars

import numpy as np

PROB_ATIPICO = 0.15
DESVIACIONES_TIPICO = 1.5
DESVIACIONES_ATIPICO = 3.0

# --- Selector de modo de generación — ver docstring del módulo. ---
MODOS_GENERACION_VALIDOS = frozenset({"tipico", "atipico", "aleatorio"})

_modo_generacion_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "modo_generacion", default="aleatorio"
)


class ModoGeneracionInvalidoError(ValueError):
    """`modo_generacion` no es uno de los 3 valores válidos."""


def activar_modo_generacion(modo: str) -> contextvars.Token:
    """Activa `modo` para el hilo/tarea actual — devuelve un token para restaurar el valor
    anterior con `desactivar_modo_generacion`. Preferir el gestor de contexto
    `modo_generacion_activo` salvo que el cuerpo de la función que activa el modo sea demasiado
    largo para envolverlo cómodamente en un `with` (mismo efecto, sin reindentar todo el cuerpo)."""
    if modo not in MODOS_GENERACION_VALIDOS:
        raise ModoGeneracionInvalidoError(f"modo_generacion='{modo}' no válido. Debe ser uno de: {sorted(MODOS_GENERACION_VALIDOS)}")
    return _modo_generacion_var.set(modo)


def desactivar_modo_generacion(token: contextvars.Token) -> None:
    _modo_generacion_var.reset(token)


@contextlib.contextmanager
def modo_generacion_activo(modo: str):
    """Gestor de contexto: `with modo_generacion_activo("tipico"): ...` — mismo efecto que
    `activar_modo_generacion`/`desactivar_modo_generacion`, para cuerpos de función cortos donde
    envolver todo en un `with` no penaliza la legibilidad."""
    token = activar_modo_generacion(modo)
    try:
        yield
    finally:
        desactivar_modo_generacion(token)


def _resolver_binario_por_modo(rng: np.random.Generator, probabilidad_base: float) -> bool:
    """Decide cualquier sorteo binario del motor ("¿pasa el fenómeno X o no?"), respetando
    `modo_generacion` — ver docstring del módulo. `probabilidad_base` es la probabilidad de que
    el sorteo dé `True` bajo modo "aleatorio" (el comportamiento de siempre, sin cambios).

    "tipico"/"atipico" fuerzan la rama MAYORITARIA/MINORITARIA respectivamente — NO
    "True"/"False" a secas: para `probabilidad_base <= 0,5` (el caso de todos los mecanismos
    actuales salvo uno) la rama minoritaria es `True`, así que "tipico"→False/"atipico"→True; si
    algún mecanismo tuviera `probabilidad_base > 0,5` (ocurre en la práctica: el techo absoluto
    de `motor.insolvencias.probabilidad_insolvencia` con los boosts de arquetipo 4+7 apilados
    puede llegar a 0,60), la polaridad se invierte automáticamente — "tipico" sigue siendo "el
    caso más común/aburrido", "atipico" sigue siendo "el caso raro/notable", en vez de fijar
    ciegamente `True`/`False` y arriesgar forzar la rama mayoritaria bajo el nombre "atípico"."""
    sorteo = rng.random() < probabilidad_base  # SIEMPRE se consume, cambie o no el modo — ver docstring
    modo = _modo_generacion_var.get()
    if modo == "aleatorio":
        return sorteo
    rama_true_es_minoritaria = probabilidad_base <= 0.5
    if modo == "atipico":
        return rama_true_es_minoritaria
    return not rama_true_es_minoritaria  # "tipico"


def _decidir_atipico(rng: np.random.Generator) -> bool:
    return _resolver_binario_por_modo(rng, PROB_ATIPICO)


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
    atipico = _decidir_atipico(rng)
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
    atipico = _decidir_atipico(rng)
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
