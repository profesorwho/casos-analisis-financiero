"""Documento de solución del caso (encargo #113) — 9 secciones didácticas construidas SOLO a
partir de datos ya generados del caso (`evolucion.plausibilidad`, `balance_eur`/`pyg_eur`,
`generar_efe`, `motor.calendario_deuda`) — no recalcula ni sortea nada del motor. Ver
`renderer/generar_solucion_caso.py` para el punto de entrada y `docs/decisiones_plausibilidad.md`
#113 para la verificación de las 2 piezas de cálculo NUEVAS de este módulo (PMM, DuPont)."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from render_pdf import fmt_eur
from catalogo_narrativo_arquetipos import CATALOGO_NARRATIVO_ARQUETIPOS

styles = getSampleStyleSheet()
titulo_seccion = ParagraphStyle("TituloSeccionSolucion", parent=styles["Heading1"], fontSize=14, spaceAfter=6)
subtitulo_seccion = ParagraphStyle("SubtituloSeccionSolucion", parent=styles["Heading3"], fontSize=10.5, spaceBefore=8, spaceAfter=3)
cuerpo = ParagraphStyle("CuerpoSolucion", parent=styles["Normal"], fontSize=9, leading=13, spaceAfter=6, alignment=4)
aviso = ParagraphStyle("AvisoSolucion", parent=cuerpo, fontName="Helvetica-Oblique", textColor=colors.HexColor("#666666"), fontSize=8)
encabezado_tabla = ParagraphStyle("EncabezadoTablaSolucion", parent=cuerpo, fontSize=7.5, leading=8.5, fontName="Helvetica-Bold")

AÑOS = (2023, 2024, 2025)

# --------------------------------------------------------------------------------------------
# Nombres legibles de los ratios que aparecen en las tablas de este documento — no todos los 23
# de RATIOS_PLAUSIBILIDAD_SEÑALIZABLES aparecen aquí, solo los usados en alguna sección.
# --------------------------------------------------------------------------------------------
RATIO_NOMBRE_LEGIBLE: dict[str, str] = {
    "ratios.liquidez": "Liquidez general (AC / PC)",
    "ratios.tesoreria": "Prueba ácida (Realizable+Disponible / PC)",
    "ratios.disponibilidad_ratio": "Disponibilidad (Disponible / PC)",
    "ratios.fm_ventas": "Fondo de maniobra / Ventas",
    "ratios.fm_activo": "Fondo de maniobra / Activo total",
    "ratios.endeudamiento": "Endeudamiento (Pasivo total / Activo total)",
    "ratios.calidad_deuda": "Calidad de la deuda (Pasivo corriente / Deudas totales)",
    "ratios.coste_deuda": "Coste de la deuda (informativo, ver aviso)",
    "ratios.cobertura_gastos_fin": "Cobertura de gastos financieros (informativo, ver aviso)",
    "ratios.capacidad_devolucion": "Capacidad de devolución de la deuda",
    "ratios.rotacion_activo": "Rotación del activo total",
    "ratios.rotacion_activo_no_corriente": "Rotación del activo no corriente",
    "ratios.rotacion_activo_corriente": "Rotación del activo corriente",
    "ratios.rotacion_existencias": "Rotación de existencias",
    "ratios.plazo_existencias": "Plazo medio de existencias (días)",
    "ratios.cobro_dias": "Plazo medio de cobro (días)",
    "ratios.pago_dias": "Plazo medio de pago (informativo, ver aviso)",
    "ratios.financiacion_clientes": "Financiación de clientes por proveedores",
    "ratios.roi": "Rentabilidad económica (ROI)",
    "ratios.roe": "Rentabilidad financiera (ROE)",
    "ratios.flujo_caja_activo": "Flujo de caja / Activo total",
    "ratios.flujo_caja_ventas": "Flujo de caja / Ventas",
    "ratios.beneficio_empleado": "Beneficio por empleado (miles €)",
    "ratios.gastos_personal_empleado": "Gasto de personal por empleado (miles €)",
    "pyg.baii_pct": "BAII / Ingresos de explotación (%)",
    "pyg.margen_bruto_pct": "Margen bruto / Ingresos de explotación (%)",
}

# Ratios "ancla" verificados por arquetipo (ver catalogo_narrativo_arquetipos.py para el detalle
# de la verificación) — usados en la sección 9 para unir arquetipos con señales. Vacío = el
# arquetipo no tiene un efecto claramente apreciable en los 23 ratios de plausibilidad (20, 21) o
# no tiene efecto numérico en absoluto (memoria_pura: 7, 19, 22) — declarado así explícitamente,
# no forzado.
ARQUETIPO_RATIOS_RELACIONADOS: dict[str, tuple[str, ...]] = {
    "crecimiento_destruccion_caja": ("ratios.rotacion_existencias", "ratios.cobro_dias"),
    "beneficio_sin_cash_flow": ("ratios.disponibilidad_ratio",),
    "aumento_nof": ("ratios.rotacion_existencias", "ratios.cobro_dias"),
    "deterioro_ciclo_caja": ("ratios.cobro_dias",),
    "exceso_stock": ("ratios.rotacion_existencias", "ratios.plazo_existencias"),
    "aumento_clientes": ("ratios.cobro_dias",),
    "dependencia_pocos_clientes": (),
    "refinanciacion": ("ratios.calidad_deuda",),
    "apalancamiento": ("ratios.endeudamiento",),
    "mejora_ebitda": ("pyg.baii_pct",),
    "mejora_margen": ("pyg.margen_bruto_pct",),
    "resultado_extraordinario": ("pyg.baii_pct",),
    "roe_elevado_apalancamiento": ("ratios.endeudamiento", "ratios.roe"),
    "riesgo_liquidez_pese_beneficio": ("ratios.disponibilidad_ratio",),
    "riesgo_refinanciacion": ("ratios.calidad_deuda",),
    "capex_elevado": ("ratios.rotacion_activo_no_corriente",),
    "adquisicion": ("ratios.rotacion_activo_no_corriente", "ratios.endeudamiento"),
    "activo_mantenido_venta": (),
    "operaciones_vinculadas": (),
    "coberturas": (),
    "informacion_relevante_memoria": (),
}


def _tabla(filas, anchos, encabezado=True):
    if encabezado:
        filas = [[Paragraph(c, encabezado_tabla) if isinstance(c, str) else c for c in filas[0]]] + filas[1:]
    t = Table(filas, colWidths=anchos)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _fmt_pct(valor: float | None) -> str:
    return "n/d" if valor is None else f"{valor * 100:.1f}%"


def _fmt_pct_ya_100(valor: float | None) -> str:
    """Para valores que YA vienen en base 100 (pyg_pct)."""
    return "n/d" if valor is None else f"{valor:.1f}%"


def _fmt_num(valor: float | None, decimales: int = 2) -> str:
    return "n/d" if valor is None else f"{valor:.{decimales}f}"


def _fmt_dias(valor: float | None) -> str:
    return "n/d" if valor is None else f"{valor:.0f} días"


# --------------------------------------------------------------------------------------------
# Parseo de arquetipos activos — ver docstring de motor/evolucion_arquetipo.py,
# `generar_evolucion_combinada`/`motor.memoria.generar_caso_combinado`: formato "id" simple si
# solo hay UN arquetipo en total (cuantitativo o memoria_pura), "id1+id2+..." / "id1:int1+..."
# si hay 2 o más — SIEMPRE en orden alfabético de id.
# --------------------------------------------------------------------------------------------

def parsear_arquetipos_activos(evolucion) -> list[tuple[str, str]]:
    ids = evolucion.arquetipo.split("+")
    if len(ids) == 1:
        return [(ids[0], evolucion.intensidad)]
    pares = []
    for par in evolucion.intensidad.split("+"):
        arquetipo_id, intensidad = par.split(":")
        pares.append((arquetipo_id, intensidad))
    return pares


# --------------------------------------------------------------------------------------------
# Cálculos NUEVOS y puramente aritméticos sobre ratios YA existentes — sin sortear nada, sin
# ancla de catálogo propia (ver docs/decisiones_plausibilidad.md #113 para la verificación).
# --------------------------------------------------------------------------------------------

def calcular_pmm(valores_ratios: dict[str, float | None]) -> tuple[float | None, float | None]:
    """PMM económico = plazo_existencias + cobro_dias; PMM financiero = económico − pago_dias.
    `None` si falta cualquier componente (denominador 0 en el ratio de origen). El PMM
    financiero PUEDE ser negativo — la empresa cobra antes de lo que tarda en pagar a sus
    proveedores, una situación real y no necesariamente anómala (financiación neta gratuita del
    ciclo de explotación vía proveedores) — NO se trata aquí como una anomalía por sí sola."""
    plazo_existencias = valores_ratios.get("ratios.plazo_existencias")
    cobro_dias = valores_ratios.get("ratios.cobro_dias")
    pago_dias = valores_ratios.get("ratios.pago_dias")
    if plazo_existencias is None or cobro_dias is None:
        return None, None
    pmm_economico = plazo_existencias + cobro_dias
    pmm_financiero = pmm_economico - pago_dias if pago_dias is not None else None
    return pmm_economico, pmm_financiero


def calcular_apalancamiento_financiero(balance_eur: dict[str, float]) -> float | None:
    """Identidad contable Pasivo total / Patrimonio neto — sin ancla de catálogo, es una
    definición, no una estimación. `None` si el PN es 0 (caso degenerado)."""
    pasivo_total = balance_eur["pasivo_no_corriente"] + balance_eur["pasivo_corriente"]
    pn = balance_eur["patrimonio_neto"]
    return pasivo_total / pn if pn else None


def calcular_rf_dupont(roi: float | None, balance_eur: dict[str, float], pyg_eur: dict[str, float]) -> float | None:
    """Descomposición DuPont de la rentabilidad financiera — **fórmula corregida tras el
    protocolo de parada del encargo #113** (ver decisiones_plausibilidad.md #113 para el
    historial completo): la fórmula ORIGINAL del encargo (`RF = RE + (RE − coste_deuda) ×
    Pasivo_total/PN`) NO es una identidad — desviación máxima de 9,17 puntos porcentuales en un
    barrido de control de 216 casos — por dos motivos: (a) mezcla una base de apalancamiento
    (Pasivo TOTAL, con deuda comercial sin coste) con un coste de la deuda que el motor solo
    define sobre deuda FINANCIERA (`ratios.coste_deuda = gastos_financieros/deuda_financiera`);
    (b) ignora el efecto fiscal (ROE es una magnitud DESPUÉS de impuestos, ROI y coste_deuda son
    ANTES).

    Fórmula corregida, derivada ALGEBRAICAMENTE (no por tanteo) a partir de las identidades
    EXACTAS del propio motor — `resultado_ejercicio = bai − impuesto_beneficios` y
    `bai = baii + ingresos_financieros − gastos_financieros` (`motor/empresa_base.py`,
    `_completar_pyg_con_deuda`; ambas verificadas exactas sobre casos reales, incluidos los que
    tienen `coberturas`/`capex_elevado` activo con ajuste de grupo89 en `_evaluar`) —
    sustituyendo `ratios.roi = baii/activo_total` y despejando:

        RF = ROI × (1 + Pasivo_total/PN) + Ingresos_financieros/PN − Gastos_financieros/PN
             − Impuesto_beneficios/PN

    Usa `gastos_financieros`/`impuesto_beneficios` en EUROS directamente (no
    `ratios.coste_deuda` × una base ni un tipo impositivo recompuesto) — esto es DELIBERADO y es
    la clave de por qué esta versión SÍ es exacta incondicionalmente: `impuesto_beneficios` real
    del caso YA excluye el efecto de grupo89 de su base imponible (subgrupo 83, liquidado aparte
    — ver `motor/evolucion_arquetipo.py::_evaluar`, docstring del ajuste post-hoc) sin que haga
    falta conocer ni reproducir esa exclusión aquí: tomar el valor YA calculado por el motor,
    en vez de recomponerlo a partir de un tipo efectivo, es lo que hace que la identidad se
    mantenga también en los casos con cobertura/subvención activa. **Verificado: 6.480
    comprobaciones (27 sectores × 2 segmentos × 8 semillas × 5 configuraciones, los 3 años),
    desviación máxima 1,71e-13 (ruido de punto flotante) — 0 casos con residuo** — ver
    tests/test_mapeo_solucion.py::test_identidad_dupont_sobre_barrido y decisiones_
    plausibilidad.md #113. `None` si el PN es 0 (caso degenerado) o `roi` es `None`."""
    pn = balance_eur["patrimonio_neto"]
    if roi is None or not pn:
        return None
    pasivo_total = balance_eur["pasivo_no_corriente"] + balance_eur["pasivo_corriente"]
    return (
        roi * (1 + pasivo_total / pn)
        + pyg_eur["ingresos_financieros"] / pn
        - pyg_eur["gastos_financieros"] / pn
        - pyg_eur["impuesto_beneficios"] / pn
    )


# --------------------------------------------------------------------------------------------
# Sección 1 — Resumen ejecutivo
# --------------------------------------------------------------------------------------------

GRUPOS_SEMAFORO: dict[str, tuple[str, ...]] = {
    "Liquidez": ("ratios.liquidez", "ratios.tesoreria", "ratios.disponibilidad_ratio", "ratios.fm_ventas", "ratios.fm_activo"),
    "Solvencia": ("ratios.endeudamiento", "ratios.calidad_deuda", "ratios.capacidad_devolucion"),
    "Rentabilidad": ("ratios.roi", "ratios.roe", "pyg.baii_pct", "pyg.margen_bruto_pct"),
}


def _semaforo(plausibilidad, grupo_ratios: tuple[str, ...]) -> str:
    for señal in plausibilidad.señales:
        if señal.ratio in grupo_ratios:
            return "CON DESVIACIONES frente al sector"
    return "sin desviaciones frente al sector"


def seccion_1_resumen_ejecutivo(evolucion, arquetipos_activos: list[tuple[str, str]]) -> list:
    flow = [Paragraph("1. Resumen ejecutivo", titulo_seccion)]
    flow.append(Paragraph(
        f"Caso generado con semilla {evolucion.semilla}, sector \"{evolucion.sector_nombre}\" "
        f"({evolucion.sector_codigo}), segmento \"{evolucion.segmento}\".", cuerpo
    ))

    flow.append(Paragraph("Lo que el caso incorpora", subtitulo_seccion))
    for arquetipo_id, intensidad in arquetipos_activos:
        descripcion = CATALOGO_NARRATIVO_ARQUETIPOS.get(arquetipo_id, "(sin descripción en el catálogo)")
        flow.append(Paragraph(f"<b>{arquetipo_id}</b> (intensidad: {intensidad}) — {descripcion}", cuerpo))

    flow.append(Paragraph("Semáforo por bloque (frente a los datos reales del sector)", subtitulo_seccion))
    filas = [["Bloque", "Estado"]]
    for nombre_grupo, ratios_grupo in GRUPOS_SEMAFORO.items():
        filas.append([nombre_grupo, _semaforo(evolucion.plausibilidad, ratios_grupo)])
    flow.append(_tabla(filas, anchos=[6 * cm, 10 * cm]))

    n_señales = len(evolucion.plausibilidad.señales)
    ids_arquetipos = ", ".join(aid for aid, _ in arquetipos_activos)
    flow.append(Paragraph(
        f"<b>Diagnóstico.</b> El caso incorpora {len(arquetipos_activos)} arquetipo(s): "
        f"{ids_arquetipos}. Se han detectado {n_señales} desviación(es) frente al comportamiento "
        f"típico del sector en el barrido completo de ratios de los 3 ejercicios (sección 8). "
        "Las secciones siguientes desarrollan cada bloque del análisis y, en la sección 9, "
        "conectan cada arquetipo incorporado con las señales que explica.", cuerpo
    ))
    return flow


# --------------------------------------------------------------------------------------------
# Sección 2 — Análisis patrimonial
# --------------------------------------------------------------------------------------------

MASAS_ACTIVO = (("activo_no_corriente", "Activo no corriente"), ("activo_corriente", "Activo corriente"))
MASAS_ACTIVO_DETALLE = (("existencias", "  Existencias"), ("realizable", "  Realizable"), ("disponible", "  Disponible"))
MASAS_PN_PASIVO = (
    ("patrimonio_neto", "Patrimonio neto"),
    ("pasivo_no_corriente", "Pasivo no corriente"),
    ("pasivo_corriente", "Pasivo corriente"),
)


def _activo_total(balance_eur: dict) -> float:
    return balance_eur["activo_no_corriente"] + balance_eur["activo_corriente"]


def seccion_2_analisis_patrimonial(ejercicios: dict) -> list:
    flow = [Paragraph("2. Análisis patrimonial", titulo_seccion)]

    flow.append(Paragraph("Porcentajes verticales (cada masa sobre el activo total = PN+Pasivo total)", subtitulo_seccion))
    filas = [["Masa"] + [str(a) for a in AÑOS]]
    for clave, etiqueta in MASAS_ACTIVO + MASAS_ACTIVO_DETALLE + MASAS_PN_PASIVO:
        fila = [etiqueta]
        for año in AÑOS:
            total = _activo_total(ejercicios[año].balance_eur)
            fila.append(_fmt_pct(ejercicios[año].balance_eur[clave] / total) if total else "n/d")
        filas.append(fila)
    flow.append(_tabla(filas, anchos=[6.5 * cm, 3.9 * cm, 3.9 * cm, 3.9 * cm]))

    flow.append(Paragraph("Porcentajes horizontales (variación interanual)", subtitulo_seccion))
    filas = [["Masa", "2023 → 2024", "2024 → 2025"]]
    for clave, etiqueta in MASAS_ACTIVO + MASAS_ACTIVO_DETALLE + MASAS_PN_PASIVO:
        fila = [etiqueta]
        for a0, a1 in ((2023, 2024), (2024, 2025)):
            v0 = ejercicios[a0].balance_eur[clave]
            v1 = ejercicios[a1].balance_eur[clave]
            fila.append(_fmt_pct((v1 - v0) / v0) if v0 else "n/d")
        filas.append(fila)
    flow.append(_tabla(filas, anchos=[6.5 * cm, 5.85 * cm, 5.85 * cm]))

    flow.append(Paragraph("Fondo de maniobra (Activo corriente − Pasivo corriente)", subtitulo_seccion))
    fms = {}
    filas = [["", *[str(a) for a in AÑOS]]]
    fila = ["Fondo de maniobra (€)"]
    for año in AÑOS:
        b = ejercicios[año].balance_eur
        fm = b["activo_corriente"] - b["pasivo_corriente"]
        fms[año] = fm
        fila.append(fmt_eur(fm))
    filas.append(fila)
    flow.append(_tabla(filas, anchos=[6.5 * cm, 3.9 * cm, 3.9 * cm, 3.9 * cm]))

    if fms[2025] < 0:
        interpretacion = (
            "El fondo de maniobra es NEGATIVO en 2025: el pasivo corriente supera al activo "
            "corriente — la empresa financia parte de su activo no corriente (o simplemente "
            "arrastra un déficit de circulante) con pasivo exigible a corto plazo, una posición "
            "de riesgo si no hay una renovación fluida de ese pasivo."
        )
    elif fms[2025] < fms[2023]:
        interpretacion = (
            "El fondo de maniobra es positivo en 2025 pero HA DISMINUIDO respecto a 2023 — la "
            "holgura de circulante se ha reducido a lo largo del caso, aunque sin llegar a ser "
            "negativa."
        )
    else:
        interpretacion = (
            "El fondo de maniobra es positivo y se ha mantenido o ampliado a lo largo del caso — "
            "cobertura financiera del circulante razonable, sin tensión aparente en la "
            "estructura de plazos del balance."
        )
    flow.append(Paragraph(interpretacion, cuerpo))
    return flow


# --------------------------------------------------------------------------------------------
# Sección 3 — Liquidez a corto plazo
# --------------------------------------------------------------------------------------------

def seccion_3_liquidez(evolucion) -> list:
    flow = [Paragraph("3. Análisis financiero a corto plazo (liquidez)", titulo_seccion)]
    filas = [["Ratio", *[str(a) for a in AÑOS]]]
    for ratio in ("ratios.liquidez", "ratios.tesoreria", "ratios.disponibilidad_ratio"):
        fila = [RATIO_NOMBRE_LEGIBLE[ratio]]
        for año in AÑOS:
            fila.append(_fmt_num(evolucion.plausibilidad.valores_por_año[año].get(ratio)))
        filas.append(fila)
    flow.append(_tabla(filas, anchos=[7 * cm, 3.8 * cm, 3.8 * cm, 3.8 * cm]))

    flow.append(Paragraph("Período medio de maduración (PMM)", subtitulo_seccion))
    filas = [["", *[str(a) for a in AÑOS]]]
    fila_eco = ["PMM económico (días)"]
    fila_fin = ["PMM financiero (días)"]
    for año in AÑOS:
        pmm_eco, pmm_fin = calcular_pmm(evolucion.plausibilidad.valores_por_año[año])
        fila_eco.append(_fmt_dias(pmm_eco))
        fila_fin.append(_fmt_dias(pmm_fin))
    filas.append(fila_eco)
    filas.append(fila_fin)
    flow.append(_tabla(filas, anchos=[7 * cm, 3.8 * cm, 3.8 * cm, 3.8 * cm]))
    flow.append(Paragraph(
        "El PMM económico es el tiempo que transcurre desde que se invierte en existencias "
        "hasta que se cobra la venta (plazo de existencias + plazo de cobro). El PMM financiero "
        "resta el plazo de pago a proveedores: <b>puede ser negativo de forma legítima</b> "
        "cuando la empresa cobra a sus clientes antes de lo que tarda en pagar a sus "
        "proveedores — no se trata aquí como una anomalía en sí misma, es un dato informativo "
        "más sobre la posición de caja del ciclo de explotación. El plazo de pago (`ratios.pago_"
        "dias`) es un ratio informativo del catálogo (ver aviso más abajo) — su ancla de sector "
        "está contaminada por un denominador poco fiable en los sectores de servicios, así que "
        "el PMM financiero debe leerse con esa cautela.", aviso
    ))
    return flow


# --------------------------------------------------------------------------------------------
# Sección 4 — Endeudamiento y solvencia
# --------------------------------------------------------------------------------------------

CATEGORIAS_CALENDARIO_NO_COMERCIALES = (
    "entidades_credito", "arrendamiento_financiero", "obligaciones", "otros_pasivos_financieros",
    "derivados", "acreedores_inmovilizado", "fianzas_deudas_socios", "remanente_otras_deudas",
)


def seccion_4_endeudamiento(evolucion, calendario) -> list:
    flow = [Paragraph("4. Análisis financiero a largo plazo (endeudamiento y solvencia)", titulo_seccion)]
    filas = [["Ratio", *[str(a) for a in AÑOS]]]
    for ratio in ("ratios.endeudamiento", "ratios.calidad_deuda", "ratios.coste_deuda",
                  "ratios.cobertura_gastos_fin", "ratios.capacidad_devolucion"):
        fila = [RATIO_NOMBRE_LEGIBLE[ratio]]
        for año in AÑOS:
            fila.append(_fmt_num(evolucion.plausibilidad.valores_por_año[año].get(ratio)))
        filas.append(fila)
    flow.append(_tabla(filas, anchos=[7 * cm, 3.8 * cm, 3.8 * cm, 3.8 * cm]))
    flow.append(Paragraph(
        "El coste de la deuda y la cobertura de gastos financieros son ratios INFORMATIVOS: su "
        "ancla de catálogo está contaminada (mezclan en el denominador partidas ajenas al "
        "interés real de la deuda) — se muestran por completitud, no como señal dura de "
        "plausibilidad.", aviso
    ))

    tramos_2025 = calendario.vencimientos_por_año[2025]
    total_un_año = sum(tramos_2025[c].un_año for c in CATEGORIAS_CALENDARIO_NO_COMERCIALES)
    total_deuda = sum(tramos_2025[c].total for c in CATEGORIAS_CALENDARIO_NO_COMERCIALES)
    if total_deuda > 0 and total_un_año / total_deuda > 0.5:
        flow.append(Paragraph(
            f"<b>Concentración de vencimientos.</b> El {total_un_año / total_deuda:.0%} de la "
            "deuda no comercial de 2025 vence en el próximo ejercicio (tramo \"1 año\") — "
            "consulta el calendario de vencimientos completo por categoría en la Nota 7 de la "
            "Memoria (encargo #112) para valorar el riesgo de refinanciación.", cuerpo
        ))
    return flow


# --------------------------------------------------------------------------------------------
# Sección 5 — Análisis económico (cuenta de resultados)
# --------------------------------------------------------------------------------------------

PARTIDAS_ESTRUCTURA_GASTOS = (
    ("consumos_explotacion", "Consumos de explotación"),
    ("gastos_personal", "Gastos de personal"),
    ("otros_gastos_explot", "Otros gastos de explotación"),
    ("amortizaciones", "Amortizaciones"),
)


def seccion_5_analisis_economico(ejercicios, evolucion) -> list:
    flow = [Paragraph("5. Análisis económico (cuenta de resultados)", titulo_seccion)]
    filas = [["", *[str(a) for a in AÑOS]]]
    fila_margen = ["Margen bruto / Ingresos explot."]
    fila_baii = ["BAII / Ingresos explot."]
    fila_resultado = ["Resultado del ejercicio (€)"]
    for año in AÑOS:
        fila_margen.append(_fmt_pct_ya_100(evolucion.plausibilidad.valores_por_año[año].get("pyg.margen_bruto_pct")))
        fila_baii.append(_fmt_pct_ya_100(evolucion.plausibilidad.valores_por_año[año].get("pyg.baii_pct")))
        fila_resultado.append(fmt_eur(ejercicios[año].pyg_eur["resultado_ejercicio"]))
    filas.append(fila_margen)
    filas.append(fila_baii)
    filas.append(fila_resultado)
    flow.append(_tabla(filas, anchos=[7 * cm, 3.8 * cm, 3.8 * cm, 3.8 * cm]))

    flow.append(Paragraph("Estructura de gastos principales (% sobre ingresos de explotación)", subtitulo_seccion))
    filas = [["Partida", *[str(a) for a in AÑOS]]]
    for clave, etiqueta in PARTIDAS_ESTRUCTURA_GASTOS:
        fila = [etiqueta]
        for año in AÑOS:
            fila.append(_fmt_pct_ya_100(ejercicios[año].pyg_pct[clave]))
        filas.append(fila)
    flow.append(_tabla(filas, anchos=[7 * cm, 3.8 * cm, 3.8 * cm, 3.8 * cm]))
    return flow


# --------------------------------------------------------------------------------------------
# Sección 6 — Rentabilidad (ROI/ROE + descomposición DuPont)
# --------------------------------------------------------------------------------------------

def seccion_6_rentabilidad(evolucion, ejercicios) -> list:
    flow = [Paragraph("6. Análisis de la rentabilidad", titulo_seccion)]
    filas = [["Ratio", *[str(a) for a in AÑOS]]]
    for ratio in ("ratios.roi", "ratios.roe"):
        fila = [RATIO_NOMBRE_LEGIBLE[ratio]]
        for año in AÑOS:
            fila.append(_fmt_pct(evolucion.plausibilidad.valores_por_año[año].get(ratio)))
        filas.append(fila)
    flow.append(_tabla(filas, anchos=[7 * cm, 3.8 * cm, 3.8 * cm, 3.8 * cm]))

    flow.append(Paragraph("Descomposición DuPont de la rentabilidad financiera", subtitulo_seccion))
    flow.append(Paragraph(
        "RF = ROI × (1 + Pasivo total/PN) + Ingresos financieros/PN − Gastos financieros/PN − "
        "Impuesto sobre beneficios/PN. Es una identidad algebraica exacta (verificado en 6.480 "
        "comprobaciones, desviación máxima 1,7e-13 — ver decisiones_plausibilidad.md #113): la "
        "columna \"RF calculada\" coincide con la \"Rentabilidad financiera (ROE)\" de la tabla "
        "anterior en todo ejercicio con patrimonio neto distinto de cero.", cuerpo
    ))
    filas = [["", *[str(a) for a in AÑOS]]]
    fila_apal = ["Apalancamiento (Pasivo total/PN)"]
    fila_rf = ["RF calculada (DuPont)"]
    for año in AÑOS:
        valores = evolucion.plausibilidad.valores_por_año[año]
        apalancamiento = calcular_apalancamiento_financiero(ejercicios[año].balance_eur)
        rf = calcular_rf_dupont(valores.get("ratios.roi"), ejercicios[año].balance_eur, ejercicios[año].pyg_eur)
        fila_apal.append(_fmt_num(apalancamiento))
        fila_rf.append(_fmt_pct(rf))
    filas.append(fila_apal)
    filas.append(fila_rf)
    flow.append(_tabla(filas, anchos=[7 * cm, 3.8 * cm, 3.8 * cm, 3.8 * cm]))
    return flow


# --------------------------------------------------------------------------------------------
# Sección 7 — Estado de Flujos de Efectivo
# --------------------------------------------------------------------------------------------

def _patron_efe(efe) -> str:
    explotacion, inversion, financiacion = efe.a5_flujo_explotacion, efe.b8_flujo_inversion, efe.c12_flujo_financiacion
    if explotacion > 0 and inversion < 0 and financiacion < 0:
        return "La explotación genera caja suficiente para invertir y, además, reducir la financiación externa neta — patrón saludable."
    if explotacion > 0 and inversion < 0 and financiacion > 0:
        return "La explotación genera caja, pero la empresa financia inversión ADICIONAL con deuda nueva (o aportaciones) — patrón de crecimiento apalancado."
    if explotacion <= 0:
        return "La explotación NO genera caja este ejercicio (o la consume) — cualquier inversión o servicio de la deuda depende de financiación externa o del disponible acumulado."
    if inversion > 0:
        return "El flujo de inversión es positivo — el ejercicio se caracteriza por desinversión neta (venta de activos), no por nueva inversión."
    return "Patrón mixto, sin un caso típico claro — revisa los 3 importes de la tabla directamente."


def seccion_7_efe(efes: dict) -> list:
    flow = [Paragraph("7. Análisis del Estado de Flujos de Efectivo", titulo_seccion)]
    filas = [["", "2024", "2025"]]
    for etiqueta, campo in [
        ("A.5) Flujo de explotación", "a5_flujo_explotacion"),
        ("B.8) Flujo de inversión", "b8_flujo_inversion"),
        ("C.12) Flujo de financiación", "c12_flujo_financiacion"),
        ("Variación neta del efectivo", "e_variacion_neta_efectivo"),
    ]:
        filas.append([etiqueta] + [fmt_eur(getattr(efes[a], campo)) for a in (2024, 2025)])
    flow.append(_tabla(filas, anchos=[7.5 * cm, 5.45 * cm, 5.45 * cm]))
    for año in (2024, 2025):
        flow.append(Paragraph(f"<b>{año}:</b> {_patron_efe(efes[año])}", cuerpo))
    return flow


# --------------------------------------------------------------------------------------------
# Sección 8 — Señales de alerta
# --------------------------------------------------------------------------------------------

def _texto_señal(señal) -> str:
    nombre = RATIO_NOMBRE_LEGIBLE.get(señal.ratio, señal.ratio)
    verbo = "por ENCIMA" if señal.direccion == "por_encima" else "por DEBAJO"
    return (
        f"{nombre} en {señal.año}: valor del caso {señal.valor:.3g}, típico del sector "
        f"{señal.huber_9y:.3g} — {verbo} de lo habitual ({abs(señal.desviaciones):.1f} "
        "desviaciones del sector)."
    )


def seccion_8_señales(evolucion) -> list:
    flow = [Paragraph("8. Señales de alerta (banderas rojas)", titulo_seccion)]
    señales = evolucion.plausibilidad.señales
    if not señales:
        flow.append(Paragraph(
            "Sin desviaciones significativas frente al sector en el barrido de ratios de los 3 "
            "ejercicios.", cuerpo
        ))
        return flow
    filas = [["Ratio", "Año", "Valor del caso", "Típico del sector", "Desviaciones", "Dirección"]]
    for señal in sorted(señales, key=lambda s: (s.año, s.ratio)):
        filas.append([
            RATIO_NOMBRE_LEGIBLE.get(señal.ratio, señal.ratio), str(señal.año),
            _fmt_num(señal.valor, 3), _fmt_num(señal.huber_9y, 3),
            "∞" if señal.desviaciones in (float("inf"), float("-inf")) else _fmt_num(señal.desviaciones, 1),
            "por encima" if señal.direccion == "por_encima" else "por debajo",
        ])
    flow.append(_tabla(filas, anchos=[5.2 * cm, 1.6 * cm, 2.7 * cm, 2.7 * cm, 2.7 * cm, 2.7 * cm]))
    for señal in sorted(señales, key=lambda s: (s.año, s.ratio)):
        flow.append(Paragraph(f"- {_texto_señal(señal)}", cuerpo))
    return flow


# --------------------------------------------------------------------------------------------
# Sección 9 — Diagnóstico integrado
# --------------------------------------------------------------------------------------------

def seccion_9_diagnostico(evolucion, arquetipos_activos: list[tuple[str, str]]) -> list:
    flow = [Paragraph("9. Diagnóstico integrado", titulo_seccion)]
    señales = evolucion.plausibilidad.señales
    for arquetipo_id, intensidad in arquetipos_activos:
        ratios_relacionados = ARQUETIPO_RATIOS_RELACIONADOS.get(arquetipo_id, ())
        señales_explicadas = [s for s in señales if s.ratio in ratios_relacionados]
        flow.append(Paragraph(f"<b>{arquetipo_id}</b> (intensidad: {intensidad})", subtitulo_seccion))
        if not ratios_relacionados:
            flow.append(Paragraph(
                "Este arquetipo no tiene un efecto claramente atribuible a los ratios de la "
                "sección 8 (ver su ficha en la sección 1/catálogo para el detalle) — no se le "
                "atribuye ninguna señal.", cuerpo
            ))
        elif not señales_explicadas:
            flow.append(Paragraph(
                "Ningún ratio de los habitualmente asociados a este arquetipo "
                f"({', '.join(RATIO_NOMBRE_LEGIBLE.get(r, r) for r in ratios_relacionados)}) "
                "llega a desviarse lo suficiente del sector como para generar señal en este "
                "caso concreto — el efecto puede estar presente sin cruzar el umbral de "
                "plausibilidad.", cuerpo
            ))
        else:
            for señal in señales_explicadas:
                flow.append(Paragraph(f"- {_texto_señal(señal)}", cuerpo))

    flow.append(Paragraph(
        "<b>Cierre.</b> El caso reúne los arquetipos descritos en el resumen ejecutivo; las "
        "señales de la sección 8 que no aparecen vinculadas arriba a ningún arquetipo son ruido "
        "de generación esperado (el propio diseño del motor incluye variación típica/atípica "
        "entre empresas del mismo sector) o consecuencia de segundo orden de la interacción "
        "entre arquetipos (p. ej. el interés de una deuda nueva erosionando la rentabilidad en "
        "un ejercicio posterior) — no cada señal tiene por qué tener un arquetipo causante "
        "directo.", cuerpo
    ))
    return flow


def generar_documento_solucion(evolucion, ejercicios, efes, calendario) -> list[list]:
    arquetipos_activos = parsear_arquetipos_activos(evolucion)
    return [
        seccion_1_resumen_ejecutivo(evolucion, arquetipos_activos),
        seccion_2_analisis_patrimonial(ejercicios),
        seccion_3_liquidez(evolucion),
        seccion_4_endeudamiento(evolucion, calendario),
        seccion_5_analisis_economico(ejercicios, evolucion),
        seccion_6_rentabilidad(evolucion, ejercicios),
        seccion_7_efe(efes),
        seccion_8_señales(evolucion),
        seccion_9_diagnostico(evolucion, arquetipos_activos),
    ]
