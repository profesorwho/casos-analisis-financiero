"""Mapeo del EFE — 2 periodos (2024, 2025), cada uno un EstadoFlujosEfectivo(2023->2024) y
(2024->2025). El modelo Normal es el único que tiene EFE oficialmente, pero se genera también
para Abreviado por decisión del proyecto (valor didáctico, ver especificaciones tarea 82) —
misma estructura en ambos, sin sub-letras que quitar (el EFE oficial no las tiene)."""
from __future__ import annotations

from tipos import LineaEstado
from notas_memoria import NOTA_POR_LINEA

PERIODOS = (2024, 2025)


def _v(efes, extractor):
    return {año: extractor(efes[año]) for año in PERIODOS}


def mapear_efe(efes: dict) -> list[LineaEstado]:
    L = []
    L.append(LineaEstado("A", "FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE EXPLOTACIÓN", 0, {}, negrita=True))
    L.append(LineaEstado("1", "Resultado del ejercicio antes de impuestos", 2, _v(efes, lambda e: e.a1_resultado_antes_impuestos)))
    L.append(LineaEstado("2", "Ajustes del resultado", 2, _v(efes, lambda e: (
        e.a2a_amortizacion + e.a2e_deterioro_enajenacion_inmovilizado + e.a2g_ingresos_financieros
        + e.a2h_gastos_financieros + e.a2k_otros_ingresos_gastos
    )), negrita=True))
    for letra, etq, campo in [
        ("a)", "Amortización del inmovilizado", "a2a_amortizacion"),
        ("e)", "Resultados por bajas y enajenaciones del inmovilizado", "a2e_deterioro_enajenacion_inmovilizado"),
        ("g)", "Ingresos financieros", "a2g_ingresos_financieros"),
        ("h)", "Gastos financieros", "a2h_gastos_financieros"),
        ("k)", "Otros ingresos y gastos", "a2k_otros_ingresos_gastos"),
    ]:
        L.append(LineaEstado(letra, etq, 3, _v(efes, lambda e, c=campo: getattr(e, c)),
                  nota=NOTA_POR_LINEA.get(f"efe.{campo}")))
    L.append(LineaEstado("3", "Cambios en el capital corriente", 2, _v(efes, lambda e: (
        e.a3a_existencias + e.a3b_deudores + e.a3d_acreedores + e.a3e_otros_pasivos_corrientes + e.a3f_otros_activos_pasivos_no_corrientes
    )), negrita=True))
    for letra, etq, campo in [
        ("a)", "Existencias", "a3a_existencias"), ("b)", "Deudores y otras cuentas a cobrar", "a3b_deudores"),
        ("d)", "Acreedores y otras cuentas a pagar", "a3d_acreedores"),
        ("e)", "Otros pasivos corrientes", "a3e_otros_pasivos_corrientes"),
        ("f)", "Otros activos y pasivos no corrientes", "a3f_otros_activos_pasivos_no_corrientes"),
    ]:
        L.append(LineaEstado(letra, etq, 3, _v(efes, lambda e, c=campo: getattr(e, c))))
    L.append(LineaEstado("4", "Otros flujos de efectivo de las actividades de explotación", 2, _v(efes, lambda e: (
        e.a4a_pagos_intereses + e.a4c_cobros_intereses + e.a4d_impuesto_beneficios
    )), negrita=True))
    for letra, etq, campo in [("a)", "Pagos de intereses", "a4a_pagos_intereses"), ("c)", "Cobros de intereses", "a4c_cobros_intereses"),
                              ("d)", "Cobros (pagos) por impuesto sobre beneficios", "a4d_impuesto_beneficios")]:
        L.append(LineaEstado(letra, etq, 3, _v(efes, lambda e, c=campo: getattr(e, c))))
    L.append(LineaEstado("A.5)", "FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE EXPLOTACIÓN", 1, _v(efes, lambda e: e.a5_flujo_explotacion), negrita=True))

    L.append(LineaEstado("B", "FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE INVERSIÓN", 0, {}, negrita=True))
    for cod, etq, campo in [
        ("6", "Pagos por inversiones — Empresas del grupo (adquisición)", "b6a_empresas_grupo_adquisicion"),
        ("6", "Pagos por inversiones en inmovilizado intangible", "b6b7_intangible"),
        ("6", "Pagos por inversiones en inmovilizado material", "b6b7_material"),
        ("6", "Pagos por inversiones en inversiones inmobiliarias", "b6b7_inversiones_inmobiliarias"),
        ("6", "Pagos por inversiones — Otros activos financieros", "b6b7_otros_activos_financieros"),
        ("6c", "Préstamo a empresas del grupo", "b6c_prestamo_empresas_grupo"),
        ("7", "Cobros por desinversiones — Enajenación de inmovilizado", "b6_enajenacion_inmovilizado"),
    ]:
        L.append(LineaEstado(cod, etq, 2, _v(efes, lambda e, c=campo: getattr(e, c))))
    L.append(LineaEstado("B.8)", "FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE INVERSIÓN", 1, _v(efes, lambda e: e.b8_flujo_inversion), negrita=True))

    L.append(LineaEstado("C", "FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE FINANCIACIÓN", 0, {}, negrita=True))
    for cod, etq, campo in [
        ("9", "Cobros por instrumentos de patrimonio (subvenciones, donaciones y legados)", "c9_instrumentos_patrimonio"),
        ("10", "Variación neta de deuda financiera", "c10_variacion_neta_deuda_financiera"),
        ("10c", "Deudas con empresas del grupo y asociadas", "c10c_empresas_grupo"),
        ("11a", "Pagos por dividendos", "c11a_dividendos"),
    ]:
        L.append(LineaEstado(cod, etq, 2, _v(efes, lambda e, c=campo: getattr(e, c)), nota=NOTA_POR_LINEA.get(f"efe.{campo}")))
    L.append(LineaEstado("C.12)", "FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE FINANCIACIÓN", 1, _v(efes, lambda e: e.c12_flujo_financiacion), negrita=True))

    L.append(LineaEstado("E)", "AUMENTO/DISMINUCIÓN NETA DEL EFECTIVO O EQUIVALENTES", 0, _v(efes, lambda e: e.e_variacion_neta_efectivo), negrita=True))
    L.append(LineaEstado("", "Efectivo o equivalentes al comienzo del ejercicio", 1, _v(efes, lambda e: e.disponible_inicial)))
    L.append(LineaEstado("", "Efectivo o equivalentes al final del ejercicio", 1, _v(efes, lambda e: e.disponible_final), negrita=True))
    return L
