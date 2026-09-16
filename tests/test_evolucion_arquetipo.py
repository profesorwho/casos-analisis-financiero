import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo, version_catalogo
from motor.empresa_base import (
    DISPERSION_TIPO_INTERES_PP,
    PRIMA_RIESGO_POR_CATEGORIA,
    REFERENCIA_EURIBOR_12M_POR_AÑO,
    SUELO_TIPO_INTERES,
    TECHO_TIPO_INTERES,
    categoria_de_sector,
    resolver_fila_sector,
)
from motor.evolucion_arquetipo import (
    AÑO_BASE,
    DIAS_AÑO,
    N_DESVIACIONES_TECHO_ENDEUDAMIENTO,
    PGC_VERSION,
    TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    EvolucionArquetipoError,
    generar_evolucion_arquetipo,
)

# Este archivo prueba específicamente el arquetipo 1 ("Crecimiento con destrucción de caja")
# sobre el núcleo genérico. Los arquetipos 5/9/11/15 tienen su propio archivo:
# tests/test_arquetipos_generalizados.py.
ARQUETIPO_1 = "crecimiento_destruccion_caja"

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


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _generar(catalogo, arquetipos, sector, semilla, intensidad, ventas=VENTAS_OBJETIVO_2023):
    return generar_evolucion_arquetipo(
        sector,
        "grandes_medianas",
        ventas,
        semilla=semilla,
        intensidad=intensidad,
        arquetipo_id=ARQUETIPO_1,
        catalogo=catalogo,
        arquetipos=arquetipos,
    )


def _casos(catalogo, arquetipos, sector, intensidad):
    return [_generar(catalogo, arquetipos, sector, s, intensidad) for s in SEMILLAS]


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_los_tres_balances_cuadran(catalogo, arquetipos, sector, intensidad):
    for evolucion in _casos(catalogo, arquetipos, sector, intensidad):
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
def test_patrimonio_neto_sigue_el_resultado_del_ejercicio(catalogo, arquetipos, sector, intensidad):
    """El patrimonio neto crece con el resultado del ejercicio MÁS el movimiento neto de las dos
    líneas de PN de grupo89 (ajustes por cambio de valor, subvenciones — ver
    motor/coberturas_subvenciones.py): 0 en los casos sin cobertura/subvención, pero no siempre
    (la subvención tiene una probabilidad de fondo incluso sin arquetipo, ver
    PROPENSION_SUBVENCION_BASELINE_POR_CATEGORIA) — no se puede asumir 0 a priori para
    cualquier sector/semilla — MENOS el payout de dividendos (#79-#80, transversal, activo en
    cualquier caso independientemente del arquetipo — arquetipo 1 no genera `apalancamiento_
    extra_eur`, así que no hace falta restarlo aquí, pero el payout sí aplica siempre)."""
    for evolucion in _casos(catalogo, arquetipos, sector, intensidad):
        ej = evolucion.ejercicios
        delta_grupo89_2024 = (ej[2024].ajustes_cambio_valor_pn_eur - ej[2023].ajustes_cambio_valor_pn_eur) + (
            ej[2024].subvenciones_pn_eur - ej[2023].subvenciones_pn_eur
        )
        delta_grupo89_2025 = (ej[2025].ajustes_cambio_valor_pn_eur - ej[2024].ajustes_cambio_valor_pn_eur) + (
            ej[2025].subvenciones_pn_eur - ej[2024].subvenciones_pn_eur
        )
        assert ej[2024].balance_eur["patrimonio_neto"] == pytest.approx(
            ej[2023].balance_eur["patrimonio_neto"]
            + ej[2024].pyg_eur["resultado_ejercicio"]
            + delta_grupo89_2024
            - ej[2024].payout_dividendos_eur,
            abs=0.01,
        )
        assert ej[2025].balance_eur["patrimonio_neto"] == pytest.approx(
            ej[2024].balance_eur["patrimonio_neto"]
            + ej[2025].pyg_eur["resultado_ejercicio"]
            + delta_grupo89_2025
            - ej[2025].payout_dividendos_eur,
            abs=0.01,
        )


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_las_ventas_crecen_cada_año(catalogo, arquetipos, sector, intensidad):
    for evolucion in _casos(catalogo, arquetipos, sector, intensidad):
        ej = evolucion.ejercicios
        assert ej[2023].ventas < ej[2024].ventas < ej[2025].ventas


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_existencias_y_clientes_crecen_mas_que_las_ventas(catalogo, arquetipos, sector, intensidad):
    for evolucion in _casos(catalogo, arquetipos, sector, intensidad):
        ej = evolucion.ejercicios

        # >= y no > estricto: cuando el endeudamiento resultante superaría el techo de
        # plausibilidad del sector (riesgo_endeudamiento=True), la contención amortigua el
        # exceso de circulante hasta, como mucho, el crecimiento proporcional a ventas — nunca
        # por debajo de él. Ver test_contencion_de_endeudamiento para la contención en sí.
        #
        # "Clientes" (realizable) se reconstruye BRUTO (sumando de vuelta `insolvencia_
        # deduccion_realizable_eur`, ver motor/insolvencias.py) antes de comparar: el deterioro
        # de insolvencia de clientes tiene probabilidad de fondo INDEPENDIENTE de cualquier
        # arquetipo, así que puede reducir "realizable" pese a que este arquetipo lo empuje al
        # alza — esta comprobación es sobre la huella DEL ARQUETIPO, no sobre el balance final ya
        # neto de insolvencia.
        realizable_bruto_2023 = ej[2023].balance_eur["realizable"] + ej[2023].insolvencia_deduccion_realizable_eur
        realizable_bruto_2024 = ej[2024].balance_eur["realizable"] + ej[2024].insolvencia_deduccion_realizable_eur
        realizable_bruto_2025 = ej[2025].balance_eur["realizable"] + ej[2025].insolvencia_deduccion_realizable_eur

        crecimiento_ventas_2024 = ej[2024].ventas / ej[2023].ventas - 1
        crecimiento_existencias_2024 = ej[2024].balance_eur["existencias"] / ej[2023].balance_eur["existencias"] - 1
        crecimiento_clientes_2024 = realizable_bruto_2024 / realizable_bruto_2023 - 1
        assert crecimiento_existencias_2024 >= crecimiento_ventas_2024 - 1e-9
        assert crecimiento_clientes_2024 >= crecimiento_ventas_2024 - 1e-9

        crecimiento_ventas_2025 = ej[2025].ventas / ej[2024].ventas - 1
        crecimiento_existencias_2025 = ej[2025].balance_eur["existencias"] / ej[2024].balance_eur["existencias"] - 1
        crecimiento_clientes_2025 = realizable_bruto_2025 / realizable_bruto_2024 - 1
        assert crecimiento_existencias_2025 >= crecimiento_ventas_2025 - 1e-9
        assert crecimiento_clientes_2025 >= crecimiento_ventas_2025 - 1e-9

        # ... y por tanto la rotación de existencias no mejora, respecto al propio año anterior
        # de la empresa (no solo respecto al sector). `cobro_dias` se reconstruye BRUTO (mismo
        # motivo que "realizable" arriba: `EjercicioEmpresa.cobro_dias` se deriva de "realizable"
        # YA neto de insolvencia, que el deterioro puede acortar pese a la huella del arquetipo).
        assert ej[2024].rotacion_existencias <= ej[2023].rotacion_existencias + 1e-9
        assert ej[2025].rotacion_existencias <= ej[2024].rotacion_existencias + 1e-9
        cobro_dias_bruto_2023 = realizable_bruto_2023 / ej[2023].ventas * DIAS_AÑO
        cobro_dias_bruto_2024 = realizable_bruto_2024 / ej[2024].ventas * DIAS_AÑO
        cobro_dias_bruto_2025 = realizable_bruto_2025 / ej[2025].ventas * DIAS_AÑO
        assert cobro_dias_bruto_2024 >= cobro_dias_bruto_2023 - 1e-9
        assert cobro_dias_bruto_2025 >= cobro_dias_bruto_2024 - 1e-9


@pytest.mark.parametrize("sector", SECTORES)
@pytest.mark.parametrize("intensidad", INTENSIDADES)
def test_tesoreria_cae_o_deuda_corto_compensa(catalogo, arquetipos, sector, intensidad):
    for evolucion in _casos(catalogo, arquetipos, sector, intensidad):
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
def test_el_efecto_es_mas_marcado_en_2025_que_en_2024(catalogo, arquetipos, sector, intensidad):
    # Solo se compara en los casos sin contención de endeudamiento: si esta amortigua 2024 o
    # 2025, deja de ser una comparación "arquetipo puro" (ver test_contencion_de_endeudamiento).
    for evolucion in _casos(catalogo, arquetipos, sector, intensidad):
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
def test_intensidad_fuerte_tiene_mas_efecto_que_moderado(catalogo, arquetipos, sector):
    for semilla in SEMILLAS:
        moderado = _generar(catalogo, arquetipos, sector, semilla, "moderado")
        fuerte = _generar(catalogo, arquetipos, sector, semilla, "fuerte")

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
def test_gastos_financieros_dependen_de_la_deuda_tomada(catalogo, arquetipos, sector):
    # Antes de anclar los gastos financieros a la deuda financiera media, moderado y fuerte
    # daban EXACTAMENTE la misma cobertura de gastos financieros cada año (los % de PyG se
    # sorteaban independientes del nivel de deuda). Ahora deben divergir, porque fuerte toma
    # más deuda para financiar un arquetipo más intenso.
    huellas_moderado = set()
    huellas_fuerte = set()
    for semilla in SEMILLAS:
        moderado = _generar(catalogo, arquetipos, sector, semilla, "moderado")
        fuerte = _generar(catalogo, arquetipos, sector, semilla, "fuerte")
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
def test_tipo_de_interes_implicito_es_razonable_para_el_sector(catalogo, arquetipos, sector, intensidad):
    # Cotas de la fuente de mercado (Euríbor 12M + prima de riesgo por categoría, ver
    # motor/empresa_base.py) — ya NO de `ratios.coste_deuda` del catálogo (diagnóstico cerrado,
    # decisiones_plausibilidad.md #41-43). El centro depende del año (Euríbor distinto cada año).
    categoria = categoria_de_sector(sector)

    for evolucion in _casos(catalogo, arquetipos, sector, intensidad):
        anterior = evolucion.ejercicios[AÑO_BASE]
        for año in (2024, 2025):
            ej = evolucion.ejercicios[año]
            centro = REFERENCIA_EURIBOR_12M_POR_AÑO[año] + PRIMA_RIESGO_POR_CATEGORIA[categoria]
            cota_inferior = max(SUELO_TIPO_INTERES, centro - 3 * DISPERSION_TIPO_INTERES_PP) - 1e-6
            cota_superior = min(TECHO_TIPO_INTERES, centro + 3 * DISPERSION_TIPO_INTERES_PP) + 1e-6
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
def test_contencion_de_endeudamiento_respeta_el_techo_del_sector(catalogo, arquetipos, sector, intensidad):
    fila = resolver_fila_sector(catalogo, sector, "grandes_medianas")
    techo_esperado = min(
        fila["ratios.endeudamiento.huber_9y"] + N_DESVIACIONES_TECHO_ENDEUDAMIENTO * fila["ratios.endeudamiento.huber_scale_mad"],
        TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    )
    for evolucion in _casos(catalogo, arquetipos, sector, intensidad):
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
                # El arquetipo 1 siempre toca existencias y realizable, así que siempre hay
                # algo que amortiguar (deterioro_aplicado_eur > 0) cuando hay riesgo.
                assert ej.deterioro_aplicado_eur > 0.0

                # Tolerancia ligada a la convergencia del bucle de contención (converge al
                # importe de amortiguación con TOLERANCIA_CONVERGENCIA_DETERIORO_EUR=1€, no a
                # una precisión infinita), no un margen arbitrario.
                assert ej.endeudamiento <= techo_esperado + 1e-4 or ej.contencion_al_limite
            else:
                assert ej.endeudamiento_sin_contener is None
                assert ej.deterioro_aplicado_eur == 0.0


def test_contencion_de_endeudamiento_se_activa_en_algun_caso(catalogo, arquetipos):
    # Confirma que el mecanismo no es código muerto: para un sector con endeudamiento Huber
    # bajo (Siderurgia) y el arquetipo en fuerte, debe activarse al menos una vez en un barrido
    # de semillas razonable.
    activaciones = 0
    for semilla in range(20):
        evolucion = _generar(catalogo, arquetipos, "24.1", semilla, "fuerte")
        activaciones += sum(evolucion.ejercicios[año].riesgo_endeudamiento for año in (2024, 2025))
    assert activaciones > 0


def test_reproducibilidad_misma_semilla(catalogo, arquetipos):
    a = _generar(catalogo, arquetipos, "24.1", 99, "moderado")
    b = _generar(catalogo, arquetipos, "24.1", 99, "moderado")
    for año in (2023, 2024, 2025):
        assert a.ejercicios[año].balance_eur == b.ejercicios[año].balance_eur
        assert a.ejercicios[año].pyg_eur == b.ejercicios[año].pyg_eur


def test_año_base_coincide_con_empresa_base_directa(catalogo, arquetipos):
    from motor.empresa_base import generar_empresa_base

    evolucion = _generar(catalogo, arquetipos, "24.1", 5, "moderado")
    empresa_directa = generar_empresa_base(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=5, catalogo=catalogo
    )
    assert evolucion.ejercicios[AÑO_BASE].balance_eur == empresa_directa.balance_eur
    assert evolucion.ejercicios[AÑO_BASE].pyg_eur == empresa_directa.pyg_eur


def test_intensidad_invalida_lanza_error(catalogo, arquetipos):
    with pytest.raises(EvolucionArquetipoError, match="Intensidad"):
        _generar(catalogo, arquetipos, "24.1", 1, "extrema")


def test_arquetipo_desconocido_lanza_error(catalogo, arquetipos):
    with pytest.raises(EvolucionArquetipoError, match="no reconocido"):
        generar_evolucion_arquetipo(
            "24.1",
            "grandes_medianas",
            VENTAS_OBJETIVO_2023,
            semilla=1,
            intensidad="moderado",
            arquetipo_id="no_existe",
            catalogo=catalogo,
            arquetipos=arquetipos,
        )


def test_metadatos_de_trazabilidad_presentes(catalogo, arquetipos):
    # Sección 2.15: cada caso debe poder reconstruirse y defenderse, lo que exige guardar qué
    # arquetipo/intensidad/semilla lo generaron y contra qué versión del catálogo y del PGC.
    evolucion = _generar(catalogo, arquetipos, "24.1", 3, "fuerte")
    assert evolucion.arquetipo == ARQUETIPO_1
    assert evolucion.intensidad == "fuerte"
    assert evolucion.semilla == 3
    assert evolucion.catalogo_version == version_catalogo()
    assert evolucion.pgc_version == PGC_VERSION == "PGC RD 1514/2007"


def test_catalogo_version_es_la_del_catalogo_pasado_explicitamente(catalogo, arquetipos):
    # No debe depender de recargar el catálogo por defecto: tiene que venir del propio
    # DataFrame recibido, para que sea fiel a lo que realmente se usó en esa llamada.
    evolucion = _generar(catalogo, arquetipos, "24.1", 1, "moderado")
    assert evolucion.catalogo_version == catalogo.attrs["catalogo_version"]


def test_reimplementacion_generica_reproduce_los_valores_de_referencia(catalogo, arquetipos):
    # Regresión dura: valores exactos del arquetipo 1 para este caso concreto (sector 24.1,
    # semilla 5, fuerte). RE-PINNEADO tras el encargo de continuidad del sorteo anual de PyG
    # (decisiones_plausibilidad.md #75/#77/#78): `_generar_pyg_hasta_baii` ya no redibuja cada
    # año como una empresa nueva contra el Huber del sector — 2024/2025 ahora tienen memoria del
    # año anterior y menos varianza (`_generar_partida_con_memoria`, motor/ruido.py). El año base
    # (2023) sigue siendo un sorteo limpio, sin cambios — existencias 2023 idéntica a antes. El
    # mecanismo del arquetipo 1 en sí (existencias por continuidad) NO cambió, pero al cambiar el
    # ruido de fondo de PyG cambia resultado_ejercicio/PN, que cambia endeudamiento, que cambia
    # CUÁNTO amortigua la contención de plausibilidad sobre existencias en 2024/2025 — mismo tipo
    # de re-pin ya hecho una vez antes, para el cambio de fuente de `tipo_interes` (#41-43). Si
    # este test vuelve a fallar SIN que se haya tocado deliberadamente la semilla del RNG ni el
    # mecanismo de continuidad de PyG, sí es una regresión real del arquetipo 1.
    evolucion = _generar(catalogo, arquetipos, "24.1", 5, "fuerte")
    ej = evolucion.ejercicios
    assert ej[2023].balance_eur["existencias"] == pytest.approx(2_344_937, abs=1)
    assert ej[2024].balance_eur["existencias"] == pytest.approx(3_744_065, abs=1)
    assert ej[2025].balance_eur["existencias"] == pytest.approx(4_478_283, abs=1)
    assert ej[2023].endeudamiento == pytest.approx(0.600, abs=1e-3)
    assert ej[2024].endeudamiento == pytest.approx(0.669, abs=1e-3)
    assert ej[2025].endeudamiento == pytest.approx(0.716, abs=1e-3)


def test_sectores_distintos_no_comparten_crecimiento_pleno_objetivo(catalogo, arquetipos):
    # Regresión del mismo sesgo que el de test_reimplementacion_generica_...: la semilla de
    # `semilla_secuencia` (de la que salen rng_tendencia y rngs_pyg) se sembraba solo con
    # `semilla`, así que cualquier sector/segmento con la misma semilla obtenía exactamente el
    # mismo crecimiento_pleno_objetivo (para arquetipos sin rango_crecimiento_pleno propio, que
    # no depende del sector) y el mismo ruido de PyG de 2024/2025. Corregido mezclando
    # sector+segmento (NO intensidad) en la semilla — ver docstring del módulo. Barrido de los 27
    # sectores del catálogo x 4 semillas: 0 duplicados esperados.
    import re

    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    for semilla in range(4):
        valores = [
            generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
            ).crecimiento_pleno_objetivo
            for codigo in codigos
        ]
        assert len(set(valores)) == len(valores), f"semilla {semilla}: hay sectores con el mismo crecimiento_pleno_objetivo"


def test_mismo_sector_y_semilla_comparte_crecimiento_pleno_objetivo_entre_intensidades(catalogo, arquetipos):
    # Lo contrario del test anterior: por diseño, la misma semilla+sector+segmento con
    # intensidades distintas SÍ debe compartir el "ruido de fondo" (aquí, crecimiento_pleno_objetivo
    # cuando el arquetipo no define rango propio) — el mezclado de sector+segmento en la semilla
    # NO incluye la intensidad. Solo el empuje propio del arquetipo debe variar con ella (ver
    # también test_intensidad_fuerte_tiene_mas_efecto_que_moderado).
    for sector in ("24.1", "62", "47.1"):
        for semilla in SEMILLAS:
            valores = {
                generar_evolucion_arquetipo(
                    sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
                    arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
                ).crecimiento_pleno_objetivo
                for intensidad in ("leve", "moderado", "fuerte")
            }
            assert len(valores) == 1, f"sector {sector}, semilla {semilla}: crecimiento_pleno_objetivo varía con la intensidad"
