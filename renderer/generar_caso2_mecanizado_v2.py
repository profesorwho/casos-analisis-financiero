import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tipos import LineaEstado
from render_pdf import construir_tabla_estado, generar_pdf

def v(d2023, d2024, d2025):
    return {2023: d2023, 2024: d2024, 2025: d2025}

lineas_activo = [
    LineaEstado("A", "ACTIVO NO CORRIENTE", 0, v(1841230, 2125130, 2433940), negrita=True),
    LineaEstado("I", "Inmovilizado intangible", 1, v(41230, 37680, 33940), nota=5),
    LineaEstado("II", "Inmovilizado material", 1, v(1800000, 2087450, 2400000), nota=5),
    LineaEstado("III", "Inversiones inmobiliarias", 1, v(0, 0, 0)),
    LineaEstado("IV", "Inversiones en empresas del grupo y asociadas a largo plazo", 1, v(0, 0, 0)),
    LineaEstado("V", "Inversiones financieras a largo plazo", 1, v(0, 0, 0)),
    LineaEstado("VI", "Activos por impuesto diferido", 1, v(0, 0, 0)),

    LineaEstado("B", "ACTIVO CORRIENTE", 0, v(1818460, 2016990, 2421390), negrita=True),
    LineaEstado("II", "Existencias", 1, v(981340, 1014870, 1038210)),
    LineaEstado("III", "Deudores comerciales y otras cuentas a cobrar", 1, v(822526, 1028158, 1233789), negrita=True),
    LineaEstado("1", "Clientes por ventas y prestaciones de servicios", 2, v(739726, 924658, 1109589)),
    LineaEstado("2", "Deudores varios", 2, v(58200, 72750, 87300)),
    LineaEstado("3", "Otros créditos con las Administraciones Públicas", 2, v(24600, 30750, 36900)),
    LineaEstado("VI", "Periodificaciones a corto plazo", 1, v(14400, 18000, 21600)),
    LineaEstado("VII", "Efectivo y otros activos líquidos equivalentes", 1, v(760194, 955492, 1154661), negrita=True),

    LineaEstado("", "TOTAL ACTIVO (A + B)", 0, v(4419690, 5141650, 5882200), negrita=True),
]

lineas_pasivo = [
    LineaEstado("A", "PATRIMONIO NETO", 0, v(1923450, 2100250, 2209850), negrita=True),
    LineaEstado("A-1", "Fondos propios", 1, v(1923450, 2100250, 2209850), negrita=True),
    LineaEstado("I", "Capital", 2, v(1000000, 1000000, 1000000)),
    LineaEstado("III", "Reservas", 2, v(823450, 923450, 1100250)),
    LineaEstado("VII", "Resultado del ejercicio", 2, v(100000, 176800, 109600)),
    LineaEstado("A-2", "Ajustes por cambios de valor", 1, v(0, 0, 0)),
    LineaEstado("A-3", "Subvenciones, donaciones y legados recibidos", 1, v(0, 0, 0)),

    LineaEstado("B", "PASIVO NO CORRIENTE", 0, v(512400, 578900, 651300), negrita=True),
    LineaEstado("I", "Provisiones a largo plazo", 1, v(0, 0, 0)),
    LineaEstado("II", "Deudas a largo plazo", 1, v(512400, 578900, 651300), negrita=True),
    LineaEstado("III", "Deudas con empresas del grupo y asociadas a largo plazo", 1, v(0, 0, 0)),
    LineaEstado("IV", "Pasivos por impuesto diferido", 1, v(0, 0, 0)),

    LineaEstado("C", "PASIVO CORRIENTE", 0, v(1983840, 2462500, 3021050), negrita=True),
    LineaEstado("II", "Provisiones a corto plazo", 1, v(0, 0, 0)),
    LineaEstado("III", "Deudas a corto plazo", 1, v(1187600, 1398200, 1642800), negrita=True),
    LineaEstado("V", "Acreedores comerciales y otras cuentas a pagar", 1, v(781540, 1046650, 1358400), negrita=True),
    LineaEstado("1", "Proveedores", 2, v(683940, 928650, 1219800)),
    LineaEstado("2", "Personal", 2, v(58700, 70900, 83200)),
    LineaEstado("3", "Otras deudas con las Administraciones Públicas", 2, v(38900, 47100, 55400)),
    LineaEstado("VI", "Periodificaciones a corto plazo", 1, v(14700, 17650, 19850)),

    LineaEstado("", "TOTAL PATRIMONIO NETO Y PASIVO (A + B + C)", 0, v(4419690, 5141650, 5882200), negrita=True),
]

lineas_pyg = [
    LineaEstado("1", "Importe neto de la cifra de negocios", 2, v(6000000, 7500000, 9000000), negrita=True),
    LineaEstado("2", "Variación de existencias de productos terminados y en curso de fabricación", 2, v(33530, 32410, 24680)),
    LineaEstado("3", "Trabajos realizados por la empresa para su activo", 2, v(0, 0, 0)),
    LineaEstado("4", "Aprovisionamientos", 2, v(-4091530, -5308410, -6570680), negrita=True),
    LineaEstado("5", "Otros ingresos de explotación", 2, v(21400, 23800, 26100)),
    LineaEstado("6", "Gastos de personal", 2, v(-947300, -1148600, -1352900)),
    LineaEstado("7", "Otros gastos de explotación", 2, v(-648700, -782300, -918600)),
    LineaEstado("8", "Amortización del inmovilizado", 2, v(-187400, -241900, -298600)),
    LineaEstado("9", "Imputación de subvenciones de inmovilizado no financiero y otras", 2, v(0, 0, 0)),
    LineaEstado("10", "Excesos de provisiones", 2, v(0, 0, 0)),
    LineaEstado("11", "Deterioro y resultado por enajenaciones del inmovilizado", 2, v(0, 250000, 400000)),
    LineaEstado("12", "Diferencia negativa de combinaciones de negocio", 2, v(0, 0, 0)),
    LineaEstado("13", "Otros resultados", 2, v(0, 0, 0)),
    LineaEstado("A)", "RESULTADO DE EXPLOTACIÓN", 1, v(180000, 325000, 310000), negrita=True),

    LineaEstado("14", "Ingresos financieros", 2, v(5000, 6000, 7000), negrita=True),
    LineaEstado("15", "Gastos financieros", 2, v(-60000, -110000, -180000)),
    LineaEstado("16", "Variación de valor razonable en instrumentos financieros", 2, v(0, 0, 0)),
    LineaEstado("17", "Diferencias de cambio", 2, v(0, 0, 0)),
    LineaEstado("18", "Deterioro y resultado por enajenaciones de instrumentos financieros", 2, v(0, 0, 0)),
    LineaEstado("19", "Otros ingresos y gastos de carácter financiero", 2, v(0, 0, 0)),
    LineaEstado("B)", "RESULTADO FINANCIERO", 1, v(-55000, -104000, -173000), negrita=True),
    LineaEstado("C)", "RESULTADO ANTES DE IMPUESTOS", 1, v(125000, 221000, 137000), negrita=True),
    LineaEstado("20", "Impuestos sobre beneficios (20%)", 2, v(-25000, -44200, -27400)),
    LineaEstado("D)", "RESULTADO DEL EJERCICIO", 1, v(100000, 176800, 109600), negrita=True),
]

from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm

nota_estilo = ParagraphStyle("NotaCliente", fontName="Helvetica-Oblique", fontSize=8.5, leading=11,
                              textColor=colors.HexColor("#333333"), spaceBefore=8)

columnas = [2023, 2024, 2025]
etq = ["2023", "2024", "2025"]

seccion_activo = construir_tabla_estado("Balance — Activo", "PGC PYMES · Cuentas anuales abreviadas · Importes en euros", lineas_activo, columnas, etq)
seccion_activo.append(Spacer(1, 0.3 * cm))
seccion_activo.append(Paragraph(
    "Nota: durante los ejercicios 2023, 2024 y 2025, aproximadamente el 80% de la cifra de "
    "negocios de la Sociedad ha correspondido a un único cliente, Componentes Automotrices "
    "Ibérica, S.A.",
    nota_estilo
))

secciones = [
    seccion_activo,
    construir_tabla_estado("Balance — Patrimonio Neto y Pasivo", "PGC PYMES · Cuentas anuales abreviadas · Importes en euros", lineas_pasivo, columnas, etq),
    construir_tabla_estado("Cuenta de Pérdidas y Ganancias", "PGC PYMES · Cuentas anuales abreviadas · Importes en euros", lineas_pyg, columnas, etq),
]

generar_pdf(str(Path(__file__).resolve().parent / "output" / "caso2_mecanizado_precision_v2.pdf"),
            "Mecanizados Bizkaia", "Subcontratación de mecanizado (automoción)", "abreviado", secciones)
print("Generado.")
