"""Tests del PDF de solución en modo narrativo (encargo #114). Los que llaman de verdad a la API
de Anthropic se saltan limpiamente si `ANTHROPIC_API_KEY` no está en el entorno — el resto
(construcción del paquete de verdad, ensamblado con tablas simuladas, márgenes de un PDF
generado en modo determinista de respaldo) no necesita clave y corre siempre."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pdfplumber
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "renderer"))

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.efe import generar_efe
from motor.calendario_deuda import calcular_calendario_deuda
from motor.memoria import generar_caso_combinado

from mapeo_solucion_narrativo import construir_paquete_verdad, construir_prompt
from generar_solucion_caso_narrativo import generar_solucion_caso_narrativo

REQUIERE_API_KEY = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY no está definida en el entorno — no se puede llamar a la API real.",
)

MARGEN_PT = 36.9

CASOS_REFERENCIA = [
    ("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "normal"),
    ("28", "pequeñas", 5_000_000.0, 15, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "abreviado"),
    ("19", "grandes_medianas", 15_000_000.0, 15, {"coberturas": "fuerte"}, "coberturas"),
]


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _construir_paquete(catalogo, arquetipos, sector, segmento, ventas, semilla, combo):
    evolucion = generar_caso_combinado(sector, segmento, ventas, semilla, combo, catalogo=catalogo, arquetipos=arquetipos)
    ejercicios = evolucion.ejercicios
    efes = {2024: generar_efe(ejercicios[2023], ejercicios[2024], True), 2025: generar_efe(ejercicios[2024], ejercicios[2025], True)}
    calendario = calcular_calendario_deuda(evolucion)
    return construir_paquete_verdad(evolucion, ejercicios, efes, calendario, arquetipos)


def test_paquete_de_verdad_es_serializable_a_json(catalogo, arquetipos):
    import json

    paquete = _construir_paquete(catalogo, arquetipos, "28", "grandes_medianas", 15_000_000.0, 15,
                                  {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"})
    texto = json.dumps(paquete, ensure_ascii=False)
    assert len(texto) > 100


def test_prompt_incluye_el_catalogo_y_no_incluye_tablas(catalogo, arquetipos):
    paquete = _construir_paquete(catalogo, arquetipos, "28", "grandes_medianas", 15_000_000.0, 15, {"exceso_stock": "fuerte"})
    prompt = construir_prompt(paquete)
    assert "exceso_stock" in prompt
    assert "Rotación de existencias" in prompt or "rotacion_existencias" in prompt
    assert "no las escribes tú" in prompt or "no las reproduzcas" in prompt


def test_prompt_declara_explicitamente_los_arquetipos_sin_efecto_claro(catalogo, arquetipos):
    paquete = _construir_paquete(catalogo, arquetipos, "19", "grandes_medianas", 15_000_000.0, 15, {"coberturas": "fuerte"})
    prompt = construir_prompt(paquete)
    assert "sin efecto claro" in prompt


def test_fallback_determinista_no_desborda_el_margen(tmp_path, catalogo, arquetipos):
    """No requiere API — fuerza el fallback (sin ANTHROPIC_API_KEY en este entorno de test, si
    no está definida) y comprueba el PDF resultante como en encargos anteriores."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("Este test comprueba específicamente el PDF de fallback sin clave de API.")
    ruta = tmp_path / "fallback.pdf"
    modelo, modo = generar_solucion_caso_narrativo(
        "28", "grandes_medianas", 15_000_000.0, 15,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        "Empresa de prueba", str(ruta), estricto_api=False,
    )
    assert modo == "determinista_fallback"
    with pdfplumber.open(str(ruta)) as pdf:
        assert len(pdf.pages) > 1
        for page in pdf.pages:
            palabras = page.extract_words()
            if not palabras:
                continue
            min_x0 = min(w["x0"] for w in palabras)
            max_x1 = max(w["x1"] for w in palabras)
            assert min_x0 >= MARGEN_PT - 1.0, page.page_number
            assert max_x1 <= page.width - MARGEN_PT + 1.0, page.page_number


# --------------------------------------------------------------------------------------------
# Generación REAL con la API — solo si hay ANTHROPIC_API_KEY. Máximo 3 casos (Normal, Abreviado,
# Coberturas), cada uno con hasta MAX_INTENTOS llamadas — acotado, no es un barrido.
# --------------------------------------------------------------------------------------------

@REQUIERE_API_KEY
@pytest.mark.parametrize("sector,segmento,ventas,semilla,combo,nombre", CASOS_REFERENCIA)
def test_generacion_real_de_los_3_casos_de_referencia(tmp_path, sector, segmento, ventas, semilla, combo, nombre):
    ruta = tmp_path / f"{nombre}.pdf"
    modelo, modo = generar_solucion_caso_narrativo(
        sector, segmento, ventas, semilla, combo, f"Referencia {nombre}", str(ruta),
        forzar_regeneracion=True, estricto_api=True,
    )
    assert modo == "narrativo"
    assert ruta.exists()
    with pdfplumber.open(str(ruta)) as pdf:
        for page in pdf.pages:
            palabras = page.extract_words()
            if not palabras:
                continue
            min_x0 = min(w["x0"] for w in palabras)
            max_x1 = max(w["x1"] for w in palabras)
            assert min_x0 >= MARGEN_PT - 1.0, page.page_number
            assert max_x1 <= page.width - MARGEN_PT + 1.0, page.page_number
