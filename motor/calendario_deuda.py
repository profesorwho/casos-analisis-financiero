"""Calendario de vencimientos y cuadro de movimientos de la deuda (encargo #112) — módulo NUEVO
y PURO de DERIVACIÓN sobre un caso ya generado (`EvolucionArquetipo`). No genera balance, PyG,
EFE ni ECPN, no sortea ningún importe del motor, no toca ninguna dataclass existente: toma los
saldos YA cuadrados de cada ejercicio (`deudas_fin_largo_desglose_eur`/`..._corto_desglose_eur`,
`otras_deudas_largo_desglose_eur`/`..._corto_desglose_eur`, `balance_eur["acreedores_comerciales"]`,
`cobertura_plazo_residual_años`) y los reparte en tramos de vencimiento (1/2/3/4/5/más de 5 años)
más un cuadro de movimientos anual (2024/2025) de la deuda financiera con coste.

**Investigación previa (PGC, RD 1514/2007, texto consolidado BOE-A-2007-19884)** — verificado
contra el PDF oficial, no de memoria (ver `docs/decisiones_plausibilidad.md` #112 para el detalle
completo de la búsqueda):
- Memoria NORMAL, Nota 9 "Instrumentos financieros", apartado 9.3.2.1.b) "Riesgo de liquidez":
  *"Para los pasivos financieros que tengan un vencimiento determinado o determinable, se deberá
  informar sobre los importes que venzan en cada uno de los cinco años siguientes al cierre del
  ejercicio y del resto hasta su último vencimiento. Estas indicaciones figurarán separadamente
  para cada una de las partidas de pasivos financieros conforme al modelo de balance."*
- Memoria ABREVIADA, apartado 6 "Pasivos financieros", letra a): el mismo texto casi literal
  ("importe de las deudas que venzan en cada uno de los cinco años siguientes... para cada uno de
  los epígrafes y partidas relativos a deudas, conforme al modelo de balance"). **Corrección
  respecto a la premisa del encargo**: la información de vencimientos SÍ es obligatoria en el
  modelo Abreviado (Nota 6.a), no solo en el Normal — no se marca "incluido con fines didácticos"
  en ningún modelo, a diferencia del EFE (que sí es exclusivo de modelo Normal/obligación real).
- Excluye, por construcción del propio modelo de balance (epígrafes NO clasificados como "deudas"
  con vencimiento propio): provisiones (epígrafes I/II "Provisiones", propio del subgrupo 14, ver
  `motor/provisiones.py`), periodificaciones (epígrafes V/VI, propio del primer lote de desglose),
  y los saldos con AAPP que viven dentro de acreedores comerciales/`aapp_pendiente` (parte de
  "Acreedores comerciales y otras cuentas a pagar", no de "Deudas"). Las filas de este módulo
  cubren "II. Deudas a largo/corto plazo" (entidades de crédito, arrendamiento financiero,
  obligaciones, otros pasivos financieros, derivados — cuarto lote), "Otras deudas" no financieras
  (acreedores por inmovilizado, fianzas/depósitos, deudas con socios, remanente — quinto lote) y,
  de forma más laxa que el texto estricto de la nota (que habla de "deudas", no de "acreedores
  comerciales"), una fila de "Acreedores comerciales" (100% a 1 año, sin vencimiento a largo en
  este motor) para que la tabla reconcilie con el 100% de la deuda no comercial mostrada en
  Balance — decisión del propio encargo, documentada como ampliación didáctica, no como exigencia
  estricta del PGC.

**Independencia total del resto del motor**: los 4 parámetros nuevos (`plazo_remanente_entidades_
credito_años`, `plazo_remanente_otros_pasivos_financieros_años`, `año_vencimiento_obligaciones`,
`plazo_acreedores_inmovilizado_años`) se sortean con un generador INDEPENDIENTE, sembrado con un
hash ESTABLE (`zlib.crc32`, nunca `hash()` de Python) de `(semilla, sector, segmento,
"calendario_deuda", sufijo)` — mismo patrón que `_entropia_otras_deudas`/`sortear_deudas_socios_
baseline` en `motor/empresa_base.py`. Nunca se toca el `rng` principal del caso: generar el
calendario de un caso no cambia ni un euro de su balance/PyG/EFE/ECPN ya calculados (verificado en
`tests/test_calendario_deuda.py::test_generar_calendario_no_altera_el_caso`)."""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field

import numpy as np

from motor.evolucion_arquetipo import AÑO_BASE, AÑOS, PLAZO_REMANENTE_ARRENDAMIENTO_AÑOS, EvolucionArquetipo

# --------------------------------------------------------------------------------------------
# Hipótesis de diseño de los 4 parámetros nuevos — ver docs/decisiones_plausibilidad.md #112
# para la justificación completa (incluidas las fuentes citadas o la ausencia declarada de ellas).
# Ninguno tiene ancla de catálogo ACCID (el catálogo no modela calendarios de vencimiento).
# --------------------------------------------------------------------------------------------

# Entidades de crédito — plazo remanente TOTAL (en años, medido desde el cierre de CADA ejercicio,
# sorteado una vez por caso, no por año) de la masa "residual" que agrega tanto financiación de
# circulante como de inversión a plazo medio. Orden de magnitud anclado a fuente EXTERNA: ICO
# (Instituto de Crédito Oficial), líneas "ICO Empresas y Emprendedores" — plazos de amortización
# ofertados de 1, 3, 5, 7, 10, 15 o 20 años según la finalidad (ico.es, líneas de mediación,
# consultado septiembre de 2026); un rango 5-10 años cubre el tramo medio de un préstamo de
# inversión, deliberadamente más largo que el circulante puro (que este motor separa en las
# categorías "obligaciones"/"otros pasivos financieros", con sus propios rangos, más cortos).
RANGO_PLAZO_REMANENTE_ENTIDADES_CREDITO_AÑOS = (5, 10)

# Otros pasivos financieros — residual/mixto (ver `PERFIL_DEUDAS_FIN_POR_CATEGORIA`, sin sesgo
# fuerte hacia ningún plazo, `FRACCION_LARGO_POR_TIPO_DEUDA_FIN["otros_pasivos_financieros"]=0.55`,
# el reparto largo/corto más equilibrado de las 3 categorías con perfil propio) — plazo remanente
# más corto que entidades de crédito, coherente con ese reparto más equilibrado. Hipótesis de
# diseño PURA, sin fuente externa específica (a diferencia de entidades de crédito).
RANGO_PLAZO_REMANENTE_OTROS_PASIVOS_FINANCIEROS_AÑOS = (3, 6)

# Obligaciones y otros valores negociables — vencimiento BULLET (un solo tramo, todo el importe
# en el año de vencimiento), rango orientativo tal como sugiere el propio encargo. Hipótesis de
# diseño PURA — no se encontró una fuente externa fiable y específica para el plazo típico de
# emisiones de renta fija de PYME/empresa mediana española (MARF u otro) que se pudiera citar sin
# inventar precisión; se declara así explícitamente, sin fuente.
RANGO_AÑO_VENCIMIENTO_OBLIGACIONES = (5, 8)

# Acreedores por adquisición de inmovilizado a largo plazo — aplazamiento de proveedor de bienes
# de equipo, reparto uniforme entre los años 2..P_inm. Hipótesis de diseño PURA, rango orientativo
# del propio encargo — no se encontró fuente externa específica para el plazo típico de este tipo
# de financiación de proveedor en España; se declara así, sin fuente.
RANGO_PLAZO_ACREEDORES_INMOVILIZADO_AÑOS = (2, 4)

TRAMOS = ("dos", "tres", "cuatro", "cinco", "mas_de_cinco")


def _entropia_calendario(sector: str, segmento: str, sufijo: str) -> int:
    return zlib.crc32(f"{sector}|{segmento}|calendario_deuda{sufijo}".encode("utf-8"))


@dataclass(frozen=True)
class TramosVencimiento:
    """Los 6 tramos oficiales de la Nota de "Pasivos financieros"/"Riesgo de liquidez" — `un_año`
    es SIEMPRE el saldo a corto plazo exacto de la categoría en el Balance de ese ejercicio; los
    otros 5 reparten el saldo a largo plazo. `total` debe cuadrar con el saldo total (corto+largo)
    de la categoría a 1 € — comprobado en `tests/test_calendario_deuda.py`, nunca corregido aquí
    con ningún plug: un descuadre es un error de implementación (ver protocolo de parada del
    encargo)."""
    un_año: float
    dos: float
    tres: float
    cuatro: float
    cinco: float
    mas_de_cinco: float

    @property
    def total(self) -> float:
        return self.un_año + self.dos + self.tres + self.cuatro + self.cinco + self.mas_de_cinco


@dataclass(frozen=True)
class ParametrosCalendarioDeuda:
    """Sorteo ÚNICO por caso (sector+segmento+semilla) de los 4 parámetros sin ancla de catálogo
    — ver constantes arriba para el rango y la justificación de cada uno."""
    plazo_remanente_entidades_credito_años: int
    plazo_remanente_otros_pasivos_financieros_años: int
    año_vencimiento_obligaciones: int
    plazo_acreedores_inmovilizado_años: int


@dataclass(frozen=True)
class MovimientoCategoria:
    """Cuadro de movimientos de UNA categoría de deuda financiera CON coste, UN ejercicio (2024 o
    2025) — ver docstring del módulo, "Diseño 2" del encargo. `saldo_final == saldo_inicial -
    amortizaciones + disposiciones` es una identidad ALGEBRAICA por construcción (no una
    comprobación externa): `disposiciones` se despeja siempre de esa misma ecuación."""
    categoria: str
    saldo_inicial_eur: float
    amortizaciones_eur: float
    disposiciones_eur: float
    saldo_final_eur: float
    cancelacion_anticipada: bool  # True si la regla "normal" de disposiciones daba negativo (ver docstring del módulo)


@dataclass(frozen=True)
class CalendarioDeuda:
    parametros: ParametrosCalendarioDeuda
    vencimientos_por_año: dict[int, dict[str, TramosVencimiento]] = field(default_factory=dict)
    movimientos_por_año: dict[int, dict[str, MovimientoCategoria]] = field(default_factory=dict)


def _sortear_parametros(sector: str, segmento: str, semilla: int) -> ParametrosCalendarioDeuda:
    rng_ec = np.random.default_rng([semilla, _entropia_calendario(sector, segmento, "_entidades_credito")])
    lo, hi = RANGO_PLAZO_REMANENTE_ENTIDADES_CREDITO_AÑOS
    plazo_ec = int(rng_ec.integers(lo, hi + 1))

    rng_otros = np.random.default_rng([semilla, _entropia_calendario(sector, segmento, "_otros_pasivos_financieros")])
    lo, hi = RANGO_PLAZO_REMANENTE_OTROS_PASIVOS_FINANCIEROS_AÑOS
    plazo_otros = int(rng_otros.integers(lo, hi + 1))

    rng_ob = np.random.default_rng([semilla, _entropia_calendario(sector, segmento, "_obligaciones")])
    lo, hi = RANGO_AÑO_VENCIMIENTO_OBLIGACIONES
    año_vencimiento_ob = int(rng_ob.integers(lo, hi + 1))

    rng_inm = np.random.default_rng([semilla, _entropia_calendario(sector, segmento, "_acreedores_inmovilizado")])
    lo, hi = RANGO_PLAZO_ACREEDORES_INMOVILIZADO_AÑOS
    plazo_inm = int(rng_inm.integers(lo, hi + 1))

    return ParametrosCalendarioDeuda(
        plazo_remanente_entidades_credito_años=plazo_ec,
        plazo_remanente_otros_pasivos_financieros_años=plazo_otros,
        año_vencimiento_obligaciones=año_vencimiento_ob,
        plazo_acreedores_inmovilizado_años=plazo_inm,
    )


def _reparto_lineal(monto_largo_eur: float, plazo_remanente_años: float) -> TramosVencimiento:
    """Amortización lineal (cuotas anuales iguales) del importe a largo plazo entre los años 2 y
    `plazo_remanente_años` (ambos inclusive) — los años > 5 se acumulan en "más de 5". Usado por
    "entidades de crédito", "otros pasivos financieros", "remanente" (otras deudas) y "derivados"
    (ver `_reparto_derivados`, caso especial de este mismo mecanismo en un único tramo si el plazo
    residual real del swap ya es conocido). `plazo_remanente_años` se clampa a un mínimo de 2 —
    todo lo que sea a un año ya está clasificado en `un_año` (saldo a corto plazo del Balance, no
    parte del largo que reparte esta función)."""
    plazo = max(plazo_remanente_años, 2)
    n_cuotas = plazo - 1
    cuota = monto_largo_eur / n_cuotas
    tramos = {"dos": 0.0, "tres": 0.0, "cuatro": 0.0, "cinco": 0.0, "mas_de_cinco": 0.0}
    nombre_por_año = {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco"}
    for año_relativo in range(2, int(plazo) + 1):
        clave = nombre_por_año.get(año_relativo, "mas_de_cinco")
        tramos[clave] += cuota
    return tramos


def _reparto_bullet(monto_largo_eur: float, año_vencimiento_relativo: float) -> dict[str, float]:
    """Todo el importe a largo plazo vence en UN solo tramo — usado por "obligaciones" (bullet
    real, sin amortización periódica) y por "derivados" (el valor razonable del swap vence de
    golpe con el contrato, no se amortiza por cuotas)."""
    año = max(año_vencimiento_relativo, 2)
    tramos = {"dos": 0.0, "tres": 0.0, "cuatro": 0.0, "cinco": 0.0, "mas_de_cinco": 0.0}
    nombre_por_año = {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco"}
    clave = nombre_por_año.get(int(año), "mas_de_cinco")
    tramos[clave] = monto_largo_eur
    return tramos


def _reparto_sin_vencimiento_cierto(monto_largo_eur: float) -> dict[str, float]:
    """Fianzas/depósitos recibidos y deudas con socios y administradores — sin vencimiento
    contractual cierto (ver Diseño 1 del encargo): convención documentada, todo el importe a
    "más de 5 años"."""
    return {"dos": 0.0, "tres": 0.0, "cuatro": 0.0, "cinco": 0.0, "mas_de_cinco": monto_largo_eur}


def _tramos(un_año_eur: float, reparto_largo: dict[str, float]) -> TramosVencimiento:
    return TramosVencimiento(
        un_año=un_año_eur,
        dos=reparto_largo["dos"],
        tres=reparto_largo["tres"],
        cuatro=reparto_largo["cuatro"],
        cinco=reparto_largo["cinco"],
        mas_de_cinco=reparto_largo["mas_de_cinco"],
    )


def _vencimientos_de_un_año(evolucion: EvolucionArquetipo, año: int, parametros: ParametrosCalendarioDeuda) -> dict[str, TramosVencimiento]:
    ej = evolucion.ejercicios[año]
    dfl = ej.deudas_fin_largo_desglose_eur
    dfc = ej.deudas_fin_corto_desglose_eur
    odl = ej.otras_deudas_largo_desglose_eur
    odc = ej.otras_deudas_corto_desglose_eur

    plazo_remanente_arrendamiento = PLAZO_REMANENTE_ARRENDAMIENTO_AÑOS - (año - AÑO_BASE)

    resultado: dict[str, TramosVencimiento] = {}
    resultado["entidades_credito"] = _tramos(
        dfc.get("entidades_credito", 0.0),
        _reparto_lineal(dfl.get("entidades_credito", 0.0), parametros.plazo_remanente_entidades_credito_años),
    )
    resultado["arrendamiento_financiero"] = _tramos(
        dfc.get("arrendamiento_financiero", 0.0),
        _reparto_lineal(dfl.get("arrendamiento_financiero", 0.0), plazo_remanente_arrendamiento),
    )
    resultado["obligaciones"] = _tramos(
        dfc.get("obligaciones", 0.0),
        _reparto_bullet(dfl.get("obligaciones", 0.0), parametros.año_vencimiento_obligaciones - (año - AÑO_BASE)),
    )
    resultado["otros_pasivos_financieros"] = _tramos(
        dfc.get("otros_pasivos_financieros", 0.0),
        _reparto_lineal(dfl.get("otros_pasivos_financieros", 0.0), parametros.plazo_remanente_otros_pasivos_financieros_años),
    )
    resultado["derivados"] = _tramos(
        dfc.get("derivados", 0.0),
        _reparto_bullet(dfl.get("derivados", 0.0), ej.cobertura_plazo_residual_años),
    )
    resultado["acreedores_inmovilizado"] = _tramos(
        odc.get("acreedores_inmovilizado", 0.0),
        _reparto_lineal(odl.get("acreedores_inmovilizado", 0.0), parametros.plazo_acreedores_inmovilizado_años),
    )
    resultado["fianzas_deudas_socios"] = _tramos(
        odc.get("fianzas_depositos", 0.0),
        _reparto_sin_vencimiento_cierto(odl.get("fianzas_depositos", 0.0) + odl.get("deudas_socios", 0.0)),
    )
    resultado["remanente_otras_deudas"] = _tramos(
        odc.get("remanente", 0.0),
        _reparto_lineal(odl.get("remanente", 0.0), parametros.plazo_remanente_entidades_credito_años),
    )
    resultado["acreedores_comerciales"] = _tramos(
        ej.balance_eur.get("acreedores_comerciales", 0.0),
        {"dos": 0.0, "tres": 0.0, "cuatro": 0.0, "cinco": 0.0, "mas_de_cinco": 0.0},
    )
    return resultado


CATEGORIAS_DEUDA_FINANCIERA = ("entidades_credito", "obligaciones", "arrendamiento_financiero", "otros_pasivos_financieros", "derivados")
CATEGORIAS_DEUDA_FINANCIERA_CON_COSTE = ("entidades_credito", "obligaciones", "arrendamiento_financiero", "otros_pasivos_financieros")
CATEGORIAS_RUN_OFF = ("arrendamiento_financiero", "obligaciones")


def _saldo_categoria(ej, categoria: str) -> float:
    return ej.deudas_fin_largo_desglose_eur.get(categoria, 0.0) + ej.deudas_fin_corto_desglose_eur.get(categoria, 0.0)


def _movimiento_categoria(categoria: str, ej_anterior, ej_actual) -> MovimientoCategoria:
    saldo_inicial = _saldo_categoria(ej_anterior, categoria)
    saldo_final = _saldo_categoria(ej_actual, categoria)
    cancelacion_anticipada = False

    if categoria in CATEGORIAS_RUN_OFF:
        amortizaciones = max(0.0, saldo_inicial - saldo_final)
        disposiciones = max(0.0, saldo_final - saldo_inicial)
    else:
        corto_anterior = ej_anterior.deudas_fin_corto_desglose_eur.get(categoria, 0.0)
        amortizaciones = min(corto_anterior, saldo_inicial)
        disposiciones = saldo_final - saldo_inicial + amortizaciones
        if disposiciones < 0:
            cancelacion_anticipada = True
            amortizaciones = saldo_inicial - saldo_final
            disposiciones = 0.0

    return MovimientoCategoria(
        categoria=categoria,
        saldo_inicial_eur=saldo_inicial,
        amortizaciones_eur=amortizaciones,
        disposiciones_eur=disposiciones,
        saldo_final_eur=saldo_inicial - amortizaciones + disposiciones,
        cancelacion_anticipada=cancelacion_anticipada,
    )


def calcular_calendario_deuda(evolucion: EvolucionArquetipo) -> CalendarioDeuda:
    """Punto de entrada único del módulo — deriva el calendario completo (clasificación por
    vencimientos de los 3 ejercicios + cuadro de movimientos de 2024 y 2025) de un caso YA
    generado. No modifica `evolucion` ni ninguno de sus `EjercicioEmpresa` — solo LEE."""
    parametros = _sortear_parametros(evolucion.sector_codigo, evolucion.segmento, evolucion.semilla)

    vencimientos_por_año = {año: _vencimientos_de_un_año(evolucion, año, parametros) for año in AÑOS}

    movimientos_por_año: dict[int, dict[str, MovimientoCategoria]] = {}
    for año in (2024, 2025):
        ej_anterior = evolucion.ejercicios[año - 1]
        ej_actual = evolucion.ejercicios[año]
        movimientos_por_año[año] = {
            categoria: _movimiento_categoria(categoria, ej_anterior, ej_actual)
            for categoria in CATEGORIAS_DEUDA_FINANCIERA
        }

    return CalendarioDeuda(
        parametros=parametros,
        vencimientos_por_año=vencimientos_por_año,
        movimientos_por_año=movimientos_por_año,
    )
