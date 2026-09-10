"""Tests del tercer lote de arquetipos (2, 12, 14, 16, 17 — sección 2.24).

2, 14 y 16 reutilizan mecanismos ya existentes sin código nuevo (tesoreria, apalancamiento,
reclasificacion_deuda respectivamente, este último con dirección opuesta y una nota de memoria
propia). 12 y 17 son mecanismos nuevos (evento_puntual y capex) — ver docstring de
motor/evolucion_arquetipo.py para el diseño de ambos y de los hallazgos cuantificados.

El arquetipo 13 (Diferencias EBITDA/EBIT/beneficio/caja) no tiene entrada en data/arquetipos.json
a propósito: es una comparación de síntesis sobre magnitudes que la PyG ya genera (baii, bai,
resultado_ejercicio, amortizaciones), no requiere ninguna huella nueva — pertenece a la futura
capa de análisis/diagnóstico, no al motor de generación.
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import resolver_fila_sector
from motor.evolucion_arquetipo import (
    FRACCION_MINIMA_VS_HUBER,
    N_DESVIACIONES_TECHO_ENDEUDAMIENTO,
    NOTAS_MEMORIA_RIESGO_REFINANCIACION,
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


def _generar(catalogo, arquetipos, arquetipo_id, sector, semilla, intensidad="fuerte"):
    return generar_evolucion_arquetipo(
        sector,
        "grandes_medianas",
        VENTAS_OBJETIVO_2023,
        semilla=semilla,
        intensidad=intensidad,
        arquetipo_id=arquetipo_id,
        catalogo=catalogo,
        arquetipos=arquetipos,
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


# --------------------------------------------------------------------------------------------
# Arquetipo 2: Beneficio sin cash flow suficiente — mismo mecanismo que el 15 (EfectoTesoreria),
# reutilizado bajo un id/nombre/ratio_catalogo distintos.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_beneficio_sin_cash_flow_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "beneficio_sin_cash_flow", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_beneficio_sin_cash_flow_no_toca_circulante_ni_pyg(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "beneficio_sin_cash_flow", sector, semilla, intensidad="moderado")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            for variable in ("existencias", "realizable", "acreedores_comerciales"):
                proporcional = ej[año_anterior].balance_eur[variable] * (1 + crecimiento_ventas)
                assert ej[año].balance_eur[variable] == pytest.approx(proporcional, rel=1e-9)
            for modo in ej[año].modos.values():
                assert modo in ("tipico", "atipico")  # ningún "arquetipo": no hay primitivas forzadas


@pytest.mark.parametrize("sector", SECTORES)
def test_beneficio_sin_cash_flow_disponible_cae_o_deuda_corto_compensa(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "beneficio_sin_cash_flow", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            activo_anterior = ej[año_anterior].balance_eur["activo_no_corriente"] + ej[año_anterior].balance_eur["activo_corriente"]
            activo_actual = ej[año].balance_eur["activo_no_corriente"] + ej[año].balance_eur["activo_corriente"]
            disponible_relativo_anterior = ej[año_anterior].balance_eur["disponible"] / activo_anterior
            disponible_relativo_actual = ej[año].balance_eur["disponible"] / activo_actual
            disponible_cae = disponible_relativo_actual < disponible_relativo_anterior
            deuda_corto_sube = ej[año].balance_eur["deudas_fin_corto"] > ej[año_anterior].balance_eur["deudas_fin_corto"]
            assert disponible_cae or deuda_corto_sube


# --------------------------------------------------------------------------------------------
# Arquetipo 12: Resultado extraordinario — suceso puntual en un único año (2024 o 2025, sorteado
# por caso), no una tendencia progresiva.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_resultado_extraordinario_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "resultado_extraordinario", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_resultado_extraordinario_solo_afecta_a_un_año(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "resultado_extraordinario", sector, semilla)
        ej = evolucion.ejercicios
        años_con_evento = [
            año for año in (2023, 2024, 2025) if ej[año].modos.get("pyg.resultado_extraordinario") == "arquetipo"
        ]
        assert len(años_con_evento) == 1, f"semilla {semilla}: {len(años_con_evento)} años con el suceso, se esperaba 1"
        assert años_con_evento[0] in (2024, 2025)
        # El año SIN el suceso (de los dos años del arquetipo) debe volver al ruido normal.
        año_sin_evento = 2025 if años_con_evento[0] == 2024 else 2024
        assert ej[año_sin_evento].modos.get("pyg.resultado_extraordinario") in ("tipico", "atipico")


@pytest.mark.parametrize("sector", SECTORES)
def test_resultado_extraordinario_reproducible_mismo_año_con_misma_semilla(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        a = _generar(catalogo, arquetipos, "resultado_extraordinario", sector, semilla)
        b = _generar(catalogo, arquetipos, "resultado_extraordinario", sector, semilla, intensidad="fuerte")
        año_a = next(año for año in (2024, 2025) if a.ejercicios[año].modos.get("pyg.resultado_extraordinario") == "arquetipo")
        año_b = next(año for año in (2024, 2025) if b.ejercicios[año].modos.get("pyg.resultado_extraordinario") == "arquetipo")
        assert año_a == año_b, "el año del suceso no debería depender de la intensidad"


def test_resultado_extraordinario_distribucion_del_año_no_esta_sesgada(catalogo, arquetipos):
    # Regresión del tipo de sesgo ya encontrado en nota_memoria: el año del suceso se sortea con
    # rng_tendencia, que ya es independiente por sector+segmento — se comprueba aquí que la
    # distribución entre 2024/2025 no colapsa a un único valor por semilla (barrido de 27
    # sectores x 4 semillas = 108 sorteos "efectivos", independientes de la intensidad).
    import re as re_

    codigos = [re_.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    distribucion = {2024: 0, 2025: 0}
    for codigo in codigos:
        for semilla in range(4):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="resultado_extraordinario", catalogo=catalogo, arquetipos=arquetipos,
            )
            for año in (2024, 2025):
                if evolucion.ejercicios[año].modos.get("pyg.resultado_extraordinario") == "arquetipo":
                    distribucion[año] += 1
    total = sum(distribucion.values())
    assert total == len(codigos) * 4
    # Ninguno de los dos años debe acaparar (casi) todos los sorteos: comprobación laxa de
    # variedad real, no una prueba estadística estricta (n=108 es pequeño para un chi-cuadrado
    # fino, pero un reparto 108/0 o 0/108 sí sería una señal inequívoca de sesgo).
    assert distribucion[2024] >= 20 and distribucion[2025] >= 20, distribucion


@pytest.mark.parametrize("sector", SECTORES)
def test_resultado_extraordinario_no_altera_el_circulante(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "resultado_extraordinario", sector, semilla, intensidad="moderado")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            for variable in ("existencias", "realizable", "acreedores_comerciales"):
                proporcional = ej[año_anterior].balance_eur[variable] * (1 + crecimiento_ventas)
                assert ej[año].balance_eur[variable] == pytest.approx(proporcional, rel=1e-9)


# --------------------------------------------------------------------------------------------
# Arquetipo 14: ROE elevado por apalancamiento — mismo mecanismo (EfectoApalancamiento) que el
# arquetipo 9, declarado como variante en data/arquetipos.json.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_roe_elevado_apalancamiento_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "roe_elevado_apalancamiento", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_roe_elevado_apalancamiento_sube_el_endeudamiento_igual_que_apalancamiento(catalogo, arquetipos, sector):
    # No repite toda la batería de test_apalancamiento_* de test_arquetipos_generalizados.py
    # (sería duplicar exactamente el mismo mecanismo): solo confirma que la huella de deuda es
    # idéntica a la del arquetipo 9 para el mismo caso, ya que comparten efecto y parámetros.
    for semilla in SEMILLAS:
        ev_9 = _generar(catalogo, arquetipos, "apalancamiento", sector, semilla)
        ev_14 = _generar(catalogo, arquetipos, "roe_elevado_apalancamiento", sector, semilla)
        for año in (2023, 2024, 2025):
            assert ev_9.ejercicios[año].balance_eur["deudas_fin_largo"] == pytest.approx(
                ev_14.ejercicios[año].balance_eur["deudas_fin_largo"], rel=1e-9
            )
            assert ev_9.ejercicios[año].endeudamiento == pytest.approx(ev_14.ejercicios[año].endeudamiento, rel=1e-9)


# --------------------------------------------------------------------------------------------
# Arquetipo 16: Riesgo de refinanciación — mecanismo reclasificacion_deuda (arquetipo 8) con
# dirección opuesta, más una nota de memoria sobre vencimiento próximo.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_refinanciacion_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "riesgo_refinanciacion", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_refinanciacion_no_altera_la_deuda_financiera_total(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "riesgo_refinanciacion", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            deuda_total_proporcional = (
                ej[año_anterior].balance_eur["deudas_fin_largo"] + ej[año_anterior].balance_eur["deudas_fin_corto"]
            ) * (1 + crecimiento_ventas)
            deuda_total_real = ej[año].balance_eur["deudas_fin_largo"] + ej[año].balance_eur["deudas_fin_corto"]
            assert deuda_total_real == pytest.approx(deuda_total_proporcional, abs=1.0)


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_refinanciacion_baja_la_proporcion_a_largo_plazo(catalogo, arquetipos, sector):
    # No siempre baja en sentido estricto: si el año anterior ya quedó por debajo del suelo
    # defensivo de plausibilidad (FRACCION_MINIMA_VS_HUBER x huber de calidad_deuda del sector
    # — el mismo suelo que ya protege cualquier ratio de continuidad, ver _mover_ratio_continuo),
    # el año siguiente se recorta AL suelo en vez de seguir bajando, lo que puede subir respecto
    # al año anterior. Comprobado con sector 24.1/semilla 3: calidad_deuda 2023 salió
    # anormalmente baja (0,00375) por simple ruido del año base, muy por debajo del suelo
    # (0,06011); 2024 se recorta a ese suelo (sube), 2025 se queda plano en el suelo.
    for semilla in SEMILLAS:
        fila = resolver_fila_sector(catalogo, sector, "grandes_medianas")
        suelo = FRACCION_MINIMA_VS_HUBER * fila["ratios.calidad_deuda.huber_9y"]
        evolucion = _generar(catalogo, arquetipos, "riesgo_refinanciacion", sector, semilla, intensidad="fuerte")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            calidad_anterior = ej[año_anterior].balance_eur["deudas_fin_largo"] / (
                ej[año_anterior].balance_eur["deudas_fin_largo"] + ej[año_anterior].balance_eur["deudas_fin_corto"]
            )
            calidad_actual = ej[año].balance_eur["deudas_fin_largo"] / (
                ej[año].balance_eur["deudas_fin_largo"] + ej[año].balance_eur["deudas_fin_corto"]
            )
            assert calidad_actual <= calidad_anterior + 1e-9 or calidad_actual == pytest.approx(suelo, rel=1e-6)


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_refinanciacion_siempre_lleva_nota_memoria(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "riesgo_refinanciacion", sector, semilla)
        for año in (2024, 2025):
            nota = evolucion.ejercicios[año].nota_memoria
            assert nota is not None
            assert nota in NOTAS_MEMORIA_RIESGO_REFINANCIACION


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_refinanciacion_nota_memoria_reproducible(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        a = _generar(catalogo, arquetipos, "riesgo_refinanciacion", sector, semilla)
        b = _generar(catalogo, arquetipos, "riesgo_refinanciacion", sector, semilla)
        assert a.ejercicios[2024].nota_memoria == b.ejercicios[2024].nota_memoria
        assert a.ejercicios[2025].nota_memoria == b.ejercicios[2025].nota_memoria


def test_riesgo_refinanciacion_nota_memoria_varia_entre_las_5_opciones(catalogo, arquetipos):
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    notas_vistas = set()
    for codigo in codigos:
        for semilla in range(4):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="riesgo_refinanciacion", catalogo=catalogo, arquetipos=arquetipos,
            )
            notas_vistas.add(evolucion.ejercicios[2024].nota_memoria)
            notas_vistas.add(evolucion.ejercicios[2025].nota_memoria)
    assert len(notas_vistas) == len(NOTAS_MEMORIA_RIESGO_REFINANCIACION), notas_vistas


# --------------------------------------------------------------------------------------------
# Arquetipo 17: Capex elevado — activo_no_corriente al alza vía continuidad, financiado con
# deuda a largo plazo nueva.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_capex_elevado_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "capex_elevado", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_capex_elevado_activo_no_corriente_crece_mas_que_ventas(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "capex_elevado", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            crecimiento_activo = ej[año].balance_eur["activo_no_corriente"] / ej[año_anterior].balance_eur["activo_no_corriente"] - 1
            assert crecimiento_activo >= crecimiento_ventas - 1e-9


@pytest.mark.parametrize("sector", SECTORES)
def test_capex_elevado_no_toca_circulante(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "capex_elevado", sector, semilla, intensidad="moderado")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            for variable in ("existencias", "realizable", "acreedores_comerciales"):
                proporcional = ej[año_anterior].balance_eur[variable] * (1 + crecimiento_ventas)
                assert ej[año].balance_eur[variable] == pytest.approx(proporcional, rel=1e-9)


@pytest.mark.parametrize("sector", SECTORES)
def test_capex_elevado_se_financia_con_deuda_a_largo_no_con_patrimonio_neto(catalogo, arquetipos, sector):
    # El exceso de activo_no_corriente sobre lo proporcional debe reflejarse (dentro de la
    # tolerancia del plug de cuadre) en un exceso equivalente de deudas_fin_largo — no se resta
    # nada de patrimonio_neto por esta vía (a diferencia de "apalancamiento").
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "capex_elevado", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            activo_proporcional = ej[año_anterior].balance_eur["activo_no_corriente"] * (1 + crecimiento_ventas)
            exceso_activo = ej[año].balance_eur["activo_no_corriente"] - activo_proporcional
            deudas_largo_proporcional = ej[año_anterior].balance_eur["deudas_fin_largo"] * (1 + crecimiento_ventas)
            exceso_deuda_largo = ej[año].balance_eur["deudas_fin_largo"] - deudas_largo_proporcional
            if exceso_activo > 1.0:
                assert exceso_deuda_largo == pytest.approx(exceso_activo, rel=1e-6)


def test_capex_elevado_riesgo_endeudamiento_siempre_señalizado(catalogo, arquetipos):
    # Regresión del hallazgo del stress test: el arquetipo 17 no toca circulante, así que cuando
    # dispara riesgo_endeudamiento queda siempre en contencion_al_limite=True (no hay palanca de
    # circulante que amortiguar) — el mismo patrón ya establecido para 9/11/15/16. Lo que importa
    # es que el chequeo (incondicional) nunca deje pasar un caso sin señalizar. Barrido
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
                    arquetipo_id="capex_elevado", catalogo=catalogo, arquetipos=arquetipos,
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
