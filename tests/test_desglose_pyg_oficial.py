"""Tests del desglose de PyG en líneas oficiales del PGC (Normal y Abreviado) — ENCARGO 1/2 de
este lote (ver motor/empresa_base.py y motor/evolucion_arquetipo.py). Se AÑADE ENCIMA de los
agregados internos ya existentes (`cifra_negocios`, `consumos_explotacion`, `otros_gastos_
explot`, `gastos_personal`, `ingresos_financieros`), sin sustituirlos: cada sub-partida debe
sumar EXACTO a su agregado (tolerancia `TOLERANCIA_CUADRE_EUR`).

Cubre lo pedido explícitamente:
  1) cifra_negocios -> ventas/servicios, perfil por categoría.
  2) consumos_explotacion -> mercaderías/materias primas/trabajos de terceros/deterioro.
  3) otros_gastos_explot -> servicios exteriores/tributos/pérdidas por operaciones comerciales
     (enlazada a `motor.insolvencias`, nunca un sorteo nuevo)/otros gastos de gestión/GEI (0.0).
  4) gastos_personal -> sueldos y salarios/cargas sociales (anclado a los tipos de cotización
     vigentes 2023-2025)/provisiones (enlazada a `motor.provisiones`, nunca un sorteo nuevo).
  5) ingresos_financieros -> empresas del grupo (derivado de `inversion_grupo_largo_eur` x
     `tipo_interes`, arquetipo 20)/terceros.
  6) resultado_extraordinario expuesto como línea oficial "13. Otros resultados" (alias, sin
     cambio numérico).
  7) exceso_eur de provisiones/insolvencias expuesto como línea oficial "10. Excesos de
     provisiones" (alias, sin cambio numérico).
  8) ECPN: "Resultados de ejercicios anteriores" como columna propia, separada de "Reservas".
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.ecpn import generar_ecpn
from motor.empresa_base import (
    MEI_EMPRESARIAL_PP_POR_AÑO,
    PERFIL_CIFRA_NEGOCIOS_POR_CATEGORIA,
    PRIMA_ACCIDENTES_TRABAJO_POR_CATEGORIA,
    TASA_CARGAS_SOCIALES_BASE_PP,
    TOLERANCIA_CUADRE_EUR,
    categoria_de_sector,
    generar_empresa_base,
    tasa_cargas_sociales_pct,
)
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.memoria import generar_caso_combinado

VENTAS_OBJETIVO_2023 = 15_000_000.0

DESGLOSES_SIMPLES = {
    "cifra_negocios": "pyg_cifra_negocios_desglose_eur",
    "consumos_explotacion": "pyg_consumos_explotacion_desglose_eur",
    "otros_gastos_explot": "pyg_otros_gastos_explot_desglose_eur",
    "gastos_personal": "pyg_gastos_personal_desglose_eur",
    "ingresos_financieros": "pyg_ingresos_financieros_desglose_eur",
}


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _sectores(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


def _assert_cuadra_y_no_negativo(ejercicio, etiqueta):
    for agregado, campo in DESGLOSES_SIMPLES.items():
        total_agregado = ejercicio.pyg_eur[agregado]
        desglose = getattr(ejercicio, campo)
        assert sum(desglose.values()) == pytest.approx(total_agregado, abs=TOLERANCIA_CUADRE_EUR), (
            f"{etiqueta}: {agregado} no cuadra ({sum(desglose.values())} vs {total_agregado})"
        )
        for componente, valor in desglose.items():
            assert valor >= -1e-6, f"{etiqueta}: {agregado}.{componente}={valor} es negativo"


# --------------------------------------------------------------------------------------------
# Suma exacta y no negatividad — empresa base y evolución, barrido amplio.
# --------------------------------------------------------------------------------------------


def test_desglose_pyg_oficial_suma_exacta_en_empresa_base(catalogo):
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            _assert_cuadra_y_no_negativo(empresa, f"base sector={codigo} semilla={semilla}")


@pytest.mark.parametrize("arquetipo_id", ["exceso_stock", "apalancamiento", "aumento_clientes", "operaciones_vinculadas"])
def test_desglose_pyg_oficial_suma_exacta_en_evolucion(catalogo, arquetipos, arquetipo_id):
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                _assert_cuadra_y_no_negativo(ejercicio, f"{arquetipo_id} sector={codigo} semilla={semilla} año={ejercicio.año}")


def test_desglose_pyg_oficial_suma_exacta_en_combos(catalogo, arquetipos):
    combo = {"crecimiento_destruccion_caja": "fuerte", "apalancamiento": "fuerte", "riesgo_liquidez_pese_beneficio": "fuerte"}
    for codigo in ("24.1", "62", "68"):
        for semilla in range(3):
            caso = generar_caso_combinado(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla, combo, catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in caso.ejercicios.values():
                _assert_cuadra_y_no_negativo(ejercicio, f"combo sector={codigo} semilla={semilla} año={ejercicio.año}")


# --------------------------------------------------------------------------------------------
# 1) Cifra de negocios: perfil por categoría, dominancia esperada.
# --------------------------------------------------------------------------------------------


def test_cifra_negocios_servicios_dominante_en_profesionales_y_tic():
    for categoria in ("servicios_profesionales", "servicios_tic"):
        perfil = PERFIL_CIFRA_NEGOCIOS_POR_CATEGORIA[categoria]
        assert perfil["servicios"] > perfil["ventas"]


def test_cifra_negocios_ventas_dominante_en_industria_comercio_construccion():
    for categoria in ("industria", "comercio_hosteleria", "construccion"):
        perfil = PERFIL_CIFRA_NEGOCIOS_POR_CATEGORIA[categoria]
        assert perfil["ventas"] > perfil["servicios"]


def test_perfil_cifra_negocios_perfil_fijo_desde_2023(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    perfiles = {año: ej.pyg_cifra_negocios_perfil_pct for año, ej in evolucion.ejercicios.items()}
    assert perfiles[2023] == perfiles[2024] == perfiles[2025]


# --------------------------------------------------------------------------------------------
# 3) Otros gastos de explotación: enlace con insolvencias (cuenta 490), GEI siempre 0.
# --------------------------------------------------------------------------------------------


def test_perdidas_deterioro_comercial_coincide_con_dotacion_insolvencia(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(10):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in (evolucion.ejercicios[2024], evolucion.ejercicios[2025]):
                if ejercicio.insolvencia_dotacion_eur <= 0:
                    continue
                comprobados += 1
                desglose = ejercicio.pyg_otros_gastos_explot_desglose_eur
                assert desglose["perdidas_deterioro_operaciones_comerciales"] == pytest.approx(
                    ejercicio.insolvencia_dotacion_eur, abs=TOLERANCIA_CUADRE_EUR
                )
    assert comprobados > 0, "ninguna dotación de insolvencia observada — ampliar el barrido"


def test_gases_efecto_invernadero_siempre_cero(catalogo, arquetipos):
    for codigo in ("24.1", "62"):
        evolucion = generar_evolucion_arquetipo(
            codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
            arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
        )
        for ejercicio in evolucion.ejercicios.values():
            assert ejercicio.pyg_otros_gastos_explot_desglose_eur["gases_efecto_invernadero"] == 0.0


# --------------------------------------------------------------------------------------------
# 4) Gastos de personal: tasa de cotización por año (MEI escalonado) y enlace con provisiones.
# --------------------------------------------------------------------------------------------


def test_tasa_cargas_sociales_escala_con_el_mei_por_año():
    for categoria in ("industria", "servicios_tic"):
        tasas = {año: tasa_cargas_sociales_pct(año, categoria) for año in (2023, 2024, 2025)}
        assert tasas[2023] < tasas[2024] < tasas[2025]
        for año in (2023, 2024, 2025):
            esperado = TASA_CARGAS_SOCIALES_BASE_PP + MEI_EMPRESARIAL_PP_POR_AÑO[año] + PRIMA_ACCIDENTES_TRABAJO_POR_CATEGORIA[categoria]
            assert tasas[año] == pytest.approx(esperado)


def test_cargas_sociales_es_la_fraccion_esperada_del_resto_sin_provision(catalogo):
    empresa = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, catalogo=catalogo)
    categoria = categoria_de_sector("24.1")
    tasa = tasa_cargas_sociales_pct(2023, categoria)
    desglose = empresa.pyg_gastos_personal_desglose_eur
    assert desglose["provisiones"] == 0.0  # el año base nunca dota provisión
    assert desglose["cargas_sociales"] == pytest.approx(desglose["sueldos_salarios"] * tasa, rel=1e-9)


def test_provision_dotacion_gastos_personal_coincide_y_reduce_el_resto(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in (evolucion.ejercicios[2024], evolucion.ejercicios[2025]):
                if ejercicio.provision_dotacion_eur <= 0 or ejercicio.provision_naturaleza_pyg != "gastos_personal":
                    continue
                comprobados += 1
                desglose = ejercicio.pyg_gastos_personal_desglose_eur
                assert desglose["provisiones"] == pytest.approx(ejercicio.provision_dotacion_eur, abs=TOLERANCIA_CUADRE_EUR)
                categoria = categoria_de_sector(codigo)
                tasa = tasa_cargas_sociales_pct(ejercicio.año, categoria)
                resto_esperado = ejercicio.pyg_eur["gastos_personal"] - ejercicio.provision_dotacion_eur
                assert desglose["sueldos_salarios"] + desglose["cargas_sociales"] == pytest.approx(resto_esperado, abs=TOLERANCIA_CUADRE_EUR)
                assert desglose["cargas_sociales"] == pytest.approx(desglose["sueldos_salarios"] * tasa, rel=1e-6)
    assert comprobados > 0, "ninguna provisión de naturaleza 'gastos_personal' observada — ampliar el barrido"


# --------------------------------------------------------------------------------------------
# 5) Ingresos financieros: enlace con el préstamo a matriz del arquetipo 20 (operaciones
# vinculadas) — sin sorteo nuevo, topado al agregado.
# --------------------------------------------------------------------------------------------


def test_ingresos_financieros_grupo_cero_sin_prestamo_a_matriz(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    for ejercicio in evolucion.ejercicios.values():
        assert ejercicio.inversion_grupo_largo_eur == 0.0
        assert ejercicio.pyg_ingresos_financieros_desglose_eur["empresas_grupo"] == 0.0
        assert ejercicio.pyg_ingresos_financieros_desglose_eur["terceros"] == pytest.approx(
            ejercicio.pyg_eur["ingresos_financieros"], abs=TOLERANCIA_CUADRE_EUR
        )


def test_ingresos_financieros_grupo_deriva_del_prestamo_a_matriz(catalogo, arquetipos):
    for semilla in range(60):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="operaciones_vinculadas", catalogo=catalogo, arquetipos=arquetipos,
        )
        ejercicio = evolucion.ejercicios[2025]
        if ejercicio.operacion_vinculada_tipo != "prestamo_matriz" or ejercicio.inversion_grupo_largo_eur <= 0:
            continue
        desglose = ejercicio.pyg_ingresos_financieros_desglose_eur
        bruto_esperado = ejercicio.inversion_grupo_largo_eur * ejercicio.tipo_interes
        esperado = min(bruto_esperado, ejercicio.pyg_eur["ingresos_financieros"])
        assert desglose["empresas_grupo"] == pytest.approx(esperado, abs=TOLERANCIA_CUADRE_EUR)
        assert desglose["empresas_grupo"] + desglose["terceros"] == pytest.approx(
            ejercicio.pyg_eur["ingresos_financieros"], abs=TOLERANCIA_CUADRE_EUR
        )
        assert desglose["terceros"] >= -1e-6
        return
    pytest.fail("ninguna semilla activó 'prestamo_matriz' con importe positivo — ampliar el barrido")


# --------------------------------------------------------------------------------------------
# 6) y 7) Líneas oficiales alias — sin cambio numérico respecto a los campos ya existentes.
# --------------------------------------------------------------------------------------------


def test_linea_13_otros_resultados_es_alias_de_resultado_extraordinario(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
        arquetipo_id="resultado_extraordinario", catalogo=catalogo, arquetipos=arquetipos,
    )
    for ejercicio in evolucion.ejercicios.values():
        assert ejercicio.pyg_linea_13_otros_resultados_eur == ejercicio.pyg_eur["resultado_extraordinario"]


def test_linea_10_excesos_provisiones_suma_provision_e_insolvencia(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(10):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert ejercicio.pyg_linea_10_excesos_provisiones_eur == pytest.approx(
                    ejercicio.provision_exceso_eur + ejercicio.insolvencia_exceso_eur
                )
                if ejercicio.pyg_linea_10_excesos_provisiones_eur > 0:
                    comprobados += 1
    assert comprobados > 0, "ningún exceso de provisión/insolvencia observado — ampliar el barrido"


# --------------------------------------------------------------------------------------------
# 8) ECPN: "Resultados de ejercicios anteriores" separado de "Reservas".
# --------------------------------------------------------------------------------------------


def test_ecpn_resultados_ejercicios_anteriores_cierra_siempre_en_cero(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
    )
    for año in (2024, 2025):
        ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
        assert ecpn.saldo_inicio.resultados_ejercicios_anteriores == pytest.approx(
            evolucion.ejercicios[año - 1].pyg_eur["resultado_ejercicio"]
        )
        assert ecpn.saldo_final.resultados_ejercicios_anteriores == pytest.approx(0.0, abs=1e-6)
        assert ecpn.cuadra


def test_ecpn_reservas_saldo_final_no_cambia_al_separar_la_columna(catalogo, arquetipos):
    """El saldo final de "Reservas" debe seguir siendo el mismo que daba la fórmula fusionada
    anterior (reservas(t-1) + resultado(t-1) - distribuciones) — la separación de columnas es de
    presentación, no debe alterar ningún total ya validado."""
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
    )
    for año in (2024, 2025):
        anterior = evolucion.ejercicios[año - 1]
        actual = evolucion.ejercicios[año]
        ecpn = generar_ecpn(anterior, actual, obligatorio=True)
        esperado = (
            anterior.reservas_eur
            + anterior.pyg_eur["resultado_ejercicio"]
            - (actual.apalancamiento_extra_eur + actual.payout_dividendos_eur)
        )
        assert ecpn.saldo_final.reservas == pytest.approx(esperado, abs=0.01)
