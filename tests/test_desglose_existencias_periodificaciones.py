"""Tests del primer lote de desglose de balance según el mapeo oficial del PGC: existencias (6
sub-partidas oficiales) y periodificaciones (activo a corto, pasivo a corto y largo). Mismo
patrón que `activo_no_corriente` (ver test_desagregacion_pn_y_activo.py): perfil por sector,
ruido mixto, desglose expuesto internamente sin alterar la masa agregada del balance.

La clasificación de existencias es por TIER (`TIER_EXISTENCIAS_POR_SECTOR`), no por
`categoria_de_sector` — verificado contra el dato real de `balance.existencias_pct` del
catálogo que varios sectores de una misma categoría de `activo_no_corriente` tienen un carácter
de existencias radicalmente distinto (ver decisiones_plausibilidad.md #52-53). Periodificaciones
sí reutilizan las 9 categorías de siempre (no había ninguna señal en el dato real que pidiera lo
contrario).
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import (
    CATEGORIA_SECTOR,
    PERFIL_EXISTENCIAS_POR_TIER,
    PERIODIFICACION_ACTIVO_PCT_POR_CATEGORIA,
    PERIODIFICACION_PASIVO_PCT_POR_CATEGORIA,
    SUELO_PERIODIFICACION_PCT,
    TECHO_PERIODIFICACION_PCT,
    TIER_EXISTENCIAS_POR_SECTOR,
    categoria_de_sector,
    generar_empresa_base,
    tier_existencias_de_sector,
)
from motor.evolucion_arquetipo import generar_evolucion_arquetipo

VENTAS_OBJETIVO_2023 = 15_000_000.0


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _sectores(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


def test_existencias_desglose_suma_100_por_ciento_en_empresa_base(catalogo):
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            assert sum(empresa.existencias_perfil_pct.values()) == pytest.approx(1.0, abs=1e-9)
            assert sum(empresa.existencias_desglose_eur.values()) == pytest.approx(
                empresa.balance_eur["existencias"], abs=0.01
            )
            for valor in empresa.existencias_perfil_pct.values():
                assert valor >= 0


def test_existencias_desglose_suma_100_por_ciento_en_evolucion_con_exceso_stock(catalogo, arquetipos):
    """El arquetipo 5 (exceso de stock) mueve `existencias` — el desglose debe seguir sumando
    exactamente el total, en los 3 años, y el perfil (%) debe mantenerse constante desde 2023
    (el exceso se reparte automáticamente según ese perfil fijo, sin código especial)."""
    for codigo in ("24.1", "47.1", "62"):
        for semilla in range(3):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
            )
            perfil_2023 = evolucion.ejercicios[2023].existencias_perfil_pct
            for año, ejercicio in evolucion.ejercicios.items():
                assert ejercicio.existencias_perfil_pct == perfil_2023
                assert sum(ejercicio.existencias_desglose_eur.values()) == pytest.approx(
                    ejercicio.balance_eur["existencias"], abs=0.01
                )


def test_existencias_sin_combinaciones_ilogicas(catalogo, arquetipos):
    """Verificación cuantificada pedida explícitamente — no genérica ("el componente dominante
    nunca cambia": varias categorías tienen 2-3 componentes deliberadamente próximos, p. ej.
    industria 28%/27%/30% entre materias primas/curso/terminados, donde SÍ es esperable que el
    ruido altere cuál queda primero sin que eso sea ilógico), sino específica sobre las parejas
    donde SÍ hay una relación de negocio clara que nunca debería invertirse — una por cada uno
    de los 8 tiers de existencias."""
    for codigo in _sectores(catalogo):
        tier = tier_existencias_de_sector(codigo)
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
            )
            for año, ejercicio in evolucion.ejercicios.items():
                d = ejercicio.existencias_desglose_eur
                ctx = f"{codigo} tier={tier} semilla={semilla} año={año}"
                if tier == "comercio_hosteleria":
                    assert d["comerciales"] > d["productos_curso"], ctx
                    assert d["comerciales"] > d["productos_terminados"], ctx
                    assert d["comerciales"] > d["materias_primas"], ctx
                if tier == "construccion":
                    assert d["productos_curso"] > d["comerciales"], ctx
                    assert d["productos_curso"] > d["subproductos_residuos"], ctx
                if tier == "industria":
                    assert d["comerciales"] < max(d["materias_primas"], d["productos_curso"], d["productos_terminados"]), ctx
                if tier == "producto_en_curso":
                    # Trabajos en curso no facturados: la partida dominante con claridad, muy
                    # por encima de cualquier otra (perfil centro 0,85 vs. el resto <=0,08).
                    otras = sum(v for k, v in d.items() if k != "productos_curso")
                    assert d["productos_curso"] > otras, ctx
                if tier == "inmobiliario_mixto":
                    assert (d["productos_curso"] + d["productos_terminados"]) > d["comerciales"], ctx
                    assert d["productos_curso"] > d["comerciales"], ctx
                if tier == "sanidad_consumibles":
                    assert d["materias_primas"] > d["comerciales"], ctx
                    assert d["materias_primas"] > d["productos_terminados"], ctx
                if tier == "cero_total" and año == 2023:
                    # Sin pretensión de significado de negocio (reparto neutro) — la única
                    # invariante real es que el TOTAL sigue siendo marginal frente al balance,
                    # comprobado en el año BASE (2023): "exceso_stock" es un arquetipo que
                    # infla existencias deliberadamente en 2024/2025 para cualquier sector, así
                    # que no tendría sentido pedirle "marginal" bajo su propio efecto de estrés.
                    activo_total = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
                    assert ejercicio.balance_eur["existencias"] < 0.03 * activo_total, ctx


def test_periodificaciones_dentro_de_rango_razonable_y_son_sub_componente(catalogo):
    """Las periodificaciones son una fracción (no una masa nueva): nunca deben superar su masa
    "madre", y su magnitud debe quedar dentro del rango de diseño (suelo/techo defensivo)."""
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            assert SUELO_PERIODIFICACION_PCT - 1e-6 <= empresa.periodificacion_activo_pct <= TECHO_PERIODIFICACION_PCT + 1e-6
            assert SUELO_PERIODIFICACION_PCT - 1e-6 <= empresa.periodificacion_pasivo_corto_pct <= TECHO_PERIODIFICACION_PCT + 1e-6
            assert SUELO_PERIODIFICACION_PCT - 1e-6 <= empresa.periodificacion_pasivo_largo_pct <= TECHO_PERIODIFICACION_PCT + 1e-6
            assert empresa.periodificacion_activo_eur <= empresa.balance_eur["realizable"] + 1e-6
            assert empresa.periodificacion_pasivo_corto_eur <= empresa.balance_eur["otras_deudas_corto"] + 1e-6
            assert empresa.periodificacion_pasivo_largo_eur <= empresa.balance_eur["otras_deudas_largo"] + 1e-6


def test_periodificaciones_perfil_constante_y_eur_recalculado_en_evolucion(catalogo, arquetipos):
    """Mismo patrón que capital_social/activo_no_corriente: el % es un rasgo fijo del caso desde
    2023, el importe en euros se recalcula cada año sobre la masa (ya cuadrada) de ese año."""
    for arquetipo_id in ("apalancamiento", "capex_elevado", "exceso_stock"):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=2, intensidad="fuerte",
            arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
        )
        pct_2023 = (
            evolucion.ejercicios[2023].periodificacion_activo_pct,
            evolucion.ejercicios[2023].periodificacion_pasivo_corto_pct,
            evolucion.ejercicios[2023].periodificacion_pasivo_largo_pct,
        )
        for año, ejercicio in evolucion.ejercicios.items():
            assert (
                ejercicio.periodificacion_activo_pct,
                ejercicio.periodificacion_pasivo_corto_pct,
                ejercicio.periodificacion_pasivo_largo_pct,
            ) == pct_2023
            assert ejercicio.periodificacion_activo_eur == pytest.approx(
                ejercicio.periodificacion_activo_pct * ejercicio.balance_eur["realizable"], abs=0.01
            )
            assert ejercicio.periodificacion_pasivo_corto_eur == pytest.approx(
                ejercicio.periodificacion_pasivo_corto_pct * ejercicio.balance_eur["otras_deudas_corto"], abs=0.01
            )
            assert ejercicio.periodificacion_pasivo_largo_eur == pytest.approx(
                ejercicio.periodificacion_pasivo_largo_pct * ejercicio.balance_eur["otras_deudas_largo"], abs=0.01
            )


def test_todos_los_27_sectores_tienen_tier_de_existencias_y_categoria_de_periodificacion(catalogo):
    for codigo in _sectores(catalogo):
        tier_existencias_de_sector(codigo)  # no debe lanzar
        categoria = categoria_de_sector(codigo)
        assert categoria in PERIODIFICACION_ACTIVO_PCT_POR_CATEGORIA
        assert categoria in PERIODIFICACION_PASIVO_PCT_POR_CATEGORIA


def test_todos_los_tiers_de_existencias_suman_100_por_ciento():
    for perfil in PERFIL_EXISTENCIAS_POR_TIER.values():
        assert sum(perfil.values()) == pytest.approx(1.0, abs=1e-9)


def test_cada_sector_de_categoria_sector_tiene_tier_de_existencias_asignado():
    # TIER_EXISTENCIAS_POR_SECTOR se define por sector, no por categoría — confirma que cubre
    # exactamente los mismos 27 sectores que CATEGORIA_SECTOR, ni de más ni de menos.
    assert set(TIER_EXISTENCIAS_POR_SECTOR) == set(CATEGORIA_SECTOR)
