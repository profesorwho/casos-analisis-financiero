"""Motor mínimo: genera el balance y la PyG base de una empresa a partir del catálogo
sectorial, con variabilidad realista entre empresas de un mismo sector.

Sin arquetipos, sin serie de tres años, sin EFE: un único ejercicio, coherente y cuadrado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from motor.catalogo import cargar_y_validar_catalogo

SEGMENTOS_VALIDOS = frozenset({"grandes_medianas", "pequeñas"})

PROB_ATIPICO = 0.15
DESVIACIONES_TIPICO = 1.5
DESVIACIONES_ATIPICO = 3.0

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
    """
    primitivas_forzadas = primitivas_forzadas or {}
    brutos: dict[str, float] = {}
    modos: dict[str, str] = {}
    for nombre_salida, variable in PRIMITIVAS_PYG.items():
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
    amortizaciones_eur = brutos["amortizaciones"] / 100 * ingresos_explotacion_eur
    resultado_extraordinario_eur = brutos["resultado_extraordinario"] / 100 * ingresos_explotacion_eur
    ingresos_financieros_eur = brutos["ingresos_financieros"] / 100 * ingresos_explotacion_eur
    impuesto_beneficios_eur = brutos["impuesto_beneficios"] / 100 * ingresos_explotacion_eur

    margen_bruto_eur = ingresos_explotacion_eur - consumos_explotacion_eur
    valor_añadido_eur = margen_bruto_eur - otros_gastos_explot_eur
    baii_eur = valor_añadido_eur - gastos_personal_eur - amortizaciones_eur + resultado_extraordinario_eur

    return _PygParcial(
        ingresos_explotacion_eur=ingresos_explotacion_eur,
        cifra_negocios_eur=cifra_negocios_eur,
        otros_ingresos_explot_eur=otros_ingresos_explot_eur,
        consumos_explotacion_eur=consumos_explotacion_eur,
        margen_bruto_eur=margen_bruto_eur,
        otros_gastos_explot_eur=otros_gastos_explot_eur,
        valor_añadido_eur=valor_añadido_eur,
        gastos_personal_eur=gastos_personal_eur,
        amortizaciones_eur=amortizaciones_eur,
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
    "grandes_medianas" o "pequeñas". El resultado es reproducible: misma semilla, mismo caso.
    """
    if segmento not in SEGMENTOS_VALIDOS:
        raise EmpresaBaseError(f"Segmento '{segmento}' no válido. Debe ser uno de: {sorted(SEGMENTOS_VALIDOS)}")
    if ventas_objetivo <= 0:
        raise EmpresaBaseError(f"ventas_objetivo debe ser positivo, recibido: {ventas_objetivo}")

    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    fila = resolver_fila_sector(catalogo, sector, segmento)
    sector_nombre = fila["sector"]

    rng = np.random.default_rng(semilla)

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
    parcial_pyg = _generar_pyg_hasta_baii(rng, fila, ventas_objetivo)
    pyg_pct, pyg_eur = _completar_pyg_con_deuda(parcial_pyg, deuda_financiera_eur)

    modos = {**modos_balance, "rotacion_activo": modo_rotacion, **parcial_pyg.modos}

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
    )
