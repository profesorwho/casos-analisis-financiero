"""Tests del paso 2 del flujo manual de narrativa (encargo #115, `renderer/construir_solucion_
narrativa.py`) — sin llamar a ninguna API. Cubre lo pedido explícitamente: extracción robusta de
JSON de una respuesta "de chat" pegada (>=5 formatos, sin "reparar" JSON inválido — protocolo de
parada del encargo); el mensaje de corrección coincide LITERALMENTE con el que usa
`narrativa_llm.generar_narrativa_con_verificacion` para el reintento automático; el flujo
completo `importar_respuesta` (válido -> PDF + caché; inválido -> fichero de corrección, sin PDF;
meta ausente; paquete de verdad desincronizado) sobre un caso REAL; y los 16 casos sintéticos de
invención de cifras del #114 (`tests/test_narrativa_llm.py::CASOS_SINTETICOS`), reutilizados a
escala real contra los bancos por sección del mismo caso (arreglo del #115-fix)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "renderer"))

import narrativa_llm
from mapeo_solucion_narrativo import construir_bancos_de_verdad_por_seccion, construir_paquete_verdad
from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.memoria import generar_caso_combinado
from motor.efe import generar_efe
from motor.calendario_deuda import calcular_calendario_deuda
from narrativa_llm import NOMBRES_SECCIONES, VerificacionNumericaError, calcular_clave_cache, verificar_cifras

import construir_solucion_narrativa as csn
from construir_solucion_narrativa import (
    MetaNoEncontradaError,
    PaqueteDeVerdadDesincronizadoError,
    RespuestaSinJSONError,
    construir_mensaje_correccion,
    extraer_json_de_respuesta_pegada,
    importar_respuesta,
)

SECTOR, SEGMENTO, VENTAS, SEMILLA = "28", "grandes_medianas", 15_000_000.0, 15
ARQUETIPOS = {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}


@pytest.fixture(autouse=True)
def _cache_aislada(monkeypatch, tmp_path):
    monkeypatch.setattr(narrativa_llm, "DIRECTORIO_CACHE", tmp_path / "narrativa_cache")


@pytest.fixture(scope="module")
def caso_real():
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(SECTOR, SEGMENTO, VENTAS, SEMILLA, ARQUETIPOS, catalogo=catalogo, arquetipos=arquetipos)
    ejercicios = evolucion.ejercicios
    efes = {2024: generar_efe(ejercicios[2023], ejercicios[2024], True), 2025: generar_efe(ejercicios[2024], ejercicios[2025], True)}
    calendario = calcular_calendario_deuda(evolucion)
    paquete_verdad = construir_paquete_verdad(evolucion, ejercicios, efes, calendario, arquetipos)
    return {"evolucion": evolucion, "paquete_verdad": paquete_verdad}


def _texto_9_secciones(por_seccion: dict[str, str]) -> str:
    return json.dumps(por_seccion, ensure_ascii=False)


def _secciones_neutras(**overrides) -> dict[str, str]:
    base = {seccion: "Análisis sin cifras específicas en esta sección." for seccion in NOMBRES_SECCIONES}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------------------------
# (1) Extracción robusta de JSON — >=5 formatos, nunca "repara" JSON inválido.
# --------------------------------------------------------------------------------------------

def test_extraccion_bloque_json_con_etiqueta():
    texto = "Aquí tienes mi respuesta:\n```json\n" + _texto_9_secciones(_secciones_neutras()) + "\n```\nEspero que sirva."
    datos = extraer_json_de_respuesta_pegada(texto)
    assert set(datos) == set(NOMBRES_SECCIONES)


def test_extraccion_bloque_codigo_sin_etiqueta_json():
    texto = "```\n" + _texto_9_secciones(_secciones_neutras()) + "\n```"
    datos = extraer_json_de_respuesta_pegada(texto)
    assert set(datos) == set(NOMBRES_SECCIONES)


def test_extraccion_sin_bloques_de_codigo_por_fuerza_bruta():
    texto = "Claro, aquí está: " + _texto_9_secciones(_secciones_neutras()) + " ¿Necesitas algo más?"
    datos = extraer_json_de_respuesta_pegada(texto)
    assert set(datos) == set(NOMBRES_SECCIONES)


def test_extraccion_falla_si_falta_una_seccion():
    incompleto = _secciones_neutras()
    del incompleto["seccion_5"]
    texto = "```json\n" + json.dumps(incompleto, ensure_ascii=False) + "\n```"
    with pytest.raises(RespuestaSinJSONError, match="seccion_5"):
        extraer_json_de_respuesta_pegada(texto)


def test_extraccion_no_repara_json_con_comillas_simples():
    """Protocolo de parada del encargo: nunca se "arregla" JSON inválido en silencio."""
    texto = "```json\n{'seccion_1': 'texto'}\n```"
    with pytest.raises(RespuestaSinJSONError):
        extraer_json_de_respuesta_pegada(texto)


def test_extraccion_sin_ningun_objeto_json_en_el_texto():
    with pytest.raises(RespuestaSinJSONError, match="no se encontró"):
        extraer_json_de_respuesta_pegada("No he podido generar una respuesta esta vez.")


def test_extraccion_elige_el_primer_bloque_valido_con_las_9_claves():
    incompleto = _secciones_neutras()
    del incompleto["seccion_2"]
    completo = _secciones_neutras(seccion_1="del segundo bloque")
    texto = (
        "Primer intento (incompleto):\n```json\n" + json.dumps(incompleto, ensure_ascii=False) + "\n```\n"
        "Versión corregida:\n```json\n" + json.dumps(completo, ensure_ascii=False) + "\n```"
    )
    datos = extraer_json_de_respuesta_pegada(texto)
    assert datos["seccion_1"] == "del segundo bloque"


# --------------------------------------------------------------------------------------------
# (2) El mensaje de corrección coincide LITERALMENTE con el de narrativa_llm (duplicado
# deliberado, protegido aquí).
# --------------------------------------------------------------------------------------------

def test_mensaje_correccion_coincide_con_el_de_narrativa_llm(monkeypatch):
    capturado = {}

    def _llamar_llm_falso(mensajes, modelo=None):
        if len(mensajes) > 1:
            capturado["mensaje"] = mensajes[-1]["content"]
        return {seccion: "Cifra inventada del 999%." for seccion in NOMBRES_SECCIONES}

    monkeypatch.setattr(narrativa_llm, "llamar_llm", _llamar_llm_falso)
    banco_vacio: set[float] = set()
    bancos = {seccion: banco_vacio for seccion in NOMBRES_SECCIONES}
    with pytest.raises(VerificacionNumericaError) as exc_info:
        narrativa_llm.generar_narrativa_con_verificacion("prompt de prueba", bancos)

    assert "mensaje" in capturado, "el cliente simulado nunca recibió un turno de corrección"
    assert capturado["mensaje"] == construir_mensaje_correccion(exc_info.value.cifras_no_verificadas_por_seccion)


# --------------------------------------------------------------------------------------------
# (3) importar_respuesta — flujo completo sobre un caso REAL.
# --------------------------------------------------------------------------------------------

def _preparar_meta(tmp_path, caso_real) -> Path:
    ruta_meta = tmp_path / "prompt.meta.json"
    metadatos = {
        "clave": calcular_clave_cache(SECTOR, SEGMENTO, VENTAS, SEMILLA, ARQUETIPOS, caso_real["paquete_verdad"]),
        "sector": SECTOR, "segmento": SEGMENTO, "ventas_objetivo": VENTAS, "semilla": SEMILLA,
        "arquetipos_intensidades": ARQUETIPOS, "paquete_verdad": caso_real["paquete_verdad"],
    }
    ruta_meta.write_text(json.dumps(metadatos, ensure_ascii=False), encoding="utf-8")
    return ruta_meta


def test_importar_respuesta_meta_no_encontrada(tmp_path):
    ruta_respuesta = tmp_path / "respuesta.txt"
    ruta_respuesta.write_text("{}", encoding="utf-8")
    with pytest.raises(MetaNoEncontradaError):
        importar_respuesta(str(ruta_respuesta), str(tmp_path / "no_existe.meta.json"), str(tmp_path / "salida.pdf"), "Empresa de prueba")


def test_importar_respuesta_valida_genera_pdf_y_cachea(tmp_path, caso_real):
    ruta_meta = _preparar_meta(tmp_path, caso_real)
    roe_2025_pct = round(caso_real["paquete_verdad"]["ratios_por_año"]["2025"]["ratios.roe"] * 100)
    liquidez_2025 = caso_real["paquete_verdad"]["ratios_por_año"]["2025"]["ratios.liquidez"]

    secciones = _secciones_neutras(
        seccion_1="El caso incorpora 2 arquetipos y presenta 6 señales de alerta.",
        seccion_3=f"La liquidez general se sitúa en torno a {liquidez_2025:.1f}.",
        seccion_6=f"La rentabilidad financiera (ROE) ronda el {roe_2025_pct}% en 2025.",
    )
    ruta_respuesta = tmp_path / "respuesta.txt"
    ruta_respuesta.write_text("```json\n" + json.dumps(secciones, ensure_ascii=False) + "\n```", encoding="utf-8")

    ruta_pdf = tmp_path / "salida.pdf"
    resultado = importar_respuesta(str(ruta_respuesta), str(ruta_meta), str(ruta_pdf), "Empresa de prueba")

    assert resultado["verificado"] is True
    assert Path(resultado["ruta_pdf"]).exists()
    assert not (tmp_path / "respuesta_correccion.txt").exists()

    metadatos = json.loads(ruta_meta.read_text(encoding="utf-8"))
    cacheado = narrativa_llm.leer_cache(metadatos["clave"])
    assert cacheado is not None
    assert cacheado["modelo"] == csn.MODELO_ETIQUETA_MANUAL
    assert cacheado["secciones"]["seccion_6"] == secciones["seccion_6"]


def test_importar_respuesta_invalida_escribe_correccion_sin_pdf(tmp_path, caso_real):
    """Reproduce el hallazgo del #115-fix pero YA CORREGIDO: una cifra de ROE claramente
    inventada, muy alejada del valor real, se rechaza — sin el arreglo por sección esto colaba
    (ver decisiones_plausibilidad.md #115-fix)."""
    ruta_meta = _preparar_meta(tmp_path, caso_real)
    secciones = _secciones_neutras(seccion_6="La rentabilidad financiera (ROE) alcanza el 35%.")
    ruta_respuesta = tmp_path / "respuesta.txt"
    ruta_respuesta.write_text("```json\n" + json.dumps(secciones, ensure_ascii=False) + "\n```", encoding="utf-8")

    ruta_pdf = tmp_path / "salida.pdf"
    resultado = importar_respuesta(str(ruta_respuesta), str(ruta_meta), str(ruta_pdf), "Empresa de prueba")

    assert resultado["verificado"] is False
    assert not ruta_pdf.exists()
    ruta_correccion = Path(resultado["ruta_correccion"])
    assert ruta_correccion.exists()
    assert "35.0" in ruta_correccion.read_text(encoding="utf-8")
    assert resultado["cifras_no_verificadas_por_seccion"]["seccion_6"] == [35.0]

    metadatos = json.loads(ruta_meta.read_text(encoding="utf-8"))
    assert narrativa_llm.leer_cache(metadatos["clave"]) is None


def test_importar_respuesta_paquete_de_verdad_desincronizado(tmp_path, caso_real, monkeypatch):
    """Si el motor cambió entre el paso 1 y el paso 2, nunca se sirve una narrativa verificada
    contra datos obsoletos — se detecta comparando el paquete de verdad regenerado con el
    guardado."""
    ruta_meta = _preparar_meta(tmp_path, caso_real)
    secciones = _secciones_neutras()
    ruta_respuesta = tmp_path / "respuesta.txt"
    ruta_respuesta.write_text("```json\n" + json.dumps(secciones, ensure_ascii=False) + "\n```", encoding="utf-8")

    def _paquete_verdad_alterado(*args, **kwargs):
        alterado = dict(caso_real["paquete_verdad"])
        alterado["meta"] = dict(alterado["meta"])
        alterado["meta"]["semilla"] = 999999
        return alterado

    monkeypatch.setattr(csn, "construir_paquete_verdad", _paquete_verdad_alterado)

    with pytest.raises(PaqueteDeVerdadDesincronizadoError):
        importar_respuesta(str(ruta_respuesta), str(ruta_meta), str(tmp_path / "salida.pdf"), "Empresa de prueba")


# --------------------------------------------------------------------------------------------
# (4) Los 16 casos sintéticos del #114 (`test_narrativa_llm.CASOS_SINTETICOS`), reutilizados a
# ESCALA REAL contra los bancos por sección del mismo caso (el que reveló el hallazgo del
# #115-fix) — cada texto se compara contra el banco de la sección donde legítimamente aparecería.
# --------------------------------------------------------------------------------------------

CASOS_SINTETICOS_POR_SECCION = [
    # (texto, debe_pasar, seccion)
    ("La rentabilidad financiera (ROE) ronda el 11% en 2025.", True, "seccion_6"),
    ("El resultado del ejercicio ascendió a 921.926 euros.", True, "seccion_5"),
    ("El resultado del ejercicio superó los 900.000 euros.", True, "seccion_5"),
    ("El fondo de maniobra alcanza aproximadamente 5,07 millones de euros.", True, "seccion_2"),
    ("La liquidez general se sitúa en torno a 1,8.", True, "seccion_3"),
    ("El endeudamiento ronda el 52%.", True, "seccion_4"),
    ("La rentabilidad económica (ROI) es de aproximadamente el 7%.", True, "seccion_6"),
    ("El caso incorpora 2 arquetipos y presenta 6 señales de alerta.", True, "seccion_1"),
    ("En 2025 la situación mejora respecto a años anteriores.", True, "seccion_1"),
    ("La rentabilidad financiera (ROE) alcanza el 35%.", False, "seccion_6"),
    ("El resultado del ejercicio fue de 1.500.000 euros.", False, "seccion_5"),
    ("El resultado del ejercicio de OTRO caso fue de 250.000 euros.", False, "seccion_5"),
    ("El endeudamiento es del 90%, una cifra alarmante.", False, "seccion_4"),
    ("Se detectan 20 señales de alerta en el caso.", False, "seccion_8"),
    ("El fondo de maniobra es de 12 millones de euros.", False, "seccion_2"),
    ("La liquidez general es de 4,5, un valor muy alto.", False, "seccion_3"),
]


@pytest.mark.parametrize("texto,debe_pasar,seccion", CASOS_SINTETICOS_POR_SECCION)
def test_casos_sinteticos_del_114_a_escala_real(caso_real, texto, debe_pasar, seccion):
    bancos = construir_bancos_de_verdad_por_seccion(caso_real["paquete_verdad"])
    fallos = verificar_cifras(texto, bancos[seccion])
    pasa = len(fallos) == 0
    assert pasa == debe_pasar, f"texto={texto!r} seccion={seccion} fallos={fallos}"


def test_casos_sinteticos_del_114_cubre_al_menos_15():
    assert len(CASOS_SINTETICOS_POR_SECCION) >= 15
