"""Mapeo de la PyG a las líneas oficiales del PGC. Normal: 20 líneas con sub-letras a-e donde
aplica. Abreviado: mismas 20 líneas SIN sub-letras (una sola cifra por línea) y sin separar
operaciones continuadas/interrumpidas (ver modelo_abreviado_pgc.md).

Dos carve-outs verificados en el propio `otros_ingresos_explot` antes de escribir este mapeo
(no asumidos): la imputación de subvenciones (línea 9) y los excesos de provisiones/insolvencias
(línea 10) viven MEZCLADOS dentro de `pyg_eur["otros_ingresos_explot"]` — línea 5 real = total
menos esas dos, o se duplicarían euros entre 3 líneas oficiales distintas.
"""
from __future__ import annotations

from tipos import LineaEstado
from notas_memoria import NOTA_POR_LINEA

AÑOS = (2023, 2024, 2025)


def _v(ejercicios, extractor):
    return {año: extractor(ejercicios[año]) for año in AÑOS}


def _otros_ingresos_explot_neto(e):
    return e.pyg_eur["otros_ingresos_explot"] - e.subvencion_transferencia_bruto_eur - e.pyg_linea_10_excesos_provisiones_eur


def _variacion_existencias(ejercicios, año):
    if año == 2023:
        return 0.0  # sin año -1 dentro de la ventana de 3 años mostrada
    def pt(e):
        return e.existencias_desglose_eur.get("productos_curso", 0.0) + e.existencias_desglose_eur.get("productos_terminados", 0.0)
    return pt(ejercicios[año]) - pt(ejercicios[año - 1])


def mapear_pyg(ejercicios: dict, modelo: str) -> list[LineaEstado]:
    L = []
    normal = modelo == "normal"

    L.append(LineaEstado("1", "Importe neto de la cifra de negocios", 2,
              _v(ejercicios, lambda e: e.pyg_eur["cifra_negocios"]), negrita=True))
    if normal:
        L.append(LineaEstado("a)", "Ventas", 3, _v(ejercicios, lambda e: e.pyg_cifra_negocios_desglose_eur.get("ventas", 0.0))))
        L.append(LineaEstado("b)", "Prestaciones de servicios", 3, _v(ejercicios, lambda e: e.pyg_cifra_negocios_desglose_eur.get("servicios", 0.0))))

    L.append(LineaEstado("2", "Variación de existencias de productos terminados y en curso de fabricación", 2,
              {año: _variacion_existencias(ejercicios, año) for año in AÑOS}))
    L.append(LineaEstado("3", "Trabajos realizados por la empresa para su activo", 2, _v(ejercicios, lambda e: 0.0)))

    L.append(LineaEstado("4", "Aprovisionamientos", 2,
              _v(ejercicios, lambda e: -e.pyg_eur["consumos_explotacion"]), negrita=True))
    if normal:
        etq = {"mercaderias": "Consumo de mercaderías", "materias_primas": "Consumo de materias primas y otras materias consumibles",
               "trabajos_otras_empresas": "Trabajos realizados por otras empresas", "deterioro": "Deterioro de mercaderías, materias primas y otros aprovisionamientos"}
        letras = ["a)", "b)", "c)", "d)"]
        for letra, (clave, etqt) in zip(letras, etq.items()):
            L.append(LineaEstado(letra, etqt, 3, _v(ejercicios, lambda e, c=clave: -e.pyg_consumos_explotacion_desglose_eur.get(c, 0.0))))

    L.append(LineaEstado("5", "Otros ingresos de explotación", 2, _v(ejercicios, _otros_ingresos_explot_neto), negrita=True))

    L.append(LineaEstado("6", "Gastos de personal", 2,
              _v(ejercicios, lambda e: -e.pyg_eur["gastos_personal"]), negrita=True))
    if normal:
        etq_p = {"sueldos_salarios": "Sueldos, salarios y asimilados", "cargas_sociales": "Cargas sociales", "provisiones": "Provisiones"}
        for letra, (clave, etqt) in zip(["a)", "b)", "c)"], etq_p.items()):
            L.append(LineaEstado(letra, etqt, 3, _v(ejercicios, lambda e, c=clave: -e.pyg_gastos_personal_desglose_eur.get(c, 0.0))))

    L.append(LineaEstado("7", "Otros gastos de explotación", 2,
              _v(ejercicios, lambda e: -e.pyg_eur["otros_gastos_explot"]), negrita=True, nota=NOTA_POR_LINEA.get("pyg.otros_gastos_explot")))
    if normal:
        etq_g = {"servicios_exteriores": "Servicios exteriores", "tributos": "Tributos",
                 "perdidas_deterioro_operaciones_comerciales": "Pérdidas, deterioro y variación de provisiones por operaciones comerciales",
                 "otros_gestion_corriente": "Otros gastos de gestión corriente", "gases_efecto_invernadero": "Gastos por emisión de gases de efecto invernadero"}
        for letra, (clave, etqt) in zip(["a)", "b)", "c)", "d)", "e)"], etq_g.items()):
            L.append(LineaEstado(letra, etqt, 3, _v(ejercicios, lambda e, c=clave: -e.pyg_otros_gastos_explot_desglose_eur.get(c, 0.0))))

    L.append(LineaEstado("8", "Amortización del inmovilizado", 2, _v(ejercicios, lambda e: -e.pyg_eur["amortizaciones"]), nota=NOTA_POR_LINEA.get("pyg.amortizacion")))
    L.append(LineaEstado("9", "Imputación de subvenciones de inmovilizado no financiero y otras", 2,
              _v(ejercicios, lambda e: e.subvencion_transferencia_bruto_eur)))
    L.append(LineaEstado("10", "Excesos de provisiones", 2, _v(ejercicios, lambda e: e.pyg_linea_10_excesos_provisiones_eur)))
    L.append(LineaEstado("11", "Deterioro y resultado por enajenaciones del inmovilizado", 2,
              _v(ejercicios, lambda e: e.pyg_eur["deterioro_enajenacion_inmovilizado"]), nota=NOTA_POR_LINEA.get("pyg.deterioro_enajenacion_inmovilizado")))
    L.append(LineaEstado("12", "Diferencia negativa de combinaciones de negocio", 2, _v(ejercicios, lambda e: 0.0)))
    L.append(LineaEstado("13", "Otros resultados", 2, _v(ejercicios, lambda e: e.pyg_linea_13_otros_resultados_eur)))

    codigo_expl = "A.1)" if normal else "A)"
    L.append(LineaEstado(codigo_expl, "RESULTADO DE EXPLOTACIÓN", 1, _v(ejercicios, lambda e: e.pyg_eur["baii"]), negrita=True))

    L.append(LineaEstado("14", "Ingresos financieros", 2, _v(ejercicios, lambda e: e.pyg_eur["ingresos_financieros"]), negrita=True, nota=NOTA_POR_LINEA.get("pyg.ingresos_financieros")))
    L.append(LineaEstado("a)", "De participaciones en instrumentos de patrimonio — empresas del grupo", 3,
              _v(ejercicios, lambda e: e.pyg_ingresos_financieros_desglose_eur.get("empresas_grupo", 0.0))))
    L.append(LineaEstado("b)", "De valores negociables y de créditos del activo — terceros", 3,
              _v(ejercicios, lambda e: e.pyg_ingresos_financieros_desglose_eur.get("terceros", 0.0))))
    L.append(LineaEstado("15", "Gastos financieros", 2, _v(ejercicios, lambda e: -e.pyg_eur["gastos_financieros"]), nota=NOTA_POR_LINEA.get("pyg.gastos_financieros")))
    L.append(LineaEstado("16", "Variación de valor razonable en instrumentos financieros", 2, _v(ejercicios, lambda e: 0.0)))
    L.append(LineaEstado("17", "Diferencias de cambio", 2, _v(ejercicios, lambda e: 0.0)))
    L.append(LineaEstado("18", "Deterioro y resultado por enajenaciones de instrumentos financieros", 2, _v(ejercicios, lambda e: 0.0)))
    L.append(LineaEstado("19", "Otros ingresos y gastos de carácter financiero", 2, _v(ejercicios, lambda e: 0.0)))

    codigo_fin = "A.2)" if normal else "B)"
    L.append(LineaEstado(codigo_fin, "RESULTADO FINANCIERO", 1,
              _v(ejercicios, lambda e: e.pyg_eur["ingresos_financieros"] - e.pyg_eur["gastos_financieros"]), negrita=True))
    codigo_bai = "A.3)" if normal else "C)"
    L.append(LineaEstado(codigo_bai, "RESULTADO ANTES DE IMPUESTOS", 1, _v(ejercicios, lambda e: e.pyg_eur["bai"]), negrita=True))
    L.append(LineaEstado("20", "Impuestos sobre beneficios", 2, _v(ejercicios, lambda e: -e.pyg_eur["impuesto_beneficios"]), nota=NOTA_POR_LINEA.get("pyg.impuesto_beneficios")))
    codigo_final = "A.4) RESULTADO DEL EJERCICIO PROCEDENTE DE OPERACIONES CONTINUADAS" if normal else "D) RESULTADO DEL EJERCICIO"
    codigo, etq_final = (codigo_final.split(") ", 1)[0] + ")", codigo_final.split(") ", 1)[1])
    L.append(LineaEstado(codigo, etq_final, 1, _v(ejercicios, lambda e: e.pyg_eur["resultado_ejercicio"]), negrita=True))
    return L
