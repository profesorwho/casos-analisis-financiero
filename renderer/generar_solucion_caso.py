"""Documento de solución del caso — encargo #113. Tercer PDF del proyecto (junto a las cuentas
anuales, `renderer/generar_caso_completo.py`), puramente didáctico para el profesorado: NO forma
parte de las cuentas anuales del caso. Lee `evolucion.plausibilidad` (motor/evolucion_arquetipo.py)
y no toca ningún fichero de `motor/` — ver `renderer/mapeo_solucion.py` para las 9 secciones."""
import sys
from pathlib import Path

_RENDERER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RENDERER_DIR.parent))  # raíz del repo, para motor.*
sys.path.insert(0, str(_RENDERER_DIR))  # renderer/, para los módulos hermanos

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.memoria import generar_caso_combinado
from motor.efe import generar_efe
from motor.calendario_deuda import calcular_calendario_deuda

from clasificacion import clasificar_caso
from mapeo_solucion import generar_documento_solucion

styles = getSampleStyleSheet()
portada_titulo = ParagraphStyle("PortadaTituloSolucion", parent=styles["Heading1"], fontSize=20, alignment=TA_CENTER, spaceAfter=6)
portada_sub = ParagraphStyle("PortadaSubSolucion", parent=styles["Normal"], fontSize=11, alignment=TA_CENTER, textColor=colors.grey)
portada_aviso = ParagraphStyle(
    "PortadaAvisoSolucion", parent=styles["Normal"], fontSize=10.5, alignment=TA_CENTER,
    textColor=colors.HexColor("#a83232"), fontName="Helvetica-Bold", spaceBefore=16,
)

AVISO_DOCENTE = "Documento de solución — uso docente, no es parte de las cuentas anuales del caso"


class EvolucionSinPlausibilidadError(RuntimeError):
    """`evolucion.plausibilidad` es None en la ruta normal de generación — protocolo de parada
    del encargo #113: no se genera ningún documento con datos a medias."""


def _pie_de_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Oblique", 7.5)
    canvas.setFillColor(colors.HexColor("#a83232"))
    ancho_pagina = A4[0]
    canvas.drawCentredString(ancho_pagina / 2, 0.9 * cm, AVISO_DOCENTE)
    canvas.restoreState()


def generar_solucion_caso(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades,
                           nombre_empresa, ruta_salida):
    """MISMA firma que `generar_caso_completo` — llamada con los mismos parámetros produce el
    documento de solución del mismo caso exacto (mismo `evolucion`)."""
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades,
                                        catalogo=catalogo, arquetipos=arquetipos)
    if evolucion.plausibilidad is None:
        raise EvolucionSinPlausibilidadError(
            f"evolucion.plausibilidad es None para {sector}/{segmento}/semilla {semilla} — "
            "protocolo de parada del encargo #113, no se genera el documento."
        )

    ejercicios = evolucion.ejercicios
    modelo = clasificar_caso(evolucion, sector, segmento, catalogo)
    obligatorio = modelo == "normal"
    efes = {
        2024: generar_efe(ejercicios[2023], ejercicios[2024], obligatorio),
        2025: generar_efe(ejercicios[2024], ejercicios[2025], obligatorio),
    }
    calendario = calcular_calendario_deuda(evolucion)

    secciones = generar_documento_solucion(evolucion, ejercicios, efes, calendario)

    Path(ruta_salida).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(ruta_salida, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.7 * cm,
                             leftMargin=1.3 * cm, rightMargin=1.3 * cm)
    flow = [
        Spacer(1, 5 * cm),
        Paragraph("Análisis y Solución del Caso", portada_titulo),
        Paragraph(nombre_empresa, portada_sub),
        Paragraph(f"Sector: {sector} · Ejercicios 2023-2025 · Modelo {modelo.capitalize()}", portada_sub),
        Paragraph(AVISO_DOCENTE, portada_aviso),
        PageBreak(),
    ]
    for seccion in secciones:
        flow.extend(seccion)
        flow.append(PageBreak())
    if flow and isinstance(flow[-1], PageBreak):
        flow.pop()
    doc.build(flow, onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)
    return modelo


if __name__ == "__main__":
    modelo = generar_solucion_caso(
        sector="28", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=15,
        arquetipos_intensidades={"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        nombre_empresa="Herramientas de Precisión Ibérica, S.L.",
        ruta_salida=str(_RENDERER_DIR / "output" / "solucion_caso.pdf"),
    )
    print("Modelo:", modelo)
