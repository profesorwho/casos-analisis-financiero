"""Tests de la desagregación de PN (Capital/Reservas/Resultado) y de `activo_no_corriente`
(material/intangible/inversiones_inmobiliarias/otros_financieros) — sección "Desagregación de
Patrimonio Neto" / "Desagregación de activo_no_corriente" del encargo del EFE/ECPN. Aplica a
CUALQUIER balance que el motor genere (empresa_base y evolucion_arquetipo), no solo al ECPN/EFE.
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import (
    PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA,
    categoria_de_sector,
    generar_empresa_base,
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


def test_todos_los_27_sectores_tienen_categoria(catalogo):
    for codigo in _sectores(catalogo):
        categoria_de_sector(codigo)  # no debe lanzar


def test_capital_y_reservas_reconcilian_con_pn_en_empresa_base(catalogo):
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            suma = empresa.capital_social_eur + empresa.reservas_eur + empresa.pyg_eur["resultado_ejercicio"]
            assert suma == pytest.approx(empresa.balance_eur["patrimonio_neto"], abs=0.01)
            assert empresa.capital_social_eur > 0


def test_activo_no_corriente_desglose_suma_100_por_ciento_en_empresa_base(catalogo):
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            assert sum(empresa.activo_no_corriente_perfil_pct.values()) == pytest.approx(1.0, abs=1e-9)
            assert sum(empresa.activo_no_corriente_desglose_eur.values()) == pytest.approx(
                empresa.balance_eur["activo_no_corriente"], abs=0.01
            )
            for valor in empresa.activo_no_corriente_perfil_pct.values():
                assert valor >= 0


def test_componente_dominante_del_perfil_coincide_con_la_categoria(catalogo):
    """Ninguna fábrica debería salir con más intangible que material, ni ningún sector
    profesional/TIC con más material que intangible — el ruido no debe voltear la identidad de
    la categoría. Verificado sobre 10 semillas por sector."""
    for codigo in _sectores(catalogo):
        categoria = categoria_de_sector(codigo)
        dominante_esperado = max(
            PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA[categoria],
            key=PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA[categoria].get,
        )
        for semilla in range(10):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            dominante_real = max(empresa.activo_no_corriente_perfil_pct, key=empresa.activo_no_corriente_perfil_pct.get)
            assert dominante_real == dominante_esperado, f"{codigo} semilla={semilla}: {empresa.activo_no_corriente_perfil_pct}"


def test_capital_social_constante_y_reservas_reconcilian_en_evolucion(catalogo, arquetipos):
    for arquetipo_id in ("apalancamiento", "adquisicion", "exceso_stock"):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
            arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
        )
        capital_2023 = evolucion.ejercicios[2023].capital_social_eur
        for año, ejercicio in evolucion.ejercicios.items():
            assert ejercicio.capital_social_eur == capital_2023
            suma = ejercicio.capital_social_eur + ejercicio.reservas_eur + ejercicio.pyg_eur["resultado_ejercicio"]
            assert suma == pytest.approx(ejercicio.balance_eur["patrimonio_neto"], abs=0.01)
            # `activo_no_corriente_desglose_eur` es SIEMPRE el desglose del TOTAL de ese año
            # (perfil x balance_eur["activo_no_corriente"] completo, incluido cualquier salto de
            # adquisición ya absorbido) — no hay que sumarle el incremento aparte, esa resta solo
            # se hace en motor/efe.py al calcular el flujo de inversión "orgánico" de la
            # transición entre dos años. Ver docstring de EjercicioEmpresa.
            assert sum(ejercicio.activo_no_corriente_desglose_eur.values()) == pytest.approx(
                ejercicio.balance_eur["activo_no_corriente"], abs=0.01
            )


@pytest.mark.parametrize("codigo", ["69.2", "62", "24.1", "68"])
def test_otros_financieros_no_se_amortiza_y_crece_con_ventas(catalogo, arquetipos, codigo):
    """decisiones #100: `otros_financieros` (inversiones financieras) nunca se amortiza — crece
    solo con su propio crecimiento de ventas (mismo % en 2024 y 2025 bajo un arquetipo de
    crecimiento constante) en vez de encogerse pro-rata con la amortización del agregado, y el
    TOTAL de activo no corriente no cambia (solo la composición): las 4 partes siguen sumándolo."""
    evolucion = generar_evolucion_arquetipo(
        codigo, "pequeñas", 8_000_000.0, semilla=2, intensidad="moderado",
        arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
    )
    of = [evolucion.ejercicios[a].activo_no_corriente_desglose_eur["otros_financieros"] for a in (2023, 2024, 2025)]
    assert of[1] > of[0] and of[2] > of[1], "otros_financieros no debe encogerse (nunca se amortiza)"
    assert of[1] / of[0] == pytest.approx(of[2] / of[1], rel=1e-9)
    for ejercicio in evolucion.ejercicios.values():
        assert sum(ejercicio.activo_no_corriente_desglose_eur.values()) == pytest.approx(
            ejercicio.balance_eur["activo_no_corriente"], abs=0.01
        )


def test_reservas_no_absurdamente_negativas_en_barrido_amplio(catalogo, arquetipos):
    """Comprobación cuantificada pedida explícitamente: negativo es contablemente posible
    (pérdidas acumuladas), pero no debería ser el resultado típico. Umbral de referencia: menos
    del 5% de los ejercicios con reservas negativas en el barrido de arquetipos más agresivos."""
    negativos = 0
    total = 0
    for arquetipo_id in ("apalancamiento", "adquisicion", "capex_elevado"):
        for codigo in _sectores(catalogo)[:10]:
            for semilla in range(4):
                evolucion = generar_evolucion_arquetipo(
                    codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                    arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
                )
                for año in (2024, 2025):
                    total += 1
                    if evolucion.ejercicios[año].reservas_eur < 0:
                        negativos += 1
    assert negativos / total < 0.05, f"{negativos}/{total} ejercicios con reservas negativas"


# --------------------------------------------------------------------------------------------
# Hallazgo de auditoría de trazabilidad (Ronda 1, Fase 4, ver motor/resumen_caso.py): el modo
# típico/atípico de `activo_no_corriente`, las periodificaciones y `capital_social` se
# descartaba con `_generar_partida(...) -> valor, _` — mismo patrón ya corregido para
# existencias/deudores/acreedores/deudas financieras/ROE_caso, aplicado aquí a estos 3 sitios
# ANTERIORES a los lotes de desglose de balance (decisiones #24-25).
# --------------------------------------------------------------------------------------------


def test_generar_perfil_activo_no_corriente_expone_el_modo_de_cada_componente(catalogo):
    import numpy as np

    from motor.empresa_base import generar_perfil_activo_no_corriente

    perfil, modos = generar_perfil_activo_no_corriente(np.random.default_rng(1), "industria")
    assert set(perfil) == set(modos)
    assert set(modos.values()) <= {"tipico", "atipico"}

    empresa = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, catalogo=catalogo)
    assert {k for k in empresa.modos if k.startswith("activo_no_corriente.")} == {
        f"activo_no_corriente.{componente}" for componente in empresa.activo_no_corriente_perfil_pct
    }

    vistos_atipico = 0
    for semilla in range(30):
        e = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
        vistos_atipico += sum(1 for k, v in e.modos.items() if k.startswith("activo_no_corriente.") and v == "atipico")
    assert vistos_atipico > 0


def test_generar_periodificaciones_pct_expone_el_modo_de_cada_una(catalogo):
    import numpy as np

    from motor.empresa_base import generar_periodificaciones_pct

    activo, corto, largo, modo_activo, modo_corto, modo_largo = generar_periodificaciones_pct(
        np.random.default_rng(1), "industria"
    )
    assert modo_activo in ("tipico", "atipico")
    assert modo_corto in ("tipico", "atipico")
    assert modo_largo in ("tipico", "atipico")

    empresa = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, catalogo=catalogo)
    assert set(empresa.modos) >= {"periodificacion_activo", "periodificacion_pasivo_corto", "periodificacion_pasivo_largo"}

    vistos_atipico = 0
    for semilla in range(30):
        e = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
        vistos_atipico += sum(1 for k, v in e.modos.items() if k.startswith("periodificacion_") and v == "atipico")
    assert vistos_atipico > 0


def test_generar_capital_social_expone_su_modo(catalogo):
    import numpy as np

    from motor.empresa_base import _generar_capital_social

    valor, modo = _generar_capital_social(np.random.default_rng(1), 1_000_000.0)
    assert valor >= 0
    assert modo in ("tipico", "atipico")

    empresa = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, catalogo=catalogo)
    assert empresa.modos.get("capital_social") in ("tipico", "atipico")

    vistos_atipico = 0
    for semilla in range(30):
        e = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
        if e.modos.get("capital_social") == "atipico":
            vistos_atipico += 1
    assert vistos_atipico > 0
