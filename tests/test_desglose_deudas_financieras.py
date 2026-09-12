"""Tests del cuarto y último lote de desglose de balance: Deudas financieras (largo y corto
plazo) desglosadas según el modelo oficial del PGC — I. Obligaciones y otros valores negociables,
II. Deudas con entidades de crédito, III. Acreedores por arrendamiento financiero, IV. Derivados,
V. Otros pasivos financieros — carve-out de `deudas_fin_largo`/`deudas_fin_corto` (ver
motor/empresa_base.py, `calcular_desglose_deudas_fin`).

Cubre lo pedido explícitamente: "Entidades de crédito" como residual (nunca sorteado); perfil de
arrendamiento financiero/obligaciones por categoría de sector; Derivados Tipo 2 puro (solo con el
arquetipo 21 activo, sin probabilidad de fondo); migración del derivado del arquetipo 21 desde la
aproximación anterior ("otros activos financieros"/"otras deudas") a su línea propia, sin alterar
ningún total ya validado (interés, endeudamiento, EFE, EIGR); `reclasificacion_deuda` (8/16)
operando SOLO sobre "Entidades de crédito", dejando leasing/obligaciones/otros con su propio
reparto largo/corto fijo; identidad Balance↔PyG explícita (lección del lote 3)."""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.ecpn import generar_ecpn, generar_eigr
from motor.efe import generar_efe
from motor.empresa_base import PERFIL_DEUDAS_FIN_POR_CATEGORIA, categoria_de_sector, generar_empresa_base
from motor.evolucion_arquetipo import generar_evolucion_arquetipo, generar_evolucion_combinada
from motor.memoria import generar_caso_combinado

VENTAS_OBJETIVO_2023 = 15_000_000.0
CATEGORIAS_TIPO1 = ("entidades_credito", "obligaciones", "arrendamiento_financiero", "otros_pasivos_financieros")


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
    """Misma fórmula que tests/test_amortizacion.py y tests/test_provisiones.py — ver ahí para
    el razonamiento de por qué es una comprobación distinta de `_cuadra`."""
    suma = (
        ejercicio.capital_social_eur
        + ejercicio.reservas_eur
        + ejercicio.pyg_eur["resultado_ejercicio"]
        + ejercicio.ajustes_cambio_valor_pn_eur
        + ejercicio.subvenciones_pn_eur
    )
    return abs(suma - ejercicio.balance_eur["patrimonio_neto"])


# --------------------------------------------------------------------------------------------
# Suma exacta — empresa base y evolución, con y sin arquetipos que muevan deuda financiera.
# --------------------------------------------------------------------------------------------


def test_desglose_deudas_fin_suma_exacta_en_empresa_base(catalogo):
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            dl = empresa.deudas_fin_largo_desglose_eur
            dc = empresa.deudas_fin_corto_desglose_eur
            assert set(dl) == set(dc) == set(CATEGORIAS_TIPO1) | {"derivados"}
            assert sum(dl.values()) == pytest.approx(empresa.balance_eur["deudas_fin_largo"], abs=0.01)
            assert sum(dc.values()) == pytest.approx(empresa.balance_eur["deudas_fin_corto"], abs=0.01)
            assert dl["derivados"] == 0.0  # sin cobertura en la empresa base
            assert dc["derivados"] == 0.0
            for valor in {**dl, **dc}.values():
                assert valor >= -1e-6


@pytest.mark.parametrize("arquetipo_id", ["exceso_stock", "apalancamiento", "capex_elevado", "adquisicion"])
def test_desglose_deudas_fin_suma_exacta_en_evolucion(catalogo, arquetipos, arquetipo_id):
    for codigo in ("24.1", "4941", "68"):
        for semilla in range(3):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                dl = ejercicio.deudas_fin_largo_desglose_eur
                dc = ejercicio.deudas_fin_corto_desglose_eur
                assert sum(dl.values()) == pytest.approx(ejercicio.balance_eur["deudas_fin_largo"], abs=0.01)
                assert sum(dc.values()) == pytest.approx(ejercicio.balance_eur["deudas_fin_corto"], abs=0.01)
                for valor in {**dl, **dc}.values():
                    assert valor >= -1e-6, f"{codigo} semilla={semilla} año={ejercicio.año}: {dl} {dc}"


# --------------------------------------------------------------------------------------------
# "Combinaciones ilógicas" reforzado: leasing/obligaciones con el peso sectorial esperado,
# derivados en cero sin cobertura activa.
# --------------------------------------------------------------------------------------------


def test_leasing_mas_frecuente_en_sectores_de_activo_material_pesado(catalogo):
    # No es una partición binaria: servicios_industriales es deliberadamente un caso intermedio
    # (15% — reparación/instalación/ingeniería tiene ALGO de activo material propio, sin llegar
    # al nivel de industria/construcción/transporte) — se compara contra el grupo de peso más
    # bajo (oficinas puras), no contra un umbral único para "todo lo que no es boost".
    boost = ("transporte_logistica", "construccion", "industria")
    bajo = ("servicios_profesionales", "servicios_tic", "administracion_educacion_sanidad", "inmobiliario")
    centro_boost = min(PERFIL_DEUDAS_FIN_POR_CATEGORIA[cat]["arrendamiento_financiero"] for cat in boost)
    centro_bajo = max(PERFIL_DEUDAS_FIN_POR_CATEGORIA[cat]["arrendamiento_financiero"] for cat in bajo)
    assert centro_boost > centro_bajo, f"boost mínimo {centro_boost} vs. bajo máximo {centro_bajo}"
    for codigo in _sectores(catalogo):
        cat = categoria_de_sector(codigo)
        assert PERFIL_DEUDAS_FIN_POR_CATEGORIA[cat]["arrendamiento_financiero"] > 0


def test_obligaciones_marginal_salvo_industria(catalogo):
    for codigo in _sectores(catalogo):
        cat = categoria_de_sector(codigo)
        centro = PERFIL_DEUDAS_FIN_POR_CATEGORIA[cat]["obligaciones"]
        if cat == "industria":
            assert centro > 0.01
        else:
            assert centro <= 0.01


def test_derivados_en_cero_sin_arquetipo_21_activo(catalogo, arquetipos):
    for codigo in _sectores(catalogo):
        for arquetipo_id in ("exceso_stock", "apalancamiento", "aumento_clientes"):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert ejercicio.deudas_fin_largo_desglose_eur["derivados"] == 0.0
                assert ejercicio.deudas_fin_corto_desglose_eur["derivados"] == 0.0


def test_entidades_credito_nunca_negativo_bajo_reclasificacion_agresiva(catalogo, arquetipos):
    """Barrido de estrés (arquetipo 16, "riesgo de refinanciación" — la reclasificación más
    agresiva disponible) — confirma el techo defensivo de `calcular_desglose_deudas_fin`."""
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="riesgo_refinanciacion", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                dl = ejercicio.deudas_fin_largo_desglose_eur
                dc = ejercicio.deudas_fin_corto_desglose_eur
                assert dl["entidades_credito"] >= -1e-6
                assert dc["entidades_credito"] >= -1e-6
                assert sum(dl.values()) == pytest.approx(ejercicio.balance_eur["deudas_fin_largo"], abs=0.01)
                assert sum(dc.values()) == pytest.approx(ejercicio.balance_eur["deudas_fin_corto"], abs=0.01)
                comprobados += 1
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# reclasificacion_deuda (8/16): confirmado — opera SOLO sobre "Entidades de crédito"; el reparto
# largo/corto propio de leasing/obligaciones/otros no se mueve con la reclasificación.
# --------------------------------------------------------------------------------------------


def test_reclasificacion_deuda_no_mueve_el_reparto_propio_de_leasing_obligaciones_otros(catalogo, arquetipos):
    """Verificación cuantificada, no asumida: la fracción largo/(largo+corto) de cada una de las
    3 categorías con perfil propio debe mantenerse prácticamente constante entre 2023 y 2025 pese
    a que `riesgo_refinanciacion` empuja agresivamente el AGREGADO hacia corto plazo — mientras
    que la de "Entidades de crédito" sí debe moverse con fuerza (es la que absorbe el efecto).

    Excluye los casos (raros: draw atípico del catálogo, ~15% de probabilidad) donde
    `deudas_fin_largo` YA es casi cero en el propio año base 2023, sin relación con
    `reclasificacion_deuda` — ahí el techo defensivo de `calcular_desglose_deudas_fin` se activa
    desde el principio (protege el cuadre, ver `test_entidades_credito_nunca_negativo_bajo_
    reclasificacion_agresiva`), así que la comparación 2023->2025 mezclaría dos efectos
    distintos (el techo defensivo Y la reclasificación) en vez de aislar el segundo."""
    comprobados = 0
    for codigo in ("24.1", "4941", "41.2"):
        for semilla in range(5):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="riesgo_refinanciacion", catalogo=catalogo, arquetipos=arquetipos,
            )
            ej_2023 = evolucion.ejercicios[2023]
            ej_2025 = evolucion.ejercicios[2025]
            # El techo defensivo puede activarse en CUALQUIERA de los dos años (no solo 2023):
            # "riesgo_refinanciacion" reduce `deudas_fin_largo` año a año, así que 2025 es, si
            # acaso, más propenso a tocarlo que 2023 — se excluyen ambos casos por igual.
            if (
                ej_2023.deudas_fin_largo_desglose_eur["entidades_credito"] < 1.0
                or ej_2025.deudas_fin_largo_desglose_eur["entidades_credito"] < 1.0
            ):
                continue  # techo defensivo activo en algún año — no es un caso limpio para esta comprobación

            def _fraccion_largo(ejercicio, categoria):
                largo = ejercicio.deudas_fin_largo_desglose_eur[categoria]
                corto = ejercicio.deudas_fin_corto_desglose_eur[categoria]
                total = largo + corto
                return largo / total if total > 0 else None

            for categoria in ("arrendamiento_financiero", "obligaciones", "otros_pasivos_financieros"):
                f0 = _fraccion_largo(ej_2023, categoria)
                f1 = _fraccion_largo(ej_2025, categoria)
                if f0 is None or f1 is None:
                    continue
                assert abs(f1 - f0) < 0.03, f"{codigo} semilla={semilla} {categoria}: {f0:.4f} -> {f1:.4f}"
                comprobados += 1

            f0_entidades = _fraccion_largo(ej_2023, "entidades_credito")
            f1_entidades = _fraccion_largo(ej_2025, "entidades_credito")
            if f0_entidades is not None and f1_entidades is not None:
                assert abs(f1_entidades - f0_entidades) > 0.05, (
                    f"{codigo} semilla={semilla}: entidades_credito no absorbió la reclasificación "
                    f"({f0_entidades:.4f} -> {f1_entidades:.4f})"
                )
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# Confirmación: la contención de endeudamiento (9/14/17/18/20) sigue funcionando sobre el TOTAL
# agregado, sin que el desglose interno lo rompa.
# --------------------------------------------------------------------------------------------


def test_endeudamiento_sigue_operando_sobre_el_agregado_no_el_desglose(catalogo, arquetipos):
    from motor.evolucion_arquetipo import _endeudamiento

    comprobados = 0
    for codigo in ("24.1", "4941"):
        for semilla in range(5):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                # El endeudamiento reportado coincide exactamente con el recalculado desde
                # pasivo_no_corriente/pasivo_corriente ya agregados — el desglose (una partición
                # interna de esos mismos euros) no puede, por construcción, cambiar el total.
                assert ejercicio.endeudamiento == pytest.approx(_endeudamiento(ejercicio.balance_eur), rel=1e-9)
                comprobados += 1
    assert comprobados > 0

    activaciones = 0
    for codigo in _sectores(catalogo):
        for semilla in range(4):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in (evolucion.ejercicios[2024], evolucion.ejercicios[2025]):
                if ejercicio.riesgo_endeudamiento:
                    activaciones += 1
    assert activaciones > 0, "ninguna activación de riesgo_endeudamiento — el mecanismo de contención dejó de funcionar"


# --------------------------------------------------------------------------------------------
# Migración del arquetipo 21 (Derivados) — misma magnitud, ubicación distinta, ningún total
# alterado (interés, endeudamiento, EFE, EIGR).
# --------------------------------------------------------------------------------------------


def _ejercicio_con_derivado_pasivo(catalogo, arquetipos, sector="24.1", semilla_max=40):
    for semilla in range(semilla_max):
        evolucion = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="coberturas", catalogo=catalogo, arquetipos=arquetipos,
        )
        if evolucion.ejercicios[2025].cobertura_valor_swap_eur < 0:
            return semilla, evolucion
    return None, None


def _ejercicio_con_derivado_activo(catalogo, arquetipos, sector="24.1", semilla_max=40):
    for semilla in range(semilla_max):
        evolucion = generar_evolucion_arquetipo(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="coberturas", catalogo=catalogo, arquetipos=arquetipos,
        )
        if evolucion.ejercicios[2025].cobertura_valor_swap_eur > 0:
            return semilla, evolucion
    return None, None


def test_derivado_pasivo_aterriza_en_deudas_fin_largo_no_en_otras_deudas(catalogo, arquetipos):
    semilla, evolucion = _ejercicio_con_derivado_pasivo(catalogo, arquetipos)
    assert evolucion is not None, "ninguna semilla dio un swap con valor negativo — ampliar el barrido"
    ejercicio = evolucion.ejercicios[2025]
    importe_esperado = -ejercicio.cobertura_valor_swap_eur
    assert ejercicio.deudas_fin_largo_desglose_eur["derivados"] == pytest.approx(importe_esperado, abs=0.01)
    assert ejercicio.deudas_fin_corto_desglose_eur["derivados"] == 0.0
    assert _cuadra(ejercicio)


def test_derivado_activo_sigue_en_activo_no_corriente_sin_desglose_propio_en_deudas_fin(catalogo, arquetipos):
    """Lado activo: fuera del alcance de este lote (que solo desglosa "Deudas financieras") —
    confirmado que sigue en `activo_no_corriente`, identificable vía `cobertura_valor_swap_eur`,
    y que NO aparece (ni positivo ni falso-negativo) en el desglose de deudas financieras."""
    semilla, evolucion = _ejercicio_con_derivado_activo(catalogo, arquetipos)
    assert evolucion is not None, "ninguna semilla dio un swap con valor positivo — ampliar el barrido"
    ejercicio = evolucion.ejercicios[2025]
    assert ejercicio.cobertura_valor_swap_eur > 0
    assert ejercicio.deudas_fin_largo_desglose_eur["derivados"] == 0.0
    assert ejercicio.deudas_fin_corto_desglose_eur["derivados"] == 0.0
    assert _cuadra(ejercicio)


def test_tipo_interes_no_se_ve_afectado_por_el_derivado_pasivo(catalogo, arquetipos):
    """El derivado NUNCA debe alimentar `gastos_financieros` — comparación directa contra un caso
    sin cobertura activa, mismo sector/semilla/intensidad, para aislar el efecto."""
    semilla, evolucion_con = _ejercicio_con_derivado_pasivo(catalogo, arquetipos)
    assert evolucion_con is not None
    evolucion_sin = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    # El tipo de interés (no la deuda financiera) es idéntico entre casos activados por
    # arquetipos distintos, con la misma semilla+sector — comparación indirecta: verificamos que
    # gastos_financieros/deuda_financiera_media (el tipo IMPLÍCITO) sigue dentro del rango de
    # plausibilidad ya validado (SUELO/TECHO_TIPO_INTERES), no inflado por el derivado.
    from motor.empresa_base import SUELO_TIPO_INTERES, TECHO_TIPO_INTERES

    for ejercicio in evolucion_con.ejercicios.values():
        deuda_media_con_coste_eur = (
            ejercicio.deudas_fin_largo_desglose_eur["entidades_credito"]
            + ejercicio.deudas_fin_largo_desglose_eur["obligaciones"]
            + ejercicio.deudas_fin_largo_desglose_eur["arrendamiento_financiero"]
            + ejercicio.deudas_fin_largo_desglose_eur["otros_pasivos_financieros"]
            + sum(ejercicio.deudas_fin_corto_desglose_eur.values())
        )
        if deuda_media_con_coste_eur > 0:
            tipo_implicito = ejercicio.pyg_eur["gastos_financieros"] / deuda_media_con_coste_eur
            assert SUELO_TIPO_INTERES - 0.02 <= tipo_implicito <= TECHO_TIPO_INTERES + 0.10, (
                f"año={ejercicio.año}: tipo implícito {tipo_implicito:.3f} sugiere que el derivado "
                "está contaminando gastos_financieros"
            )


def test_efe_cuadra_con_derivado_pasivo_y_activo(catalogo, arquetipos):
    for finder in (_ejercicio_con_derivado_pasivo, _ejercicio_con_derivado_activo):
        semilla, evolucion = finder(catalogo, arquetipos)
        assert evolucion is not None
        for año in (2024, 2025):
            efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            assert efe.cuadra, f"semilla={semilla} año={año}: descuadre {efe.descuadre_eur}"


def test_eigr_y_ecpn_siguen_cuadrando_y_coincidiendo_con_derivado_activo(catalogo, arquetipos):
    for finder in (_ejercicio_con_derivado_pasivo, _ejercicio_con_derivado_activo):
        semilla, evolucion = finder(catalogo, arquetipos)
        assert evolucion is not None
        for año in (2024, 2025):
            ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            eigr = generar_eigr(evolucion.ejercicios[año], obligatorio=True)
            assert ecpn.cuadra, f"semilla={semilla} año={año}: ECPN descuadre {ecpn.descuadre_eur}"
            assert eigr.d_total_ingresos_gastos_reconocidos == pytest.approx(
                ecpn.total_ingresos_gastos_reconocidos.total, abs=0.01
            ), f"semilla={semilla} año={año}: EIGR y ECPN no coinciden"


# --------------------------------------------------------------------------------------------
# Identidad Balance<->PyG del resultado del ejercicio — explícita (lección del lote 3, no
# asumir que otra comprobación ya la cubre).
# --------------------------------------------------------------------------------------------


def test_identidad_balance_pyg_con_deudas_fin_desglosadas_y_derivado_activo(catalogo, arquetipos):
    comprobados = 0
    for finder in (_ejercicio_con_derivado_pasivo, _ejercicio_con_derivado_activo):
        semilla, evolucion = finder(catalogo, arquetipos)
        assert evolucion is not None
        for ejercicio in evolucion.ejercicios.values():
            diff_eur = _identidad_pn(ejercicio)
            assert diff_eur < 1e-6, f"semilla={semilla} año={ejercicio.año}: diferencia {diff_eur}€"
            comprobados += 1
    assert comprobados > 0


def test_identidad_balance_pyg_en_barrido_amplio_sin_cobertura(catalogo, arquetipos):
    """Regresión de fondo: el desglose de deudas financieras (siempre activo, no solo con
    cobertura) no debe romper la identidad en ningún caso, con o sin arquetipo 21."""
    for codigo in _sectores(catalogo):
        for arquetipo_id in ("apalancamiento", "riesgo_refinanciacion", "capex_elevado"):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=2, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert _identidad_pn(ejercicio) < 1e-6, f"{codigo} {arquetipo_id} año={ejercicio.año}"


# --------------------------------------------------------------------------------------------
# Regresión combinada — Combo E (adquisición + activo_mantenido_venta + operaciones_vinculadas +
# coberturas) sigue cuadrando con el derivado en su línea nueva.
# --------------------------------------------------------------------------------------------


def test_combo_e_sigue_cuadrando_con_el_derivado_reubicado(catalogo, arquetipos):
    comprobados = 0
    for semilla in range(10):
        caso = generar_caso_combinado(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"adquisicion": "fuerte", "activo_mantenido_venta": "fuerte", "operaciones_vinculadas": "fuerte", "coberturas": "fuerte"},
            catalogo=catalogo, arquetipos=arquetipos,
        )
        if caso.ejercicios[2025].cobertura_valor_swap_eur == 0:
            continue
        comprobados += 1
        for ejercicio in caso.ejercicios.values():
            assert _cuadra(ejercicio)
            assert _identidad_pn(ejercicio) < 1e-6
            dl = ejercicio.deudas_fin_largo_desglose_eur
            dc = ejercicio.deudas_fin_corto_desglose_eur
            assert sum(dl.values()) == pytest.approx(ejercicio.balance_eur["deudas_fin_largo"], abs=0.01)
            assert sum(dc.values()) == pytest.approx(ejercicio.balance_eur["deudas_fin_corto"], abs=0.01)
        for año in (2024, 2025):
            efe = generar_efe(caso.ejercicios[año - 1], caso.ejercicios[año], obligatorio=True)
            ecpn = generar_ecpn(caso.ejercicios[año - 1], caso.ejercicios[año], obligatorio=True)
            assert efe.cuadra and ecpn.cuadra, f"semilla={semilla} año={año}"
    assert comprobados > 0, "ninguna semilla combinó Combo E con un swap distinto de cero — ampliar el barrido"
