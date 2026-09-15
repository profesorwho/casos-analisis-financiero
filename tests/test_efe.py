"""Tests del Estado de Flujos de Efectivo (EFE, método indirecto, modelo normal PGC).

La comprobación central del proyecto para este módulo: reconciliación exacta con
`disponible` ya generado por el motor (tolerancia 0,01€) — no que el EFE "tenga buena pinta".
Barrido representativo (no el sweep exhaustivo completo, ejecutado aparte) sobre los 21
arquetipos en solitario, las 6 combinaciones recomendadas y un caso sin empuje real de
arquetipo, para varios sectores y semillas.
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.efe import generar_efe
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.memoria import generar_caso_combinado

VENTAS_OBJETIVO_2023 = 15_000_000.0

SECTORES = [
    pytest.param("24.1", id="industria-siderurgia"),
    pytest.param("62", id="servicios-tic"),
    pytest.param("68", id="inmobiliario"),
]

COMBOS_RECOMENDADOS = {
    "A": {"exceso_stock": "fuerte", "dependencia_pocos_clientes": "fuerte"},
    "B": {"crecimiento_destruccion_caja": "fuerte", "mejora_margen": "fuerte"},
    "C": {"crecimiento_destruccion_caja": "fuerte", "apalancamiento": "fuerte", "riesgo_liquidez_pese_beneficio": "fuerte"},
    "D": {"mejora_ebitda": "fuerte", "resultado_extraordinario": "fuerte"},
    "E": {"adquisicion": "fuerte", "activo_mantenido_venta": "fuerte", "operaciones_vinculadas": "fuerte", "coberturas": "fuerte"},
    "F": {"crecimiento_destruccion_caja": "fuerte", "exceso_stock": "fuerte", "apalancamiento": "fuerte", "riesgo_refinanciacion": "fuerte"},
}


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


CUANTITATIVOS_A_PROBAR = [
    "crecimiento_destruccion_caja", "beneficio_sin_cash_flow", "aumento_nof", "deterioro_ciclo_caja",
    "exceso_stock", "aumento_clientes", "refinanciacion", "apalancamiento", "mejora_ebitda",
    "mejora_margen", "resultado_extraordinario", "roe_elevado_apalancamiento",
    "riesgo_liquidez_pese_beneficio", "riesgo_refinanciacion", "capex_elevado", "adquisicion", "coberturas",
]


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("arquetipo_id", CUANTITATIVOS_A_PROBAR)
def test_efe_reconcilia_arquetipos_en_solitario(catalogo, arquetipos, sector, arquetipo_id):
    for semilla in range(3):
        evolucion = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
        )
        for año in (2024, 2025):
            efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            assert efe.cuadra, (
                f"{arquetipo_id} sector={sector} semilla={semilla} año={año}: "
                f"descuadre {efe.descuadre_eur:,.4f}€"
            )


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("nombre_combo", sorted(COMBOS_RECOMENDADOS))
def test_efe_reconcilia_combos_recomendados(catalogo, arquetipos, sector, nombre_combo):
    combo = COMBOS_RECOMENDADOS[nombre_combo]
    for semilla in range(3):
        evolucion = generar_caso_combinado(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla, combo, catalogo=catalogo, arquetipos=arquetipos,
        )
        for año in (2024, 2025):
            efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            assert efe.cuadra, (
                f"Combo {nombre_combo} sector={sector} semilla={semilla} año={año}: "
                f"descuadre {efe.descuadre_eur:,.4f}€"
            )


def test_efe_amortizacion_siempre_cero(catalogo, arquetipos):
    """Desviación deliberada del modelo de texto (ver docstring de motor/efe.py): este motor no
    reduce activo_no_corriente por amortización acumulada, así que añadirla de vuelta en A.2.a
    duplicaría el efecto ya absorbido por el parche de cuadre (A.3.e) y rompería la
    reconciliación. Fijado como test de regresión explícito, no solo un comentario."""
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="mejora_ebitda", catalogo=catalogo, arquetipos=arquetipos,
    )
    efe = generar_efe(evolucion.ejercicios[2023], evolucion.ejercicios[2024], obligatorio=True)
    assert efe.a2a_amortizacion == 0.0


def test_efe_lineas_sin_mecanismo_quedan_en_cero(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
    )
    efe = generar_efe(evolucion.ejercicios[2023], evolucion.ejercicios[2024], obligatorio=True)
    assert efe.a2k_otros_ingresos_gastos == 0.0
    assert efe.a3c_otros_activos_corrientes == 0.0
    assert efe.a4b_cobros_dividendos == 0.0
    assert efe.a4e_otros == 0.0
    assert efe.c9_instrumentos_patrimonio == 0.0
    assert efe.d_efecto_tipo_cambio == 0.0


def test_efe_apalancamiento_genera_flujo_bruto_de_financiacion(catalogo, arquetipos):
    """El mecanismo de apalancamiento (9/14) financia una distribución con deuda nueva — se
    espera un C.11.a (dividendos, pago) exactamente igual a -(apalancamiento_extra_eur +
    payout_dividendos_eur) cuando el efecto actúa ese año — el payout de fondo (#79-#80) es
    transversal, comparte la misma línea C.11.a (mismo criterio que el modelo oficial PGC, que
    no distingue la fuente de financiación del dividendo, ver decisiones #80)."""
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
    )
    for año in (2024, 2025):
        ejercicio = evolucion.ejercicios[año]
        efe = generar_efe(evolucion.ejercicios[año - 1], ejercicio, obligatorio=True)
        if ejercicio.apalancamiento_extra_eur > 0:
            assert efe.c11a_dividendos == pytest.approx(
                -(ejercicio.apalancamiento_extra_eur + ejercicio.payout_dividendos_eur)
            )


def test_efe_obligatorio_se_marca_explicitamente(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    efe_obligatorio = generar_efe(evolucion.ejercicios[2023], evolucion.ejercicios[2024], obligatorio=True)
    efe_no_obligatorio = generar_efe(evolucion.ejercicios[2023], evolucion.ejercicios[2024], obligatorio=False)
    assert efe_obligatorio.obligatorio is True
    assert efe_no_obligatorio.obligatorio is False
    # El marcado de obligatoriedad no debe alterar ninguna cifra del propio estado.
    assert efe_obligatorio.e_variacion_neta_efectivo == efe_no_obligatorio.e_variacion_neta_efectivo
