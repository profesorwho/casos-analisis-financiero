"""Mapeo del ECPN. Documento A (EIGR): filas simples, 2 periodos (2024, 2025), misma forma que
EFE. Documento B (Estado Total de Cambios): forma distinta — columnas son categorías de PN, no
años — se representa aparte, no como LineaEstado."""
from __future__ import annotations

from tipos import LineaEstado

PERIODOS = (2024, 2025)


def mapear_eigr(eigrs: dict) -> list[LineaEstado]:
    def _v(extractor):
        return {año: extractor(eigrs[año]) for año in PERIODOS}
    L = []
    L.append(LineaEstado("A)", "Resultado de la cuenta de pérdidas y ganancias", 0, _v(lambda e: e.a_resultado_ejercicio), negrita=True))
    L.append(LineaEstado("II", "Por coberturas de flujos de efectivo", 1, _v(lambda e: e.b2_coberturas)))
    L.append(LineaEstado("VII", "Subvenciones, donaciones y legados recibidos", 1, _v(lambda e: e.b7_subvenciones)))
    L.append(LineaEstado("", "Efecto impositivo", 1, _v(lambda e: e.b9_efecto_impositivo)))
    L.append(LineaEstado("B)", "Total ingresos y gastos imputados directamente en el patrimonio neto", 0, _v(lambda e: e.b_total), negrita=True))
    L.append(LineaEstado("IX", "Por coberturas de flujos de efectivo", 1, _v(lambda e: e.c2_coberturas)))
    L.append(LineaEstado("X", "Subvenciones, donaciones y legados recibidos", 1, _v(lambda e: e.c7_subvenciones)))
    L.append(LineaEstado("", "Efecto impositivo", 1, _v(lambda e: e.c9_efecto_impositivo)))
    L.append(LineaEstado("C)", "Total transferencias a la cuenta de pérdidas y ganancias", 0, _v(lambda e: e.c_total), negrita=True))
    L.append(LineaEstado("", "TOTAL DE INGRESOS Y GASTOS RECONOCIDOS (A+B+C)", 0,
              _v(lambda e: e.d_total_ingresos_gastos_reconocidos), negrita=True))
    return L


COLUMNAS_ECPN = [
    ("capital", "Capital"), ("reservas", "Reservas"),
    ("resultados_ejercicios_anteriores", "Resultados de ejercicios anteriores"),
    ("ajustes_cambio_valor", "Ajustes por cambios de valor"), ("subvenciones", "Subvenciones, donaciones y legados"),
    ("resultado_ejercicio", "Resultado del ejercicio"), ("total", "TOTAL"),
]


def mapear_ecpn_documento_b(ecpns: dict) -> dict:
    """Devuelve {año: [(etiqueta_fila, FilaECPN), ...]} — una tabla por año, filas = movimientos,
    columnas = categorías de PN (ver COLUMNAS_ECPN). El renderizador la trata aparte del resto."""
    resultado = {}
    for año in PERIODOS:
        e = ecpns[año]
        resultado[año] = [
            (f"SALDO INICIO {año}", e.saldo_inicio),
            ("Total ingresos y gastos reconocidos", e.total_ingresos_gastos_reconocidos),
            ("Operaciones con socios o propietarios", e.operaciones_con_socios),
            ("Otras variaciones del patrimonio neto", e.otras_variaciones),
            (f"SALDO FINAL {año}", e.saldo_final),
        ]
    return resultado
