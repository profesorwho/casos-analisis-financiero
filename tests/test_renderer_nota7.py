"""Tests de la Nota 7 (Pasivos financieros) reescrita del renderizador de PDF (encargo #112.4) —
comprueban las tablas RENDERIZADAS (extraídas del PDF con pdfplumber, no el dato crudo del motor)
contra el Balance y el EFE del mismo caso, y que el PDF se genera sin excepción en ambos modelos.

Las tablas de la Nota 7 no llevan líneas de cuadrícula completas (solo un filete bajo la cabecera
y otro sobre el total, igual que el resto de tablas del renderizador) — la detección de tablas
"por líneas" de pdfplumber no las encuentra, así que se extrae el TEXTO de la página y se parsean
las filas por posición (categoría conocida seguida de N números), no por estructura de tabla."""
from __future__ import annotations

import re

import pdfplumber
import pytest

from motor.arquetipos import cargar_arquetipos
from motor.calendario_deuda import calcular_calendario_deuda
from motor.catalogo import cargar_y_validar_catalogo
from motor.efe import generar_efe
from motor.memoria import generar_caso_combinado
from renderer.generar_caso_completo import generar_caso_completo

MARGEN_PT = 36.9

CATEGORIAS_VENCIMIENTOS = [
    ("Deudas con entidades de crédito", "entidades_credito"),
    ("Obligaciones y otros valores negociables", "obligaciones"),
    ("Acreedores por arrendamiento financiero", "arrendamiento_financiero"),
    ("Otros pasivos financieros", "otros_pasivos_financieros"),
    ("Derivados", "derivados"),
    ("Acreedores por adquisición de inmovilizado", "acreedores_inmovilizado"),
    ("Fianzas, depósitos y deudas con socios", "fianzas_deudas_socios"),
    ("Otras deudas (remanente)", "remanente_otras_deudas"),
    ("Acreedores comerciales y otras cuentas a pagar", "acreedores_comerciales"),
]

CATEGORIAS_MOVIMIENTO = [
    ("Deudas con entidades de crédito", "entidades_credito"),
    ("Obligaciones y otros valores negociables", "obligaciones"),
    ("Acreedores por arrendamiento financiero", "arrendamiento_financiero"),
    ("Otros pasivos financieros", "otros_pasivos_financieros"),
    ("Derivados", "derivados"),
]

NUM_RE = re.compile(r"\(?[\d.]+\)?")


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _parse_eur(celda: str) -> float:
    s = celda.strip()
    negativo = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(".", "")
    if s == "":
        return 0.0
    valor = float(s)
    return -valor if negativo else valor


def _generar_pdf(tmp_path, sector, segmento, ventas, semilla, combo, nombre):
    ruta = tmp_path / f"{nombre}.pdf"
    generar_caso_completo(sector, segmento, ventas, semilla, combo, nombre, str(ruta))
    return ruta


def _texto_completo(ruta) -> str:
    with pdfplumber.open(str(ruta)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def _seccion_nota_7(texto: str) -> str:
    inicio = texto.index("7. Pasivos financieros")
    fin = texto.index("8. Fondos propios", inicio)
    return texto[inicio:fin]


def _segmentos_por_ejercicio(seccion: str, n_segmentos: int) -> list[str]:
    marcas = [m.start() for m in re.finditer(r"Ejercicio \d{4}", seccion)]
    assert len(marcas) == n_segmentos, marcas
    limites = marcas + [len(seccion)]
    return [seccion[limites[i]:limites[i + 1]] for i in range(n_segmentos)]


def _extraer_filas(segmento: str, categorias: list[tuple[str, str]], n_valores: int) -> dict[str, list[float]]:
    texto = re.sub(r"\s+", " ", segmento.replace("\n", " ")).strip()
    resultados: dict[str, list[float]] = {}
    pos = 0
    for etiqueta, clave in categorias:
        idx = texto.index(etiqueta, pos)
        resto = texto[idx + len(etiqueta):]
        numeros: list[str] = []
        fin_relativo = 0
        for m in NUM_RE.finditer(resto):
            numeros.append(m.group())
            fin_relativo = m.end()
            if len(numeros) == n_valores:
                break
        assert len(numeros) == n_valores, (etiqueta, numeros)
        resultados[clave] = [_parse_eur(n) for n in numeros]
        pos = idx + len(etiqueta) + fin_relativo
    # fila "Total", inmediatamente después de la última categoría
    idx_total = texto.index("Total", pos)
    resto = texto[idx_total + len("Total"):]
    numeros = []
    for m in NUM_RE.finditer(resto):
        numeros.append(m.group())
        if len(numeros) == n_valores:
            break
    resultados["__total__"] = [_parse_eur(n) for n in numeros]
    return resultados


def test_pdf_normal_y_abreviado_generan_sin_excepcion(tmp_path, catalogo, arquetipos):
    ruta_normal = _generar_pdf(
        tmp_path, "28", "grandes_medianas", 15_000_000.0, 15,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "normal",
    )
    ruta_abreviado = _generar_pdf(
        tmp_path, "28", "pequeñas", 5_000_000.0, 15,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "abreviado",
    )
    assert ruta_normal.exists()
    assert ruta_abreviado.exists()


def test_totales_de_la_tabla_de_vencimientos_cuadran_con_el_balance(tmp_path, catalogo, arquetipos):
    sector, segmento, ventas, semilla = "28", "grandes_medianas", 15_000_000.0, 15
    combo = {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}
    ruta = _generar_pdf(tmp_path, sector, segmento, ventas, semilla, combo, "normal_venc")
    evolucion = generar_caso_combinado(sector, segmento, ventas, semilla, combo, catalogo=catalogo, arquetipos=arquetipos)
    calendario = calcular_calendario_deuda(evolucion)

    seccion = _seccion_nota_7(_texto_completo(ruta))
    segmentos = _segmentos_por_ejercicio(seccion.split("Movimiento de la deuda financiera")[0], 3)

    for segmento_texto, año in zip(segmentos, (2023, 2024, 2025)):
        filas = _extraer_filas(segmento_texto, CATEGORIAS_VENCIMIENTOS, 7)
        total_esperado = [0.0] * 7
        for _, clave in CATEGORIAS_VENCIMIENTOS:
            t = calendario.vencimientos_por_año[año][clave]
            esperados = [t.un_año, t.dos, t.tres, t.cuatro, t.cinco, t.mas_de_cinco, t.total]
            for i, (renderizado, esperado) in enumerate(zip(filas[clave], esperados)):
                assert renderizado == pytest.approx(esperado, abs=1.0), (año, clave, i)
                total_esperado[i] += esperado
        for renderizado, esperado in zip(filas["__total__"], total_esperado):
            assert renderizado == pytest.approx(esperado, abs=1.0), año


def test_total_de_la_tabla_de_vencimientos_coincide_con_las_partidas_del_balance(tmp_path, catalogo, arquetipos):
    sector, segmento, ventas, semilla = "28", "grandes_medianas", 15_000_000.0, 15
    combo = {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}
    ruta = _generar_pdf(tmp_path, sector, segmento, ventas, semilla, combo, "normal_balance")
    evolucion = generar_caso_combinado(sector, segmento, ventas, semilla, combo, catalogo=catalogo, arquetipos=arquetipos)

    seccion = _seccion_nota_7(_texto_completo(ruta))
    segmentos = _segmentos_por_ejercicio(seccion.split("Movimiento de la deuda financiera")[0], 3)

    for segmento_texto, año in zip(segmentos, (2023, 2024, 2025)):
        filas = _extraer_filas(segmento_texto, CATEGORIAS_VENCIMIENTOS, 7)
        total_renderizado = filas["__total__"][-1]
        ej = evolucion.ejercicios[año]
        total_esperado = (
            sum(ej.deudas_fin_largo_desglose_eur.values()) + sum(ej.deudas_fin_corto_desglose_eur.values())
            + sum(ej.otras_deudas_largo_desglose_eur.values()) + sum(ej.otras_deudas_corto_desglose_eur.values())
            + ej.balance_eur["acreedores_comerciales"]
        )
        assert total_renderizado == pytest.approx(total_esperado, abs=1.0), año


def test_movimiento_de_la_deuda_cuadra_con_el_efe(tmp_path, catalogo, arquetipos):
    sector, segmento, ventas, semilla = "28", "grandes_medianas", 15_000_000.0, 15
    combo = {"riesgo_refinanciacion": "fuerte"}
    ruta = _generar_pdf(tmp_path, sector, segmento, ventas, semilla, combo, "normal_mov")
    evolucion = generar_caso_combinado(sector, segmento, ventas, semilla, combo, catalogo=catalogo, arquetipos=arquetipos)

    seccion = _seccion_nota_7(_texto_completo(ruta))
    seccion_movimiento = seccion.split("Movimiento de la deuda financiera")[1]
    seccion_movimiento = seccion_movimiento.split("El calendario de vencimientos")[0]
    segmentos = _segmentos_por_ejercicio(seccion_movimiento, 2)

    for segmento_texto, año in zip(segmentos, (2024, 2025)):
        filas = _extraer_filas(segmento_texto, CATEGORIAS_MOVIMIENTO, 4)
        saldo_inicial, amortizaciones, disposiciones, saldo_final = filas["__total__"]
        efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
        assert (disposiciones - amortizaciones) == pytest.approx(efe.c10_variacion_neta_deuda_financiera, abs=1.0), año
        assert saldo_final == pytest.approx(saldo_inicial - amortizaciones + disposiciones, abs=1.0)


def test_nota_7_no_desborda_el_margen(tmp_path, catalogo, arquetipos):
    casos = [
        ("28", "grandes_medianas", 15_000_000.0, 15, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "n1"),
        ("28", "pequeñas", 5_000_000.0, 15, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, "n2"),
        ("28", "grandes_medianas", 15_000_000.0, 15, {"riesgo_refinanciacion": "fuerte"}, "n3"),
    ]
    for sector, segmento, ventas, semilla, combo, nombre in casos:
        ruta = _generar_pdf(tmp_path, sector, segmento, ventas, semilla, combo, nombre)
        with pdfplumber.open(str(ruta)) as pdf:
            for page in pdf.pages:
                palabras = page.extract_words()
                if not palabras:
                    continue
                min_x0 = min(w["x0"] for w in palabras)
                max_x1 = max(w["x1"] for w in palabras)
                assert min_x0 >= MARGEN_PT - 1.0, (nombre, page.page_number, min_x0)
                assert max_x1 <= page.width - MARGEN_PT + 1.0, (nombre, page.page_number, max_x1)
