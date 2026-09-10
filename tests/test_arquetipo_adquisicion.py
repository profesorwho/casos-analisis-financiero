"""Tests del arquetipo 18 (Adquisición — sección 2.24).

El más distinto de todos los implementados hasta ahora: no es una desviación progresiva de un
ratio a lo largo de 3 años, es un salto discreto y exógeno de activo_no_corriente en un único
ejercicio FIJO (AÑO_ADQUISICION, siempre 2024, nunca sorteado — ver docstring del módulo,
sección "Arquetipo 18", para el porqué), financiado con caja + deuda a largo nueva, con
separación explícita de ventas orgánicas/inorgánicas y una nota de memoria OBLIGATORIA (no
opcional como en el resto de usos de `nota_memoria`).
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import resolver_fila_sector
from motor.evolucion_arquetipo import (
    AÑO_ADQUISICION,
    INTENSIDAD_BASE,
    N_DESVIACIONES_TECHO_ENDEUDAMIENTO,
    NOTAS_MEMORIA_ADQUISICION,
    TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    generar_evolucion_arquetipo,
)

VENTAS_OBJETIVO_2023 = 8_000_000.0
SEMILLAS = range(8)

SECTORES = [
    pytest.param("24.1", id="industrial-siderurgia"),
    pytest.param("62", id="servicios-tic"),
    pytest.param("47.1", id="comercio-supermercados"),
]


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _generar(catalogo, arquetipos, sector, semilla, intensidad="fuerte"):
    return generar_evolucion_arquetipo(
        sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
        arquetipo_id="adquisicion", catalogo=catalogo, arquetipos=arquetipos,
    )


def _cuadra(ejercicio) -> bool:
    activo = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
    pn_pasivo = (
        ejercicio.balance_eur["patrimonio_neto"]
        + ejercicio.balance_eur["pasivo_no_corriente"]
        + ejercicio.balance_eur["pasivo_corriente"]
    )
    return abs(activo - pn_pasivo) <= 0.01


def _techo_endeudamiento(fila):
    return min(
        fila["ratios.endeudamiento.huber_9y"] + N_DESVIACIONES_TECHO_ENDEUDAMIENTO * fila["ratios.endeudamiento.huber_scale_mad"],
        TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    )


@pytest.mark.parametrize("sector", SECTORES)
def test_adquisicion_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_adquisicion_solo_ocurre_en_2024_nunca_en_2025(catalogo, arquetipos, sector):
    # A diferencia del arquetipo 12 (año sorteado), aquí el año es FIJO — ver AÑO_ADQUISICION.
    assert AÑO_ADQUISICION == 2024
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, sector, semilla)
        ej = evolucion.ejercicios
        assert ej[2023].ventas_organicas_eur is None
        assert ej[2023].ventas_inorganicas_eur is None
        assert ej[2024].ventas_organicas_eur is not None
        assert ej[2024].ventas_inorganicas_eur is not None
        assert ej[2024].ventas_inorganicas_eur > 0
        assert ej[2025].ventas_organicas_eur is None
        assert ej[2025].ventas_inorganicas_eur is None


@pytest.mark.parametrize("sector", SECTORES)
def test_adquisicion_desglose_de_ventas_suma_el_total(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, sector, semilla)
        ej = evolucion.ejercicios[2024]
        assert ej.ventas_organicas_eur + ej.ventas_inorganicas_eur == pytest.approx(ej.ventas, rel=1e-9)
        # Las orgánicas deben coincidir con lo que habría dado el crecimiento normal, sin el
        # arquetipo (mismo crecimiento_ventas que ya lleva registrado el ejercicio).
        anterior = evolucion.ejercicios[2023]
        proporcional_sin_arquetipo = anterior.ventas * (1 + ej.crecimiento_ventas)
        assert ej.ventas_organicas_eur == pytest.approx(proporcional_sin_arquetipo, rel=1e-9)


@pytest.mark.parametrize("sector", SECTORES)
def test_adquisicion_incremento_de_activo_proporcional_a_intensidad(catalogo, arquetipos, sector):
    # Regresión de la fórmula de magnitud: incremento = intensidad_base x activo total 2023
    # (antes de la operación) — no escalado por fracción del año (suceso puntual, no progresivo).
    for intensidad in ("leve", "moderado", "fuerte"):
        for semilla in SEMILLAS:
            evolucion = _generar(catalogo, arquetipos, sector, semilla, intensidad)
            ej = evolucion.ejercicios
            activo_total_2023 = ej[2023].balance_eur["activo_no_corriente"] + ej[2023].balance_eur["activo_corriente"]
            activo_no_corriente_proporcional = ej[2023].balance_eur["activo_no_corriente"] * (
                1 + (ej[2024].ventas_organicas_eur / ej[2023].ventas - 1)
            )
            exceso_activo = ej[2024].balance_eur["activo_no_corriente"] - activo_no_corriente_proporcional
            incremento_esperado = INTENSIDAD_BASE[intensidad] * activo_total_2023
            assert exceso_activo == pytest.approx(incremento_esperado, rel=1e-6)


@pytest.mark.parametrize("sector", SECTORES)
def test_adquisicion_no_se_repite_en_2025(catalogo, arquetipos, sector):
    # 2025 crece proporcionalmente desde la base YA ampliada de 2024, sin una segunda inyección.
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, sector, semilla)
        ej = evolucion.ejercicios
        crecimiento_ventas_2025 = ej[2025].ventas / ej[2024].ventas - 1
        proporcional = ej[2024].balance_eur["activo_no_corriente"] * (1 + crecimiento_ventas_2025)
        assert ej[2025].balance_eur["activo_no_corriente"] == pytest.approx(proporcional, rel=1e-6)


@pytest.mark.parametrize("sector", SECTORES)
def test_adquisicion_financiada_con_caja_y_deuda_a_largo_no_negativa(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, sector, semilla)
        ej = evolucion.ejercicios
        assert ej[2024].balance_eur["disponible"] >= -0.01
        assert ej[2024].balance_eur["deudas_fin_largo"] >= ej[2023].balance_eur["deudas_fin_largo"]


@pytest.mark.parametrize("sector", SECTORES)
def test_adquisicion_nota_memoria_es_obligatoria_solo_en_2024(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, sector, semilla)
        ej = evolucion.ejercicios
        assert ej[2023].nota_memoria is None
        assert ej[2024].nota_memoria is not None
        assert ej[2024].nota_memoria in NOTAS_MEMORIA_ADQUISICION
        assert ej[2025].nota_memoria is None


@pytest.mark.parametrize("sector", SECTORES)
def test_adquisicion_nota_memoria_reproducible(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        a = _generar(catalogo, arquetipos, sector, semilla)
        b = _generar(catalogo, arquetipos, sector, semilla)
        assert a.ejercicios[2024].nota_memoria == b.ejercicios[2024].nota_memoria


def test_adquisicion_nota_memoria_varia_entre_las_5_opciones(catalogo, arquetipos):
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    notas_vistas = set()
    for codigo in codigos:
        for semilla in range(4):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="adquisicion", catalogo=catalogo, arquetipos=arquetipos,
            )
            notas_vistas.add(evolucion.ejercicios[2024].nota_memoria)
    assert len(notas_vistas) == len(NOTAS_MEMORIA_ADQUISICION), notas_vistas


def test_adquisicion_riesgo_endeudamiento_siempre_señalizado(catalogo, arquetipos):
    # Mismo patrón ya establecido para 9/11/15/16/17: el arquetipo no toca circulante, así que
    # cuando dispara riesgo_endeudamiento queda en contencion_al_limite=True — lo que importa es
    # que el chequeo (incondicional) nunca deje pasar un caso sin señalizar. Barrido
    # representativo (27 sectores x 3 intensidades x 4 semillas = 324 casos).
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    sin_señal = []
    activaciones = 0
    for codigo in codigos:
        fila = resolver_fila_sector(catalogo, codigo, "grandes_medianas")
        techo = _techo_endeudamiento(fila)
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                evolucion = generar_evolucion_arquetipo(
                    codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
                    arquetipo_id="adquisicion", catalogo=catalogo, arquetipos=arquetipos,
                )
                for año, ejercicio in evolucion.ejercicios.items():
                    if año == 2023:
                        continue
                    if ejercicio.riesgo_endeudamiento:
                        activaciones += 1
                    if ejercicio.endeudamiento > techo + 1e-6 and not ejercicio.riesgo_endeudamiento:
                        sin_señal.append((codigo, intensidad, semilla, año))
    assert activaciones > 0, "la muestra no incluyó ningún caso donde se activara la contención: ajustar el barrido"
    assert not sin_señal, f"{len(sin_señal)} casos sin señalizar: {sin_señal[:10]}"


def test_adquisicion_sin_descuadres_en_barrido_completo(catalogo, arquetipos):
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    descuadres = []
    for codigo in codigos:
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                evolucion = generar_evolucion_arquetipo(
                    codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
                    arquetipo_id="adquisicion", catalogo=catalogo, arquetipos=arquetipos,
                )
                for ejercicio in evolucion.ejercicios.values():
                    activo = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
                    pn_pasivo = (
                        ejercicio.balance_eur["patrimonio_neto"]
                        + ejercicio.balance_eur["pasivo_no_corriente"]
                        + ejercicio.balance_eur["pasivo_corriente"]
                    )
                    if abs(activo - pn_pasivo) > 0.01:
                        descuadres.append((codigo, intensidad, semilla, ejercicio.año))
    assert not descuadres, f"{len(descuadres)} descuadres: {descuadres[:10]}"
