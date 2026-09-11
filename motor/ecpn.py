"""Estado de Cambios en el Patrimonio Neto (ECPN), Documento B — "Estado total de cambios en el
patrimonio neto" del modelo NORMAL del PGC. Capa de cálculo pura sobre la desagregación de PN
(Capital / Reservas y resultados de ejercicios anteriores / Resultado del ejercicio) que el
motor ya genera para dos ejercicios consecutivos — no genera ningún dato nuevo.

**Documento A (Estado de Ingresos y Gastos Reconocidos) queda APARCADO, decisión ya tomada, no
implementado aquí** — ver `docs/decisiones_plausibilidad.md`: exige movimientos de las cuentas
de grupo 8/9 (valoración de instrumentos financieros, coberturas, subvenciones, actuariales,
diferencias de conversión) que este motor no cuantifica (ni el arquetipo 21 -coberturas- ni el
19 -activo para la venta- producen un ajuste de PN cuantificado, solo notas de memoria), y solo
es legalmente obligatorio para grandes empresas — ni siquiera para el resto de modelo normal. Al
quedar aparcado, la fila "Total de ingresos y gastos reconocidos" de este Documento B equivale
aquí EXACTAMENTE al resultado del ejercicio (sin ajustes de valor que sumarle, porque no se
generan).

Modelo oficial de filas verificado (misma metodología PGC 2007 que el EFE): saldo inicial del
ejercicio, total de ingresos y gastos reconocidos, operaciones con socios o propietarios, otras
variaciones del patrimonio neto, saldo final del ejercicio — aplicado aquí sobre las 3 columnas
de PN que el motor desagrega (Capital, Reservas y resultados de ejercicios anteriores, Resultado
del ejercicio) más el TOTAL, en vez de las ~12 columnas completas del modelo oficial (prima de
emisión, acciones propias, ajustes por cambios de valor, subvenciones, etc. — NINGUNA de ellas
tiene mecanismo que las alimente en este motor, ver decisiones_plausibilidad.md).

**Reclasificación del resultado del ejercicio anterior**: al iniciar el ejercicio t, el
resultado del ejercicio (t-1) dejó de ser "del ejercicio" — se reclasifica a reservas. Esto ya
es consistente por construcción con cómo se deriva `EjercicioEmpresa.reservas_eur` (ver
`empresa_base.py`): reservas(t) = reservas(t-1) + resultado_ejercicio(t-1) -
apalancamiento_extra_eur(t) — verificado algebraicamente y confirmado por la reconciliación
exhaustiva (ver validación).

**Operaciones con socios**: el único mecanismo del motor que mueve PN sin pasar por el resultado
del ejercicio es el arquetipo 9/14 (apalancamiento) — la deuda nueva financia una distribución a
PN (ver `evolucion_arquetipo.py`). Se registra aquí como una operación con socios que reduce
Reservas (una distribución con cargo a reservas, tratamiento habitual cuando no hay resultado
del propio ejercicio suficiente o disponible para repartir directamente).
"""

from __future__ import annotations

from dataclasses import dataclass

from motor.evolucion_arquetipo import EjercicioEmpresa

TOLERANCIA_CUADRE_EUR = 0.01


@dataclass(frozen=True)
class FilaECPN:
    capital: float
    reservas: float
    resultado_ejercicio: float

    @property
    def total(self) -> float:
        return self.capital + self.reservas + self.resultado_ejercicio


@dataclass(frozen=True)
class EstadoCambiosPatrimonioNeto:
    año: int
    obligatorio: bool  # False si el caso clasifica legalmente como modelo abreviado (Art. 257.3 LSC)

    saldo_inicio: FilaECPN
    total_ingresos_gastos_reconocidos: FilaECPN  # = resultado del ejercicio (Documento A aparcado)
    operaciones_con_socios: FilaECPN  # arquetipo 9/14 (apalancamiento): distribución con cargo a reservas
    otras_variaciones: FilaECPN  # SIEMPRE 0 — sin mecanismo que lo alimente
    saldo_final: FilaECPN

    pn_total_real_eur: float  # balance_eur["patrimonio_neto"] del ejercicio actual, fuente de verdad
    descuadre_eur: float

    @property
    def cuadra(self) -> bool:
        return abs(self.descuadre_eur) <= TOLERANCIA_CUADRE_EUR


def generar_ecpn(anterior: EjercicioEmpresa, actual: EjercicioEmpresa, obligatorio: bool) -> EstadoCambiosPatrimonioNeto:
    """ECPN (Documento B) del ejercicio `actual` frente al `anterior`."""
    saldo_inicio = FilaECPN(
        capital=anterior.capital_social_eur,
        reservas=anterior.reservas_eur + anterior.pyg_eur["resultado_ejercicio"],  # reclasificación
        resultado_ejercicio=0.0,
    )
    total_ingresos_gastos = FilaECPN(
        capital=0.0, reservas=0.0, resultado_ejercicio=actual.pyg_eur["resultado_ejercicio"]
    )
    operaciones_con_socios = FilaECPN(
        capital=0.0, reservas=-actual.apalancamiento_extra_eur, resultado_ejercicio=0.0
    )
    otras_variaciones = FilaECPN(capital=0.0, reservas=0.0, resultado_ejercicio=0.0)

    saldo_final = FilaECPN(
        capital=saldo_inicio.capital + operaciones_con_socios.capital + otras_variaciones.capital,
        reservas=saldo_inicio.reservas + operaciones_con_socios.reservas + otras_variaciones.reservas,
        resultado_ejercicio=total_ingresos_gastos.resultado_ejercicio,
    )

    pn_total_real = actual.balance_eur["patrimonio_neto"]
    descuadre = saldo_final.total - pn_total_real

    return EstadoCambiosPatrimonioNeto(
        año=actual.año,
        obligatorio=obligatorio,
        saldo_inicio=saldo_inicio,
        total_ingresos_gastos_reconocidos=total_ingresos_gastos,
        operaciones_con_socios=operaciones_con_socios,
        otras_variaciones=otras_variaciones,
        saldo_final=saldo_final,
        pn_total_real_eur=pn_total_real,
        descuadre_eur=descuadre,
    )
