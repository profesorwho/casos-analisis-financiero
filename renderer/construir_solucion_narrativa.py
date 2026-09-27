"""Paso 2 del flujo MANUAL de narrativa (encargo #115) — lee la respuesta que la persona pegó
de claude.ai (o el asistente que use), extrae el JSON de forma robusta (una respuesta de chat
normal trae prosa alrededor, probablemente un bloque ```json ... ```), la verifica con el MISMO
verificador del #114/#115-fix (`narrativa_llm.verificar_cifras` + los bancos por sección de
`mapeo_solucion_narrativo.construir_bancos_de_verdad_por_seccion`, sin tocar ninguno de los dos)
y, si todo cuadra, construye el PDF reutilizando `mapeo_solucion_narrativo.ensamblar_documento_
narrativo` (también sin tocarlo). Si algo no cuadra, no construye ningún PDF: escribe un fichero
de corrección listo para pegar de vuelta en la misma conversación.

No se modifica ni un carácter de `narrativa_llm.py`/`mapeo_solucion_narrativo.py` — este módulo
solo los importa."""
import json
import re
import sys
from pathlib import Path

_RENDERER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RENDERER_DIR.parent))
sys.path.insert(0, str(_RENDERER_DIR))

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
from generar_solucion_caso import AVISO_DOCENTE
from mapeo_solucion_narrativo import (
    construir_bancos_de_verdad_por_seccion,
    construir_paquete_verdad,
    ensamblar_documento_narrativo,
)
from narrativa_llm import (
    NOMBRES_SECCIONES,
    escribir_cache,
    verificar_cifras,
)

MODELO_ETIQUETA_MANUAL = "manual (respuesta pegada de claude.ai)"


class RespuestaSinJSONError(ValueError):
    """No se encontró en el texto pegado un objeto JSON con las 9 claves de sección — ver
    `extraer_json_de_respuesta_pegada`. Nunca se adivina contenido: si esto salta, hay que volver
    a pegar la respuesta completa."""


class MetaNoEncontradaError(FileNotFoundError):
    """Falta el `.meta.json` del paso 1 — hay que repetir `exportar_prompt` para este caso."""


class PaqueteDeVerdadDesincronizadoError(RuntimeError):
    """El paquete de verdad guardado en el paso 1 ya no coincide con el que generaría el motor
    hoy para los mismos parámetros — indica que el motor cambió entre el paso 1 y el paso 2.
    Nunca se construye un PDF con una narrativa verificada contra datos obsoletos: hay que
    repetir el paso 1 (y, probablemente, pedir una respuesta nueva del LLM)."""


# --------------------------------------------------------------------------------------------
# Extracción robusta del JSON — ver docs/decisiones_plausibilidad.md #115 para la lista completa
# de formatos aceptados/rechazados y por qué (protocolo de parada: nunca se baja el rigor para
# aceptar JSON claramente inválido, p. ej. con comillas simples).
# --------------------------------------------------------------------------------------------

_PATRON_BLOQUE_CODIGO = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def extraer_json_de_respuesta_pegada(texto: str) -> dict[str, str]:
    """Intenta, en este orden: (1) cada bloque ``` ... ``` del texto (con o sin la etiqueta
    "json"), de arriba a abajo, quedándose con el primero que sea JSON válido y tenga las 9
    claves; (2) si no hay ningún bloque de código válido, el primer "{" hasta el ÚLTIMO "}" del
    texto completo. Nunca intenta "reparar" JSON inválido (comillas simples, comas colgantes,
    etc.) — eso sería exactamente el tipo de parseo permisivo que el protocolo de parada de este
    encargo prohíbe: si el JSON está mal formado, falla con un mensaje claro en vez de adivinar."""
    candidatos = [m.group(1) for m in _PATRON_BLOQUE_CODIGO.finditer(texto)]
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio != -1 and fin != -1 and fin > inicio:
        candidatos.append(texto[inicio:fin + 1])

    errores = []
    for candidato in candidatos:
        candidato = candidato.strip()
        i, f = candidato.find("{"), candidato.rfind("}")
        if i == -1 or f == -1 or f <= i:
            errores.append("bloque sin un objeto JSON reconocible")
            continue
        try:
            datos = json.loads(candidato[i:f + 1])
        except json.JSONDecodeError as e:
            errores.append(f"JSON inválido ({e})")
            continue
        if not isinstance(datos, dict):
            errores.append("el JSON no es un objeto (dict)")
            continue
        faltantes = [s for s in NOMBRES_SECCIONES if s not in datos]
        if faltantes:
            errores.append(f"faltan las claves: {faltantes}")
            continue
        return {seccion: str(datos[seccion]) for seccion in NOMBRES_SECCIONES}

    detalle = "; ".join(errores) if errores else "no se encontró ningún '{' ... '}' en el texto"
    raise RespuestaSinJSONError(
        "No se ha podido extraer un JSON válido con las 9 secciones de la respuesta pegada "
        f"({detalle}). Vuelve a pegar la respuesta COMPLETA del LLM (incluidos los ``` si los "
        "lleva) en un fichero de texto nuevo — no se adivina contenido."
    )


# --------------------------------------------------------------------------------------------
# Mensaje de corrección — MISMA redacción que usa `narrativa_llm.generar_narrativa_con_
# verificacion` para el reintento automático (aquí el reintento lo hace la persona, no el bucle).
# Duplicado deliberadamente (no se toca narrativa_llm.py, por protocolo de este encargo) — la
# igualdad de texto está protegida por un test de regresión
# (tests/test_construir_solucion_narrativa.py::test_mensaje_correccion_coincide_con_el_de_narrativa_llm).
# --------------------------------------------------------------------------------------------

def construir_mensaje_correccion(cifras_no_verificadas_por_seccion: dict[str, list[float]]) -> str:
    detalle_fallos = "\n".join(
        f"- {seccion}: {cifras}" for seccion, cifras in cifras_no_verificadas_por_seccion.items() if cifras
    )
    return (
        "Las siguientes cifras de tu respuesta anterior NO coinciden (ni siquiera con un "
        "margen de redondeo razonable) con ningún dato del paquete de hechos que te di. "
        "Corrígelas usando SOLO números que aparezcan en el paquete de hechos original "
        "(puedes redondearlos o expresarlos como porcentaje, pero no inventar ni tomar "
        "cifras de otro ejercicio o de otro caso). Devuelve de nuevo el JSON COMPLETO con "
        "las 9 secciones.\n\nCifras sin respaldo, por sección:\n" + detalle_fallos
    )


CABECERA_CORRECCION = """\
========================================================================
CORRECCIÓN NECESARIA — narrativa manual del documento de solución (#115)
========================================================================
La respuesta pegada no superó la verificación numérica. Pega el texto de
abajo en la MISMA conversación de claude.ai donde generaste la respuesta
anterior, guarda la respuesta nueva en un fichero de texto NUEVO, y vuelve
a ejecutar `importar_respuesta` con ese fichero nuevo.
========================================================================

"""


def _escribir_correccion(ruta_respuesta_pegada, cifras_no_verificadas_por_seccion: dict[str, list[float]]) -> Path:
    ruta_respuesta_pegada = Path(ruta_respuesta_pegada)
    ruta_correccion = ruta_respuesta_pegada.with_name(ruta_respuesta_pegada.stem + "_correccion.txt")
    mensaje = construir_mensaje_correccion(cifras_no_verificadas_por_seccion)
    ruta_correccion.write_text(CABECERA_CORRECCION + mensaje, encoding="utf-8")
    return ruta_correccion


# --------------------------------------------------------------------------------------------
# Ensamblado del PDF — mismo estilo de portada/pie de página que `generar_solucion_caso_
# narrativo.py` (#114), duplicado aquí porque este es un punto de entrada nuevo e independiente
# (el flujo manual no pasa por esa función, que asume una llamada a la API síncrona).
# --------------------------------------------------------------------------------------------

styles = getSampleStyleSheet()
_portada_titulo = ParagraphStyle("PortadaTituloSolucionManual", parent=styles["Heading1"], fontSize=20, alignment=TA_CENTER, spaceAfter=6)
_portada_sub = ParagraphStyle("PortadaSubSolucionManual", parent=styles["Normal"], fontSize=11, alignment=TA_CENTER, textColor=colors.grey)
_portada_aviso = ParagraphStyle(
    "PortadaAvisoSolucionManual", parent=styles["Normal"], fontSize=10.5, alignment=TA_CENTER,
    textColor=colors.HexColor("#a83232"), fontName="Helvetica-Bold", spaceBefore=16,
)


def _pie_de_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Oblique", 7.5)
    canvas.setFillColor(colors.HexColor("#a83232"))
    canvas.drawCentredString(A4[0] / 2, 0.9 * cm, AVISO_DOCENTE)
    canvas.restoreState()


def importar_respuesta(ruta_respuesta_pegada, ruta_meta, ruta_salida_pdf, nombre_empresa) -> dict:
    """Lee la respuesta pegada, la verifica, y construye el PDF si todo cuadra. Devuelve un dict
    de estado (`verificado`, y si no lo está, `ruta_correccion`). Nunca genera un PDF con datos a
    medias: si la verificación falla, no se crea ningún fichero en `ruta_salida_pdf`."""
    ruta_meta = Path(ruta_meta)
    if not ruta_meta.exists():
        raise MetaNoEncontradaError(
            f"No se encuentra {ruta_meta} — repite el paso 1 (`exportar_prompt`) para este caso "
            "antes de importar una respuesta."
        )
    metadatos = json.loads(ruta_meta.read_text(encoding="utf-8"))
    paquete_verdad_guardado = metadatos["paquete_verdad"]

    texto_respuesta = Path(ruta_respuesta_pegada).read_text(encoding="utf-8")
    secciones = extraer_json_de_respuesta_pegada(texto_respuesta)

    bancos_por_seccion = construir_bancos_de_verdad_por_seccion(paquete_verdad_guardado)
    cifras_no_verificadas_por_seccion = {
        seccion: verificar_cifras(texto, bancos_por_seccion[seccion]) for seccion, texto in secciones.items()
    }
    if any(cifras_no_verificadas_por_seccion.values()):
        ruta_correccion = _escribir_correccion(ruta_respuesta_pegada, cifras_no_verificadas_por_seccion)
        return {"verificado": False, "ruta_correccion": str(ruta_correccion), "cifras_no_verificadas_por_seccion": cifras_no_verificadas_por_seccion}

    # Regenera el caso (determinista: misma semilla -> mismo caso) para reconstruir las tablas y
    # comprobar que el paquete de verdad no ha cambiado desde el paso 1 (si el motor cambió entre
    # medias, esto lo detecta en vez de servir una narrativa desincronizada de los datos).
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(
        metadatos["sector"], metadatos["segmento"], metadatos["ventas_objetivo"], metadatos["semilla"],
        metadatos["arquetipos_intensidades"], catalogo=catalogo, arquetipos=arquetipos,
    )
    ejercicios = evolucion.ejercicios
    modelo_clasificacion = clasificar_caso(evolucion, metadatos["sector"], metadatos["segmento"], catalogo)
    efes = {
        2024: generar_efe(ejercicios[2023], ejercicios[2024], True),
        2025: generar_efe(ejercicios[2024], ejercicios[2025], True),
    }
    calendario = calcular_calendario_deuda(evolucion)
    paquete_verdad_actual = construir_paquete_verdad(evolucion, ejercicios, efes, calendario, arquetipos)
    if paquete_verdad_actual != paquete_verdad_guardado:
        raise PaqueteDeVerdadDesincronizadoError(
            "El paquete de verdad ya no coincide con el del paso 1 — el motor ha cambiado entre "
            "medias. Repite el paso 1 (exportar_prompt) y pide una respuesta nueva del LLM."
        )

    escribir_cache(metadatos["clave"], secciones, MODELO_ETIQUETA_MANUAL, intentos=1)

    secciones_flow = ensamblar_documento_narrativo(evolucion, ejercicios, efes, calendario, secciones)

    ruta_salida_pdf = Path(ruta_salida_pdf)
    ruta_salida_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(ruta_salida_pdf), pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.7 * cm,
                             leftMargin=1.3 * cm, rightMargin=1.3 * cm)
    flow = [
        Spacer(1, 5 * cm),
        Paragraph("Análisis y Solución del Caso", _portada_titulo),
        Paragraph(nombre_empresa, _portada_sub),
        Paragraph(f"Sector: {metadatos['sector']} · Ejercicios 2023-2025 · Modelo {modelo_clasificacion.capitalize()}", _portada_sub),
        Paragraph(AVISO_DOCENTE, _portada_aviso),
        PageBreak(),
    ]
    for seccion in secciones_flow:
        flow.extend(seccion)
        flow.append(PageBreak())
    if flow and isinstance(flow[-1], PageBreak):
        flow.pop()
    doc.build(flow, onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)

    return {"verificado": True, "ruta_pdf": str(ruta_salida_pdf), "modelo_clasificacion": modelo_clasificacion}
