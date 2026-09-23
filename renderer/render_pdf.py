"""Capa de render — reportlab Platypus. Agnóstica de PGC: solo sabe dibujar tablas con
indentación/negrita/formato español de números a partir de listas de LineaEstado."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

styles = getSampleStyleSheet()
titulo_estilo = ParagraphStyle("TituloEstado", parent=styles["Heading1"], fontSize=14, spaceAfter=4)
subtitulo_estilo = ParagraphStyle("Subtitulo", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=10)
portada_titulo = ParagraphStyle("PortadaTitulo", parent=styles["Heading1"], fontSize=20, alignment=TA_CENTER, spaceAfter=6)
portada_sub = ParagraphStyle("PortadaSub", parent=styles["Normal"], fontSize=11, alignment=TA_CENTER, textColor=colors.grey)


def fmt_eur(valor: float) -> str:
    if valor is None:
        return ""
    neg = valor < -0.005
    v = abs(valor)
    entero = int(round(v))
    s = f"{entero:,}".replace(",", ".")
    return f"({s})" if neg else s


celda_estilo = ParagraphStyle("Celda", parent=styles["Normal"], fontSize=8, leading=9.5)
celda_estilo_bold = ParagraphStyle("CeldaBold", parent=celda_estilo, fontName="Helvetica-Bold")


def _fila_tabla(linea, columnas):
    indent = "&nbsp;" * (4 * linea.nivel)
    etiqueta = f"{linea.codigo}&nbsp;&nbsp;{linea.etiqueta}".strip() if linea.codigo else linea.etiqueta
    estilo = celda_estilo_bold if linea.negrita else celda_estilo
    fila = [Paragraph(indent + etiqueta, estilo)]
    for col in columnas:
        fila.append(fmt_eur(linea.valores.get(col)) if linea.valores else "")
    fila.append(str(linea.nota) if linea.nota else "")
    return fila


def construir_tabla_estado(titulo: str, subtitulo: str, lineas: list, columnas: list, etiquetas_columnas: list) -> list:
    flow = [Paragraph(titulo, titulo_estilo), Paragraph(subtitulo, subtitulo_estilo)]
    encabezado = ["Concepto"] + etiquetas_columnas + ["Notas"]
    filas = [encabezado]
    negritas_idx = []
    for i, linea in enumerate(lineas, start=1):
        filas.append(_fila_tabla(linea, columnas))
        if linea.negrita:
            negritas_idx.append(i)

    ancho_valor = 2.3 * cm
    ancho_notas = 1.2 * cm
    ancho_label = 18.4 * cm - ancho_valor * len(columnas) - ancho_notas
    anchos = [ancho_label] + [ancho_valor] * len(columnas) + [ancho_notas]
    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    estilo = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor("#2c3e50")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in negritas_idx:
        estilo.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
        estilo.append(("LINEABOVE", (0, i), (-1, i), 0.5, colors.HexColor("#bdc3c7")))
    tabla.setStyle(TableStyle(estilo))
    flow.append(tabla)
    return flow


def construir_ecpn_documento_b(titulo: str, subtitulo: str, tabla_por_año: dict) -> list:
    from mapeo_ecpn import COLUMNAS_ECPN
    encabezado_estilo = ParagraphStyle("Encabezado", parent=styles["Normal"], fontSize=6.5, leading=7.5,
                                        textColor=colors.white, fontName="Helvetica-Bold")
    flow = [Paragraph(titulo, titulo_estilo), Paragraph(subtitulo, subtitulo_estilo)]
    for año, filas_fila_ecpn in tabla_por_año.items():
        encabezado = [Paragraph("Concepto", encabezado_estilo)] + [Paragraph(etq, encabezado_estilo) for _, etq in COLUMNAS_ECPN]
        filas = [encabezado]
        for etiqueta, fila_ecpn in filas_fila_ecpn:
            fila = [Paragraph(etiqueta, celda_estilo)] + [fmt_eur(getattr(fila_ecpn, clave)) for clave, _ in COLUMNAS_ECPN]
            filas.append(fila)
        anchos = [4.2 * cm] + [2.37 * cm] * len(COLUMNAS_ECPN)
        tabla = Table(filas, colWidths=anchos, repeatRows=1)
        estilo = [
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#bdc3c7")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]
        tabla.setStyle(TableStyle(estilo))
        flow.append(Paragraph(f"Ejercicio {año}", ParagraphStyle("Año", parent=styles["Heading3"], fontSize=10, spaceBefore=8)))
        flow.append(tabla)
    return flow


def generar_pdf(ruta_salida: str, empresa_nombre: str, sector: str, modelo: str, secciones: list):
    Path(ruta_salida).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(ruta_salida, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                             leftMargin=1.3 * cm, rightMargin=1.3 * cm)
    flow = [
        Spacer(1, 6 * cm),
        Paragraph(empresa_nombre, portada_titulo),
        Paragraph(f"Cuentas Anuales — Modelo {modelo.capitalize()}", portada_sub),
        Paragraph(f"Sector: {sector} · Ejercicios 2023-2025", portada_sub),
        PageBreak(),
    ]
    for seccion in secciones:
        flow.extend(seccion)
        flow.append(PageBreak())
    if flow and isinstance(flow[-1], PageBreak):
        flow.pop()
    doc.build(flow)
