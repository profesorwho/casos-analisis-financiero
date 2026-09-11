"""Tests del Estado de Cambios en el Patrimonio Neto (ECPN, Documento B — modelo normal PGC).

Comprobación central: Capital + Reservas + Resultado del ejercicio = PN total real del motor
(tolerancia 0,01€), sobre el mismo barrido representativo que el EFE.
"""

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.ecpn import generar_ecpn
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

CUANTITATIVOS_A_PROBAR = [
    "crecimiento_destruccion_caja", "beneficio_sin_cash_flow", "aumento_nof", "deterioro_ciclo_caja",
    "exceso_stock", "aumento_clientes", "refinanciacion", "apalancamiento", "mejora_ebitda",
    "mejora_margen", "resultado_extraordinario", "roe_elevado_apalancamiento",
    "riesgo_liquidez_pese_beneficio", "riesgo_refinanciacion", "capex_elevado", "adquisicion",
]


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("arquetipo_id", CUANTITATIVOS_A_PROBAR)
def test_ecpn_reconcilia_arquetipos_en_solitario(catalogo, arquetipos, sector, arquetipo_id):
    for semilla in range(3):
        evolucion = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
        )
        for año in (2024, 2025):
            ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            assert ecpn.cuadra, (
                f"{arquetipo_id} sector={sector} semilla={semilla} año={año}: "
                f"descuadre {ecpn.descuadre_eur:,.4f}€"
            )


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("nombre_combo", sorted(COMBOS_RECOMENDADOS))
def test_ecpn_reconcilia_combos_recomendados(catalogo, arquetipos, sector, nombre_combo):
    combo = COMBOS_RECOMENDADOS[nombre_combo]
    for semilla in range(3):
        evolucion = generar_caso_combinado(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla, combo, catalogo=catalogo, arquetipos=arquetipos,
        )
        for año in (2024, 2025):
            ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            assert ecpn.cuadra, (
                f"Combo {nombre_combo} sector={sector} semilla={semilla} año={año}: "
                f"descuadre {ecpn.descuadre_eur:,.4f}€"
            )


def test_ecpn_capital_social_constante_entre_ejercicios(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
    )
    capitales = {año: ej.capital_social_eur for año, ej in evolucion.ejercicios.items()}
    assert capitales[2023] == capitales[2024] == capitales[2025]
    assert capitales[2023] > 0


def test_ecpn_operaciones_con_socios_solo_cuando_hay_apalancamiento(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    for año in (2024, 2025):
        ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
        assert ecpn.operaciones_con_socios.total == 0.0


def test_ecpn_otras_variaciones_siempre_cero(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="adquisicion", catalogo=catalogo, arquetipos=arquetipos,
    )
    for año in (2024, 2025):
        ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
        assert ecpn.otras_variaciones.total == 0.0


def test_ecpn_obligatorio_se_marca_explicitamente(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    ecpn_si = generar_ecpn(evolucion.ejercicios[2023], evolucion.ejercicios[2024], obligatorio=True)
    ecpn_no = generar_ecpn(evolucion.ejercicios[2023], evolucion.ejercicios[2024], obligatorio=False)
    assert ecpn_si.obligatorio is True
    assert ecpn_no.obligatorio is False
    assert ecpn_si.saldo_final.total == ecpn_no.saldo_final.total
