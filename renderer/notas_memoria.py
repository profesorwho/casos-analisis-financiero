"""Numeración de notas de memoria — fijada una vez, compartida por el renderizador de
Balance/PyG/EFE/ECPN (PDF 1) y el futuro ensamblador de Memoria (PDF 2).

Criterio (verificado contra la práctica normativa real, no la numeración completa 1-25 del
formulario oficial del PGC): las notas sin contenido se eliminan y se renumeran correlativamente
las que permanecen. Aquí se listan SOLO los apartados que el motor puede alimentar con datos
reales de verdad — ver especificaciones_proyecto_casos_balances.md, tarea 82.
"""

from __future__ import annotations

NOTAS: dict[int, str] = {
    1: "Actividad de la empresa",
    2: "Bases de presentación de las cuentas anuales",
    3: "Aplicación de resultados",
    4: "Normas de registro y valoración",
    5: "Inmovilizado material, intangible e inversiones inmobiliarias",
    6: "Activos financieros",
    7: "Pasivos financieros",
    8: "Fondos propios",
    9: "Situación fiscal",
    10: "Operaciones con partes vinculadas",
    11: "Otra información",
}

# Línea oficial (clave interna usada por mapeo_pgc) -> número de nota. Una línea sin entrada
# aquí no lleva referencia de nota (no todas las líneas oficiales necesitan una).
NOTA_POR_LINEA: dict[str, int] = {
    # Balance — Activo no corriente
    "activo_no_corriente.intangible": 5,
    "activo_no_corriente.material": 5,
    "activo_no_corriente.inversiones_inmobiliarias": 5,
    "activo_no_corriente.otros_financieros": 6,
    "activo_no_corriente.inversion_grupo_largo": 6,
    # Balance — Activo corriente
    "realizable.clientes_empresas_grupo": 10,
    # Balance — Patrimonio neto
    "pn.capital": 8,
    "pn.reservas": 8,
    "pn.resultado_ejercicio": 3,
    # Balance — Pasivo no corriente
    "pasivo_no_corriente.provisiones_largo": 4,
    "pasivo_no_corriente.deudas_fin_largo": 7,
    "pasivo_no_corriente.deuda_grupo_largo": 10,
    "pasivo_no_corriente.impuesto_diferido": 9,
    # Balance — Pasivo corriente
    "pasivo_corriente.provisiones_corto": 4,
    "pasivo_corriente.deudas_fin_corto": 7,
    "pasivo_corriente.deuda_grupo_corto": 10,
    # PyG
    "pyg.amortizacion": 5,
    "pyg.deterioro_enajenacion_inmovilizado": 5,
    "pyg.ingresos_financieros": 6,
    "pyg.gastos_financieros": 7,
    "pyg.impuesto_beneficios": 9,
    "pyg.otros_gastos_explot": 4,
    # EFE
    "efe.a2a_amortizacion": 5,
    "efe.a2e_deterioro_enajenacion_inmovilizado": 5,
    "efe.c10_variacion_neta_deuda_financiera": 7,
    "efe.c10c_empresas_grupo": 10,
}
