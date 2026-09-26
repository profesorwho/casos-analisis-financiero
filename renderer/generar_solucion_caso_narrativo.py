"""Documento de solución del caso, modo NARRATIVO (encargo #114) — misma firma que
`generar_solucion_caso` (#113) más `forzar_regeneracion`/`estricto_api`. El modo determinista del
#113 (`renderer/generar_solucion_caso.py`) sigue funcionando exactamente igual y es el modo por
defecto/de respaldo si la narración falla — no se toca ni se borra nada de él."""
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
from generar_solucion_caso import AVISO_DOCENTE, EvolucionSinPlausibilidadError
from mapeo_solucion import generar_documento_solucion
from mapeo_solucion_narrativo import construir_paquete_verdad, ensamblar_documento_narrativo, obtener_narrativa
from narrativa_llm import NarrativaLLMError, VerificacionNumericaError

styles = getSampleStyleSheet()
portada_titulo = ParagraphStyle("PortadaTituloSolucionNarr", parent=styles["Heading1"], fontSize=20, alignment=TA_CENTER, spaceAfter=6)
portada_sub = ParagraphStyle("PortadaSubSolucionNarr", parent=styles["Normal"], fontSize=11, alignment=TA_CENTER, textColor=colors.grey)
portada_aviso = ParagraphStyle(
    "PortadaAvisoSolucionNarr", parent=styles["Normal"], fontSize=10.5, alignment=TA_CENTER,
    textColor=colors.HexColor("#a83232"), fontName="Helvetica-Bold", spaceBefore=16,
)
aviso_fallback = ParagraphStyle(
    "AvisoFallback", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
    textColor=colors.HexColor("#a86a32"), fontName="Helvetica-Oblique", spaceBefore=6, spaceAfter=6,
)


def _pie_de_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Oblique", 7.5)
    canvas.setFillColor(colors.HexColor("#a83232"))
    canvas.drawCentredString(A4[0] / 2, 0.9 * cm, AVISO_DOCENTE)
    canvas.restoreState()


def generar_solucion_caso_narrativo(
    sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades, nombre_empresa, ruta_salida,
    forzar_regeneracion: bool = False, estricto_api: bool = True, modelo: str | None = None,
):
    """MISMA firma que `generar_solucion_caso` (#113) + `forzar_regeneracion` (ignora la caché) +
    `estricto_api` (comportamiento por defecto SEGURO: `True` propaga la excepción si la
    narración falla tras los reintentos, en vez de generar un PDF con datos a medias; `False`
    cae al modo determinista del #113 con un aviso visible en la portada del PDF)."""
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades,
                                        catalogo=catalogo, arquetipos=arquetipos)
    if evolucion.plausibilidad is None:
        raise EvolucionSinPlausibilidadError(
            f"evolucion.plausibilidad es None para {sector}/{segmento}/semilla {semilla} — "
            "protocolo de parada, no se genera el documento."
        )

    ejercicios = evolucion.ejercicios
    modelo_clasificacion = clasificar_caso(evolucion, sector, segmento, catalogo)
    obligatorio = modelo_clasificacion == "normal"
    efes = {
        2024: generar_efe(ejercicios[2023], ejercicios[2024], obligatorio),
        2025: generar_efe(ejercicios[2024], ejercicios[2025], obligatorio),
    }
    calendario = calcular_calendario_deuda(evolucion)
    paquete_verdad = construir_paquete_verdad(evolucion, ejercicios, efes, calendario, arquetipos)

    aviso_narrativo = None
    modo_usado = "narrativo"
    try:
        textos_por_seccion, metadatos = obtener_narrativa(
            sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades, paquete_verdad,
            modelo=modelo, forzar_regeneracion=forzar_regeneracion,
        )
        secciones = ensamblar_documento_narrativo(evolucion, ejercicios, efes, calendario, textos_por_seccion)
    except (NarrativaLLMError, VerificacionNumericaError) as e:
        if estricto_api:
            raise
        modo_usado = "determinista_fallback"
        aviso_narrativo = (
            f"AVISO: la narración por IA no estuvo disponible ({type(e).__name__}) — este "
            "documento se ha generado en modo determinista (encargo #113) como alternativa "
            "segura."
        )
        secciones = generar_documento_solucion(evolucion, ejercicios, efes, calendario)

    Path(ruta_salida).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(ruta_salida, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.7 * cm,
                             leftMargin=1.3 * cm, rightMargin=1.3 * cm)
    flow = [
        Spacer(1, 5 * cm),
        Paragraph("Análisis y Solución del Caso", portada_titulo),
        Paragraph(nombre_empresa, portada_sub),
        Paragraph(f"Sector: {sector} · Ejercicios 2023-2025 · Modelo {modelo_clasificacion.capitalize()}", portada_sub),
        Paragraph(AVISO_DOCENTE, portada_aviso),
    ]
    if aviso_narrativo:
        flow.append(Paragraph(aviso_narrativo, aviso_fallback))
    flow.append(PageBreak())
    for seccion in secciones:
        flow.extend(seccion)
        flow.append(PageBreak())
    if flow and isinstance(flow[-1], PageBreak):
        flow.pop()
    doc.build(flow, onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)
    return modelo_clasificacion, modo_usado


if __name__ == "__main__":
    modelo_resultado, modo = generar_solucion_caso_narrativo(
        sector="28", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=15,
        arquetipos_intensidades={"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        nombre_empresa="Herramientas de Precisión Ibérica, S.L.",
        ruta_salida=str(_RENDERER_DIR / "output" / "solucion_caso_narrativo.pdf"),
        estricto_api=False,
    )
    print("Modelo:", modelo_resultado, "- modo:", modo)
