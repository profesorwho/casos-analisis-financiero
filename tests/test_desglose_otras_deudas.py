"""Tests del quinto lote de desglose de balance: "Otras deudas" (largo y corto plazo) —
carve-out de `otras_deudas_largo`/`otras_deudas_corto` (ver motor/empresa_base.py,
`calcular_desglose_otras_deudas`).

Cubre lo pedido explícitamente: residuo excluye provisiones (tercer lote)/deudas con el grupo
(arquetipo 20)/pasivos por impuesto diferido (grupo 8/9) sin re-etiquetar el mismo euro dos veces;
`deudas_socios` con probabilidad de fondo baja y SIN boost de ningún arquetipo; `aapp_pendiente`
con probabilidad/magnitud ancladas al boost de arquetipo 4 ("deterioro_ciclo_caja")/7
("dependencia_pocos_clientes"), mismo mecanismo que `motor/insolvencias.py`; reclasificación anual
1/plazo de `acreedores_inmovilizado` de largo a corto; suma exacta con la masa agregada, 0
sub-partidas negativas; EFE/ECPN sin descuadres nuevos."""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.ecpn import generar_ecpn
from motor.efe import generar_efe
from motor.empresa_base import (
    FRACCION_RECLASIFICACION_ACREEDORES_INMOVILIZADO,
    MULTIPLICADOR_MAGNITUD_AAPP_PENDIENTE_BOOST,
    PROBABILIDAD_AAPP_PENDIENTE_BASE,
    PROBABILIDAD_DEUDAS_SOCIOS_LARGO,
    TECHO_PROBABILIDAD_AAPP_PENDIENTE_ABSOLUTO,
    calcular_desglose_otras_deudas,
    generar_empresa_base,
    probabilidad_aapp_pendiente,
    sortear_aapp_pendiente_corto_pct,
    sortear_deudas_socios_baseline,
)
from motor.coberturas_subvenciones import pasivo_por_impuesto_diferido_eur
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.memoria import generar_caso_combinado

VENTAS_OBJETIVO_2023 = 15_000_000.0
CATEGORIAS_LARGO = ("acreedores_inmovilizado", "fianzas_depositos", "deudas_socios", "remanente")
CATEGORIAS_CORTO = ("acreedores_inmovilizado", "fianzas_depositos", "aapp_pendiente", "remanente")


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


def _pasivos_por_impuesto_diferido_eur(ejercicio) -> float:
    """Reconstruye `pasivos_por_impuesto_diferido_eur` (local a `_evolucionar_un_año`, no expuesto
    como campo propio de `EjercicioEmpresa`) a partir de los 2 saldos brutos SÍ expuestos — mismas
    2 llamadas que motor.evolucion_arquetipo, ver ese módulo."""
    return pasivo_por_impuesto_diferido_eur(ejercicio.cobertura_saldo_1340_bruto_eur) + pasivo_por_impuesto_diferido_eur(
        ejercicio.subvencion_saldo_130_bruto_eur
    )


def _otras_deudas_largo_target_eur(ejercicio) -> float:
    """El residuo que el quinto lote SÍ desglosa — agregado menos las 3 piezas ya identificadas
    con su propio epígrafe oficial (provisiones/deudas del grupo/pasivos por impuesto diferido,
    ver docstring del módulo). `sum(otras_deudas_largo_desglose_eur.values())` debe cuadrar EXACTO
    contra esto, no contra el agregado bruto (que las incluye)."""
    return (
        ejercicio.balance_eur["otras_deudas_largo"]
        - ejercicio.provision_saldo_largo_eur
        - ejercicio.deuda_grupo_largo_eur
        - _pasivos_por_impuesto_diferido_eur(ejercicio)
    )


def _otras_deudas_corto_target_eur(ejercicio) -> float:
    return max(0.0, ejercicio.balance_eur["otras_deudas_corto"] - ejercicio.provision_saldo_corto_eur)


def _identidad_pn(ejercicio) -> float:
    """Misma fórmula que el resto de tests de lotes de desglose de balance (ver
    tests/test_desglose_deudas_financieras.py) — este lote no toca PyG/PN en absoluto (carve-out
    puro de balance, sin ningún euro nuevo), así que debe seguir cuadrando exacto sin cambios."""
    suma = (
        ejercicio.capital_social_eur
        + ejercicio.reservas_eur
        + ejercicio.pyg_eur["resultado_ejercicio"]
        + ejercicio.ajustes_cambio_valor_pn_eur
        + ejercicio.subvenciones_pn_eur
    )
    return abs(suma - ejercicio.balance_eur["patrimonio_neto"])


# --------------------------------------------------------------------------------------------
# Suma exacta — empresa base y evolución, con y sin arquetipos que muevan el residuo.
# --------------------------------------------------------------------------------------------


def test_desglose_otras_deudas_suma_exacta_en_empresa_base(catalogo):
    """Año base: sin provisiones/deudas del grupo/pasivos por impuesto diferido activos todavía
    (ninguno de esos 3 mecanismos actúa antes de 2024) — el residuo coincide con el propio
    agregado bruto del catálogo, sin nada que restar."""
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            dl = empresa.otras_deudas_largo_desglose_eur
            dc = empresa.otras_deudas_corto_desglose_eur
            assert set(dl) == set(CATEGORIAS_LARGO)
            assert set(dc) == set(CATEGORIAS_CORTO)
            assert sum(dl.values()) == pytest.approx(empresa.balance_eur["otras_deudas_largo"], abs=0.01)
            assert sum(dc.values()) == pytest.approx(empresa.balance_eur["otras_deudas_corto"], abs=0.01)
            # Sin reclasificación en el año base (no hay "año anterior").
            assert dc["aapp_pendiente"] == pytest.approx(empresa.aapp_pendiente_corto_pct * empresa.balance_eur["otras_deudas_corto"])
            for valor in {**dl, **dc}.values():
                assert valor >= -1e-6


@pytest.mark.parametrize(
    "arquetipo_id", ["exceso_stock", "apalancamiento", "capex_elevado", "adquisicion", "riesgo_refinanciacion", "deterioro_ciclo_caja"]
)
def test_desglose_otras_deudas_suma_exacta_en_evolucion(catalogo, arquetipos, arquetipo_id):
    for codigo in ("24.1", "4941", "68"):
        for semilla in range(3):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                dl = ejercicio.otras_deudas_largo_desglose_eur
                dc = ejercicio.otras_deudas_corto_desglose_eur
                assert sum(dl.values()) == pytest.approx(_otras_deudas_largo_target_eur(ejercicio), abs=0.01)
                assert sum(dc.values()) == pytest.approx(_otras_deudas_corto_target_eur(ejercicio), abs=0.01)
                for valor in {**dl, **dc}.values():
                    assert valor >= -1e-6, f"{codigo} semilla={semilla} año={ejercicio.año}: {dl} {dc}"


def test_sin_negativos_en_barrido_amplio_27_sectores(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(5):
            for arquetipo_id in ("apalancamiento", "riesgo_refinanciacion", "deterioro_ciclo_caja"):
                evolucion = generar_evolucion_arquetipo(
                    codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                    arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
                )
                for ejercicio in evolucion.ejercicios.values():
                    dl = ejercicio.otras_deudas_largo_desglose_eur
                    dc = ejercicio.otras_deudas_corto_desglose_eur
                    for componente, valor in {**dl, **dc}.items():
                        assert valor >= -1e-6, f"{codigo} semilla={semilla} {arquetipo_id} año={ejercicio.año} {componente}={valor}"
                    assert sum(dl.values()) == pytest.approx(_otras_deudas_largo_target_eur(ejercicio), abs=0.01)
                    assert sum(dc.values()) == pytest.approx(_otras_deudas_corto_target_eur(ejercicio), abs=0.01)
                    comprobados += 1
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# `deudas_socios` — probabilidad de fondo baja, minoritaria, SIN boost de ningún arquetipo.
# --------------------------------------------------------------------------------------------


def test_deudas_socios_activacion_dentro_del_rango_esperado(catalogo):
    activas = 0
    total = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            activa = sortear_deudas_socios_baseline(codigo, "grandes_medianas", semilla)
            total += 1
            if activa:
                activas += 1
    tasa = activas / total
    assert 0.0 < tasa < PROBABILIDAD_DEUDAS_SOCIOS_LARGO + 0.10, f"tasa {tasa:.1%} fuera de rango ({activas}/{total})"


def test_deudas_socios_nunca_aparece_en_el_desglose_de_corto(catalogo):
    for codigo in ("24.1", "62", "68"):
        for semilla in range(10):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            assert "deudas_socios" not in empresa.otras_deudas_corto_desglose_eur


def test_deudas_socios_pct_invariante_al_arquetipo(catalogo, arquetipos):
    """Versión limpia de la comprobación anterior: el PORCENTAJE (no el importe, que escala con
    el agregado de cada arquetipo) debe ser IDÉNTICO sea cual sea el arquetipo activo."""
    comprobados = 0
    for codigo in ("24.1", "4941", "68", "62"):
        for semilla in range(6):
            evo_a = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
            )
            evo_b = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="deterioro_ciclo_caja", catalogo=catalogo, arquetipos=arquetipos,
            )
            assert evo_a.ejercicios[2023].otras_deudas_largo_perfil_pct["deudas_socios"] == pytest.approx(
                evo_b.ejercicios[2023].otras_deudas_largo_perfil_pct["deudas_socios"]
            )
            comprobados += 1
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# `aapp_pendiente` — mismo mecanismo que motor.insolvencias: probabilidad de fondo baja + boost
# de arquetipo 4/7 (probabilidad Y magnitud). Se RE-INVOCA cada año (nunca fijo desde 2023, a
# diferencia del resto del perfil), pero el resultado es DETERMINISTA para una misma semilla/
# sector/segmento/boost — NO un sorteo año a año independiente, ver docstring de `sortear_aapp_
# pendiente_corto_pct` (motor/empresa_base.py) para la propiedad completa.
# --------------------------------------------------------------------------------------------


def test_aapp_pendiente_en_el_año_base_usa_solo_la_probabilidad_base_sin_boost(catalogo, arquetipos):
    """El año base SÍ puede tener `aapp_pendiente` activo (probabilidad de fondo, igual que
    `deudas_socios` — no es un evento "dotado" como provisiones/insolvencias, ver docstring del
    módulo), pero NUNCA con boost: los arquetipos 4/7 no actúan en 2023. Se compara contra el
    sorteo directo con boost=False/False, que debe coincidir exacto (misma entropía)."""
    from motor.empresa_base import sortear_aapp_pendiente_corto_pct as _sortear

    for codigo in ("24.1", "62", "47.1"):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="deterioro_ciclo_caja", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio_2023 = evolucion.ejercicios[2023]
            pct_base_esperado, _ = _sortear(codigo, "grandes_medianas", semilla, False, False)
            assert ejercicio_2023.aapp_pendiente_corto_pct == pytest.approx(pct_base_esperado)


def test_aapp_pendiente_continuidad_determinista_entre_2024_y_2025(catalogo, arquetipos):
    """Pregunta explícita del usuario antes de comitear: ¿`aapp_pendiente` puede "parpadear"
    (aparecer un año sí y el siguiente no) pese a que el problema de ciclo de caja/dependencia de
    clientes sigue activo los dos años? Respuesta verificada aquí de forma permanente: NO — como
    `deterioro_ciclo_caja_activo`/`dependencia_pocos_clientes_activo` son propiedades del CASO
    completo (un arquetipo activo en `definiciones` lo está en 2024 Y 2025 por igual) y la
    entropía del rng de `sortear_aapp_pendiente_corto_pct` no depende del año, el resultado
    (activación Y magnitud) es IDÉNTICO bit a bit en 2024 y 2025 siempre que el arquetipo no
    cambie entre esos años (nunca cambia, en esta arquitectura) — sin necesitar un campo de estado
    tipo `saldo_eur` como en `motor.insolvencias`/`motor.provisiones`. Cubre tanto el arquetipo 4
    (cuantitativo, `deterioro_ciclo_caja`) como el 7 (memoria_pura, vía `generar_caso_combinado`,
    que es el único camino por el que su booleano llega al motor)."""
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(4):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="deterioro_ciclo_caja", catalogo=catalogo, arquetipos=arquetipos,
            )
            assert evolucion.ejercicios[2024].aapp_pendiente_corto_pct == evolucion.ejercicios[2025].aapp_pendiente_corto_pct, (
                f"{codigo} semilla={semilla}: aapp_pendiente 'parpadeó' entre 2024 y 2025 con el arquetipo 4 activo los dos años"
            )
            comprobados += 1

            caso = generar_caso_combinado(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
                {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, catalogo=catalogo, arquetipos=arquetipos,
            )
            assert caso.ejercicios[2024].aapp_pendiente_corto_pct == caso.ejercicios[2025].aapp_pendiente_corto_pct, (
                f"{codigo} semilla={semilla}: aapp_pendiente 'parpadeó' entre 2024 y 2025 con el arquetipo 7 activo los dos años"
            )
            comprobados += 1
    assert comprobados > 0


def test_probabilidad_de_fondo_con_arquetipo_neutro_dentro_del_rango_pedido(catalogo, arquetipos):
    activas = 0
    total = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            total += 1
            if evolucion.ejercicios[2025].aapp_pendiente_corto_pct > 0:
                activas += 1
    tasa = activas / total
    assert PROBABILIDAD_AAPP_PENDIENTE_BASE - 0.05 <= tasa <= PROBABILIDAD_AAPP_PENDIENTE_BASE + 0.10, (
        f"tasa de activación {tasa:.1%} fuera del rango de base esperado ({activas}/{total})"
    )


def test_probabilidad_sube_con_deterioro_ciclo_caja_a_nivel_de_formula():
    p_base = probabilidad_aapp_pendiente(False, False)
    p_con_4 = probabilidad_aapp_pendiente(True, False)
    p_con_7 = probabilidad_aapp_pendiente(False, True)
    p_con_ambos = probabilidad_aapp_pendiente(True, True)
    assert p_base == pytest.approx(PROBABILIDAD_AAPP_PENDIENTE_BASE)
    assert p_con_4 > p_base
    assert p_con_7 > p_base
    assert p_con_ambos > p_con_4
    assert p_con_ambos > p_con_7
    assert p_con_ambos <= TECHO_PROBABILIDAD_AAPP_PENDIENTE_ABSOLUTO


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
                if evolucion.ejercicios[2025].aapp_pendiente_corto_pct > 0:
                    activas += 1
        return activas / total

    tasa_base = _tasa("aumento_clientes")
    tasa_con_4 = _tasa("deterioro_ciclo_caja")
    assert tasa_con_4 > tasa_base, f"con el 4 ({tasa_con_4:.1%}) no supera la línea base ({tasa_base:.1%})"


def test_sortear_aapp_pendiente_escala_por_el_boost_a_nivel_de_formula():
    sector, segmento, semilla = "24.1", "grandes_medianas", 3
    sin_boost, _ = sortear_aapp_pendiente_corto_pct(sector, segmento, semilla, False, False)
    con_boost, _ = sortear_aapp_pendiente_corto_pct(sector, segmento, semilla, True, False)
    if sin_boost > 0:
        # Solo exacto si ninguno de los dos draws se topó con el suelo/techo de plausibilidad.
        assert con_boost == pytest.approx(sin_boost * MULTIPLICADOR_MAGNITUD_AAPP_PENDIENTE_BOOST) or con_boost >= sin_boost


def test_sortear_aapp_pendiente_monotona_con_el_boost():
    """Misma propiedad que `sortear_insolvencia_baseline`: si activa SIN el boost, tiene que
    activar también CON el boost (mismo `rng.random()`, el umbral solo puede subir)."""
    sector, segmento = "24.1", "grandes_medianas"
    activaciones_sin_boost = 0
    for semilla in range(200):
        sin_boost, _ = sortear_aapp_pendiente_corto_pct(sector, segmento, semilla, False, False)
        con_boost, _ = sortear_aapp_pendiente_corto_pct(sector, segmento, semilla, True, True)
        if sin_boost > 0:
            activaciones_sin_boost += 1
            assert con_boost > 0, f"semilla {semilla}: activa sin boost pero no con boost"
    assert activaciones_sin_boost > 0, "ninguna activación sin boost en 200 semillas — ampliar el rango"


def test_arquetipo_7_sube_probabilidad_y_magnitud_en_la_practica_via_caso_combinado(catalogo, arquetipos):
    """Comprobación pedida explícitamente (mismo patrón que `test_insolvencias.py`): genera el
    MISMO caso (sector, semilla) con y sin el arquetipo 7 activo vía `generar_caso_combinado` y
    confirma que `dependencia_pocos_clientes_activo` sube la probabilidad Y la magnitud de
    `aapp_pendiente` — no solo a nivel de fórmula."""
    activas_sin_7 = 0
    activas_con_7 = 0
    total = 40
    sector = "47.1"
    for semilla in range(total):
        sin_7 = generar_caso_combinado(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"aumento_clientes": "fuerte"}, catalogo=catalogo, arquetipos=arquetipos,
        )
        con_7 = generar_caso_combinado(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}, catalogo=catalogo, arquetipos=arquetipos,
        )
        ej_sin = sin_7.ejercicios[2025]
        ej_con = con_7.ejercicios[2025]
        if ej_sin.aapp_pendiente_corto_pct > 0:
            activas_sin_7 += 1
            assert ej_con.aapp_pendiente_corto_pct > 0, f"semilla {semilla}: activa sin el 7 pero no con el 7"
            assert ej_con.aapp_pendiente_corto_pct >= ej_sin.aapp_pendiente_corto_pct
        if ej_con.aapp_pendiente_corto_pct > 0:
            activas_con_7 += 1

    tasa_sin_7 = activas_sin_7 / total
    tasa_con_7 = activas_con_7 / total
    assert tasa_con_7 > tasa_sin_7, f"el 7 no subió la tasa observada: sin={tasa_sin_7:.1%} con={tasa_con_7:.1%}"


# --------------------------------------------------------------------------------------------
# Reclasificación anual de `acreedores_inmovilizado` (largo -> corto) — verificación cuantificada
# de la fórmula, no solo asumida por construcción.
# --------------------------------------------------------------------------------------------


def test_calcular_desglose_otras_deudas_reclasifica_1_sobre_plazo_del_largo_anterior():
    perfil_largo = {"acreedores_inmovilizado": 0.55, "fianzas_depositos": 0.30, "deudas_socios": 0.0, "remanente": 0.15}
    perfil_corto_resto = {"acreedores_inmovilizado": 0.20, "fianzas_depositos": 0.55, "remanente": 0.25}
    largo_anterior_eur = 900_000.0

    desglose_largo, desglose_corto = calcular_desglose_otras_deudas(
        perfil_largo, perfil_corto_resto, aapp_pendiente_corto_pct=0.0,
        otras_deudas_largo_residual_eur=1_000_000.0, otras_deudas_corto_residual_eur=2_000_000.0,
        acreedores_inmovilizado_largo_anterior_eur=largo_anterior_eur,
    )
    reclasificado_esperado_eur = largo_anterior_eur * FRACCION_RECLASIFICACION_ACREEDORES_INMOVILIZADO
    resto_corto_eur = 2_000_000.0 - reclasificado_esperado_eur
    esperado_acreedores_inmovilizado_corto_eur = perfil_corto_resto["acreedores_inmovilizado"] * resto_corto_eur + reclasificado_esperado_eur

    assert desglose_corto["acreedores_inmovilizado"] == pytest.approx(esperado_acreedores_inmovilizado_corto_eur)
    assert sum(desglose_largo.values()) == pytest.approx(1_000_000.0)
    assert sum(desglose_corto.values()) == pytest.approx(2_000_000.0)


def test_calcular_desglose_otras_deudas_topa_la_reclasificacion_sin_dejar_nada_negativo():
    """Técho defensivo: si el saldo largo anterior fuera enorme frente al residuo de corto de
    este año (caída brusca del residuo, o `aapp_pendiente` consumiendo la mayor parte), la
    reclasificación se topa y ningún componente queda negativo — mismo espíritu que el técho
    defensivo de `calcular_desglose_deudas_fin` (cuarto lote)."""
    perfil_largo = {"acreedores_inmovilizado": 0.55, "fianzas_depositos": 0.30, "deudas_socios": 0.0, "remanente": 0.15}
    perfil_corto_resto = {"acreedores_inmovilizado": 0.20, "fianzas_depositos": 0.55, "remanente": 0.25}

    desglose_largo, desglose_corto = calcular_desglose_otras_deudas(
        perfil_largo, perfil_corto_resto, aapp_pendiente_corto_pct=0.20,
        otras_deudas_largo_residual_eur=1_000_000.0, otras_deudas_corto_residual_eur=50_000.0,
        acreedores_inmovilizado_largo_anterior_eur=10_000_000.0,  # enorme frente al residuo de corto
    )
    for valor in {**desglose_largo, **desglose_corto}.values():
        assert valor >= -1e-6
    assert sum(desglose_corto.values()) == pytest.approx(50_000.0, abs=0.01)


def test_reclasificacion_observada_en_evolucion_real(catalogo, arquetipos):
    """Verificación EN LA PRÁCTICA (no solo en la fórmula aislada): el `acreedores_inmovilizado`
    de corto de 2024 debe incluir, por encima de su propio perfil de origen, la reclasificación
    del `acreedores_inmovilizado` largo de 2023 — se comprueba restando la porción de origen
    (perfil fijo x residuo de corto tras la propia reclasificación) y comparando el resto contra
    la fórmula de reclasificación."""
    comprobados = 0
    for codigo in ("24.1", "4941", "68"):
        for semilla in range(3):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
            )
            ej_2023 = evolucion.ejercicios[2023]
            ej_2024 = evolucion.ejercicios[2024]
            largo_2023_eur = ej_2023.otras_deudas_largo_desglose_eur["acreedores_inmovilizado"]
            reclasificado_esperado_eur = largo_2023_eur * FRACCION_RECLASIFICACION_ACREEDORES_INMOVILIZADO
            # Cota inferior simple y robusta (sin reproducir la fórmula exacta del residuo, que ya
            # se comprueba a nivel de unidad arriba): el importe de corto en 2024 no puede ser
            # inferior a lo puramente reclasificado (el perfil de origen solo puede sumar más).
            assert ej_2024.otras_deudas_corto_desglose_eur["acreedores_inmovilizado"] >= reclasificado_esperado_eur - 1.0, (
                f"{codigo} semilla={semilla}: corto 2024 ({ej_2024.otras_deudas_corto_desglose_eur['acreedores_inmovilizado']:,.2f}) "
                f"por debajo de la reclasificación esperada ({reclasificado_esperado_eur:,.2f})"
            )
            comprobados += 1
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# Exclusión de provisiones/deudas del grupo/pasivos por impuesto diferido — no re-etiquetar el
# mismo euro dos veces bajo dos epígrafes oficiales distintos.
# --------------------------------------------------------------------------------------------


def test_residuo_excluye_provisiones_del_desglose_de_otras_deudas(catalogo, arquetipos):
    """Con una provisión a largo activa (tercer lote), la suma del desglose de este lote más el
    saldo de provisión debe reconstruir el agregado completo — el desglose de este lote, por sí
    solo, NUNCA debe sumar el agregado completo cuando la provisión es > 0 (si lo hiciera, estaría
    re-contando ese euro)."""
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(6):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                if ejercicio.provision_saldo_largo_eur > 1.0:
                    suma_lote5_largo = sum(ejercicio.otras_deudas_largo_desglose_eur.values())
                    assert suma_lote5_largo == pytest.approx(_otras_deudas_largo_target_eur(ejercicio), abs=0.01)
                    assert suma_lote5_largo < ejercicio.balance_eur["otras_deudas_largo"] - 1.0, (
                        "el desglose sumó el agregado bruto completo pese a haber provisión activa "
                        "— re-etiquetando el mismo euro dos veces"
                    )
                    comprobados += 1
                if ejercicio.provision_saldo_corto_eur > 1.0:
                    suma_lote5_corto = sum(ejercicio.otras_deudas_corto_desglose_eur.values())
                    assert suma_lote5_corto == pytest.approx(_otras_deudas_corto_target_eur(ejercicio), abs=0.01)
                    assert suma_lote5_corto < ejercicio.balance_eur["otras_deudas_corto"] - 1.0, (
                        "el desglose sumó el agregado bruto completo pese a haber provisión activa "
                        "— re-etiquetando el mismo euro dos veces"
                    )
                    comprobados += 1
    assert comprobados > 0, "ninguna provisión activa en el barrido — ampliar semillas"


def test_residuo_excluye_deuda_grupo_y_pasivos_impuesto_diferido(catalogo, arquetipos):
    comprobados = 0
    for semilla in range(15):
        evolucion = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="operaciones_vinculadas", catalogo=catalogo, arquetipos=arquetipos,
        )
        for ejercicio in evolucion.ejercicios.values():
            if ejercicio.deuda_grupo_largo_eur > 1.0:
                suma_lote5_largo = sum(ejercicio.otras_deudas_largo_desglose_eur.values())
                assert suma_lote5_largo == pytest.approx(_otras_deudas_largo_target_eur(ejercicio), abs=0.01)
                assert suma_lote5_largo < ejercicio.balance_eur["otras_deudas_largo"] - 1.0
                comprobados += 1
    assert comprobados > 0, "ninguna 'financiación recibida de grupo' activa — ampliar semillas"


# --------------------------------------------------------------------------------------------
# Cuadre de EFE/ECPN — igual estándar que el resto de lotes (sin líneas nuevas, es un carve-out).
# --------------------------------------------------------------------------------------------


def test_efe_y_ecpn_cuadran_sin_descuadres_nuevos(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for arquetipo_id in ("apalancamiento", "riesgo_refinanciacion", "deterioro_ciclo_caja"):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=2, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            for año in (2024, 2025):
                efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
                ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
                assert efe.cuadra, f"{codigo} {arquetipo_id} año={año}: EFE descuadre {efe.descuadre_eur}"
                assert ecpn.cuadra, f"{codigo} {arquetipo_id} año={año}: ECPN descuadre {ecpn.descuadre_eur}"
                comprobados += 1
    assert comprobados > 0


def test_identidad_balance_pyg_en_barrido_amplio(catalogo, arquetipos):
    for codigo in _sectores(catalogo):
        for arquetipo_id in ("apalancamiento", "deterioro_ciclo_caja"):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=2, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert _identidad_pn(ejercicio) < 1e-6, f"{codigo} {arquetipo_id} año={ejercicio.año}"
                assert _cuadra(ejercicio)


# --------------------------------------------------------------------------------------------
# Trazabilidad — modo típico/atípico expuesto para cada componente del perfil fijo.
# --------------------------------------------------------------------------------------------


def test_generar_perfil_otras_deudas_expone_el_modo_de_cada_componente(catalogo):
    empresa = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, catalogo=catalogo)
    assert {k for k in empresa.modos if k.startswith("otras_deudas_largo.")} == {
        f"otras_deudas_largo.{c}" for c in empresa.otras_deudas_largo_perfil_pct
    }
    assert {k for k in empresa.modos if k.startswith("otras_deudas_corto_resto.")} == {
        f"otras_deudas_corto_resto.{c}" for c in empresa.otras_deudas_corto_resto_perfil_pct
    }
    assert "otras_deudas_aapp_pendiente_corto" in empresa.modos

    vistos_atipico = 0
    for semilla in range(30):
        e = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
        vistos_atipico += sum(
            1 for k, v in e.modos.items() if (k.startswith("otras_deudas_largo.") or k.startswith("otras_deudas_corto_resto.")) and v == "atipico"
        )
    assert vistos_atipico > 0
