"""Tests de los 4 arquetipos usados como prueba de estrés del núcleo genérico (5, 9, 11, 15).

El arquetipo 1 (reimplementado sobre el mismo núcleo) tiene su propia batería de tests, más
extensa por ser el original, en tests/test_evolucion_arquetipo.py.
"""

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE, generar_evolucion_arquetipo

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


def test_margen_bruto_respeta_el_techo_de_plausibilidad_del_sector(catalogo, arquetipos):
    # Regresión del hallazgo del stress test: antes de _limitar_por_subtotal, 1.796 de 2.592
    # ejercicios evaluados del arquetipo "mejora_margen" (69%) superaban huber_9y + 3·MAD de
    # margen_bruto del sector sin ninguna señal — ver docstring del módulo. Barrido
    # representativo (27 sectores x 3 intensidades x 4 semillas = 324 casos), no los 1.296
    # completos, para mantener la suite rápida.
    import re

    from motor.empresa_base import resolver_fila_sector
    from motor.evolucion_arquetipo import N_DESVIACIONES_TECHO_PYG

    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    por_encima_sin_señal = []
    activaciones = 0
    for codigo in codigos:
        fila = resolver_fila_sector(catalogo, codigo, "grandes_medianas")
        techo_margen = fila["pyg.margen_bruto_pct.huber_9y"] + N_DESVIACIONES_TECHO_PYG * fila["pyg.margen_bruto_pct.huber_scale_mad"]
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                evolucion = generar_evolucion_arquetipo(
                    codigo,
                    "grandes_medianas",
                    VENTAS_OBJETIVO_2023,
                    semilla=semilla,
                    intensidad=intensidad,
                    arquetipo_id="mejora_margen",
                    catalogo=catalogo,
                    arquetipos=arquetipos,
                )
                for año in (2024, 2025):
                    ej = evolucion.ejercicios[año]
                    if ej.riesgo_plausibilidad_pyg:
                        activaciones += 1
                    if ej.pyg_pct["margen_bruto"] > techo_margen + 1e-6 and not ej.riesgo_plausibilidad_pyg:
                        por_encima_sin_señal.append((codigo, intensidad, semilla, año, ej.pyg_pct["margen_bruto"], techo_margen))
    assert activaciones > 0, "la muestra no incluyó ningún caso donde se activara la contención: ajustar el barrido"
    assert not por_encima_sin_señal, f"{len(por_encima_sin_señal)} casos sin señalizar: {por_encima_sin_señal[:10]}"


def test_margen_bruto_nunca_supera_el_techo_del_sector(catalogo, arquetipos):
    from motor.empresa_base import resolver_fila_sector
    from motor.evolucion_arquetipo import N_DESVIACIONES_TECHO_PYG

    for sector in ("24.1", "62", "47.1"):
        fila = resolver_fila_sector(catalogo, sector, "grandes_medianas")
        techo_margen = fila["pyg.margen_bruto_pct.huber_9y"] + N_DESVIACIONES_TECHO_PYG * fila["pyg.margen_bruto_pct.huber_scale_mad"]
        for semilla in SEMILLAS:
            evolucion = _generar(catalogo, arquetipos, "mejora_margen", sector, semilla)
            for ejercicio in evolucion.ejercicios.values():
                assert ejercicio.pyg_pct["margen_bruto"] <= techo_margen + 1e-6


# --------------------------------------------------------------------------------------------
# Segundo lote: arquetipos 3, 4, 6, 8, 10 (sección 2.24). 3 y 6 reutilizan el mecanismo de
# masa_circulante sin ningún código nuevo; 4 ejercita la generalización de NOF con signo
# (existencias/realizable ACTIVO vs. acreedores_comerciales PASIVO); 8 es un mecanismo nuevo
# (reclasificacion_deuda); 10 ejercita el techo de plausibilidad de PyG de "base dinámica"
# (gastos_personal -> baii, a diferencia de margen_bruto que es "100 - primitiva").
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_aumento_nof_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "aumento_nof", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_aumento_clientes_solo_toca_realizable(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "aumento_clientes", sector, semilla, intensidad="moderado")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            for variable in ("existencias", "acreedores_comerciales"):
                proporcional = ej[año_anterior].balance_eur[variable] * (1 + crecimiento_ventas)
                assert ej[año].balance_eur[variable] == pytest.approx(proporcional, rel=1e-9)
            realizable_proporcional = ej[año_anterior].balance_eur["realizable"] * (1 + crecimiento_ventas)
            assert ej[año].balance_eur["realizable"] >= realizable_proporcional - 1e-6


@pytest.mark.parametrize("sector", SECTORES)
def test_deterioro_ciclo_caja_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "deterioro_ciclo_caja", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_deterioro_ciclo_caja_realizable_sube_y_acreedores_baja(catalogo, arquetipos, sector):
    # Huella opuesta simultánea: realizable (activo) sube más que ventas, acreedores_comerciales
    # (pasivo) sube menos — las dos presionan la NOF en la misma dirección (más déficit de caja).
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "deterioro_ciclo_caja", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            realizable_proporcional = ej[año_anterior].balance_eur["realizable"] * (1 + crecimiento_ventas)
            acreedores_proporcional = ej[año_anterior].balance_eur["acreedores_comerciales"] * (1 + crecimiento_ventas)
            assert ej[año].balance_eur["realizable"] >= realizable_proporcional - 1e-6
            assert ej[año].balance_eur["acreedores_comerciales"] <= acreedores_proporcional + 1e-6


@pytest.mark.parametrize("sector", SECTORES)
def test_refinanciacion_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "refinanciacion", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_refinanciacion_no_altera_la_deuda_financiera_total(catalogo, arquetipos, sector):
    # Reclasifica largo/corto plazo sin cambiar el total: una renegociación cambia el
    # vencimiento, no el importe (ver EfectoReclasificacionDeuda en motor/arquetipos.py).
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "refinanciacion", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            crecimiento_ventas = ej[año].ventas / ej[año_anterior].ventas - 1
            deuda_total_proporcional = (
                ej[año_anterior].balance_eur["deudas_fin_largo"] + ej[año_anterior].balance_eur["deudas_fin_corto"]
            ) * (1 + crecimiento_ventas)
            deuda_total_real = ej[año].balance_eur["deudas_fin_largo"] + ej[año].balance_eur["deudas_fin_corto"]
            assert deuda_total_real == pytest.approx(deuda_total_proporcional, abs=1.0)


@pytest.mark.parametrize("sector", SECTORES)
def test_refinanciacion_sube_la_proporcion_a_largo_plazo(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "refinanciacion", sector, semilla, intensidad="fuerte")
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            calidad_anterior = ej[año_anterior].balance_eur["deudas_fin_largo"] / (
                ej[año_anterior].balance_eur["deudas_fin_largo"] + ej[año_anterior].balance_eur["deudas_fin_corto"]
            )
            calidad_actual = ej[año].balance_eur["deudas_fin_largo"] / (
                ej[año].balance_eur["deudas_fin_largo"] + ej[año].balance_eur["deudas_fin_corto"]
            )
            assert calidad_actual >= calidad_anterior - 1e-9


@pytest.mark.parametrize("sector", SECTORES)
def test_mejora_ebitda_balances_cuadran(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "mejora_ebitda", sector, semilla)
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"semilla {semilla}, año {ejercicio.año}: descuadre"


@pytest.mark.parametrize("sector", SECTORES)
def test_mejora_ebitda_gastos_personal_baja_salvo_limite_por_ruido_de_base(catalogo, arquetipos, sector):
    # A diferencia de mejora_margen (base fija, ver test_mejora_margen_...), aquí NO se puede
    # exigir que gastos_personal_pct baje siempre: la base de baii (valor_añadido, amortizaciones,
    # resultado_extraordinario) se sortea de nuevo cada año, independiente del arquetipo. La
    # contención (_limitar_gastos_personal_por_baii) amortigua la intensidad del propio arquetipo
    # antes de invertir su sentido — solo lo invierte (sube gastos_personal por encima del año
    # anterior) cuando ni siquiera con intensidad cero bastaría, es decir, cuando el desbordamiento
    # viene del ruido de la base ese año, no del arquetipo. Eso es exactamente lo que marca
    # `pyg_contencion_al_limite`. Cuantificado en la prueba de estrés completa (ver
    # test_mejora_ebitda_las_subidas_de_gastos_personal_siempre_coinciden_con_el_limite_por_ruido):
    # de 316 activaciones, 173 (54,7%) se resuelven amortiguando sin invertir el sentido, 143
    # (45,3%) sí lo invierten — y las 143 coinciden EXACTAMENTE con pyg_contencion_al_limite=True.
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "mejora_ebitda", sector, semilla)
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            sube = ej[año].pyg_pct["gastos_personal"] > ej[año_anterior].pyg_pct["gastos_personal"] + 1e-9
            assert sube == ej[año].pyg_contencion_al_limite, (
                f"sector {sector}, semilla {semilla}, año {año}: sube={sube} pero "
                f"pyg_contencion_al_limite={ej[año].pyg_contencion_al_limite}"
            )
        assert ej[2024].modos["pyg.gastos_personal"] == "arquetipo"
        assert ej[2025].modos["pyg.gastos_personal"] == "arquetipo"


def test_mejora_ebitda_baii_respeta_el_techo_de_plausibilidad_del_sector(catalogo, arquetipos):
    # Regresión del hallazgo del stress test: sin _limitar_gastos_personal_por_baii, 316 de 648
    # ejercicios evaluados (48.8%) superaban huber_9y + 3·MAD de baii_pct del sector sin ninguna
    # señal. Barrido representativo (27 sectores x 3 intensidades x 4 semillas = 324 casos).
    import re

    from motor.empresa_base import resolver_fila_sector
    from motor.evolucion_arquetipo import N_DESVIACIONES_TECHO_PYG

    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    por_encima_sin_señal = []
    activaciones = 0
    for codigo in codigos:
        fila = resolver_fila_sector(catalogo, codigo, "grandes_medianas")
        techo_baii = fila["pyg.baii_pct.huber_9y"] + N_DESVIACIONES_TECHO_PYG * fila["pyg.baii_pct.huber_scale_mad"]
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                evolucion = generar_evolucion_arquetipo(
                    codigo,
                    "grandes_medianas",
                    VENTAS_OBJETIVO_2023,
                    semilla=semilla,
                    intensidad=intensidad,
                    arquetipo_id="mejora_ebitda",
                    catalogo=catalogo,
                    arquetipos=arquetipos,
                )
                for año in (2024, 2025):
                    ej = evolucion.ejercicios[año]
                    if ej.riesgo_plausibilidad_pyg:
                        activaciones += 1
                    if ej.pyg_pct["baii"] > techo_baii + 1e-6 and not ej.riesgo_plausibilidad_pyg:
                        por_encima_sin_señal.append((codigo, intensidad, semilla, año, ej.pyg_pct["baii"], techo_baii))
    assert activaciones > 0, "la muestra no incluyó ningún caso donde se activara la contención: ajustar el barrido"
    assert not por_encima_sin_señal, f"{len(por_encima_sin_señal)} casos sin señalizar: {por_encima_sin_señal[:10]}"


def test_mejora_ebitda_las_subidas_de_gastos_personal_siempre_coinciden_con_el_limite_por_ruido(catalogo, arquetipos):
    # Regresión del hallazgo del stress test (ver docstring del módulo, sección "base
    # dinámica"): a diferencia de margen_bruto, la base de baii se sortea de nuevo cada año, así
    # que el objetivo de continuidad de gastos_personal a veces requiere subirlo (en vez de
    # bajarlo) para no perforar el techo — pero SOLO cuando amortiguar la intensidad del propio
    # arquetipo a cero ya no basta (`pyg_contencion_al_limite=True`). De 648 transiciones
    # evaluadas (27 sectores x 3 intensidades x 4 semillas x 2 años), 143 (22,1%) suben — las 143
    # coinciden EXACTAMENTE con pyg_contencion_al_limite=True, ni una menos ni una más: nunca una
    # subida sin que amortiguar la intensidad fuera insuficiente, y nunca pyg_contencion_al_limite
    # activado sin que realmente suba.
    import re

    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    discrepancias = []
    subidas_totales = 0
    for codigo in codigos:
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                evolucion = generar_evolucion_arquetipo(
                    codigo,
                    "grandes_medianas",
                    VENTAS_OBJETIVO_2023,
                    semilla=semilla,
                    intensidad=intensidad,
                    arquetipo_id="mejora_ebitda",
                    catalogo=catalogo,
                    arquetipos=arquetipos,
                )
                ej = evolucion.ejercicios
                for año_anterior, año in ((2023, 2024), (2024, 2025)):
                    sube = ej[año].pyg_pct["gastos_personal"] > ej[año_anterior].pyg_pct["gastos_personal"] + 1e-9
                    if sube:
                        subidas_totales += 1
                    if sube != ej[año].pyg_contencion_al_limite:
                        discrepancias.append((codigo, intensidad, semilla, año, sube, ej[año].pyg_contencion_al_limite))
    assert subidas_totales > 0, "la muestra no incluyó ningún caso de subida: ajustar el barrido"
    assert not discrepancias, f"{len(discrepancias)} discrepancias entre subida y pyg_contencion_al_limite: {discrepancias[:10]}"


def test_mejora_ebitda_nota_memoria_solo_aparece_con_pyg_contencion_al_limite(catalogo, arquetipos):
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "mejora_ebitda", "24.1", semilla)
        for ejercicio in evolucion.ejercicios.values():
            if ejercicio.pyg_contencion_al_limite:
                assert ejercicio.nota_memoria is not None
                assert ejercicio.nota_memoria in NOTAS_MEMORIA_GASTOS_PERSONAL_AL_LIMITE
            else:
                assert ejercicio.nota_memoria is None


def test_mejora_ebitda_nota_memoria_es_reproducible_con_la_misma_semilla(catalogo, arquetipos):
    # Misma semilla (y mismo resto de parámetros) -> siempre la misma redacción.
    for semilla in SEMILLAS:
        primera = _generar(catalogo, arquetipos, "mejora_ebitda", "24.1", semilla)
        segunda = _generar(catalogo, arquetipos, "mejora_ebitda", "24.1", semilla)
        for año in (2024, 2025):
            assert primera.ejercicios[año].nota_memoria == segunda.ejercicios[año].nota_memoria


def test_mejora_ebitda_nota_memoria_varia_entre_las_5_opciones(catalogo, arquetipos):
    # A lo largo de los 143 casos con pyg_contencion_al_limite=True (barrido representativo: 27
    # sectores x 3 intensidades x 4 semillas x 2 años = 648 transiciones), deben aparecer varias
    # de las 5 redacciones alternativas, no una única repetida siempre.
    import re

    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    notas_vistas = set()
    casos_con_nota = 0
    for codigo in codigos:
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                evolucion = generar_evolucion_arquetipo(
                    codigo,
                    "grandes_medianas",
                    VENTAS_OBJETIVO_2023,
                    semilla=semilla,
                    intensidad=intensidad,
                    arquetipo_id="mejora_ebitda",
                    catalogo=catalogo,
                    arquetipos=arquetipos,
                )
                for año in (2024, 2025):
                    ej = evolucion.ejercicios[año]
                    if ej.pyg_contencion_al_limite:
                        casos_con_nota += 1
                        notas_vistas.add(ej.nota_memoria)
    assert casos_con_nota > 0, "la muestra no incluyó ningún caso con pyg_contencion_al_limite: ajustar el barrido"
    assert len(notas_vistas) > 1, f"solo apareció una redacción en {casos_con_nota} casos: {notas_vistas}"


def test_margen_bruto_sin_contener_queda_registrado(catalogo, arquetipos):
    # Cuando se activa la contención, el valor previo (sin topar) debe quedar trazado, igual
    # que endeudamiento_sin_contener.
    encontrado_alguno = False
    for semilla in SEMILLAS:
        evolucion = _generar(catalogo, arquetipos, "mejora_margen", "24.1", semilla, intensidad="fuerte")
        for ejercicio in evolucion.ejercicios.values():
            if ejercicio.riesgo_plausibilidad_pyg:
                encontrado_alguno = True
                assert "margen_bruto" in ejercicio.pyg_subtotales_sin_contener
                assert ejercicio.pyg_subtotales_sin_contener["margen_bruto"] > ejercicio.pyg_pct["margen_bruto"]
    assert encontrado_alguno, "ninguna de las semillas activó la contención: ajustar el caso de prueba"
