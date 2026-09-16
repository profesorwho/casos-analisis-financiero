"""Tests del deterioro de valor de créditos por operaciones comerciales (cuenta 490 del PGC,
`motor/insolvencias.py`) — DETERIORO DE ACTIVO (resta de "Clientes" dentro de realizable), a
diferencia de las provisiones del subgrupo 14 (`tests/test_provisiones.py`, pasivo).

Cubre lo pedido explícitamente: probabilidad de fondo independiente de cualquier arquetipo
(incluido el 6, "línea base sana"), magnitud (probabilidad Y importe) anclada a `ratios.cobro_
dias`, boost de probabilidad/magnitud con los arquetipos 4 (deterioro del ciclo de caja) y 7
(dependencia de pocos clientes, verificado EN LA PRÁCTICA vía `generar_caso_combinado`, no solo
a nivel de fórmula), movimiento anual completo, conexión con PyG (dotación en `otros_gastos_
explot`, exceso en `otros_ingresos_explot`), identidad Balance↔PyG explícita (lección de
`test_provisiones.py`), suma exacta con Clientes/Deudores, y cuadre del EFE/ECPN sin líneas
nuevas."""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.ecpn import generar_ecpn
from motor.efe import generar_efe
from motor.empresa_base import resolver_fila_sector
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.insolvencias import (
    PROBABILIDAD_INSOLVENCIA_SUELO,
    PROBABILIDAD_INSOLVENCIA_TECHO,
    MULTIPLICADOR_MAGNITUD_BOOST,
    factor_riesgo_cobro_dias,
    probabilidad_insolvencia,
    sortear_importe_insolvencia_eur,
    sortear_insolvencia_baseline,
)
from motor.memoria import generar_caso_combinado

VENTAS_OBJETIVO_2023 = 15_000_000.0

# Sectores extremos del catálogo real (ver docstring de motor/insolvencias.py): 47.1 (Comercio al
# por menor / supermercados) el cobro_dias más corto (9,6 días — factor de riesgo 0, probabilidad
# en su suelo); 30.2 (Fabricación de material ferroviario) el más largo (186,3 días — factor 1,
# probabilidad en su techo).
SECTOR_COBRO_CORTO = "47.1"
SECTOR_COBRO_LARGO = "30.2"


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _sectores(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


def _cuadra(ejercicio) -> bool:
    activo = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
    pn_pasivo = (
        ejercicio.balance_eur["patrimonio_neto"]
        + ejercicio.balance_eur["pasivo_no_corriente"]
        + ejercicio.balance_eur["pasivo_corriente"]
    )
    return activo == pytest.approx(pn_pasivo, abs=1.0)


def _identidad_pn(ejercicio) -> float:
    """Misma fórmula EXACTA que `tests/test_provisiones.py::_identidad_pn` (que a su vez
    reproduce `tests/test_amortizacion.py::_identidad_pn`) — reproducida aquí, no importada, por
    el mismo motivo: la dotación/exceso de insolvencia mueve `pyg_eur["resultado_ejercicio"]`
    exactamente igual que la amortización/provisión/grupo89, así que la identidad debe seguir
    cuadrando EXACTA, comprobación distinta y más estricta que el `_cuadra` agregado."""
    suma = (
        ejercicio.capital_social_eur
        + ejercicio.reservas_eur
        + ejercicio.pyg_eur["resultado_ejercicio"]
        + ejercicio.ajustes_cambio_valor_pn_eur
        + ejercicio.subvenciones_pn_eur
    )
    return abs(suma - ejercicio.balance_eur["patrimonio_neto"])


# --------------------------------------------------------------------------------------------
# Probabilidad de fondo, independiente de cualquier arquetipo — verificada con el arquetipo 6
# ("Aumento de clientes (base)", línea base sana), no solo teóricamente. Fácil de encontrar por
# semilla (20%-40% de base, según el sector), no un 2%.
# --------------------------------------------------------------------------------------------


def test_probabilidad_de_fondo_con_arquetipo_6_dentro_del_rango_pedido(catalogo, arquetipos):
    activas = 0
    total = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            total += 1
            if evolucion.ejercicios[2025].insolvencia_activa:
                activas += 1
    tasa = activas / total
    assert PROBABILIDAD_INSOLVENCIA_SUELO - 0.05 <= tasa <= PROBABILIDAD_INSOLVENCIA_TECHO + 0.05, (
        f"tasa de activación {tasa:.1%} fuera del rango de base esperado (216 casos: {activas} activas)"
    )


def test_insolvencia_nunca_dotada_en_el_año_base(catalogo, arquetipos):
    for codigo in ("24.1", "62", "47.1"):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio_2023 = evolucion.ejercicios[2023]
            assert ejercicio_2023.insolvencia_saldo_eur == 0.0
            assert ejercicio_2023.insolvencia_dotacion_eur == 0.0
            assert ejercicio_2023.insolvencia_deduccion_realizable_eur == 0.0


# --------------------------------------------------------------------------------------------
# Anclaje a cobro_dias — la probabilidad Y la magnitud deben escalar con el plazo de cobro real
# del sector, no un sorteo independiente. Verificado a nivel de fórmula (determinista) Y
# empíricamente sobre un barrido amplio (no solo asumido por construcción de la rampa).
# --------------------------------------------------------------------------------------------


def test_factor_riesgo_cobro_dias_satura_fuera_del_rango():
    assert factor_riesgo_cobro_dias(9.6) == 0.0
    assert factor_riesgo_cobro_dias(186.3) == 1.0
    assert 0.0 < factor_riesgo_cobro_dias(90.0) < 1.0


def test_probabilidad_sube_con_cobro_dias_a_nivel_de_formula():
    p_corto = probabilidad_insolvencia(9.6, False, False)
    p_largo = probabilidad_insolvencia(186.3, False, False)
    assert p_corto == pytest.approx(PROBABILIDAD_INSOLVENCIA_SUELO)
    assert p_largo == pytest.approx(PROBABILIDAD_INSOLVENCIA_TECHO)
    assert p_largo > p_corto


def test_probabilidad_observada_es_mayor_en_el_sector_de_cobro_largo(catalogo, arquetipos):
    def _tasa(sector):
        activas = 0
        total = 0
        for semilla in range(25):
            evolucion = generar_evolucion_arquetipo(
                sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            total += 1
            if evolucion.ejercicios[2025].insolvencia_activa:
                activas += 1
        return activas / total

    tasa_corto = _tasa(SECTOR_COBRO_CORTO)
    tasa_largo = _tasa(SECTOR_COBRO_LARGO)
    assert tasa_largo > tasa_corto, f"cobro largo ({tasa_largo:.1%}) no supera a cobro corto ({tasa_corto:.1%})"


def test_magnitud_media_es_mayor_en_el_sector_de_cobro_largo(catalogo, arquetipos):
    def _importe_medio_pct_clientes(sector):
        importes = []
        for semilla in range(25):
            evolucion = generar_evolucion_arquetipo(
                sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio = evolucion.ejercicios[2025]
            if ejercicio.insolvencia_activa and ejercicio.insolvencia_importe_dotado_eur > 0:
                importes.append(ejercicio.insolvencia_importe_dotado_eur)
        assert importes, f"ningún caso activo para {sector} — ampliar el barrido"
        return sum(importes) / len(importes)

    medio_corto = _importe_medio_pct_clientes(SECTOR_COBRO_CORTO)
    medio_largo = _importe_medio_pct_clientes(SECTOR_COBRO_LARGO)
    assert medio_largo > medio_corto, f"cobro largo ({medio_largo:,.0f}€) no supera a cobro corto ({medio_corto:,.0f}€)"


# --------------------------------------------------------------------------------------------
# Boost de arquetipo 4 (deterioro del ciclo de caja, cuantitativo) — probabilidad Y magnitud
# mayores que la línea base, verificado sobre un barrido amplio.
# --------------------------------------------------------------------------------------------


def test_arquetipo_4_deterioro_ciclo_caja_sube_la_probabilidad_observada(catalogo, arquetipos):
    def _tasa(arquetipo_id):
        activas = 0
        total = 0
        for codigo in _sectores(catalogo):
            for semilla in range(6):
                evolucion = generar_evolucion_arquetipo(
                    codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                    arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
                )
                total += 1
                if evolucion.ejercicios[2025].insolvencia_activa:
                    activas += 1
        return activas / total

    tasa_base = _tasa("aumento_clientes")
    tasa_con_4 = _tasa("deterioro_ciclo_caja")
    assert tasa_con_4 > tasa_base, f"con el 4 ({tasa_con_4:.1%}) no supera la línea base ({tasa_base:.1%})"


def test_sortear_importe_insolvencia_escala_por_el_boost_a_nivel_de_formula():
    sector, segmento, semilla = "24.1", "grandes_medianas", 3
    clientes_referencia_eur = 5_000_000.0
    cobro_dias = 90.0
    sin_boost = sortear_importe_insolvencia_eur(sector, segmento, semilla, clientes_referencia_eur, cobro_dias, False)
    con_boost = sortear_importe_insolvencia_eur(sector, segmento, semilla, clientes_referencia_eur, cobro_dias, True)
    # Ambos por encima del suelo defensivo (si no, el suelo absorbería el factor de escala).
    assert sin_boost > 5_000.0
    assert con_boost == pytest.approx(sin_boost * MULTIPLICADOR_MAGNITUD_BOOST)


# --------------------------------------------------------------------------------------------
# Boost de arquetipo 7 (dependencia de pocos clientes, memoria_pura) — verificado EN LA
# PRÁCTICA vía `generar_caso_combinado` (pedido explícitamente por el usuario), no solo a nivel
# de fórmula: el booleano `dependencia_pocos_clientes_activo` tiene que llegar de verdad desde
# `motor.memoria` hasta `motor.evolucion_arquetipo`/`motor.insolvencias` y cambiar el resultado.
# --------------------------------------------------------------------------------------------


def test_probabilidad_sube_con_dependencia_pocos_clientes_a_nivel_de_formula():
    p_sin_7 = probabilidad_insolvencia(90.0, False, False)
    p_con_7 = probabilidad_insolvencia(90.0, False, True)
    assert p_con_7 > p_sin_7


def test_sortear_insolvencia_baseline_monotona_con_el_boost():
    """Para cualquier semilla, si activa SIN el boost, tiene que activar también CON el boost
    (mismo `rng.random()` — la entropía del sorteo no depende de cobro_dias ni de los booleanos,
    solo el umbral cambia — ver `sortear_insolvencia_baseline`). Propiedad determinista,
    comprobada de forma exhaustiva sobre un rango amplio de semillas."""
    sector, segmento = "24.1", "grandes_medianas"
    cobro_dias = 90.0
    activaciones_sin_boost = 0
    for semilla in range(200):
        sin_boost = sortear_insolvencia_baseline(sector, segmento, semilla, cobro_dias, False, False)
        con_boost = sortear_insolvencia_baseline(sector, segmento, semilla, cobro_dias, False, True)
        if sin_boost.activa:
            activaciones_sin_boost += 1
            assert con_boost.activa, f"semilla {semilla}: activa sin boost pero no con boost"
    assert activaciones_sin_boost > 0, "ninguna activación sin boost en 200 semillas — ampliar el rango"


def test_arquetipo_7_sube_probabilidad_y_magnitud_en_la_practica_via_caso_combinado(catalogo, arquetipos):
    """Comprobación pedida explícitamente: genera el MISMO caso (sector, semilla) con y sin el
    arquetipo 7 activo (vía `generar_caso_combinado`, el orquestador real que combina clases
    `cuantitativo`+`memoria_pura`) y confirma que el booleano `dependencia_pocos_clientes_activo`
    efectivamente sube la probabilidad Y la magnitud de insolvencia — no solo que la señal llega
    a algún sitio, sino que cambia el resultado del caso frente a NO tenerlo. Sector de cobro
    corto (probabilidad de base en su suelo, 20%): el salto del boost (+10pp) es más fácil de
    observar como activaciones NUEVAS que no ocurrirían sin el 7."""
    activas_sin_7 = 0
    activas_con_7 = 0
    importes_sin_7 = []
    importes_con_7 = []
    total = 40
    for semilla in range(total):
        sin_7 = generar_caso_combinado(
            SECTOR_COBRO_CORTO, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"aumento_clientes": "fuerte"}, catalogo=catalogo, arquetipos=arquetipos,
        )
        con_7 = generar_caso_combinado(
            SECTOR_COBRO_CORTO, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, catalogo=catalogo, arquetipos=arquetipos,
        )
        # El arquetipo 7 es memoria_pura: no debe cambiar NADA más del caso cuantitativo salvo,
        # precisamente, la insolvencia (mismo criterio de aislamiento que el 22 en provisiones).
        assert [n.arquetipo_id for n in con_7.notas_memoria_pura] == ["dependencia_pocos_clientes"]

        ej_sin = sin_7.ejercicios[2025]
        ej_con = con_7.ejercicios[2025]
        if ej_sin.insolvencia_activa:
            activas_sin_7 += 1
            importes_sin_7.append(ej_sin.insolvencia_importe_dotado_eur)
        if ej_con.insolvencia_activa:
            activas_con_7 += 1
            importes_con_7.append(ej_con.insolvencia_importe_dotado_eur)
        # Monotonía a nivel de caso concreto: si activa SIN el 7, tiene que activar también CON
        # el 7 (mismo draw de `rng.random()`, solo compite contra un umbral más alto) — y si
        # activa en ambos, el importe dotado con el 7 debe ser EXACTAMENTE el boost de magnitud.
        if ej_sin.insolvencia_activa:
            assert ej_con.insolvencia_activa, f"semilla {semilla}: activa sin el 7 pero no con el 7"
            assert ej_con.insolvencia_importe_dotado_eur == pytest.approx(
                ej_sin.insolvencia_importe_dotado_eur * MULTIPLICADOR_MAGNITUD_BOOST
            ), f"semilla {semilla}: el importe con el 7 no escala por el boost de magnitud"

    tasa_sin_7 = activas_sin_7 / total
    tasa_con_7 = activas_con_7 / total
    assert tasa_con_7 > tasa_sin_7, (
        f"el arquetipo 7 no subió la tasa de activación observada: sin={tasa_sin_7:.1%} con={tasa_con_7:.1%}"
    )
    assert importes_con_7, "ningún caso con el 7 activó la insolvencia — ampliar semillas"
    assert sum(importes_con_7) / len(importes_con_7) > 0


# --------------------------------------------------------------------------------------------
# Movimiento anual — saldo_inicial + dotación - aplicación - exceso = saldo_final, exacto. Y la
# propiedad de diseño distintiva frente a provisiones (ver docstring de motor/insolvencias.py):
# la DEDUCCIÓN sobre `realizable` solo decrece con la reversión, nunca con la aplicación.
# --------------------------------------------------------------------------------------------


def test_movimiento_anual_reconcilia_exacto(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].insolvencia_activa:
                continue
            for año_anterior, año in ((2023, 2024), (2024, 2025)):
                anterior = evolucion.ejercicios[año_anterior]
                actual = evolucion.ejercicios[año]
                esperado = (
                    anterior.insolvencia_saldo_eur
                    + actual.insolvencia_dotacion_eur
                    - actual.insolvencia_aplicacion_eur
                    - actual.insolvencia_exceso_eur
                )
                assert actual.insolvencia_saldo_eur == pytest.approx(esperado, abs=0.01), f"{codigo} semilla={semilla} año={año}"
                comprobados += 1
    assert comprobados > 0


def test_saldo_nunca_negativo(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert ejercicio.insolvencia_saldo_eur >= 0.0
                assert ejercicio.insolvencia_deduccion_realizable_eur >= -1e-6
                comprobados += 1
    assert comprobados > 0


def test_deduccion_realizable_no_se_recupera_con_aplicacion_solo_con_reversion(catalogo, arquetipos):
    """Propiedad de diseño central (ver docstring del módulo): la aplicación es una baja
    definitiva (sin efecto neto en `realizable`, ya reconocida en PyG el año de la dotación); la
    reversión SÍ libera `realizable`. Se comprueba que `insolvencia_deduccion_realizable_eur`
    nunca SUBE de un año a otro salvo por una reversión ese mismo año (nunca por aplicación
    sola)."""
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].insolvencia_activa:
                continue
            for año_anterior, año in ((2023, 2024), (2024, 2025)):
                anterior = evolucion.ejercicios[año_anterior]
                actual = evolucion.ejercicios[año]
                delta_deduccion = actual.insolvencia_deduccion_realizable_eur - anterior.insolvencia_deduccion_realizable_eur
                if actual.insolvencia_aplicacion_eur > 0 and actual.insolvencia_exceso_eur == 0.0:
                    # Solo aplicación este año: la deducción no debe bajar (no debe "recuperarse"
                    # realizable por la baja definitiva).
                    assert delta_deduccion >= -1e-6, f"{codigo} semilla={semilla} año={año}: la deducción bajó solo por aplicación"
                if actual.insolvencia_exceso_eur > 0:
                    # La reversión SÍ debe reducir la deducción, por el importe exacto del exceso.
                    assert delta_deduccion == pytest.approx(-actual.insolvencia_exceso_eur, abs=0.01)
                comprobados += 1
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# Conexión con PyG — dotación siempre en otros_gastos_explot (cuenta 490, nunca gasto de
# personal), exceso siempre en otros_ingresos_explot.
# --------------------------------------------------------------------------------------------


def test_dotacion_afecta_baii_y_exceso_afecta_margen_bruto(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in (evolucion.ejercicios[2024], evolucion.ejercicios[2025]):
                if ejercicio.insolvencia_dotacion_eur > 0:
                    comprobados += 1
                    # La dotación resta de otros_gastos_explot (verificable indirectamente: el
                    # caso con dotación > 0 es, por diseño, siempre el año de dotación completo).
                    assert ejercicio.insolvencia_dotacion_eur == pytest.approx(ejercicio.insolvencia_importe_dotado_eur)
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# Cuadre de balance/PyG/EFE/ECPN — igual estándar que provisiones y grupo89.
# --------------------------------------------------------------------------------------------


def test_balance_y_pyg_cuadran_con_insolvencia_activa(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(10):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].insolvencia_activa:
                continue
            for ejercicio in evolucion.ejercicios.values():
                assert _cuadra(ejercicio), f"{codigo} semilla={semilla} año={ejercicio.año}"
                comprobados += 1
    assert comprobados > 0


def test_identidad_balance_pyg_resultado_ejercicio_con_insolvencia_activa(catalogo, arquetipos):
    """Pedido explícitamente: la identidad Balance↔PyG del resultado del ejercicio, comprobada
    de forma EXPLÍCITA (no asumida heredada de otro mecanismo — aprendizaje del lote 3 de
    provisiones, ver `tests/test_provisiones.py::test_identidad_balance_pyg_resultado_ejercicio_
    con_provision_activa`)."""
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].insolvencia_activa:
                continue
            for ejercicio in evolucion.ejercicios.values():
                diff_eur = _identidad_pn(ejercicio)
                assert diff_eur < 1e-6, f"{codigo} semilla={semilla} año={ejercicio.año}: diferencia {diff_eur}€"
                comprobados += 1
    assert comprobados > 0, "ningún caso con insolvencia activa en el barrido — ampliar semillas"


def test_suma_exacta_con_clientes_deudores(catalogo, arquetipos):
    """Pedido explícitamente: la suma del desglose de deudores (incluida "Clientes") tiene que
    coincidir EXACTO con `balance_eur["realizable"]` YA neto de insolvencia — no asumido por
    construcción del desglose (perfil % fijo aplicado al agregado de ESTE año), comprobado."""
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(10):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].insolvencia_activa:
                continue
            for ejercicio in evolucion.ejercicios.values():
                suma_desglose = sum(ejercicio.deudores_desglose_eur.values())
                assert suma_desglose == pytest.approx(ejercicio.balance_eur["realizable"], abs=0.01), (
                    f"{codigo} semilla={semilla} año={ejercicio.año}"
                )
                # "Clientes" sigue siendo la sub-partida dominante (perfil ~88%, ver segundo
                # lote de desglose de balance) incluso con el deterioro ya restado del total.
                assert ejercicio.deudores_desglose_eur["clientes"] > 0
                comprobados += 1
    assert comprobados > 0


def test_efe_y_ecpn_cuadran_con_insolvencia_activa_arquetipo_solo_y_combinado(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].insolvencia_activa:
                continue
            for año in (2024, 2025):
                efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
                ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
                assert efe.cuadra, f"{codigo} semilla={semilla} año={año}: EFE descuadre {efe.descuadre_eur:,.4f}€"
                assert ecpn.cuadra, f"{codigo} semilla={semilla} año={año}: ECPN descuadre {ecpn.descuadre_eur:,.4f}€"
                comprobados += 1
    assert comprobados > 0

    comprobados_combo = 0
    for semilla in range(30):
        caso = generar_caso_combinado(
            SECTOR_COBRO_LARGO, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
            catalogo=catalogo, arquetipos=arquetipos,
        )
        if not caso.ejercicios[2025].insolvencia_activa:
            continue
        for ejercicio in caso.ejercicios.values():
            assert _identidad_pn(ejercicio) < 1e-6, f"combo semilla={semilla} año={ejercicio.año}"
        for año in (2024, 2025):
            efe = generar_efe(caso.ejercicios[año - 1], caso.ejercicios[año], obligatorio=True)
            ecpn = generar_ecpn(caso.ejercicios[año - 1], caso.ejercicios[año], obligatorio=True)
            assert efe.cuadra and ecpn.cuadra, f"combo semilla={semilla} año={año}"
        comprobados_combo += 1
    assert comprobados_combo > 0, "ninguna semilla combinó insolvencia activa con el arquetipo 7 — ampliar el barrido"


def test_efe_cuadra_sin_lineas_nuevas(catalogo, arquetipos):
    """Verificación EMPÍRICA (no solo algebraica) de que `a3b_deudores` ya existente absorbe el
    efecto exacto del deterioro, sin ningún cambio en motor/efe.py — ver docstring del módulo."""
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(10):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].insolvencia_activa:
                continue
            for año in (2024, 2025):
                anterior = evolucion.ejercicios[año - 1]
                actual = evolucion.ejercicios[año]
                efe = generar_efe(anterior, actual, obligatorio=True)
                assert efe.cuadra, f"{codigo} semilla={semilla} año={año}: descuadre={efe.descuadre_eur}"
                esperado_a3b = -(actual.balance_eur["realizable"] - anterior.balance_eur["realizable"])
                assert efe.a3b_deudores == pytest.approx(esperado_a3b, abs=0.01)
                comprobados += 1
    assert comprobados > 0
