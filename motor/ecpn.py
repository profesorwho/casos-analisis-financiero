"""Estado de Cambios en el Patrimonio Neto (ECPN) — Documento B ("Estado total de cambios en el
patrimonio neto") y Documento A ("Estado de ingresos y gastos reconocidos", EIGR) del modelo
NORMAL del PGC. Capa de cálculo pura sobre la desagregación de PN que el motor ya genera para dos
ejercicios consecutivos — no genera ningún dato nuevo.

**Documento A ya NO está aparcado** (lo estuvo hasta el encargo de coberturas/subvenciones — ver
`docs/decisiones_plausibilidad.md`): dependía de que el motor cuantificara movimientos de grupo
8/9, que ahora sí existen para 2 de las 6 familias del PGC (coberturas de flujos de efectivo,
arquetipo 21; subvenciones de capital, transversal — ver `motor/coberturas_subvenciones.py`). El
resto de familias (valoración de instrumentos financieros, diferencias de conversión,
actuariales, activos mantenidos para la venta) siguen sin mecanismo y sus líneas del Documento A
se agregan en un único importe `b_resto_fuera_de_alcance`/`c_resto_fuera_de_alcance`, siempre
0.0, documentado como fuera de alcance por decisión — no como omisión silenciosa.

**Obligatoriedad de cada documento — corrección respecto a lo asumido en la versión anterior de
este módulo.** Se afirmaba que el Documento A "solo es legalmente obligatorio para grandes
empresas — ni siquiera para el resto de modelo normal", una distinción DISTINTA del criterio de
modelo abreviado/normal (Art. 257 LSC). Verificado explícitamente para este encargo (búsqueda
externa, no de memoria): el PGC (RD 1514/2007, Normas de Elaboración de las Cuentas Anuales)
permite un "ECPN ABREVIADO" (un único documento, equivalente a este Documento B, sin Documento A)
a las empresas que pueden formular balance y memoria abreviados — el MISMO test de 2-de-3 del
Art. 257.1 LSC ya implementado en `motor.clasificacion_legal`, con los mismos umbrales
(actualizados en el tiempo junto con los de balance/memoria: la referencia histórica de 2007,
2.850.000 €/5.700.000 €/50 trabajadores, es literalmente el umbral ORIGINAL de Art. 257 LSC antes
de sus actualizaciones posteriores a los 4.000.000 €/8.000.000 €/50 vigentes que usa este motor
— no un umbral distinto y más estricto de "gran empresa"). No existe, en el texto del PGC, una
tercera categoría "gran empresa" separada de "modelo normal" a estos efectos: la expresión
"grandes empresas" que usaban algunas fuentes secundarias es un sinónimo coloquial de "empresas
que no pueden formular en abreviado", no un umbral numérico distinto. Por eso aquí Documento A y
Documento B comparten EXACTAMENTE el mismo flag `obligatorio` (el que ya calcula
`motor.clasificacion_legal` para el caso) — no se ha añadido ningún clasificador nuevo.

Modelo oficial de filas verificado (misma metodología PGC 2007 que el EFE): saldo inicial del
ejercicio, total de ingresos y gastos reconocidos, operaciones con socios o propietarios, otras
variaciones del patrimonio neto, saldo final del ejercicio — aplicado aquí sobre las 6 columnas
de PN que el motor desagrega (Capital, Reservas, Resultados de ejercicios anteriores, Ajustes
por cambios de valor, Subvenciones/donaciones/legados, Resultado del ejercicio) más el TOTAL, en
vez de las ~12 columnas completas del modelo oficial (prima de emisión, acciones propias, etc. —
sin mecanismo que las alimente en este motor, ver decisiones_plausibilidad.md). "Reservas" y
"Resultados de ejercicios anteriores" son columnas SEPARADAS del modelo oficial (antes de este
encargo se presentaban fusionadas en una sola, ver más abajo) — la desagregación de PN del motor
(`EjercicioEmpresa.reservas_eur`) no distingue reservas "puras" de resultados de años previos
más allá del último ejercicio cerrado, así que la separación aplica únicamente a ESE último
resultado (ver "Reclasificación" abajo); cualquier resultado más antiguo ya quedó incorporado a
`reservas_eur` en su propio ejercicio de cierre y no se puede desagregar retroactivamente.

**Reclasificación del resultado del ejercicio anterior**: al iniciar el ejercicio t, el
resultado del ejercicio (t-1) dejó de ser "del ejercicio" — pasa a la columna "Resultados de
ejercicios anteriores" en el saldo de apertura (antes de este encargo se sumaba directamente a
"Reservas", fusionando ambas columnas en una — ver más abajo). Dentro del propio ejercicio t, esa
columna se reclasifica de nuevo a "Reservas" vía la fila "Otras variaciones" (antes siempre 0.0,
ahora el único movimiento que alimenta esa fila) — por construcción, "Resultados de ejercicios
anteriores" SIEMPRE cierra el ejercicio en 0.0 (todo lo que entra por el saldo de apertura sale
por "Otras variaciones" ese mismo año), y el saldo final de "Reservas" no cambia ni un céntimo
respecto a la versión anterior de este módulo (sigue siendo consistente por construcción con
cómo se deriva `EjercicioEmpresa.reservas_eur`, ver `empresa_base.py`: reservas(t) = reservas(t-1)
+ resultado_ejercicio(t-1) - apalancamiento_extra_eur(t) - verificado algebraicamente y
confirmado por la reconciliación exhaustiva, ver validación) — la separación es puramente de
PRESENTACIÓN (qué fila/columna aloja el importe en qué momento del año), no cambia ningún total.

**Operaciones con socios**: el único mecanismo del motor que mueve PN sin pasar por el resultado
del ejercicio (ni por las reservas de grupo89) es el arquetipo 9/14 (apalancamiento) — la deuda
nueva financia una distribución a PN (ver `evolucion_arquetipo.py`). Se registra aquí como una
operación con socios que reduce Reservas (una distribución con cargo a reservas, tratamiento
habitual cuando no hay resultado del propio ejercicio suficiente o disponible para repartir
directamente).

**El total del Documento A (D = A+B+C) es la fuente de verdad para la fila "Total de ingresos y
gastos reconocidos" del Documento B** — verificado algebraicamente y en el barrido de
validación (ver decisiones_plausibilidad.md) que D coincide exactamente con
`resultado_ejercicio + Δ(ajustes_cambio_valor neto) + Δ(subvenciones neto)`, la misma cifra que
usa el Documento B para esa fila.
"""

from __future__ import annotations

from dataclasses import dataclass

from motor.coberturas_subvenciones import TIPO_IMPOSITIVO_GENERAL
from motor.evolucion_arquetipo import EjercicioEmpresa

TOLERANCIA_CUADRE_EUR = 0.01


@dataclass(frozen=True)
class FilaECPN:
    capital: float
    reservas: float
    resultados_ejercicios_anteriores: float
    ajustes_cambio_valor: float
    subvenciones: float
    resultado_ejercicio: float

    @property
    def total(self) -> float:
        return (
            self.capital
            + self.reservas
            + self.resultados_ejercicios_anteriores
            + self.ajustes_cambio_valor
            + self.subvenciones
            + self.resultado_ejercicio
        )


@dataclass(frozen=True)
class EstadoCambiosPatrimonioNeto:
    año: int
    obligatorio: bool  # False si el caso clasifica legalmente como modelo abreviado (Art. 257.3 LSC)

    saldo_inicio: FilaECPN
    total_ingresos_gastos_reconocidos: FilaECPN  # = Documento A, fila D, desagregada por columna de PN
    operaciones_con_socios: FilaECPN  # arquetipo 9/14 (apalancamiento) + payout de fondo (#79-#80): distribución con cargo a reservas
    otras_variaciones: FilaECPN  # SIEMPRE 0 — sin mecanismo que lo alimente
    saldo_final: FilaECPN

    pn_total_real_eur: float  # balance_eur["patrimonio_neto"] del ejercicio actual, fuente de verdad
    descuadre_eur: float

    @property
    def cuadra(self) -> bool:
        return abs(self.descuadre_eur) <= TOLERANCIA_CUADRE_EUR


@dataclass(frozen=True)
class EstadoIngresosGastosReconocidos:
    """Documento A del ECPN — ver docstring del módulo para el alcance (coberturas + subvención,
    resto de familias en 0 documentado) y la obligatoriedad (comparte `obligatorio` con el
    Documento B, no hay un umbral "gran empresa" distinto)."""

    año: int
    obligatorio: bool

    a_resultado_ejercicio: float

    b2_coberturas: float
    b7_subvenciones: float
    b_resto_fuera_de_alcance: float  # SIEMPRE 0.0 — valoración instrumentos financieros, actuariales, diferencias de conversión, etc. (fuera de alcance, ver docstring)
    b9_efecto_impositivo: float
    b_total: float

    c2_coberturas: float
    c7_subvenciones: float
    c_resto_fuera_de_alcance: float  # SIEMPRE 0.0 — mismo motivo que b_resto_fuera_de_alcance
    c9_efecto_impositivo: float
    c_total: float

    d_total_ingresos_gastos_reconocidos: float  # = A + B_total + C_total


def generar_eigr(actual: EjercicioEmpresa, obligatorio: bool) -> EstadoIngresosGastosReconocidos:
    """Documento A del ejercicio `actual` — a diferencia del Documento B (que compara dos
    ejercicios), el EIGR es una fotografía de UN solo ejercicio: los importes B/C son los flujos
    BRUTOS de ESE año, ya expuestos directamente en `EjercicioEmpresa` (no hace falta el
    ejercicio anterior)."""
    a = actual.pyg_eur["resultado_ejercicio"]

    b2 = actual.cobertura_eficaz_bruto_eur
    b7 = actual.subvencion_importe_concedido_eur
    b_resto = 0.0
    b9 = -(b2 + b7) * TIPO_IMPOSITIVO_GENERAL
    b_total = b2 + b7 + b_resto + b9

    c2 = -actual.cobertura_transferencia_bruto_eur
    c7 = -actual.subvencion_transferencia_bruto_eur
    c_resto = 0.0
    c9 = -(c2 + c7) * TIPO_IMPOSITIVO_GENERAL
    c_total = c2 + c7 + c_resto + c9

    d = a + b_total + c_total

    return EstadoIngresosGastosReconocidos(
        año=actual.año,
        obligatorio=obligatorio,
        a_resultado_ejercicio=a,
        b2_coberturas=b2,
        b7_subvenciones=b7,
        b_resto_fuera_de_alcance=b_resto,
        b9_efecto_impositivo=b9,
        b_total=b_total,
        c2_coberturas=c2,
        c7_subvenciones=c7,
        c_resto_fuera_de_alcance=c_resto,
        c9_efecto_impositivo=c9,
        c_total=c_total,
        d_total_ingresos_gastos_reconocidos=d,
    )


def generar_ecpn(anterior: EjercicioEmpresa, actual: EjercicioEmpresa, obligatorio: bool) -> EstadoCambiosPatrimonioNeto:
    """ECPN (Documento B) del ejercicio `actual` frente al `anterior`. La fila "Total de ingresos
    y gastos reconocidos" desagrega por columna de PN el mismo total D que calcula
    `generar_eigr` (Documento A) — verificado que ambos coinciden exactamente en
    `tests/test_ecpn.py`, no se recalcula aquí llamando a `generar_eigr` para evitar acoplar
    los dos documentos más de lo necesario (cada uno es autónomo, como en el PGC real)."""
    saldo_inicio = FilaECPN(
        capital=anterior.capital_social_eur,
        reservas=anterior.reservas_eur,  # pura — ya NO incluye el resultado del año anterior, ver docstring
        resultados_ejercicios_anteriores=anterior.pyg_eur["resultado_ejercicio"],  # reclasificación, columna propia
        ajustes_cambio_valor=anterior.ajustes_cambio_valor_pn_eur,
        subvenciones=anterior.subvenciones_pn_eur,
        resultado_ejercicio=0.0,
    )
    total_ingresos_gastos = FilaECPN(
        capital=0.0,
        reservas=0.0,
        resultados_ejercicios_anteriores=0.0,
        ajustes_cambio_valor=actual.ajustes_cambio_valor_pn_eur - anterior.ajustes_cambio_valor_pn_eur,
        subvenciones=actual.subvenciones_pn_eur - anterior.subvenciones_pn_eur,
        resultado_ejercicio=actual.pyg_eur["resultado_ejercicio"],
    )
    operaciones_con_socios = FilaECPN(
        capital=0.0,
        reservas=-(actual.apalancamiento_extra_eur + actual.payout_dividendos_eur),
        resultados_ejercicios_anteriores=0.0,
        ajustes_cambio_valor=0.0,
        subvenciones=0.0,
        resultado_ejercicio=0.0,
    )
    # Única fila que mueve "Resultados de ejercicios anteriores" — reclasifica dentro del propio
    # ejercicio t el importe que entró por el saldo de apertura hacia "Reservas" (ver docstring):
    # por construcción, esta columna siempre cierra el año en 0.0, y "Reservas" recupera
    # exactamente el mismo saldo final que tenía antes de separar ambas columnas.
    otras_variaciones = FilaECPN(
        capital=0.0,
        reservas=saldo_inicio.resultados_ejercicios_anteriores,
        resultados_ejercicios_anteriores=-saldo_inicio.resultados_ejercicios_anteriores,
        ajustes_cambio_valor=0.0,
        subvenciones=0.0,
        resultado_ejercicio=0.0,
    )

    saldo_final = FilaECPN(
        capital=saldo_inicio.capital + operaciones_con_socios.capital + otras_variaciones.capital,
        reservas=saldo_inicio.reservas + operaciones_con_socios.reservas + otras_variaciones.reservas,
        resultados_ejercicios_anteriores=(
            saldo_inicio.resultados_ejercicios_anteriores + otras_variaciones.resultados_ejercicios_anteriores
        ),
        ajustes_cambio_valor=saldo_inicio.ajustes_cambio_valor + total_ingresos_gastos.ajustes_cambio_valor,
        subvenciones=saldo_inicio.subvenciones + total_ingresos_gastos.subvenciones,
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
