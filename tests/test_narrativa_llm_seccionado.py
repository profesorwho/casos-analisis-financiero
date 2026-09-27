"""Verificación a ESCALA REAL del banco de verdad por sección (encargo #115-fix, cierra el
hallazgo descubierto durante el #115).

Contexto del hallazgo (ver docs/decisiones_plausibilidad.md #115-fix para el detalle completo):
con un banco de verdad GLOBAL (todos los ~278 valores de un caso real en un único conjunto), el
verificador numérico del #114 dejaba pasar cifras inventadas por pura COLISIÓN con algún valor no
relacionado del banco — un ROE inventado del 35% (real 11,4%) pasaba porque coincidía con un
"Activo no corriente = 35,6%" de otra sección/año. Medido sobre un caso real: 92/101 (91,1%) de
los porcentajes arbitrarios 0-100% pasaban contra el banco global.

Este fichero reproduce ese barrido (no solo el ejemplo puntual) contra el mismo caso real, ANTES
(banco global, con las funciones genéricas de `narrativa_llm.py`, que siguen existiendo) y
DESPUÉS (bancos por sección, `mapeo_solucion_narrativo.construir_bancos_de_verdad_por_seccion`),
como test PERMANENTE — para que esta regresión no pueda volver a colarse sin que un test lo
detecte. Todos los conteos son deterministas (mismo caso, mismo barrido) — se pinnean como
regresión, no como rango aproximado.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "renderer"))

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.efe import generar_efe
from motor.calendario_deuda import calcular_calendario_deuda
from motor.memoria import generar_caso_combinado

from mapeo_solucion_narrativo import construir_bancos_de_verdad_por_seccion, construir_paquete_verdad
from narrativa_llm import (
    NOMBRES_SECCIONES,
    construir_banco_de_verdad,
    extraer_numeros_del_texto,
    verificar_cifras,
    verificar_secciones,
)

SECCIONES_CON_BANCO_PROPIO = NOMBRES_SECCIONES[:-1]  # 1-8 — la 9 no tiene banco de referencia, ver abajo


@pytest.fixture(scope="module")
def paquete_verdad_real():
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(
        "28", "grandes_medianas", 15_000_000.0, 15,
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        catalogo=catalogo, arquetipos=arquetipos,
    )
    ejercicios = evolucion.ejercicios
    efes = {
        2024: generar_efe(ejercicios[2023], ejercicios[2024], True),
        2025: generar_efe(ejercicios[2024], ejercicios[2025], True),
    }
    calendario = calcular_calendario_deuda(evolucion)
    return construir_paquete_verdad(evolucion, ejercicios, efes, calendario, arquetipos), evolucion


def _barrido_porcentajes():
    return [f"El valor es del {p}%." for p in range(0, 101)]


def _barrido_euros():
    return [f"El importe asciende a {v} euros." for v in range(1000, 5_001_000, 50_000)]


def _barrido_dias():
    return [f"El plazo es de {d} días." for d in range(0, 366)]


def _barrido_decimales_ratio():
    return [f"El ratio es de {v / 100:.2f}." for v in range(0, 500, 5)]


def _tasa_pasan(textos, banco) -> int:
    return sum(1 for texto in textos if not verificar_cifras(texto, banco))


# --------------------------------------------------------------------------------------------
# (1) Reproduce el hallazgo original — banco GLOBAL, sigue siendo posible construirlo con las
# funciones genéricas de narrativa_llm.py (ya no se usa en la ruta de producción, pero las
# funciones siguen existiendo y deben seguir demostrando el problema que motivó el rediseño).
# --------------------------------------------------------------------------------------------

def test_banco_global_reproduce_el_hallazgo_91_por_ciento(paquete_verdad_real):
    paquete_verdad, _ = paquete_verdad_real
    banco_global = construir_banco_de_verdad(paquete_verdad)
    pasan = _tasa_pasan(_barrido_porcentajes(), banco_global)
    assert pasan == 92, (
        f"El banco global pasó {pasan}/101 porcentajes arbitrarios (se esperaban 92, el hallazgo "
        "original documentado en decisiones_plausibilidad.md #115-fix) — si este número cambió, "
        "revisa si el caso de referencia o `construir_banco_de_verdad` cambiaron."
    )


def test_banco_global_deja_pasar_roe_35_por_ciento_bug_original(paquete_verdad_real):
    """Documenta el bug ORIGINAL como regresión: el banco global (ya no usado en producción)
    sigue dejando pasar esta cifra inventada por colisión — si esto empezara a fallar, alguien
    cambió `construir_banco_de_verdad`/`verificar_cifras` de forma que ya no reproduce el
    hallazgo, y hay que revisar si el arreglo por secciones sigue siendo necesario tal cual."""
    paquete_verdad, evolucion = paquete_verdad_real
    roe_real = evolucion.plausibilidad.valores_por_año[2025].get("ratios.roe")
    assert roe_real < 0.20  # confirma que 35% está claramente alejado del valor real
    banco_global = construir_banco_de_verdad(paquete_verdad)
    fallos = verificar_cifras("La rentabilidad financiera (ROE) alcanza el 35%.", banco_global)
    assert fallos == [], "El banco global debería seguir dejando pasar esta cifra inventada (bug documentado, ya no en producción)"


# --------------------------------------------------------------------------------------------
# (2) El arreglo — bancos por sección: el ejemplo puntual del ROE=35% ahora se rechaza.
# --------------------------------------------------------------------------------------------

def test_roe_35_por_ciento_se_rechaza_contra_banco_de_su_propia_seccion(paquete_verdad_real):
    paquete_verdad, evolucion = paquete_verdad_real
    roe_real = evolucion.plausibilidad.valores_por_año[2025].get("ratios.roe")
    assert roe_real < 0.20
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    fallos = verificar_cifras("La rentabilidad financiera (ROE) alcanza el 35%.", bancos["seccion_6"])
    assert fallos == [35.0]


def test_roe_real_redondeado_sigue_pasando_contra_su_propia_seccion(paquete_verdad_real):
    """El arreglo no debe volverse tan estricto que rechace un redondeo razonable del valor
    REAL — sigue siendo una criba de errores gruesos, no de precisión perfecta."""
    paquete_verdad, evolucion = paquete_verdad_real
    roe_real_pct = round(evolucion.plausibilidad.valores_por_año[2025].get("ratios.roe") * 100)
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    fallos = verificar_cifras(f"La rentabilidad financiera (ROE) ronda el {roe_real_pct}%.", bancos["seccion_6"])
    assert fallos == []


# --------------------------------------------------------------------------------------------
# (3) Tasa de falsos positivos DESPUÉS del arreglo, por sección y por tipo de unidad — barrido
# completo (porcentajes/euros/días/decimales de ratio), pinneado como regresión. Ver
# docs/decisiones_plausibilidad.md #115-fix para la tabla completa y la discusión de las 2
# secciones (2 y 9) que quedan con una tasa todavía alta, DOCUMENTADA en vez de forzada a bajar
# con una tolerancia más estrecha sin dato que la respalde.
# --------------------------------------------------------------------------------------------

TASAS_ESPERADAS_POR_SECCION = {
    # seccion: (pasan_porcentajes, pasan_euros, pasan_dias, pasan_decimales)
    "seccion_1": (7, 0, 28, 21),
    "seccion_2": (60, 19, 81, 90),   # alto — ver nota más abajo, documentado no forzado
    "seccion_3": (15, 19, 187, 51),
    "seccion_4": (41, 0, 62, 71),
    "seccion_5": (25, 5, 87, 34),
    "seccion_6": (24, 0, 61, 51),
    "seccion_7": (7, 3, 28, 21),
    "seccion_8": (34, 0, 70, 55),
    # seccion_9 NO tiene banco de referencia — su tasa depende de lo que se cite de verdad en el
    # texto de 1-8, no de un banco fijo. Ver el bloque "(4) Sección 9 — banco DINÁMICO" más abajo.
}


@pytest.mark.parametrize("seccion", SECCIONES_CON_BANCO_PROPIO)
def test_tasa_falsos_positivos_por_seccion_pinneada(paquete_verdad_real, seccion):
    paquete_verdad, _ = paquete_verdad_real
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    banco = bancos[seccion]
    observado = (
        _tasa_pasan(_barrido_porcentajes(), banco),
        _tasa_pasan(_barrido_euros(), banco),
        _tasa_pasan(_barrido_dias(), banco),
        _tasa_pasan(_barrido_decimales_ratio(), banco),
    )
    assert observado == TASAS_ESPERADAS_POR_SECCION[seccion], (
        f"{seccion}: tasas observadas {observado} != esperadas {TASAS_ESPERADAS_POR_SECCION[seccion]} "
        "(porcentajes, euros, días, decimales de ratio) — si esto cambió, actualiza la tabla SOLO "
        "tras entender por qué (el motor cambió, el paquete de verdad cambió de forma, etc.), no "
        "para silenciar el test."
    )


def test_porcentajes_y_euros_mejoran_claramente_frente_al_banco_global_en_toda_seccion(paquete_verdad_real):
    """Comprobación de dirección, no de umbral absoluto (ver nota de la tabla de arriba: la
    tasa de "decimales de ratio" queda alta en varias secciones por una causa DISTINTA — el
    suelo `TOLERANCIA_ABSOLUTA=0.5` es ancho frente a ratios reales <1.0, no una fuga entre
    secciones — documentado en decisiones_plausibilidad.md #115-fix, no corregido aquí porque
    tocar la tolerancia es una decisión aparte que necesita su propio dato). Lo que SÍ debe
    cumplirse siempre, en TODAS las secciones sin excepción: porcentajes y euros (los 2 tipos de
    unidad del ejemplo original del hallazgo, ROE% y resultado en €) deben mejorar frente al
    banco global."""
    paquete_verdad, _ = paquete_verdad_real
    banco_global = construir_banco_de_verdad(paquete_verdad)
    pasan_global_pct = _tasa_pasan(_barrido_porcentajes(), banco_global) / 101
    pasan_global_eur = _tasa_pasan(_barrido_euros(), banco_global) / 100
    for seccion, (pct, eur, _dias, _dec) in TASAS_ESPERADAS_POR_SECCION.items():
        assert pct / 101 <= pasan_global_pct, f"{seccion}: porcentajes no mejoró frente al banco global"
        assert eur / 100 <= pasan_global_eur, f"{seccion}: euros no mejoró frente al banco global"


# --------------------------------------------------------------------------------------------
# (4) Sección 9 — banco DINÁMICO, no la unión estática de 1-8 (corrección sobre el primer diseño
# del #115-fix, que sí usaba esa unión: con ella, sección 9 seguía en 89,1%/89,1%/... falsos
# positivos —esencialmente el mismo nivel que el banco GLOBAL original— porque la unión de bancos
# de REFERENCIA incluye TODO lo que 1-8 podrían citar, no lo que realmente citaron. La corrección
# usa `narrativa_llm.verificar_secciones`, que verifica las secciones 1-8 en orden y acumula solo
# las cifras que aparecieron en su texto Y pasaron su propia verificación; esa acumulación —no
# ningún banco de referencia— es lo que se usa para verificar la sección 9. Ver decisiones_
# plausibilidad.md (entrada de este arreglo puntual sobre la fila #115-fix) para el detalle.
# --------------------------------------------------------------------------------------------

def _respuesta_bien_formada(paquete_verdad: dict) -> dict[str, str]:
    """Simula una narrativa razonable (no perfecta, no exhaustiva) citando un puñado de cifras
    REALES por sección — el mismo tipo de densidad de citas que un LLM bien comportado produciría,
    no todo lo que la sección podría citar. `seccion_9` se deja vacía aquí — el barrido la rellena."""
    r2025 = paquete_verdad["ratios_por_año"]["2025"]
    liquidez = r2025["ratios.liquidez"]
    endeudamiento_pct = round(r2025["ratios.endeudamiento"] * 100)
    roe_pct = round(r2025["ratios.roe"] * 100)
    roi_pct = round(r2025["ratios.roi"] * 100)
    resultado = paquete_verdad["pyg_por_año"]["2025"]["resultado_ejercicio_eur"]
    fm = paquete_verdad["fondo_maniobra_eur_por_año"]["2025"]
    meta = paquete_verdad["meta"]
    return {
        "seccion_1": f"El caso incorpora {meta['n_arquetipos']} arquetipos y presenta {meta['n_señales']} señales de alerta en 2025.",
        "seccion_2": f"El fondo de maniobra alcanza aproximadamente {fm / 1e6:.2f} millones de euros en 2025.",
        "seccion_3": f"La liquidez general se sitúa en torno a {liquidez:.1f} en 2025.",
        "seccion_4": f"El endeudamiento ronda el {endeudamiento_pct}% en 2025.",
        "seccion_5": f"El resultado del ejercicio ascendió a {resultado:,.0f} euros en 2025.".replace(",", "."),
        "seccion_6": f"La rentabilidad financiera (ROE) ronda el {roe_pct}% y la económica (ROI) el {roi_pct}% en 2025.",
        "seccion_7": "El flujo de explotación de 2025 es positivo.",
        "seccion_8": f"Se detectan {meta['n_señales']} señales de alerta en el caso.",
        "seccion_9": "",
    }


def _banco_dinamico_seccion_9(paquete_verdad: dict, bancos_1_a_8: dict[str, set[float]]) -> set[float]:
    """Reproduce, fuera de `verificar_secciones`, el banco acumulado que le tocaría a la sección
    9 para una respuesta bien formada dada — usado para el barrido (que necesita probar textos de
    sección 9 DISTINTOS del de la respuesta real, uno por cada valor del barrido)."""
    secciones = _respuesta_bien_formada(paquete_verdad)
    acumuladas: set[float] = set()
    for seccion in SECCIONES_CON_BANCO_PROPIO:
        texto = secciones[seccion]
        banco = bancos_1_a_8[seccion]
        numeros = extraer_numeros_del_texto(texto)
        fallos_set = set(verificar_cifras(texto, banco))
        acumuladas.update(n for n in numeros if n not in fallos_set)
    return acumuladas


def test_seccion_9_no_tiene_banco_de_referencia_en_construir_bancos_de_verdad_por_seccion(paquete_verdad_real):
    paquete_verdad, _ = paquete_verdad_real
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    assert set(bancos) == set(SECCIONES_CON_BANCO_PROPIO)
    assert "seccion_9" not in bancos


def test_banco_dinamico_de_seccion_9_es_exactamente_lo_citado_en_1_a_8(paquete_verdad_real):
    paquete_verdad, _ = paquete_verdad_real
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    acumuladas = _banco_dinamico_seccion_9(paquete_verdad, bancos)
    # 9 cifras citadas en la respuesta bien formada: 2 (arquetipos), 6 (señales), 5.07 (fondo de
    # maniobra en millones, aunque el texto usa 5,07 -> se guarda 5070000.0 el número LITERAL del
    # texto, no el original en euros), 1.8 (liquidez), 52 (endeudamiento%), 11 y 7 (ROE/ROI%),
    # 921926 (resultado), 2025 (año, estructural) — pinneado como regresión.
    assert acumuladas == {2.0, 6.0, 1.8, 52.0, 11.0, 7.0, 921926.0, 5070000.0, 2025.0}


def test_verificar_secciones_acumula_lo_mismo_que_el_calculo_manual(paquete_verdad_real):
    """`narrativa_llm.verificar_secciones` (la función real de producción) debe dar el MISMO
    resultado que el cálculo manual de arriba para la sección 9, sobre la MISMA respuesta bien
    formada (con la 9 rellena con una cifra real, que debe pasar)."""
    paquete_verdad, _ = paquete_verdad_real
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    secciones = _respuesta_bien_formada(paquete_verdad)
    secciones["seccion_9"] = "El diagnóstico conecta el ROE del 11% con las 6 señales detectadas."
    resultado = verificar_secciones(secciones, bancos)
    assert all(fallos == [] for fallos in resultado.values()), resultado


def test_seccion_9_rechaza_una_cifra_que_nunca_se_citaron_en_1_a_8(paquete_verdad_real):
    """Una cifra REAL del caso (existe en el paquete de verdad, un ratio de otra sección que no
    se citó en la respuesta) debe seguir RECHAZÁNDOSE en la sección 9 si nadie la citó antes —
    "ya se verificó" significa que apareció en el texto, no que "está en el caso"."""
    paquete_verdad, _ = paquete_verdad_real
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    secciones = _respuesta_bien_formada(paquete_verdad)
    # tesorería no se cita en ninguna de las 8 secciones bien formadas — real, pero no citada.
    tesoreria_pct = round(paquete_verdad["ratios_por_año"]["2025"]["ratios.tesoreria"] * 100)
    secciones["seccion_9"] = f"La tesorería del {tesoreria_pct}% respalda el diagnóstico."
    resultado = verificar_secciones(secciones, bancos)
    assert resultado["seccion_9"] == [float(tesoreria_pct)]


def test_seccion_9_tasa_de_falsos_positivos_dinamica_pinneada(paquete_verdad_real):
    """Repite el barrido de las 4 unidades SOLO para la sección 9, con el banco dinámico de la
    respuesta bien formada — objetivo del arreglo: un rango comparable al 7%-40% del resto de
    secciones, no el ~90% que daba la unión estática anterior."""
    paquete_verdad, _ = paquete_verdad_real
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    acumuladas = _banco_dinamico_seccion_9(paquete_verdad, bancos)

    observado = (
        _tasa_pasan(_barrido_porcentajes(), acumuladas),
        _tasa_pasan(_barrido_euros(), acumuladas),
        _tasa_pasan(_barrido_dias(), acumuladas),
        _tasa_pasan(_barrido_decimales_ratio(), acumuladas),
    )
    esperado = (9, 5, 9, 25)  # de 101, 100, 366, 100 respectivamente
    assert observado == esperado, f"seccion_9 (dinámico): observado {observado} != esperado {esperado}"

    # las 4 tasas deben quedar dentro (o por debajo) del rango 7%-40% que tienen el resto de
    # secciones — el objetivo explícito de este arreglo puntual.
    totales = (101, 100, 366, 100)
    for pasan, total in zip(observado, totales):
        assert pasan / total <= 0.40, f"seccion_9 (dinámico): {pasan}/{total} supera el 40% objetivo"


def test_seccion_9_dinamica_mejora_frente_a_la_union_estatica_anterior(paquete_verdad_real):
    """Regresión histórica: la unión ESTÁTICA que tenía el primer diseño del #115-fix (ya
    eliminada del código, `construir_bancos_de_verdad_por_seccion` ya no la calcula) daba
    90/101, 27/100, 270/366, 97/100 — prácticamente el mismo nivel que el banco global original.
    El banco DINÁMICO debe mejorar claramente en las 4 unidades."""
    paquete_verdad, _ = paquete_verdad_real
    bancos = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    acumuladas = _banco_dinamico_seccion_9(paquete_verdad, bancos)

    tasa_union_estatica_historica = (90 / 101, 27 / 100, 270 / 366, 97 / 100)
    observado = (
        _tasa_pasan(_barrido_porcentajes(), acumuladas) / 101,
        _tasa_pasan(_barrido_euros(), acumuladas) / 100,
        _tasa_pasan(_barrido_dias(), acumuladas) / 366,
        _tasa_pasan(_barrido_decimales_ratio(), acumuladas) / 100,
    )
    for obs, antes in zip(observado, tasa_union_estatica_historica):
        assert obs < antes, f"seccion_9 dinámica ({obs:.1%}) no mejoró frente a la unión estática histórica ({antes:.1%})"
