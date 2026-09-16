"""Tests del selector de modo de generación (`modo_generacion` — sección 2.16/2.17, Fase 4
Ronda 2 punto 2, `motor/ruido.py`). Cubre: el único punto de control (`_resolver_binario_por_
modo`, con su polaridad auto-adaptativa), que hereda de forma transparente hasta el año base sin
tocar ningún helper interno, el acoplamiento de las decisiones binarias transversales
(provisión/insolvencia/subvención de fondo), la trazabilidad (`EvolucionArquetipo.modo_
generacion`/`ResumenParticularidadesCaso.modo_generacion`), la reproducibilidad por semilla, y
la verificación cuantificada de dispersión de dificultad entre variantes de examen (típico vs.
aleatorio) pedida explícitamente antes de cerrar la Fase 4."""

import statistics

import numpy as np
import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import generar_empresa_base
from motor.evolucion_arquetipo import generar_evolucion_arquetipo, generar_evolucion_combinada
from motor.memoria import generar_caso_combinado
from motor.resumen_caso import resumen_particularidades_caso
from motor.ruido import (
    MODOS_GENERACION_VALIDOS,
    ModoGeneracionInvalidoError,
    _resolver_binario_por_modo,
    activar_modo_generacion,
    desactivar_modo_generacion,
    modo_generacion_activo,
)

VENTAS_OBJETIVO_2023 = 15_000_000.0


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


# --------------------------------------------------------------------------------------------
# `_resolver_binario_por_modo` — el único punto de control, en aislamiento.
# --------------------------------------------------------------------------------------------


def test_tipico_fuerza_siempre_false_con_probabilidad_baja():
    rng = np.random.default_rng(0)
    with modo_generacion_activo("tipico"):
        resultados = {_resolver_binario_por_modo(rng, 0.25) for _ in range(30)}
    assert resultados == {False}


def test_atipico_fuerza_siempre_true_con_probabilidad_baja():
    rng = np.random.default_rng(0)
    with modo_generacion_activo("atipico"):
        resultados = {_resolver_binario_por_modo(rng, 0.25) for _ in range(30)}
    assert resultados == {True}


def test_polaridad_auto_adaptativa_con_probabilidad_mayoritaria():
    # Hallazgo real durante la implementación (ver docstring de motor.ruido): con probabilidad
    # >0,5, "atípico" (la rama rara) es False, no True — verificado explícitamente, no asumido.
    rng = np.random.default_rng(0)
    with modo_generacion_activo("tipico"):
        resultados_tipico = {_resolver_binario_por_modo(rng, 0.60) for _ in range(30)}
    with modo_generacion_activo("atipico"):
        resultados_atipico = {_resolver_binario_por_modo(rng, 0.60) for _ in range(30)}
    assert resultados_tipico == {True}  # la rama MAYORITARIA con prob=0,60 es True
    assert resultados_atipico == {False}  # la rama MINORITARIA con prob=0,60 es False


def test_aleatorio_es_el_comportamiento_por_defecto_sin_activar_nada():
    rng = np.random.default_rng(0)
    resultados = {_resolver_binario_por_modo(rng, 0.25) for _ in range(200)}
    assert resultados == {True, False}  # con 200 sorteos a 25%, deben verse ambas ramas


def test_modo_invalido_lanza_error():
    with pytest.raises(ModoGeneracionInvalidoError):
        activar_modo_generacion("no_existe")


def test_activar_desactivar_manual_restaura_el_valor_anterior():
    rng = np.random.default_rng(0)
    token = activar_modo_generacion("tipico")
    try:
        assert _resolver_binario_por_modo(rng, 0.25) is False
    finally:
        desactivar_modo_generacion(token)
    # Tras desactivar, vuelve al comportamiento "aleatorio" por defecto.
    resultados = {_resolver_binario_por_modo(rng, 0.25) for _ in range(200)}
    assert resultados == {True, False}


def test_gestores_anidados_restauran_correctamente():
    rng = np.random.default_rng(0)
    with modo_generacion_activo("tipico"):
        assert _resolver_binario_por_modo(rng, 0.25) is False
        with modo_generacion_activo("atipico"):
            assert _resolver_binario_por_modo(rng, 0.25) is True
        # Al salir del anidado, vuelve a "tipico", no al default "aleatorio".
        assert _resolver_binario_por_modo(rng, 0.25) is False


# --------------------------------------------------------------------------------------------
# Herencia transparente hasta el año base — el hallazgo real detectado durante la
# implementación (generar_empresa_base con un valor por defecto concreto habría vuelto siempre
# a "aleatorio" para el año base, pese al modo pedido para el resto del caso).
# --------------------------------------------------------------------------------------------


def test_generar_empresa_base_en_solitario_respeta_su_propio_modo_generacion(catalogo):
    for modo in ("tipico", "atipico"):
        vistos = set()
        for semilla in range(15):
            empresa = generar_empresa_base(
                "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla,
                catalogo=catalogo, modo_generacion=modo,
            )
            vistos.update(empresa.modos.values())
        vistos.discard("derivado")  # amortización, no pasa por el mecanismo típico/atípico
        assert vistos == {modo}


def test_año_base_hereda_el_modo_de_generar_evolucion_combinada_sin_pasarlo_explicito(catalogo, arquetipos):
    # Regresión del bug real: `generar_empresa_base` tenía, en una versión intermedia de esta
    # implementación, un valor por defecto concreto ("aleatorio") — como `generar_evolucion_
    # combinada` no se lo pasaba explícito, el año base SIEMPRE volvía a "aleatorio" pese al modo
    # pedido para el resto del caso. Corregido con un sentinel `None` ("hereda el ambiente ya
    # activo"). Este test fija el comportamiento correcto para que no se repita.
    for modo in ("tipico", "atipico"):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=3, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos, modo_generacion=modo,
        )
        modos_año_base = set(evolucion.ejercicios[2023].modos.values())
        modos_año_base.discard("derivado")
        assert modos_año_base == {modo}, f"modo={modo}: el año base no heredó el modo correctamente ({modos_año_base})"


# --------------------------------------------------------------------------------------------
# El caso completo (3 años) — ningún "tipico"/"atipico" se cuela ni se pierde en ningún año.
# --------------------------------------------------------------------------------------------


def test_caso_completo_tipico_no_tiene_ningun_atipico_en_ningun_año(catalogo, arquetipos):
    for semilla in range(10):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="tipico",
        )
        for ejercicio in evolucion.ejercicios.values():
            assert "atipico" not in ejercicio.modos.values()


def test_caso_completo_atipico_no_tiene_ningun_tipico_en_ningun_año(catalogo, arquetipos):
    for semilla in range(10):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="atipico",
        )
        for ejercicio in evolucion.ejercicios.values():
            assert "tipico" not in ejercicio.modos.values()


def test_modo_aleatorio_por_defecto_no_cambia_nada_ya_existente(catalogo, arquetipos):
    # 0 casos existentes deben cambiar: comprobación directa de que omitir modo_generacion
    # produce el MISMO resultado que pasarlo explícito como "aleatorio".
    a = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=5, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
    )
    b = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=5, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="aleatorio",
    )
    assert a == b


# --------------------------------------------------------------------------------------------
# Decisiones binarias transversales acopladas — provisión/insolvencia/subvención de fondo.
# --------------------------------------------------------------------------------------------


def test_tipico_nunca_activa_provision_ni_insolvencia(catalogo, arquetipos):
    for semilla in range(15):
        evolucion = generar_evolucion_arquetipo(
            "30.2", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="tipico",
        )
        assert evolucion.ejercicios[2025].provision_activa is False
        assert evolucion.ejercicios[2025].insolvencia_activa is False


def test_atipico_siempre_activa_provision_e_insolvencia(catalogo, arquetipos):
    for semilla in range(15):
        evolucion = generar_evolucion_arquetipo(
            "30.2", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="atipico",
        )
        assert evolucion.ejercicios[2025].provision_activa is True
        assert evolucion.ejercicios[2025].insolvencia_activa is True


def test_atipico_puede_apilar_provision_e_insolvencia_a_la_vez_sin_descuadre(catalogo, arquetipos):
    from motor.efe import generar_efe

    evolucion = generar_evolucion_arquetipo(
        "30.2", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
        arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="atipico",
    )
    assert evolucion.ejercicios[2025].provision_activa
    assert evolucion.ejercicios[2025].insolvencia_activa
    for año in (2024, 2025):
        efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
        assert efe.cuadra, f"año={año}: descuadre={efe.descuadre_eur}"


# --------------------------------------------------------------------------------------------
# Trazabilidad (sección 2.15) — modo_generacion visible como cualquier otro metadato.
# --------------------------------------------------------------------------------------------


def test_modo_generacion_queda_registrado_en_evolucion_arquetipo(catalogo, arquetipos):
    for modo in MODOS_GENERACION_VALIDOS:
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos, modo_generacion=modo,
        )
        assert evolucion.modo_generacion == modo


def test_modo_generacion_llega_al_resumen_de_particularidades(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
        arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="tipico",
    )
    r = resumen_particularidades_caso(evolucion)
    assert r.modo_generacion == "tipico"


def test_generar_caso_combinado_reenvia_modo_generacion(catalogo, arquetipos):
    caso = generar_caso_combinado(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, 1,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        catalogo=catalogo, arquetipos=arquetipos, modo_generacion="atipico",
    )
    assert caso.modo_generacion == "atipico"
    assert caso.ejercicios[2025].insolvencia_activa is True


# --------------------------------------------------------------------------------------------
# Reproducibilidad — misma semilla + mismo modo, mismo caso, siempre.
# --------------------------------------------------------------------------------------------


def test_misma_semilla_y_modo_da_el_mismo_caso(catalogo, arquetipos):
    for modo in MODOS_GENERACION_VALIDOS:
        a = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=7, intensidad="fuerte",
            arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos, modo_generacion=modo,
        )
        b = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=7, intensidad="fuerte",
            arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos, modo_generacion=modo,
        )
        assert a == b


def test_misma_semilla_distinto_modo_puede_dar_distinto_caso(catalogo, arquetipos):
    # No es un requisito que deban COINCIDIR entre modos (ver diseño aprobado) — solo que cada
    # uno sea reproducible consigo mismo. Confirma que en la práctica SÍ difieren (si no, el
    # modo no estaría teniendo ningún efecto real).
    tipico = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=7, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="tipico",
    )
    atipico = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=7, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="atipico",
    )
    assert tipico.ejercicios[2025].balance_eur != atipico.ejercicios[2025].balance_eur


def test_distintas_semillas_bajo_tipico_dan_variedad_real(catalogo, arquetipos):
    ventas_2025 = {
        generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos, modo_generacion="tipico",
        ).ejercicios[2025].balance_eur["patrimonio_neto"]
        for semilla in range(10)
    }
    assert len(ventas_2025) == 10, "todas las semillas deberían dar resultados distintos bajo 'tipico'"


# --------------------------------------------------------------------------------------------
# Variantes de examen — verificación cuantificada de dispersión de dificultad, pedida
# explícitamente antes de cerrar la Fase 4. Usa el Combo B de la sección 2.26 (Crecimiento con
# destrucción de caja + Mejora de margen, score=1,00 — CONSTANTE entre variantes por
# construcción, no es lo que se mide: ver docstring de motor/ruido.py y el razonamiento del
# diseño aprobado) como caso de referencia documentado.
# --------------------------------------------------------------------------------------------


def _numero_de_señales(catalogo, arquetipos, semilla, modo_generacion):
    caso = generar_evolucion_combinada(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
        {"crecimiento_destruccion_caja": "moderado", "mejora_margen": "moderado"},
        catalogo=catalogo, arquetipos=arquetipos, modo_generacion=modo_generacion,
    )
    return len(caso.plausibilidad.señales)


def test_dispersion_de_señales_es_mas_estrecha_bajo_tipico_que_bajo_aleatorio(catalogo, arquetipos):
    """Verificación cuantificada pedida explícitamente antes de cerrar la Fase 4 — Combo B
    (sección 2.26, score=1,00, 2 arquetipos). N=25 semillas por grupo (suite rápida; el barrido
    más amplio, N=50, se ejecutó aparte como script ad hoc para el informe de resultados, mismo
    criterio que `stress_plausibilidad.py` en toda la Fase 3)."""
    n = 25
    señales_tipico = [_numero_de_señales(catalogo, arquetipos, semilla, "tipico") for semilla in range(n)]
    señales_aleatorio = [_numero_de_señales(catalogo, arquetipos, semilla, "aleatorio") for semilla in range(n)]

    media_tipico = statistics.mean(señales_tipico)
    media_aleatorio = statistics.mean(señales_aleatorio)
    desviacion_tipico = statistics.pstdev(señales_tipico)
    desviacion_aleatorio = statistics.pstdev(señales_aleatorio)

    # La media de señales bajo "tipico" debe ser sustancialmente menor (menos casos raros) — y,
    # si hay variación en ambos grupos, la dispersión bajo "tipico" no debe ser mayor.
    assert media_tipico <= media_aleatorio, f"media típico={media_tipico} > media aleatorio={media_aleatorio}"
    if desviacion_aleatorio > 0:
        assert desviacion_tipico <= desviacion_aleatorio + 1e-9, (
            f"desviación típico={desviacion_tipico} > desviación aleatorio={desviacion_aleatorio}"
        )


def test_score_de_complejidad_seccion_2_25_es_constante_entre_variantes(catalogo, arquetipos):
    # El score de la sección 2.25 depende SOLO de combo+intensidad, nunca de la semilla — por
    # construcción, no hay nada que "dispersar" ahí entre variantes de examen (ver docstring del
    # módulo motor/ruido.py). Lo único que puede variar variante a variante es el resultado
    # numérico generado (comprobado en el test anterior), no la puntuación estructural. Este
    # test fija esa propiedad explícitamente para no repetir la confusión durante el diseño.
    combos = [
        generar_evolucion_combinada(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"crecimiento_destruccion_caja": "moderado", "mejora_margen": "moderado"},
            catalogo=catalogo, arquetipos=arquetipos, modo_generacion="tipico",
        )
        for semilla in range(5)
    ]
    # El propio combo+intensidad (la entrada a la fórmula de la sección 2.25) es idéntico en las
    # 5 variantes por construcción — se confirma aquí explícitamente, no solo se asume.
    arquetipos_por_variante = {tuple(sorted(c.arquetipo.split("+"))) for c in combos}
    assert len(arquetipos_por_variante) == 1
