"""Tests de `motor/resumen_caso.py` — capa de agregación pura sobre un caso YA generado (Ronda
1, Fase 4). No genera ni corrige ningún dato: solo consolida lo que `EvolucionArquetipo`/
`EjercicioEmpresa` ya exponen. Cubre las 3 partes del encargo: (a) las 5 partículas de
trazabilidad de la sección 2.15 se propagan correctas; (b) los 4 bloques de "particularidades"
(atípicos, señales de riesgo, plausibilidad, notas de memoria, movimiento anual) se consolidan
sin perder ni inventar nada; (c) el modo típico/atípico, antes disperso/incompleto, ahora aparece
de forma consistente para los mecanismos añadidos después del diseño original."""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.memoria import generar_caso_combinado
from motor.resumen_caso import ItemModoAtipico, SeñalRiesgoCaso, resumen_particularidades_caso

VENTAS_OBJETIVO_2023 = 15_000_000.0


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _sectores(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


# --------------------------------------------------------------------------------------------
# Parte A (sección 2.15) — los 5 campos de trazabilidad, propagados sin pérdida.
# --------------------------------------------------------------------------------------------


def test_los_5_campos_de_trazabilidad_estan_presentes_y_poblados(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=3, intensidad="fuerte",
        arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
    )
    r = resumen_particularidades_caso(evolucion)
    assert r.arquetipo == "aumento_clientes"
    assert r.intensidad == "fuerte"
    assert r.semilla == 3
    assert r.catalogo_version and r.catalogo_version != "desconocida"
    assert r.pgc_version


def test_trazabilidad_en_caso_combinado_incluye_memoria_pura(catalogo, arquetipos):
    caso = generar_caso_combinado(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, 5,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "moderado"},
        catalogo=catalogo, arquetipos=arquetipos,
    )
    r = resumen_particularidades_caso(caso)
    assert "dependencia_pocos_clientes" in r.arquetipo
    assert "aumento_clientes" in r.arquetipo


# --------------------------------------------------------------------------------------------
# Parte B — modo típico/atípico consolidado, con año correcto (per-año para pyg.*, None para
# rasgos fijos desde 2023).
# --------------------------------------------------------------------------------------------


def test_atipicos_solo_incluye_entradas_marcadas_como_atipico(catalogo, arquetipos):
    comprobados = 0
    for semilla in range(15):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
        )
        r = resumen_particularidades_caso(evolucion)
        for item in r.atipicos:
            assert isinstance(item, ItemModoAtipico)
            comprobados += 1
        # Verificación cruzada directa contra los `modos` de cada ejercicio: todo lo que
        # `resumen_particularidades_caso` marca como atípico DEBE estar como "atipico" en algún
        # `ejercicio.modos`, y viceversa (ningún atípico real se queda fuera).
        atipicos_esperados = set()
        for año, ejercicio in evolucion.ejercicios.items():
            for partida, modo in ejercicio.modos.items():
                if modo == "atipico":
                    año_esperado = año if partida.startswith("pyg.") else None
                    atipicos_esperados.add((partida, año_esperado))
        atipicos_obtenidos = {(item.partida, item.año) for item in r.atipicos}
        assert atipicos_obtenidos == atipicos_esperados
    assert comprobados > 0, "ningún atípico detectado en 15 semillas — ampliar el barrido"


def test_atipicos_de_activo_no_corriente_periodificaciones_y_capital_social_llegan_al_resumen(catalogo, arquetipos):
    # Corrección adicional pedida: activo_no_corriente/periodificaciones/capital_social (previos
    # a los lotes de desglose, decisiones #24-25) tenían el MISMO problema que existencias/
    # deudores/acreedores/deudas financieras/ROE_caso — corregido en motor/empresa_base.py, se
    # verifica aquí que el resumen consolidado los recoge, con año=None (rasgo fijo desde 2023).
    for semilla in range(20):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
        )
        r = resumen_particularidades_caso(evolucion)
        encontrados = [
            a for a in r.atipicos if a.partida.startswith(("activo_no_corriente.", "periodificacion_", "capital_social"))
        ]
        if encontrados:
            assert all(a.año is None for a in encontrados)
            return
    pytest.fail("no se encontró en 20 semillas ningún atípico de estos 3 sitios — ampliar el barrido")


def test_atipicos_fijos_desde_2023_llevan_año_none_pyg_lleva_año_concreto(catalogo, arquetipos):
    # Barrido hasta encontrar un caso con al menos un atípico de cada tipo, para comprobar la
    # regla año=None (rasgo de caso) vs. año=concreto (primitiva de PyG) de forma explícita.
    for semilla in range(30):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
        )
        r = resumen_particularidades_caso(evolucion)
        no_pyg = [i for i in r.atipicos if not i.partida.startswith("pyg.")]
        pyg = [i for i in r.atipicos if i.partida.startswith("pyg.")]
        if no_pyg and pyg:
            assert all(i.año is None for i in no_pyg)
            assert all(i.año in (2023, 2024, 2025) for i in pyg)
            return
    pytest.fail("no se encontró en 30 semillas un caso con ambos tipos de atípico a la vez")


# --------------------------------------------------------------------------------------------
# Señales de riesgo — solo las 2 señales "padre" (contención va dentro del detalle).
# --------------------------------------------------------------------------------------------


def test_señales_de_riesgo_solo_los_2_tipos_padre(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(4):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
            )
            r = resumen_particularidades_caso(evolucion)
            for señal in r.señales_riesgo:
                assert isinstance(señal, SeñalRiesgoCaso)
                assert señal.tipo in ("riesgo_endeudamiento", "riesgo_plausibilidad_pyg")
                comprobados += 1
    assert comprobados > 0


def test_señal_riesgo_endeudamiento_coincide_con_el_campo_del_ejercicio(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(4):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
            )
            r = resumen_particularidades_caso(evolucion)
            años_con_señal = {s.año for s in r.señales_riesgo if s.tipo == "riesgo_endeudamiento"}
            años_esperados = {año for año, ej in evolucion.ejercicios.items() if ej.riesgo_endeudamiento}
            assert años_con_señal == años_esperados
            comprobados += 1
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# Plausibilidad, notas de memoria, movimiento anual — expuestos sin reprocesar.
# --------------------------------------------------------------------------------------------


def test_plausibilidad_expuesta_tal_cual(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
        arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
    )
    r = resumen_particularidades_caso(evolucion)
    assert r.plausibilidad is evolucion.plausibilidad


def test_notas_memoria_combina_ejercicio_y_memoria_pura_ordenadas(catalogo, arquetipos):
    caso = generar_caso_combinado(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, 2,
        {"riesgo_refinanciacion": "fuerte", "informacion_relevante_memoria": "fuerte"},
        catalogo=catalogo, arquetipos=arquetipos,
    )
    r = resumen_particularidades_caso(caso)
    ids_notas = {n.nota.arquetipo_id for n in r.notas_memoria}
    # riesgo_refinanciacion (16) siempre deja huella de nota_memoria; informacion_relevante (22)
    # es memoria_pura, año=None.
    assert "informacion_relevante_memoria" in ids_notas
    notas_22 = [n for n in r.notas_memoria if n.nota.arquetipo_id == "informacion_relevante_memoria"]
    assert all(n.año is None for n in notas_22)
    # Orden: por año (los case-level con año=None van primero, tratados como -1), luego número.
    claves_orden = [(n.año if n.año is not None else -1, n.nota.numero) for n in r.notas_memoria]
    assert claves_orden == sorted(claves_orden)


def test_movimiento_provision_vacio_si_el_caso_no_tiene_provision(catalogo, arquetipos):
    for semilla in range(10):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
        )
        if evolucion.ejercicios[2025].provision_activa:
            continue
        r = resumen_particularidades_caso(evolucion)
        assert r.movimiento_provision == ()


def test_movimiento_provision_presente_cuando_el_caso_tiene_provision(catalogo, arquetipos):
    for semilla in range(20):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
        )
        if not evolucion.ejercicios[2025].provision_activa:
            continue
        r = resumen_particularidades_caso(evolucion)
        assert {m.año for m in r.movimiento_provision} == {2024, 2025}
        # Reconciliación exacta con lo ya expuesto en el ejercicio (sin reprocesar el dato).
        for m in r.movimiento_provision:
            ej = evolucion.ejercicios[m.año]
            assert m.saldo_largo_eur == ej.provision_saldo_largo_eur
            assert m.dotacion_eur == ej.provision_dotacion_eur
        return
    pytest.fail("ninguna semilla activó la provisión en 20 intentos — ampliar el barrido")


def test_movimiento_insolvencia_presente_cuando_el_caso_tiene_insolvencia(catalogo, arquetipos):
    for semilla in range(20):
        evolucion = generar_evolucion_arquetipo(
            "30.2", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
        )
        if not evolucion.ejercicios[2025].insolvencia_activa:
            continue
        r = resumen_particularidades_caso(evolucion)
        assert {m.año for m in r.movimiento_insolvencia} == {2024, 2025}
        for m in r.movimiento_insolvencia:
            ej = evolucion.ejercicios[m.año]
            assert m.deduccion_realizable_eur == ej.insolvencia_deduccion_realizable_eur
        return
    pytest.fail("ninguna semilla activó la insolvencia en 20 intentos — ampliar el barrido (sector de cobro largo)")


def test_bienes_totalmente_amortizados_no_se_duplican_entre_años(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo)[:6]:
        for semilla in range(4):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            r = resumen_particularidades_caso(evolucion)
            # Cada bien (identificado por tipo+valor_bruto+año_amortizacion_total) debe aparecer
            # como mucho UNA vez, en el año exacto en que se agotó — no repetido en años
            # posteriores (bienes_totalmente_amortizados_en es acumulativo por diseño).
            claves = [(b.año, b.bien.tipo, b.bien.valor_bruto_eur) for b in r.bienes_totalmente_amortizados]
            assert len(claves) == len(set(claves))
            for b in r.bienes_totalmente_amortizados:
                assert b.bien.año_amortizacion_total == b.año
                comprobados += 1
    assert comprobados > 0


def test_tiene_particularidades_false_solo_si_no_hay_nada_que_reportar():
    # No requiere generar un caso real: verifica la propiedad de forma aislada sobre un objeto
    # manual sin ninguna particularidad.
    from motor.resumen_caso import ResumenParticularidadesCaso

    vacio = ResumenParticularidadesCaso(
        sector_codigo="24.1", sector_nombre="x", segmento="grandes_medianas",
        arquetipo="aumento_clientes", intensidad="leve", semilla=0,
        catalogo_version="v", pgc_version="v",
        atipicos=(), señales_riesgo=(), plausibilidad=None, notas_memoria=(),
        movimiento_provision=(), movimiento_insolvencia=(), bienes_totalmente_amortizados=(),
    )
    assert vacio.tiene_particularidades is False
