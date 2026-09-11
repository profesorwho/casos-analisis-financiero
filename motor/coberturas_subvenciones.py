"""Coberturas de flujos de efectivo (arquetipo 21) y subvenciones de capital (vinculadas al
arquetipo 17, "Capex elevado") — cuentas de grupo 8/9 del PGC, con su efecto impositivo
transversal (subgrupo 83). Alcance aprobado explícitamente (no las 6 familias completas del
PGC): estas 2 operaciones + el efecto impositivo. El resto (coberturas de inversión neta en el
extranjero, diferencias de conversión, FVOCI, pérdidas actuariales, activos mantenidos para la
venta) queda fuera de alcance por decisión — ver `docs/decisiones_plausibilidad.md`.

**Diseño de cuadre exacto (derivado algebraicamente antes de implementar, no solo verificado
después).** Los dos mecanismos comparten un patrón: un ajuste bruto entra en una reserva de PN
(1340 para coberturas, 130 para subvenciones), se presenta NETO de su efecto impositivo
(cuentas 4740/479), y una parte se recicla a la PyG con el tiempo. La condición de cuadre
exacto (Activo = Pasivo + PN en todo momento, sin depender de que el plug de "otras deudas a
corto" absorba el residuo) exige dos decisiones de diseño no obvias, verificadas por álgebra
antes de escribir el código:

1. **Las cantidades que se reciclan a la PyG (transferencia por vencimiento + ineficacia de la
   cobertura; imputación anual de la subvención) son el importe BRUTO completo, no neto de
   impuesto** — y se inyectan en la cascada de PyG DESACOPLADAS del `impuesto_beneficios_pct`
   sorteado de forma genérica (que no "sabe" nada de este ajuste específico). Si se inyectaran
   netas de impuesto, o si se dejara que el sorteo genérico de `impuesto_beneficios` las
   gravara una segunda vez, el balance dejaría de cuadrar por el importe de esa diferencia —
   verificado derivando la partida doble a mano (ver test
   `test_identidad_balance_pyg_...` de `tests/test_coberturas_subvenciones.py`).
2. **La cobertura, a diferencia de la subvención, coloca en balance el valor razonable BRUTO
   completo del derivado (`valor_swap_eur`, incluida la parte ineficaz)**, no solo el saldo de
   la reserva 1340 (que excluye la ineficacia, nunca pasa por PN) — son dos cifras DISTINTAS
   que se derivan del mismo `ΔVR` anual pero evolucionan de forma distinta. La subvención, al
   ser un cobro real de caja que no se "devuelve" al imputarse a la PyG, coloca en balance un
   importe de caja FIJO (el cobro inicial, una sola vez) que ya no cambia con el saldo de la
   reserva 130 — la diferencia entre ambos, con el tiempo, la absorbe automáticamente
   `resultado_ejercicio`/reservas a través de la propia imputación bruta a la PyG (punto 1).

**Tipo impositivo**: 25% general (Ley 27/2014), aplicado plano sin distinguir por segmento —
el motor no tiene ya construido ningún mecanismo de tipo reducido por tamaño en ningún otro
punto, así que introducir uno aquí sería una hipótesis nueva no pedida; usar el general es la
opción de consistencia interna (ver encargo).
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from motor.amortizacion import SubLoteActivo, generar_cohortes_capex
from motor.ruido import _generar_partida

AÑO_BASE = 2023

TIPO_IMPOSITIVO_GENERAL = 0.25

# --------------------------------------------------------------------------------------------
# Coberturas de flujos de efectivo (arquetipo 21) — swap de tipo de interés, paga fijo/recibe
# variable (cubre deuda a tipo variable). Ver docstring del módulo para el diseño de cuadre.
# --------------------------------------------------------------------------------------------

# % de la deuda financiera cubierta, por intensidad — mismo rango que `motor.memoria.
# RANGOS_COBERTURA_PCT_DEUDA` (coherencia de escala con la nota cualitativa), pero sorteado de
# forma INDEPENDIENTE con su propio RNG: la nota (motor.memoria.generar_nota_coberturas) sigue
# sorteando su propio % para el texto — hipótesis de diseño aceptada, documentada como tal (ver
# decisiones_plausibilidad.md): el % citado en la nota y el nocional realmente modelado pueden
# no coincidir exactamente, ambos plausibles dentro del mismo rango.
RANGO_COBERTURA_PCT_DEUDA = {"leve": (0.30, 0.45), "moderado": (0.45, 0.65), "fuerte": (0.65, 0.90)}

# Plazo residual de la cobertura en años, sorteado UNA vez en el año base (2023) y decreciente
# en 1 cada año — rango orientativo de un IRS típico sobre deuda corporativa a medio plazo.
RANGO_PLAZO_RESIDUAL_AÑOS_INICIAL = (2.0, 8.0)

# Factor de duración modificada residual ≈ plazo × este factor — ajuste estándar por
# liquidación periódica (no al vencimiento), documentado explícitamente como hipótesis de
# diseño: punto medio del rango 0,85-0,95 que da el encargo, fijo, sin ruido.
FACTOR_DURACION_LIQUIDACION_PERIODICA = 0.90

# Ineficacia de cobertura: 0%-5% va directo a PyG, el resto a PN — hipótesis de diseño.
RANGO_INEFICACIA_PCT = (0.0, 0.05)

# Suelo defensivo sobre la deuda financiera usada para el nocional — evita un nocional nulo si
# alguna combinación extrema dejara la deuda financiera en cero.
SUELO_DEUDA_FINANCIERA_EUR = 1.0

# Techo defensivo sobre |Δr| usado en la fórmula de sensibilidad — verificado cuantitativamente
# que hace falta (ver decisiones_plausibilidad.md): `tipo_interes` en este motor es un coste de
# la deuda sintético por sector (sorteado con el ruido mixto habitual sobre el Huber/MAD del
# catálogo), que mezcla tipo de referencia + prima de riesgo/spread de crédito del sector — su
# volatilidad año a año puede ser mucho mayor que la de un tipo de referencia real (Euríbor),
# sobre todo en sectores pequeños y volátiles (Restaurantes, 56.1: Δr observado de -20 puntos en
# un barrido de 972 casos). Un IRS solo cubre el tipo de REFERENCIA, no el spread de crédito
# propio de la empresa — acotar Δr a un movimiento anual plausible de un tipo de referencia real
# (généroso pero acotado) evita que el ajuste de la cobertura absorba, de rebote, la volatilidad
# de una variable que no está cubriendo.
TECHO_DELTA_R_ANUAL = 0.03


def _entropia_cobertura(sector: str, segmento: str, sufijo: str = "") -> int:
    return zlib.crc32(f"{sector}|{segmento}|cobertura{sufijo}".encode("utf-8"))


def sortear_parametros_cobertura(sector: str, segmento: str, semilla: int, intensidad: str) -> tuple[float, float, float]:
    """Sorteo ÚNICO por caso (no por año): % de deuda cubierta, plazo residual inicial (en
    2023) y eficacia. RNG propio e independiente (no desplaza ningún sorteo existente)."""
    rng = np.random.default_rng([semilla, _entropia_cobertura(sector, segmento)])
    bajo, alto = RANGO_COBERTURA_PCT_DEUDA[intensidad]
    pct_cobertura_deuda = rng.uniform(bajo, alto)
    plazo_bajo, plazo_alto = RANGO_PLAZO_RESIDUAL_AÑOS_INICIAL
    plazo_residual_inicial_años = rng.uniform(plazo_bajo, plazo_alto)
    ineficacia_bajo, ineficacia_alto = RANGO_INEFICACIA_PCT
    eficacia_pct = 1.0 - rng.uniform(ineficacia_bajo, ineficacia_alto)
    return pct_cobertura_deuda, plazo_residual_inicial_años, eficacia_pct


@dataclass(frozen=True)
class PasoCobertura:
    """Resultado de evolucionar la cobertura un año: el nuevo estado (a guardar en
    `EjercicioEmpresa`) y los importes BRUTOS de este año (para el ajuste de PyG y para el
    Documento A / EIGR)."""

    nocional_vivo_eur: float
    plazo_residual_años: float
    valor_swap_eur: float  # V(t): valor razonable BRUTO acumulado del derivado (con signo)
    saldo_1340_bruto_eur: float  # B(t): reserva de PN bruta acumulada (con signo)
    eficaz_bruto_eur: float  # nuevo importe bruto que entra en la reserva este año (B.2 del EIGR)
    transferencia_bruto_eur: float  # importe bruto reciclado a PyG por vencimiento este año (magnitud de C.2)
    ineficaz_bruto_eur: float  # importe bruto que va directo a PyG, nunca pasó por PN


def evolucionar_cobertura(
    año: int,
    deuda_financiera_actual_eur: float,
    tipo_interes_actual: float,
    tipo_interes_anterior: float,
    nocional_anterior_eur: float,
    plazo_residual_anterior_años: float,
    valor_swap_anterior_eur: float,
    saldo_1340_bruto_anterior_eur: float,
    pct_cobertura_deuda: float,
    eficacia_pct: float,
) -> PasoCobertura:
    """Un paso anual de la cobertura (2024 o 2025 — en 2023, año base, todo el estado parte de
    cero, no se llama a esta función). `Δr` = variación del tipo de interés del sector entre el
    cierre anterior y el actual (ya se sortea en la cascada de PyG, aquí solo se lee).

    ΔVR(swap) = +nocional_vivo(t-1) × duración_modificada(t) × Δr(t) — signo POSITIVO (no el de
    la fórmula genérica de sensibilidad de un bono, que sería negativo): la empresa paga fijo/
    recibe variable, así que el swap SUBE de valor cuando suben los tipos (instrucción explícita
    del encargo, ver docstring del módulo `motor.evolucion_arquetipo` / decisiones_
    plausibilidad.md)."""
    nocional_vivo_eur = pct_cobertura_deuda * deuda_financiera_actual_eur
    plazo_residual_años = max(0.0, plazo_residual_anterior_años - 1.0)
    duracion_modificada = plazo_residual_años * FACTOR_DURACION_LIQUIDACION_PERIODICA
    delta_r = tipo_interes_actual - tipo_interes_anterior
    delta_r = max(-TECHO_DELTA_R_ANUAL, min(TECHO_DELTA_R_ANUAL, delta_r))
    delta_vr_eur = nocional_anterior_eur * duracion_modificada * delta_r

    eficaz_bruto_eur = eficacia_pct * delta_vr_eur
    ineficaz_bruto_eur = (1.0 - eficacia_pct) * delta_vr_eur

    # Transferencia anual a PyG por vencimiento: proporcional a la fracción del PLAZO que vence
    # este año, aplicada sobre el saldo de 1340 al INICIO del año — hipótesis de diseño
    # razonable (no una fórmula única impuesta por el PGC), documentada explícitamente.
    plazo_al_inicio_del_año = plazo_residual_anterior_años
    fraccion_vencimiento = 1.0 / plazo_al_inicio_del_año if plazo_al_inicio_del_año > 1e-9 else 1.0
    transferencia_bruto_eur = fraccion_vencimiento * saldo_1340_bruto_anterior_eur

    saldo_1340_bruto_eur = saldo_1340_bruto_anterior_eur + eficaz_bruto_eur - transferencia_bruto_eur
    valor_swap_eur = valor_swap_anterior_eur + delta_vr_eur

    return PasoCobertura(
        nocional_vivo_eur=nocional_vivo_eur,
        plazo_residual_años=plazo_residual_años,
        valor_swap_eur=valor_swap_eur,
        saldo_1340_bruto_eur=saldo_1340_bruto_eur,
        eficaz_bruto_eur=eficaz_bruto_eur,
        transferencia_bruto_eur=transferencia_bruto_eur,
        ineficaz_bruto_eur=ineficaz_bruto_eur,
    )


def ajuste_gastos_financieros_cobertura_eur(paso: PasoCobertura) -> float:
    """Importe a RESTAR de `gastos_financieros` (positivo = reduce el gasto: el swap gana valor
    cuando suben los tipos, compensando el mayor coste real de la deuda a tipo variable
    cubierta) — ver docstring del módulo, punto 1 del diseño de cuadre."""
    return paso.ineficaz_bruto_eur + paso.transferencia_bruto_eur


# --------------------------------------------------------------------------------------------
# Subvenciones de capital pendientes de imputar — vinculadas al arquetipo 17 (Capex elevado)
# como disparador principal, con una probabilidad de fondo baja incluso sin arquetipo. Ver
# docstring del módulo para el diseño de cuadre (asimétrico frente a coberturas: el cobro de
# caja es fijo, no seguidor de la reserva 130).
# --------------------------------------------------------------------------------------------

# Propensión de fondo (probabilidad de que exista una subvención de capital SIN que el
# arquetipo 17 esté activo) por categoría de sector — hipótesis de diseño, mismo patrón que los
# perfiles de `empresa_base.PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA`: sectores industriales/
# tecnológicos/con mayor tradición de ayudas públicas a la inversión (I+D, digitalización,
# eficiencia energética, agroalimentario dentro de "industria") más altos; servicios puros
# (profesionales, comercio/hostelería, inmobiliario) casi nulos.
PROPENSION_SUBVENCION_BASELINE_POR_CATEGORIA: dict[str, float] = {
    "industria": 0.20,  # incluye agroalimentario dentro de esta categoría (ver empresa_base.CATEGORIA_SECTOR)
    "servicios_tic": 0.15,
    "servicios_industriales": 0.15,
    "administracion_educacion_sanidad": 0.12,
    "transporte_logistica": 0.10,
    "construccion": 0.08,
    "comercio_hosteleria": 0.02,
    "servicios_profesionales": 0.02,
    "inmobiliario": 0.02,
}

# Magnitud del capex subvencionable "de fondo" (sin arquetipo 17): fracción del activo no
# corriente del año anterior — orden de magnitud plausible de una inversión puntual apoyada por
# un programa público, sin llegar a la escala de un "capex elevado" completo.
RANGO_CAPEX_BASELINE_PCT_ACTIVO_NO_CORRIENTE = (0.03, 0.10)

# % de cofinanciación pública sobre el CAPEX subvencionado — rango orientativo de programas
# públicos españoles/europeos habituales (líneas ICO/CDTI/FEDER, ayudas autonómicas a la
# inversión), sin dato ACCID que lo ancle — hipótesis de diseño.
RANGO_PCT_COFINANCIACION = (0.10, 0.40)


def _entropia_subvencion(sector: str, segmento: str, sufijo: str = "") -> int:
    return zlib.crc32(f"{sector}|{segmento}|subvencion{sufijo}".encode("utf-8"))


def sortear_subvencion_baseline(sector: str, segmento: str, semilla: int, categoria: str) -> tuple[bool, int]:
    """Sorteo ÚNICO por caso (no depende de ningún arquetipo): si existe una subvención "de
    fondo" y, si existe, en qué año se concede (2024 o 2025, 50/50). Solo se usa cuando el
    arquetipo 17 NO está activo en el caso (ver `_evolucionar_un_año`: mutuamente excluyente
    con la vía "capex_elevado", nunca ambas ni ninguna en función de un resultado suerte del
    17)."""
    rng = np.random.default_rng([semilla, _entropia_subvencion(sector, segmento, "_baseline")])
    propension = PROPENSION_SUBVENCION_BASELINE_POR_CATEGORIA[categoria]
    activa = rng.random() < propension
    año_concesion = 2024 if rng.integers(2) == 0 else 2025
    return activa, año_concesion


def capex_subvencionable_baseline_eur(sector: str, segmento: str, semilla: int, activo_no_corriente_anterior_eur: float) -> float:
    rng = np.random.default_rng([semilla, _entropia_subvencion(sector, segmento, "_baseline_magnitud")])
    bajo, alto = RANGO_CAPEX_BASELINE_PCT_ACTIVO_NO_CORRIENTE
    return rng.uniform(bajo, alto) * activo_no_corriente_anterior_eur


def sortear_pct_cofinanciacion(sector: str, segmento: str, semilla: int) -> float:
    rng = np.random.default_rng([semilla, _entropia_subvencion(sector, segmento, "_pct_cofinanciacion")])
    bajo, alto = RANGO_PCT_COFINANCIACION
    return rng.uniform(bajo, alto)


def generar_activo_subvencionado(sector: str, segmento: str, semilla: int, año: int, capex_subvencionable_eur: float) -> tuple[SubLoteActivo, ...]:
    """El "activo subvencionado" de la NRV 18.ª — se reutiliza `generar_cohortes_capex` (100% a
    instalaciones técnicas y maquinaria, inversión productiva típica) para que el activo
    financiado por la subvención entre también en la colección amortizable del caso, con un
    sufijo de entropía propio para no colisionar con las cohortes de capex "normales" del
    arquetipo 17 cuando la vía es la del disparador principal (mismo importe, mismo año, pero
    NO debe generar una cohorte duplicada: ver `_evolucionar_un_año`, que en la vía "17" reutiliza
    la cohorte YA creada por el capex en vez de llamar aquí de nuevo)."""
    return generar_cohortes_capex(sector, segmento, semilla, año, capex_subvencionable_eur)


@dataclass(frozen=True)
class PasoSubvencion:
    saldo_130_bruto_eur: float
    transferencia_bruto_eur: float  # importe bruto imputado a la PyG (otros_ingresos_explot) este año


def evolucionar_subvencion(saldo_130_bruto_anterior_eur: float, activo_asociado: tuple[SubLoteActivo, ...], año: int) -> PasoSubvencion:
    """NRV 18.ª: el importe transferido este año = saldo pendiente al inicio del año × (cuota de
    amortización del año del activo subvencionado / base amortizable pendiente de ese activo al
    inicio del año) — se libera al mismo ritmo que se amortiza el activo que financió, usando
    directamente los datos de cohortes de amortización ya existentes (motor.amortizacion), no un
    cálculo aparte."""
    if saldo_130_bruto_anterior_eur <= 0 or not activo_asociado:
        return PasoSubvencion(saldo_130_bruto_eur=0.0, transferencia_bruto_eur=0.0)

    cuota_año_eur = sum(sl.gasto_en(año) for sl in activo_asociado)
    base_pendiente_inicio_eur = sum(sl.valor_bruto_eur - sl.acumulada_en(año - 1) for sl in activo_asociado)

    if base_pendiente_inicio_eur <= 1e-9:
        return PasoSubvencion(saldo_130_bruto_eur=0.0, transferencia_bruto_eur=saldo_130_bruto_anterior_eur)

    ratio = min(1.0, cuota_año_eur / base_pendiente_inicio_eur)
    transferencia_bruto_eur = ratio * saldo_130_bruto_anterior_eur
    saldo_130_bruto_eur = saldo_130_bruto_anterior_eur - transferencia_bruto_eur
    return PasoSubvencion(saldo_130_bruto_eur=saldo_130_bruto_eur, transferencia_bruto_eur=transferencia_bruto_eur)


# --------------------------------------------------------------------------------------------
# Efecto impositivo (subgrupo 83) — helpers puros compartidos, sin estado propio: cada mecanismo
# expone su saldo bruto (`saldo_1340_bruto_eur`, `saldo_130_bruto_eur`) y estas funciones derivan
# la presentación neta y las cuentas de impuesto diferido — ver docstring del módulo.
# --------------------------------------------------------------------------------------------


def presentacion_neta_eur(saldo_bruto_eur: float) -> float:
    return saldo_bruto_eur * (1.0 - TIPO_IMPOSITIVO_GENERAL)


def activo_por_impuesto_diferido_eur(saldo_bruto_eur: float) -> float:
    return max(0.0, -saldo_bruto_eur) * TIPO_IMPOSITIVO_GENERAL


def pasivo_por_impuesto_diferido_eur(saldo_bruto_eur: float) -> float:
    return max(0.0, saldo_bruto_eur) * TIPO_IMPOSITIVO_GENERAL
