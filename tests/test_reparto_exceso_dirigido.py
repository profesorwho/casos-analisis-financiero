"""Tests del encargo de reparto de sub-partidas (decisiones_plausibilidad.md #99): Parte A (el
exceso de un arquetipo va a la sub-partida objetivo, no repartido con el % fijo) y Parte B (5
cuentas de movimiento casi nulo con dinámica propia)."""

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import (
    EXISTENCIAS_OBJETIVO_EXCESO_STOCK,
    FRACCION_AMORTIZACION_ANUAL_DESEMBOLSOS_EXIGIDOS,
    PLAZO_REMANENTE_ARRENDAMIENTO_AÑOS,
    _pesos_exceso_stock,
    _reparto_organico_con_exceso_dirigido,
    generar_evolucion_arquetipo,
)

VENTAS = 8_000_000.0
PERFIL = {"a": 0.5, "b": 0.3, "c": 0.2}


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _evo(catalogo, arquetipos, sector, arquetipo_id, intensidad="fuerte", semilla=1, segmento="pequeñas"):
    return generar_evolucion_arquetipo(
        sector, segmento, VENTAS, semilla=semilla, intensidad=intensidad, arquetipo_id=arquetipo_id,
        catalogo=catalogo, arquetipos=arquetipos,
    )


# --- Parte A: helper puro ---------------------------------------------------------------


def test_exceso_va_al_100_a_la_subpartida_objetivo():
    r = _reparto_organico_con_exceso_dirigido(PERFIL, 1000.0, 200.0, "c")
    assert r["a"] == pytest.approx(500.0) and r["b"] == pytest.approx(300.0) and r["c"] == pytest.approx(400.0)
    assert sum(r.values()) == pytest.approx(1200.0)


def test_sin_objetivo_el_exceso_se_reparte_con_el_perfil_fijo():
    r = _reparto_organico_con_exceso_dirigido(PERFIL, 1000.0, 200.0, None)
    assert r == pytest.approx({"a": 600.0, "b": 360.0, "c": 240.0})


def test_objetivo_repartido_entre_varias_por_peso():
    r = _reparto_organico_con_exceso_dirigido(PERFIL, 1000.0, 100.0, {"a": 0.25, "b": 0.75})
    assert r["a"] == pytest.approx(525.0) and r["b"] == pytest.approx(375.0) and r["c"] == pytest.approx(200.0)


def test_techo_defensivo_exceso_negativo_que_dejaria_el_objetivo_en_negativo_cae_a_proporcional():
    r = _reparto_organico_con_exceso_dirigido(PERFIL, 1000.0, -300.0, "c")  # forzar dejaría c = 200-300 < 0
    assert all(v >= 0 for v in r.values())
    assert sum(r.values()) == pytest.approx(700.0)
    assert r["c"] == pytest.approx(0.2 * 700.0)


def test_exceso_stock_incluye_materias_primas_con_pesos_del_perfil_del_caso():
    assert "materias_primas" in EXISTENCIAS_OBJETIVO_EXCESO_STOCK
    perfil = {
        "comerciales": 0.2, "materias_primas": 0.4, "productos_curso": 0.1, "productos_terminados": 0.1,
        "subproductos_residuos": 0.1, "anticipos_proveedores": 0.1,
    }
    pesos = _pesos_exceso_stock(perfil)
    assert set(pesos) == set(EXISTENCIAS_OBJETIVO_EXCESO_STOCK)
    assert sum(pesos.values()) == pytest.approx(1.0)
    assert pesos["materias_primas"] == pytest.approx(0.4 / 0.8)


# --- Parte A: extremo a extremo -----------------------------------------------------------


@pytest.mark.parametrize("arquetipo_id", ["aumento_clientes", "deterioro_ciclo_caja"])
def test_exceso_de_realizable_va_a_clientes(catalogo, arquetipos, arquetipo_id):
    evo = _evo(catalogo, arquetipos, "24.1", arquetipo_id)
    ej, base = evo.ejercicios[2025], evo.ejercicios[2023]
    otros_2025 = sum(v for k, v in ej.deudores_desglose_eur.items() if k != "clientes")
    otros_2023 = sum(v for k, v in base.deudores_desglose_eur.items() if k != "clientes")
    crec_clientes = ej.deudores_desglose_eur["clientes"] / base.deudores_desglose_eur["clientes"]
    crec_otros = otros_2025 / otros_2023
    # las demás sub-partidas no absorben el exceso: crecen mucho menos que "clientes"
    assert crec_clientes > crec_otros


def test_exceso_stock_en_sanidad_consumibles_deja_materias_primas_por_encima_de_comerciales(catalogo, arquetipos):
    """Regresión del hallazgo que paraba #99: con 3 partidas objetivo (sin materias_primas),
    `comerciales` absorbía ~80 % del exceso en 86.1 y superaba a `materias_primas`."""
    for semilla in range(4):
        ej = _evo(catalogo, arquetipos, "86.1", "exceso_stock", semilla=semilla).ejercicios[2025]
        d = ej.existencias_desglose_eur
        assert d["materias_primas"] > d["comerciales"], f"semilla {semilla}: {d}"


def test_apalancamiento_va_a_entidades_de_credito(catalogo, arquetipos):
    base = _evo(catalogo, arquetipos, "24.1", "apalancamiento", intensidad="leve").ejercicios[2025]
    fuerte = _evo(catalogo, arquetipos, "24.1", "apalancamiento", intensidad="fuerte").ejercicios[2025]
    d_total = fuerte.balance_eur["deudas_fin_largo"] - base.balance_eur["deudas_fin_largo"]
    d_ent = (
        fuerte.deudas_fin_largo_desglose_eur["entidades_credito"]
        - base.deudas_fin_largo_desglose_eur["entidades_credito"]
    )
    assert d_total > 0 and d_ent / d_total > 0.85


# --- Parte B: 5 cuentas de movimiento casi nulo ---------------------------------------------


def test_accionistas_desembolsos_exigidos_decrece_hacia_cero(catalogo, arquetipos):
    evo = _evo(catalogo, arquetipos, "24.1", "aumento_clientes")
    v = [evo.ejercicios[a].deudores_desglose_eur["accionistas_desembolsos_exigidos"] for a in (2023, 2024, 2025)]
    f = 1 - FRACCION_AMORTIZACION_ANUAL_DESEMBOLSOS_EXIGIDOS
    assert v[0] > 0
    assert v[1] == pytest.approx(v[0] * f) and v[2] == pytest.approx(v[1] * f)


def test_arrendamiento_financiero_amortiza_lineal_y_obligaciones_es_plana(catalogo, arquetipos):
    evo = _evo(catalogo, arquetipos, "29", "aumento_clientes")

    def total(ej, clave):
        return ej.deudas_fin_largo_desglose_eur[clave] + ej.deudas_fin_corto_desglose_eur[clave]

    arr = [total(evo.ejercicios[a], "arrendamiento_financiero") for a in (2023, 2024, 2025)]
    obl = [total(evo.ejercicios[a], "obligaciones") for a in (2023, 2024, 2025)]
    assert arr[0] > 0
    assert arr[1] == pytest.approx(arr[0] * (1 - 1 / PLAZO_REMANENTE_ARRENDAMIENTO_AÑOS))
    assert arr[2] == pytest.approx(arr[0] * (1 - 2 / PLAZO_REMANENTE_ARRENDAMIENTO_AÑOS))
    assert obl[1] == pytest.approx(obl[0]) and obl[2] == pytest.approx(obl[0])


def test_tres_cuentas_identicas_con_cualquier_arquetipo_sin_efecto_en_ventas(catalogo, arquetipos):
    """Accionistas/obligaciones/arrendamiento no dependen del arquetipo activo."""

    def cuentas(ej):
        return (
            ej.deudores_desglose_eur["accionistas_desembolsos_exigidos"],
            ej.deudas_fin_largo_desglose_eur["obligaciones"] + ej.deudas_fin_corto_desglose_eur["obligaciones"],
            ej.deudas_fin_largo_desglose_eur["arrendamiento_financiero"]
            + ej.deudas_fin_corto_desglose_eur["arrendamiento_financiero"],
        )

    ref = _evo(catalogo, arquetipos, "24.1", "aumento_clientes")
    for aid in ("exceso_stock", "apalancamiento", "deterioro_ciclo_caja", "refinanciacion", "capex_elevado"):
        otro = _evo(catalogo, arquetipos, "24.1", aid)
        for a in (2024, 2025):
            assert cuentas(otro.ejercicios[a]) == pytest.approx(cuentas(ref.ejercicios[a])), (aid, a)


def test_personal_acreedor_sigue_el_crecimiento_de_gastos_de_personal(catalogo, arquetipos):
    for aid in ("aumento_clientes", "crecimiento_destruccion_caja"):
        evo = _evo(catalogo, arquetipos, "24.1", aid)
        p = [evo.ejercicios[a].acreedores_desglose_eur["personal"] for a in (2023, 2024, 2025)]
        g = [evo.ejercicios[a].pyg_eur["gastos_personal"] for a in (2023, 2024, 2025)]
        assert p[1] / p[0] == pytest.approx(g[1] / g[0]) and p[2] / p[1] == pytest.approx(g[2] / g[1])
