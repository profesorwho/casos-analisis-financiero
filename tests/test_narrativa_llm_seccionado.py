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
from narrativa_llm import NOMBRES_SECCIONES, construir_banco_de_verdad, verificar_cifras


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
    "seccion_9": (90, 27, 270, 97),  # UNIÓN de 1-8 por diseño — ver decisiones #115-fix
}


@pytest.mark.parametrize("seccion", NOMBRES_SECCIONES)
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
        if seccion == "seccion_9":
            continue  # unión deliberada de 1-8, no se espera mejora frente al global
        assert pct / 101 <= pasan_global_pct, f"{seccion}: porcentajes no mejoró frente al banco global"
        assert eur / 100 <= pasan_global_eur, f"{seccion}: euros no mejoró frente al banco global"
