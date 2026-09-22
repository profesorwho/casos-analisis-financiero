"""Estado de Flujos de Efectivo (EFE), método indirecto, modelo NORMAL del PGC — sección 2.2/2.5
del documento de especificaciones. Capa de cálculo pura sobre el balance/PyG que el motor YA
genera para dos ejercicios consecutivos (p. ej. 2023→2024) — no genera ningún dato nuevo, no
toca `motor.empresa_base` ni `motor.evolucion_arquetipo` más que consumir los campos que ya
exponen (incluida la desagregación de PN y de `activo_no_corriente` añadida para este encargo).

Modelo oficial verificado externamente (no de memoria) contra una fuente que cita el RD
1514/2007 — estructura A) Explotación / B) Inversión / C) Financiación / D) Tipo de cambio /
E) Variación neta, línea por línea. Ver CLAUDE.md, sección "EFE y ECPN", para el mapeo completo
de mecanismos del motor a líneas de este modelo, revisado por el usuario antes de implementar.

**`a2a_amortizacion` ACTIVADO (encargo que cierra #26/#94/#96, ver decisiones_plausibilidad.md
#98) — historial de la decisión, no borrado, porque explica por qué el motor tardó tres encargos
en llegar aquí**: originalmente (decisión #26) se dejó siempre en 0.0 porque `activo_no_corriente`
nunca se reducía por amortización acumulada — sumarla en A.2.a habría duplicado el efecto que el
"parche" de cuadre (`otras_deudas_corto`, A.3.e) ya absorbía en silencio. Esa premisa dejó de ser
cierta con el encargo #98 (`motor/evolucion_arquetipo.py`, bloque "Amortización real neta contra
el Balance"): en años evolucionados, `activo_no_corriente` YA se reduce por la amortización real
de la colección de `motor/amortizacion.py`. Ahora `a2a_amortizacion = actual.pyg_eur[
"amortizaciones"]` (el mismo gasto no monetario ya restado en A.1) — y, en paralelo, el delta
"orgánico" de B.6/7 (más abajo) se ajusta para reflejar el capex BRUTO del año (antes de
amortización), no el neto ya mermado por ella: sin ese ajuste, la reconciliación de `disponible`
se rompería en el importe exacto de la amortización, igual que se habría roto en la decisión #26
si se hubiera sumado sin más en aquel momento. Los dos ajustes (A.2.a +amortización, B.6/7
−amortización adicional de salida) se cancelan exactamente en la variación neta de efectivo — la
amortización sigue sin ser un flujo de caja, solo cambia de qué línea "no monetaria" se reclasifica
la reversión, del parche genérico de A.3.e a las líneas oficiales del modelo de texto. Los demás
ajustes de A.2 (ingresos/gastos financieros) siguen incluidos tal cual porque se cancelan
exactamente dentro del propio EFE (A.2.g/h se deshacen en A.4.a/c), sin depender de si el balance
tiene o no una partida propia detrás.

**Bajas anticipadas de sub-lotes (línea 11 PGC, "Deterioro y resultado por enajenaciones del
inmovilizado" — ver motor/amortizacion.py)**: `a2e_deterioro_enajenacion_inmovilizado` revierte
ÍNTEGRO el resultado no monetario de la línea 11 ya incluido en A.1 (el valor en libros dado de
baja nunca es caja, y la plus/minusvalía sobre él tampoco); el único movimiento de caja real (el
precio de venta, si hubo enajenación) aparece en B) como `b6_enajenacion_inmovilizado`, un cobro
positivo — nunca en A). El valor en libros de la baja se excluye del delta "orgánico" que
alimenta `b6b7_intangible/material/inversiones_inmobiliarias/otros_activos_financieros` (mismo
criterio que ya excluye el salto de adquisición del arquetipo 18, `b6a`): una baja no es una
compra/venta "normal" repartible por el perfil fijo del caso.

**Atribución por categoría de B.6/7 CORREGIDA (decisiones_plausibilidad.md #102, cierra el
hallazgo secundario de #100)** — historial, no borrado: hasta este encargo, las 4 líneas de
B.6/7 se derivaban repartiendo el delta AGREGADO de `activo_no_corriente` con el perfil % FIJO
de 4 categorías (`activo_no_corriente_perfil_pct`, constante desde 2023). Eso era correcto
mientras las 4 categorías se movían todas juntas (antes de #94/#96/#100) pero dejó de serlo
cuando cada una ganó su propia dinámica real: material/intangible/inversiones_inmobiliarias
siguen el capex-amortización real (#98) compartiendo un único "pool" amortizable, mientras
`otros_financieros` (#100) crece de forma TOTALMENTE independiente, ajena a capex/amortización/
bajas. Repartir el agregado (que mezclaba ambas dinámicas) con el perfil de 4 categorías
desalineaba cada línea individual del Balance ya corregido (hasta 764.000€ de diferencia en el
peor caso del barrido; caso documentado en #100, sector 69.2/semilla 2/2025: -367.298€ en el
EFE frente a +397.069€ real) — el subtotal B.8 y el cuadre general seguían exactos por
construcción algebraica, el problema era solo de atribución. Ahora `b6b7_otros_activos_
financieros` es el delta real DIRECTO (sin ajuste, nunca participa en adquisición/capex/
amortización/bajas); material/intangible/inversiones_inmobiliarias se derivan del delta real del
POOL amortizable (mismas exclusiones de adquisición/baja/amortización que antes) repartido con
el peso relativo `perfil[c]/(perfil.material+perfil.intangible+perfil.inversiones_
inmobiliarias)` — el MISMO peso que `motor/evolucion_arquetipo.py` usa para construir ese
desglose cada año, no un dato independiente. Verificado algebraicamente y en barrido (27×2×6×4
combos) que B.8 no cambia ni un céntimo — es una repartición distinta del mismo total.
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
    a2a_amortizacion: float  # = pyg_eur["amortizaciones"] del año actual — ver docstring del módulo (decisiones_plausibilidad.md #98)
    a2e_deterioro_enajenacion_inmovilizado: float  # revierte la línea 11 de PyG (no monetaria en A.1) — ver motor/amortizacion.py
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
    b6_enajenacion_inmovilizado: float  # cobro real por las bajas que fueron enajenación (0.0 si fue deterioro puro) — ver motor/amortizacion.py
    b6c_prestamo_empresas_grupo: float  # arquetipo 20, "préstamo a matriz" — variación de inversion_grupo_largo_eur
    b8_flujo_inversion: float

    # C) Flujos de efectivo de las actividades de financiación
    c9_instrumentos_patrimonio: float  # = cobro de subvenciones de capital en el año de concesión (ver motor/coberturas_subvenciones.py) — 0.0 si no hay subvención; capital social sigue fijo, sin ampliaciones/reducciones modeladas
    c10_variacion_neta_deuda_financiera: float  # neto emisión/devolución de deudas_fin_largo/corto — el motor no distingue gross issuance/repayment dentro del año
    c10c_empresas_grupo: float  # arquetipo 20, "financiación recibida de grupo" — variación de deuda_grupo_largo_eur (letra (c) del desglose oficial de la línea 10, NUNCA mezclada con c10: esa masa no genera gastos financieros, ver motor/evolucion_arquetipo.py)
    c11a_dividendos: float  # arquetipo 9/14 (apalancamiento, financiada con la deuda nueva de C.10) + payout de fondo (financiado con caja real, #79-#80) — una sola línea, mismo criterio que el modelo oficial PGC (no distingue fuente de financiación del dividendo)
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
    # A.2.a ("Amortización del inmovilizado") — activado desde decisiones_plausibilidad.md #98:
    # ver docstring del módulo. Añade de vuelta, en A), el gasto no monetario ya restado en A.1;
    # su contrapartida (capex bruto vs. neto) se ajusta más abajo en B.6/7.
    a2a = actual.pyg_eur["amortizaciones"]
    # A.2.e ("Resultados por bajas y enajenaciones del inmovilizado") — revierte ÍNTEGRO el
    # resultado no monetario de la línea 11 de PyG ya incluido en A.1 (BAI): el valor en libros
    # dado de baja no es una salida de caja de este año, y la plus/minusvalía sobre él tampoco lo
    # es — el único movimiento de caja real (el precio de venta cobrado, si hubo enajenación) se
    # muestra aparte, en B) como cobro de inversión (`b6_enajenacion_inmovilizado`), NUNCA aquí.
    # Mismo criterio que a2a/a2k: una reclasificación contable sin caja detrás.
    a2e = -actual.pyg_eur["deterioro_enajenacion_inmovilizado"]
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
    # A.3.f excluye el grupo89 (impuesto diferido de cobertura y subvención, ver motor/
    # coberturas_subvenciones.py) alojado dentro de `otras_deudas_largo`: son reclasificaciones
    # puramente contables sin ningún flujo de caja detrás (a diferencia de un pasivo operativo
    # real) — su contrapartida es la línea de PN correspondiente, no caja, así que tratarlas
    # aquí como "fuente de caja" duplicaría un movimiento que no existe. Mismo criterio que ya se
    # aplica a la amortización (a2a). El derivado de la cobertura, cuando es PASIVO, YA NO vive
    # aquí desde el cuarto lote de desglose de balance (ver `c10` más abajo, que ahora es quien lo
    # excluye — se movió de línea, no de tratamiento: sigue sin flujo de caja propio). También
    # excluye `deuda_grupo_largo_eur` (arquetipo 20, "financiación recibida de grupo"): es una
    # actividad de FINANCIACIÓN (Sección C, ver más abajo, letra (c) del desglose oficial de la
    # línea 10), no de explotación — mismo criterio de exclusión que grupo89, aunque la
    # naturaleza sea distinta (aquí SÍ hay caja real detrás, solo que no es caja operativa).
    grupo89_pasivo_no_corriente_actual = actual.pasivos_por_impuesto_diferido_eur + actual.deuda_grupo_largo_eur
    grupo89_pasivo_no_corriente_anterior = anterior.pasivos_por_impuesto_diferido_eur + anterior.deuda_grupo_largo_eur
    a3f = (actual.balance_eur["otras_deudas_largo"] - grupo89_pasivo_no_corriente_actual) - (
        anterior.balance_eur["otras_deudas_largo"] - grupo89_pasivo_no_corriente_anterior
    )

    a4a = -actual.pyg_eur["gastos_financieros"]
    a4b = 0.0
    a4c = actual.pyg_eur["ingresos_financieros"]
    a4d = -actual.pyg_eur["impuesto_beneficios"]
    a4e = 0.0

    a5 = a1 + a2a + a2e + a2g + a2h + a2k + a3a + a3b + a3c + a3d + a3e + a3f + a4a + a4b + a4c + a4d + a4e

    # B) Inversión — desglose por categoría (material/intangible/inversiones_inmobiliarias/otros
    # financieros) a partir del DELTA REAL de cada categoría en `activo_no_corriente_desglose_eur`
    # (mismo patrón que `a3a_existencias`/`a3b_deudores`/`a3d_acreedores`), NO del perfil % fijo
    # aplicado al agregado — corrección de atribución (ver decisiones_plausibilidad.md, entrada
    # de este encargo): desde #100, `otros_financieros` crece de forma TOTALMENTE independiente
    # (proporcional a su propio saldo del año anterior, ajeno a capex/amortización/bajas) mientras
    # material/intangible/inversiones_inmobiliarias comparten un único "pool" amortizable que SÍ
    # seguía el capex-amortización real desde #98 — repartir el delta AGREGADO con el perfil fijo
    # de 4 categorías (que incluye el peso de otros_financieros) desalineaba cada línea individual
    # del importe real que el Balance ya mostraba para esa categoría concreta, aunque el subtotal
    # B.8 siguiera cuadrando por construcción. `otros_financieros` no participa nunca en
    # adquisición/capex/amortización/bajas (motor/amortizacion.py: "nunca amortizable"; motor/
    # evolucion_arquetipo.py: crece con su propia fórmula, `otros_financieros_eur = anterior × (1
    # + crecimiento_ventas)`) — su delta real en el Balance ES, directamente, el flujo de
    # inversión orgánico de esa categoría, sin ningún ajuste adicional.
    delta_otros_financieros = (
        actual.activo_no_corriente_desglose_eur["otros_financieros"]
        - anterior.activo_no_corriente_desglose_eur["otros_financieros"]
    )
    b_otros_financieros = -delta_otros_financieros

    # Las otras 3 categorías SÍ comparten un único "pool" amortizable (`activo_no_corriente_
    # amortizable_eur`, motor/evolucion_arquetipo.py) que sigue el capex-amortización real —
    # adquisición (18) se pliega ahí entera (nunca en otros_financieros, ver arriba) y se excluye
    # aquí con el mismo criterio que el agregado de antes (`- actual.incremento...`), igual que
    # las bajas (`+ actual.baja_valor_en_libros_eur`) y la amortización real (`+ actual.pyg_eur[
    # "amortizaciones"]`, para recuperar el capex BRUTO — ver decisiones_plausibilidad.md #98,
    # cancelado exactamente contra A.2.a). El resultado (`delta_amortizable_organico`) se reparte
    # entre las 3 categorías con el MISMO peso relativo fijo que usa `motor/evolucion_arquetipo.py`
    # para construir `activo_no_corriente_desglose_eur` cada año (`activo_no_corriente_perfil_pct`
    # renormalizado a estas 3 claves, ya que su reparto real en el Balance ES ese peso relativo
    # aplicado al pool — no un dato independiente que haya que re-derivar).
    material_actual = actual.activo_no_corriente_desglose_eur["material"]
    intangible_actual = actual.activo_no_corriente_desglose_eur["intangible"]
    inversiones_inmobiliarias_actual = actual.activo_no_corriente_desglose_eur["inversiones_inmobiliarias"]
    amortizable_actual = material_actual + intangible_actual + inversiones_inmobiliarias_actual
    amortizable_anterior = (
        anterior.activo_no_corriente_desglose_eur["material"]
        + anterior.activo_no_corriente_desglose_eur["intangible"]
        + anterior.activo_no_corriente_desglose_eur["inversiones_inmobiliarias"]
    )
    delta_amortizable_organico = (
        amortizable_actual
        - actual.incremento_activo_adquisicion_eur
        + actual.baja_valor_en_libros_eur
        + actual.pyg_eur["amortizaciones"]
        - amortizable_anterior
    )
    perfil = actual.activo_no_corriente_perfil_pct
    peso_amortizable_total = perfil["material"] + perfil["intangible"] + perfil["inversiones_inmobiliarias"]
    b_intangible = -(perfil["intangible"] / peso_amortizable_total) * delta_amortizable_organico
    b_material = -(perfil["material"] / peso_amortizable_total) * delta_amortizable_organico
    b_inversiones_inmobiliarias = -(perfil["inversiones_inmobiliarias"] / peso_amortizable_total) * delta_amortizable_organico
    b_adquisicion = -actual.incremento_activo_adquisicion_eur
    b_enajenacion_inmovilizado = actual.baja_valor_venta_eur
    b_prestamo_grupo = -(actual.inversion_grupo_largo_eur - anterior.inversion_grupo_largo_eur)

    b8 = (
        b_intangible + b_material + b_inversiones_inmobiliarias + b_otros_financieros
        + b_adquisicion + b_enajenacion_inmovilizado + b_prestamo_grupo
    )

    # C) Financiación — `c10` excluye el derivado de la cobertura (cuando es PASIVO): desde el
    # cuarto lote de desglose de balance vive dentro de `deudas_fin_largo` (línea "IV. Derivados"
    # de "Deudas financieras", ver motor/evolucion_arquetipo.py, `_construir_balance`) en vez de
    # `otras_deudas_largo` (aproximación anterior, donde SÍ se excluía de A.3.f, ver arriba) —
    # mismo tratamiento de siempre (sin flujo de caja propio, valoración a mercado pura), solo
    # cambia qué línea del EFE es quien la excluye. El total del EFE no cambia en ningún caso: es
    # el mismo importe excluido, solo se mueve de fórmula.
    derivados_pasivo_actual = max(0.0, -actual.cobertura_valor_swap_eur)
    derivados_pasivo_anterior = max(0.0, -anterior.cobertura_valor_swap_eur)
    deuda_financiera_actual = (
        actual.balance_eur["deudas_fin_largo"] - derivados_pasivo_actual + actual.balance_eur["deudas_fin_corto"]
    )
    deuda_financiera_anterior = (
        anterior.balance_eur["deudas_fin_largo"] - derivados_pasivo_anterior + anterior.balance_eur["deudas_fin_corto"]
    )
    c10 = deuda_financiera_actual - deuda_financiera_anterior
    # C.9 ("Cobros y pagos por instrumentos de patrimonio... subvenciones, donaciones y legados
    # recibidos") — antes siempre 0.0 por no existir ningún mecanismo detrás; el encargo de
    # coberturas/subvenciones lo rellena con el cobro real de caja del año de concesión (ver
    # motor/coberturas_subvenciones.py y motor/evolucion_arquetipo.py — el importe se añade
    # directamente a `disponible` ese año, C.9 es la contrapartida que lo explica en el EFE).
    c9 = actual.subvencion_importe_concedido_eur
    # C.10.c ("Deudas con empresas del grupo y asociadas") — arquetipo 20, "financiación recibida
    # de grupo": variación de `deuda_grupo_largo_eur`, deliberadamente FUERA de `c10` (esa masa
    # nunca alimenta gastos_financieros, ver motor/evolucion_arquetipo.py — mezclarla con c10
    # confundiría "deuda con coste" con "deuda sin coste" en la misma línea).
    c10c = actual.deuda_grupo_largo_eur - anterior.deuda_grupo_largo_eur
    c11a = -(actual.apalancamiento_extra_eur + actual.payout_dividendos_eur)
    c12 = c9 + c10 + c10c + c11a

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
        a2e_deterioro_enajenacion_inmovilizado=a2e,
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
        b6_enajenacion_inmovilizado=b_enajenacion_inmovilizado,
        b6c_prestamo_empresas_grupo=b_prestamo_grupo,
        b8_flujo_inversion=b8,
        c9_instrumentos_patrimonio=c9,
        c10_variacion_neta_deuda_financiera=c10,
        c10c_empresas_grupo=c10c,
        c11a_dividendos=c11a,
        c12_flujo_financiacion=c12,
        d_efecto_tipo_cambio=d,
        e_variacion_neta_efectivo=e,
        disponible_inicial=disponible_inicial,
        disponible_final=disponible_final,
        descuadre_eur=descuadre,
    )
