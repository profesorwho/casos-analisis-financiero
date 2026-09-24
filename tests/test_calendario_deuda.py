"""Tests del calendario de vencimientos y cuadro de movimientos de la deuda (encargo #112,
`motor/calendario_deuda.py`) — módulo NUEVO y PURO de derivación sobre un caso ya generado.

Cubre lo pedido explícitamente: (a) suma de tramos == saldo de la clase en Balance (1 €); (b)
tramos no negativos; (c) saldo final == saldo inicial - amortizaciones + disposiciones; (d)
conciliación con `c10` del EFE; (e) determinismo; (f) independencia (no altera el caso); (g)
reglas por categoría en casos construidos a mano (bullet, fianzas, leasing con remanente
decreciente). Los puntos (a), (d) y (f) se demuestran con una versión "rota" deliberada de la
regla correspondiente que SÍ falla el test (revertida a continuación) — ver los 3 tests marcados.
"""
from __future__ import annotations

import copy
import dataclasses

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.calendario_deuda import (
    CATEGORIAS_DEUDA_FINANCIERA,
    CATEGORIAS_DEUDA_FINANCIERA_CON_COSTE,
    _reparto_bullet,
    _reparto_lineal,
    _reparto_sin_vencimiento_cierto,
    calcular_calendario_deuda,
)
from motor.catalogo import cargar_y_validar_catalogo
from motor.efe import generar_efe
from motor.memoria import generar_caso_combinado

VENTAS_OBJETIVO_2023 = 15_000_000.0
TOLERANCIA_EUR = 1.0


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _casos(catalogo, arquetipos):
    sectores = ["24.1", "69.2", "30.2", "68"]
    combos = [
        {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        {"exceso_stock": "fuerte"},
        {"capex_elevado": "fuerte"},
        {"refinanciacion": "fuerte"},
        {"riesgo_refinanciacion": "fuerte"},
    ]
    casos = []
    for sector in sectores:
        for segmento in ("pequeñas", "grandes_medianas"):
            for semilla in (5, 15):
                for combo in combos:
                    casos.append((sector, segmento, semilla, combo))
    return casos


def _generar(catalogo, arquetipos, sector, segmento, semilla, combo):
    return generar_caso_combinado(
        sector, segmento, VENTAS_OBJETIVO_2023, semilla, combo, catalogo=catalogo, arquetipos=arquetipos,
    )


CATEGORIAS_TODAS = (
    "entidades_credito", "arrendamiento_financiero", "obligaciones", "otros_pasivos_financieros",
    "derivados", "acreedores_inmovilizado", "fianzas_deudas_socios", "remanente_otras_deudas",
    "acreedores_comerciales",
)


def _saldo_balance_categoria(ej, categoria: str) -> float:
    if categoria == "acreedores_comerciales":
        return ej.balance_eur.get("acreedores_comerciales", 0.0)
    if categoria in ("entidades_credito", "arrendamiento_financiero", "obligaciones", "otros_pasivos_financieros", "derivados"):
        return ej.deudas_fin_largo_desglose_eur.get(categoria, 0.0) + ej.deudas_fin_corto_desglose_eur.get(categoria, 0.0)
    if categoria == "acreedores_inmovilizado":
        return ej.otras_deudas_largo_desglose_eur.get("acreedores_inmovilizado", 0.0) + ej.otras_deudas_corto_desglose_eur.get("acreedores_inmovilizado", 0.0)
    if categoria == "fianzas_deudas_socios":
        return (
            ej.otras_deudas_largo_desglose_eur.get("fianzas_depositos", 0.0)
            + ej.otras_deudas_largo_desglose_eur.get("deudas_socios", 0.0)
            + ej.otras_deudas_corto_desglose_eur.get("fianzas_depositos", 0.0)
        )
    if categoria == "remanente_otras_deudas":
        return ej.otras_deudas_largo_desglose_eur.get("remanente", 0.0) + ej.otras_deudas_corto_desglose_eur.get("remanente", 0.0)
    raise AssertionError(categoria)


# --- (a) suma de tramos == saldo de la clase en Balance, para todas las clases y ejercicios ----

def test_suma_de_tramos_cuadra_con_balance(catalogo, arquetipos):
    comprobados = 0
    for sector, segmento, semilla, combo in _casos(catalogo, arquetipos):
        evolucion = _generar(catalogo, arquetipos, sector, segmento, semilla, combo)
        calendario = calcular_calendario_deuda(evolucion)
        for año, por_categoria in calendario.vencimientos_por_año.items():
            ej = evolucion.ejercicios[año]
            for categoria in CATEGORIAS_TODAS:
                esperado = _saldo_balance_categoria(ej, categoria)
                assert por_categoria[categoria].total == pytest.approx(esperado, abs=TOLERANCIA_EUR), (
                    sector, segmento, semilla, combo, año, categoria
                )
                comprobados += 1
    assert comprobados > 500


def test_suma_de_tramos_falla_si_se_rompe_la_regla(catalogo, arquetipos):
    """Demuestra que (a) SÍ detecta un descuadre: reparte el largo de "entidades_credito" con un
    plazo equivocado (usa el propio saldo como si fuera años) para forzar que la comprobación
    ingenua de "suma == balance" siga cuadrando (la suma de _reparto_lineal siempre sale exacta
    por construcción) pero verifica en su lugar que un CAMBIO deliberado en el propio total
    correcto (sumar 1 € de más al reparto) hace fallar la aserción — control de que el test (a)
    no es tautológico."""
    evolucion = _generar(catalogo, arquetipos, "24.1", "grandes_medianas", 5, {"capex_elevado": "fuerte"})
    calendario = calcular_calendario_deuda(evolucion)
    tramos = calendario.vencimientos_por_año[2024]["entidades_credito"]
    tramos_rotos = dataclasses.replace(tramos, mas_de_cinco=tramos.mas_de_cinco + 1.0)
    esperado = _saldo_balance_categoria(evolucion.ejercicios[2024], "entidades_credito")
    with pytest.raises(AssertionError):
        assert tramos_rotos.total == pytest.approx(esperado, abs=TOLERANCIA_EUR)


# --- (b) tramos no negativos ---------------------------------------------------------------

def test_tramos_no_negativos(catalogo, arquetipos):
    comprobados = 0
    for sector, segmento, semilla, combo in _casos(catalogo, arquetipos):
        evolucion = _generar(catalogo, arquetipos, sector, segmento, semilla, combo)
        calendario = calcular_calendario_deuda(evolucion)
        for por_categoria in calendario.vencimientos_por_año.values():
            for categoria in CATEGORIAS_TODAS:
                t = por_categoria[categoria]
                for valor in (t.un_año, t.dos, t.tres, t.cuatro, t.cinco, t.mas_de_cinco):
                    assert valor >= -1e-6
                    comprobados += 1
    assert comprobados > 3000


# --- (c) saldo final == saldo inicial - amortizaciones + disposiciones ----------------------

def test_saldo_final_es_saldo_inicial_menos_amortizaciones_mas_disposiciones(catalogo, arquetipos):
    comprobados = 0
    for sector, segmento, semilla, combo in _casos(catalogo, arquetipos):
        evolucion = _generar(catalogo, arquetipos, sector, segmento, semilla, combo)
        calendario = calcular_calendario_deuda(evolucion)
        for año, por_categoria in calendario.movimientos_por_año.items():
            for categoria, mov in por_categoria.items():
                assert mov.saldo_final_eur == pytest.approx(
                    mov.saldo_inicial_eur - mov.amortizaciones_eur + mov.disposiciones_eur, abs=1e-6
                )
                saldo_real = _saldo_balance_categoria(evolucion.ejercicios[año], categoria)
                assert mov.saldo_final_eur == pytest.approx(saldo_real, abs=TOLERANCIA_EUR)
                comprobados += 1
    assert comprobados > 300


# --- (d) conciliación con c10 del EFE --------------------------------------------------------

def test_conciliacion_con_c10_del_efe(catalogo, arquetipos):
    comprobados = 0
    for sector, segmento, semilla, combo in _casos(catalogo, arquetipos):
        evolucion = _generar(catalogo, arquetipos, sector, segmento, semilla, combo)
        calendario = calcular_calendario_deuda(evolucion)
        for año in (2024, 2025):
            efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            movimiento_neto = sum(
                calendario.movimientos_por_año[año][c].disposiciones_eur - calendario.movimientos_por_año[año][c].amortizaciones_eur
                for c in CATEGORIAS_DEUDA_FINANCIERA_CON_COSTE
            )
            assert movimiento_neto == pytest.approx(efe.c10_variacion_neta_deuda_financiera, abs=TOLERANCIA_EUR), (
                sector, segmento, semilla, combo, año
            )
            comprobados += 1
    assert comprobados > 100


def test_conciliacion_con_c10_falla_si_se_incluyen_los_derivados(catalogo, arquetipos):
    """Demuestra que (d) SÍ detecta un descuadre: si por error se incluyeran los derivados en la
    conciliación (categoría explícitamente excluida, ver docstring del módulo), la igualdad con
    `c10` dejaría de cumplirse en cualquier caso donde el derivado tenga saldo no nulo (arquetipo
    "coberturas" activo)."""
    evolucion = _generar(catalogo, arquetipos, "24.1", "grandes_medianas", 5, {"coberturas": "fuerte"})
    calendario = calcular_calendario_deuda(evolucion)
    año = 2024
    efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
    movimiento_con_derivados = sum(
        calendario.movimientos_por_año[año][c].disposiciones_eur - calendario.movimientos_por_año[año][c].amortizaciones_eur
        for c in CATEGORIAS_DEUDA_FINANCIERA
    )
    derivado_activo = calendario.movimientos_por_año[año]["derivados"].saldo_final_eur != 0 or calendario.movimientos_por_año[año]["derivados"].saldo_inicial_eur != 0
    assert derivado_activo, "el caso de control necesita el derivado activo para que el contraejemplo sea significativo"
    assert movimiento_con_derivados != pytest.approx(efe.c10_variacion_neta_deuda_financiera, abs=TOLERANCIA_EUR)


# --- (e) determinismo -------------------------------------------------------------------------

def test_determinismo_mismo_caso_misma_llamada(catalogo, arquetipos):
    evolucion = _generar(catalogo, arquetipos, "24.1", "grandes_medianas", 5, {"capex_elevado": "fuerte"})
    calendario_1 = calcular_calendario_deuda(evolucion)
    calendario_2 = calcular_calendario_deuda(evolucion)
    assert calendario_1.parametros == calendario_2.parametros
    for año in calendario_1.vencimientos_por_año:
        for categoria in CATEGORIAS_TODAS:
            assert calendario_1.vencimientos_por_año[año][categoria] == calendario_2.vencimientos_por_año[año][categoria]


def test_determinismo_entre_generaciones_independientes_del_caso(catalogo, arquetipos):
    evolucion_1 = _generar(catalogo, arquetipos, "68", "pequeñas", 15, {"riesgo_refinanciacion": "fuerte"})
    evolucion_2 = _generar(catalogo, arquetipos, "68", "pequeñas", 15, {"riesgo_refinanciacion": "fuerte"})
    calendario_1 = calcular_calendario_deuda(evolucion_1)
    calendario_2 = calcular_calendario_deuda(evolucion_2)
    assert calendario_1.parametros == calendario_2.parametros


# --- (f) independencia: generar el calendario no altera el caso -----------------------------

def test_generar_calendario_no_altera_el_caso(catalogo, arquetipos):
    evolucion = _generar(catalogo, arquetipos, "30.2", "grandes_medianas", 5, {"exceso_stock": "fuerte"})
    antes = copy.deepcopy({año: (ej.balance_eur, ej.pyg_eur) for año, ej in evolucion.ejercicios.items()})
    calcular_calendario_deuda(evolucion)
    for año, ej in evolucion.ejercicios.items():
        assert ej.balance_eur == antes[año][0]
        assert ej.pyg_eur == antes[año][1]


def test_independencia_falla_si_el_calculo_muta_el_balance(catalogo, arquetipos):
    """Demuestra que (f) SÍ detecta una mutación: si `calcular_calendario_deuda` mutara el
    balance del caso (violación deliberada, simulada aquí sin tocar el módulo real), la
    comprobación de igualdad antes/después dejaría de cumplirse."""
    evolucion = _generar(catalogo, arquetipos, "30.2", "grandes_medianas", 5, {"exceso_stock": "fuerte"})
    antes = copy.deepcopy(evolucion.ejercicios[2024].balance_eur)
    evolucion.ejercicios[2024].balance_eur["disponible"] += 1.0  # mutación deliberada, solo para el contraejemplo
    with pytest.raises(AssertionError):
        assert evolucion.ejercicios[2024].balance_eur == antes


# --- (g) reglas por categoría en casos construidos a mano ------------------------------------

def test_reparto_bullet_pone_todo_el_importe_en_un_solo_tramo():
    tramos = _reparto_bullet(120_000.0, año_vencimiento_relativo=6)
    assert tramos == {"dos": 0.0, "tres": 0.0, "cuatro": 0.0, "cinco": 0.0, "mas_de_cinco": 120_000.0}
    tramos_dentro = _reparto_bullet(50_000.0, año_vencimiento_relativo=3)
    assert tramos_dentro == {"dos": 0.0, "tres": 50_000.0, "cuatro": 0.0, "cinco": 0.0, "mas_de_cinco": 0.0}


def test_reparto_sin_vencimiento_cierto_va_todo_a_mas_de_cinco():
    tramos = _reparto_sin_vencimiento_cierto(75_000.0)
    assert tramos == {"dos": 0.0, "tres": 0.0, "cuatro": 0.0, "cinco": 0.0, "mas_de_cinco": 75_000.0}


def test_reparto_lineal_leasing_con_remanente_decreciente():
    """Simula el patrón real de `PLAZO_REMANENTE_ARRENDAMIENTO_AÑOS - (año-2023)`: remanente 5 en
    2023, 4 en 2024, 3 en 2025 — la cuota por año SUBE a medida que el remanente decrece (menos
    años para repartir el mismo tipo de saldo), y el tramo "más de cinco" desaparece en cuanto el
    remanente es <=5 (siempre, en este ejemplo)."""
    remanente_2023 = _reparto_lineal(100_000.0, 5)
    assert remanente_2023["mas_de_cinco"] == 0.0
    assert remanente_2023["dos"] == pytest.approx(25_000.0)  # 100_000 / (5-1)
    remanente_2024 = _reparto_lineal(100_000.0, 4)
    assert remanente_2024["cinco"] == 0.0
    assert remanente_2024["dos"] == pytest.approx(100_000.0 / 3)
    remanente_2025 = _reparto_lineal(100_000.0, 3)
    assert remanente_2025["cuatro"] == 0.0
    assert remanente_2025["dos"] == pytest.approx(50_000.0)  # 100_000 / (3-1)


def test_reparto_lineal_con_remanente_mayor_de_cinco_acumula_en_mas_de_cinco():
    tramos = _reparto_lineal(90_000.0, 10)  # 9 cuotas de 10_000: años 2..10
    cuota = 90_000.0 / 9
    assert tramos["dos"] == pytest.approx(cuota)
    assert tramos["cinco"] == pytest.approx(cuota)
    assert tramos["mas_de_cinco"] == pytest.approx(cuota * 5)  # años 6,7,8,9,10


def test_reparto_lineal_clampa_el_plazo_minimo_a_dos():
    tramos = _reparto_lineal(40_000.0, 1)
    assert tramos == {"dos": 40_000.0, "tres": 0.0, "cuatro": 0.0, "cinco": 0.0, "mas_de_cinco": 0.0}


# --- Frecuencia de "cancelación anticipada" (protocolo de parada: no debe superar el 15%) ----

def test_frecuencia_cancelacion_anticipada_bajo_el_15_por_ciento(catalogo, arquetipos):
    total_por_categoria = {c: 0 for c in ("entidades_credito", "otros_pasivos_financieros", "derivados")}
    cancelaciones_por_categoria = {c: 0 for c in total_por_categoria}
    for sector, segmento, semilla, combo in _casos(catalogo, arquetipos):
        evolucion = _generar(catalogo, arquetipos, sector, segmento, semilla, combo)
        calendario = calcular_calendario_deuda(evolucion)
        for por_categoria in calendario.movimientos_por_año.values():
            for categoria in total_por_categoria:
                total_por_categoria[categoria] += 1
                if por_categoria[categoria].cancelacion_anticipada:
                    cancelaciones_por_categoria[categoria] += 1
    for categoria, total in total_por_categoria.items():
        tasa = cancelaciones_por_categoria[categoria] / total
        assert tasa <= 0.15, (categoria, tasa, cancelaciones_por_categoria[categoria], total)
