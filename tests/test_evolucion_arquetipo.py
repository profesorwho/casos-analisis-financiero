import pytest

from motor.catalogo import cargar_y_validar_catalogo, version_catalogo
from motor.empresa_base import SUELO_TIPO_INTERES, TECHO_TIPO_INTERES, resolver_fila_sector
from motor.evolucion_arquetipo import (
    ARQUETIPO_ID,
    AÑO_BASE,
    N_DESVIACIONES_TECHO_ENDEUDAMIENTO,
    PGC_VERSION,
    TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    EvolucionArquetipoError,
    generar_evolucion_arquetipo,
)

VENTAS_OBJETIVO_2023 = 8_000_000.0
SEMILLAS = range(5)

# Un sector industrial, uno de servicios y uno de comercio (los mismos que en empresa_base).
SECTORES = [
    pytest.param("24.1", id="industrial-siderurgia"),
    pytest.param("62", id="servicios-tic"),
    pytest.param("47.1", id="comercio-supermercados"),
]
INTENSIDADES = [pytest.param("moderado", id="moderado"), pytest.param("fuerte", id="fuerte")]


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


def _casos(catalogo, sector, intensidad):
    return [
        generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=s, intensidad=intensidad, catalogo=catalogo
        )
        for s in SEMILLAS
    ]


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_los_tres_balances_cuadran(catalogo, sector, intensidad):
    for evolucion in _casos(catalogo, sector, intensidad):
        for año, ejercicio in evolucion.ejercicios.items():
            activo = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
            pn_pasivo = (
                ejercicio.balance_eur["patrimonio_neto"]
                + ejercicio.balance_eur["pasivo_no_corriente"]
                + ejercicio.balance_eur["pasivo_corriente"]
            )
            assert abs(activo - pn_pasivo) <= 0.01, f"{año} (semilla {evolucion.semilla}): descuadre de balance"


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_patrimonio_neto_sigue_el_resultado_del_ejercicio(catalogo, sector, intensidad):
    for evolucion in _casos(catalogo, sector, intensidad):
        ej = evolucion.ejercicios
        assert ej[2024].balance_eur["patrimonio_neto"] == pytest.approx(
            ej[2023].balance_eur["patrimonio_neto"] + ej[2024].pyg_eur["resultado_ejercicio"], abs=0.01
        )
        assert ej[2025].balance_eur["patrimonio_neto"] == pytest.approx(
            ej[2024].balance_eur["patrimonio_neto"] + ej[2025].pyg_eur["resultado_ejercicio"], abs=0.01
        )


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_las_ventas_crecen_cada_año(catalogo, sector, intensidad):
    for evolucion in _casos(catalogo, sector, intensidad):
        ej = evolucion.ejercicios
        assert ej[2023].ventas < ej[2024].ventas < ej[2025].ventas


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_existencias_y_clientes_crecen_mas_que_las_ventas(catalogo, sector, intensidad):
    for evolucion in _casos(catalogo, sector, intensidad):
        ej = evolucion.ejercicios

        # >= y no > estricto: cuando el endeudamiento resultante superaría el techo de
        # plausibilidad del sector (riesgo_endeudamiento=True), la contención amortigua el
        # exceso de circulante hasta, como mucho, el crecimiento proporcional a ventas — nunca
        # por debajo de él. Ver test_contencion_de_endeudamiento para la contención en sí.
        crecimiento_ventas_2024 = ej[2024].ventas / ej[2023].ventas - 1
        crecimiento_existencias_2024 = ej[2024].balance_eur["existencias"] / ej[2023].balance_eur["existencias"] - 1
        crecimiento_clientes_2024 = ej[2024].balance_eur["realizable"] / ej[2023].balance_eur["realizable"] - 1
        assert crecimiento_existencias_2024 >= crecimiento_ventas_2024 - 1e-9
        assert crecimiento_clientes_2024 >= crecimiento_ventas_2024 - 1e-9

        crecimiento_ventas_2025 = ej[2025].ventas / ej[2024].ventas - 1
        crecimiento_existencias_2025 = ej[2025].balance_eur["existencias"] / ej[2024].balance_eur["existencias"] - 1
        crecimiento_clientes_2025 = ej[2025].balance_eur["realizable"] / ej[2024].balance_eur["realizable"] - 1
        assert crecimiento_existencias_2025 >= crecimiento_ventas_2025 - 1e-9
        assert crecimiento_clientes_2025 >= crecimiento_ventas_2025 - 1e-9

        # ... y por tanto la rotación de existencias no mejora y el plazo de cobro no se acorta,
        # respecto al propio año anterior de la empresa (no solo respecto al sector).
        assert ej[2024].rotacion_existencias <= ej[2023].rotacion_existencias + 1e-9
        assert ej[2025].rotacion_existencias <= ej[2024].rotacion_existencias + 1e-9
        assert ej[2024].cobro_dias >= ej[2023].cobro_dias - 1e-9
        assert ej[2025].cobro_dias >= ej[2024].cobro_dias - 1e-9


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_tesoreria_cae_o_deuda_corto_compensa(catalogo, sector, intensidad):
    for evolucion in _casos(catalogo, sector, intensidad):
        ej = evolucion.ejercicios
        for año_anterior, año in ((2023, 2024), (2024, 2025)):
            activo_anterior = (
                ej[año_anterior].balance_eur["activo_no_corriente"] + ej[año_anterior].balance_eur["activo_corriente"]
            )
            activo_actual = ej[año].balance_eur["activo_no_corriente"] + ej[año].balance_eur["activo_corriente"]
            disponible_relativo_anterior = ej[año_anterior].balance_eur["disponible"] / activo_anterior
            disponible_relativo_actual = ej[año].balance_eur["disponible"] / activo_actual
            tesoreria_cae = disponible_relativo_actual < disponible_relativo_anterior
            deuda_corto_sube = ej[año].balance_eur["deudas_fin_corto"] > ej[año_anterior].balance_eur["deudas_fin_corto"]
            assert tesoreria_cae or deuda_corto_sube, f"{año} (semilla {evolucion.semilla}): ni cae la caja ni sube la deuda CP"


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_el_efecto_es_mas_marcado_en_2025_que_en_2024(catalogo, sector, intensidad):
    # Solo se compara en los casos sin contención de endeudamiento: si esta amortigua 2024 o
    # 2025, deja de ser una comparación "arquetipo puro" (ver test_contencion_de_endeudamiento).
    for evolucion in _casos(catalogo, sector, intensidad):
        ej = evolucion.ejercicios
        if ej[2024].riesgo_endeudamiento or ej[2025].riesgo_endeudamiento:
            continue
        caida_relativa_2024 = 1 - ej[2024].rotacion_existencias / ej[2023].rotacion_existencias
        caida_relativa_2025 = 1 - ej[2025].rotacion_existencias / ej[2024].rotacion_existencias
        assert caida_relativa_2025 > caida_relativa_2024

        alargue_relativo_2024 = ej[2024].cobro_dias / ej[2023].cobro_dias - 1
        alargue_relativo_2025 = ej[2025].cobro_dias / ej[2024].cobro_dias - 1
        assert alargue_relativo_2025 > alargue_relativo_2024


@pytest.mark.parametrize("sector", SECTORES)
def test_intensidad_fuerte_tiene_mas_efecto_que_moderado(catalogo, sector):
    for semilla in SEMILLAS:
        moderado = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="moderado", catalogo=catalogo
        )
        fuerte = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte", catalogo=catalogo
        )

        # Estas dos se cumplen siempre: no dependen de la contención de endeudamiento (el
        # crecimiento de ventas objetivo y las ventas resultantes no se amortiguan nunca).
        assert fuerte.crecimiento_pleno_objetivo > moderado.crecimiento_pleno_objetivo
        assert fuerte.ejercicios[2025].ventas > moderado.ejercicios[2025].ventas

        # La comparación de ratios solo se hace cuando ninguno de los dos casos ha necesitado
        # contención en 2025 (si no, "fuerte" puede quedar amortiguado más que "moderado" y
        # dejar de ser una comparación limpia del arquetipo).
        if fuerte.ejercicios[2025].riesgo_endeudamiento or moderado.ejercicios[2025].riesgo_endeudamiento:
            continue

        caida_rotacion_moderado = 1 - moderado.ejercicios[2025].rotacion_existencias / moderado.ejercicios[2023].rotacion_existencias
        caida_rotacion_fuerte = 1 - fuerte.ejercicios[2025].rotacion_existencias / fuerte.ejercicios[2023].rotacion_existencias
        assert caida_rotacion_fuerte > caida_rotacion_moderado

        alargue_cobro_moderado = moderado.ejercicios[2025].cobro_dias / moderado.ejercicios[2023].cobro_dias - 1
        alargue_cobro_fuerte = fuerte.ejercicios[2025].cobro_dias / fuerte.ejercicios[2023].cobro_dias - 1
        assert alargue_cobro_fuerte > alargue_cobro_moderado


@pytest.mark.parametrize("sector", SECTORES)
def test_gastos_financieros_dependen_de_la_deuda_tomada(catalogo, sector):
    # Antes de anclar los gastos financieros a la deuda financiera media, moderado y fuerte
    # daban EXACTAMENTE la misma cobertura de gastos financieros cada año (los % de PyG se
    # sorteaban independientes del nivel de deuda). Ahora deben divergir, porque fuerte toma
    # más deuda para financiar un arquetipo más intenso.
    huellas_moderado = set()
    huellas_fuerte = set()
    for semilla in SEMILLAS:
        moderado = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="moderado", catalogo=catalogo
        )
        fuerte = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte", catalogo=catalogo
        )
        for año in (2024, 2025):
            gf_moderado = moderado.ejercicios[año].pyg_eur["gastos_financieros"]
            gf_fuerte = fuerte.ejercicios[año].pyg_eur["gastos_financieros"]
            assert gf_moderado != pytest.approx(gf_fuerte, rel=1e-9), (
                f"semilla {semilla}, {año}: gastos financieros idénticos entre moderado y fuerte"
            )
            cob_moderado = moderado.ejercicios[año].cobertura_gastos_financieros
            cob_fuerte = fuerte.ejercicios[año].cobertura_gastos_financieros
            assert cob_moderado != pytest.approx(cob_fuerte, rel=1e-9), (
                f"semilla {semilla}, {año}: cobertura de gastos financieros idéntica entre moderado y fuerte"
            )
            huellas_moderado.add(round(gf_moderado, 2))
            huellas_fuerte.add(round(gf_fuerte, 2))
    # Con 5 semillas x 2 años, si dependieran de verdad de la deuda (que varía con cada sorteo
    # de márgenes y con el crecimiento pleno objetivo de cada semilla) no deberían salir todos
    # los valores iguales entre sí tampoco.
    assert len(huellas_moderado) > 1
    assert len(huellas_fuerte) > 1


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_tipo_de_interes_implicito_es_razonable_para_el_sector(catalogo, sector, intensidad):
    fila = resolver_fila_sector(catalogo, sector, "grandes_medianas")
    huber_coste_deuda = fila["ratios.coste_deuda.huber_9y"]
    mad_coste_deuda = fila["ratios.coste_deuda.huber_scale_mad"]
    # Mismas cotas que aplica _generar_pyg_hasta_baii al sortear el tipo de interés: huber +/-
    # hasta 3 desviaciones (MAD), recortado al suelo/techo defensivo absoluto.
    cota_inferior = max(SUELO_TIPO_INTERES, huber_coste_deuda - 3 * mad_coste_deuda) - 1e-6
    cota_superior = min(TECHO_TIPO_INTERES, huber_coste_deuda + 3 * mad_coste_deuda) + 1e-6

    for evolucion in _casos(catalogo, sector, intensidad):
        anterior = evolucion.ejercicios[AÑO_BASE]
        for año in (2024, 2025):
            ej = evolucion.ejercicios[año]
            deuda_inicio = anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"]
            deuda_fin = ej.balance_eur["deudas_fin_largo"] + ej.balance_eur["deudas_fin_corto"]
            deuda_media = (deuda_inicio + deuda_fin) / 2
            tipo_implicito = ej.pyg_eur["gastos_financieros"] / deuda_media
            assert cota_inferior <= tipo_implicito <= cota_superior, (
                f"semilla {ej.año}: tipo implícito {tipo_implicito:.4f} fuera de "
                f"[{cota_inferior:.4f}, {cota_superior:.4f}] para el sector"
            )
            anterior = ej


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_contencion_de_endeudamiento_respeta_el_techo_del_sector(catalogo, sector, intensidad):
    fila = resolver_fila_sector(catalogo, sector, "grandes_medianas")
    techo_esperado = min(
        fila["ratios.endeudamiento.huber_9y"] + N_DESVIACIONES_TECHO_ENDEUDAMIENTO * fila["ratios.endeudamiento.huber_scale_mad"],
        TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    )
    for evolucion in _casos(catalogo, sector, intensidad):
        for año in (2024, 2025):
            ej = evolucion.ejercicios[año]
            if ej.riesgo_endeudamiento:
                # La contención siempre debe bajar el endeudamiento respecto a financiarlo
                # todo con deuda. Debe dejarlo en el techo de plausibilidad, EXCEPTO cuando el
                # propio motor marca contencion_al_limite=True (se agotó el margen de
                # amortiguación posible antes de llegar al techo — casi siempre porque el
                # déficit de caja ya ha llegado a cero: a partir de ahí, amortiguar más no
                # cambia ni el activo ni el pasivo, ver docstring del módulo).
                assert ej.endeudamiento_sin_contener is not None
                assert ej.endeudamiento < ej.endeudamiento_sin_contener
                assert ej.deterioro_aplicado_eur > 0.0

                # Tolerancia ligada a la convergencia del bucle de contención (converge al
                # importe de amortiguación con TOLERANCIA_CONVERGENCIA_DETERIORO_EUR=1€, no a
                # una precisión infinita), no un margen arbitrario.
                assert ej.endeudamiento <= techo_esperado + 1e-4 or ej.contencion_al_limite
            else:
                assert ej.endeudamiento_sin_contener is None
                assert ej.deterioro_aplicado_eur == 0.0


def test_contencion_de_endeudamiento_se_activa_en_algun_caso(catalogo):
    # Confirma que el mecanismo no es código muerto: para un sector con endeudamiento Huber
    # bajo (Siderurgia) y el arquetipo en fuerte, debe activarse al menos una vez en un barrido
    # de semillas razonable.
    activaciones = 0
    for semilla in range(20):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte", catalogo=catalogo
        )
        activaciones += sum(evolucion.ejercicios[año].riesgo_endeudamiento for año in (2024, 2025))
    assert activaciones > 0


def test_reproducibilidad_misma_semilla(catalogo):
    a = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=99, intensidad="moderado", catalogo=catalogo
    )
    b = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=99, intensidad="moderado", catalogo=catalogo
    )
    for año in (2023, 2024, 2025):
        assert a.ejercicios[año].balance_eur == b.ejercicios[año].balance_eur
        assert a.ejercicios[año].pyg_eur == b.ejercicios[año].pyg_eur


def test_año_base_coincide_con_empresa_base_directa(catalogo):
    from motor.empresa_base import generar_empresa_base

    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=5, intensidad="moderado", catalogo=catalogo
    )
    empresa_directa = generar_empresa_base(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=5, catalogo=catalogo
    )
    assert evolucion.ejercicios[AÑO_BASE].balance_eur == empresa_directa.balance_eur
    assert evolucion.ejercicios[AÑO_BASE].pyg_eur == empresa_directa.pyg_eur


def test_intensidad_invalida_lanza_error(catalogo):
    with pytest.raises(EvolucionArquetipoError, match="Intensidad"):
        generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="extrema", catalogo=catalogo
        )


def test_metadatos_de_trazabilidad_presentes(catalogo):
    # Sección 2.15: cada caso debe poder reconstruirse y defenderse, lo que exige guardar qué
    # arquetipo/intensidad/semilla lo generaron y contra qué versión del catálogo y del PGC.
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=3, intensidad="fuerte", catalogo=catalogo
    )
    assert evolucion.arquetipo == ARQUETIPO_ID
    assert evolucion.intensidad == "fuerte"
    assert evolucion.semilla == 3
    assert evolucion.catalogo_version == version_catalogo()
    assert evolucion.pgc_version == PGC_VERSION == "PGC RD 1514/2007"


def test_catalogo_version_es_la_del_catalogo_pasado_explicitamente(catalogo):
    # No debe depender de recargar el catálogo por defecto: tiene que venir del propio
    # DataFrame recibido, para que sea fiel a lo que realmente se usó en esa llamada.
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="moderado", catalogo=catalogo
    )
    assert evolucion.catalogo_version == catalogo.attrs["catalogo_version"]
