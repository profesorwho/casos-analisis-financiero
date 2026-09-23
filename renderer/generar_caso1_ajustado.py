import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tipos import LineaEstado
from render_pdf import construir_tabla_estado, generar_pdf

AÑOS = (2023, 2024, 2025)

def v(d2023, d2024, d2025):
    return {2023: d2023, 2024: d2024, 2025: d2025}

# ============ BALANCE — ACTIVO ============
lineas_activo = [
    LineaEstado("A", "ACTIVO NO CORRIENTE", 0, v(1646491, 1564509, 1493377), negrita=True),
    LineaEstado("I", "Inmovilizado intangible", 1, v(141705, 133482, 126258), nota=5),
    LineaEstado("II", "Inmovilizado material", 1, v(1330800, 1253575, 1185732), nota=5),
    LineaEstado("III", "Inversiones inmobiliarias", 1, v(35419, 33364, 31558), nota=5),
    LineaEstado("IV", "Inversiones en empresas del grupo y asociadas a largo plazo", 1, v(0, 0, 0), nota=6),
    LineaEstado("V", "Inversiones financieras a largo plazo", 1, v(138567, 144088, 149829), nota=6),
    LineaEstado("VI", "Activos por impuesto diferido", 1, v(0, 0, 0)),

    LineaEstado("B", "ACTIVO CORRIENTE", 0, v(3471434, 4296796, 5682664), negrita=True),
    LineaEstado("II", "Existencias", 1, v(1038529, 1079907, 1122934)),
    LineaEstado("III", "Deudores comerciales y otras cuentas a cobrar", 1, v(1204547, 2537709, 4272862), negrita=True),
    LineaEstado("1", "Clientes por ventas y prestaciones de servicios", 2, v(1127294, 2458494, 4167020)),
    LineaEstado("2", "Clientes, empresas del grupo y asociadas", 2, v(0, 0, 0), nota=10),
    LineaEstado("3", "Deudores varios", 2, v(54139, 56043, 75540)),
    LineaEstado("4", "Otros créditos con las Administraciones Públicas", 2, v(21064, 21805, 29391)),
    LineaEstado("5", "Accionistas (socios) por desembolsos exigidos", 2, v(2050, 1367, 911)),
    LineaEstado("VI", "Periodificaciones a corto plazo", 1, v(21586, 29180, 45514)),
    LineaEstado("VII", "Efectivo y otros activos líquidos equivalentes", 1, v(1206772, 650000, 241354), negrita=True),

    LineaEstado("", "TOTAL ACTIVO (A + B)", 0, v(5117925, 5861305, 7176041), negrita=True),
]

# ============ BALANCE — PN Y PASIVO ============
lineas_pasivo = [
    LineaEstado("A", "PATRIMONIO NETO", 0, v(3230452, 3797007, 4497842), negrita=True),
    LineaEstado("A-1", "Fondos propios", 1, v(3230452, 3797007, 4497842), negrita=True),
    LineaEstado("I", "Capital", 2, v(1100000, 1100000, 1100000), nota=8),
    LineaEstado("III", "Reservas", 2, v(1442055, 1717414, 2109251), nota=8),
    LineaEstado("VII", "Resultado del ejercicio", 2, v(688397, 979593, 1288591), nota=3),
    LineaEstado("A-2", "Ajustes por cambios de valor", 1, v(0, 0, 0)),
    LineaEstado("A-3", "Subvenciones, donaciones y legados recibidos", 1, v(0, 0, 0)),

    LineaEstado("B", "PASIVO NO CORRIENTE", 0, v(625441, 650360, 676273), negrita=True),
    LineaEstado("I", "Provisiones a largo plazo", 1, v(0, 0, 0), nota=4),
    LineaEstado("II", "Deudas a largo plazo", 1, v(621130, 645877, 671611), negrita=True, nota=7),
    LineaEstado("III", "Deudas con empresas del grupo y asociadas a largo plazo", 1, v(0, 0, 0), nota=10),
    LineaEstado("IV", "Pasivos por impuesto diferido", 1, v(0, 0, 0), nota=9),
    LineaEstado("V", "Periodificaciones a largo plazo", 1, v(4311, 4483, 4662)),

    LineaEstado("C", "PASIVO CORRIENTE", 0, v(1262032, 1413938, 2001926), negrita=True),
    LineaEstado("II", "Provisiones a corto plazo", 1, v(0, 0, 0), nota=4),
    LineaEstado("III", "Deudas a corto plazo", 1, v(341713, 355328, 675395), negrita=True, nota=7),
    LineaEstado("V", "Acreedores comerciales y otras cuentas a pagar", 1, v(625994, 651105, 753625), negrita=True),
    LineaEstado("1", "Proveedores", 2, v(572673, 595645, 619462)),
    LineaEstado("2", "Proveedores, empresas del grupo", 2, v(0, 0, 0)),
    LineaEstado("3", "Acreedores varios", 2, v(28774, 29928, 31125)),
    LineaEstado("4", "Personal", 2, v(0, 0, 31485)),
    LineaEstado("5", "Pasivos por impuesto corriente", 2, v(0, 0, 0)),
    LineaEstado("6", "Otras deudas con las Administraciones Públicas", 2, v(0, 0, 45000)),
    LineaEstado("7", "Anticipos de clientes", 2, v(24547, 25532, 26553)),
    LineaEstado("VI", "Periodificaciones a corto plazo", 1, v(16860, 10832, 4349)),
    LineaEstado("VII", "Otras deudas a corto plazo", 1, v(277465, 396673, 568557)),

    LineaEstado("", "TOTAL PATRIMONIO NETO Y PASIVO (A + B + C)", 0, v(5117925, 5861305, 7176041), negrita=True),
]

# ============ PyG ============
lineas_pyg = [
    LineaEstado("1", "Importe neto de la cifra de negocios", 2, v(5000000, 5750000, 6900000), negrita=True),
    LineaEstado("2", "Variación de existencias de productos terminados y en curso de fabricación", 2, v(0, 24346, 25316)),
    LineaEstado("3", "Trabajos realizados por la empresa para su activo", 2, v(0, 0, 0)),
    LineaEstado("4", "Aprovisionamientos", 2, v(-2072432, -2415333, -3133441), negrita=True),
    LineaEstado("5", "Otros ingresos de explotación", 2, v(59315, 58210, 64999)),
    LineaEstado("6", "Gastos de personal", 2, v(-1415266, -1462872, -1516324)),
    LineaEstado("7", "Otros gastos de explotación", 2, v(-577276, -599268, -620083), nota=4),
    LineaEstado("8", "Amortización del inmovilizado", 2, v(-144341, -144203, -133467), nota=5),
    LineaEstado("9", "Imputación de subvenciones de inmovilizado no financiero y otras", 2, v(0, 0, 0)),
    LineaEstado("10", "Excesos de provisiones", 2, v(0, 0, 0)),
    LineaEstado("11", "Deterioro y resultado por enajenaciones del inmovilizado", 2, v(0, -3380, 0), nota=5),
    LineaEstado("12", "Diferencia negativa de combinaciones de negocio", 2, v(0, 0, 0)),
    LineaEstado("13", "Otros resultados", 2, v(0, 0, 0)),
    LineaEstado("A)", "RESULTADO DE EXPLOTACIÓN", 1, v(850000, 1207500, 1587000), negrita=True),

    LineaEstado("14", "Ingresos financieros", 2, v(22213, 18733, 19519), negrita=True, nota=6),
    LineaEstado("a)", "De participaciones en instrumentos de patrimonio — empresas del grupo", 3, v(0, 0, 0)),
    LineaEstado("b)", "De valores negociables y de créditos del activo — terceros", 3, v(22213, 18733, 19519)),
    LineaEstado("15", "Gastos financieros", 2, v(-42819, -46000, -54000), nota=7),
    LineaEstado("16", "Variación de valor razonable en instrumentos financieros", 2, v(0, 0, 0)),
    LineaEstado("17", "Diferencias de cambio", 2, v(0, 0, 0)),
    LineaEstado("18", "Deterioro y resultado por enajenaciones de instrumentos financieros", 2, v(0, 0, 0)),
    LineaEstado("19", "Otros ingresos y gastos de carácter financiero", 2, v(0, 0, 0)),
    LineaEstado("B)", "RESULTADO FINANCIERO", 1, v(-20606, -27267, -34481), negrita=True),
    LineaEstado("C)", "RESULTADO ANTES DE IMPUESTOS", 1, v(829394, 1180233, 1552519), negrita=True),
    LineaEstado("20", "Impuestos sobre beneficios (17%)", 2, v(-140997, -200640, -263928), nota=9),
    LineaEstado("D)", "RESULTADO DEL EJERCICIO", 1, v(688397, 979593, 1288591), negrita=True),
    LineaEstado("", "Dividendo a distribuir (payout 60%)", 2, v(413038, 587756, 773155)),
]

columnas = [2023, 2024, 2025]
etq = ["2023", "2024", "2025"]

secciones = [
    construir_tabla_estado("Balance — Activo", "Modelo Abreviado · Importes en euros · Caso ajustado manualmente", lineas_activo, columnas, etq),
    construir_tabla_estado("Balance — Patrimonio Neto y Pasivo", "Modelo Abreviado · Importes en euros · Caso ajustado manualmente", lineas_pasivo, columnas, etq),
    construir_tabla_estado("Cuenta de Pérdidas y Ganancias", "Modelo Abreviado · Importes en euros · Caso ajustado manualmente", lineas_pyg, columnas, etq),
]

generar_pdf(str(Path(__file__).resolve().parent / "output" / "caso1_empresa_trampa_ajustado.pdf"),
            "Herramientas de Precisión Ibérica, S.L.", "28", "abreviado", secciones)
print("Generado.")
