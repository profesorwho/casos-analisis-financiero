"""Tests de `motor/similitud_casos.py` — función de comparación entre casos (sección 2.20,
pieza PARCIAL: solo la función, sin aplicarla sobre ningún repositorio todavía, ver docstring del
módulo). Cubre las 4 dimensiones comparadas por separado y la puntuación combinada, con casos
reales generados por el motor (no mocks — coherente con el resto de la suite)."""

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.similitud_casos import SimilitudCasosError, similitud_entre_casos

VENTAS_OBJETIVO_2023 = 15_000_000.0


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _caso(catalogo, arquetipos, sector, arquetipo_id, intensidad, semilla, segmento="grandes_medianas"):
    return generar_evolucion_arquetipo(
        sector, segmento, VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
        arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
    )


def test_un_caso_comparado_consigo_mismo_da_puntuacion_1(catalogo, arquetipos):
    caso = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 1)
    r = similitud_entre_casos(caso, caso, catalogo=catalogo)
    assert r.puntuacion == pytest.approx(1.0)
    assert r.mismo_sector and r.mismo_segmento
    assert r.similitud_arquetipos == pytest.approx(1.0)
    assert r.similitud_intensidad == pytest.approx(1.0)
    assert r.similitud_numerica == pytest.approx(1.0)
    assert r.arquetipos_en_comun == ("apalancamiento",)


def test_mismo_sector_arquetipo_intensidad_distinta_semilla_da_puntuacion_alta_pero_no_1(catalogo, arquetipos):
    a = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 1)
    b = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 7)
    r = similitud_entre_casos(a, b, catalogo=catalogo)
    assert r.similitud_sector_segmento == pytest.approx(1.0)
    assert r.similitud_arquetipos == pytest.approx(1.0)
    assert r.similitud_intensidad == pytest.approx(1.0)
    # Las cifras SÍ difieren entre semillas — no debería salir un perfil numérico idéntico.
    assert r.similitud_numerica < 1.0
    assert 0.4 < r.puntuacion < 1.0


def test_sector_y_arquetipo_distintos_da_puntuacion_baja(catalogo, arquetipos):
    a = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 1)
    b = _caso(catalogo, arquetipos, "62", "mejora_margen", "leve", 1)
    r = similitud_entre_casos(a, b, catalogo=catalogo)
    assert not r.mismo_sector
    assert r.similitud_sector_segmento == pytest.approx(0.0)
    assert r.similitud_arquetipos == pytest.approx(0.0)
    assert r.similitud_intensidad == pytest.approx(0.0)  # sin arquetipos en común, no comparable
    assert r.arquetipos_en_comun == ()
    assert r.puntuacion < 0.3


def test_mismo_sector_distinto_segmento_da_similitud_intermedia(catalogo, arquetipos):
    a = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 1, segmento="grandes_medianas")
    b = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 1, segmento="pequeñas")
    r = similitud_entre_casos(a, b, catalogo=catalogo)
    assert r.mismo_sector and not r.mismo_segmento
    assert r.similitud_sector_segmento == pytest.approx(0.5)


def test_intensidad_mas_lejana_da_menor_similitud_de_intensidad(catalogo, arquetipos):
    base = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "leve", 1)
    moderado = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "moderado", 1)
    fuerte = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 1)
    r_cercano = similitud_entre_casos(base, moderado, catalogo=catalogo)
    r_lejano = similitud_entre_casos(base, fuerte, catalogo=catalogo)
    assert r_cercano.similitud_intensidad > r_lejano.similitud_intensidad
    assert r_lejano.similitud_intensidad == pytest.approx(0.0)  # leve vs fuerte: distancia máxima


def test_similitud_es_simetrica(catalogo, arquetipos):
    a = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 1)
    b = _caso(catalogo, arquetipos, "62", "apalancamiento", "moderado", 3)
    r_ab = similitud_entre_casos(a, b, catalogo=catalogo)
    r_ba = similitud_entre_casos(b, a, catalogo=catalogo)
    assert r_ab.puntuacion == pytest.approx(r_ba.puntuacion)
    assert r_ab.similitud_numerica == pytest.approx(r_ba.similitud_numerica)


def test_puntuacion_esta_acotada_entre_0_y_1(catalogo, arquetipos):
    casos = [
        _caso(catalogo, arquetipos, sector, arquetipo_id, intensidad, semilla)
        for sector, arquetipo_id, intensidad, semilla in [
            ("24.1", "apalancamiento", "fuerte", 1),
            ("62", "mejora_margen", "leve", 2),
            ("47.1", "exceso_stock", "moderado", 3),
        ]
    ]
    for i, a in enumerate(casos):
        for b in casos[i:]:
            r = similitud_entre_casos(a, b, catalogo=catalogo)
            assert 0.0 <= r.puntuacion <= 1.0


def test_caso_sin_plausibilidad_lanza_error(catalogo, arquetipos):
    import dataclasses

    caso = _caso(catalogo, arquetipos, "24.1", "apalancamiento", "fuerte", 1)
    caso_sin_plausibilidad = dataclasses.replace(caso, plausibilidad=None)
    with pytest.raises(SimilitudCasosError):
        similitud_entre_casos(caso_sin_plausibilidad, caso, catalogo=catalogo)


def test_arquetipos_en_comun_con_caso_combinado(catalogo, arquetipos):
    from motor.memoria import generar_caso_combinado

    combinado = generar_caso_combinado(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, 1,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "moderado"},
        catalogo=catalogo, arquetipos=arquetipos,
    )
    solo_aumento_clientes = _caso(catalogo, arquetipos, "24.1", "aumento_clientes", "fuerte", 9)
    r = similitud_entre_casos(combinado, solo_aumento_clientes, catalogo=catalogo)
    assert r.arquetipos_en_comun == ("aumento_clientes",)
    # Jaccard: 1 en común / 2 en la unión (combinado tiene 2, el otro tiene 1, ambos comparten 1).
    assert r.similitud_arquetipos == pytest.approx(1 / 2)
