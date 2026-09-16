"""Deterioro de valor de créditos por operaciones comerciales (cuenta 490 del PGC) — provisión de
insolvencias de clientes. A diferencia de las provisiones del subgrupo 14 (`motor/provisiones.py`,
pasivo, obligación probable), esta es un DETERIORO DE ACTIVO: resta directamente de "Clientes"
dentro de Deudores comerciales y otras cuentas a cobrar (realizable), sin añadir ninguna deuda
nueva. Ver PGC, norma de registro y valoración 9ª (instrumentos financieros), deterioro de valor
de créditos por operaciones comerciales.

**Probabilidad de fondo, independiente de cualquier arquetipo** (mismo patrón ya construido para
`sortear_provision_baseline`/`sortear_subvencion_baseline`) — para que pueda aparecer también con
el arquetipo 6 ("línea base sana"), demostrando su efecto sin depender de un caso de riesgo.

**Magnitud (probabilidad Y importe) anclada a `ratios.cobro_dias` del catálogo, no un sorteo
independiente**: cuanto más largo el plazo de cobro típico del sector/caso, mayor el riesgo real
de impago — un cliente que tarda 150 días en pagar es estructuralmente más propenso al impago que
uno que tarda 20. `factor_riesgo_cobro_dias` es una rampa lineal entre `UMBRAL_COBRO_DIAS_
INSOLVENCIA` (60 días — por debajo, sin riesgo adicional sobre el suelo) y `TECHO_COBRO_DIAS_
INSOLVENCIA` (150 días — a partir de ahí, riesgo máximo); ambos anclados a la distribución real de
`ratios.cobro_dias.huber_9y` de los 27 sectores (rango 9,6-186,3 días, media≈86,3, mediana≈84,0):
el umbral deja fuera a la mitad "corta" del catálogo (mediana justo por encima), el techo cubre el
grueso de la cola larga sin dejar la rampa completamente plana en el extremo (30.2, el sector más
lento, con 186,3 días, satura el factor en 1,0 igual que cualquier otro por encima de 150).
Probabilidad base 20%-40% (`PROBABILIDAD_INSOLVENCIA_SUELO/TECHO`, dentro del rango "fácil de
encontrar por semilla" ya usado para provisiones); rango de importe (2%-5% de Clientes en el
extremo sin riesgo, 4%-10% en el extremo de mayor riesgo) escala con el MISMO factor.

**Conexión con los arquetipos 4 (deterioro del ciclo de caja) y 7 (dependencia de pocos
clientes)**: cuando cualquiera de los dos está activo, la probabilidad sube (+10 puntos
porcentuales cada uno, acumulables, topado a `TECHO_PROBABILIDAD_INSOLVENCIA_ABSOLUTO=60%`) y la
magnitud también (`MULTIPLICADOR_MAGNITUD_BOOST=1,3`, si cualquiera de los dos está activo — no
acumulable entre ambos: la razón económica es la misma "esto es más arriesgado de lo normal", no
dos riesgos independientes que se sumen). Criterio: 4 señala que el circulante YA se está
deteriorando (empeora el contexto de cobro real, más allá de lo que el `cobro_dias` sectorial por
sí solo sugiere); 7 señala concentración en pocos clientes (si uno de ellos impaga, el golpe es
proporcionalmente mayor y más probable que ocurra en el horizonte de 3 años del caso).

**Movimiento anual** (saldo inicial/dotación/aplicación/reversión/saldo final) — mismo patrón que
`motor/provisiones.py`: dotación ÍNTEGRA el año de dotación (2024 o 2025, 50/50, nunca en el año
base); a partir de ahí, liberación LINEAL (tasa anual = importe dotado / plazo) repartida
`FRACCION_APLICACION=0,70` aplicación / 0,30 reversión (mismo criterio y mismo valor que
provisiones — una provisión de insolvencia rutinaria se confirma mayoritariamente como pérdida
real, con una fracción menor de sobre-estimación).

**Aplicación vs. reversión — asimetría deliberada sobre lo que le pasa a `realizable`, distinta de
provisiones.** En provisiones (pasivo), tanto la aplicación (uso real) como el exceso (reversión)
LIBERAN el pasivo por igual — ambos reducen la deuda. Aquí NO: la aplicación es la BAJA DEFINITIVA
del derecho de cobro (el cliente formalmente no va a pagar) — retira a la vez, por el mismo
importe, el saldo bruto de "Clientes" y el deterioro que lo cubría, así que el efecto NETO sobre
`realizable` es CERO en el momento de la baja (la pérdida ya se reconoció íntegra en la PyG el año
de la dotación, no se reconoce dos veces ni se revierte). La reversión, en cambio, SÍ es una
mejora económica real (el cliente pagó después de todo, o el riesgo se reevaluó a la baja) — libera
deterioro y `realizable` recupera ese importe, con abono a "Excesos de provisiones" en PyG (misma
línea que usan las provisiones del subgrupo 14, sin desglosar aparte en el modelo oficial). Por
eso `PasoInsolvencia` expone DOS magnitudes distintas: `saldo_eur` (deterioro vivo, para la
memoria/futura incidencia didáctica — decrece con aplicación Y reversión, igual que una provisión)
y `deduccion_realizable_eur` (lo que de verdad se resta de `realizable_eur` cada año — decrece
SOLO con la reversión acumulada; la aplicación no lo mueve, queda permanentemente incorporada).

**PyG**: dotación resta de `otros_gastos_explot` (línea 7 del modelo oficial — el deterioro de
créditos comerciales no es un gasto de personal, a diferencia de alguna categoría del subgrupo
14); reversión suma a `otros_ingresos_explot` ("Excesos de provisiones"), mismo patrón que
provisiones.

**EFE — SIN línea nueva, verificado (no asumido)**: `a3b_deudores` (`motor/efe.py`) ya se calcula
como `-(actual.balance_eur["realizable"] - anterior.balance_eur["realizable"])` — puesto que el
deterioro reduce `realizable` directamente (sin pasar por ninguna deuda nueva), esa línea ya
existente absorbe el efecto exacto sin ningún cambio en `motor/efe.py`, igual que las provisiones
del subgrupo 14 se reconcilian vía A.3.e/A.3.f sin línea nueva."""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from motor.ruido import _resolver_binario_por_modo

# --- Anclaje a cobro_dias (ver docstring del módulo) ---
UMBRAL_COBRO_DIAS_INSOLVENCIA = 60.0
TECHO_COBRO_DIAS_INSOLVENCIA = 150.0

# --- Probabilidad de fondo (antes de los boosts de arquetipo) ---
PROBABILIDAD_INSOLVENCIA_SUELO = 0.20
PROBABILIDAD_INSOLVENCIA_TECHO = 0.40
BOOST_PROBABILIDAD_DETERIORO_CICLO_CAJA = 0.10
BOOST_PROBABILIDAD_DEPENDENCIA_CLIENTES = 0.10
TECHO_PROBABILIDAD_INSOLVENCIA_ABSOLUTO = 0.60

# --- Magnitud: % de "Clientes" (dentro de deudores) del año anterior a la dotación ---
RANGO_IMPORTE_PCT_CLIENTES_SUELO = (0.02, 0.05)
RANGO_IMPORTE_PCT_CLIENTES_TECHO = (0.04, 0.10)
MULTIPLICADOR_MAGNITUD_BOOST = 1.3
SUELO_IMPORTE_INSOLVENCIA_EUR = 5_000.0

# --- Horizonte y reparto aplicación/reversión — mismo criterio que provisiones, horizonte más
# corto (el deterioro de un cliente concreto se resuelve más rápido que una provisión genérica). ---
RANGO_PLAZO_TOTAL_AÑOS_INSOLVENCIA = (0.5, 2.0)
FRACCION_APLICACION = 0.70


def _entropia_insolvencia(sector: str, segmento: str, sufijo: str = "") -> int:
    return zlib.crc32(f"{sector}|{segmento}|insolvencia{sufijo}".encode("utf-8"))


def factor_riesgo_cobro_dias(cobro_dias_huber: float) -> float:
    """Rampa lineal 0..1 entre `UMBRAL_COBRO_DIAS_INSOLVENCIA` y `TECHO_COBRO_DIAS_INSOLVENCIA`
    — ver docstring del módulo para el anclaje contra la distribución real del catálogo."""
    rango = TECHO_COBRO_DIAS_INSOLVENCIA - UMBRAL_COBRO_DIAS_INSOLVENCIA
    return min(max((cobro_dias_huber - UMBRAL_COBRO_DIAS_INSOLVENCIA) / rango, 0.0), 1.0)


def probabilidad_insolvencia(
    cobro_dias_huber: float, deterioro_ciclo_caja_activo: bool, dependencia_clientes_activo: bool
) -> float:
    factor = factor_riesgo_cobro_dias(cobro_dias_huber)
    base = PROBABILIDAD_INSOLVENCIA_SUELO + factor * (PROBABILIDAD_INSOLVENCIA_TECHO - PROBABILIDAD_INSOLVENCIA_SUELO)
    boost = 0.0
    if deterioro_ciclo_caja_activo:
        boost += BOOST_PROBABILIDAD_DETERIORO_CICLO_CAJA
    if dependencia_clientes_activo:
        boost += BOOST_PROBABILIDAD_DEPENDENCIA_CLIENTES
    return min(base + boost, TECHO_PROBABILIDAD_INSOLVENCIA_ABSOLUTO)


@dataclass(frozen=True)
class ParametrosInsolvencia:
    """Rasgos ESTRUCTURALES de la insolvencia del caso, sorteados UNA vez (no por año) — mismo
    criterio que `ParametrosProvision`. `activa=False` dispensa el resto de campos. Como con
    provisiones, la MAGNITUD (`importe_dotado_eur`) no se sortea aquí: depende de "Clientes" del
    año anterior a la dotación, que no se conoce hasta que ese año se resuelve — ver
    `sortear_importe_insolvencia_eur`. Sin campo `categoria` (a diferencia de provisiones): una
    única cuenta (490), sin variantes."""

    activa: bool = False
    año_dotacion: int = 0
    plazo_total_años: float = 0.0


def sortear_insolvencia_baseline(
    sector: str,
    segmento: str,
    semilla: int,
    cobro_dias_huber: float,
    deterioro_ciclo_caja_activo: bool,
    dependencia_clientes_activo: bool,
) -> ParametrosInsolvencia:
    """Sorteo ÚNICO por caso, probabilidad anclada a `cobro_dias_huber` + boost de arquetipo 4/7
    — ver docstring del módulo. Acoplado a `modo_generacion` (Fase 4 Ronda 2 punto 2, ver motor.
    ruido) vía `_resolver_binario_por_modo`, que aquí es imprescindible en su forma auto-
    adaptativa: `probabilidad` puede superar 0,5 con los boosts de arquetipo 4/7 apilados (hasta
    `TECHO_PROBABILIDAD_INSOLVENCIA_ABSOLUTO=0,60`) — ver docstring de `motor.ruido` para el
    hallazgo completo."""
    rng = np.random.default_rng([semilla, _entropia_insolvencia(sector, segmento, "_baseline")])
    probabilidad = probabilidad_insolvencia(cobro_dias_huber, deterioro_ciclo_caja_activo, dependencia_clientes_activo)
    activa = _resolver_binario_por_modo(rng, probabilidad)
    if not activa:
        # Consume los mismos draws que la rama activa (mismo cuidado ya aplicado en provisiones)
        # para que la posición de cualquier sorteo posterior no dependa de si salió activa.
        rng.integers(2)
        rng.uniform(*RANGO_PLAZO_TOTAL_AÑOS_INSOLVENCIA)
        return ParametrosInsolvencia()

    año_dotacion = 2024 if rng.integers(2) == 0 else 2025
    plazo_total_años = rng.uniform(*RANGO_PLAZO_TOTAL_AÑOS_INSOLVENCIA)
    return ParametrosInsolvencia(activa=True, año_dotacion=año_dotacion, plazo_total_años=plazo_total_años)


def sortear_importe_insolvencia_eur(
    sector: str,
    segmento: str,
    semilla: int,
    clientes_referencia_eur: float,
    cobro_dias_huber: float,
    boost_magnitud_activo: bool,
) -> float:
    rng = np.random.default_rng([semilla, _entropia_insolvencia(sector, segmento, "_magnitud")])
    factor = factor_riesgo_cobro_dias(cobro_dias_huber)
    bajo = RANGO_IMPORTE_PCT_CLIENTES_SUELO[0] + factor * (
        RANGO_IMPORTE_PCT_CLIENTES_TECHO[0] - RANGO_IMPORTE_PCT_CLIENTES_SUELO[0]
    )
    alto = RANGO_IMPORTE_PCT_CLIENTES_SUELO[1] + factor * (
        RANGO_IMPORTE_PCT_CLIENTES_TECHO[1] - RANGO_IMPORTE_PCT_CLIENTES_SUELO[1]
    )
    bruto_eur = rng.uniform(bajo, alto) * clientes_referencia_eur
    if boost_magnitud_activo:
        bruto_eur *= MULTIPLICADOR_MAGNITUD_BOOST
    return max(bruto_eur, SUELO_IMPORTE_INSOLVENCIA_EUR)


@dataclass(frozen=True)
class PasoInsolvencia:
    saldo_eur: float  # deterioro vivo (decrece con aplicación Y reversión) — memoria/incidencia futura
    dotacion_eur: float  # solo > 0 en el año de dotación
    aplicacion_eur: float  # baja definitiva del derecho de cobro — sin caja, sin PyG, NO recupera realizable
    exceso_eur: float  # reversión ("Excesos de provisiones") — sin caja, SÍ recupera realizable
    exceso_acumulado_eur: float  # reversión acumulada desde la dotación — estado a trasladar al año siguiente
    deduccion_realizable_eur: float  # lo que se resta de `realizable_eur` este año (ver docstring)


def evolucionar_insolvencia(
    parametros: ParametrosInsolvencia,
    importe_dotado_eur: float,
    saldo_anterior_eur: float,
    exceso_acumulado_anterior_eur: float,
    año: int,
) -> PasoInsolvencia:
    """Un paso anual. `saldo_anterior_eur`/`exceso_acumulado_anterior_eur` son 0.0 antes del año
    de dotación (y el propio `PARAMETROS_INSOLVENCIA_INACTIVA` ya deja `activa=False` para cuando
    no hay ninguna insolvencia en el caso). `deduccion_realizable_eur = importe_dotado_eur −
    exceso_acumulado_eur` — ver docstring del módulo para por qué la aplicación NO forma parte de
    esta resta (a diferencia de `saldo_eur`, que sí decrece con ambas)."""
    if not parametros.activa or año < parametros.año_dotacion:
        return PasoInsolvencia(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    if año == parametros.año_dotacion:
        saldo_eur = importe_dotado_eur
        dotacion_eur = importe_dotado_eur
        aplicacion_eur = 0.0
        exceso_eur = 0.0
        exceso_acumulado_eur = exceso_acumulado_anterior_eur
    else:
        tasa_anual_eur = importe_dotado_eur / parametros.plazo_total_años
        reduccion_eur = min(saldo_anterior_eur, tasa_anual_eur)
        aplicacion_eur = reduccion_eur * FRACCION_APLICACION
        exceso_eur = reduccion_eur - aplicacion_eur
        saldo_eur = saldo_anterior_eur - reduccion_eur
        dotacion_eur = 0.0
        exceso_acumulado_eur = exceso_acumulado_anterior_eur + exceso_eur

    deduccion_realizable_eur = importe_dotado_eur - exceso_acumulado_eur
    return PasoInsolvencia(saldo_eur, dotacion_eur, aplicacion_eur, exceso_eur, exceso_acumulado_eur, deduccion_realizable_eur)
