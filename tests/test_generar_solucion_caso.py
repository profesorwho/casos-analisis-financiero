"""Tests del PDF de solución del caso (encargo #113, `renderer/generar_solucion_caso.py`) —
comprueban que las tablas RENDERIZADAS de ratios cuadran con `evolucion.plausibilidad.
valores_por_año` (no con un recálculo propio), que el PDF se genera sin excepción en modelo
Normal y Abreviado, y que ninguna página desborda el margen."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pdfplumber
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "renderer"))

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.memoria import generar_caso_combinado

from generar_solucion_caso import AVISO_DOCENTE, generar_solucion_caso

MARGEN_PT = 36.9


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _parse_num(celda: str) -> float:
    s = celda.strip().rstrip("%")
    if s in ("n/d", ""):
        return None
    return float(s)


def test_pdf_normal_abreviado_y_coberturas_generan_sin_excepcion(tmp_path, catalogo, arquetipos):
    rutas = []
    for sector, segmento, ventas, semilla, combo, nombre in [
        ("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "normal"),
        ("28", "pequeñas", 5_000_000.0, 15, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "abreviado"),
        ("19", "grandes_medianas", 15_000_000.0, 15, {"coberturas": "fuerte"}, "coberturas"),
    ]:
        ruta = tmp_path / f"{nombre}.pdf"
        generar_solucion_caso(sector, segmento, ventas, semilla, combo, "Empresa de prueba", str(ruta))
        assert ruta.exists()
        rutas.append(ruta)


def test_tabla_de_liquidez_cuadra_con_plausibilidad(tmp_path, catalogo, arquetipos):
    sector, segmento, ventas, semilla = "28", "grandes_medianas", 15_000_000.0, 15
    combo = {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}
    ruta = tmp_path / "normal.pdf"
    generar_solucion_caso(sector, segmento, ventas, semilla, combo, "Empresa de prueba", str(ruta))
    evolucion = generar_caso_combinado(sector, segmento, ventas, semilla, combo, catalogo=catalogo, arquetipos=arquetipos)

    with pdfplumber.open(str(ruta)) as pdf:
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
    inicio = texto.index("3. Análisis financiero a corto plazo")
    fin = texto.index("Período medio de maduración")
    seccion = texto[inicio:fin]

    filas_esperadas = [
        ("Liquidez general", "ratios.liquidez"),
        ("Prueba ácida", "ratios.tesoreria"),
        ("Disponibilidad", "ratios.disponibilidad_ratio"),
    ]
    for etiqueta, ratio in filas_esperadas:
        idx = seccion.index(etiqueta)
        resto = seccion[idx:]
        numeros = re.findall(r"-?\d+\.\d+", resto)[:3]
        for año, num in zip((2023, 2024, 2025), numeros):
            esperado = evolucion.plausibilidad.valores_por_año[año][ratio]
            assert float(num) == pytest.approx(esperado, abs=0.01), (etiqueta, año)


def test_tabla_dupont_coincide_con_roe_en_el_pdf(tmp_path, catalogo, arquetipos):
    sector, segmento, ventas, semilla = "19", "grandes_medianas", 15_000_000.0, 15
    combo = {"coberturas": "fuerte"}
    ruta = tmp_path / "coberturas.pdf"
    generar_solucion_caso(sector, segmento, ventas, semilla, combo, "Empresa de prueba", str(ruta))

    with pdfplumber.open(str(ruta)) as pdf:
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
    inicio = texto.index("6. Análisis de la rentabilidad")
    fin = texto.index("7. Análisis del Estado")
    seccion = texto[inicio:fin]

    idx_roe = seccion.index("Rentabilidad financiera")
    roe_vals = re.findall(r"-?\d+\.\d+%", seccion[idx_roe:])[:3]
    idx_rf = seccion.index("RF calculada")
    rf_vals = re.findall(r"-?\d+\.\d+%", seccion[idx_rf:])[:3]
    assert roe_vals == rf_vals


def test_pie_de_pagina_presente_en_todas_las_paginas(tmp_path, catalogo, arquetipos):
    ruta = tmp_path / "normal.pdf"
    generar_solucion_caso(
        "28", "grandes_medianas", 15_000_000.0, 15,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        "Empresa de prueba", str(ruta),
    )
    with pdfplumber.open(str(ruta)) as pdf:
        assert len(pdf.pages) > 1
        for page in pdf.pages:
            texto = page.extract_text() or ""
            assert AVISO_DOCENTE in texto or AVISO_DOCENTE.replace("é", "e") in texto.replace("é", "e"), page.page_number


def test_no_desborda_el_margen(tmp_path, catalogo, arquetipos):
    casos = [
        ("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "n1"),
        ("28", "pequeñas", 5_000_000.0, 15, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "n2"),
        ("19", "grandes_medianas", 15_000_000.0, 15, {"coberturas": "fuerte"}, "n3"),
    ]
    for sector, segmento, ventas, semilla, combo, nombre in casos:
        ruta = tmp_path / f"{nombre}.pdf"
        generar_solucion_caso(sector, segmento, ventas, semilla, combo, "Empresa de prueba", str(ruta))
        with pdfplumber.open(str(ruta)) as pdf:
            for page in pdf.pages:
                palabras = page.extract_words()
                if not palabras:
                    continue
                min_x0 = min(w["x0"] for w in palabras)
                max_x1 = max(w["x1"] for w in palabras)
                assert min_x0 >= MARGEN_PT - 1.0, (nombre, page.page_number, min_x0)
                assert max_x1 <= page.width - MARGEN_PT + 1.0, (nombre, page.page_number, max_x1)
