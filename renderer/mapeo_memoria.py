"""Generador genérico de Memoria — funciona con cualquier caso que el motor genere, no con
ninguno en particular. 11 notas: 7 derivadas de datos reales del caso (3,5,6,7,9,10,11) + 4 de
plantilla fija con pocas variables (1,2,4,8) — ver especificaciones, numeración ya fijada al
diseñar el renderizador de PDF 1.
"""
from __future__ import annotations

from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm

from render_pdf import fmt_eur
from motor.coberturas_subvenciones import TIPO_IMPOSITIVO_GENERAL, pasivo_por_impuesto_diferido_eur

styles = getSampleStyleSheet()
titulo_nota = ParagraphStyle("TituloNota", parent=styles["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=4)
cuerpo = ParagraphStyle("CuerpoNota", parent=styles["Normal"], fontSize=9, leading=13, spaceAfter=6, alignment=4)
aviso = ParagraphStyle("Aviso", parent=cuerpo, fontName="Helvetica-Oblique", textColor=colors.HexColor("#666666"), fontSize=8)

RESERVA_LEGAL_PCT = 0.10
RESERVA_LEGAL_TOPE_PCT_CAPITAL = 0.20


encabezado_tabla = ParagraphStyle("EncabezadoTabla", parent=cuerpo, fontSize=7.5, leading=8.5, fontName="Helvetica-Bold")


def _tabla_simple(filas, anchos=None, encabezado=False):
    anchos = anchos or [8 * cm, 4 * cm]
    if encabezado:
        filas = [[Paragraph(c, encabezado_tabla) if isinstance(c, str) else c for c in filas[0]]] + filas[1:]
    t = Table(filas, colWidths=anchos)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _notas_narrativas_por_tema(evolucion, ejercicios):
    """Recoge todas las NotaMemoria generadas por arquetipos (7/10/16/18/19/20/21/22), de donde
    sea que vivan (evolucion.notas_memoria_pura, o ejercicio.notas_memoria por año), sin duplicar."""
    vistas = set()
    notas = []
    for n in getattr(evolucion, "notas_memoria_pura", ()):
        if n.arquetipo_id not in vistas:
            notas.append(n)
            vistas.add(n.arquetipo_id)
    for ej in ejercicios.values():
        for n in getattr(ej, "notas_memoria", ()):
            if n.arquetipo_id not in vistas:
                notas.append(n)
                vistas.add(n.arquetipo_id)
    return notas


def nota_1_actividad(nombre_empresa, sector_nombre):
    texto = (
        f"{nombre_empresa} tiene como objeto social principal el desarrollo de actividades "
        f"propias del sector \"{sector_nombre}\", con domicilio social en territorio español. "
        f"La Sociedad no forma parte de un grupo de empresas a efectos de consolidación, salvo "
        f"que se indique lo contrario en la nota 10. El ejercicio económico coincide con el año "
        f"natural."
    )
    return [Paragraph(texto, cuerpo)]


def nota_2_bases_presentacion(modelo):
    texto = (
        "Las cuentas anuales se han formulado a partir de los registros contables de la "
        "Sociedad, aplicando las disposiciones legales vigentes en materia contable, con el "
        "objeto de mostrar la imagen fiel del patrimonio, de la situación financiera y de los "
        f"resultados. Se han elaborado según el modelo {modelo.capitalize()} del Plan General "
        "de Contabilidad. No existen razones excepcionales que justifiquen la falta de "
        "aplicación de disposiciones legales en materia contable. Se ha considerado la "
        "aplicación del principio de empresa en funcionamiento, sin que existan incertidumbres "
        "significativas que puedan generar dudas sobre dicho principio. No se han producido "
        "cambios en criterios contables ni correcciones de errores significativos respecto al "
        "ejercicio anterior."
    )
    return [Paragraph(texto, cuerpo)]


def nota_3_aplicacion_resultados(ejercicios, modelo, capital_social_eur):
    flow = []
    if modelo == "abreviado":
        flow.append(Paragraph(
            "En el modelo Abreviado esta información se presenta formalmente en la hoja de "
            "identificación de la sociedad, no en la Memoria — se incluye aquí para no perderla, "
            "dado que esa hoja no se genera en este documento.", aviso
        ))
    reserva_legal_acum = 0.0
    for año in (2023, 2024, 2025):
        resultado = ejercicios[año].pyg_eur["resultado_ejercicio"]
        dividendo = max(0.0, getattr(ejercicios[año], "payout_dividendos_eur", 0.0))
        if resultado > 0:
            tope_restante = max(0.0, RESERVA_LEGAL_TOPE_PCT_CAPITAL * capital_social_eur - reserva_legal_acum)
            reserva_legal = min(RESERVA_LEGAL_PCT * resultado, tope_restante)
        else:
            reserva_legal = 0.0
        reserva_legal_acum += reserva_legal
        reservas_voluntarias = resultado - dividendo - reserva_legal
        flow.append(Paragraph(f"<b>Ejercicio {año}</b>", cuerpo))
        filas = [
            ["Base de reparto", ""],
            ["Saldo de la cuenta de pérdidas y ganancias", fmt_eur(resultado)],
            ["Aplicación", ""],
            ["A reserva legal", fmt_eur(reserva_legal)],
            ["A dividendos", fmt_eur(dividendo)],
            ["A reservas voluntarias", fmt_eur(reservas_voluntarias)],
        ]
        flow.append(_tabla_simple(filas))
        flow.append(Spacer(1, 0.2 * cm))
    flow.append(Paragraph(
        "La dotación a reserva legal se ha estimado aplicando el 10% del resultado del "
        "ejercicio hasta alcanzar el 20% del capital social (art. 274 LSC), sin conocer el saldo "
        "exacto de reserva legal ya dotada en ejercicios previos a 2023 — hipótesis de diseño, "
        "no un dato verificado.", aviso
    ))
    return flow


def nota_4_normas_registro():
    texto = (
        "Los criterios contables más significativos aplicados son los siguientes. "
        "<b>Inmovilizado material e intangible</b>: valorado al precio de adquisición, "
        "amortizado linealmente según la vida útil estimada de cada elemento. "
        "<b>Existencias</b>: valoradas al precio de adquisición o coste de producción, "
        "aplicando el criterio de precio medio ponderado. <b>Instrumentos financieros</b>: "
        "los activos y pasivos financieros se valoran inicialmente al valor razonable y "
        "posteriormente al coste amortizado. <b>Impuesto sobre beneficios</b>: el gasto se "
        "calcula en función del resultado contable antes de impuestos, sin diferencias "
        "significativas entre resultado contable y base imponible en el ejercicio. "
        "<b>Ingresos y gastos</b>: se imputan en función del criterio de devengo."
    )
    return [Paragraph(texto, cuerpo)]


def nota_5_inmovilizado(evolucion, ejercicios, notas_narrativas):
    flow = []
    flow.append(Paragraph(
        "Movimiento del inmovilizado material e intangible por categorías — coste, amortización "
        "acumulada y valor neto contable. La inversión inmobiliaria (si la hay) sigue el mismo "
        "criterio que las construcciones de uso comercial y se muestra por separado.", cuerpo
    ))
    for año in (2024, 2025):
        coleccion_ini = ejercicios[año - 1].coleccion_activos_amortizables
        coleccion_fin = ejercicios[año].coleccion_activos_amortizables
        tipos_presentes = sorted({sl.tipo for sl in coleccion_fin} | {sl.tipo for sl in coleccion_ini})
        if not tipos_presentes:
            continue
        filas = [["Categoría", "Coste inicial", "Coste final", "Amort. acum. inicial", "Amort. acum. final", "Dotación ejercicio", "Valor neto final"]]
        for tipo in tipos_presentes:
            bruto_ini = sum(sl.valor_bruto_eur for sl in coleccion_ini if sl.tipo == tipo)
            bruto_fin = sum(sl.valor_bruto_eur for sl in coleccion_fin if sl.tipo == tipo)
            acum_ini = sum(sl.acumulada_en(año - 1) for sl in coleccion_ini if sl.tipo == tipo)
            acum_fin = sum(sl.acumulada_en(año) for sl in coleccion_fin if sl.tipo == tipo)
            dotacion = sum(sl.gasto_en(año) for sl in coleccion_fin if sl.tipo == tipo)
            nombre_tipo = tipo.replace("_", " ").capitalize()
            filas.append([nombre_tipo, fmt_eur(bruto_ini), fmt_eur(bruto_fin), fmt_eur(acum_ini),
                          fmt_eur(acum_fin), fmt_eur(dotacion), fmt_eur(bruto_fin - acum_fin)])
        flow.append(Paragraph(f"<b>Ejercicio {año}</b>", cuerpo))
        flow.append(_tabla_simple(filas, anchos=[3.6 * cm] + [2.3 * cm] * 6, encabezado=True))
        flow.append(Spacer(1, 0.15 * cm))
    flow.append(Paragraph(
        "El coste inicial/final de cada categoría refleja el efecto conjunto de nuevas "
        "incorporaciones y bajas del ejercicio — el motor no distingue altas y bajas brutas por "
        "separado dentro de la misma categoría, solo el saldo neto resultante. La amortización "
        "se calcula de forma individualizada por sub-lote de activos, según su vida útil fiscal "
        "de referencia (tablas oficiales de amortización, coeficiente mínimo de cada tipo).",
        aviso
    ))
    for n in notas_narrativas:
        if n.arquetipo_id in ("adquisicion",):
            flow.append(Paragraph(n.texto, cuerpo))
    return flow


def nota_6_activos_financieros(ejercicios, modelo):
    filas = [["", "2023", "2024", "2025"],
             ["Inversiones financieras a largo plazo"] + [fmt_eur(ejercicios[a].activo_no_corriente_desglose_eur.get("otros_financieros", 0.0)) for a in (2023, 2024, 2025)]]
    flow = [_tabla_simple(filas, anchos=[6 * cm, 2.7 * cm, 2.7 * cm, 2.7 * cm])]
    flow.append(Paragraph(
        "Corresponde a instrumentos financieros mantenidos por la Sociedad, valorados a coste "
        "amortizado. No existen correcciones valorativas por deterioro registradas en el ejercicio.",
        cuerpo
    ))
    inversion_grupo = ejercicios[2025].inversion_grupo_largo_eur
    if inversion_grupo > 0:
        flow.append(Paragraph(
            f"La Sociedad mantiene un crédito a largo plazo con su sociedad matriz por importe de "
            f"{fmt_eur(inversion_grupo)} (ver nota 10) — se trata de un derecho de crédito, no de "
            f"una participación en el capital de dicha sociedad.", cuerpo
        ))
    referencia_legal = (
        "(indicación 2ª del art. 260 LSC, de contenido obligatorio en el modelo Abreviado por "
        "remisión del art. 261 LSC)."
        if modelo == "abreviado" else
        "(indicación 2ª del art. 260 LSC)."
    )
    flow.append(Paragraph(
        "La Sociedad no posee, de forma directa o indirecta, un porcentaje igual o superior al "
        "20% del capital de ninguna otra sociedad, ni ejerce sobre ellas una influencia "
        f"significativa {referencia_legal}", cuerpo
    ))
    return flow


def nota_7_pasivos_financieros(ejercicios, notas_narrativas):
    flow = []
    filas = [["Vencimiento", "2024", "2025"]]
    for a in (2024, 2025):
        pass
    filas.append(["Hasta 1 año"] + [fmt_eur(ejercicios[a].balance_eur["deudas_fin_corto"]) for a in (2024, 2025)])
    filas.append(["Entre 1 y 5 años"] + [fmt_eur(ejercicios[a].balance_eur["deudas_fin_largo"]) for a in (2024, 2025)])
    flow.append(_tabla_simple(filas, anchos=[6 * cm, 3.5 * cm, 3.5 * cm]))
    flow.append(Paragraph(
        "El desglose por plazo de vencimiento es una simplificación (largo plazo agrupado en "
        "\"entre 1 y 5 años\") — el motor no modela un calendario de vencimientos individual por "
        "préstamo.", aviso
    ))
    for n in notas_narrativas:
        if n.arquetipo_id in ("refinanciacion", "riesgo_refinanciacion"):
            flow.append(Paragraph(n.texto, cuerpo))
    return flow


def nota_8_fondos_propios(ejercicios):
    texto = (
        "No se han producido ampliaciones ni reducciones de capital social en el ejercicio. La "
        "Sociedad no mantiene acciones o participaciones propias. El capital social está "
        "representado por una única clase de participaciones, todas ellas con los mismos "
        "derechos (indicación 3ª del art. 260 LSC — no existen varias clases de acciones). El "
        "movimiento de reservas se detalla en el Estado de Cambios en el Patrimonio Neto y en la "
        "nota 3."
    )
    flow = [Paragraph(texto, cuerpo)]

    hay_subvencion = any(
        ejercicios[a].subvencion_saldo_130_bruto_eur > 0 or ejercicios[a].subvencion_importe_concedido_eur > 0
        for a in (2024, 2025)
    )
    if hay_subvencion:
        flow.append(Paragraph("<b>Subvenciones, donaciones y legados recibidos</b>", cuerpo))
        filas = [["", "2024", "2025"]]
        for etiqueta, extractor in (
            ("Saldo inicial (bruto)", lambda e, año: ejercicios[año - 1].subvencion_saldo_130_bruto_eur),
            ("Importe concedido en el ejercicio", lambda e, año: e.subvencion_importe_concedido_eur),
            ("Imputado a resultados del ejercicio", lambda e, año: -e.subvencion_transferencia_bruto_eur),
            ("Saldo final (bruto)", lambda e, año: e.subvencion_saldo_130_bruto_eur),
            ("Efecto impositivo (pasivo por impuesto diferido)", lambda e, año: pasivo_por_impuesto_diferido_eur(e.subvencion_saldo_130_bruto_eur)),
            ("Saldo final (neto, ver Balance A-3)", lambda e, año: e.subvenciones_pn_eur),
        ):
            filas.append([etiqueta] + [fmt_eur(extractor(ejercicios[a], a)) for a in (2024, 2025)])
        flow.append(_tabla_simple(filas, anchos=[9 * cm, 3 * cm, 3 * cm], encabezado=True))
        flow.append(Paragraph(
            "El saldo bruto se presenta neto de su efecto impositivo (pasivo por impuesto "
            f"diferido, tipo general del {TIPO_IMPOSITIVO_GENERAL:.0%} — art. 29 de la Ley "
            "27/2014, del Impuesto sobre Sociedades) en el epígrafe A-3 del Patrimonio Neto del "
            "Balance, según lo dispuesto en la norma de registro y valoración 18ª del PGC. El "
            "importe concedido corresponde a subvenciones de capital vinculadas a inversiones en "
            "inmovilizado, imputadas a resultados en proporción a su amortización.", aviso
        ))
    return flow


def nota_9_situacion_fiscal(ejercicios):
    flow = []
    for año in (2023, 2024, 2025):
        ej = ejercicios[año]
        bai = ej.pyg_eur["bai"]
        impuesto = ej.pyg_eur["impuesto_beneficios"]
        tipo_efectivo = (impuesto / bai * 100) if bai > 0 else 0.0
        # Hacienda deudora/acreedora se lee del propio Balance (deudores_desglose_eur/
        # acreedores_desglose_eur, mismas fuentes que mapeo_balance.py) — nunca se recalcula
        # aparte, para no divergir del techo defensivo que el motor aplica contra el presupuesto
        # disponible de "clientes"/"proveedores" (ver motor/empresa_base.py y motor/
        # evolucion_arquetipo.py, bloque "Hacienda Pública, deudora/acreedora"). "Pagos a cuenta"
        # se deriva por diferencia (cuota − acreedora + deudora), no se sortea aparte.
        deudora = ej.deudores_desglose_eur.get("hacienda_publica_deudora", 0.0)
        acreedora = ej.acreedores_desglose_eur.get("hacienda_publica_acreedora", 0.0)
        pagos_a_cuenta = impuesto - acreedora + deudora
        flow.append(Paragraph(f"<b>Ejercicio {año}</b>", cuerpo))
        filas = [
            ["Resultado antes de impuestos", fmt_eur(bai)],
            ["Tipo impositivo efectivo", f"{tipo_efectivo:.1f}%"],
            ["Cuota del Impuesto sobre Sociedades", fmt_eur(impuesto)],
            ["Pagos a cuenta realizados en el ejercicio", fmt_eur(pagos_a_cuenta)],
            ["Hacienda Pública, " + ("deudora" if deudora > 0 else "acreedora") + " por impuesto corriente",
             fmt_eur(deudora if deudora > 0 else acreedora)],
        ]
        flow.append(_tabla_simple(filas))
        flow.append(Spacer(1, 0.15 * cm))
    flow.append(Paragraph(
        "Los pagos a cuenta del ejercicio se obtienen por diferencia entre la cuota del Impuesto "
        "sobre Sociedades y la posición neta con la Hacienda Pública por impuesto corriente que "
        "muestra el Balance (Activos/Pasivos por impuesto corriente).", aviso
    ))

    diferido_pasivo = {a: ejercicios[a].pasivos_por_impuesto_diferido_eur for a in (2024, 2025)}
    diferido_activo = {a: ejercicios[a].activos_por_impuesto_diferido_eur for a in (2024, 2025)}
    hay_pasivo_diferido = any(v != 0 for v in diferido_pasivo.values())
    hay_activo_diferido = any(v != 0 for v in diferido_activo.values())

    piezas_pasivo = []
    if any(ejercicios[a].cobertura_saldo_1340_bruto_eur > 0 for a in (2024, 2025)):
        piezas_pasivo.append("la cobertura de flujos de efectivo contratada (ver nota 7)")
    if any(ejercicios[a].subvencion_saldo_130_bruto_eur > 0 for a in (2024, 2025)):
        piezas_pasivo.append("la subvención de capital concedida (ver nota 8)")
    piezas_activo = []
    if any(ejercicios[a].cobertura_saldo_1340_bruto_eur < 0 for a in (2024, 2025)):
        piezas_activo.append("la cobertura de flujos de efectivo contratada (ver nota 7)")

    if not hay_pasivo_diferido and not hay_activo_diferido:
        flow.append(Paragraph(
            "No existen diferencias significativas entre el resultado contable y la base imponible "
            "del Impuesto sobre Sociedades en los ejercicios presentados.", cuerpo
        ))
        return flow

    tipo_txt = (
        f"calculado al tipo general del {TIPO_IMPOSITIVO_GENERAL:.0%} (art. 29 de la Ley "
        "27/2014, del Impuesto sobre Sociedades — no al tipo efectivo de la tabla anterior, "
        "que solo se aplica al resultado del ejercicio)"
    )
    if hay_pasivo_diferido:
        flow.append(Paragraph(
            f"Existe una diferencia temporaria entre el resultado contable y la base imponible "
            f"derivada de {' y '.join(piezas_pasivo)}, registrada directamente en el patrimonio "
            f"neto sin pasar por la cuenta de pérdidas y ganancias. El efecto fiscal asociado, "
            f"{tipo_txt}, se reconoce como pasivo por impuesto diferido: "
            f"{fmt_eur(diferido_pasivo[2024])} (2024) y {fmt_eur(diferido_pasivo[2025])} (2025), "
            "mostrado en el epígrafe B.IV del Pasivo No Corriente del Balance.", cuerpo
        ))
    if hay_activo_diferido:
        if hay_pasivo_diferido:
            # Ya hay un párrafo "anterior" (pasivo diferido) al que referirse — mismo texto de
            # siempre, con el matiz de signo contrario.
            texto_activo = (
                f"Existe además una diferencia temporaria derivada de {' y '.join(piezas_activo)} "
                f"que, por signo contrario a la anterior, se reconoce como activo por impuesto "
                f"diferido: {fmt_eur(diferido_activo[2024])} (2024) y {fmt_eur(diferido_activo[2025])} "
                "(2025), mostrado en el epígrafe A.VI del Activo No Corriente del Balance."
            )
        else:
            # Sin pasivo diferido no hay ningún párrafo "anterior" al que referirse (#111,
            # defecto 1) — mismo texto que el párrafo de pasivo diferido de arriba, en espejo.
            texto_activo = (
                f"Existe una diferencia temporaria entre el resultado contable y la base imponible "
                f"derivada de {' y '.join(piezas_activo)}, registrada directamente en el patrimonio "
                f"neto sin pasar por la cuenta de pérdidas y ganancias. El efecto fiscal asociado, "
                f"{tipo_txt}, se reconoce como activo por impuesto diferido: "
                f"{fmt_eur(diferido_activo[2024])} (2024) y {fmt_eur(diferido_activo[2025])} (2025), "
                "mostrado en el epígrafe A.VI del Activo No Corriente del Balance."
            )
        flow.append(Paragraph(texto_activo, cuerpo))
    flow.append(Paragraph(
        "Al margen de estas diferencias temporarias, no existen otras diferencias significativas "
        "entre el resultado contable y la base imponible del Impuesto sobre Sociedades en los "
        "ejercicios presentados.", cuerpo
    ))
    return flow


def nota_10_partes_vinculadas(ejercicios, notas_narrativas):
    flow = []
    hay_operacion = any(ejercicios[a].operacion_vinculada_activa for a in (2024, 2025))
    if not hay_operacion:
        flow.append(Paragraph("La Sociedad no ha realizado operaciones con partes vinculadas en los ejercicios presentados.", cuerpo))
    else:
        for a in (2024, 2025):
            ej = ejercicios[a]
            if ej.operacion_vinculada_activa:
                flow.append(Paragraph(
                    f"Ejercicio {a}: operación vinculada de tipo \"{ej.operacion_vinculada_tipo}\", "
                    f"por importe de {fmt_eur(ej.operacion_vinculada_importe_eur)}.", cuerpo
                ))
        for n in notas_narrativas:
            if n.arquetipo_id in ("operaciones_vinculadas",):
                flow.append(Paragraph(n.texto, cuerpo))
    flow.append(Paragraph(
        "<b>Remuneración de administradores y alta dirección</b> (indicación 9ª del art. 260 "
        "LSC). Los administradores de la Sociedad no han percibido remuneración alguna en su "
        "condición de tales durante los ejercicios presentados, sin perjuicio, en su caso, de la "
        "retribución que perciban por el desempeño de funciones distintas a las de administrador, "
        "ya incluida dentro de los gastos de personal.", cuerpo
    ))
    flow.append(Paragraph(
        "<b>Anticipos y créditos a administradores y alta dirección</b> (indicación 10ª del art. "
        "260 LSC). No existen anticipos ni créditos concedidos a los administradores ni al "
        "personal de alta dirección, ni se han asumido obligaciones por cuenta de ellos a título "
        "de garantía, en ninguno de los ejercicios presentados.", cuerpo
    ))
    return flow


def nota_11_otra_informacion(ejercicios, plantilla_estimada, notas_narrativas):
    flow = [Paragraph(f"Número medio de empleados del ejercicio: {round(plantilla_estimada)}.", cuerpo)]
    flow.append(Paragraph("No se han producido hechos posteriores al cierre que deban mencionarse.", cuerpo))
    for n in notas_narrativas:
        if n.arquetipo_id in ("dependencia_pocos_clientes", "activo_mantenido_venta", "informacion_relevante", "coberturas"):
            flow.append(Paragraph(n.texto, cuerpo))
    return flow


NOTAS_TITULOS = {
    1: "Actividad de la empresa", 2: "Bases de presentación de las cuentas anuales",
    3: "Aplicación de resultados", 4: "Normas de registro y valoración",
    5: "Inmovilizado material, intangible e inversiones inmobiliarias", 6: "Activos financieros",
    7: "Pasivos financieros", 8: "Fondos propios", 9: "Situación fiscal",
    10: "Operaciones con partes vinculadas", 11: "Otra información",
}


def generar_memoria(evolucion, ejercicios, modelo, nombre_empresa, sector_nombre, plantilla_estimada):
    notas_narrativas = _notas_narrativas_por_tema(evolucion, ejercicios)
    capital_social_eur = ejercicios[2023].capital_social_eur
    generadores = {
        1: lambda: nota_1_actividad(nombre_empresa, sector_nombre),
        2: lambda: nota_2_bases_presentacion(modelo),
        3: lambda: nota_3_aplicacion_resultados(ejercicios, modelo, capital_social_eur),
        4: lambda: nota_4_normas_registro(),
        5: lambda: nota_5_inmovilizado(evolucion, ejercicios, notas_narrativas),
        6: lambda: nota_6_activos_financieros(ejercicios, modelo),
        7: lambda: nota_7_pasivos_financieros(ejercicios, notas_narrativas),
        8: lambda: nota_8_fondos_propios(ejercicios),
        9: lambda: nota_9_situacion_fiscal(ejercicios),
        10: lambda: nota_10_partes_vinculadas(ejercicios, notas_narrativas),
        11: lambda: nota_11_otra_informacion(ejercicios, plantilla_estimada, notas_narrativas),
    }
    flow = [Paragraph("Memoria", styles["Heading1"])]
    for numero in range(1, 12):
        flow.append(Paragraph(f"{numero}. {NOTAS_TITULOS[numero]}", titulo_nota))
        flow.extend(generadores[numero]())
    return flow
