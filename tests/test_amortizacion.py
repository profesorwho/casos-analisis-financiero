"""Tests de la amortización derivada de una colección real de activos (motor/amortizacion.py) —
arreglo de raíz: el gasto de amortización de la PyG ya no se sortea como % independiente
(`amortizaciones_pct` del catálogo), se DERIVA sumando las cuotas de los sub-lotes de activos
todavía no agotados. Comprobación central: la identidad Balance<->PyG (`patrimonio_neto ==
capital_social + reservas + resultado_ejercicio`) se mantiene exacta, y el EFE/ECPN siguen
reconciliando exactamente — ver docstring de motor/amortizacion.py para el marco normativo
(PGC, tabla fiscal) verificado antes de implementar.
"""

import re

import pytest

from motor.amortizacion import bienes_totalmente_amortizados_en
from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.ecpn import generar_ecpn
from motor.efe import generar_efe
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.memoria import generar_caso_combinado

VENTAS_OBJETIVO_2023 = 15_000_000.0

SECTORES = [
    pytest.param("24.1", id="industria-siderurgia"),
    pytest.param("62", id="servicios-tic"),
    pytest.param("68", id="inmobiliario"),
]

CUANTITATIVOS_A_PROBAR = [
    "crecimiento_destruccion_caja", "beneficio_sin_cash_flow", "aumento_nof", "deterioro_ciclo_caja",
    "exceso_stock", "aumento_clientes", "refinanciacion", "apalancamiento", "mejora_ebitda",
    "mejora_margen", "resultado_extraordinario", "roe_elevado_apalancamiento",
    "riesgo_liquidez_pese_beneficio", "riesgo_refinanciacion", "capex_elevado", "adquisicion", "coberturas",
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


def _identidad_pn(ejercicio) -> bool:
    # Incluye las dos líneas de PN de grupo89 (ajustes por cambio de valor, subvenciones — ver
    # motor/coberturas_subvenciones.py), añadidas por el encargo de coberturas/subvenciones:
    # 0.0 en los casos sin cobertura/subvención activa, pero la propensión de fondo de la
    # subvención puede activarse en CUALQUIER caso (no solo los arquetipos 17/21).
    suma = (
        ejercicio.capital_social_eur
        + ejercicio.reservas_eur
        + ejercicio.pyg_eur["resultado_ejercicio"]
        + ejercicio.ajustes_cambio_valor_pn_eur
        + ejercicio.subvenciones_pn_eur
    )
    return abs(suma - ejercicio.balance_eur["patrimonio_neto"]) < 1e-6


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("arquetipo_id", CUANTITATIVOS_A_PROBAR)
def test_identidad_balance_pyg_y_reconciliacion_efe_ecpn_arquetipos_solos(catalogo, arquetipos, sector, arquetipo_id):
    for semilla in range(3):
        evolucion = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
        )
        for año, ejercicio in evolucion.ejercicios.items():
            assert _identidad_pn(ejercicio), f"{arquetipo_id} sector={sector} semilla={semilla} año={año}"
        for año in (2024, 2025):
            efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            assert efe.cuadra, f"{arquetipo_id} sector={sector} semilla={semilla} año={año}: EFE descuadre {efe.descuadre_eur:,.4f}€"
            assert ecpn.cuadra, f"{arquetipo_id} sector={sector} semilla={semilla} año={año}: ECPN descuadre {ecpn.descuadre_eur:,.4f}€"


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("nombre_combo", sorted(COMBOS_RECOMENDADOS))
def test_identidad_balance_pyg_y_reconciliacion_efe_ecpn_combos(catalogo, arquetipos, sector, nombre_combo):
    combo = COMBOS_RECOMENDADOS[nombre_combo]
    for semilla in range(3):
        evolucion = generar_caso_combinado(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla, combo, catalogo=catalogo, arquetipos=arquetipos,
        )
        for año, ejercicio in evolucion.ejercicios.items():
            assert _identidad_pn(ejercicio), f"Combo {nombre_combo} sector={sector} semilla={semilla} año={año}"
        for año in (2024, 2025):
            efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            assert efe.cuadra, f"Combo {nombre_combo} sector={sector} semilla={semilla} año={año}: EFE descuadre {efe.descuadre_eur:,.4f}€"
            assert ecpn.cuadra, f"Combo {nombre_combo} sector={sector} semilla={semilla} año={año}: ECPN descuadre {ecpn.descuadre_eur:,.4f}€"


def test_amortizaciones_eur_derivado_es_mayor_o_igual_cero(catalogo, arquetipos):
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    for codigo in codigos:
        for semilla in range(2):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert ejercicio.pyg_eur["amortizaciones"] >= 0
                assert ejercicio.modos["pyg.amortizaciones"] == "derivado"


def test_capex_y_adquisicion_generan_cohortes_nuevas(catalogo, arquetipos):
    ev_capex = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="capex_elevado", catalogo=catalogo, arquetipos=arquetipos,
    )
    # Cada año compara contra el neto esperado (cohortes nuevas de capex menos las bajas
    # anticipadas de sub-lote de ese mismo año, línea 11 PyG — ver motor/amortizacion.py): con
    # capex "fuerte" el neto sigue siendo positivo, pero la igualdad estricta (sin restar bajas)
    # ya no es válida en general.
    n_2023 = len(ev_capex.ejercicios[2023].coleccion_activos_amortizables)
    n_2024 = len(ev_capex.ejercicios[2024].coleccion_activos_amortizables)
    n_2025 = len(ev_capex.ejercicios[2025].coleccion_activos_amortizables)
    assert n_2024 + len(ev_capex.ejercicios[2024].bajas_inmovilizado) > n_2023
    assert n_2025 + len(ev_capex.ejercicios[2025].bajas_inmovilizado) > n_2024

    ev_adq = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="adquisicion", catalogo=catalogo, arquetipos=arquetipos,
    )
    n_2023_adq = len(ev_adq.ejercicios[2023].coleccion_activos_amortizables)
    assert len(ev_adq.ejercicios[2024].coleccion_activos_amortizables) > n_2023_adq
    # AÑO_ADQUISICION es fijo=2024 — 2025 no añade cohortes propias de ESTE arquetipo, pero SÍ
    # puede (a) quitar alguna por una baja anticipada de sub-lote (línea 11 PyG, ver
    # motor/amortizacion.py) y (b) añadir cohortes de CAPEX IMPLÍCITO (encargo "amortización
    # acumulada real", decisiones_plausibilidad.md #94, motor.amortizacion.
    # generar_cohortes_capex_implicito) — el crecimiento orgánico de activo_no_corriente por
    # ventas no se detiene solo porque el arquetipo 18 ya no actúa ese año. La colección de 2025
    # = la de 2024 menos las bajas de 2025, más el capex implícito de 2025 si salió > 0 (siempre
    # el caso en el barrido de verificación, ver decisiones_plausibilidad.md #94).
    esperado_sin_capex_implicito_2025 = len(
        ev_adq.ejercicios[2024].coleccion_activos_amortizables
    ) - len(ev_adq.ejercicios[2025].bajas_inmovilizado)
    if ev_adq.ejercicios[2025].capex_implicito_eur > 0:
        assert len(ev_adq.ejercicios[2025].coleccion_activos_amortizables) > esperado_sin_capex_implicito_2025
    else:
        assert len(ev_adq.ejercicios[2025].coleccion_activos_amortizables) == esperado_sin_capex_implicito_2025


def test_bienes_totalmente_amortizados_quedan_expuestos(catalogo, arquetipos):
    """Datos para la futura nota de memoria PGC punto 2.l — se comprueba que la función los
    expone con la estructura correcta (tipo, es_construccion, valor_bruto, año), no que su
    número exacto sea uno concreto (depende de sorteos)."""
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    total_bienes = 0
    for codigo in codigos[:10]:
        for semilla in range(3):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio_2025 = evolucion.ejercicios[2025]
            bienes = bienes_totalmente_amortizados_en(ejercicio_2025.coleccion_activos_amortizables, 2025)
            total_bienes += len(bienes)
            for bien in bienes:
                assert bien.valor_bruto_eur > 0
                assert bien.año_amortizacion_total <= 2025
                assert isinstance(bien.es_construccion, bool)
    assert total_bienes > 0, "el barrido no detectó ningún bien totalmente amortizado — revisar la muestra"
