import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tipos import LineaEstado
from render_pdf import construir_tabla_estado, generar_pdf

def v(d2023, d2024, d2025):
    return {2023: d2023, 2024: d2024, 2025: d2025}

# ============ BALANCE — ACTIVO ============
lineas_activo = [
    LineaEstado("A", "ACTIVO NO CORRIENTE", 0, v(1840000, 1536000, 1132000), negrita=True),
    LineaEstado("I", "Inmovilizado intangible", 1, v(40000, 36000, 32000), nota=5),
    LineaEstado("II", "Inmovilizado material", 1, v(1800000, 1500000, 1100000), nota=5),
    LineaEstado("III", "Inversiones inmobiliarias", 1, v(0, 0, 0)),
    LineaEstado("IV", "Inversiones en empresas del grupo y asociadas a largo plazo", 1, v(0, 0, 0)),
    LineaEstado("V", "Inversiones financieras a largo plazo", 1, v(0, 0, 0)),
    LineaEstado("VI", "Activos por impuesto diferido", 1, v(0, 0, 0)),

    LineaEstado("B", "ACTIVO CORRIENTE", 0, v(2568750, 4411500, 6541250), negrita=True),
    LineaEstado("II", "Existencias", 1, v(900000, 1200000, 1600000)),
    LineaEstado("III", "Deudores comerciales y otras cuentas a cobrar", 1, v(1185000, 1798000, 2717000), negrita=True),
    LineaEstado("1", "Clientes por ventas y prestaciones de servicios", 2, v(1100000, 1700000, 2600000)),
    LineaEstado("2", "Deudores varios", 2, v(60000, 70000, 85000)),
    LineaEstado("3", "Otros créditos con las Administraciones Públicas", 2, v(25000, 28000, 32000)),
    LineaEstado("VI", "Periodificaciones a corto plazo", 1, v(15000, 18000, 22000)),
    LineaEstado("VII", "Efectivo y otros activos líquidos equivalentes", 1, v(468750, 1395500, 2202250), negrita=True),

    LineaEstado("", "TOTAL ACTIVO (A + B)", 0, v(4408750, 5947500, 7673250), negrita=True),
]

# ============ BALANCE — PN Y PASIVO ============
lineas_pasivo = [
    LineaEstado("A", "PATRIMONIO NETO", 0, v(1893750, 2059500, 2162250), negrita=True),
    LineaEstado("A-1", "Fondos propios", 1, v(1893750, 2059500, 2162250), negrita=True),
    LineaEstado("I", "Capital", 2, v(1000000, 1000000, 1000000)),
    LineaEstado("III", "Reservas", 2, v(800000, 893750, 1059500)),
    LineaEstado("VII", "Resultado del ejercicio", 2, v(93750, 165750, 102750)),
    LineaEstado("A-2", "Ajustes por cambios de valor", 1, v(0, 0, 0)),
    LineaEstado("A-3", "Subvenciones, donaciones y legados recibidos", 1, v(0, 0, 0)),

    LineaEstado("B", "PASIVO NO CORRIENTE", 0, v(500000, 600000, 700000), negrita=True),
    LineaEstado("I", "Provisiones a largo plazo", 1, v(0, 0, 0)),
    LineaEstado("II", "Deudas a largo plazo", 1, v(500000, 600000, 700000), negrita=True),
    LineaEstado("III", "Deudas con empresas del grupo y asociadas a largo plazo", 1, v(0, 0, 0)),
    LineaEstado("IV", "Pasivos por impuesto diferido", 1, v(0, 0, 0)),

    LineaEstado("C", "PASIVO CORRIENTE", 0, v(2015000, 3288000, 4811000), negrita=True),
    LineaEstado("II", "Provisiones a corto plazo", 1, v(0, 0, 0)),
    LineaEstado("III", "Deudas a corto plazo", 1, v(1200000, 2200000, 3400000), negrita=True),
    LineaEstado("V", "Acreedores comerciales y otras cuentas a pagar", 1, v(800000, 1070000, 1391000), negrita=True),
    LineaEstado("1", "Proveedores", 2, v(700000, 950000, 1250000)),
    LineaEstado("2", "Personal", 2, v(60000, 72000, 85000)),
    LineaEstado("3", "Otras deudas con las Administraciones Públicas", 2, v(40000, 48000, 56000)),
    LineaEstado("VI", "Periodificaciones a corto plazo", 1, v(15000, 18000, 20000)),

    LineaEstado("", "TOTAL PATRIMONIO NETO Y PASIVO (A + B + C)", 0, v(4408750, 5947500, 7673250), negrita=True),
]

# ============ PyG ============
lineas_pyg = [
    LineaEstado("1", "Importe neto de la cifra de negocios", 2, v(6000000, 7500000, 9000000), negrita=True),
    LineaEstado("2", "Variación de existencias de productos terminados y en curso de fabricación", 2, v(80000, 150000, 180000)),
    LineaEstado("3", "Trabajos realizados por la empresa para su activo", 2, v(0, 0, 0)),
    LineaEstado("4", "Aprovisionamientos", 2, v(-4140000, -5437000, -6744000), negrita=True),
    LineaEstado("5", "Otros ingresos de explotación", 2, v(20000, 22000, 24000)),
    LineaEstado("6", "Gastos de personal", 2, v(-950000, -1150000, -1350000)),
    LineaEstado("7", "Otros gastos de explotación", 2, v(-650000, -780000, -920000)),
    LineaEstado("8", "Amortización del inmovilizado", 2, v(-180000, -230000, -280000)),
    LineaEstado("9", "Imputación de subvenciones de inmovilizado no financiero y otras", 2, v(0, 0, 0)),
    LineaEstado("10", "Excesos de provisiones", 2, v(0, 0, 0)),
    LineaEstado("11", "Deterioro y resultado por enajenaciones del inmovilizado", 2, v(0, 250000, 400000)),
    LineaEstado("12", "Diferencia negativa de combinaciones de negocio", 2, v(0, 0, 0)),
    LineaEstado("13", "Otros resultados", 2, v(0, 0, 0)),
    LineaEstado("A)", "RESULTADO DE EXPLOTACIÓN", 1, v(180000, 325000, 310000), negrita=True),

    LineaEstado("", "  memo: resultado de explotación RECURRENTE (excluye línea 11)", 3, v(180000, 75000, -90000)),

    LineaEstado("14", "Ingresos financieros", 2, v(5000, 6000, 7000), negrita=True),
    LineaEstado("15", "Gastos financieros", 2, v(-60000, -110000, -180000)),
    LineaEstado("16", "Variación de valor razonable en instrumentos financieros", 2, v(0, 0, 0)),
    LineaEstado("17", "Diferencias de cambio", 2, v(0, 0, 0)),
    LineaEstado("18", "Deterioro y resultado por enajenaciones de instrumentos financieros", 2, v(0, 0, 0)),
    LineaEstado("19", "Otros ingresos y gastos de carácter financiero", 2, v(0, 0, 0)),
    LineaEstado("B)", "RESULTADO FINANCIERO", 1, v(-55000, -104000, -173000), negrita=True),
    LineaEstado("C)", "RESULTADO ANTES DE IMPUESTOS", 1, v(125000, 221000, 137000), negrita=True),
    LineaEstado("20", "Impuestos sobre beneficios (25%)", 2, v(-31250, -55250, -34250)),
    LineaEstado("D)", "RESULTADO DEL EJERCICIO", 1, v(93750, 165750, 102750), negrita=True),
]

columnas = [2023, 2024, 2025]
etq = ["2023", "2024", "2025"]

secciones = [
    construir_tabla_estado("Balance — Activo", "PGC PYMES · Cuentas anuales abreviadas · Importes en euros", lineas_activo, columnas, etq),
    construir_tabla_estado("Balance — Patrimonio Neto y Pasivo", "PGC PYMES · Cuentas anuales abreviadas · Importes en euros", lineas_pasivo, columnas, etq),
    construir_tabla_estado("Cuenta de Pérdidas y Ganancias", "PGC PYMES · Cuentas anuales abreviadas · Importes en euros", lineas_pyg, columnas, etq),
]

generar_pdf(str(Path(__file__).resolve().parent / "output" / "caso2_mecanizado_precision.pdf"),
            "Mecanizados de Precisión del Sur, S.L.", "Subcontratación de mecanizado (automoción)", "abreviado", secciones)
print("Generado.")
