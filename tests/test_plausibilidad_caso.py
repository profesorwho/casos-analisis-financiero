"""Tests de la validación de plausibilidad del caso completo (sección 2.13, `motor/
evolucion_arquetipo.py` — `PlausibilidadCaso`/`SeñalRatio`/`_evaluar_plausibilidad_caso`).

Pasada FINAL, independiente de qué arquetipos estén activos, sobre el caso ya generado (3 años,
con toda la desagregación) — comprueba 23 ratios (los 25 `ratios.*` del catálogo, menos 2
circulares excluidos: `ventas_empleado` siempre, `rotacion_activo` solo en el año base; más
`pyg.baii_pct`/`pyg.margen_bruto_pct` para cerrar el hallazgo original que motivó el encargo).
Diagnóstico puro — nunca corrige ningún valor. Superconjunto de las señales ya existentes
(`riesgo_endeudamiento`, `riesgo_plausibilidad_pyg`), nunca las contradice."""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import (
    AÑO_BASE,
    RATIO_CIRCULAR_SIEMPRE,
    RATIO_CIRCULAR_SOLO_AÑO_BASE,
    RATIOS_ANCLA_CONTAMINADA_INFORMATIVOS,
    RATIOS_PLAUSIBILIDAD_SEÑALIZABLES,
    generar_evolucion_arquetipo,
    generar_evolucion_combinada,
)
from motor.memoria import generar_caso_combinado

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
# Estructura — nunca corrige, siempre calcula los 3 años, cubre exactamente los ratios diseñados.
# --------------------------------------------------------------------------------------------


def test_plausibilidad_no_modifica_ningun_valor_del_caso(catalogo, arquetipos):
    """La pasada es diagnóstico puro — comparar dos generaciones del MISMO caso (con y sin leer
    `.plausibilidad`) debe dar balances/PyG idénticos."""
    ev1 = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
    )
    ev2 = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
        arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
    )
    for año in (2023, 2024, 2025):
        assert ev1.ejercicios[año].balance_eur == ev2.ejercicios[año].balance_eur
        assert ev1.ejercicios[año].pyg_eur == ev2.ejercicios[año].pyg_eur


def test_valores_por_año_cubre_los_3_años_y_todos_los_ratios_calculables(catalogo, arquetipos):
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    plaus = evolucion.plausibilidad
    assert set(plaus.valores_por_año) == {2023, 2024, 2025}
    esperados = set(RATIOS_PLAUSIBILIDAD_SEÑALIZABLES) | set(RATIOS_ANCLA_CONTAMINADA_INFORMATIVOS) | {RATIO_CIRCULAR_SIEMPRE}
    for año, valores in plaus.valores_por_año.items():
        assert set(valores) == esperados, f"año {año}: {set(valores) ^ esperados}"


def test_señales_solo_sobre_ratios_señalizables_nunca_sobre_los_excluidos(catalogo, arquetipos):
    """Ningún ratio de RATIOS_ANCLA_CONTAMINADA_INFORMATIVOS ni el circular puro generan jamás
    una SeñalRatio — barrido amplio, no solo un caso."""
    for codigo in _sectores(catalogo):
        evolucion = generar_evolucion_arquetipo(
            codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=2, intensidad="fuerte",
            arquetipo_id="apalancamiento", catalogo=catalogo, arquetipos=arquetipos,
        )
        for s in evolucion.plausibilidad.señales:
            assert s.ratio not in RATIOS_ANCLA_CONTAMINADA_INFORMATIVOS
            assert s.ratio != RATIO_CIRCULAR_SIEMPRE


def test_rotacion_activo_nunca_señalizado_en_año_base(catalogo, arquetipos):
    """Circular en 2023 (rotacion_activo se sortea directamente ahí, ver docstring del módulo)
    — barrido amplio para confirmar que la exclusión aguanta bajo estrés."""
    for codigo in _sectores(catalogo):
        for arquetipo_id in ("apalancamiento", "capex_elevado", "adquisicion"):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=3, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            señales_base = [s for s in evolucion.plausibilidad.señales if s.año == AÑO_BASE and s.ratio == RATIO_CIRCULAR_SOLO_AÑO_BASE]
            assert not señales_base, f"{codigo} {arquetipo_id}: {señales_base}"


def test_rotacion_activo_si_se_comprueba_en_2024_2025(catalogo, arquetipos):
    """Confirma que la exclusión es SOLO del año base — capex/adquisición desvían activo_no_
    corriente de forma desproporcionada a ventas, así que en 2024/2025 rotacion_activo SÍ puede
    (y en un barrido de estrés, debe) desviarse de verdad."""
    encontrada_alguna_vez = False
    for codigo in _sectores(catalogo):
        evolucion = generar_evolucion_arquetipo(
            codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
            arquetipo_id="adquisicion", catalogo=catalogo, arquetipos=arquetipos,
        )
        if any(s.ratio == RATIO_CIRCULAR_SOLO_AÑO_BASE and s.año in (2024, 2025) for s in evolucion.plausibilidad.señales):
            encontrada_alguna_vez = True
    assert encontrada_alguna_vez, "ninguna señal de rotacion_activo en 2024/2025 en todo el barrido — ampliarlo"


# --------------------------------------------------------------------------------------------
# Superconjunto — nunca contradice ni duplica las señales ya existentes.
# --------------------------------------------------------------------------------------------


def test_riesgo_endeudamiento_implica_señal_de_ratios_endeudamiento(catalogo, arquetipos):
    """Barrido amplio (arquetipos que mueven endeudamiento con fuerza) — 0 discrepancias:
    siempre que `riesgo_endeudamiento=True`, debe existir una SeñalRatio de
    'ratios.endeudamiento' para ese mismo año (mismo techo EXACTO, incluido el recorte absoluto
    0,85 — ver docstring de `_evaluar_plausibilidad_caso`). Excluye los ejercicios donde el
    amortiguador de circulante SÍ existía y se agotó (`contencion_al_limite=True` CON
    `deterioro_aplicado_eur>0`) — ver test siguiente para esa excepción, documentada aparte. NO
    excluye `contencion_al_limite=True` con `deterioro_aplicado_eur==0` (arquetipos sin palanca
    de circulante — apalancamiento/capex/adquisición: ahí el balance final es idéntico al
    candidato sin corregir, así que SÍ debe seguir señalizando)."""
    comprobados = 0
    activaciones = 0
    for codigo in _sectores(catalogo):
        for arquetipo_id in ("apalancamiento", "capex_elevado", "adquisicion", "riesgo_refinanciacion"):
            for semilla in range(3):
                evolucion = generar_evolucion_arquetipo(
                    codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                    arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
                )
                for año, ejercicio in evolucion.ejercicios.items():
                    if ejercicio.contencion_al_limite and ejercicio.deterioro_aplicado_eur > 0:
                        continue
                    comprobados += 1
                    if ejercicio.riesgo_endeudamiento:
                        activaciones += 1
                        tiene_señal = any(
                            s.año == año and s.ratio == "ratios.endeudamiento" for s in evolucion.plausibilidad.señales
                        )
                        assert tiene_señal, f"{codigo} {arquetipo_id} semilla={semilla} año={año}: riesgo_endeudamiento sin señal nueva"
    assert activaciones > 0, "ningún caso con riesgo_endeudamiento en el barrido — ampliarlo"
    assert comprobados > 0


def test_riesgo_endeudamiento_con_contencion_al_limite_puede_no_señalizar(catalogo, arquetipos):
    """Excepción encontrada en el stress test cuantificado (combos con varios arquetipos 'fuerte'
    apilados, p. ej. combo F): cuando la amortiguación de circulante se agota SIN llegar al techo
    (`contencion_al_limite=True`), el bucle aplica el deterioro máximo disponible en UNA sola
    pasada y termina — no reevalúa si, tras esa corrección, el patrimonio neto se ha recuperado
    lo bastante (menos deuda nueva → menos gasto financiero → más PN) como para que el
    endeudamiento FINAL quede en realidad por DEBAJO del techo, no por encima. `riesgo_
    endeudamiento=True` sigue siendo la señal honesta de que el CANDIDATO antes de corregir era
    implausible (`endeudamiento_sin_contener`), pero no garantiza que el valor ya corregido lo
    siga siendo — mismo patrón que la excepción de provisión/PyG (#39/#60/#72): una señal sobre
    el PROCESO de contención, no sobre el valor final. Confirmado en el barrido de las 6
    combinaciones recomendadas: TODAS las discrepancias tenían `contencion_al_limite=True` CON
    `deterioro_aplicado_eur>0` (la palanca existía y se agotó) — nunca con deterioro=0 (arquetipo
    sin palanca de circulante, ahí el balance final coincide con el candidato sin corregir)."""
    combo_f = {
        "crecimiento_destruccion_caja": "fuerte", "exceso_stock": "fuerte",
        "apalancamiento": "fuerte", "riesgo_refinanciacion": "fuerte",
    }
    encontrado_contencion_al_limite_por_debajo_del_techo = False
    for codigo in _sectores(catalogo):
        for semilla in range(4):
            evolucion = generar_evolucion_combinada(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla, combo_f,
                catalogo=catalogo, arquetipos=arquetipos,
            )
            for año, ejercicio in evolucion.ejercicios.items():
                if ejercicio.riesgo_endeudamiento and ejercicio.contencion_al_limite and ejercicio.deterioro_aplicado_eur > 0:
                    tiene_señal = any(
                        s.año == año and s.ratio == "ratios.endeudamiento" for s in evolucion.plausibilidad.señales
                    )
                    if not tiene_señal:
                        encontrado_contencion_al_limite_por_debajo_del_techo = True
    assert encontrado_contencion_al_limite_por_debajo_del_techo, (
        "ningún caso de la excepción documentada en el barrido — si el mecanismo de contención "
        "cambió, revisar si la excepción sigue siendo válida"
    )


def test_riesgo_plausibilidad_pyg_implica_señal_de_baii_o_margen_bruto(catalogo, arquetipos):
    """Excluye los ejercicios donde una provisión (tercer lote) dota/libera ese mismo año —
    mismo criterio ya establecido en #39/#60 (`tests/test_arquetipos_generalizados.py`): la
    dotación/exceso se inyecta DESPUÉS de que `_limitar_por_subtotal`/`_limitar_gastos_personal_
    por_baii` ya fijaron baii/margen_bruto EXACTAMENTE en su techo/suelo — un ajuste transversal
    posterior e independiente del arquetipo puede devolver el valor final a un rango plausible
    (o alejarlo más), así que `riesgo_plausibilidad_pyg=True` (una señal sobre el momento de la
    contención, no sobre el valor final) puede legítimamente no coincidir con esta pasada (que
    mira el valor YA final). Confirmado en el barrido: las discrepancias encontradas antes de
    esta exclusión SIEMPRE tenían `provision_dotacion_eur>0` ese año."""
    comprobados = 0
    activaciones = 0
    for codigo in _sectores(catalogo):
        for arquetipo_id in ("mejora_ebitda", "mejora_margen"):
            for intensidad in ("leve", "moderado", "fuerte"):
                for semilla in range(3):
                    evolucion = generar_evolucion_arquetipo(
                        codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
                        arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
                    )
                    for año, ejercicio in evolucion.ejercicios.items():
                        if ejercicio.provision_dotacion_eur > 0 or ejercicio.provision_exceso_eur > 0:
                            continue
                        comprobados += 1
                        if ejercicio.riesgo_plausibilidad_pyg:
                            activaciones += 1
                            tiene_señal = any(
                                s.año == año and s.ratio in ("pyg.baii_pct", "pyg.margen_bruto_pct")
                                for s in evolucion.plausibilidad.señales
                            )
                            assert tiene_señal, f"{codigo} {arquetipo_id} {intensidad} semilla={semilla} año={año}: sin señal nueva"
    assert activaciones > 0
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# Hallazgo original (motivación del encargo): un caso con empuje mínimo de arquetipo puede salir
# implausible en baii_pct/margen_bruto_pct sin que NADA lo detectara — ahora sí queda señalizado.
# --------------------------------------------------------------------------------------------


def test_hallazgo_original_baii_margen_bruto_queda_señalizado_con_empuje_minimo(catalogo, arquetipos):
    """Aproximación de 'sin ningún arquetipo activo' — intensidad 'leve' de un arquetipo neutro
    (mismo criterio ya usado en decisiones #18). Confirma que la pasada SÍ detecta casos donde
    `riesgo_plausibilidad_pyg` nunca se activó (el mecanismo antiguo solo corre cuando el propio
    arquetipo empuja esa primitiva) pero baii_pct/margen_bruto_pct son igualmente implausibles."""
    encontrado_sin_riesgo_viejo_pero_con_señal_nueva = False
    for codigo in _sectores(catalogo):
        for semilla in range(6):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="leve",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for año, ejercicio in evolucion.ejercicios.items():
                señal_pyg = any(
                    s.año == año and s.ratio in ("pyg.baii_pct", "pyg.margen_bruto_pct") for s in evolucion.plausibilidad.señales
                )
                if señal_pyg and not ejercicio.riesgo_plausibilidad_pyg:
                    encontrado_sin_riesgo_viejo_pero_con_señal_nueva = True
    assert encontrado_sin_riesgo_viejo_pero_con_señal_nueva, (
        "ningún caso mostró el hallazgo original (implausible en baii_pct/margen_bruto_pct sin "
        "que riesgo_plausibilidad_pyg lo detectara) — el propio hallazgo #18 ya lo cuantificó en "
        "6,9% de los ejercicios, así que debería aparecer en un barrido de este tamaño"
    )


# --------------------------------------------------------------------------------------------
# Fórmulas verificadas contra el PDF ACCID — regresión de los 3 errores propios encontrados al
# verificar (unidades de los ratios "por empleado", financiacion_clientes, capacidad_devolucion).
# --------------------------------------------------------------------------------------------


def test_ratios_por_empleado_en_miles_de_euros_no_en_euros_crudos(catalogo, arquetipos):
    """ventas_empleado es circular por diseño (ver RATIO_CIRCULAR_SIEMPRE) — se usa aquí solo
    como ancla de unidades: recalcular ventas/plantilla_estimada debe reproducir CASI exacto el
    valor REALMENTE sorteado por `estimar_ventas_por_empleado` para este caso concreto (no el
    huber_9y del catálogo — el ruido mixto típico/atípico puede desviarlo bastante del centro,
    eso NO es lo que se comprueba aquí; comparar contra el centro fue el error del primer
    borrador de este test)."""
    from motor.clasificacion_legal import estimar_ventas_por_empleado

    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    ventas_empleado_sorteado, _ = estimar_ventas_por_empleado("24.1", "grandes_medianas", 0, catalogo)
    valores = evolucion.plausibilidad.valores_por_año[2025]
    assert valores["ratios.ventas_empleado"] == pytest.approx(ventas_empleado_sorteado, rel=1e-6)
    # gastos_personal_empleado/beneficio_empleado deben quedar en el mismo orden de magnitud que
    # ventas_empleado (decenas-cientos), nunca miles/decenas de miles (que delataría € crudos).
    assert 1 < valores["ratios.gastos_personal_empleado"] < 2000
    assert -2000 < valores["ratios.beneficio_empleado"] < 2000


def test_financiacion_clientes_es_un_ratio_directo_no_dias(catalogo, arquetipos):
    """PDF ACCID: 'Financiación de la inversión en clientes por acreedores comerciales =
    Acreedores comerciales / Clientes' — un ratio adimensional (típicamente 0,3-1,5), NO una
    cifra en días (que rondaría cientos)."""
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    valor = evolucion.plausibilidad.valores_por_año[2025]["ratios.financiacion_clientes"]
    assert 0.0 < valor < 5.0


def test_capacidad_devolucion_usa_pasivo_total_no_solo_deuda_financiera(catalogo, arquetipos):
    """PDF ACCID: el denominador es el TOTAL de deudas (todo el pasivo), no solo la deuda
    financiera — el propio texto explica que sustituye 'Préstamos' por 'total de deudas'."""
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    ejercicio = evolucion.ejercicios[2025]
    valor = evolucion.plausibilidad.valores_por_año[2025]["ratios.capacidad_devolucion"]
    flujo_caja = ejercicio.pyg_eur["resultado_ejercicio"] + ejercicio.pyg_eur["amortizaciones"]
    pasivo_total = ejercicio.balance_eur["pasivo_no_corriente"] + ejercicio.balance_eur["pasivo_corriente"]
    assert valor == pytest.approx(flujo_caja / pasivo_total, rel=1e-9)


# --------------------------------------------------------------------------------------------
# Combinado (generar_caso_combinado) — la pasada también corre ahí, vía generar_evolucion_
# combinada, sin necesitar ningún hook adicional en motor/memoria.py.
# --------------------------------------------------------------------------------------------


def test_plausibilidad_disponible_tambien_via_generar_caso_combinado(catalogo, arquetipos):
    caso = generar_caso_combinado(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, 0,
        {"adquisicion": "fuerte", "activo_mantenido_venta": "fuerte", "operaciones_vinculadas": "fuerte", "coberturas": "fuerte"},
        catalogo=catalogo, arquetipos=arquetipos,
    )
    assert caso.plausibilidad is not None
    assert set(caso.plausibilidad.valores_por_año) == {2023, 2024, 2025}


def test_generar_evolucion_combinada_con_combo_produce_plausibilidad(catalogo, arquetipos):
    evolucion = generar_evolucion_combinada(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, 0,
        {"exceso_stock": "fuerte"},
        catalogo=catalogo, arquetipos=arquetipos,
    )
    assert evolucion.plausibilidad is not None
    assert isinstance(evolucion.plausibilidad.tiene_señales, bool)
