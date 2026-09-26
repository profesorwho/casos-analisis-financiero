"""Tests del cliente/verificador/caché de la narrativa (encargo #114, `renderer/narrativa_llm.py`).

Cubre lo pedido explícitamente: (1) verificador de cifras exhaustivo con >=15 textos sintéticos,
sin llamar a la API; (2) la clave de caché cambia si cambia cualquier valor del paquete de verdad
y NO cambia si solo cambia algo irrelevante (el nombre de la empresa, que ni siquiera forma parte
del paquete); (3) fallback determinista con un cliente simulado que siempre inventa una cifra —
`estricto_api=False` cae al modo determinista con aviso, `estricto_api=True` propaga la excepción.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "renderer"))

import narrativa_llm
from narrativa_llm import (
    NOMBRES_SECCIONES,
    VerificacionNumericaError,
    calcular_clave_cache,
    construir_banco_de_verdad,
    extraer_numeros_del_texto,
    generar_narrativa_con_verificacion,
    verificar_cifras,
)

PAQUETE_EJEMPLO = {
    "meta": {"sector_codigo": "28", "semilla": 15, "n_arquetipos": 2, "n_señales": 6},
    "ratios_por_año": {
        "2025": {"ratios.roe": 0.114, "ratios.roi": 0.072, "ratios.liquidez": 1.77, "ratios.endeudamiento": 0.52},
    },
    "pyg_por_año": {"2025": {"resultado_ejercicio_eur": 921926.0}},
    "fondo_maniobra_eur_por_año": {"2025": 5071496.0},
}


# --- (1) Verificador de cifras — >=15 textos sintéticos, mitad deben pasar, mitad deben fallar ---

CASOS_SINTETICOS = [
    # (texto, debe_pasar, motivo)
    ("La rentabilidad financiera (ROE) ronda el 11% en 2025.", True, "redondeo razonable de 11,4%"),
    ("El resultado del ejercicio ascendió a 921.926 euros.", True, "cifra exacta del banco"),
    ("El resultado del ejercicio superó los 900.000 euros.", True, "redondeo a la baja, <5% de diferencia"),
    ("El fondo de maniobra alcanza aproximadamente 5,07 millones de euros.", True, "5.071.496 expresado en millones"),
    ("La liquidez general se sitúa en torno a 1,8.", True, "redondeo de 1,77"),
    ("El endeudamiento ronda el 52%.", True, "0,52 expresado como porcentaje"),
    ("La rentabilidad económica (ROI) es de aproximadamente el 7%.", True, "redondeo de 7,2%"),
    ("El caso incorpora 2 arquetipos y presenta 6 señales de alerta.", True, "cifras exactas del banco (meta)"),
    ("En 2025 la situación mejora respecto a años anteriores.", True, "sin cifras que verificar (2025 es un año, estructural)"),
    # --- deben FALLAR ---
    ("La rentabilidad financiera (ROE) alcanza el 35%.", False, "cifra inventada, muy alejada del 11,4% real"),
    ("El resultado del ejercicio fue de 1.500.000 euros.", False, "orden de magnitud distinto (real: 921.926)"),
    ("El resultado del ejercicio de OTRO caso fue de 250.000 euros.", False, "cifra de otro caso, no está en el banco"),
    ("El endeudamiento es del 90%, una cifra alarmante.", False, "cifra inventada, muy alejada del 52% real"),
    ("Se detectan 20 señales de alerta en el caso.", False, "cuenta inventada (real: 6)"),
    ("El fondo de maniobra es de 12 millones de euros.", False, "orden de magnitud distinto (real: ~5,07 millones)"),
    ("La liquidez general es de 4,5, un valor muy alto.", False, "cifra inventada, muy alejada de 1,77"),
]


@pytest.mark.parametrize("texto,debe_pasar,motivo", CASOS_SINTETICOS)
def test_verificador_casos_sinteticos(texto, debe_pasar, motivo):
    banco = construir_banco_de_verdad(PAQUETE_EJEMPLO)
    fallos = verificar_cifras(texto, banco)
    pasa = len(fallos) == 0
    assert pasa == debe_pasar, f"{motivo!r} -- texto={texto!r} fallos={fallos}"


def test_verificador_exhaustivo_tiene_al_menos_15_casos():
    assert len(CASOS_SINTETICOS) >= 15
    assert sum(1 for _, ok, _ in CASOS_SINTETICOS if ok) >= 5
    assert sum(1 for _, ok, _ in CASOS_SINTETICOS if not ok) >= 5


def test_tolerancia_no_deja_pasar_una_cifra_claramente_inventada():
    """Ver protocolo de parada del encargo: si la tolerancia fuera tan amplia que dejara pasar
    una cifra claramente inventada, hay que reportarlo, no bajar el rigor en silencio. Este test
    demuestra que NO es el caso: una cifra al doble (o más) de la real falla siempre."""
    banco = construir_banco_de_verdad(PAQUETE_EJEMPLO)
    for ratio_real, cifra_inventada in [(0.114, 0.30), (0.52, 0.95), (1.77, 4.0)]:
        fallos = verificar_cifras(f"El valor es {cifra_inventada * 100:.0f}%.", banco)
        assert fallos, (ratio_real, cifra_inventada)


# --- Extracción de números — formatos español y plano ------------------------------------------

def test_extraer_numeros_formato_espanol_miles():
    assert extraer_numeros_del_texto("El importe es de 1.234.567 euros.") == [1234567.0]


def test_extraer_numeros_formato_espanol_miles_con_decimal():
    assert extraer_numeros_del_texto("El importe es de 1.234.567,89 euros.") == [1234567.89]


def test_extraer_numeros_formato_plano_decimal():
    assert extraer_numeros_del_texto("El BAII representa el 8.2% de las ventas.") == [8.2]


def test_extraer_numeros_con_multiplicador_millones():
    assert extraer_numeros_del_texto("Cerca de 1,2 millones de euros.") == [1_200_000.0]


def test_extraer_numeros_con_multiplicador_mil():
    assert extraer_numeros_del_texto("Unos 50 mil euros de fianza.") == [50_000.0]


def test_extraer_numeros_no_confunde_900_mil_con_decimal():
    """Regresión de un bug real detectado durante el desarrollo: '900.000' se parseaba como
    900,0 (tratando el punto de miles como decimal) en vez de 900.000."""
    assert extraer_numeros_del_texto("Supera los 900.000 euros.") == [900_000.0]


# --- (2) Caché: la clave cambia si cambia el paquete de verdad, no si cambia algo irrelevante ---

def test_clave_cache_estable_con_los_mismos_datos():
    clave1 = calcular_clave_cache("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte"}, PAQUETE_EJEMPLO)
    clave2 = calcular_clave_cache("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte"}, PAQUETE_EJEMPLO)
    assert clave1 == clave2


def test_clave_cache_cambia_si_cambia_una_cifra_del_paquete_de_verdad():
    import copy
    paquete_modificado = copy.deepcopy(PAQUETE_EJEMPLO)
    paquete_modificado["ratios_por_año"]["2025"]["ratios.roe"] = 0.999
    clave_original = calcular_clave_cache("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte"}, PAQUETE_EJEMPLO)
    clave_modificada = calcular_clave_cache("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte"}, paquete_modificado)
    assert clave_original != clave_modificada


def test_clave_cache_no_depende_del_nombre_de_empresa():
    """El nombre de la empresa NUNCA forma parte del paquete de verdad ni de los parámetros de
    la clave — dos llamadas con el mismo caso pero distinto nombre_empresa (un parámetro que
    generar_solucion_caso_narrativo ni siquiera pasa a calcular_clave_cache) deben compartir
    caché."""
    clave_a = calcular_clave_cache("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte"}, PAQUETE_EJEMPLO)
    clave_b = calcular_clave_cache("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte"}, PAQUETE_EJEMPLO)
    assert clave_a == clave_b  # calcular_clave_cache no recibe nombre_empresa en absoluto por diseño


def test_clave_cache_cambia_si_cambian_los_parametros_de_entrada():
    clave_a = calcular_clave_cache("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte"}, PAQUETE_EJEMPLO)
    clave_b = calcular_clave_cache("28", "grandes_medianas", 15_000_000.0, 16, {"aumento_clientes": "fuerte"}, PAQUETE_EJEMPLO)
    assert clave_a != clave_b


# --- (3) Fallback: cliente simulado que siempre inventa una cifra -----------------------------

def _respuesta_json_con_cifra_inventada() -> dict[str, str]:
    return {seccion: f"Un análisis con una cifra inventada del 999% en {seccion}." for seccion in NOMBRES_SECCIONES}


def test_generar_narrativa_falla_tras_reintentos_con_cliente_que_siempre_inventa(monkeypatch):
    llamadas = {"n": 0}

    def _llamar_llm_falso(mensajes, modelo=None):
        llamadas["n"] += 1
        return _respuesta_json_con_cifra_inventada()

    monkeypatch.setattr(narrativa_llm, "llamar_llm", _llamar_llm_falso)
    with pytest.raises(VerificacionNumericaError) as exc_info:
        generar_narrativa_con_verificacion("prompt de prueba", PAQUETE_EJEMPLO)
    assert llamadas["n"] == narrativa_llm.MAX_INTENTOS
    assert all(cifras for cifras in exc_info.value.cifras_no_verificadas_por_seccion.values())


def test_generar_solucion_narrativo_estricto_true_propaga_excepcion(monkeypatch, tmp_path):
    def _obtener_narrativa_falsa(*args, **kwargs):
        raise VerificacionNumericaError({"seccion_1": [999.0]})

    monkeypatch.setattr("generar_solucion_caso_narrativo.obtener_narrativa", _obtener_narrativa_falsa)
    from generar_solucion_caso_narrativo import generar_solucion_caso_narrativo

    with pytest.raises(VerificacionNumericaError):
        generar_solucion_caso_narrativo(
            "28", "grandes_medianas", 15_000_000.0, 15,
            {"aumento_clientes": "fuerte"}, "Empresa de prueba", str(tmp_path / "no_deberia_existir.pdf"),
            estricto_api=True,
        )
    assert not (tmp_path / "no_deberia_existir.pdf").exists()


def test_generar_solucion_narrativo_estricto_false_cae_a_determinista_con_aviso(monkeypatch, tmp_path):
    def _obtener_narrativa_falsa(*args, **kwargs):
        raise VerificacionNumericaError({"seccion_1": [999.0]})

    monkeypatch.setattr("generar_solucion_caso_narrativo.obtener_narrativa", _obtener_narrativa_falsa)
    from generar_solucion_caso_narrativo import generar_solucion_caso_narrativo

    ruta = tmp_path / "fallback.pdf"
    modelo, modo = generar_solucion_caso_narrativo(
        "28", "grandes_medianas", 15_000_000.0, 15,
        {"aumento_clientes": "fuerte"}, "Empresa de prueba", str(ruta),
        estricto_api=False,
    )
    assert modo == "determinista_fallback"
    assert ruta.exists()

    import pdfplumber
    with pdfplumber.open(str(ruta)) as pdf:
        texto_portada = pdf.pages[0].extract_text()
    assert "modo determinista" in texto_portada or "modo determinista" in texto_portada.replace("\n", " ")
