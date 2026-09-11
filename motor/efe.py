"""Estado de Flujos de Efectivo (EFE), método indirecto, modelo NORMAL del PGC — sección 2.2/2.5
del documento de especificaciones. Capa de cálculo pura sobre el balance/PyG que el motor YA
genera para dos ejercicios consecutivos (p. ej. 2023→2024) — no genera ningún dato nuevo, no
toca `motor.empresa_base` ni `motor.evolucion_arquetipo` más que consumir los campos que ya
exponen (incluida la desagregación de PN y de `activo_no_corriente` añadida para este encargo).

Modelo oficial verificado externamente (no de memoria) contra una fuente que cita el RD
1514/2007 — estructura A) Explotación / B) Inversión / C) Financiación / D) Tipo de cambio /
E) Variación neta, línea por línea. Ver CLAUDE.md, sección "EFE y ECPN", para el mapeo completo
de mecanismos del motor a líneas de este modelo, revisado por el usuario antes de implementar.

**Corrección importante sobre la amortización (A.2.a), respecto a lo propuesto inicialmente**:
el modelo oficial exige añadir de vuelta la amortización en A.2.a (es un gasto no monetario en
una empresa real, cuya contrapartida es una reducción del valor en libros del inmovilizado). En
ESTE motor, sin embargo, `activo_no_corriente` NUNCA se reduce por amortización (no hay
amortización acumulada modelada contra el activo — ver decisiones_plausibilidad.md) — así que la
amortización, en términos de la identidad del balance de este motor, se comporta EXACTAMENTE
como un gasto en efectivo cualquiera: la reducción de PN que causa se absorbe automáticamente
por el "parche" de cuadre (`otras_deudas_corto`, ya mapeado a A.3.e), NO por ninguna reducción de
activo. Añadirla de vuelta en A.2.a sin más duplicaría ese efecto (se contaría una vez vía A.3.e
y otra vez vía A.2.a) y rompería la reconciliación en exactamente el importe de la amortización
del año — verificado numéricamente con un caso mínimo antes de fijar esto. Por eso `a2a_amortizacion`
se deja siempre en 0.0 aquí, una desviación deliberada del modelo de texto, documentada
explícitamente, no un olvido. Los demás ajustes de A.2 (ingresos/gastos financieros) SÍ se
incluyen tal cual porque se cancelan exactamente dentro del propio EFE (A.2.g/h se deshacen en
A.4.a/c), sin depender de si el balance tiene o no una partida propia detrás.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from motor.evolucion_arquetipo import EjercicioEmpresa

TOLERANCIA_CUADRE_EUR = 0.01


@dataclass(frozen=True)
class EstadoFlujosEfectivo:
    año: int
    obligatorio: bool  # False si el caso clasifica legalmente como modelo abreviado (Art. 257.3 LSC)

    # A) Flujos de efectivo de las actividades de explotación
    a1_resultado_antes_impuestos: float
    a2a_amortizacion: float  # SIEMPRE 0.0 en este motor — ver docstring del módulo
    a2g_ingresos_financieros: float
    a2h_gastos_financieros: float
    a2k_otros_ingresos_gastos: float  # SIEMPRE 0.0 — sin mecanismo que lo alimente
    a3a_existencias: float
    a3b_deudores: float
    a3c_otros_activos_corrientes: float  # SIEMPRE 0.0 — sin mecanismo que lo alimente
    a3d_acreedores: float
    a3e_otros_pasivos_corrientes: float
    a3f_otros_activos_pasivos_no_corrientes: float
    a4a_pagos_intereses: float
    a4b_cobros_dividendos: float  # SIEMPRE 0.0 — sin cartera de inversión que los genere
    a4c_cobros_intereses: float
    a4d_impuesto_beneficios: float
    a4e_otros: float  # SIEMPRE 0.0
    a5_flujo_explotacion: float

    # B) Flujos de efectivo de las actividades de inversión — signo: negativo = pago, positivo = cobro
    b6b7_intangible: float
    b6b7_material: float
    b6b7_inversiones_inmobiliarias: float
    b6b7_otros_activos_financieros: float
    b6a_empresas_grupo_adquisicion: float  # arquetipo 18 — salto separado del crecimiento orgánico
    b8_flujo_inversion: float

    # C) Flujos de efectivo de las actividades de financiación
    c9_instrumentos_patrimonio: float  # = cobro de subvenciones de capital en el año de concesión (ver motor/coberturas_subvenciones.py) — 0.0 si no hay subvención; capital social sigue fijo, sin ampliaciones/reducciones modeladas
    c10_variacion_neta_deuda_financiera: float  # neto emisión/devolución — el motor no distingue gross issuance/repayment dentro del año
    c11a_dividendos: float  # arquetipo 9/14 (apalancamiento): la distribución financiada con la deuda nueva de C.10
    c12_flujo_financiacion: float

    # D) y E)
    d_efecto_tipo_cambio: float  # SIEMPRE 0.0 — sin moneda extranjera modelada
    e_variacion_neta_efectivo: float
    disponible_inicial: float
    disponible_final: float
    descuadre_eur: float

    @property
    def cuadra(self) -> bool:
        return abs(self.descuadre_eur) <= TOLERANCIA_CUADRE_EUR


def generar_efe(anterior: EjercicioEmpresa, actual: EjercicioEmpresa, obligatorio: bool) -> EstadoFlujosEfectivo:
    """EFE del ejercicio `actual` frente al `anterior` (p. ej. 2023→2024 o 2024→2025)."""
    a1 = actual.pyg_eur["bai"]
    a2a = 0.0  # ver docstring del módulo
    a2g = -actual.pyg_eur["ingresos_financieros"]
    a2h = actual.pyg_eur["gastos_financieros"]
    # A.2.k ("otros ajustes") — reversa el importe BRUTO que la cobertura/subvención inyectó en
    # el resultado antes de impuestos (A.1) vía `otros_ingresos_explot`/`gastos_financieros`
    # (imputación anual de la subvención + ineficacia y transferencia por vencimiento de la
    # cobertura, ver motor/coberturas_subvenciones.py): es una reclasificación contable pura
    # desde una reserva de PN (130/1340) hacia el resultado del ejercicio, SIN flujo de caja
    # alguno — igual naturaleza que a2a (amortización), que también se revierte por no tener
    # contrapartida de caja. Sin este reverso, A.1 arrastraría el importe como si fuera caja
    # operativa real y el EFE dejaría de cuadrar exactamente en ese importe.
    a2k = -(actual.subvencion_transferencia_bruto_eur + actual.cobertura_ineficaz_bruto_eur + actual.cobertura_transferencia_bruto_eur)

    a3a = -(actual.balance_eur["existencias"] - anterior.balance_eur["existencias"])
    a3b = -(actual.balance_eur["realizable"] - anterior.balance_eur["realizable"])
    a3c = 0.0
    a3d = actual.balance_eur["acreedores_comerciales"] - anterior.balance_eur["acreedores_comerciales"]
    a3e = actual.balance_eur["otras_deudas_corto"] - anterior.balance_eur["otras_deudas_corto"]
    # A.3.f excluye el grupo89 (cobertura si es pasivo + impuesto diferido de cobertura y
    # subvención, ver motor/coberturas_subvenciones.py) alojado dentro de `otras_deudas_largo`:
    # son valoraciones/reclasificaciones puramente contables sin ningún flujo de caja detrás
    # (a diferencia de un pasivo operativo real) — su contrapartida es la línea de PN
    # correspondiente, no caja, así que tratarlas aquí como "fuente de caja" duplicaría un
    # movimiento que no existe. Mismo criterio que ya se aplica a la amortización (a2a).
    grupo89_pasivo_no_corriente_actual = actual.pasivos_por_impuesto_diferido_eur + max(0.0, -actual.cobertura_valor_swap_eur)
    grupo89_pasivo_no_corriente_anterior = anterior.pasivos_por_impuesto_diferido_eur + max(0.0, -anterior.cobertura_valor_swap_eur)
    a3f = (actual.balance_eur["otras_deudas_largo"] - grupo89_pasivo_no_corriente_actual) - (
        anterior.balance_eur["otras_deudas_largo"] - grupo89_pasivo_no_corriente_anterior
    )

    a4a = -actual.pyg_eur["gastos_financieros"]
    a4b = 0.0
    a4c = actual.pyg_eur["ingresos_financieros"]
    a4d = -actual.pyg_eur["impuesto_beneficios"]
    a4e = 0.0

    a5 = a1 + a2a + a2g + a2h + a2k + a3a + a3b + a3c + a3d + a3e + a3f + a4a + a4b + a4c + a4d + a4e

    # B) Inversión — desglose por perfil (material/intangible/inversiones_inmobiliarias/otros
    # financieros), constante para el caso, aplicado al cambio ORGÁNICO de activo_no_corriente
    # (excluyendo el salto de adquisición del año actual, si lo hay, que se muestra aparte en
    # B.6.a). Ver docstring de EjercicioEmpresa.activo_no_corriente_desglose_eur.
    # Excluye, igual que A.3.f, el grupo89 alojado dentro de `activo_no_corriente` (el derivado
    # de la cobertura si es activo + su impuesto diferido) — sin flujo de caja detrás, ver más
    # arriba.
    grupo89_activo_no_corriente_actual = actual.activos_por_impuesto_diferido_eur + max(0.0, actual.cobertura_valor_swap_eur)
    grupo89_activo_no_corriente_anterior = anterior.activos_por_impuesto_diferido_eur + max(0.0, anterior.cobertura_valor_swap_eur)
    delta_activo_no_corriente_organico = (
        (actual.balance_eur["activo_no_corriente"] - grupo89_activo_no_corriente_actual)
        - actual.incremento_activo_adquisicion_eur
        - (anterior.balance_eur["activo_no_corriente"] - grupo89_activo_no_corriente_anterior)
    )
    perfil = actual.activo_no_corriente_perfil_pct
    b_intangible = -perfil["intangible"] * delta_activo_no_corriente_organico
    b_material = -perfil["material"] * delta_activo_no_corriente_organico
    b_inversiones_inmobiliarias = -perfil["inversiones_inmobiliarias"] * delta_activo_no_corriente_organico
    b_otros_financieros = -perfil["otros_financieros"] * delta_activo_no_corriente_organico
    b_adquisicion = -actual.incremento_activo_adquisicion_eur

    b8 = b_intangible + b_material + b_inversiones_inmobiliarias + b_otros_financieros + b_adquisicion

    # C) Financiación
    deuda_financiera_actual = actual.balance_eur["deudas_fin_largo"] + actual.balance_eur["deudas_fin_corto"]
    deuda_financiera_anterior = anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"]
    c10 = deuda_financiera_actual - deuda_financiera_anterior
    # C.9 ("Cobros y pagos por instrumentos de patrimonio... subvenciones, donaciones y legados
    # recibidos") — antes siempre 0.0 por no existir ningún mecanismo detrás; el encargo de
    # coberturas/subvenciones lo rellena con el cobro real de caja del año de concesión (ver
    # motor/coberturas_subvenciones.py y motor/evolucion_arquetipo.py — el importe se añade
    # directamente a `disponible` ese año, C.9 es la contrapartida que lo explica en el EFE).
    c9 = actual.subvencion_importe_concedido_eur
    c11a = -actual.apalancamiento_extra_eur
    c12 = c9 + c10 + c11a

    d = 0.0
    e = a5 + b8 + c12 + d

    disponible_inicial = anterior.balance_eur["disponible"]
    disponible_final = actual.balance_eur["disponible"]
    descuadre = (disponible_inicial + e) - disponible_final

    return EstadoFlujosEfectivo(
        año=actual.año,
        obligatorio=obligatorio,
        a1_resultado_antes_impuestos=a1,
        a2a_amortizacion=a2a,
        a2g_ingresos_financieros=a2g,
        a2h_gastos_financieros=a2h,
        a2k_otros_ingresos_gastos=a2k,
        a3a_existencias=a3a,
        a3b_deudores=a3b,
        a3c_otros_activos_corrientes=a3c,
        a3d_acreedores=a3d,
        a3e_otros_pasivos_corrientes=a3e,
        a3f_otros_activos_pasivos_no_corrientes=a3f,
        a4a_pagos_intereses=a4a,
        a4b_cobros_dividendos=a4b,
        a4c_cobros_intereses=a4c,
        a4d_impuesto_beneficios=a4d,
        a4e_otros=a4e,
        a5_flujo_explotacion=a5,
        b6b7_intangible=b_intangible,
        b6b7_material=b_material,
        b6b7_inversiones_inmobiliarias=b_inversiones_inmobiliarias,
        b6b7_otros_activos_financieros=b_otros_financieros,
        b6a_empresas_grupo_adquisicion=b_adquisicion,
        b8_flujo_inversion=b8,
        c9_instrumentos_patrimonio=c9,
        c10_variacion_neta_deuda_financiera=c10,
        c11a_dividendos=c11a,
        c12_flujo_financiacion=c12,
        d_efecto_tipo_cambio=d,
        e_variacion_neta_efectivo=e,
        disponible_inicial=disponible_inicial,
        disponible_final=disponible_final,
        descuadre_eur=descuadre,
    )
