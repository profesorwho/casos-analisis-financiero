"""Tests del documento de solución del caso (encargo #113, `renderer/mapeo_solucion.py` +
`renderer/generar_solucion_caso.py` + `renderer/catalogo_narrativo_arquetipos.py`).

Cubre lo pedido explícitamente: `evolucion.plausibilidad` nunca `None` en la ruta normal;
identidad DuPont exacta (protocolo de parada del encargo, resuelto — ver decisiones_
plausibilidad.md #113); PMM (económico/financiero, incluido que puede ser negativo);
`parsear_arquetipos_activos` para caso único y combinado; catálogo narrativo completo (21
arquetipos, no 20 — discrepancia del propio encargo); resumen ejecutivo nombra exactamente los
arquetipos inyectados.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "renderer"))

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.memoria import generar_caso_combinado

from catalogo_narrativo_arquetipos import CATALOGO_NARRATIVO_ARQUETIPOS
from mapeo_solucion import (
    ARQUETIPO_RATIOS_RELACIONADOS,
    calcular_apalancamiento_financiero,
    calcular_pmm,
    calcular_rf_dupont,
    parsear_arquetipos_activos,
)

VENTAS_POR_SEGMENTO = {"pequeñas": 5_000_000.0, "grandes_medianas": 15_000_000.0}


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _sectores(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


def _generar(catalogo, arquetipos, sector, segmento, semilla, combo):
    return generar_caso_combinado(
        sector, segmento, VENTAS_POR_SEGMENTO[segmento], semilla, combo, catalogo=catalogo, arquetipos=arquetipos,
    )


# --- Catálogo narrativo completo -------------------------------------------------------------

def test_catalogo_narrativo_cubre_todos_los_arquetipos(arquetipos):
    assert set(CATALOGO_NARRATIVO_ARQUETIPOS.keys()) == set(arquetipos.keys())
    assert len(arquetipos) == 21  # 1-22 sin el 13 -- el encargo hablaba de "20", discrepancia declarada
    assert set(ARQUETIPO_RATIOS_RELACIONADOS.keys()) == set(arquetipos.keys())


def test_catalogo_narrativo_no_esta_vacio_para_ningun_arquetipo():
    for arquetipo_id, texto in CATALOGO_NARRATIVO_ARQUETIPOS.items():
        assert len(texto) > 50, arquetipo_id


# --- evolucion.plausibilidad nunca None en la ruta normal (protocolo de parada) --------------

def test_plausibilidad_nunca_es_none_en_ruta_normal(catalogo, arquetipos):
    casos = [
        ("28", "grandes_medianas", {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}),
        ("28", "pequeñas", {"exceso_stock": "fuerte"}),
        ("19", "grandes_medianas", {"coberturas": "fuerte"}),
    ]
    for sector, segmento, combo in casos:
        evolucion = _generar(catalogo, arquetipos, sector, segmento, 15, combo)
        assert evolucion.plausibilidad is not None, (sector, segmento, combo)
        for año in (2023, 2024, 2025):
            assert evolucion.plausibilidad.valores_por_año[año] is not None


# --- Identidad DuPont (protocolo de parada resuelto — ver decisiones_plausibilidad.md #113) ---

def test_identidad_dupont_sobre_barrido(catalogo, arquetipos):
    sectores = ["24.1", "47.1", "19", "68", "69.2", "30.3"]
    segmentos = ["pequeñas", "grandes_medianas"]
    semillas = [3, 15, 23]
    combos = [
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        {"capex_elevado": "fuerte"},
        {"coberturas": "fuerte"},
        {"riesgo_refinanciacion": "fuerte"},
    ]
    comprobados = 0
    for sector in sectores:
        for segmento in segmentos:
            for semilla in semillas:
                for combo in combos:
                    evolucion = _generar(catalogo, arquetipos, sector, segmento, semilla, combo)
                    for año in (2023, 2024, 2025):
                        valores = evolucion.plausibilidad.valores_por_año[año]
                        ej = evolucion.ejercicios[año]
                        if not ej.balance_eur["patrimonio_neto"]:
                            continue
                        roi = valores.get("ratios.roi")
                        roe = valores.get("ratios.roe")
                        if roi is None or roe is None:
                            continue
                        rf = calcular_rf_dupont(roi, ej.balance_eur, ej.pyg_eur)
                        assert rf == pytest.approx(roe, abs=1e-6), (sector, segmento, semilla, combo, año)
                        comprobados += 1
    assert comprobados > 300


def test_identidad_dupont_falla_si_se_usa_la_formula_original_del_encargo(catalogo, arquetipos):
    """Documenta, con un contraejemplo reproducible, que la fórmula LITERAL del encargo original
    (RF = RE + (RE - coste_deuda) x Pasivo_total/PN) NO es una identidad — motivo del protocolo
    de parada resuelto en decisiones_plausibilidad.md #113."""
    evolucion = _generar(catalogo, arquetipos, "24.1", "grandes_medianas", 5, {"capex_elevado": "fuerte"})
    valores = evolucion.plausibilidad.valores_por_año[2025]
    ej = evolucion.ejercicios[2025]
    re_, kd, roe = valores["ratios.roi"], valores["ratios.coste_deuda"], valores["ratios.roe"]
    assert kd is not None
    apalancamiento = calcular_apalancamiento_financiero(ej.balance_eur)
    rf_formula_original = re_ + (re_ - kd) * apalancamiento
    assert rf_formula_original != pytest.approx(roe, abs=1e-6)


# --- PMM ---------------------------------------------------------------------------------------

def test_pmm_formula_basica():
    valores = {"ratios.plazo_existencias": 40.0, "ratios.cobro_dias": 60.0, "ratios.pago_dias": 30.0}
    economico, financiero = calcular_pmm(valores)
    assert economico == pytest.approx(100.0)
    assert financiero == pytest.approx(70.0)


def test_pmm_financiero_puede_ser_negativo():
    valores = {"ratios.plazo_existencias": 10.0, "ratios.cobro_dias": 20.0, "ratios.pago_dias": 90.0}
    economico, financiero = calcular_pmm(valores)
    assert economico == pytest.approx(30.0)
    assert financiero == pytest.approx(-60.0)


def test_pmm_none_si_falta_un_componente():
    assert calcular_pmm({"ratios.plazo_existencias": None, "ratios.cobro_dias": 10.0, "ratios.pago_dias": 5.0}) == (None, None)
    economico, financiero = calcular_pmm({"ratios.plazo_existencias": 10.0, "ratios.cobro_dias": 10.0, "ratios.pago_dias": None})
    assert economico == pytest.approx(20.0)
    assert financiero is None


def test_pmm_financiero_negativo_en_barrido_real(catalogo, arquetipos):
    """Confirma que el PMM financiero negativo no es un caso de laboratorio: se observa en un
    barrido real, justificando por qué la documentación de la sección 3 lo trata como legítimo."""
    n_negativos = 0
    n_total = 0
    for sector in _sectores(catalogo):
        for semilla in (3, 7, 11):
            evolucion = _generar(catalogo, arquetipos, sector, "grandes_medianas", semilla, {"aumento_clientes": "leve"})
            for año in (2023, 2024, 2025):
                _, financiero = calcular_pmm(evolucion.plausibilidad.valores_por_año[año])
                if financiero is not None:
                    n_total += 1
                    if financiero < 0:
                        n_negativos += 1
    assert n_total > 0
    assert n_negativos > 0


# --- parsear_arquetipos_activos ----------------------------------------------------------------

def test_parsear_arquetipos_activos_caso_unico(catalogo, arquetipos):
    evolucion = _generar(catalogo, arquetipos, "28", "grandes_medianas", 15, {"aumento_clientes": "fuerte"})
    assert parsear_arquetipos_activos(evolucion) == [("aumento_clientes", "fuerte")]


def test_parsear_arquetipos_activos_combinado(catalogo, arquetipos):
    evolucion = _generar(
        catalogo, arquetipos, "28", "grandes_medianas", 15,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "leve"},
    )
    pares = dict(parsear_arquetipos_activos(evolucion))
    assert pares == {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "leve"}


# --- Resumen ejecutivo nombra exactamente los arquetipos inyectados --------------------------

def test_resumen_ejecutivo_nombra_exactamente_los_arquetipos_inyectados(catalogo, arquetipos):
    casos = [
        ("24.1", {"exceso_stock": "fuerte"}),
        ("47.1", {"capex_elevado": "moderado"}),
        ("68", {"aumento_clientes": "leve", "riesgo_refinanciacion": "fuerte"}),
    ]
    for sector, combo in casos:
        evolucion = _generar(catalogo, arquetipos, sector, "grandes_medianas", 11, combo)
        activos = parsear_arquetipos_activos(evolucion)
        assert set(aid for aid, _ in activos) == set(combo.keys())
        assert dict(activos) == combo
