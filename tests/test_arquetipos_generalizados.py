"""Tests de los 4 arquetipos usados como prueba de estrés del núcleo genérico (5, 9, 11, 15).

El arquetipo 1 (reimplementado sobre el mismo núcleo) tiene su propia batería de tests, más
extensa por ser el original, en tests/test_evolucion_arquetipo.py.
"""

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import generar_evolucion_arquetipo

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


# --------------------------------------------------------------------------------------------
# Arquetipo 5: Exceso de stock — el caso base, una sola variable (masa_circulante).
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_exceso_stock_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "exceso_stock", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_exceso_stock_solo_toca_existencias(catalogo, arquetipos, sector):
    # A diferencia del arquetipo 1, este NO debe tocar "realizable": tiene que quedarse
    # exactamente en su crecimiento proporcional a ventas cada año.
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "exceso_stock", sector, semilla, intensidad="moderado")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            realizable_proporcional = ej[año_anterior].balance_eur["realizable"] * (1 + crecimiento_ventas)
            assert ej[año].balance_eur["realizable"] == pytest.approx(realizable_proporcional, rel=1e-9)


@pytest.mark.parametrize("sector", SECTORES)
def test_exceso_stock_existencias_crecen_mas_que_ventas_y_rotacion_empeora(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "exceso_stock", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            crecimiento_existencias = ej[año].balance_eur["existencias"] / ej[año_anterior].balance_eur["existencias"] - 1
            assert crecimiento_existencias >= crecimiento_ventas - 1e-9
            assert ej[año].rotacion_existencias <= ej[año_anterior].rotacion_existencias + 1e-9


# --------------------------------------------------------------------------------------------
# Arquetipo 11: Mejora de margen — toca la PyG, no el balance de circulante.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_mejora_margen_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "mejora_margen", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_mejora_margen_no_toca_el_circulante(catalogo, arquetipos, sector):
    # Ni existencias ni clientes se desvían: el efecto es puramente de PyG.
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "mejora_margen", sector, semilla, intensidad="moderado")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            for variable in ("existencias", "realizable"):
                proporcional = ej[año_anterior].balance_eur[variable] * (1 + crecimiento_ventas)
                assert ej[año].balance_eur[variable] == pytest.approx(proporcional, rel=1e-9)


@pytest.mark.parametrize("sector", SECTORES)
def test_mejora_margen_consumos_bajan_y_margen_bruto_sube(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "mejora_margen", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            assert ej[año].pyg_pct["consumos_explotacion"] <= ej[año_anterior].pyg_pct["consumos_explotacion"] + 1e-9
            assert ej[año].pyg_pct["margen_bruto"] >= ej[año_anterior].pyg_pct["margen_bruto"] - 1e-9
        # El efecto se registra con modo "arquetipo", no "tipico"/"atipico" (no es ruido).
        assert ej[2024].modos["pyg.consumos_explotacion"] == "arquetipo"
        assert ej[2025].modos["pyg.consumos_explotacion"] == "arquetipo"


# --------------------------------------------------------------------------------------------
# Arquetipo 9: Apalancamiento — deuda y PN relativo; interactúa con el enlace deuda-interés y
# la contención de endeudamiento.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_apalancamiento_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "apalancamiento", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_apalancamiento_no_toca_el_circulante(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "apalancamiento", sector, semilla, intensidad="moderado")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            for variable in ("existencias", "realizable"):
                proporcional = ej[año_anterior].balance_eur[variable] * (1 + crecimiento_ventas)
                assert ej[año].balance_eur[variable] == pytest.approx(proporcional, rel=1e-9)


@pytest.mark.parametrize("sector", SECTORES)
def test_apalancamiento_sube_deuda_a_largo(catalogo, arquetipos, sector):
    # No se comprueba que el endeudamiento sea monótono creciente año a año: ver docstring del
    # módulo ("espiral de deuda") — un año sin deuda nueva (apalancamiento_extra_eur=0) puede
    # incluso bajar ligeramente respecto al anterior si este había quedado por encima del techo
    # por el residuo de interés, y el nuevo objetivo (topado al techo) parte de un valor menor.
    huellas_extra = set()
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "apalancamiento", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            if ej[año].apalancamiento_extra_eur > 0:
                # Deudas a largo sube más que lo proporcional a ventas: el extra es la huella
                # directa del efecto (no un residuo del cuadre general).
                crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
                deudas_largo_proporcional = ej[año_anterior].balance_eur["deudas_fin_largo"] * (1 + crecimiento_ventas)
                assert ej[año].balance_eur["deudas_fin_largo"] == pytest.approx(
                    deudas_largo_proporcional + ej[año].apalancamiento_extra_eur, abs=1.0
                )
            huellas_extra.add(round(ej[año].apalancamiento_extra_eur, 2))
    # Con 8 semillas x 2 años, el efecto debe activarse (extra > 0) al menos alguna vez.
    assert any(v > 0 for v in huellas_extra)


@pytest.mark.parametrize("sector", SECTORES)
def test_apalancamiento_topa_la_deuda_nueva_al_techo_del_sector(catalogo, arquetipos, sector):
    # El techo de plausibilidad limita cuánta deuda NUEVA añade el efecto CADA año (salvo el
    # residuo habitual de interés de segundo orden, absorbido por el plug de cuadre — puede ser
    # de varios puntos porcentuales si la deuda nueva es grande, no solo una fracción de euro).
    # NO corrige que la deuda ya acumulada siga devengando interés en años siguientes: por eso
    # solo se comprueba en los años en los que el efecto añade deuda nueva de verdad
    # (apalancamiento_extra_eur > 0), no en todos — ver docstring del módulo, "espiral de deuda".
    from motor.empresa_base import resolver_fila_sector
    from motor.evolucion_arquetipo import N_DESVIACIONES_TECHO_ENDEUDAMIENTO, TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO

    fila = resolver_fila_sector(catalogo, sector, "grandes_medianas")
    techo = min(
        fila["ratios.endeudamiento.huber_9y"] + N_DESVIACIONES_TECHO_ENDEUDAMIENTO * fila["ratios.endeudamiento.huber_scale_mad"],
        TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    )
    comprobados = 0
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "apalancamiento", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            if ejercicio.apalancamiento_extra_eur > 0:
                assert ejercicio.endeudamiento <= techo + 0.05
                comprobados += 1
    assert comprobados > 0, "el efecto no llegó a activarse en ningún ejercicio de esta muestra"


@pytest.mark.parametrize("sector", SECTORES)
def test_apalancamiento_sube_gastos_financieros(catalogo, arquetipos, sector):
    # Comprobación directa de que el enlace deuda-interés reacciona al efecto: cuando hay
    # deuda extra por apalancamiento, la deuda financiera media es mayor que la que habría sin
    # el efecto (proporcional), así que los gastos financieros también deben serlo.
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "apalancamiento", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            if ej[año].apalancamiento_extra_eur > 1000:
                crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
                deudas_corto_proporcional = ej[año_anterior].balance_eur["deudas_fin_corto"] * (1 + crecimiento_ventas)
                deudas_largo_proporcional = ej[año_anterior].balance_eur["deudas_fin_largo"] * (1 + crecimiento_ventas)
                deuda_fin_proporcional = deudas_corto_proporcional + deudas_largo_proporcional
                deuda_fin_real = ej[año].balance_eur["deudas_fin_largo"] + ej[año].balance_eur["deudas_fin_corto"]
                assert deuda_fin_real > deuda_fin_proporcional


# --------------------------------------------------------------------------------------------
# Arquetipo 15: Riesgo de liquidez pese a beneficio — tesorería a la baja, resultado normal.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_liquidez_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "riesgo_liquidez_pese_beneficio", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_liquidez_no_toca_el_circulante_ni_la_pyg(catalogo, arquetipos, sector):
    # El efecto es puramente sobre disponible: existencias/realizable proporcionales, y la PyG
    # sigue su cascada normal (no hay primitivas forzadas) — es la divergencia "beneficio sano,
    # caja tensa" de la huella del arquetipo.
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "riesgo_liquidez_pese_beneficio", sector, semilla, intensidad="moderado")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            for variable in ("existencias", "realizable"):
                proporcional = ej[año_anterior].balance_eur[variable] * (1 + crecimiento_ventas)
                assert ej[año].balance_eur[variable] == pytest.approx(proporcional, rel=1e-9)
            for modo in ej[año].modos.values():
                assert modo in ("tipico", "atipico")  # ningún "arquetipo": no hay primitivas forzadas


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_liquidez_tesoreria_cae_o_deuda_corto_compensa(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "riesgo_liquidez_pese_beneficio", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            activo_anterior = ej[año_anterior].balance_eur["activo_no_corriente"] + ej[año_anterior].balance_eur["activo_corriente"]
            activo_actual = ej[año].balance_eur["activo_no_corriente"] + ej[año].balance_eur["activo_corriente"]
            disponible_relativo_anterior = ej[año_anterior].balance_eur["disponible"] / activo_anterior
            disponible_relativo_actual = ej[año].balance_eur["disponible"] / activo_actual
            tesoreria_cae = disponible_relativo_actual < disponible_relativo_anterior
            deuda_corto_sube = ej[año].balance_eur["deudas_fin_corto"] > ej[año_anterior].balance_eur["deudas_fin_corto"]
            assert tesoreria_cae or deuda_corto_sube, f"semilla {semilla}, {año}: ni cae la caja ni sube la deuda CP"


@pytest.mark.parametrize("sector", SECTORES)
def test_riesgo_liquidez_el_resultado_suele_ser_positivo(catalogo, arquetipos, sector):
    # "Beneficio sano pese a la tensión de caja": no se garantiza matemáticamente (la PyG sigue
    # siendo ruido normal de sector), pero para la mayoría de semillas debería salir positivo
    # si el sector en sí es saneado (huber de margen positivo) — comprobación de sanidad, no
    # una propiedad estructural estricta.
    positivos = 0
    total = 0
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "riesgo_liquidez_pese_beneficio", sector, semilla, intensidad="moderado")
        for año in (2024, 2025):
            total += 1
            if evolucion.ejercicios[año].pyg_eur["resultado_ejercicio"] > 0:
                positivos += 1
    assert positivos / total >= 0.5


# --------------------------------------------------------------------------------------------
# Estrés cruzado: los 5 arquetipos implementados, muchos sectores y semillas, sin excepciones,
# descuadres ni valores negativos donde no deban darse.
# --------------------------------------------------------------------------------------------


def test_estres_sin_excepciones_ni_descuadres(catalogo, arquetipos):
    sectores_amplios = ["24.1", "62", "47.1", "29", "20.1", "68", "19"]
    problemas = []
    for arquetipo_id in arquetipos:
        for sector in sectores_amplios:
            for intensidad in ("leve", "moderado", "fuerte"):
                for semilla in range(6):
                    evolucion = _generar(catalogo, arquetipos, arquetipo_id, sector, semilla, intensidad)
                    for ejercicio in evolucion.ejercicios.values():
                        if not _cuadra(ejercicio):
                            problemas.append((arquetipo_id, sector, intensidad, semilla, ejercicio.año, "descuadre"))
                        if ejercicio.pyg_eur["gastos_financieros"] < 0:
                            problemas.append((arquetipo_id, sector, intensidad, semilla, ejercicio.año, "gastos_fin<0"))
                        for nombre, valor in ejercicio.balance_eur.items():
                            # patrimonio_neto puede legítimamente ir a negativo en casos
                            # extremos de apalancamiento + mal año operativo (ver docstring del
                            # módulo) — no se trata como valor absurdo, a diferencia del resto
                            # de partidas (existencias, deudas, etc.), que nunca deben serlo.
                            if nombre != "patrimonio_neto" and valor < -0.01:
                                problemas.append((arquetipo_id, sector, intensidad, semilla, ejercicio.año, f"{nombre}<0"))
    assert not problemas, f"{len(problemas)} problemas, primeros 10: {problemas[:10]}"


def test_espiral_de_deuda_de_apalancamiento_siempre_queda_señalizada(catalogo, arquetipos):
    # Regresión del hallazgo del stress test: cuando la deuda acumulada de un año erosiona el
    # PN del siguiente vía intereses (sin que se añada deuda nueva ese año), el chequeo de
    # plausibilidad de endeudamiento tiene que detectarlo igualmente — no solo cuando hay
    # déficit de NOF o deuda nueva de apalancamiento ESE año concreto. Ver docstring del módulo,
    # sección "espiral de deuda". Barrido representativo (27 sectores x 3 intensidades x 4
    # semillas = 324 casos), no los 1.296 completos, para mantener la suite rápida.
    import re

    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    umbral = 0.15
    sin_detectar = []
    total_bajo_umbral = 0
    for codigo in codigos:
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                evolucion = generar_evolucion_arquetipo(
                    codigo,
                    "grandes_medianas",
                    VENTAS_OBJETIVO_2023,
                    semilla=semilla,
                    intensidad=intensidad,
                    arquetipo_id="apalancamiento",
                    catalogo=catalogo,
                    arquetipos=arquetipos,
                )
                ej2023, ej2025 = evolucion.ejercicios[2023], evolucion.ejercicios[2025]
                activo2023 = ej2023.balance_eur["activo_no_corriente"] + ej2023.balance_eur["activo_corriente"]
                activo2025 = ej2025.balance_eur["activo_no_corriente"] + ej2025.balance_eur["activo_corriente"]
                pn_activo_2023 = ej2023.balance_eur["patrimonio_neto"] / activo2023
                pn_activo_2025 = ej2025.balance_eur["patrimonio_neto"] / activo2025
                if pn_activo_2023 >= umbral and pn_activo_2025 < umbral:
                    total_bajo_umbral += 1
                    detectado = ej2025.riesgo_endeudamiento or evolucion.ejercicios[2024].riesgo_endeudamiento
                    if not detectado:
                        sin_detectar.append((codigo, intensidad, semilla, pn_activo_2025))
    assert total_bajo_umbral > 0, "la muestra no incluyó ningún caso de espiral de deuda: ajustar el barrido"
    assert not sin_detectar, f"{len(sin_detectar)} casos de espiral de deuda sin señalizar: {sin_detectar}"
