"""Motor mínimo: genera el balance y la PyG base de una empresa a partir del catálogo
sectorial, con variabilidad realista entre empresas de un mismo sector.

Sin arquetipos, sin serie de tres años, sin EFE: un único ejercicio, coherente y cuadrado.

**Semilla del generador aleatorio.** `rng` se siembra con `semilla` MEZCLADA con un hash
estable (`zlib.crc32`, no `hash()` de Python — este varía entre procesos por PYTHONHASHSEED,
rompería la reproducibilidad) de `sector+segmento`, no con `semilla` a secas. Sembrar solo con
`semilla` (como hacía la primera versión) dejaba a CUALQUIER sector/segmento con el mismo
número de semilla partiendo del MISMO estado de `rng` — y como el modo típico/atípico y el
valor z de cada partida (`_generar_partida`/`_normal_truncada`) no dependen de huber/mad, solo
su escalado posterior sí, la secuencia de sorteos consumida era, en la práctica, IDÉNTICA entre
sectores distintos que compartieran semilla (verificado: el z de `rotacion_activo` coincidía
hasta 1e-9 entre dos sectores cualesquiera con la misma semilla) — se corrigió tras una
auditoría pedida explícitamente al encontrar el mismo patrón en el sorteo de `nota_memoria` de
`motor.evolucion_arquetipo`. La intensidad NO se mezcla aquí (no aplica: esta función no la
conoce) ni en la semilla equivalente de `motor.evolucion_arquetipo.generar_evolucion_arquetipo`
— por diseño, la misma semilla+sector+segmento con intensidades distintas debe compartir el
mismo "ruido de fondo" de la empresa (ver docstring de ese módulo), solo el propio empuje del
arquetipo varía con la intensidad.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from motor.amortizacion import AÑO_BASE as _AÑO_BASE_AMORTIZACION
from motor.amortizacion import amortizacion_eur_del_año, generar_coleccion_y_perfiles_base
from motor.catalogo import cargar_y_validar_catalogo
# Reexportados (no solo usados aquí): otros módulos (p. ej. motor/clasificacion_legal.py,
# motor/amortizacion.py) los importan como motor.empresa_base.<nombre> — mover la definición a
# motor/ruido.py (para que motor/amortizacion.py pueda reutilizarlos sin crear una importación
# circular con este módulo) no les obliga a cambiar su propio import.
from motor.ruido import (  # noqa: F401
    DESVIACIONES_ATIPICO,
    DESVIACIONES_TIPICO,
    PROB_ATIPICO,
    _generar_partida,
    _normal_truncada,
    _renormalizar_a_total,
)

SEGMENTOS_VALIDOS = frozenset({"grandes_medianas", "pequeñas"})

TOLERANCIA_CUADRE_EUR = 0.01
SUELO_PORCENTAJE = 0.01
SUELO_ROTACION_ACTIVO = 0.05
SUELO_TIPO_INTERES = 0.01  # 1%: floor defensivo, evita coste de deuda nulo o negativo
TECHO_TIPO_INTERES = 0.40  # 40%: techo defensivo frente a sectores con MAD grande

# Nombre de salida -> nombre de variable en el catálogo (prefijo "balance.")
MASAS_BALANCE = {
    "activo_no_corriente": "activo_no_corriente",
    "activo_corriente": "activo_corriente",
    "existencias": "existencias_pct",
    "realizable": "realizable_pct",
    "disponible": "disponible_pct",
    "patrimonio_neto": "patrimonio_neto_pct",
    "pasivo_no_corriente": "pasivo_no_corriente_pct",
    "deudas_fin_largo": "deudas_fin_largo_pct",
    "otras_deudas_largo": "otras_deudas_largo_pct",
    "pasivo_corriente": "pasivo_corriente_pct",
    "acreedores_comerciales": "acreedores_comerciales_pct",
    "deudas_fin_corto": "deudas_fin_corto_pct",
    "otras_deudas_corto": "otras_deudas_corto_pct",
}

# Partidas primitivas de la PyG (ruido) -> nombre de variable en el catálogo (prefijo "pyg.").
# "gastos_financieros" NO está aquí: se calcula (deuda financiera media x tipo de interés),
# no se sortea como % independiente — ver _generar_pyg_hasta_baii/_completar_pyg_con_deuda.
PRIMITIVAS_PYG = {
    "cifra_negocios": "cifra_negocios_pct",
    "otros_ingresos_explot": "otros_ingresos_explot_pct",
    "consumos_explotacion": "consumos_explotacion_pct",
    "otros_gastos_explot": "otros_gastos_explot_pct",
    "gastos_personal": "gastos_personal_pct",
    "amortizaciones": "amortizaciones_pct",
    "resultado_extraordinario": "resultado_extraordinario_pct",
    "ingresos_financieros": "ingresos_financieros_pct",
    "impuesto_beneficios": "impuesto_beneficios_pct",
}

# Primitivas de PyG que no pueden ser negativas (importes de ingreso/gasto en sí mismos).
# resultado_extraordinario e impuesto_beneficios sí pueden serlo (crédito fiscal, extraordinario
# negativo): el propio catálogo tiene valores Huber negativos para ambas en algunos sectores.
PRIMITIVAS_PYG_NO_NEGATIVAS = frozenset(PRIMITIVAS_PYG) - {"resultado_extraordinario", "impuesto_beneficios"}

SUBTOTALES_PYG = ("ingresos_explotacion", "margen_bruto", "valor_añadido", "baii", "bai", "resultado_ejercicio")

_RE_CODIGO_SECTOR = re.compile(r"\(([^()]+)\)\s*$")

# --------------------------------------------------------------------------------------------
# Desagregación de patrimonio neto (Capital / Reservas y resultados de ejercicios anteriores /
# Resultado del ejercicio) — HIPÓTESIS DE DISEÑO, no un dato del catálogo ACCID (que solo da el
# agregado `patrimonio_neto_pct`). El capital social es un atributo de la EMPRESA, fijado una
# única vez al generar el año base (2023) y constante en 2024/2025 — no varía porque cambien los
# resultados anuales, igual que en la realidad (una ampliación/reducción de capital es un hecho
# discreto, no algo que este motor modela). Las reservas se derivan por resta, no son una fuente
# de ruido propia: reservas(t) = PN(t) - capital_social - resultado_del_ejercicio(t).
# --------------------------------------------------------------------------------------------
CAPITAL_SOCIAL_FRACCION_PN_CENTRO = 0.40
CAPITAL_SOCIAL_FRACCION_PN_SPREAD = 0.06
CAPITAL_SOCIAL_FRACCION_PN_SUELO = 0.30
CAPITAL_SOCIAL_FRACCION_PN_TECHO = 0.50

# --------------------------------------------------------------------------------------------
# Desagregación de `activo_no_corriente` (material / intangible / inversiones inmobiliarias /
# otros activos financieros) — HIPÓTESIS DE DISEÑO, no un dato del catálogo ACCID (que nunca
# desglosó activo_no_corriente más allá del agregado). Necesaria para poder rellenar el desglose
# de inversión que exige el modelo oficial del EFE (sección B). Perfil por CATEGORÍA de sector
# (las 8 categorías de la sección 2.22 del documento de especificaciones), no un único reparto
# para los 27 sectores — cada perfil suma exactamente 1.0. El salto de activo del arquetipo 18
# (adquisición) se mantiene aparte de este reparto, ver `motor/efe.py`.
# --------------------------------------------------------------------------------------------
CATEGORIA_SECTOR: dict[str, str] = {
    # Industria (9)
    "24.1": "industria", "29": "industria", "10.1": "industria", "20.1": "industria",
    "28": "industria", "30.3": "industria", "30.2": "industria", "19": "industria", "35.1": "industria",
    # Servicios industriales (4)
    "33.1": "servicios_industriales", "33.2": "servicios_industriales",
    "71": "servicios_industriales", "72": "servicios_industriales",
    # Servicios profesionales / TIC (3) — sub-divididos en dos PERFILES (no dos bloques nuevos
    # de la sección 2.22, que se mantiene en 8 bloques a efectos del catálogo de sectores): el
    # perfil de `activo_no_corriente` de contabilidad/auditoría/consultoría (69.2/70.2) resultó
    # muy distinto del de programación/TIC (62) — ver decisiones_plausibilidad.md #29/#33.
    "69.2": "servicios_profesionales", "70.2": "servicios_profesionales", "62": "servicios_tic",
    # Transporte y logística (2)
    "52": "transporte_logistica", "4941": "transporte_logistica",
    # Comercio y hostelería (4)
    "47.1": "comercio_hosteleria", "46": "comercio_hosteleria",
    "56.1": "comercio_hosteleria", "55.1": "comercio_hosteleria",
    # Construcción (2)
    "41.2": "construccion", "43.2": "construccion",
    # Administración, educación y sanidad (2)
    "85": "administracion_educacion_sanidad", "86.1": "administracion_educacion_sanidad",
    # Inmobiliario (1)
    "68": "inmobiliario",
}

# Cada perfil suma exactamente 1.0. Criterio contable orientativo (documentado como hipótesis,
# no dato ACCID): sectores intensivos en capital físico (industria, transporte, comercio,
# construcción, administración/sanidad) llevan `material` dominante; servicios profesionales/TIC
# invierten más en intangible (software, patentes, fondo de comercio); inmobiliario lleva
# `inversiones_inmobiliarias` dominante por definición del propio sector.
PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "industria": {"material": 0.80, "intangible": 0.10, "inversiones_inmobiliarias": 0.02, "otros_financieros": 0.08},
    "servicios_industriales": {"material": 0.55, "intangible": 0.25, "inversiones_inmobiliarias": 0.03, "otros_financieros": 0.17},
    # Contabilidad/auditoría/consultoría (69.2/70.2): pese a ser "servicios profesionales", el
    # activo_no_corriente típico de estos 2 sectores en el catálogo es MUY grande respecto a sus
    # ingresos (rotacion_activo inusualmente baja, ~0,28-0,30 — activo_no_corriente 2,5-2,8x los
    # ingresos, ver decisiones #29). No es plausible que una consultora tenga ese volumen de
    # activo en oficinas/software: lo más razonable es que la mayor parte sea PARTICIPACIONES/
    # inversiones financieras (estructuras de holding, habituales en redes de auditoría/
    # consultoría con oficinas asociadas) — `otros_financieros` dominante, material e intangible
    # bajos. Ver #33 para la verificación cuantificada de que esto corrige el hallazgo #29.
    "servicios_profesionales": {"material": 0.15, "intangible": 0.15, "inversiones_inmobiliarias": 0.05, "otros_financieros": 0.65},
    # Programación/consultoría informática (62): el sector "TIC" propiamente dicho — aquí sí
    # tiene sentido un intangible alto (software propio, propiedad intelectual) — y su rotacion_
    # activo en el catálogo ya era razonable (no mostraba el mismo problema que 69.2/70.2).
    "servicios_tic": {"material": 0.20, "intangible": 0.50, "inversiones_inmobiliarias": 0.03, "otros_financieros": 0.27},
    "transporte_logistica": {"material": 0.80, "intangible": 0.08, "inversiones_inmobiliarias": 0.04, "otros_financieros": 0.08},
    "comercio_hosteleria": {"material": 0.75, "intangible": 0.10, "inversiones_inmobiliarias": 0.05, "otros_financieros": 0.10},
    "construccion": {"material": 0.70, "intangible": 0.05, "inversiones_inmobiliarias": 0.05, "otros_financieros": 0.20},
    "administracion_educacion_sanidad": {"material": 0.75, "intangible": 0.15, "inversiones_inmobiliarias": 0.02, "otros_financieros": 0.08},
    "inmobiliario": {"material": 0.10, "intangible": 0.03, "inversiones_inmobiliarias": 0.80, "otros_financieros": 0.07},
}

# Dispersión sintética (no hay MAD del catálogo para esto) aplicada a cada componente del
# perfil antes de renormalizar a 100% — evita que dos empresas del mismo sector salgan con el
# reparto idéntico, sin cambiar el perfil CENTRAL de la categoría.
DISPERSION_PERFIL_ACTIVO_NO_CORRIENTE = 0.20  # fracción relativa del propio valor del componente
SUELO_COMPONENTE_ACTIVO_NO_CORRIENTE_PCT = 0.005  # 0,5%: evita un componente en cero o negativo


def categoria_de_sector(sector_codigo: str) -> str:
    if sector_codigo not in CATEGORIA_SECTOR:
        raise EmpresaBaseError(f"Sector '{sector_codigo}' no tiene categoría asignada en CATEGORIA_SECTOR.")
    return CATEGORIA_SECTOR[sector_codigo]


def _redondear_cifra_vistosa(valor: float) -> float:
    """Redondea a una cifra de aspecto realista para capital social (los importes reales suelen
    ser números redondos: 60.000€, 3.000.000€, no 2.847.193,17€) — redondeo a 2 cifras
    significativas."""
    if valor <= 0:
        return 0.0
    import math

    magnitud = 10 ** math.floor(math.log10(valor))
    paso = magnitud / 10
    return round(valor / paso) * paso


def _generar_capital_social(rng: np.random.Generator, patrimonio_neto_eur: float) -> float:
    fraccion, _ = _generar_partida(
        rng,
        CAPITAL_SOCIAL_FRACCION_PN_CENTRO,
        CAPITAL_SOCIAL_FRACCION_PN_SPREAD,
        suelo=CAPITAL_SOCIAL_FRACCION_PN_SUELO,
        techo=CAPITAL_SOCIAL_FRACCION_PN_TECHO,
    )
    return _redondear_cifra_vistosa(max(0.0, patrimonio_neto_eur) * fraccion)


def generar_perfil_activo_no_corriente(rng: np.random.Generator, categoria: str) -> dict[str, float]:
    """Las 4 fracciones (material/intangible/inversiones_inmobiliarias/otros_financieros) para
    UN caso — sorteo único por empresa (no por año), con ruido alrededor del perfil central de
    su categoría de sector, renormalizado para sumar exactamente 1.0."""
    perfil_centro = PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA[categoria]
    brutos = {}
    for componente, centro in perfil_centro.items():
        valor, _ = _generar_partida(
            rng, centro, centro * DISPERSION_PERFIL_ACTIVO_NO_CORRIENTE,
            suelo=SUELO_COMPONENTE_ACTIVO_NO_CORRIENTE_PCT,
        )
        brutos[componente] = valor
    return _renormalizar_a_total(brutos, 1.0)


class EmpresaBaseError(ValueError):
    """Parámetros de entrada inválidos o sector/segmento no encontrado en el catálogo."""


@dataclass(frozen=True)
class EmpresaBase:
    sector_codigo: str
    sector_nombre: str
    segmento: str
    ventas_objetivo: float
    semilla: int
    rotacion_activo: float
    activo_total_eur: float
    balance_pct: dict[str, float]
    balance_eur: dict[str, float]
    pyg_pct: dict[str, float]
    pyg_eur: dict[str, float]
    modos: dict[str, str] = field(repr=False)
    ajuste_cuadre_eur: float = 0.0
    capital_social_eur: float = 0.0
    reservas_eur: float = 0.0
    activo_no_corriente_perfil_pct: dict[str, float] = field(default_factory=dict)
    activo_no_corriente_desglose_eur: dict[str, float] = field(default_factory=dict)
    # Amortización derivada de una colección real de activos (ver motor/amortizacion.py) — la
    # colección en sí (para evolucionarla año a año) y los perfiles de sub-tipo ya sorteados
    # (para que el arquetipo 18 -adquisición- pueda reutilizarlos sin volver a sortear "el
    # perfil completo de la categoría").
    coleccion_activos_amortizables: tuple = ()
    perfil_subtipos_material_pct: dict[str, float] = field(default_factory=dict)
    perfil_subtipos_intangible_pct: dict[str, float] = field(default_factory=dict)


def _mapa_codigo_sector(catalogo: pd.DataFrame) -> dict[str, str]:
    mapa: dict[str, str] = {}
    for nombre in catalogo["sector"].unique():
        match = _RE_CODIGO_SECTOR.search(nombre)
        if match:
            mapa[match.group(1)] = nombre
    return mapa


def resolver_fila_sector(catalogo: pd.DataFrame, sector_codigo: str, segmento: str) -> pd.Series:
    """Resuelve la fila del catálogo (huber_9y, huber_scale_mad, ...) para un sector/segmento.

    `sector_codigo` es el código entre paréntesis del catálogo (p. ej. "24.1", "4941").
    """
    if segmento not in SEGMENTOS_VALIDOS:
        raise EmpresaBaseError(f"Segmento '{segmento}' no válido. Debe ser uno de: {sorted(SEGMENTOS_VALIDOS)}")

    mapa_codigos = _mapa_codigo_sector(catalogo)
    if sector_codigo not in mapa_codigos:
        raise EmpresaBaseError(
            f"Sector '{sector_codigo}' no reconocido. Códigos disponibles: {sorted(mapa_codigos)}"
        )
    sector_nombre = mapa_codigos[sector_codigo]

    filas = catalogo[(catalogo["sector"] == sector_nombre) & (catalogo["segmento"] == segmento)]
    if len(filas) != 1:
        raise EmpresaBaseError(
            f"Se esperaba exactamente 1 fila para ({sector_nombre!r}, {segmento!r}) y hay {len(filas)}."
        )
    return filas.iloc[0]


def _generar_balance_pct(
    rng: np.random.Generator, fila: pd.Series
) -> tuple[dict[str, float], dict[str, str]]:
    brutos: dict[str, float] = {}
    modos: dict[str, str] = {}
    for nombre_salida, variable in MASAS_BALANCE.items():
        huber = fila[f"balance.{variable}.huber_9y"]
        mad = fila[f"balance.{variable}.huber_scale_mad"]
        valor, modo = _generar_partida(rng, huber, mad, suelo=SUELO_PORCENTAJE)
        brutos[nombre_salida] = valor
        modos[f"balance.{nombre_salida}"] = modo

    nivel1_activo = _renormalizar_a_total(
        {k: brutos[k] for k in ("activo_no_corriente", "activo_corriente")}, 100.0
    )
    nivel1_pasivo = _renormalizar_a_total(
        {k: brutos[k] for k in ("patrimonio_neto", "pasivo_no_corriente", "pasivo_corriente")}, 100.0
    )
    nivel2_activo_corriente = _renormalizar_a_total(
        {k: brutos[k] for k in ("existencias", "realizable", "disponible")},
        nivel1_activo["activo_corriente"],
    )
    nivel2_pasivo_no_corriente = _renormalizar_a_total(
        {k: brutos[k] for k in ("deudas_fin_largo", "otras_deudas_largo")},
        nivel1_pasivo["pasivo_no_corriente"],
    )
    nivel2_pasivo_corriente = _renormalizar_a_total(
        {k: brutos[k] for k in ("acreedores_comerciales", "deudas_fin_corto", "otras_deudas_corto")},
        nivel1_pasivo["pasivo_corriente"],
    )

    balance_pct = {
        **nivel1_activo,
        **nivel1_pasivo,
        **nivel2_activo_corriente,
        **nivel2_pasivo_no_corriente,
        **nivel2_pasivo_corriente,
    }
    return balance_pct, modos


@dataclass(frozen=True)
class _PygParcial:
    """Cascada de PyG calculada hasta BAII (no depende de la deuda financiera)."""

    ingresos_explotacion_eur: float
    cifra_negocios_eur: float
    otros_ingresos_explot_eur: float
    consumos_explotacion_eur: float
    margen_bruto_eur: float
    otros_gastos_explot_eur: float
    valor_añadido_eur: float
    gastos_personal_eur: float
    amortizaciones_eur: float
    resultado_extraordinario_eur: float
    baii_eur: float
    ingresos_financieros_eur: float
    impuesto_beneficios_eur: float
    tipo_interes: float
    modos: dict[str, str]


def _generar_pyg_hasta_baii(
    rng: np.random.Generator,
    fila: pd.Series,
    ventas_objetivo: float,
    primitivas_forzadas: dict[str, float] | None = None,
    amortizaciones_eur: float | None = None,
) -> _PygParcial:
    """Sortea las primitivas de la PyG que no dependen de deuda, y el tipo de interés del
    ejercicio (mismo mecanismo típico/atípico que el resto de partidas, anclado a
    ratios.coste_deuda del sector). No calcula gastos financieros ni nada de BAI en adelante:
    eso depende de la deuda financiera media del ejercicio, que en `evolucion_arquetipo` no se
    conoce hasta después de decidir si hay contención de endeudamiento.

    `primitivas_forzadas`: para un arquetipo con efecto "pyg_primitiva" (p. ej. mejora de
    margen sobre consumos_explotacion_pct), el valor ya calculado con continuidad respecto al
    año anterior — sustituye el sorteo de esa partida en concreto. Se registra con modo
    "arquetipo" en vez de "tipico"/"atipico" (no es ruido, es el efecto del arquetipo).

    `amortizaciones_eur`: OBLIGATORIO en la práctica desde que la amortización dejó de sortearse
    como % independiente (ver `motor/amortizacion.py`) — el gasto ya calculado a partir de la
    colección real de activos del caso, en EUROS (no en %, a diferencia de `primitivas_forzadas`:
    la conversión a % requeriría conocer `ingresos_explotacion_eur`, que todavía no está
    calculado en este punto — ver más abajo). "amortizaciones" se excluye del sorteo/bucle de
    primitivas en ese caso (no consume ningún draw de `rng`) y su modo queda registrado como
    "derivado".
    """
    primitivas_forzadas = primitivas_forzadas or {}
    brutos: dict[str, float] = {}
    modos: dict[str, str] = {}
    for nombre_salida, variable in PRIMITIVAS_PYG.items():
        if nombre_salida == "amortizaciones" and amortizaciones_eur is not None:
            modos[f"pyg.{nombre_salida}"] = "derivado"
            continue
        if nombre_salida in primitivas_forzadas:
            brutos[nombre_salida] = primitivas_forzadas[nombre_salida]
            modos[f"pyg.{nombre_salida}"] = "arquetipo"
            continue
        huber = fila[f"pyg.{variable}.huber_9y"]
        mad = fila[f"pyg.{variable}.huber_scale_mad"]
        suelo = SUELO_PORCENTAJE if nombre_salida in PRIMITIVAS_PYG_NO_NEGATIVAS else None
        valor, modo = _generar_partida(rng, huber, mad, suelo=suelo)
        brutos[nombre_salida] = valor
        modos[f"pyg.{nombre_salida}"] = modo

    tipo_interes, modo_tipo_interes = _generar_partida(
        rng,
        fila["ratios.coste_deuda.huber_9y"],
        fila["ratios.coste_deuda.huber_scale_mad"],
        suelo=SUELO_TIPO_INTERES,
        techo=TECHO_TIPO_INTERES,
    )
    modos["pyg.tipo_interes"] = modo_tipo_interes

    cifra_negocios_eur = ventas_objetivo
    otros_ingresos_explot_eur = cifra_negocios_eur * (
        brutos["otros_ingresos_explot"] / brutos["cifra_negocios"]
    )
    ingresos_explotacion_eur = cifra_negocios_eur + otros_ingresos_explot_eur

    consumos_explotacion_eur = brutos["consumos_explotacion"] / 100 * ingresos_explotacion_eur
    otros_gastos_explot_eur = brutos["otros_gastos_explot"] / 100 * ingresos_explotacion_eur
    gastos_personal_eur = brutos["gastos_personal"] / 100 * ingresos_explotacion_eur
    amortizaciones_eur_final = (
        amortizaciones_eur if amortizaciones_eur is not None else brutos["amortizaciones"] / 100 * ingresos_explotacion_eur
    )
    resultado_extraordinario_eur = brutos["resultado_extraordinario"] / 100 * ingresos_explotacion_eur
    ingresos_financieros_eur = brutos["ingresos_financieros"] / 100 * ingresos_explotacion_eur
    impuesto_beneficios_eur = brutos["impuesto_beneficios"] / 100 * ingresos_explotacion_eur

    margen_bruto_eur = ingresos_explotacion_eur - consumos_explotacion_eur
    valor_añadido_eur = margen_bruto_eur - otros_gastos_explot_eur
    baii_eur = valor_añadido_eur - gastos_personal_eur - amortizaciones_eur_final + resultado_extraordinario_eur

    return _PygParcial(
        ingresos_explotacion_eur=ingresos_explotacion_eur,
        cifra_negocios_eur=cifra_negocios_eur,
        otros_ingresos_explot_eur=otros_ingresos_explot_eur,
        consumos_explotacion_eur=consumos_explotacion_eur,
        margen_bruto_eur=margen_bruto_eur,
        otros_gastos_explot_eur=otros_gastos_explot_eur,
        valor_añadido_eur=valor_añadido_eur,
        gastos_personal_eur=gastos_personal_eur,
        amortizaciones_eur=amortizaciones_eur_final,
        resultado_extraordinario_eur=resultado_extraordinario_eur,
        baii_eur=baii_eur,
        ingresos_financieros_eur=ingresos_financieros_eur,
        impuesto_beneficios_eur=impuesto_beneficios_eur,
        tipo_interes=tipo_interes,
        modos=modos,
    )


def _completar_pyg_con_deuda(
    parcial: _PygParcial, deuda_financiera_media_eur: float
) -> tuple[dict[str, float], dict[str, float]]:
    """Termina la cascada (BAI y resultado del ejercicio) usando la deuda financiera media
    (largo + corto plazo, promedio inicio/fin del ejercicio) para calcular gastos financieros
    = deuda financiera media x tipo de interés del sector."""
    gastos_financieros_eur = deuda_financiera_media_eur * parcial.tipo_interes
    bai_eur = parcial.baii_eur + parcial.ingresos_financieros_eur - gastos_financieros_eur
    resultado_ejercicio_eur = bai_eur - parcial.impuesto_beneficios_eur

    pyg_eur = {
        "cifra_negocios": parcial.cifra_negocios_eur,
        "otros_ingresos_explot": parcial.otros_ingresos_explot_eur,
        "ingresos_explotacion": parcial.ingresos_explotacion_eur,
        "consumos_explotacion": parcial.consumos_explotacion_eur,
        "margen_bruto": parcial.margen_bruto_eur,
        "otros_gastos_explot": parcial.otros_gastos_explot_eur,
        "valor_añadido": parcial.valor_añadido_eur,
        "gastos_personal": parcial.gastos_personal_eur,
        "amortizaciones": parcial.amortizaciones_eur,
        "resultado_extraordinario": parcial.resultado_extraordinario_eur,
        "baii": parcial.baii_eur,
        "ingresos_financieros": parcial.ingresos_financieros_eur,
        "gastos_financieros": gastos_financieros_eur,
        "bai": bai_eur,
        "impuesto_beneficios": parcial.impuesto_beneficios_eur,
        "resultado_ejercicio": resultado_ejercicio_eur,
    }
    pyg_pct = {k: v / parcial.ingresos_explotacion_eur * 100 for k, v in pyg_eur.items()}
    return pyg_pct, pyg_eur


def generar_empresa_base(
    sector: str,
    segmento: str,
    ventas_objetivo: float,
    semilla: int,
    catalogo: pd.DataFrame | None = None,
) -> EmpresaBase:
    """Genera el balance y la PyG base (un ejercicio, sin arquetipos) de una empresa ficticia.

    `sector` es el código entre paréntesis del catálogo (p. ej. "24.1", "4941"). `segmento` es
    "grandes_medianas" o "pequeñas". El resultado es reproducible: misma semilla+sector+segmento,
    mismo caso (ver docstring del módulo sobre por qué la semilla del RNG mezcla sector+segmento,
    no solo `semilla`)."""
    if segmento not in SEGMENTOS_VALIDOS:
        raise EmpresaBaseError(f"Segmento '{segmento}' no válido. Debe ser uno de: {sorted(SEGMENTOS_VALIDOS)}")
    if ventas_objetivo <= 0:
        raise EmpresaBaseError(f"ventas_objetivo debe ser positivo, recibido: {ventas_objetivo}")

    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    fila = resolver_fila_sector(catalogo, sector, segmento)
    sector_nombre = fila["sector"]

    entropia_caso = zlib.crc32(f"{sector}|{segmento}".encode("utf-8"))
    rng = np.random.default_rng([semilla, entropia_caso])

    balance_pct, modos_balance = _generar_balance_pct(rng, fila)

    rotacion_activo, modo_rotacion = _generar_partida(
        rng,
        fila["ratios.rotacion_activo.huber_9y"],
        fila["ratios.rotacion_activo.huber_scale_mad"],
        suelo=SUELO_ROTACION_ACTIVO,
    )
    activo_total_eur = ventas_objetivo / rotacion_activo

    balance_eur = {clave: valor / 100 * activo_total_eur for clave, valor in balance_pct.items()}

    activo_eur = balance_eur["activo_no_corriente"] + balance_eur["activo_corriente"]
    pn_pasivo_eur = (
        balance_eur["patrimonio_neto"] + balance_eur["pasivo_no_corriente"] + balance_eur["pasivo_corriente"]
    )
    diferencia_cuadre = activo_eur - pn_pasivo_eur
    ajuste_cuadre_eur = 0.0
    if abs(diferencia_cuadre) > TOLERANCIA_CUADRE_EUR:
        balance_eur["otras_deudas_corto"] += diferencia_cuadre
        balance_pct["otras_deudas_corto"] = balance_eur["otras_deudas_corto"] / activo_total_eur * 100
        ajuste_cuadre_eur = diferencia_cuadre

    # Gastos financieros = deuda financiera media del ejercicio x tipo de interés del sector.
    # Este módulo no modela una serie temporal (no hay "ejercicio anterior"): se asume que la
    # deuda financiera se mantuvo estable durante el año, es decir inicio = fin = la del propio
    # balance ya generado. En `evolucion_arquetipo` sí hay inicio/fin distintos (ver ese módulo).
    deuda_financiera_eur = balance_eur["deudas_fin_largo"] + balance_eur["deudas_fin_corto"]

    # Perfil de activo_no_corriente y colección de activos amortizables — RNG PROPIO E
    # INDEPENDIENTE del `rng` compartido de balance/PyG (no desplaza ningún sorteo ya existente
    # de balance_pct/rotacion_activo/cifra_negocios/consumos_explotacion/gastos_personal). Tiene
    # que calcularse ANTES de la PyG porque el gasto de amortización ahora se DERIVA de esta
    # colección en vez de sortearse — ver motor/amortizacion.py (arreglo de raíz, no un parche:
    # antes `amortizaciones_pct` se sorteaba sin ninguna conexión con el inmovilizado real).
    categoria = categoria_de_sector(sector)
    rng_perfil = np.random.default_rng([semilla, zlib.crc32(f"{sector}|{segmento}|perfil_activo_no_corriente".encode("utf-8"))])
    perfil_activo_no_corriente = generar_perfil_activo_no_corriente(rng_perfil, categoria)
    activo_no_corriente_desglose_eur = {
        componente: fraccion * balance_eur["activo_no_corriente"]
        for componente, fraccion in perfil_activo_no_corriente.items()
    }
    coleccion_activos_amortizables, perfil_subtipos_material, perfil_subtipos_intangible = generar_coleccion_y_perfiles_base(
        sector, segmento, semilla, categoria, activo_no_corriente_desglose_eur
    )
    amortizacion_eur_2023 = amortizacion_eur_del_año(coleccion_activos_amortizables, _AÑO_BASE_AMORTIZACION)

    parcial_pyg = _generar_pyg_hasta_baii(rng, fila, ventas_objetivo, amortizaciones_eur=amortizacion_eur_2023)
    pyg_pct, pyg_eur = _completar_pyg_con_deuda(parcial_pyg, deuda_financiera_eur)

    modos = {**modos_balance, "rotacion_activo": modo_rotacion, **parcial_pyg.modos}

    # Desagregación de PN (ver docstrings de las constantes arriba) — sorteo AÑADIDO AL FINAL de
    # la secuencia de rng ya existente, después de todo lo demás: no desplaza ningún sorteo
    # anterior, así que no cambia ningún valor de balance/PyG previo a este punto.
    capital_social_eur = _generar_capital_social(rng, balance_eur["patrimonio_neto"])
    reservas_eur = balance_eur["patrimonio_neto"] - capital_social_eur - pyg_eur["resultado_ejercicio"]

    return EmpresaBase(
        sector_codigo=sector,
        sector_nombre=sector_nombre,
        segmento=segmento,
        ventas_objetivo=ventas_objetivo,
        semilla=semilla,
        rotacion_activo=rotacion_activo,
        activo_total_eur=activo_total_eur,
        balance_pct=balance_pct,
        balance_eur=balance_eur,
        pyg_pct=pyg_pct,
        pyg_eur=pyg_eur,
        modos=modos,
        ajuste_cuadre_eur=ajuste_cuadre_eur,
        capital_social_eur=capital_social_eur,
        reservas_eur=reservas_eur,
        activo_no_corriente_perfil_pct=perfil_activo_no_corriente,
        activo_no_corriente_desglose_eur=activo_no_corriente_desglose_eur,
        coleccion_activos_amortizables=coleccion_activos_amortizables,
        perfil_subtipos_material_pct=perfil_subtipos_material,
        perfil_subtipos_intangible_pct=perfil_subtipos_intangible,
    )
