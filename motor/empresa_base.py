"""Motor mínimo: genera el balance y la PyG base de una empresa a partir del catálogo
sectorial, con variabilidad realista entre empresas de un mismo sector.

Sin arquetipos, sin serie de tres años, sin EFE: un único ejercicio, coherente y cuadrado.

**Semilla del generador aleatorio.** `rng` se siembra con `semilla` MEZCLADA con un hash
estable (`zlib.crc32`, no `hash()` de Python — este varía entre procesos por PYTHONHASHSEED,
rompería la reproducibilidad) de `sector+segmento`, no con `semilla` a secas. Sembrar solo con
`semilla` (como hacía la primera versión) dejaba a CUALQUIER sector/segmento con el mismo
número de semilla partiendo del MISMO estado de `rng` — y como el modo típico/atípico y el
valor z de cada partida (`_generar_partida`/`_normal_truncada`) no dependen de huber/mad, solo
su escalado posterior sí, la secuencia de sorteos consumida era, en la práctica, IDÉNTICA entre
sectores distintos que compartieran semilla (verificado: el z de `rotacion_activo` coincidía
hasta 1e-9 entre dos sectores cualesquiera con la misma semilla) — se corrigió tras una
auditoría pedida explícitamente al encontrar el mismo patrón en el sorteo de `nota_memoria` de
`motor.evolucion_arquetipo`. La intensidad NO se mezcla aquí (no aplica: esta función no la
conoce) ni en la semilla equivalente de `motor.evolucion_arquetipo.generar_evolucion_arquetipo`
— por diseño, la misma semilla+sector+segmento con intensidades distintas debe compartir el
mismo "ruido de fondo" de la empresa (ver docstring de ese módulo), solo el propio empuje del
arquetipo varía con la intensidad.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from motor.amortizacion import AÑO_BASE as _AÑO_BASE_AMORTIZACION
from motor.amortizacion import amortizacion_eur_del_año, generar_coleccion_y_perfiles_base
from motor.catalogo import cargar_y_validar_catalogo
# Reexportados (no solo usados aquí): otros módulos (p. ej. motor/clasificacion_legal.py,
# motor/amortizacion.py) los importan como motor.empresa_base.<nombre> — mover la definición a
# motor/ruido.py (para que motor/amortizacion.py pueda reutilizarlos sin crear una importación
# circular con este módulo) no les obliga a cambiar su propio import.
from motor.ruido import (  # noqa: F401
    DESVIACIONES_ATIPICO,
    DESVIACIONES_TIPICO,
    MODOS_GENERACION_VALIDOS,
    PROB_ATIPICO,
    ModoGeneracionInvalidoError,
    _generar_partida,
    _generar_partida_con_memoria,
    _normal_truncada,
    _renormalizar_a_total,
    _resolver_binario_por_modo,
    activar_modo_generacion,
    desactivar_modo_generacion,
    modo_generacion_activo,
)

SEGMENTOS_VALIDOS = frozenset({"grandes_medianas", "pequeñas"})

TOLERANCIA_CUADRE_EUR = 0.01
SUELO_PORCENTAJE = 0.01
SUELO_ROTACION_ACTIVO = 0.05

# --------------------------------------------------------------------------------------------
# Tipo de interés — fuente de mercado, NO `ratios.coste_deuda` del catálogo ACCID (diagnóstico
# cerrado: ese ratio mezcla en "gastos financieros" partidas ajenas a intereses reales —
# deterioros de activos financieros, diferencias de cambio, pérdidas en enajenación de
# instrumentos financieros — y su denominador, "Préstamos", puede ser una fracción minúscula
# del pasivo en sectores financiados mayoritariamente con pasivo no financiero; produce valores
# de 74%-110% en datos reales de ACCID para sectores concretos, ver docs/decisiones_
# plausibilidad.md). Reconstruido en 3 capas: tipo de referencia (Euríbor 12M, con su variación
# histórica real) + prima de riesgo por categoría de sector y tamaño (hipótesis de diseño,
# ancladas al orden de magnitud de una fuente EXTERNA independiente, Banco de España — ver más
# abajo) + ruido mixto típico/atípico entre empresas del mismo caso (mismo mecanismo de
# siempre). Único punto de sorteo (misma posición en la secuencia de `rng` que el `tipo_interes`
# anterior, ver `_generar_pyg_hasta_baii`) — no es un mecanismo nuevo, es una fuente distinta
# para el mismo sorteo.
# --------------------------------------------------------------------------------------------

# Euríbor a 12 meses, media anual — verificado externamente (no de memoria), búsqueda cruzada
# Banco de España / euribor.com.es / hipotecasyeuribor.com, septiembre de 2026. Refleja la forma
# real de estos 3 años: 2023 todavía cerca del pico post-subidas del BCE (llegó a ~4,16% en
# octubre de 2023), 2024 con las primeras bajadas (el BCE empezó a recortar en junio de 2024),
# 2025 estabilizado más abajo (~2,0%-2,3%, con ligero repunte a final de año).
REFERENCIA_EURIBOR_12M_POR_AÑO: dict[int, float] = {
    2023: 0.0387,
    2024: 0.0327,
    2025: 0.0222,
}

# Prima de riesgo por categoría de sector (mismas 9 categorías que CATEGORIA_SECTOR/
# PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA), en puntos porcentuales sobre el Euríbor 12M, para
# "grandes_medianas" — HIPÓTESIS DE DISEÑO razonada con conocimiento financiero general (no hay
# dato de catálogo que la respalde, igual que otros perfiles ya construidos), pero ANCLADA en
# nivel medio a una fuente externa independiente: Banco de España, Boletín Estadístico, tabla
# 19.6 ("Tipos de interés TAE de nuevas operaciones... Sociedades no financieras", por tramo de
# importe del préstamo — bde.es/webbe/es/estadisticas/compartido/datos/pdf/a1906.pdf). El tramo
# "más de 1 millón de euros" (el que mejor correlaciona con financiación de gran empresa) dio
# 5,24% (2023), 4,35% (2024) y ~3,4% (media 2025) — con el Euríbor 12M de esos mismos años, la
# prima MEDIA implícita en el dato real de BdE es de ~1,2 puntos porcentuales. Los valores de
# abajo se calibraron para que su media (1,20pp) coincida con ese ancla externa, conservando el
# ORDEN relativo entre categorías (que sí es una hipótesis solo cualitativa, no verificada punto
# por punto): más colateral tangible/demanda estable = prima menor (administración/sanidad,
# inmobiliario); menos activo pignorable o mayor riesgo percibido por la banca = prima mayor
# (TIC por intangibilidad, construcción por riesgo cíclico histórico en España).
PRIMA_RIESGO_POR_CATEGORIA: dict[str, float] = {
    "administracion_educacion_sanidad": 0.0060,
    "inmobiliario": 0.0080,
    "industria": 0.0100,
    "transporte_logistica": 0.0110,
    "servicios_industriales": 0.0110,
    "comercio_hosteleria": 0.0135,
    "servicios_profesionales": 0.0150,
    "construccion": 0.0160,
    "servicios_tic": 0.0175,
}

# Recargo plano para "pequeñas" (no diferenciado por categoría — no hay base razonada sólida
# para variar la penalización por tamaño según sector, a diferencia de la prima sectorial en sí,
# así que se evita una matriz 9×2 sin justificación adicional). Ancla: BdE tabla 19.6, tramo
# "hasta 250 mil euros" (el que mejor correlaciona con financiación de pequeña empresa) dio
# 5,99% (2023), 4,79% (2024), ~4,2% (media 2025) — prima media implícita ~1,87pp, frente a
# ~1,20pp de "grandes_medianas": diferencia de ~0,7pp, redondeada aquí a 0,75pp.
RECARGO_TIPO_INTERES_PEQUEÑAS_PP = 0.0075

# Dispersión entre empresas del mismo sector/segmento/año — mismo mecanismo de ruido mixto
# típico/atípico (85%/15%) que el resto del motor, pero con una dispersión de DISEÑO (no MAD de
# catálogo: no existe un dato de catálogo limpio del que derivarla). 0,50pp: el 85% de los casos
# cae dentro de ±0,75pp del centro, el 15% atípico hasta ±1,50pp — variación de tipo entre
# empresas comparables del mismo sector/tamaño/año, coherente con diferencias reales de historial
# crediticio, relación bancaria y calidad de garantías.
DISPERSION_TIPO_INTERES_PP = 0.0050

SUELO_TIPO_INTERES = 0.015  # 1,5%: floor defensivo — un tipo por debajo del Euríbor+prima mínima no tiene sentido económico
TECHO_TIPO_INTERES = 0.12  # 12%: techo defensivo para una empresa en dificultades genuinas — ya no un valor que se alcance rutinariamente (antes 40%, con la fuente contaminada)

# --------------------------------------------------------------------------------------------
# Impuesto sobre Sociedades — tipo efectivo sobre BAI (no % de ingresos, ver diagnóstico abajo)
# + cuenta corriente con Hacienda Pública (pagos a cuenta vs. impuesto real, ver motor.
# evolucion_arquetipo, bloque "hacienda_publica_deudora"/"...acreedora" del segundo lote de
# desglose de balance). Sustituye el sorteo de `impuesto_beneficios_pct` como una primitiva más
# de PyG proporcional a ingresos (mismo bucle que consumos_explotacion/gastos_personal/otros_
# gastos_explot) — diagnóstico de partida confirmado (empresas en pérdidas con impuesto positivo,
# tipo efectivo saltando entre años sin relación con el BAI real). Investigación de Fase 1
# (docs/, `git log`, docstrings de `motor/*.py`) NO encontró ninguna justificación específica
# para tratar el impuesto como una partida más de PyG — simplificación heredada del diseño
# original sin razón documentada, no una decisión deliberada a preservar. Ver docs/decisiones_
# plausibilidad.md (hallazgo "Impuesto de Sociedades sobre BAI").
# --------------------------------------------------------------------------------------------

# Tipo nominal del Impuesto sobre Sociedades (Ley 27/2014, art. 29, con la disposición
# transitoria 44ª introducida por la Ley 7/2024) — verificado externamente (AEAT/BOE, búsqueda
# cruzada septiembre 2026, no de memoria):
# - Tipo GENERAL: 25%, sin cambios en 2023-2025 (la Ley 7/2024 solo reduce el tipo de las
#   entidades de reducida dimensión y las microempresas, no el general).
# - Entidades de Reducida Dimensión (ERD, cifra de negocio <10M€ — el tramo con el que
#   correlaciona el segmento "pequeñas" de este motor, ventas_objetivo=5M€, ver CLAUDE.md sección
#   "Clasificación legal"): 25% en 2023/2024 (el tipo reducido ERD llevaba derogado desde la
#   reforma de 2015 hasta que la Ley 7/2024 lo reintrodujo), 24% desde 2025 (primer escalón de la
#   reducción progresiva 25%->20% para 2029: 2025=24%, 2026=23%, 2027=22%, 2028=21%, 2029=20% en
#   adelante — este motor solo genera 2023-2025, así que solo el primer escalón es relevante).
# - Microempresas (cifra de negocio <1M€, tipo 21%-23% según el año) y entidades de nueva
#   creación (15% los 2 primeros ejercicios con base positiva) NO se modelan aparte: ni
#   "pequeñas" (ventas_objetivo 5M€) ni "grandes_medianas" (15M€) caen en el umbral de
#   microempresa, y el motor no rastrea la antigüedad de la empresa — introducir esos 2 tipos
#   sería una hipótesis nueva sin ninguna variable del caso que la ancle (mismo criterio que
#   `motor/coberturas_subvenciones.py` ya aplicó para no introducir un tipo reducido sin
#   mecanismo que lo dispare, ver TIPO_IMPOSITIVO_GENERAL en ese módulo).
TIPO_NOMINAL_IS_POR_AÑO_SEGMENTO: dict[int, dict[str, float]] = {
    2023: {"pequeñas": 0.25, "grandes_medianas": 0.25},
    2024: {"pequeñas": 0.25, "grandes_medianas": 0.25},
    2025: {"pequeñas": 0.24, "grandes_medianas": 0.25},
}

# Dispersión entre empresas del mismo caso — mismo mecanismo de ruido mixto típico/atípico que
# el resto del motor, representando deducciones/bonificaciones reales (doble imposición interna,
# I+D+i, reserva de capitalización/nivelación...) que separan el tipo EFECTIVO del nominal en
# distinta medida según la empresa. Sin MAD de catálogo que la ancle (ACCID no publica tipo
# efectivo) — dispersión de DISEÑO, deliberadamente MODESTA: los datos AEAT de tipo efectivo
# agregado (5,7%-19,3% sobre resultado contable según metodología; 5,11% grandes empresas vs.
# 12,24% pymes según AEDAF/infoLibre, ejercicio 2019) están dominados por grandes grupos con
# planificación fiscal internacional (consolidación fiscal, deducciones por doble imposición
# internacional) ajena al perfil de PYME doméstica que genera este motor — usarlos como ancla
# de dispersión inventaría una cola de elusión fiscal agresiva que el catálogo ACCID (pensado
# para PYMEs de los 27 sectores) no sustenta. 2,0pp de dispersión típica (85% de los casos dentro
# de ±3,0pp del nominal) es una hipótesis de diseño acotada a esa cautela.
DISPERSION_TIPO_IMPUESTO_IS_PP = 0.020
SUELO_TIPO_IMPUESTO_IS = 0.0  # una empresa con deducciones/bonificaciones suficientes puede no pagar nada ese año — nunca negativo (no se modela crédito fiscal a devolver aquí)
TECHO_TIPO_IMPUESTO_IS = 0.30  # margen sobre el nominal más alto (25%) para gastos no deducibles atípicos

# Pagos fraccionados a cuenta (modelo 202, art. 40 LIS) — modalidad del art. 40.2 (RÉGIMEN
# GENERAL, aplicable POR DEFECTO salvo que la empresa ejerza la opción expresa del art. 40.3,
# que este motor no modela): 3 pagos (abril/octubre/diciembre) del 18% cada uno sobre la CUOTA
# ÍNTEGRA del último período impositivo con plazo de declaración ya vencido — verificado en
# sede.agenciatributaria.gob.es, "Pagos fraccionados en el Impuesto sobre Sociedades" y manual
# práctico Sociedades cap. 15 (septiembre 2026). Total: 3 x 18% = 54% de la cuota del año
# ANTERIOR — esto es lo que alimenta `activos/pasivos_impuesto_corriente` (segundo lote de
# desglose de balance, motor.evolucion_arquetipo): el residuo entre lo pagado a cuenta y el
# impuesto real del ejercicio es la cuenta corriente con Hacienda, a favor (deudora, activo) o
# en contra (acreedora, pasivo) de la empresa. En el año base (2023, sin "año -1" real generado
# por este motor) se usa el propio impuesto de 2023 como proxy del año anterior —
# simplificación documentada, sin alternativa mejor sin inventar un ejercicio 2022 completo; da
# sistemáticamente una posición "Hacienda acreedora" de (1-0,54)=46% del impuesto de 2023 (nunca
# "deudora" en el año base, por construcción de la propia proxy).
FRACCION_PAGOS_A_CUENTA_IS = 0.54

# Nombre de salida -> nombre de variable en el catálogo (prefijo "balance.")
MASAS_BALANCE = {
    "activo_no_corriente": "activo_no_corriente",
    "activo_corriente": "activo_corriente",
    "existencias": "existencias_pct",
    "realizable": "realizable_pct",
    "disponible": "disponible_pct",
    "patrimonio_neto": "patrimonio_neto_pct",
    "pasivo_no_corriente": "pasivo_no_corriente_pct",
    "deudas_fin_largo": "deudas_fin_largo_pct",
    "otras_deudas_largo": "otras_deudas_largo_pct",
    "pasivo_corriente": "pasivo_corriente_pct",
    "acreedores_comerciales": "acreedores_comerciales_pct",
    "deudas_fin_corto": "deudas_fin_corto_pct",
    "otras_deudas_corto": "otras_deudas_corto_pct",
}

# Partidas primitivas de la PyG (ruido) -> nombre de variable en el catálogo (prefijo "pyg.").
# "gastos_financieros" NO está aquí: se calcula (deuda financiera media x tipo de interés),
# no se sortea como % independiente — ver _generar_pyg_hasta_baii/_completar_pyg_con_deuda.
# "impuesto_beneficios" TAMPOCO está aquí desde el rediseño del Impuesto sobre Sociedades (ver
# bloque "Impuesto sobre Sociedades" más arriba): se calcula (tipo efectivo x BAI, nunca negativo
# en años con BAI<=0), no se sortea como % de ingresos — ver _generar_pyg_hasta_baii (sortea el
# TIPO efectivo, no el importe) / _completar_pyg_con_deuda (aplica el tipo sobre el BAI ya
# calculado). Mismo patrón que "amortizaciones" desde que dejó de sortearse como % independiente.
PRIMITIVAS_PYG = {
    "cifra_negocios": "cifra_negocios_pct",
    "otros_ingresos_explot": "otros_ingresos_explot_pct",
    "consumos_explotacion": "consumos_explotacion_pct",
    "otros_gastos_explot": "otros_gastos_explot_pct",
    "gastos_personal": "gastos_personal_pct",
    "amortizaciones": "amortizaciones_pct",
    "resultado_extraordinario": "resultado_extraordinario_pct",
    "ingresos_financieros": "ingresos_financieros_pct",
}

# Primitivas de PyG que no pueden ser negativas (importes de ingreso/gasto en sí mismos).
# resultado_extraordinario sí puede serlo (extraordinario negativo): el propio catálogo tiene
# valores Huber negativos en algunos sectores.
PRIMITIVAS_PYG_NO_NEGATIVAS = frozenset(PRIMITIVAS_PYG) - {"resultado_extraordinario"}

SUBTOTALES_PYG = ("ingresos_explotacion", "margen_bruto", "valor_añadido", "baii", "bai", "resultado_ejercicio")

_RE_CODIGO_SECTOR = re.compile(r"\(([^()]+)\)\s*$")

# --------------------------------------------------------------------------------------------
# Desagregación de patrimonio neto (Capital / Reservas y resultados de ejercicios anteriores /
# Resultado del ejercicio) — HIPÓTESIS DE DISEÑO, no un dato del catálogo ACCID (que solo da el
# agregado `patrimonio_neto_pct`). El capital social es un atributo de la EMPRESA, fijado una
# única vez al generar el año base (2023) y constante en 2024/2025 — no varía porque cambien los
# resultados anuales, igual que en la realidad (una ampliación/reducción de capital es un hecho
# discreto, no algo que este motor modela). Las reservas se derivan por resta, no son una fuente
# de ruido propia: reservas(t) = PN(t) - capital_social - resultado_del_ejercicio(t).
# --------------------------------------------------------------------------------------------
CAPITAL_SOCIAL_FRACCION_PN_CENTRO = 0.40
CAPITAL_SOCIAL_FRACCION_PN_SPREAD = 0.06
CAPITAL_SOCIAL_FRACCION_PN_SUELO = 0.30
CAPITAL_SOCIAL_FRACCION_PN_TECHO = 0.50

# --------------------------------------------------------------------------------------------
# Desagregación de `activo_no_corriente` (material / intangible / inversiones inmobiliarias /
# otros activos financieros) — HIPÓTESIS DE DISEÑO, no un dato del catálogo ACCID (que nunca
# desglosó activo_no_corriente más allá del agregado). Necesaria para poder rellenar el desglose
# de inversión que exige el modelo oficial del EFE (sección B). Perfil por CATEGORÍA de sector
# (las 8 categorías de la sección 2.22 del documento de especificaciones), no un único reparto
# para los 27 sectores — cada perfil suma exactamente 1.0. El salto de activo del arquetipo 18
# (adquisición) se mantiene aparte de este reparto, ver `motor/efe.py`.
# --------------------------------------------------------------------------------------------
CATEGORIA_SECTOR: dict[str, str] = {
    # Industria (9)
    "24.1": "industria", "29": "industria", "10.1": "industria", "20.1": "industria",
    "28": "industria", "30.3": "industria", "30.2": "industria", "19": "industria", "35.1": "industria",
    # Servicios industriales (4)
    "33.1": "servicios_industriales", "33.2": "servicios_industriales",
    "71": "servicios_industriales", "72": "servicios_industriales",
    # Servicios profesionales / TIC (3) — sub-divididos en dos PERFILES (no dos bloques nuevos
    # de la sección 2.22, que se mantiene en 8 bloques a efectos del catálogo de sectores): el
    # perfil de `activo_no_corriente` de contabilidad/auditoría/consultoría (69.2/70.2) resultó
    # muy distinto del de programación/TIC (62) — ver decisiones_plausibilidad.md #29/#33.
    "69.2": "servicios_profesionales", "70.2": "servicios_profesionales", "62": "servicios_tic",
    # Transporte y logística (2)
    "52": "transporte_logistica", "4941": "transporte_logistica",
    # Comercio y hostelería (4)
    "47.1": "comercio_hosteleria", "46": "comercio_hosteleria",
    "56.1": "comercio_hosteleria", "55.1": "comercio_hosteleria",
    # Construcción (2)
    "41.2": "construccion", "43.2": "construccion",
    # Administración, educación y sanidad (2)
    "85": "administracion_educacion_sanidad", "86.1": "administracion_educacion_sanidad",
    # Inmobiliario (1)
    "68": "inmobiliario",
}

# Cada perfil suma exactamente 1.0. Criterio contable orientativo (documentado como hipótesis,
# no dato ACCID): sectores intensivos en capital físico (industria, transporte, comercio,
# construcción, administración/sanidad) llevan `material` dominante; servicios profesionales/TIC
# invierten más en intangible (software, patentes, fondo de comercio); inmobiliario lleva
# `inversiones_inmobiliarias` dominante por definición del propio sector.
PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "industria": {"material": 0.80, "intangible": 0.10, "inversiones_inmobiliarias": 0.02, "otros_financieros": 0.08},
    "servicios_industriales": {"material": 0.55, "intangible": 0.25, "inversiones_inmobiliarias": 0.03, "otros_financieros": 0.17},
    # Contabilidad/auditoría/consultoría (69.2/70.2): pese a ser "servicios profesionales", el
    # activo_no_corriente típico de estos 2 sectores en el catálogo es MUY grande respecto a sus
    # ingresos (rotacion_activo inusualmente baja, ~0,28-0,30 — activo_no_corriente 2,5-2,8x los
    # ingresos, ver decisiones #29). No es plausible que una consultora tenga ese volumen de
    # activo en oficinas/software: lo más razonable es que la mayor parte sea PARTICIPACIONES/
    # inversiones financieras (estructuras de holding, habituales en redes de auditoría/
    # consultoría con oficinas asociadas) — `otros_financieros` dominante, material e intangible
    # bajos. Ver #33 para la verificación cuantificada de que esto corrige el hallazgo #29.
    "servicios_profesionales": {"material": 0.15, "intangible": 0.15, "inversiones_inmobiliarias": 0.05, "otros_financieros": 0.65},
    # Programación/consultoría informática (62): el sector "TIC" propiamente dicho — aquí sí
    # tiene sentido un intangible alto (software propio, propiedad intelectual) — y su rotacion_
    # activo en el catálogo ya era razonable (no mostraba el mismo problema que 69.2/70.2).
    "servicios_tic": {"material": 0.20, "intangible": 0.50, "inversiones_inmobiliarias": 0.03, "otros_financieros": 0.27},
    "transporte_logistica": {"material": 0.80, "intangible": 0.08, "inversiones_inmobiliarias": 0.04, "otros_financieros": 0.08},
    "comercio_hosteleria": {"material": 0.75, "intangible": 0.10, "inversiones_inmobiliarias": 0.05, "otros_financieros": 0.10},
    "construccion": {"material": 0.70, "intangible": 0.05, "inversiones_inmobiliarias": 0.05, "otros_financieros": 0.20},
    "administracion_educacion_sanidad": {"material": 0.75, "intangible": 0.15, "inversiones_inmobiliarias": 0.02, "otros_financieros": 0.08},
    "inmobiliario": {"material": 0.10, "intangible": 0.03, "inversiones_inmobiliarias": 0.80, "otros_financieros": 0.07},
}

# Dispersión sintética (no hay MAD del catálogo para esto) aplicada a cada componente del
# perfil antes de renormalizar a 100% — evita que dos empresas del mismo sector salgan con el
# reparto idéntico, sin cambiar el perfil CENTRAL de la categoría.
DISPERSION_PERFIL_ACTIVO_NO_CORRIENTE = 0.20  # fracción relativa del propio valor del componente
SUELO_COMPONENTE_ACTIVO_NO_CORRIENTE_PCT = 0.005  # 0,5%: evita un componente en cero o negativo

# --------------------------------------------------------------------------------------------
# Desagregación de `existencias` (primer lote de desglose de balance según el mapeo oficial del
# PGC — HIPÓTESIS DE DISEÑO, el catálogo ACCID nunca desglosó existencias más allá del agregado)
# en las 6 sub-partidas oficiales: comerciales, materias primas y otros aprovisionamientos,
# productos en curso, productos terminados, subproductos/residuos/materiales recuperados,
# anticipos a proveedores. Mismo patrón de ruido mixto/renormalizado a 1.0 que el resto de
# perfiles de este bloque, pero la CLASIFICACIÓN no reutiliza `CATEGORIA_SECTOR` — verificado
# contra el dato real de `balance.existencias_pct` del catálogo (no solo criterio cualitativo,
# ver decisiones_plausibilidad.md #52) que varios sectores dentro de una misma categoría de las
# 9 de `activo_no_corriente` tienen un carácter de existencias radicalmente distinto entre sí
# (p. ej. 55.1 Hoteles, dentro de "comercio_hosteleria", con existencias reales de solo 0,84%
# del activo — nada que ver con 47.1 Supermercados al 10,75% — o 68 Inmobiliario, que el dato
# real muestra con 13,79%, de los más altos del catálogo, por mezclar promoción inmobiliaria con
# arrendamiento puro). Clasificación propia por SECTOR (no por categoría), en 8 "tiers":
#   - industria / servicios_industriales / comercio_hosteleria / construccion: sectores con
#     existencias reales y composición equivalente a la de antes (mismos números), pero ahora con
#     membresía más ajustada (ver `TIER_EXISTENCIAS_POR_SECTOR` para qué sector cae en cada uno).
#   - producto_en_curso: servicios profesionales/técnicos "por proyecto o encargo", sin producto
#     físico entregable, donde la única existencia con sentido real es el equivalente contable de
#     TRABAJOS EN CURSO NO FACTURADOS (un proyecto de consultoría empezado, un desarrollo de
#     software no entregado, un informe de arquitectura o un ensayo de I+D en marcha) — se
#     concentra casi todo en `productos_curso`. Dato real que lo respalda: 62 Programación
#     (2,43%) y 71 Arquitectura/ingeniería (5,73%, el más alto del grupo) tienen existencias
#     apreciablemente MAYORES que el grupo "cero_total" (69.2/70.2 en 0,41%/0,62%), consistente
#     con que el trabajo en curso sí genera un saldo real, no ruido.
#   - cero_total: servicios puros sin producto físico entregable Y sin el patrón de trabajo en
#     curso anterior — el dato real YA es marginal (<1,1% del activo en los 4 sectores: 85
#     Educación 0,42%, 52 Almacenamiento 0,51%, 55.1 Hoteles 0,84%, 4941 Transporte por
#     carretera 0,99%). Reparto interno sin pretensión de significado de negocio (el importe
#     total ya es insignificante, no tiene sentido fingir precisión cualitativa sobre él): las 6
#     categorías a partes iguales.
#   - inmobiliario_mixto (68, único miembro): el CNAE 68 español agregado mezcla promoción
#     inmobiliaria (construye para vender — existencias REALES de terrenos/edificios en curso y
#     terminados) con arrendamiento puro (sin existencias) — el dato real (13,79%) confirma que
#     el componente de promoción pesa lo suficiente como para que el agregado sea alto. Perfil
#     dominado por `productos_curso` (edificaciones en construcción) y `productos_terminados`
#     (promociones acabadas pendientes de venta), en la misma lógica que `construccion` — NO se
#     fuerza a "casi sin existencias" solo porque la categoría de `activo_no_corriente` para este
#     sector representa tenencia como inversión: son dos facetas del mismo epígrafe agregado.
#   - sanidad_consumibles (86.1, único miembro): separado de 85 Educación (mismo bloque
#     "administración/educación/sanidad" a efectos de `activo_no_corriente`, pero el dato real de
#     existencias diverge con fuerza: 86.1 al 1,69%, ~4x el de 85 al 0,42%) — refleja consumo
#     real de material sanitario/fungible. Composición pequeña pero real, dominada por
#     `materias_primas` (consumibles), no un cero forzado.
PERFIL_EXISTENCIAS_POR_TIER: dict[str, dict[str, float]] = {
    "industria": {
        "materias_primas": 0.28, "productos_curso": 0.27, "productos_terminados": 0.30,
        "comerciales": 0.05, "subproductos_residuos": 0.06, "anticipos_proveedores": 0.04,
    },
    "servicios_industriales": {
        "materias_primas": 0.25, "productos_curso": 0.15, "productos_terminados": 0.20,
        "comerciales": 0.28, "subproductos_residuos": 0.02, "anticipos_proveedores": 0.10,
    },
    "comercio_hosteleria": {
        "comerciales": 0.78, "materias_primas": 0.07, "productos_curso": 0.02,
        "productos_terminados": 0.05, "subproductos_residuos": 0.01, "anticipos_proveedores": 0.07,
    },
    "construccion": {
        "productos_curso": 0.45, "materias_primas": 0.20, "anticipos_proveedores": 0.17,
        "productos_terminados": 0.10, "comerciales": 0.05, "subproductos_residuos": 0.03,
    },
    # Trabajos en curso no facturados — servicios "por proyecto/encargo" (69.2/70.2/62/71/72).
    "producto_en_curso": {
        "productos_curso": 0.85, "comerciales": 0.08, "anticipos_proveedores": 0.05,
        "materias_primas": 0.01, "productos_terminados": 0.005, "subproductos_residuos": 0.005,
    },
    # Reparto neutro (1/6 cada una) — el importe total ya es insignificante en el dato real
    # (<1,1% del activo), no se pretende modelar una composición de negocio sobre él.
    "cero_total": {
        "comerciales": 1 / 6, "materias_primas": 1 / 6, "productos_curso": 1 / 6,
        "productos_terminados": 1 / 6, "subproductos_residuos": 1 / 6, "anticipos_proveedores": 1 / 6,
    },
    # CNAE 68 agregado: promoción (existencias reales) + arrendamiento (sin existencias).
    "inmobiliario_mixto": {
        "productos_curso": 0.45, "productos_terminados": 0.30, "materias_primas": 0.10,
        "anticipos_proveedores": 0.08, "comerciales": 0.05, "subproductos_residuos": 0.02,
    },
    # Consumibles/material sanitario fungible — pequeño pero real (86.1).
    "sanidad_consumibles": {
        "materias_primas": 0.55, "anticipos_proveedores": 0.20, "comerciales": 0.15,
        "productos_curso": 0.03, "subproductos_residuos": 0.05, "productos_terminados": 0.02,
    },
}

# Sector -> tier de existencias (ver docstring arriba para el razonamiento y el dato real que
# respalda cada reclasificación). Los 27 sectores del catálogo, exactamente uno por tier.
TIER_EXISTENCIAS_POR_SECTOR: dict[str, str] = {
    # industria (9)
    "24.1": "industria", "29": "industria", "10.1": "industria", "20.1": "industria",
    "28": "industria", "30.3": "industria", "30.2": "industria", "19": "industria", "35.1": "industria",
    # servicios_industriales (2 — 71/72 se reclasifican a producto_en_curso)
    "33.1": "servicios_industriales", "33.2": "servicios_industriales",
    # producto_en_curso (5)
    "69.2": "producto_en_curso", "70.2": "producto_en_curso", "62": "producto_en_curso",
    "71": "producto_en_curso", "72": "producto_en_curso",
    # cero_total (4 — incluye 55.1, que en `activo_no_corriente`/existencias antiguas caía en
    # "comercio_hosteleria" pero el dato real de existencias es radicalmente distinto)
    "85": "cero_total", "52": "cero_total", "55.1": "cero_total", "4941": "cero_total",
    # comercio_hosteleria (3 — sin 55.1)
    "47.1": "comercio_hosteleria", "46": "comercio_hosteleria", "56.1": "comercio_hosteleria",
    # construccion (2)
    "41.2": "construccion", "43.2": "construccion",
    # sanidad_consumibles (1)
    "86.1": "sanidad_consumibles",
    # inmobiliario_mixto (1)
    "68": "inmobiliario_mixto",
}

DISPERSION_PERFIL_EXISTENCIAS = 0.20
SUELO_COMPONENTE_EXISTENCIAS_PCT = 0.005


def tier_existencias_de_sector(sector_codigo: str) -> str:
    if sector_codigo not in TIER_EXISTENCIAS_POR_SECTOR:
        raise EmpresaBaseError(f"Sector '{sector_codigo}' no tiene tier de existencias asignado en TIER_EXISTENCIAS_POR_SECTOR.")
    return TIER_EXISTENCIAS_POR_SECTOR[sector_codigo]

# --------------------------------------------------------------------------------------------
# "Periodificaciones" — estructuralmente pequeñas pero casi universales (PGC: activo corriente
# VI, pasivo no corriente V, pasivo corriente VI). NO son una masa nueva del balance: se tallan
# como fracción de una masa YA existente y ya cuadrada (mismo criterio que el resto de este
# lote) — periodificaciones de ACTIVO como fracción de `realizable` (que en el modelo oficial
# agrega deudores + inversiones financieras a c/p + periodificaciones a c/p, todo bajo el mismo
# % sorteado del catálogo); periodificaciones de PASIVO (corto Y largo plazo — a diferencia del
# activo, que solo tiene periodificaciones a corto en el modelo oficial) como fracción de
# `otras_deudas_corto`/`otras_deudas_largo` respectivamente (el "resto" de pasivo no financiero
# de cada plazo). HIPÓTESIS DE DISEÑO — sin dato de catálogo que la respalde.
#   - Periodificación de ACTIVO más alta en sectores con más gastos anticipados por contratos de
#     seguros/alquileres/mantenimiento (administración/educación/sanidad, inmobiliario,
#     comercio/hostelería); más baja en sectores intensivos en producción física (industria,
#     construcción), donde el grueso del circulante no financiero está en existencias/deudores
#     operativos, no en gastos anticipados.
#   - Periodificación de PASIVO (ingresos anticipados/cobros por adelantado de clientes) más alta
#     en sectores con modelo de suscripción o cuota anticipada (servicios_tic: licencias/SaaS
#     pagados por adelantado; administración/educación/sanidad: matrículas y cuotas anticipadas,
#     contratos plurianuales) y más baja en sectores de venta/obra puntual sin cobro anticipado
#     estructural (industria, construcción — los anticipos DE construcción ya están en
#     `anticipos_proveedores` de existencias, del lado del gasto, no del ingreso).
PERIODIFICACION_ACTIVO_PCT_POR_CATEGORIA: dict[str, float] = {
    "administracion_educacion_sanidad": 0.06,
    "comercio_hosteleria": 0.05,
    "inmobiliario": 0.05,
    "servicios_profesionales": 0.04,
    "servicios_tic": 0.04,
    "servicios_industriales": 0.03,
    "transporte_logistica": 0.03,
    "construccion": 0.02,
    "industria": 0.02,
}

# Mismo valor por categoría aplicado de forma independiente a corto y largo plazo (dos sorteos
# distintos, mismo centro) — simplificación deliberada: no hay base razonada para que la
# composición de clientes con cobro anticipado difiera cualitativamente entre plazo corto y
# largo dentro del mismo sector, solo el VOLUMEN total (que ya varía año a año con la masa
# `otras_deudas_largo`/`otras_deudas_corto` de la que se talla cada una).
PERIODIFICACION_PASIVO_PCT_POR_CATEGORIA: dict[str, float] = {
    "servicios_tic": 0.08,
    "administracion_educacion_sanidad": 0.07,
    "servicios_profesionales": 0.05,
    "comercio_hosteleria": 0.04,
    "inmobiliario": 0.04,
    "transporte_logistica": 0.03,
    "servicios_industriales": 0.03,
    "construccion": 0.02,
    "industria": 0.02,
}

DISPERSION_PERIODIFICACION = 0.20
SUELO_PERIODIFICACION_PCT = 0.002
TECHO_PERIODIFICACION_PCT = 0.15

# --------------------------------------------------------------------------------------------
# Segundo lote de desglose de balance: "Deudores comerciales y otras cuentas a cobrar" (6
# sub-partidas oficiales de perfil FIJO, carve-out de `realizable`) y "Acreedores comerciales y
# otras cuentas a pagar" (6 sub-partidas oficiales de perfil FIJO, carve-out de
# `acreedores_comerciales`) — HIPÓTESIS DE DISEÑO, el catálogo ACCID nunca desglosó ninguna de
# las dos masas más allá del agregado. Mismo patrón de ruido mixto/renormalizado que el resto de
# perfiles de este bloque. "Hacienda Pública deudora/acreedora por impuesto sobre beneficios"
# (7ª sub-partida oficial de cada masa) YA NO forma parte de este perfil fijo desde el rediseño
# del Impuesto sobre Sociedades — antes era un % constante de la masa (`activos_impuesto_
# corriente`/`pasivos_impuesto_corriente`), sin relación con el impuesto real del ejercicio; ahora
# se DERIVA cada año en `motor/evolucion_arquetipo.py` (residuo entre pagos a cuenta reales y el
# impuesto real, carve-out desde "clientes"/"proveedores" con el mismo helper `_reparto_organico_
# con_exceso_dirigido` que ya usan "accionistas_desembolsos_exigidos"/"personal" — ver bloque
# "Impuesto sobre Sociedades" arriba y CLAUDE.md, sección homónima).
#
# Deudores — perfil ÚNICO, no por sector/categoría (a diferencia de existencias en el lote 1):
# verificado contra el dato real (`ratios.cobro_dias` del catálogo, comparado con los "días
# implícitos" de `realizable_pct` combinados con `rotacion_activo`) que "Clientes" ES,
# esencialmente, la totalidad de `realizable` en los 27 sectores SIN excepción — ratio cobro_dias
# real / días implícitos de realizable entre 0,89 y 1,13 en todos los casos, sin el patrón de
# outliers sectoriales que sí justificó una reclasificación en existencias (ver decisiones_
# plausibilidad.md #52). No hay señal en el dato real que pida variar este perfil por sector.
# "Clientes empresas del grupo y asociadas" y "Accionistas por desembolsos exigidos" en 0% en el
# caso base: el primero solo se activa cuando el arquetipo 20 (operaciones vinculadas) selecciona
# la operación comercial de facturación de servicios de gestión al grupo (ver
# motor/evolucion_arquetipo.py, `ParametrosOperacionVinculada`); el segundo es un supuesto
# excepcional (capital social pendiente de desembolso) sin ningún arquetipo dedicado que lo
# justifique — se deja en un residuo mínimo de ruido, no un cero forzado.
PERFIL_DEUDORES_BASE: dict[str, float] = {
    "clientes": 0.88,
    "deudores_varios": 0.055,
    "personal": 0.02,
    "otros_creditos_aapp": 0.018,
    "accionistas_desembolsos_exigidos": 0.002,
    "clientes_empresas_grupo": 0.0,
}

# Acreedores — perfil POR CATEGORÍA (las mismas 9 de `CATEGORIA_SECTOR`): a diferencia de
# deudores, aquí SÍ hay una señal real que considerar (`ratios.pago_dias`), pero el diagnóstico ya
# cerrado (mismo patrón de distorsión que `ratios.coste_deuda`, ver docs/decisiones_
# plausibilidad.md) descarta usarla como ancla LITERAL: el denominador de `pago_dias` (compras/
# consumos de explotación) es minúsculo en sectores de servicios, dispara el ratio sin que
# signifique un plazo de pago real más largo — comparado contra los "días implícitos" de
# acreedores_comerciales_pct + rotacion_activo, la divergencia va de 1,1x hasta 10,2x (peor en
# 69.2/85/55.1, los mismos sectores "casi sin producto físico" del lote 1). Se usa en su lugar
# solo la DIRECCIÓN cualitativa que el propio dato SÍ confirma con solidez (gastos_personal_pct
# del catálogo, dato fiable): categorías intensivas en mano de obra (servicios profesionales/TIC,
# administración/educación/sanidad) llevan más peso relativo en "Personal (remuneraciones
# pendientes de pago)" y algo menos en "Proveedores" que categorías intensivas en compra de
# materiales/mercancía (industria, comercio, construcción), donde "Proveedores" domina con más
# fuerza. "Proveedores empresas del grupo" en 0% en el caso base (mismo criterio que "Clientes
# empresas del grupo": solo se activa vía arquetipo 20). "Anticipos de clientes" más alto en
# categorías con cobro anticipado habitual (construcción, administración/educación/sanidad,
# TIC) — mismo criterio cualitativo ya usado en PERIODIFICACION_PASIVO_PCT_POR_CATEGORIA.
PERFIL_ACREEDORES_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "industria": {
        "proveedores": 0.82, "personal": 0.035, "acreedores_varios": 0.05,
        "otras_deudas_aapp": 0.03, "anticipos_clientes": 0.035,
        "proveedores_empresas_grupo": 0.0,
    },
    "servicios_industriales": {
        "proveedores": 0.72, "personal": 0.06, "acreedores_varios": 0.06,
        "otras_deudas_aapp": 0.035, "anticipos_clientes": 0.09,
        "proveedores_empresas_grupo": 0.0,
    },
    "servicios_profesionales": {
        "proveedores": 0.55, "personal": 0.16, "acreedores_varios": 0.09,
        "otras_deudas_aapp": 0.045, "anticipos_clientes": 0.105,
        "proveedores_empresas_grupo": 0.0,
    },
    "servicios_tic": {
        "proveedores": 0.52, "personal": 0.15, "acreedores_varios": 0.08,
        "otras_deudas_aapp": 0.04, "anticipos_clientes": 0.165,
        "proveedores_empresas_grupo": 0.0,
    },
    "transporte_logistica": {
        "proveedores": 0.75, "personal": 0.08, "acreedores_varios": 0.05,
        "otras_deudas_aapp": 0.03, "anticipos_clientes": 0.06,
        "proveedores_empresas_grupo": 0.0,
    },
    "comercio_hosteleria": {
        "proveedores": 0.80, "personal": 0.065, "acreedores_varios": 0.045,
        "otras_deudas_aapp": 0.03, "anticipos_clientes": 0.03,
        "proveedores_empresas_grupo": 0.0,
    },
    "construccion": {
        "proveedores": 0.68, "personal": 0.05, "acreedores_varios": 0.05,
        "otras_deudas_aapp": 0.03, "anticipos_clientes": 0.16,
        "proveedores_empresas_grupo": 0.0,
    },
    "administracion_educacion_sanidad": {
        "proveedores": 0.58, "personal": 0.14, "acreedores_varios": 0.055,
        "otras_deudas_aapp": 0.04, "anticipos_clientes": 0.15,
        "proveedores_empresas_grupo": 0.0,
    },
    "inmobiliario": {
        "proveedores": 0.65, "personal": 0.05, "acreedores_varios": 0.06,
        "otras_deudas_aapp": 0.035, "anticipos_clientes": 0.17,
        "proveedores_empresas_grupo": 0.0,
    },
}

DISPERSION_PERFIL_DEUDORES_ACREEDORES = 0.20
SUELO_COMPONENTE_DEUDORES_ACREEDORES_PCT = 0.002


def generar_perfil_deudores(rng: np.random.Generator) -> tuple[dict[str, float], dict[str, str]]:
    """Las 7 fracciones oficiales de deudores comerciales para UN caso — perfil único (ver
    docstring arriba), mismo mecanismo que `generar_perfil_existencias` (ruido mixto,
    renormalizado a 1.0). Devuelve también el modo típico/atípico de CADA componente (hallazgo de
    auditoría de trazabilidad — antes se descartaba con `_`, igual que el resto de perfiles de
    este bloque; expuesto ahora para que `EmpresaBase.modos` no pierda esta información, mismo
    criterio que `_generar_balance_pct` ya aplicaba a las masas de nivel superior)."""
    brutos = {}
    modos = {}
    for componente, centro in PERFIL_DEUDORES_BASE.items():
        suelo = SUELO_COMPONENTE_DEUDORES_ACREEDORES_PCT if centro > 0 else 0.0
        valor, modo = _generar_partida(
            rng, centro, max(centro, 0.01) * DISPERSION_PERFIL_DEUDORES_ACREEDORES, suelo=suelo,
        )
        brutos[componente] = valor if centro > 0 else 0.0
        modos[componente] = modo
    return _renormalizar_a_total(brutos, 1.0), modos


def generar_perfil_acreedores(rng: np.random.Generator, categoria: str) -> tuple[dict[str, float], dict[str, str]]:
    """Las 7 fracciones oficiales de acreedores comerciales para UN caso — perfil por categoría
    de sector (ver docstring arriba), mismo mecanismo que `generar_perfil_existencias`. Devuelve
    también el modo típico/atípico de cada componente — ver docstring de `generar_perfil_
    deudores`."""
    perfil_centro = PERFIL_ACREEDORES_POR_CATEGORIA[categoria]
    brutos = {}
    modos = {}
    for componente, centro in perfil_centro.items():
        suelo = SUELO_COMPONENTE_DEUDORES_ACREEDORES_PCT if centro > 0 else 0.0
        valor, modo = _generar_partida(
            rng, centro, max(centro, 0.01) * DISPERSION_PERFIL_DEUDORES_ACREEDORES, suelo=suelo,
        )
        brutos[componente] = valor if centro > 0 else 0.0
        modos[componente] = modo
    return _renormalizar_a_total(brutos, 1.0), modos


# --------------------------------------------------------------------------------------------
# Cuarto y último lote de desglose de balance: Deudas financieras (largo y corto plazo)
# desglosadas según el modelo oficial del PGC — I. Obligaciones y otros valores negociables,
# II. Deudas con entidades de crédito, III. Acreedores por arrendamiento financiero,
# IV. Derivados, V. Otros pasivos financieros. HIPÓTESIS DE DISEÑO (el catálogo ACCID nunca
# desglosó `deudas_fin_largo`/`deudas_fin_corto` más allá del agregado; verificado que ninguna de
# las 218 columnas del catálogo distingue esta financiación por instrumento).
#
# Solo 3 de las 5 categorías tienen un perfil PROPIO aquí (Obligaciones, Arrendamiento financiero,
# Otros pasivos financieros) — "Entidades de crédito" NO se sortea: es el RESIDUAL de restar las
# otras 4 al total (dominante por defecto, es la que ya genera todo el motor hoy). "Derivados" NO
# se sortea aquí en absoluto: Tipo 2 puro, disparado exclusivamente por el arquetipo 21
# (`motor.coberturas_subvenciones`, `cobertura_valor_swap_eur`) — sin probabilidad de fondo, a
# diferencia de las provisiones (no hay razón de negocio para que aparezca sin la cobertura
# activa). Ver `calcular_desglose_deudas_fin` para cómo se ensamblan las 5 juntas cada año.
#
# Arrendamiento financiero: peso por categoría de sector — mayor en sectores con activo material
# significativo en vehículos/maquinaria (transporte_logistica 30%, construcción 22%, industria
# 18% — flotas y maquinaria pesada, conecta de forma natural con las cohortes de amortización de
# motor/amortizacion.py), menor en servicios de oficina (servicios_profesionales/TIC 4-5%).
# Obligaciones y valores negociables: casi cero en la mayoría de sectores (poco típico de PYME/
# empresa mediana española fuera de grandes cotizadas) salvo industria (4% — incluye energía/
# siderurgia, mayor tamaño típico dentro del catálogo). Otros pasivos financieros: residual plano
# (3%), sin base para variarlo por sector.
PERFIL_DEUDAS_FIN_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "industria": {"obligaciones": 0.04, "arrendamiento_financiero": 0.18, "otros_pasivos_financieros": 0.03},
    "servicios_industriales": {"obligaciones": 0.01, "arrendamiento_financiero": 0.15, "otros_pasivos_financieros": 0.03},
    "servicios_profesionales": {"obligaciones": 0.01, "arrendamiento_financiero": 0.04, "otros_pasivos_financieros": 0.03},
    "servicios_tic": {"obligaciones": 0.01, "arrendamiento_financiero": 0.05, "otros_pasivos_financieros": 0.03},
    "transporte_logistica": {"obligaciones": 0.01, "arrendamiento_financiero": 0.30, "otros_pasivos_financieros": 0.03},
    "comercio_hosteleria": {"obligaciones": 0.01, "arrendamiento_financiero": 0.08, "otros_pasivos_financieros": 0.03},
    "construccion": {"obligaciones": 0.01, "arrendamiento_financiero": 0.22, "otros_pasivos_financieros": 0.03},
    "administracion_educacion_sanidad": {"obligaciones": 0.01, "arrendamiento_financiero": 0.06, "otros_pasivos_financieros": 0.03},
    "inmobiliario": {"obligaciones": 0.01, "arrendamiento_financiero": 0.05, "otros_pasivos_financieros": 0.03},
}

# Reparto largo/corto DENTRO de cada categoría — por TIPO de instrumento, no por sector (el
# calendario típico de un contrato de leasing o de una emisión de bonos no varía por sector, a
# diferencia de CUÁNTO peso tiene cada instrumento en el total, que sí es una cuestión sectorial).
# FIJO por caso (sorteado una vez, ruido mixto alrededor de este centro) — la pieza central de la
# confirmación del usuario: `reclasificacion_deuda` (arquetipos 8/16) NUNCA toca este reparto,
# solo el de "Entidades de crédito" (ver `calcular_desglose_deudas_fin`) — un leasing tiene
# calendario fijo por contrato, un bono no se renegocia como un préstamo bancario, ninguno de los
# dos debería desplazarse solo porque el arquetipo 8/16 actúe sobre la deuda bancaria.
FRACCION_LARGO_POR_TIPO_DEUDA_FIN: dict[str, float] = {
    "arrendamiento_financiero": 0.75,  # contrato multianual: la mayor parte del saldo sigue siendo a largo
    "obligaciones": 0.85,  # emisiones a varios años, largo salvo cerca del vencimiento
    "otros_pasivos_financieros": 0.55,  # residual/mixto, sin sesgo fuerte hacia ningún plazo
}

DISPERSION_PERFIL_DEUDAS_FIN = 0.20
SUELO_COMPONENTE_DEUDAS_FIN_PCT = 0.002
DISPERSION_FRACCION_LARGO_DEUDAS_FIN = 0.15
SUELO_FRACCION_LARGO_DEUDAS_FIN = 0.10
TECHO_FRACCION_LARGO_DEUDAS_FIN = 0.95


def generar_perfil_deudas_fin(
    rng: np.random.Generator, categoria: str
) -> tuple[dict[str, float], dict[str, float], dict[str, str], dict[str, str]]:
    """Perfil fijo por caso para el desglose de deudas financieras — `fraccion_total` (peso de
    cada una de las 3 categorías con perfil propio sobre el total de deuda financiera CON coste,
    ver docstring arriba) y `fraccion_largo` (su propio reparto largo/corto, fijo, por tipo de
    instrumento). Ninguno de los dos se renormaliza a 1.0: "Entidades de crédito" absorbe lo que
    quede del total, y "Derivados" no participa de este perfil en absoluto (ver
    `calcular_desglose_deudas_fin`). Devuelve también el modo típico/atípico de cada componente de
    AMBOS repartos (`modos_total`/`modos_largo`) — ver docstring de `generar_perfil_deudores`."""
    perfil_centro = PERFIL_DEUDAS_FIN_POR_CATEGORIA[categoria]
    fraccion_total = {}
    modos_total = {}
    for tipo, centro in perfil_centro.items():
        valor, modo = _generar_partida(rng, centro, centro * DISPERSION_PERFIL_DEUDAS_FIN, suelo=SUELO_COMPONENTE_DEUDAS_FIN_PCT)
        fraccion_total[tipo] = valor
        modos_total[tipo] = modo
    fraccion_largo = {}
    modos_largo = {}
    for tipo, centro in FRACCION_LARGO_POR_TIPO_DEUDA_FIN.items():
        valor, modo = _generar_partida(
            rng, centro, centro * DISPERSION_FRACCION_LARGO_DEUDAS_FIN,
            suelo=SUELO_FRACCION_LARGO_DEUDAS_FIN, techo=TECHO_FRACCION_LARGO_DEUDAS_FIN,
        )
        fraccion_largo[tipo] = valor
        modos_largo[tipo] = modo
    return fraccion_total, fraccion_largo, modos_total, modos_largo


def calcular_desglose_deudas_fin(
    fraccion_total: dict[str, float],
    fraccion_largo: dict[str, float],
    deudas_fin_largo_con_coste_eur: float,
    deudas_fin_corto_eur: float,
    derivados_pasivo_largo_eur: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Ensambla las 5 categorías del año (largo y corto), a partir del perfil FIJO del caso
    (`fraccion_total`/`fraccion_largo`) aplicado sobre las masas YA cuadradas de ESTE año —
    reutilizado tal cual desde `empresa_base.generar_empresa_base` (año base, sin reclasificación
    ni derivados activos todavía) y desde `evolucion_arquetipo._evolucionar_un_año` (2024/2025,
    después de la contención de endeudamiento). `deudas_fin_largo_con_coste_eur` es la base CON
    coste (excluye derivados — ver docstring del módulo evolucion_arquetipo, "Derivados" bloque):
    nunca incluye el derivado, que se añade aparte al final, siempre en largo plazo.

    "Entidades de crédito" es el RESIDUAL (`deudas_fin_largo_con_coste_eur - suma de las otras 3
    en largo`, y análogo en corto) — así absorbe automáticamente cualquier movimiento de
    `reclasificacion_deuda` (arquetipos 8/16, que solo mueve el TOTAL entre largo y corto, ver
    ese bloque) sin que arrendamiento financiero/obligaciones/otros pasivos financieros —cuyo
    reparto largo/corto es fijo por contrato, no renegociable— se vean arrastrados. Técho
    defensivo: si el reparto fijo de esas 3 categorías en largo (poco común, solo con
    reclasificación muy agresiva) superara la base real de ese plazo, se reescala
    proporcionalmente ENTRE ELLAS (conservando el total de cada categoría, solo cambia SU PROPIO
    reparto largo/corto ese año) para que la suma nunca supere el total real — "Entidades de
    crédito" nunca queda negativo, la suma de las 5 sigue cuadrando exacto con el total."""
    deuda_total_con_coste_eur = deudas_fin_largo_con_coste_eur + deudas_fin_corto_eur
    categoria_eur = {tipo: fraccion * deuda_total_con_coste_eur for tipo, fraccion in fraccion_total.items()}
    categoria_largo_eur = {tipo: fraccion_largo[tipo] * valor for tipo, valor in categoria_eur.items()}
    categoria_corto_eur = {tipo: categoria_eur[tipo] - categoria_largo_eur[tipo] for tipo in categoria_eur}

    suma_largo_fijo_eur = sum(categoria_largo_eur.values())
    if suma_largo_fijo_eur > deudas_fin_largo_con_coste_eur and suma_largo_fijo_eur > 0:
        factor = deudas_fin_largo_con_coste_eur / suma_largo_fijo_eur
        for tipo in categoria_largo_eur:
            exceso_eur = categoria_largo_eur[tipo] * (1 - factor)
            categoria_largo_eur[tipo] -= exceso_eur
            categoria_corto_eur[tipo] += exceso_eur
    suma_corto_fijo_eur = sum(categoria_corto_eur.values())
    if suma_corto_fijo_eur > deudas_fin_corto_eur and suma_corto_fijo_eur > 0:
        factor = deudas_fin_corto_eur / suma_corto_fijo_eur
        for tipo in categoria_corto_eur:
            exceso_eur = categoria_corto_eur[tipo] * (1 - factor)
            categoria_corto_eur[tipo] -= exceso_eur
            categoria_largo_eur[tipo] += exceso_eur

    entidades_credito_largo_eur = deudas_fin_largo_con_coste_eur - sum(categoria_largo_eur.values())
    entidades_credito_corto_eur = deudas_fin_corto_eur - sum(categoria_corto_eur.values())

    desglose_largo_eur = {"entidades_credito": entidades_credito_largo_eur, **categoria_largo_eur, "derivados": derivados_pasivo_largo_eur}
    desglose_corto_eur = {"entidades_credito": entidades_credito_corto_eur, **categoria_corto_eur, "derivados": 0.0}
    return desglose_largo_eur, desglose_corto_eur


# --------------------------------------------------------------------------------------------
# Quinto lote de desglose de balance: "Otras deudas" (largo y corto plazo) — carve-out de
# `otras_deudas_largo`/`otras_deudas_corto`. HIPÓTESIS DE DISEÑO explícita, mismo nivel de
# honestidad que `PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA`: `otras_deudas_largo_pct`/`otras_
# deudas_corto_pct` SÍ son dato ACCID real y directo (docs/ratios2024.pdf, tabla "BALANCE DE
# SITUACIÓN (%)" por sector) — pero ACCID no define su composición interna en ningún sitio
# (glosario revisado, sin entrada). Perfil PLANO (no por categoría de sector, a diferencia de
# existencias/deudores/acreedores/deudas_fin): a diferencia de esos 4 lotes, aquí no hay NINGÚN
# dato de catálogo (ni siquiera indirecto, como gastos_personal_pct para acreedores) que sugiera
# una dirección cualitativa de variación sectorial — fabricar una diferenciación sin base sería
# menos honesto que declarar el perfil plano, mismo criterio que `PROBABILIDAD_PROVISION` en
# `motor/provisiones.py` ("Probabilidad PLANA... no hay base razonada para variar por sector").
#
# Composición oficial (PGC): "Pasivo no corriente" = I. Provisiones a l/p (tercer lote,
# `motor/provisiones.py`) + II. Deudas a l/p (ESTE lote) + III. Deudas con empresas del grupo a
# l/p (arquetipo 20) + IV. Pasivos por impuesto diferido (grupo 8/9) + V. Periodificaciones a l/p
# (primer lote, un % INFORMATIVO del agregado, no una resta de él). I/III/IV se SUMAN sobre
# `otras_deudas_largo_eur` en `motor/evolucion_arquetipo.py` (nunca se sortean como fracción
# suya) — este lote desglosa solo lo que QUEDA tras restarlas ("residual"), para no re-etiquetar
# el mismo euro bajo dos epígrafes oficiales distintos a la vez (mismo criterio que excluye
# "Derivados" de la base sorteada en `calcular_desglose_deudas_fin`, cuarto lote). En "Pasivo
# corriente" solo hay una pieza equivalente: II. Provisiones a c/p (tercer lote) — no existe
# "deudas con el grupo" ni "pasivos por impuesto diferido" a corto plazo en este motor.
#
# Residuo LARGO ("II. Deudas a largo plazo", el auténtico "otras deudas" no financieras del PGC):
#   - `acreedores_inmovilizado` (dominante): "Acreedores por adquisición de inmovilizado a largo
#     plazo" — proveedores de maquinaria/vehículos/equipos con pago aplazado multianual, distinto
#     de "proveedores" de acreedores_comerciales (segundo lote, siempre plazo corto).
#   - `fianzas_depositos` (moderado): fianzas/depósitos recibidos a largo plazo (alquileres,
#     contratos de suministro/concesión con garantía retenida varios años).
#   - `deudas_socios` (probabilidad de fondo, minoritario cuando activa, 0 en caso contrario):
#     préstamos de socios/administradores a la sociedad — situación real pero NO estructural de
#     una empresa española típica (a diferencia de deuda bancaria o de proveedores). Sin ancla a
#     ningún ratio del catálogo NI boost de arquetipo (ninguno de los existentes modela
#     financiación de socios): activación única por caso, probabilidad deliberadamente baja
#     (`PROBABILIDAD_DEUDAS_SOCIOS_LARGO`) — "partida atípica" se refleja en esa probabilidad de
#     activación baja, no en el modo típico/atípico del sorteo continuo de magnitud (que sigue el
#     mismo mecanismo neutro que el resto de componentes).
#   - `remanente` (pequeño, siempre presente): "Acreedores comerciales no corrientes" + "Deuda
#     con características especiales" — 2 epígrafes oficiales minoritarios sin mecanismo propio
#     en el motor, agrupados (mismo criterio que "otros_pasivos_financieros" en el cuarto lote).
#
# Residuo CORTO ("Deudas a corto plazo" no financieras) — el añadido propio de este lote frente a
# los anteriores es la RECLASIFICACIÓN anual largo->corto de `acreedores_inmovilizado`, mismo
# ESPÍRITU que la de provisiones (`motor/provisiones.py`) pero sin horizonte sorteado por
# instancia: se usa un PLAZO TÍPICO FIJO (hipótesis de diseño, `PLAZO_ACREEDORES_INMOVILIZADO_
# AÑOS=3` — financiación de proveedor de inmovilizado típica en España: más larga que el crédito
# comercial ordinario de acreedores_comerciales -segundo lote- pero claramente más corta que un
# préstamo bancario a largo -deudas_fin_largo- o el calendario multianual de un leasing
# -arrendamiento_financiero, ambos cuarto lote-). Cada año, 1/PLAZO del saldo de `acreedores_
# inmovilizado` LARGO DEL AÑO ANTERIOR se reclasifica a corto (`FRACCION_RECLASIFICACION_
# ACREEDORES_INMOVILIZADO = 1/3`) — 0 en el año base (2023, sin "año anterior"), mismo criterio
# que "Derivados" en el cuarto lote.
#   - `acreedores_inmovilizado` = reclasificación (arriba) + "nuevas compras a corto desde
#     origen" (perfil propio, pequeño, sobre el residuo TRAS restar la reclasificación y
#     `aapp_pendiente` — compras de inmovilizado de importe pequeño que nacen directamente a
#     corto plazo, sin pasar nunca por largo).
#   - `fianzas_depositos` (moderado sobre ese mismo residuo): igual naturaleza que en largo.
#   - `aapp_pendiente` (probabilidad de fondo BAJA + boost de arquetipo 4/7, mismo mecanismo que
#     `motor/insolvencias.py`): a diferencia de los 2 componentes de arriba, NO forma parte del
#     perfil fijo-desde-2023 — se RE-INVOCA cada año (`sortear_aapp_pendiente_corto_pct`) en vez de
#     congelarse en el año base (sin arquetipos activos todavía, el boost de arquetipo 4
#     "deterioro_ciclo_caja"/7 "dependencia_pocos_clientes" nunca tendría forma de alterarlo si se
#     fijara ahí). Pese a re-invocarse, el resultado es DETERMINISTA para una misma semilla/sector/
#     segmento/boost, NO un sorteo año a año independiente — ver docstring de `sortear_aapp_
#     pendiente_corto_pct` para la propiedad completa (verificada empíricamente: con el mismo
#     arquetipo activo en 2024 y 2025, el resultado es IDÉNTICO en ambos años, sin excepciones en
#     200 casos de prueba — nunca "parpadea" entre años pese a no llevar un campo de estado propio).
#     Representa un aplazamiento/fraccionamiento excepcional de deuda con la AEAT/TGSS a corto
#     plazo (distinto de `otras_deudas_aapp`, dentro de acreedores_comerciales, segundo lote, que
#     es corriente ordinario) — más plausible cuando el ciclo de caja ya se ha deteriorado (4) o
#     hay concentración de riesgo de cobro (7), mismo razonamiento económico que ya justifica el
#     boost de insolvencias sobre esos 2 arquetipos.
#   - `remanente` (pequeño, sobre ese mismo residuo tras restar reclasificación y aapp_pendiente).
# --------------------------------------------------------------------------------------------
PERFIL_OTRAS_DEUDAS_LARGO_CENTRO: dict[str, float] = {
    "acreedores_inmovilizado": 0.55,
    "fianzas_depositos": 0.30,
    "deudas_socios": 0.10,  # forzado a 0.0 si no activa, ver generar_perfil_otras_deudas
    "remanente": 0.05,
}

# Reparto del residuo de corto TRAS restar la reclasificación de acreedores_inmovilizado y
# aapp_pendiente (ver docstring arriba) — "acreedores_inmovilizado" aquí es SOLO la porción de
# "nuevas compras a corto desde origen", no el total (que se completa sumando la reclasificación
# en `calcular_desglose_otras_deudas`).
PERFIL_OTRAS_DEUDAS_CORTO_RESTO_CENTRO: dict[str, float] = {
    "acreedores_inmovilizado": 0.20,
    "fianzas_depositos": 0.55,
    "remanente": 0.25,
}

DISPERSION_PERFIL_OTRAS_DEUDAS = 0.20
SUELO_COMPONENTE_OTRAS_DEUDAS_PCT = 0.005

PROBABILIDAD_DEUDAS_SOCIOS_LARGO = 0.12  # "minoritario"/"atípica" — deliberadamente baja, sin ancla ni boost de arquetipo

PLAZO_ACREEDORES_INMOVILIZADO_AÑOS = 3.0
FRACCION_RECLASIFICACION_ACREEDORES_INMOVILIZADO = 1.0 / PLAZO_ACREEDORES_INMOVILIZADO_AÑOS

# aapp_pendiente — mismo mecanismo que motor.insolvencias (probabilidad plana baja + boost
# aditivo capado de probabilidad + boost multiplicativo de magnitud), pero sorteado FRESCO cada
# año en vez de fijo desde 2023 (ver docstring arriba). Probabilidad base más baja que la de
# insolvencias (20%-40%, anclada a cobro_dias) o provisiones (25%, plana): un aplazamiento
# excepcional con la AEAT/TGSS es, de partida, menos común que un deterioro de cliente concreto o
# una provisión genérica.
PROBABILIDAD_AAPP_PENDIENTE_BASE = 0.12
BOOST_PROBABILIDAD_AAPP_DETERIORO_CICLO_CAJA = 0.10
BOOST_PROBABILIDAD_AAPP_DEPENDENCIA_CLIENTES = 0.10
TECHO_PROBABILIDAD_AAPP_PENDIENTE_ABSOLUTO = 0.32
CENTRO_AAPP_PENDIENTE_CORTO_PCT = 0.10  # fracción del residuo de corto (tras reclasificación) cuando activa
MULTIPLICADOR_MAGNITUD_AAPP_PENDIENTE_BOOST = 1.3  # mismo valor que MULTIPLICADOR_MAGNITUD_BOOST de insolvencias
DISPERSION_AAPP_PENDIENTE = 0.20
SUELO_COMPONENTE_AAPP_PENDIENTE_PCT = 0.005
TECHO_AAPP_PENDIENTE_PCT = 0.25


def _entropia_otras_deudas(sector: str, segmento: str, sufijo: str) -> int:
    return zlib.crc32(f"{sector}|{segmento}|otras_deudas{sufijo}".encode("utf-8"))


def sortear_deudas_socios_baseline(sector: str, segmento: str, semilla: int) -> bool:
    """Activación ÚNICA por caso (fija desde 2023, sin boost de ningún arquetipo — ninguno de los
    existentes modela financiación de socios/administradores) de si el caso tiene una partida de
    "Deudas con socios y administradores a largo plazo" — ver docstring del módulo para el
    razonamiento de la probabilidad deliberadamente baja."""
    rng = np.random.default_rng([semilla, _entropia_otras_deudas(sector, segmento, "_deudas_socios_baseline")])
    return _resolver_binario_por_modo(rng, PROBABILIDAD_DEUDAS_SOCIOS_LARGO)


def generar_perfil_otras_deudas(
    rng: np.random.Generator, deudas_socios_activa: bool
) -> tuple[dict[str, float], dict[str, float], dict[str, str], dict[str, str]]:
    """Perfil fijo por caso (largo + resto de corto, ver docstring del módulo) para el quinto
    lote de desglose de balance — mismo mecanismo de ruido mixto/renormalizado que `generar_
    perfil_deudores`. `deudas_socios_activa` fuerza su centro a 0.0 si no activa (igual criterio
    que los componentes de centro 0 en `PERFIL_DEUDORES_BASE`) — la activación en sí se decide
    aparte, en `sortear_deudas_socios_baseline`. `aapp_pendiente` NO forma parte de este perfil
    fijo: se sortea fresco cada año, ver `sortear_aapp_pendiente_corto_pct`."""
    brutos_largo: dict[str, float] = {}
    modos_largo: dict[str, str] = {}
    for componente, centro in PERFIL_OTRAS_DEUDAS_LARGO_CENTRO.items():
        centro_efectivo = centro if (componente != "deudas_socios" or deudas_socios_activa) else 0.0
        suelo = SUELO_COMPONENTE_OTRAS_DEUDAS_PCT if centro_efectivo > 0 else 0.0
        valor, modo = _generar_partida(
            rng, centro_efectivo, max(centro_efectivo, 0.01) * DISPERSION_PERFIL_OTRAS_DEUDAS, suelo=suelo,
        )
        brutos_largo[componente] = valor if centro_efectivo > 0 else 0.0
        modos_largo[componente] = modo
    perfil_largo = _renormalizar_a_total(brutos_largo, 1.0)

    brutos_corto: dict[str, float] = {}
    modos_corto: dict[str, str] = {}
    for componente, centro in PERFIL_OTRAS_DEUDAS_CORTO_RESTO_CENTRO.items():
        valor, modo = _generar_partida(
            rng, centro, centro * DISPERSION_PERFIL_OTRAS_DEUDAS, suelo=SUELO_COMPONENTE_OTRAS_DEUDAS_PCT,
        )
        brutos_corto[componente] = valor
        modos_corto[componente] = modo
    perfil_corto_resto = _renormalizar_a_total(brutos_corto, 1.0)

    return perfil_largo, perfil_corto_resto, modos_largo, modos_corto


def probabilidad_aapp_pendiente(deterioro_ciclo_caja_activo: bool, dependencia_clientes_activo: bool) -> float:
    boost = 0.0
    if deterioro_ciclo_caja_activo:
        boost += BOOST_PROBABILIDAD_AAPP_DETERIORO_CICLO_CAJA
    if dependencia_clientes_activo:
        boost += BOOST_PROBABILIDAD_AAPP_DEPENDENCIA_CLIENTES
    return min(PROBABILIDAD_AAPP_PENDIENTE_BASE + boost, TECHO_PROBABILIDAD_AAPP_PENDIENTE_ABSOLUTO)


def sortear_aapp_pendiente_corto_pct(
    sector: str,
    segmento: str,
    semilla: int,
    deterioro_ciclo_caja_activo: bool,
    dependencia_clientes_activo: bool,
) -> tuple[float, str]:
    """Fracción (0.0 si inactiva) del residuo de `otras_deudas_corto` para `aapp_pendiente` — se
    RE-INVOCA cada año (nunca fijo desde 2023 como el resto del perfil, ver docstring del módulo:
    no se guarda en ningún campo `anterior.xxx`), pero el resultado es DETERMINISTA para una
    misma combinación (sector, segmento, semilla, boosts) — no un sorteo año a año independiente.
    La entropía del rng (`_entropia_otras_deudas`) depende SOLO de sector/segmento/semilla, sin
    año: con las mismas banderas de boost, dos llamadas cualesquiera devuelven el mismo resultado
    bit a bit.

    Consecuencia práctica IMPORTANTE (verificado empíricamente, no solo argumentado — 27 sectores
    x hasta 20 semillas, arquetipo 4 y arquetipo 7 por separado, 0 excepciones en 200 casos): como
    `deterioro_ciclo_caja_activo`/`dependencia_clientes_activo` son propiedades del CASO completo
    en `motor.evolucion_arquetipo` (un arquetipo activo en `definiciones` lo está en 2024 Y 2025
    por igual — nunca se enciende/apaga a mitad de caso), la re-invocación anual NO produce
    "parpadeo" entre 2024 y 2025: si el boost está activo los dos años, el resultado (activación Y
    magnitud) es IDÉNTICO en ambos — la continuidad no viene de un campo de estado tipo `saldo_eur`
    (como en `motor.insolvencias`), sino de que la fórmula es una función pura y determinista de
    entradas que, en la práctica, no cambian de un año al siguiente dentro del mismo caso. La única
    transición real posible es 2023 (boost siempre False/False, los arquetipos no actúan todavía)
    -> 2024/2025 (boost real): ahí SÍ puede activarse por primera vez, pero nunca "parpadea" entre
    2024 y 2025. Ver `tests/test_desglose_otras_deudas.py::test_aapp_pendiente_continuidad_
    determinista_entre_2024_y_2025` para la comprobación permanente de esta propiedad.

    La activación en sí usa un rng propio: el mismo `rng.random()` se compara cada vez contra
    `probabilidad_aapp_pendiente(...)`, que solo puede SUBIR con los boosts — así, si activa sin
    boost, activa también con boost (monotonía, mismo criterio que `sortear_insolvencia_
    baseline`)."""
    rng_activacion = np.random.default_rng(
        [semilla, _entropia_otras_deudas(sector, segmento, "_aapp_pendiente_activacion")]
    )
    probabilidad = probabilidad_aapp_pendiente(deterioro_ciclo_caja_activo, dependencia_clientes_activo)
    activa = _resolver_binario_por_modo(rng_activacion, probabilidad)
    if not activa:
        return 0.0, "tipico"

    rng_magnitud = np.random.default_rng(
        [semilla, _entropia_otras_deudas(sector, segmento, "_aapp_pendiente_magnitud")]
    )
    centro = CENTRO_AAPP_PENDIENTE_CORTO_PCT
    if deterioro_ciclo_caja_activo or dependencia_clientes_activo:
        centro *= MULTIPLICADOR_MAGNITUD_AAPP_PENDIENTE_BOOST
    return _generar_partida(
        rng_magnitud, centro, centro * DISPERSION_AAPP_PENDIENTE,
        suelo=SUELO_COMPONENTE_AAPP_PENDIENTE_PCT, techo=TECHO_AAPP_PENDIENTE_PCT,
    )


def calcular_desglose_otras_deudas(
    perfil_largo_pct: dict[str, float],
    perfil_corto_resto_pct: dict[str, float],
    aapp_pendiente_corto_pct: float,
    otras_deudas_largo_residual_eur: float,
    otras_deudas_corto_residual_eur: float,
    acreedores_inmovilizado_largo_anterior_eur: float,
    fianzas_depositos_largo_eur: float | None = None,
    fianzas_depositos_corto_eur: float | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Ensambla las 4 sub-partidas de cada plazo del quinto lote sobre el residuo YA excluidas
    provisiones (tercer lote)/deudas con el grupo (arquetipo 20)/pasivos por impuesto diferido
    (grupo 8/9)/periodificaciones de pasivo (primer lote) — ver docstring del módulo.
    `otras_deudas_corto_residual_eur` se defiende con
    `max(0.0, ...)` en la llamada (no aquí) frente al caso extremo, no observado en el barrido, en
    que el plug de cuadre (que SÍ puede tocar `otras_deudas_corto`, a diferencia de largo) dejara
    el residuo por debajo de 0.

    Reclasificación (ver docstring del módulo): `FRACCION_RECLASIFICACION_ACREEDORES_
    INMOVILIZADO` del saldo de `acreedores_inmovilizado` LARGO del año anterior (0.0 en el año
    base) se suma al `acreedores_inmovilizado` de corto de este año, por encima de su propio
    perfil fijo (que solo cubre "nuevas compras a corto desde origen"). Técho defensivo (mismo
    espíritu que `calcular_desglose_deudas_fin`): la reclasificación y `aapp_pendiente` juntas
    nunca superan el residuo de corto real, así que la suma final nunca lo excede.

    `fianzas_depositos_largo_eur`/`..._corto_eur` (decisiones_plausibilidad.md #99, Parte B):
    cuando se pasan (no None — solo desde `evolucion_arquetipo._evolucionar_un_año`, NUNCA desde
    el año base 2023, que sigue usando el perfil % fijo tal cual), sustituyen el importe que
    tocaría a "fianzas_depositos" por su propia dinámica externa (crecimiento atenuado, ajeno a
    este módulo) — el resto del perfil (excluyendo esa clave) se renormaliza a 1.0 sobre el
    residuo YA restado ese importe, para que la suma total no cambie. `aapp_pendiente_eur`/
    `reclasificado_eur` (más abajo) se calculan SIEMPRE sobre el residuo COMPLETO de corto, sin
    restar la fianza — solo la parte "resto" (perfil_corto_resto_pct) se ve afectada. Técho
    defensivo (mismo espíritu que `reclasificado_eur` un poco más abajo y que
    `calcular_desglose_deudas_fin`): si la masa total se ha encogido tanto (típicamente el plug de
    cuadre general, que SÍ puede reducir `otras_deudas_corto` de un año a otro) que la fianza
    "atenuada" ya no cabe en el residuo disponible, se recorta al residuo completo (deja 0, nunca
    negativo, al resto del perfil) en vez de dejar acreedores_inmovilizado/remanente en negativo."""
    if fianzas_depositos_largo_eur is None:
        desglose_largo = {c: f * otras_deudas_largo_residual_eur for c, f in perfil_largo_pct.items()}
    else:
        fianzas_depositos_largo_efectivo_eur = max(0.0, min(fianzas_depositos_largo_eur, otras_deudas_largo_residual_eur))
        perfil_largo_sin_fianzas_pct = {c: f for c, f in perfil_largo_pct.items() if c != "fianzas_depositos"}
        presupuesto_largo_normal_eur = otras_deudas_largo_residual_eur - fianzas_depositos_largo_efectivo_eur
        desglose_largo = _renormalizar_a_total(perfil_largo_sin_fianzas_pct, presupuesto_largo_normal_eur)
        desglose_largo["fianzas_depositos"] = fianzas_depositos_largo_efectivo_eur

    aapp_pendiente_eur = aapp_pendiente_corto_pct * otras_deudas_corto_residual_eur
    reclasificado_bruto_eur = acreedores_inmovilizado_largo_anterior_eur * FRACCION_RECLASIFICACION_ACREEDORES_INMOVILIZADO
    reclasificado_eur = max(0.0, min(reclasificado_bruto_eur, otras_deudas_corto_residual_eur - aapp_pendiente_eur))
    resto_corto_eur = max(0.0, otras_deudas_corto_residual_eur - aapp_pendiente_eur - reclasificado_eur)

    if fianzas_depositos_corto_eur is None:
        desglose_corto = {c: f * resto_corto_eur for c, f in perfil_corto_resto_pct.items()}
    else:
        fianzas_depositos_corto_efectivo_eur = max(0.0, min(fianzas_depositos_corto_eur, resto_corto_eur))
        perfil_corto_resto_sin_fianzas_pct = {c: f for c, f in perfil_corto_resto_pct.items() if c != "fianzas_depositos"}
        presupuesto_corto_normal_eur = resto_corto_eur - fianzas_depositos_corto_efectivo_eur
        desglose_corto = _renormalizar_a_total(perfil_corto_resto_sin_fianzas_pct, presupuesto_corto_normal_eur)
        desglose_corto["fianzas_depositos"] = fianzas_depositos_corto_efectivo_eur
    desglose_corto["acreedores_inmovilizado"] += reclasificado_eur
    desglose_corto["aapp_pendiente"] = aapp_pendiente_eur

    return desglose_largo, desglose_corto


def categoria_de_sector(sector_codigo: str) -> str:
    if sector_codigo not in CATEGORIA_SECTOR:
        raise EmpresaBaseError(f"Sector '{sector_codigo}' no tiene categoría asignada en CATEGORIA_SECTOR.")
    return CATEGORIA_SECTOR[sector_codigo]


# --------------------------------------------------------------------------------------------
# Desglose de PyG en líneas oficiales del PGC (Ronda 1 del encargo de desglose de PyG) — se
# AÑADE ENCIMA de los agregados de `PRIMITIVAS_PYG` (que siguen existiendo sin cambios para el
# análisis interno): cada bloque de abajo reparte un agregado YA generado en sus sub-partidas
# oficiales, sin sortear el agregado dos veces. HIPÓTESIS DE DISEÑO salvo donde se indica un
# anclaje externo (gastos_personal → cargas sociales). Perfil por CATEGORÍA de sector (las
# mismas 9 de CATEGORIA_SECTOR), mismo mecanismo de ruido mixto/renormalizado a 1.0 que
# `generar_perfil_existencias`, con RNG PROPIO E INDEPENDIENTE (no desplaza ningún sorteo ya
# existente).
#
# 1) Cifra de negocios -> a) Ventas / b) Prestación de servicios. Sin dato ACCID que lo
#    respalde: industria/comercio_hosteleria/construccion venden mayoritariamente bienes
#    físicos (ventas dominante); servicios_profesionales/servicios_tic son prestación de
#    servicios casi pura; el resto (servicios_industriales, transporte_logistica,
#    administracion_educacion_sanidad, inmobiliario) se trata como mixto, sin dominancia clara.
PERFIL_CIFRA_NEGOCIOS_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "industria": {"ventas": 0.90, "servicios": 0.10},
    "comercio_hosteleria": {"ventas": 0.92, "servicios": 0.08},
    "construccion": {"ventas": 0.75, "servicios": 0.25},
    "servicios_profesionales": {"ventas": 0.05, "servicios": 0.95},
    "servicios_tic": {"ventas": 0.10, "servicios": 0.90},
    "servicios_industriales": {"ventas": 0.45, "servicios": 0.55},
    "transporte_logistica": {"ventas": 0.35, "servicios": 0.65},
    "administracion_educacion_sanidad": {"ventas": 0.15, "servicios": 0.85},
    "inmobiliario": {"ventas": 0.55, "servicios": 0.45},
}

# 2) Consumos de explotación -> a) Mercaderías / b) Materias primas y otros aprovisionamientos /
#    c) Trabajos realizados por otras empresas / d) Deterioro de mercaderías, materias primas y
#    otros aprovisionamientos. Comercio/hostelería reventa mercadería (a dominante); industria
#    consume materia prima propia (b dominante); construcción/servicios subcontratan una parte
#    grande de su "coste de ventas" (c dominante en construcción y en los 2 sectores de
#    servicios, donde apenas hay materia prima real que consumir).
PERFIL_CONSUMOS_EXPLOTACION_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "industria": {"materias_primas": 0.75, "mercaderias": 0.05, "trabajos_otras_empresas": 0.15, "deterioro": 0.05},
    "comercio_hosteleria": {"mercaderias": 0.80, "materias_primas": 0.10, "trabajos_otras_empresas": 0.05, "deterioro": 0.05},
    "construccion": {"trabajos_otras_empresas": 0.50, "materias_primas": 0.35, "mercaderias": 0.05, "deterioro": 0.10},
    "servicios_profesionales": {"trabajos_otras_empresas": 0.70, "mercaderias": 0.10, "materias_primas": 0.10, "deterioro": 0.10},
    "servicios_tic": {"trabajos_otras_empresas": 0.65, "mercaderias": 0.15, "materias_primas": 0.05, "deterioro": 0.15},
    "servicios_industriales": {"trabajos_otras_empresas": 0.45, "materias_primas": 0.30, "mercaderias": 0.10, "deterioro": 0.15},
    "transporte_logistica": {"materias_primas": 0.55, "trabajos_otras_empresas": 0.30, "mercaderias": 0.10, "deterioro": 0.05},
    "administracion_educacion_sanidad": {"trabajos_otras_empresas": 0.40, "materias_primas": 0.35, "mercaderias": 0.10, "deterioro": 0.15},
    "inmobiliario": {"trabajos_otras_empresas": 0.55, "materias_primas": 0.15, "mercaderias": 0.10, "deterioro": 0.20},
}

# 3) Otros gastos de explotación -> a) Servicios exteriores / b) Tributos / c) Pérdidas,
#    deterioro y variación de provisiones por operaciones comerciales / d) Otros gastos de
#    gestión corriente / e) Gases de efecto invernadero. Solo a)/b)/d) llevan perfil propio (3
#    componentes, suman 1.0): c) es la dotación YA sorteada de `motor.insolvencias` (cuenta 490,
#    nunca un sorteo nuevo — ver `calcular_desglose_otros_gastos_explot`); e) siempre 0.0, sin
#    mecanismo que lo alimente (fuera de alcance documentado, igual criterio que
#    `b_resto_fuera_de_alcance` del Documento A del ECPN). Servicios exteriores domina en todos
#    los sectores (alquileres, suministros, profesionales independientes); inmobiliario lleva
#    más peso en tributos (IBI).
PERFIL_OTROS_GASTOS_EXPLOT_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "industria": {"servicios_exteriores": 0.75, "tributos": 0.10, "otros_gestion_corriente": 0.15},
    "servicios_industriales": {"servicios_exteriores": 0.80, "tributos": 0.08, "otros_gestion_corriente": 0.12},
    "servicios_profesionales": {"servicios_exteriores": 0.85, "tributos": 0.05, "otros_gestion_corriente": 0.10},
    "servicios_tic": {"servicios_exteriores": 0.85, "tributos": 0.05, "otros_gestion_corriente": 0.10},
    "transporte_logistica": {"servicios_exteriores": 0.78, "tributos": 0.09, "otros_gestion_corriente": 0.13},
    "comercio_hosteleria": {"servicios_exteriores": 0.75, "tributos": 0.10, "otros_gestion_corriente": 0.15},
    "construccion": {"servicios_exteriores": 0.72, "tributos": 0.12, "otros_gestion_corriente": 0.16},
    "administracion_educacion_sanidad": {"servicios_exteriores": 0.80, "tributos": 0.07, "otros_gestion_corriente": 0.13},
    "inmobiliario": {"servicios_exteriores": 0.70, "tributos": 0.15, "otros_gestion_corriente": 0.15},
}

DISPERSION_PERFIL_PYG_OFICIAL = 0.20
SUELO_COMPONENTE_PYG_OFICIAL_PCT = 0.005

# 4) Gastos de personal -> a) Sueldos y salarios / b) Cargas sociales / c) Provisiones. b) está
# ANCLADO EXTERNAMENTE (no es una hipótesis de diseño): tipos de cotización empresarial vigentes
# para 2023-2025, verificados contra el BOE (Orden anual de cotización a la Seguridad Social).
# Verificado explícitamente para este encargo (septiembre de 2026, no de memoria) que la Orden
# PJC/178/2025 (la vigente cuando se redactó el encargo) sigue siendo la aplicable a estos 3
# años: existe una Orden más reciente, PJC/297/2026 (BOE 31/03/2026), pero rige el ejercicio
# 2026, fuera del rango que genera este motor (siempre 2023-2025) — no cambia nada de lo de
# abajo. Contingencias comunes (23,60pp empresa), desempleo régimen general indefinido (5,50pp
# empresa), FOGASA (0,20pp) y formación profesional (0,60pp empresa) se mantuvieron PLANOS los 3
# años (sin cambio legal en el periodo, confirmado contra la propia Orden 2026, que "mantiene los
# tipos del ejercicio anterior" en estos 4 conceptos) — total plano 29,90pp. El MEI (Mecanismo de
# Equidad Intergeneracional, Ley 21/2021) SÍ escala cada año de su implantación progresiva:
# 0,50pp (2023), 0,58pp (2024), 0,67pp (2025) de cuota empresarial — verificado externamente
# (evolución 0,60/0,70/0,80pp total, ~5/6 a cargo de la empresa cada año). La prima de accidentes
# de trabajo, en cambio, SÍ es una hipótesis de diseño (varía por actividad real de cada empresa,
# no por sector agregado con precisión suficiente para anclarla): se usa el orden de magnitud de
# la Tarifa de primas (RD 2930/1979) — construcción/industria/transporte con activo material y
# riesgo físico más alto, oficina (servicios profesionales/TIC) en el mínimo legal.
TASA_CARGAS_SOCIALES_BASE_PP = 0.2990  # 23,60 (CC) + 5,50 (desempleo indefinido) + 0,20 (FOGASA) + 0,60 (FP), empresa
MEI_EMPRESARIAL_PP_POR_AÑO: dict[int, float] = {2023: 0.0050, 2024: 0.0058, 2025: 0.0067}
PRIMA_ACCIDENTES_TRABAJO_POR_CATEGORIA: dict[str, float] = {
    "construccion": 0.0650,
    "industria": 0.0400,
    "transporte_logistica": 0.0350,
    "servicios_industriales": 0.0300,
    "comercio_hosteleria": 0.0250,
    "inmobiliario": 0.0200,
    "administracion_educacion_sanidad": 0.0180,
    "servicios_profesionales": 0.0150,
    "servicios_tic": 0.0150,
}


def generar_perfil_cifra_negocios(rng: np.random.Generator, categoria: str) -> tuple[dict[str, float], dict[str, str]]:
    """Las 2 fracciones oficiales de cifra de negocios (ventas/servicios) para UN caso — sorteo
    único por empresa (no por año), mismo mecanismo que `generar_perfil_activo_no_corriente`.
    Devuelve también el modo típico/atípico de cada componente."""
    perfil_centro = PERFIL_CIFRA_NEGOCIOS_POR_CATEGORIA[categoria]
    brutos, modos = {}, {}
    for componente, centro in perfil_centro.items():
        valor, modo = _generar_partida(rng, centro, centro * DISPERSION_PERFIL_PYG_OFICIAL, suelo=SUELO_COMPONENTE_PYG_OFICIAL_PCT)
        brutos[componente] = valor
        modos[componente] = modo
    return _renormalizar_a_total(brutos, 1.0), modos


def generar_perfil_consumos_explotacion(rng: np.random.Generator, categoria: str) -> tuple[dict[str, float], dict[str, str]]:
    """Las 4 fracciones oficiales de consumos de explotación para UN caso — mismo mecanismo que
    `generar_perfil_cifra_negocios`."""
    perfil_centro = PERFIL_CONSUMOS_EXPLOTACION_POR_CATEGORIA[categoria]
    brutos, modos = {}, {}
    for componente, centro in perfil_centro.items():
        valor, modo = _generar_partida(rng, centro, centro * DISPERSION_PERFIL_PYG_OFICIAL, suelo=SUELO_COMPONENTE_PYG_OFICIAL_PCT)
        brutos[componente] = valor
        modos[componente] = modo
    return _renormalizar_a_total(brutos, 1.0), modos


def generar_perfil_otros_gastos_explot(rng: np.random.Generator, categoria: str) -> tuple[dict[str, float], dict[str, str]]:
    """Las 3 fracciones CON perfil propio de "Otros gastos de explotación" (servicios exteriores/
    tributos/otros gastos de gestión corriente) para UN caso — mismo mecanismo que
    `generar_perfil_cifra_negocios`. "Pérdidas por operaciones comerciales" (enlazada a
    `motor.insolvencias`) y "Gases de efecto invernadero" (siempre 0) NO forman parte de este
    perfil — ver `calcular_desglose_otros_gastos_explot`."""
    perfil_centro = PERFIL_OTROS_GASTOS_EXPLOT_POR_CATEGORIA[categoria]
    brutos, modos = {}, {}
    for componente, centro in perfil_centro.items():
        valor, modo = _generar_partida(rng, centro, centro * DISPERSION_PERFIL_PYG_OFICIAL, suelo=SUELO_COMPONENTE_PYG_OFICIAL_PCT)
        brutos[componente] = valor
        modos[componente] = modo
    return _renormalizar_a_total(brutos, 1.0), modos


def calcular_desglose_otros_gastos_explot(
    perfil_abd: dict[str, float], otros_gastos_explot_eur: float, perdidas_deterioro_comercial_eur: float
) -> dict[str, float]:
    """Las 5 sub-partidas oficiales de "Otros gastos de explotación" de ESTE año. `perfil_abd`
    (servicios exteriores/tributos/otros gastos de gestión corriente, suma 1.0) se aplica sobre
    el RESTO del agregado tras restar `perdidas_deterioro_comercial_eur` (la dotación de
    insolvencia de ESTE año, `motor.insolvencias.PasoInsolvencia.dotacion_eur` — nunca un sorteo
    nuevo), nunca sobre el agregado completo, para que las 5 sub-partidas sumen EXACTO al
    agregado. Tope defensivo: si la dotación de insolvencia superara el propio agregado (no
    observado en el barrido, pero posible en un sector con `otros_gastos_explot` marginal), se
    trunca a él en vez de dejar a)/b)/d) en negativo — `otros_gastos_explot_eur` en sí nunca es
    negativo (suelo de `PRIMITIVAS_PYG_NO_NEGATIVAS`)."""
    perdidas_eur = max(0.0, min(perdidas_deterioro_comercial_eur, otros_gastos_explot_eur))
    resto_eur = otros_gastos_explot_eur - perdidas_eur
    desglose = {componente: fraccion * resto_eur for componente, fraccion in perfil_abd.items()}
    desglose["perdidas_deterioro_operaciones_comerciales"] = perdidas_eur
    desglose["gases_efecto_invernadero"] = 0.0
    return desglose


def tasa_cargas_sociales_pct(año: int, categoria: str) -> float:
    """Tipo de cotización empresarial total (contingencias comunes + desempleo + FOGASA + FP +
    MEI + accidentes de trabajo) — ver docstring de las constantes arriba para el anclaje
    externo (BOE) y la hipótesis de diseño (prima de accidentes por categoría)."""
    return TASA_CARGAS_SOCIALES_BASE_PP + MEI_EMPRESARIAL_PP_POR_AÑO[año] + PRIMA_ACCIDENTES_TRABAJO_POR_CATEGORIA[categoria]


def calcular_desglose_gastos_personal(
    año: int, categoria: str, gastos_personal_eur: float, provision_dotacion_gastos_personal_eur: float
) -> dict[str, float]:
    """Las 3 sub-partidas oficiales de "Gastos de personal" de ESTE año: c) "Provisiones" es la
    dotación YA sorteada de `motor.provisiones` cuando su naturaleza es "gastos_personal" (nunca
    un sorteo nuevo, 0.0 en el año base y en cualquier año sin esa provisión activa). a)/b) se
    derivan del RESTO (`gastos_personal_eur - provisiones`) mediante `tasa_cargas_sociales_pct`:
    b = resto x tasa/(1+tasa), a = resto - b — puramente derivado (sin ruido propio, a diferencia
    de los perfiles a/b/d de consumos_explotacion/otros_gastos_explot: b) es un tipo legal, no una
    hipótesis de diseño). Mismo tope defensivo que `calcular_desglose_otros_gastos_explot`."""
    provisiones_eur = max(0.0, min(provision_dotacion_gastos_personal_eur, gastos_personal_eur))
    resto_eur = gastos_personal_eur - provisiones_eur
    tasa = tasa_cargas_sociales_pct(año, categoria)
    cargas_sociales_eur = resto_eur * tasa / (1 + tasa)
    sueldos_salarios_eur = resto_eur - cargas_sociales_eur
    return {
        "sueldos_salarios": sueldos_salarios_eur,
        "cargas_sociales": cargas_sociales_eur,
        "provisiones": provisiones_eur,
    }


def calcular_desglose_ingresos_financieros(
    ingresos_financieros_eur: float, inversion_grupo_largo_eur: float, tipo_interes: float
) -> dict[str, float]:
    """Las 2 sub-partidas oficiales de "Ingresos financieros" de ESTE año: a) "De empresas del
    grupo y asociadas" se deriva de `inversion_grupo_largo_eur` (arquetipo 20, operación
    "préstamo a matriz") x el tipo de interés YA calculado del caso — sin sorteo nuevo, 0.0 si el
    arquetipo 20 no ha activado esa operación concreta (`inversion_grupo_largo_eur=0.0`). Topado
    al agregado ya sorteado (`min`, nunca negativo): el agregado de `ingresos_financieros` y el
    préstamo intragrupo son magnitudes independientes por diseño (ninguna informa a la otra en
    ningún otro punto del motor) — en el caso raro en que la fórmula supere el agregado, se trata
    como si TODO el ingreso financiero del año viniera del grupo, en vez de dejar b) "De terceros"
    en negativo."""
    bruto_grupo_eur = max(0.0, inversion_grupo_largo_eur) * tipo_interes
    empresas_grupo_eur = max(0.0, min(bruto_grupo_eur, ingresos_financieros_eur))
    terceros_eur = ingresos_financieros_eur - empresas_grupo_eur
    return {"empresas_grupo": empresas_grupo_eur, "terceros": terceros_eur}


def _redondear_cifra_vistosa(valor: float) -> float:
    """Redondea a una cifra de aspecto realista para capital social (los importes reales suelen
    ser números redondos: 60.000€, 3.000.000€, no 2.847.193,17€) — redondeo a 2 cifras
    significativas."""
    if valor <= 0:
        return 0.0
    import math

    magnitud = 10 ** math.floor(math.log10(valor))
    paso = magnitud / 10
    return round(valor / paso) * paso


def _generar_capital_social(rng: np.random.Generator, patrimonio_neto_eur: float) -> tuple[float, str]:
    """Devuelve también el modo típico/atípico del sorteo (hallazgo de auditoría de trazabilidad,
    Ronda 1 de la Fase 4 — completa la corrección ya aplicada a existencias/deudores/acreedores/
    deudas financieras/`ROE_caso`: `_generar_capital_social`, `generar_perfil_activo_no_
    corriente` y `generar_periodificaciones_pct` son ANTERIORES a los lotes de desglose de
    balance (decisiones #24-25) pero comparten el mismo patrón "sorteo Huber/MAD descartando el
    modo" — corregido aquí en origen, mismo criterio que el resto)."""
    fraccion, modo = _generar_partida(
        rng,
        CAPITAL_SOCIAL_FRACCION_PN_CENTRO,
        CAPITAL_SOCIAL_FRACCION_PN_SPREAD,
        suelo=CAPITAL_SOCIAL_FRACCION_PN_SUELO,
        techo=CAPITAL_SOCIAL_FRACCION_PN_TECHO,
    )
    return _redondear_cifra_vistosa(max(0.0, patrimonio_neto_eur) * fraccion), modo


def generar_perfil_activo_no_corriente(rng: np.random.Generator, categoria: str) -> tuple[dict[str, float], dict[str, str]]:
    """Las 4 fracciones (material/intangible/inversiones_inmobiliarias/otros_financieros) para
    UN caso — sorteo único por empresa (no por año), con ruido alrededor del perfil central de
    su categoría de sector, renormalizado para sumar exactamente 1.0. Devuelve también el modo
    típico/atípico de cada componente — ver docstring de `_generar_capital_social` (mismo
    hallazgo de auditoría) y de `generar_perfil_deudores` (mismo patrón de corrección)."""
    perfil_centro = PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA[categoria]
    brutos = {}
    modos = {}
    for componente, centro in perfil_centro.items():
        valor, modo = _generar_partida(
            rng, centro, centro * DISPERSION_PERFIL_ACTIVO_NO_CORRIENTE,
            suelo=SUELO_COMPONENTE_ACTIVO_NO_CORRIENTE_PCT,
        )
        brutos[componente] = valor
        modos[componente] = modo
    return _renormalizar_a_total(brutos, 1.0), modos


def generar_perfil_existencias(rng: np.random.Generator, sector_codigo: str) -> tuple[dict[str, float], dict[str, str]]:
    """Las 6 fracciones oficiales de existencias (comerciales/materias_primas/productos_curso/
    productos_terminados/subproductos_residuos/anticipos_proveedores) para UN caso — mismo
    mecanismo que `generar_perfil_activo_no_corriente` (sorteo único por empresa, ruido mixto
    alrededor del perfil central de su TIER de existencias, renormalizado a 1.0). Clasifica por
    SECTOR, no por `categoria_de_sector` — ver `TIER_EXISTENCIAS_POR_SECTOR`. Devuelve también el
    modo típico/atípico de cada componente — ver docstring de `generar_perfil_deudores`."""
    perfil_centro = PERFIL_EXISTENCIAS_POR_TIER[tier_existencias_de_sector(sector_codigo)]
    brutos = {}
    modos = {}
    for componente, centro in perfil_centro.items():
        valor, modo = _generar_partida(
            rng, centro, centro * DISPERSION_PERFIL_EXISTENCIAS,
            suelo=SUELO_COMPONENTE_EXISTENCIAS_PCT,
        )
        brutos[componente] = valor
        modos[componente] = modo
    return _renormalizar_a_total(brutos, 1.0), modos


def generar_periodificaciones_pct(
    rng: np.random.Generator, categoria: str
) -> tuple[float, float, float, str, str, str]:
    """Fracciones de periodificación de activo (sobre `realizable`), pasivo a corto (sobre
    `otras_deudas_corto`) y pasivo a largo (sobre `otras_deudas_largo`) — 3 sorteos
    independientes (no son un reparto que deba sumar 1.0 entre sí: cada uno talla una porción de
    una masa DISTINTA), mismo ruido mixto de siempre, sin renormalizar. Devuelve también el modo
    típico/atípico de cada uno de los 3 — ver docstring de `_generar_capital_social` (mismo
    hallazgo de auditoría de trazabilidad)."""
    centro_activo = PERIODIFICACION_ACTIVO_PCT_POR_CATEGORIA[categoria]
    centro_pasivo = PERIODIFICACION_PASIVO_PCT_POR_CATEGORIA[categoria]
    activo_pct, modo_activo = _generar_partida(
        rng, centro_activo, centro_activo * DISPERSION_PERIODIFICACION,
        suelo=SUELO_PERIODIFICACION_PCT, techo=TECHO_PERIODIFICACION_PCT,
    )
    pasivo_corto_pct, modo_pasivo_corto = _generar_partida(
        rng, centro_pasivo, centro_pasivo * DISPERSION_PERIODIFICACION,
        suelo=SUELO_PERIODIFICACION_PCT, techo=TECHO_PERIODIFICACION_PCT,
    )
    pasivo_largo_pct, modo_pasivo_largo = _generar_partida(
        rng, centro_pasivo, centro_pasivo * DISPERSION_PERIODIFICACION,
        suelo=SUELO_PERIODIFICACION_PCT, techo=TECHO_PERIODIFICACION_PCT,
    )
    return activo_pct, pasivo_corto_pct, pasivo_largo_pct, modo_activo, modo_pasivo_corto, modo_pasivo_largo


class EmpresaBaseError(ValueError):
    """Parámetros de entrada inválidos o sector/segmento no encontrado en el catálogo."""


@dataclass(frozen=True)
class EmpresaBase:
    sector_codigo: str
    sector_nombre: str
    segmento: str
    ventas_objetivo: float
    semilla: int
    rotacion_activo: float
    activo_total_eur: float
    balance_pct: dict[str, float]
    balance_eur: dict[str, float]
    pyg_pct: dict[str, float]
    pyg_eur: dict[str, float]
    modos: dict[str, str] = field(repr=False)
    ajuste_cuadre_eur: float = 0.0
    capital_social_eur: float = 0.0
    reservas_eur: float = 0.0
    activo_no_corriente_perfil_pct: dict[str, float] = field(default_factory=dict)
    activo_no_corriente_desglose_eur: dict[str, float] = field(default_factory=dict)
    # Amortización derivada de una colección real de activos (ver motor/amortizacion.py) — la
    # colección en sí (para evolucionarla año a año) y los perfiles de sub-tipo ya sorteados
    # (para que el arquetipo 18 -adquisición- pueda reutilizarlos sin volver a sortear "el
    # perfil completo de la categoría").
    coleccion_activos_amortizables: tuple = ()
    perfil_subtipos_material_pct: dict[str, float] = field(default_factory=dict)
    perfil_subtipos_intangible_pct: dict[str, float] = field(default_factory=dict)
    # Tipo de interés del ejercicio (ya sorteado dentro de _generar_pyg_hasta_baii, antes solo
    # local a esa función) — expuesto para el Δr de la cobertura de tipos de interés (arquetipo
    # 21, motor/coberturas_subvenciones.py): no es un sorteo nuevo, solo se deja de descartar.
    tipo_interes: float = 0.0
    # Tipo efectivo del Impuesto sobre Sociedades del ejercicio (ya sorteado dentro de
    # _generar_pyg_hasta_baii, mismo patrón que tipo_interes) — expuesto para la continuidad por
    # memoria del ejercicio siguiente (ver bloque "Impuesto sobre Sociedades").
    tipo_impuesto_efectivo: float = 0.0
    # Primer lote de desglose de balance (existencias + periodificaciones) — mismo patrón que
    # activo_no_corriente: perfil (%) fijo desde 2023, desglose (€) recalculado cada año sobre
    # la masa agregada YA cuadrada de ese año. Las periodificaciones son fracciones ESCALARES
    # (no un perfil de varios componentes que sume 1.0 — cada una talla una porción de una masa
    # distinta), ver generar_periodificaciones_pct.
    existencias_perfil_pct: dict[str, float] = field(default_factory=dict)
    existencias_desglose_eur: dict[str, float] = field(default_factory=dict)
    periodificacion_activo_pct: float = 0.0
    periodificacion_pasivo_corto_pct: float = 0.0
    periodificacion_pasivo_largo_pct: float = 0.0
    periodificacion_activo_eur: float = 0.0
    periodificacion_pasivo_corto_eur: float = 0.0
    periodificacion_pasivo_largo_eur: float = 0.0
    # Segundo lote de desglose de balance (deudores/acreedores comerciales) — mismo patrón:
    # perfil (%) BASE fijo desde 2023 (arquetipo-agnóstico; `motor.evolucion_arquetipo` lo
    # sobrescribe en el año base si el arquetipo 20 activa una operación comercial concreta,
    # ver `ParametrosOperacionVinculada`), desglose (€) recalculado cada año sobre la masa
    # agregada ya cuadrada de ese año.
    deudores_perfil_pct: dict[str, float] = field(default_factory=dict)
    deudores_desglose_eur: dict[str, float] = field(default_factory=dict)
    acreedores_perfil_pct: dict[str, float] = field(default_factory=dict)
    acreedores_desglose_eur: dict[str, float] = field(default_factory=dict)
    # Cuarto y último lote de desglose de balance (deudas financieras largo/corto plazo) — perfil
    # FIJO desde 2023 (`fraccion_total`/`fraccion_largo`, arquetipo-agnóstico: ni la reclasifica-
    # ción de deuda ni el derivado del arquetipo 21 tocan este perfil, solo el desglose en € de
    # cada año — ver motor.evolucion_arquetipo y calcular_desglose_deudas_fin). "Derivados" en
    # 0.0 en el año base: la cobertura nunca tiene valor razonable en 2023 (año de origen de
    # medición, ver motor.coberturas_subvenciones).
    deudas_fin_fraccion_total: dict[str, float] = field(default_factory=dict)
    deudas_fin_fraccion_largo: dict[str, float] = field(default_factory=dict)
    deudas_fin_largo_desglose_eur: dict[str, float] = field(default_factory=dict)
    deudas_fin_corto_desglose_eur: dict[str, float] = field(default_factory=dict)
    # Desglose de PyG en líneas oficiales del PGC (encargo 1/2 de este lote) — perfiles (%) fijos
    # desde 2023 para cifra_negocios/consumos_explotacion/otros_gastos_explot (arquetipo-
    # agnósticos), desglose (€) recalculado cada año sobre el agregado ya generado de ese año.
    # gastos_personal/ingresos_financieros NO llevan perfil propio (fórmula derivada, sin ruido:
    # ver calcular_desglose_gastos_personal/calcular_desglose_ingresos_financieros).
    pyg_cifra_negocios_perfil_pct: dict[str, float] = field(default_factory=dict)
    pyg_cifra_negocios_desglose_eur: dict[str, float] = field(default_factory=dict)
    pyg_consumos_explotacion_perfil_pct: dict[str, float] = field(default_factory=dict)
    pyg_consumos_explotacion_desglose_eur: dict[str, float] = field(default_factory=dict)
    pyg_otros_gastos_explot_perfil_pct: dict[str, float] = field(default_factory=dict)
    pyg_otros_gastos_explot_desglose_eur: dict[str, float] = field(default_factory=dict)
    pyg_gastos_personal_desglose_eur: dict[str, float] = field(default_factory=dict)
    pyg_ingresos_financieros_desglose_eur: dict[str, float] = field(default_factory=dict)
    # Quinto lote de desglose de balance ("Otras deudas" largo/corto plazo) — perfil (%) fijo
    # desde 2023 (`otras_deudas_largo_perfil_pct`/`..._corto_resto_perfil_pct`, arquetipo-
    # agnóstico salvo `deudas_socios_activa`, decidida una única vez sin ancla a ningún
    # arquetipo), desglose (€) recalculado cada año sobre el residuo YA cuadrado de ese año (tras
    # excluir provisiones/deudas del grupo/pasivos por impuesto diferido — ver motor/empresa_
    # base.py). `aapp_pendiente_corto_pct` es la ÚNICA pieza de este lote que NO es fija desde
    # 2023: se RE-INVOCA cada año porque su boost depende del arquetipo 4/7 (inexistente en el
    # año base) — pero el resultado es DETERMINISTA para semilla/sector/segmento/boost dados, no
    # un sorteo año a año independiente (nunca "parpadea" entre 2024 y 2025 con el mismo
    # arquetipo activo, verificado — ver docstring completo en `sortear_aapp_pendiente_corto_pct`).
    deudas_socios_activa: bool = False
    otras_deudas_largo_perfil_pct: dict[str, float] = field(default_factory=dict)
    otras_deudas_corto_resto_perfil_pct: dict[str, float] = field(default_factory=dict)
    otras_deudas_largo_desglose_eur: dict[str, float] = field(default_factory=dict)
    otras_deudas_corto_desglose_eur: dict[str, float] = field(default_factory=dict)
    aapp_pendiente_corto_pct: float = 0.0


def _mapa_codigo_sector(catalogo: pd.DataFrame) -> dict[str, str]:
    mapa: dict[str, str] = {}
    for nombre in catalogo["sector"].unique():
        match = _RE_CODIGO_SECTOR.search(nombre)
        if match:
            mapa[match.group(1)] = nombre
    return mapa


def resolver_fila_sector(catalogo: pd.DataFrame, sector_codigo: str, segmento: str) -> pd.Series:
    """Resuelve la fila del catálogo (huber_9y, huber_scale_mad, ...) para un sector/segmento.

    `sector_codigo` es el código entre paréntesis del catálogo (p. ej. "24.1", "4941").
    """
    if segmento not in SEGMENTOS_VALIDOS:
        raise EmpresaBaseError(f"Segmento '{segmento}' no válido. Debe ser uno de: {sorted(SEGMENTOS_VALIDOS)}")

    mapa_codigos = _mapa_codigo_sector(catalogo)
    if sector_codigo not in mapa_codigos:
        raise EmpresaBaseError(
            f"Sector '{sector_codigo}' no reconocido. Códigos disponibles: {sorted(mapa_codigos)}"
        )
    sector_nombre = mapa_codigos[sector_codigo]

    filas = catalogo[(catalogo["sector"] == sector_nombre) & (catalogo["segmento"] == segmento)]
    if len(filas) != 1:
        raise EmpresaBaseError(
            f"Se esperaba exactamente 1 fila para ({sector_nombre!r}, {segmento!r}) y hay {len(filas)}."
        )
    return filas.iloc[0]


def _generar_balance_pct(
    rng: np.random.Generator, fila: pd.Series
) -> tuple[dict[str, float], dict[str, str]]:
    brutos: dict[str, float] = {}
    modos: dict[str, str] = {}
    for nombre_salida, variable in MASAS_BALANCE.items():
        huber = fila[f"balance.{variable}.huber_9y"]
        mad = fila[f"balance.{variable}.huber_scale_mad"]
        valor, modo = _generar_partida(rng, huber, mad, suelo=SUELO_PORCENTAJE)
        brutos[nombre_salida] = valor
        modos[f"balance.{nombre_salida}"] = modo

    nivel1_activo = _renormalizar_a_total(
        {k: brutos[k] for k in ("activo_no_corriente", "activo_corriente")}, 100.0
    )
    nivel1_pasivo = _renormalizar_a_total(
        {k: brutos[k] for k in ("patrimonio_neto", "pasivo_no_corriente", "pasivo_corriente")}, 100.0
    )
    nivel2_activo_corriente = _renormalizar_a_total(
        {k: brutos[k] for k in ("existencias", "realizable", "disponible")},
        nivel1_activo["activo_corriente"],
    )
    nivel2_pasivo_no_corriente = _renormalizar_a_total(
        {k: brutos[k] for k in ("deudas_fin_largo", "otras_deudas_largo")},
        nivel1_pasivo["pasivo_no_corriente"],
    )
    nivel2_pasivo_corriente = _renormalizar_a_total(
        {k: brutos[k] for k in ("acreedores_comerciales", "deudas_fin_corto", "otras_deudas_corto")},
        nivel1_pasivo["pasivo_corriente"],
    )

    balance_pct = {
        **nivel1_activo,
        **nivel1_pasivo,
        **nivel2_activo_corriente,
        **nivel2_pasivo_no_corriente,
        **nivel2_pasivo_corriente,
    }
    return balance_pct, modos


# Continuidad del sorteo anual de PyG (ver decisiones_plausibilidad.md #75/#77/#78 y docstring
# de `_generar_partida_con_memoria` en motor/ruido.py) — SOLO se aplica en 2024/2025 a las
# primitivas que ningún arquetipo esté forzando ese año; el año base (2023) sigue siendo un
# sorteo limpio contra el Huber del sector, sin cambios. Calibradas empíricamente con el mismo
# método de siempre (barrido 27 sectores x 4 semillas, arquetipo "limpio" que no toca PyG).
PESO_MEMORIA_PYG_ANUAL = 0.6
FACTOR_REDUCCION_RUIDO_PYG_ANUAL = 0.3


@dataclass(frozen=True)
class _PygParcial:
    """Cascada de PyG calculada hasta BAII (no depende de la deuda financiera)."""

    ingresos_explotacion_eur: float
    cifra_negocios_eur: float
    otros_ingresos_explot_eur: float
    consumos_explotacion_eur: float
    margen_bruto_eur: float
    otros_gastos_explot_eur: float
    valor_añadido_eur: float
    gastos_personal_eur: float
    amortizaciones_eur: float
    deterioro_enajenacion_inmovilizado_eur: float
    resultado_extraordinario_eur: float
    baii_eur: float
    ingresos_financieros_eur: float
    tipo_interes: float
    tipo_impuesto_efectivo: float  # ver bloque "Impuesto sobre Sociedades" — el IMPORTE (impuesto_beneficios_eur) se calcula en _completar_pyg_con_deuda, sobre el BAI ya resuelto, no aquí
    modos: dict[str, str]


def _generar_pyg_hasta_baii(
    rng: np.random.Generator,
    fila: pd.Series,
    ventas_objetivo: float,
    año: int,
    primitivas_forzadas: dict[str, float] | None = None,
    amortizaciones_eur: float | None = None,
    deterioro_enajenacion_inmovilizado_eur: float = 0.0,
    anterior_pyg_pct: dict[str, float] | None = None,
    anterior_tipo_interes: float | None = None,
    anterior_tipo_impuesto_efectivo: float | None = None,
) -> _PygParcial:
    """Sortea las primitivas de la PyG que no dependen de deuda, y el tipo de interés del
    ejercicio (mismo mecanismo típico/atípico que el resto de partidas, pero YA NO anclado a
    `ratios.coste_deuda` del catálogo — fuente de mercado propia, ver el bloque de constantes
    `REFERENCIA_EURIBOR_12M_POR_AÑO`/`PRIMA_RIESGO_POR_CATEGORIA` más arriba y decisiones
    #41-43 en docs/decisiones_plausibilidad.md). `año` determina el nivel de Euríbor 12M;
    `segmento`/categoría de sector (ambos derivables de `fila`, no hace falta pasarlos aparte)
    determinan la prima. No calcula gastos financieros ni nada de BAI en adelante:
    eso depende de la deuda financiera media del ejercicio, que en `evolucion_arquetipo` no se
    conoce hasta después de decidir si hay contención de endeudamiento.

    `primitivas_forzadas`: para un arquetipo con efecto "pyg_primitiva" (p. ej. mejora de
    margen sobre consumos_explotacion_pct), el valor ya calculado con continuidad respecto al
    año anterior — sustituye el sorteo de esa partida en concreto. Se registra con modo
    "arquetipo" en vez de "tipico"/"atipico" (no es ruido, es el efecto del arquetipo).

    `amortizaciones_eur`: OBLIGATORIO en la práctica desde que la amortización dejó de sortearse
    como % independiente (ver `motor/amortizacion.py`) — el gasto ya calculado a partir de la
    colección real de activos del caso, en EUROS (no en %, a diferencia de `primitivas_forzadas`:
    la conversión a % requeriría conocer `ingresos_explotacion_eur`, que todavía no está
    calculado en este punto — ver más abajo). "amortizaciones" se excluye del sorteo/bucle de
    primitivas en ese caso (no consume ningún draw de `rng`) y su modo queda registrado como
    "derivado".

    `deterioro_enajenacion_inmovilizado_eur`: línea oficial 11 del modelo PGC de PyG
    ("Deterioro y resultado por enajenaciones del inmovilizado") — SIEMPRE derivada de las bajas
    anticipadas de sub-lotes de `motor/amortizacion.py` (nunca sorteada desde el catálogo: no
    existe columna ACCID para esta línea), 0.0 en el año base (2023, sin bajas) y en cualquier
    llamada que no la pase explícita. No consume ningún draw de `rng`, mismo criterio que
    `amortizaciones_eur`; su modo queda registrado como "derivado".

    `anterior_pyg_pct`/`anterior_tipo_interes`: SOLO se pasan al generar 2024/2025 (el año base
    no tiene "año anterior" al que agarrarse — sigue siendo un sorteo limpio contra el Huber del
    sector, ver `generar_empresa_base`, que no los pasa). Cuando están presentes, cualquier
    primitiva NO forzada por un arquetipo usa `_generar_partida_con_memoria` en vez de
    `_generar_partida` — continuidad con el valor REAL del año anterior y varianza reducida, en
    vez de un sorteo limpio nuevo cada año (ver decisiones_plausibilidad.md #75/#77/#78 y
    docstring de `_generar_partida_con_memoria` en motor/ruido.py). No afecta en absoluto a las
    primitivas SÍ forzadas por un arquetipo (siguen su propio mecanismo, `_mover_ratio_continuo`,
    completamente aparte de este).

    `anterior_tipo_impuesto_efectivo`: mismo patrón que `anterior_tipo_interes` — continuidad del
    TIPO efectivo del Impuesto sobre Sociedades (no del importe, que depende del BAI de cada año,
    calculado más tarde en `_completar_pyg_con_deuda`). `None` en el año base (sorteo limpio
    contra el tipo nominal del año/segmento, ver `TIPO_NOMINAL_IS_POR_AÑO_SEGMENTO`).
    """
    primitivas_forzadas = primitivas_forzadas or {}
    brutos: dict[str, float] = {}
    modos: dict[str, str] = {}
    for nombre_salida, variable in PRIMITIVAS_PYG.items():
        if nombre_salida == "amortizaciones" and amortizaciones_eur is not None:
            modos[f"pyg.{nombre_salida}"] = "derivado"
            continue
        if nombre_salida in primitivas_forzadas:
            brutos[nombre_salida] = primitivas_forzadas[nombre_salida]
            modos[f"pyg.{nombre_salida}"] = "arquetipo"
            continue
        huber = fila[f"pyg.{variable}.huber_9y"]
        mad = fila[f"pyg.{variable}.huber_scale_mad"]
        suelo = SUELO_PORCENTAJE if nombre_salida in PRIMITIVAS_PYG_NO_NEGATIVAS else None
        if anterior_pyg_pct is not None:
            valor, modo = _generar_partida_con_memoria(
                rng, anterior_pyg_pct[nombre_salida], huber, mad,
                PESO_MEMORIA_PYG_ANUAL, FACTOR_REDUCCION_RUIDO_PYG_ANUAL, suelo=suelo,
            )
        else:
            valor, modo = _generar_partida(rng, huber, mad, suelo=suelo)
        brutos[nombre_salida] = valor
        modos[f"pyg.{nombre_salida}"] = modo

    codigo_sector = _RE_CODIGO_SECTOR.search(fila["sector"]).group(1)
    categoria = categoria_de_sector(codigo_sector)
    recargo_segmento = RECARGO_TIPO_INTERES_PEQUEÑAS_PP if fila["segmento"] == "pequeñas" else 0.0
    centro_tipo_interes = REFERENCIA_EURIBOR_12M_POR_AÑO[año] + PRIMA_RIESGO_POR_CATEGORIA[categoria] + recargo_segmento
    if anterior_tipo_interes is not None:
        tipo_interes, modo_tipo_interes = _generar_partida_con_memoria(
            rng, anterior_tipo_interes, centro_tipo_interes, DISPERSION_TIPO_INTERES_PP,
            PESO_MEMORIA_PYG_ANUAL, FACTOR_REDUCCION_RUIDO_PYG_ANUAL,
            suelo=SUELO_TIPO_INTERES, techo=TECHO_TIPO_INTERES,
        )
    else:
        tipo_interes, modo_tipo_interes = _generar_partida(
            rng,
            centro_tipo_interes,
            DISPERSION_TIPO_INTERES_PP,
            suelo=SUELO_TIPO_INTERES,
            techo=TECHO_TIPO_INTERES,
        )
    modos["pyg.tipo_interes"] = modo_tipo_interes

    # Impuesto sobre Sociedades — se sortea el TIPO efectivo (no el importe, que depende del BAI
    # de este año, todavía no calculado aquí: la deuda financiera media, necesaria para
    # `gastos_financieros`, no se conoce hasta `_completar_pyg_con_deuda`). Mismo mecanismo de
    # ruido mixto típico/atípico y de continuidad por memoria que `tipo_interes` — ver bloque de
    # constantes "Impuesto sobre Sociedades" más arriba.
    segmento = fila["segmento"]
    centro_tipo_impuesto = TIPO_NOMINAL_IS_POR_AÑO_SEGMENTO[año][segmento]
    if anterior_tipo_impuesto_efectivo is not None:
        tipo_impuesto_efectivo, modo_tipo_impuesto = _generar_partida_con_memoria(
            rng, anterior_tipo_impuesto_efectivo, centro_tipo_impuesto, DISPERSION_TIPO_IMPUESTO_IS_PP,
            PESO_MEMORIA_PYG_ANUAL, FACTOR_REDUCCION_RUIDO_PYG_ANUAL,
            suelo=SUELO_TIPO_IMPUESTO_IS, techo=TECHO_TIPO_IMPUESTO_IS,
        )
    else:
        tipo_impuesto_efectivo, modo_tipo_impuesto = _generar_partida(
            rng,
            centro_tipo_impuesto,
            DISPERSION_TIPO_IMPUESTO_IS_PP,
            suelo=SUELO_TIPO_IMPUESTO_IS,
            techo=TECHO_TIPO_IMPUESTO_IS,
        )
    modos["pyg.tipo_impuesto_efectivo"] = modo_tipo_impuesto

    cifra_negocios_eur = ventas_objetivo
    otros_ingresos_explot_eur = cifra_negocios_eur * (
        brutos["otros_ingresos_explot"] / brutos["cifra_negocios"]
    )
    ingresos_explotacion_eur = cifra_negocios_eur + otros_ingresos_explot_eur

    consumos_explotacion_eur = brutos["consumos_explotacion"] / 100 * ingresos_explotacion_eur
    otros_gastos_explot_eur = brutos["otros_gastos_explot"] / 100 * ingresos_explotacion_eur
    gastos_personal_eur = brutos["gastos_personal"] / 100 * ingresos_explotacion_eur
    amortizaciones_eur_final = (
        amortizaciones_eur if amortizaciones_eur is not None else brutos["amortizaciones"] / 100 * ingresos_explotacion_eur
    )
    resultado_extraordinario_eur = brutos["resultado_extraordinario"] / 100 * ingresos_explotacion_eur
    ingresos_financieros_eur = brutos["ingresos_financieros"] / 100 * ingresos_explotacion_eur

    margen_bruto_eur = ingresos_explotacion_eur - consumos_explotacion_eur
    valor_añadido_eur = margen_bruto_eur - otros_gastos_explot_eur
    baii_eur = (
        valor_añadido_eur
        - gastos_personal_eur
        - amortizaciones_eur_final
        + deterioro_enajenacion_inmovilizado_eur
        + resultado_extraordinario_eur
    )
    modos["pyg.deterioro_enajenacion_inmovilizado"] = "derivado"

    return _PygParcial(
        ingresos_explotacion_eur=ingresos_explotacion_eur,
        cifra_negocios_eur=cifra_negocios_eur,
        otros_ingresos_explot_eur=otros_ingresos_explot_eur,
        consumos_explotacion_eur=consumos_explotacion_eur,
        margen_bruto_eur=margen_bruto_eur,
        otros_gastos_explot_eur=otros_gastos_explot_eur,
        valor_añadido_eur=valor_añadido_eur,
        gastos_personal_eur=gastos_personal_eur,
        amortizaciones_eur=amortizaciones_eur_final,
        deterioro_enajenacion_inmovilizado_eur=deterioro_enajenacion_inmovilizado_eur,
        resultado_extraordinario_eur=resultado_extraordinario_eur,
        baii_eur=baii_eur,
        ingresos_financieros_eur=ingresos_financieros_eur,
        tipo_interes=tipo_interes,
        tipo_impuesto_efectivo=tipo_impuesto_efectivo,
        modos=modos,
    )


def _completar_pyg_con_deuda(
    parcial: _PygParcial, deuda_financiera_media_eur: float
) -> tuple[dict[str, float], dict[str, float]]:
    """Termina la cascada (BAI, impuesto sobre beneficios y resultado del ejercicio) usando la
    deuda financiera media (largo + corto plazo, promedio inicio/fin del ejercicio) para calcular
    gastos financieros = deuda financiera media x tipo de interés del sector.

    Impuesto sobre Sociedades — YA NO % de ingresos (ver bloque de constantes "Impuesto sobre
    Sociedades" en `motor/empresa_base.py` y CLAUDE.md, sección homónima): tipo EFECTIVO (ya
    sorteado en `_generar_pyg_hasta_baii`, con continuidad año a año) aplicado sobre el BAI de
    ESTE año, que aquí SÍ está ya resuelto (a diferencia del punto en que se sorteó el tipo).
    Años con BAI<=0: impuesto = 0.0 (ni negativo ni positivo) — simplificación deliberada, no se
    modela compensación de bases imponibles negativas ni un activo por pérdidas a compensar (eso
    ya tiene su propio mecanismo separado y fuera de alcance aquí: activos por impuesto diferido
    de coberturas/subvenciones, `motor/coberturas_subvenciones.py`)."""
    gastos_financieros_eur = deuda_financiera_media_eur * parcial.tipo_interes
    bai_eur = parcial.baii_eur + parcial.ingresos_financieros_eur - gastos_financieros_eur
    impuesto_beneficios_eur = max(0.0, bai_eur) * parcial.tipo_impuesto_efectivo
    resultado_ejercicio_eur = bai_eur - impuesto_beneficios_eur

    pyg_eur = {
        "cifra_negocios": parcial.cifra_negocios_eur,
        "otros_ingresos_explot": parcial.otros_ingresos_explot_eur,
        "ingresos_explotacion": parcial.ingresos_explotacion_eur,
        "consumos_explotacion": parcial.consumos_explotacion_eur,
        "margen_bruto": parcial.margen_bruto_eur,
        "otros_gastos_explot": parcial.otros_gastos_explot_eur,
        "valor_añadido": parcial.valor_añadido_eur,
        "gastos_personal": parcial.gastos_personal_eur,
        "amortizaciones": parcial.amortizaciones_eur,
        "deterioro_enajenacion_inmovilizado": parcial.deterioro_enajenacion_inmovilizado_eur,
        "resultado_extraordinario": parcial.resultado_extraordinario_eur,
        "baii": parcial.baii_eur,
        "ingresos_financieros": parcial.ingresos_financieros_eur,
        "gastos_financieros": gastos_financieros_eur,
        "bai": bai_eur,
        "impuesto_beneficios": impuesto_beneficios_eur,
        "resultado_ejercicio": resultado_ejercicio_eur,
    }
    pyg_pct = {k: v / parcial.ingresos_explotacion_eur * 100 for k, v in pyg_eur.items()}
    return pyg_pct, pyg_eur


def generar_empresa_base(
    sector: str,
    segmento: str,
    ventas_objetivo: float,
    semilla: int,
    catalogo: pd.DataFrame | None = None,
    modo_generacion: str | None = None,
) -> EmpresaBase:
    """Genera el balance y la PyG base (un ejercicio, sin arquetipos) de una empresa ficticia.

    `sector` es el código entre paréntesis del catálogo (p. ej. "24.1", "4941"). `segmento` es
    "grandes_medianas" o "pequeñas". El resultado es reproducible: misma semilla+sector+segmento,
    mismo caso (ver docstring del módulo sobre por qué la semilla del RNG mezcla sector+segmento,
    no solo `semilla`).

    `modo_generacion` ("tipico"/"atipico"/"aleatorio" — sección 2.16/2.17, Fase 4 Ronda 2 punto
    2): fuerza la rama típica/atípica de TODOS los sorteos de esta función (masas de balance,
    PyG, los 4 lotes de desglose, `rotacion_activo`...) sin tocar ningún helper interno — ver
    docstring de `motor.ruido` para el diseño completo (`contextvars`, un único punto de
    control). Por defecto `None` (NO "aleatorio") a propósito: si esta función se llama anidada
    dentro de `generar_evolucion_combinada` (que ya activó su propio modo para todo el caso),
    `None` significa "hereda el modo ya activo, no lo sobrescribas" — con un valor concreto por
    defecto, el año base habría vuelto siempre a "aleatorio" pese al modo pedido para el resto
    del caso (bug real detectado y corregido antes de comitear). Llamada en solitario (sin
    ningún modo ya activo), `None` se comporta como "aleatorio" (el ambiente por defecto)."""
    if segmento not in SEGMENTOS_VALIDOS:
        raise EmpresaBaseError(f"Segmento '{segmento}' no válido. Debe ser uno de: {sorted(SEGMENTOS_VALIDOS)}")
    if ventas_objetivo <= 0:
        raise EmpresaBaseError(f"ventas_objetivo debe ser positivo, recibido: {ventas_objetivo}")

    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    if modo_generacion is None:
        return _generar_empresa_base_interno(sector, segmento, ventas_objetivo, semilla, catalogo)
    _token_modo_generacion = activar_modo_generacion(modo_generacion)
    try:
        return _generar_empresa_base_interno(sector, segmento, ventas_objetivo, semilla, catalogo)
    finally:
        desactivar_modo_generacion(_token_modo_generacion)


def _generar_empresa_base_interno(
    sector: str, segmento: str, ventas_objetivo: float, semilla: int, catalogo: pd.DataFrame
) -> EmpresaBase:
    """Cuerpo real de `generar_empresa_base`, aislado en su propia función para que el `try/
    finally` de activación de `modo_generacion` no tenga que reindentar el resto del cuerpo
    (~130 líneas) — mismo resultado, diff mínimo. No debe llamarse directamente (usa `generar_
    empresa_base`, que ya ha validado los parámetros y activado el modo)."""

    fila = resolver_fila_sector(catalogo, sector, segmento)
    sector_nombre = fila["sector"]

    entropia_caso = zlib.crc32(f"{sector}|{segmento}".encode("utf-8"))
    rng = np.random.default_rng([semilla, entropia_caso])

    balance_pct, modos_balance = _generar_balance_pct(rng, fila)

    rotacion_activo, modo_rotacion = _generar_partida(
        rng,
        fila["ratios.rotacion_activo.huber_9y"],
        fila["ratios.rotacion_activo.huber_scale_mad"],
        suelo=SUELO_ROTACION_ACTIVO,
    )
    activo_total_eur = ventas_objetivo / rotacion_activo

    balance_eur = {clave: valor / 100 * activo_total_eur for clave, valor in balance_pct.items()}

    activo_eur = balance_eur["activo_no_corriente"] + balance_eur["activo_corriente"]
    pn_pasivo_eur = (
        balance_eur["patrimonio_neto"] + balance_eur["pasivo_no_corriente"] + balance_eur["pasivo_corriente"]
    )
    diferencia_cuadre = activo_eur - pn_pasivo_eur
    ajuste_cuadre_eur = 0.0
    if abs(diferencia_cuadre) > TOLERANCIA_CUADRE_EUR:
        balance_eur["otras_deudas_corto"] += diferencia_cuadre
        balance_pct["otras_deudas_corto"] = balance_eur["otras_deudas_corto"] / activo_total_eur * 100
        ajuste_cuadre_eur = diferencia_cuadre

    # Gastos financieros = deuda financiera media del ejercicio x tipo de interés del sector.
    # Este módulo no modela una serie temporal (no hay "ejercicio anterior"): se asume que la
    # deuda financiera se mantuvo estable durante el año, es decir inicio = fin = la del propio
    # balance ya generado. En `evolucion_arquetipo` sí hay inicio/fin distintos (ver ese módulo).
    deuda_financiera_eur = balance_eur["deudas_fin_largo"] + balance_eur["deudas_fin_corto"]

    # Perfil de activo_no_corriente y colección de activos amortizables — RNG PROPIO E
    # INDEPENDIENTE del `rng` compartido de balance/PyG (no desplaza ningún sorteo ya existente
    # de balance_pct/rotacion_activo/cifra_negocios/consumos_explotacion/gastos_personal). Tiene
    # que calcularse ANTES de la PyG porque el gasto de amortización ahora se DERIVA de esta
    # colección en vez de sortearse — ver motor/amortizacion.py (arreglo de raíz, no un parche:
    # antes `amortizaciones_pct` se sorteaba sin ninguna conexión con el inmovilizado real).
    categoria = categoria_de_sector(sector)
    rng_perfil = np.random.default_rng([semilla, zlib.crc32(f"{sector}|{segmento}|perfil_activo_no_corriente".encode("utf-8"))])
    perfil_activo_no_corriente, modos_activo_no_corriente = generar_perfil_activo_no_corriente(rng_perfil, categoria)
    activo_no_corriente_desglose_eur = {
        componente: fraccion * balance_eur["activo_no_corriente"]
        for componente, fraccion in perfil_activo_no_corriente.items()
    }
    coleccion_activos_amortizables, perfil_subtipos_material, perfil_subtipos_intangible = generar_coleccion_y_perfiles_base(
        sector, segmento, semilla, categoria, activo_no_corriente_desglose_eur
    )
    amortizacion_eur_2023 = amortizacion_eur_del_año(coleccion_activos_amortizables, _AÑO_BASE_AMORTIZACION)

    # Primer lote de desglose de balance (existencias + periodificaciones) — RNG PROPIO E
    # INDEPENDIENTE, mismo criterio que el resto de perfiles de este bloque: no desplaza ningún
    # sorteo ya existente.
    rng_desglose_balance = np.random.default_rng(
        [semilla, zlib.crc32(f"{sector}|{segmento}|desglose_balance_lote1".encode("utf-8"))]
    )
    perfil_existencias, modos_existencias = generar_perfil_existencias(rng_desglose_balance, sector)
    existencias_desglose_eur = {
        componente: fraccion * balance_eur["existencias"] for componente, fraccion in perfil_existencias.items()
    }
    (
        periodificacion_activo_pct, periodificacion_pasivo_corto_pct, periodificacion_pasivo_largo_pct,
        modo_periodificacion_activo, modo_periodificacion_pasivo_corto, modo_periodificacion_pasivo_largo,
    ) = (
        generar_periodificaciones_pct(rng_desglose_balance, categoria)
    )
    periodificacion_activo_eur = periodificacion_activo_pct * balance_eur["realizable"]
    periodificacion_pasivo_corto_eur = periodificacion_pasivo_corto_pct * balance_eur["otras_deudas_corto"]
    periodificacion_pasivo_largo_eur = periodificacion_pasivo_largo_pct * balance_eur["otras_deudas_largo"]

    # Segundo lote de desglose de balance (deudores/acreedores comerciales) — RNG PROPIO E
    # INDEPENDIENTE, mismo criterio que el resto de perfiles de este bloque. Perfil BASE
    # (arquetipo-agnóstico): `motor.evolucion_arquetipo.generar_evolucion_combinada` lo
    # sobrescribe en el año base si el arquetipo 20 está activo, ver ese módulo. El residuo de
    # `realizable` excluye `periodificacion_activo_eur` (primer lote, calculada arriba) — mismo
    # criterio que el residuo de "otras deudas" (quinto lote, ver `calcular_desglose_otras_deudas`)
    # para no re-etiquetar el mismo euro bajo dos epígrafes oficiales distintos. `acreedores_
    # comerciales` no tiene ninguna partida de activo que excluir, así que su base sigue siendo el
    # agregado bruto sin cambios.
    rng_desglose_balance_lote2 = np.random.default_rng(
        [semilla, zlib.crc32(f"{sector}|{segmento}|desglose_balance_lote2".encode("utf-8"))]
    )
    perfil_deudores, modos_deudores = generar_perfil_deudores(rng_desglose_balance_lote2)
    perfil_acreedores, modos_acreedores = generar_perfil_acreedores(rng_desglose_balance_lote2, categoria)
    realizable_residual_eur = balance_eur["realizable"] - periodificacion_activo_eur
    deudores_desglose_eur = {
        componente: fraccion * realizable_residual_eur for componente, fraccion in perfil_deudores.items()
    }
    acreedores_desglose_eur = {
        componente: fraccion * balance_eur["acreedores_comerciales"] for componente, fraccion in perfil_acreedores.items()
    }

    # Cuarto y último lote de desglose de balance (deudas financieras largo/corto plazo) — RNG
    # PROPIO E INDEPENDIENTE, mismo criterio que el resto de perfiles de este bloque. Sin
    # derivados en el año base (la cobertura del arquetipo 21 parte de valor razonable 0 en 2023,
    # ver motor.coberturas_subvenciones) — la base "con coste" es, por tanto, el propio agregado
    # `deudas_fin_largo`/`deudas_fin_corto` del catálogo, sin nada que excluir todavía.
    rng_desglose_balance_lote4 = np.random.default_rng(
        [semilla, zlib.crc32(f"{sector}|{segmento}|desglose_balance_lote4".encode("utf-8"))]
    )
    deudas_fin_fraccion_total, deudas_fin_fraccion_largo, modos_deudas_fin_total, modos_deudas_fin_largo = (
        generar_perfil_deudas_fin(rng_desglose_balance_lote4, categoria)
    )
    deudas_fin_largo_desglose_eur, deudas_fin_corto_desglose_eur = calcular_desglose_deudas_fin(
        deudas_fin_fraccion_total, deudas_fin_fraccion_largo,
        balance_eur["deudas_fin_largo"], balance_eur["deudas_fin_corto"], derivados_pasivo_largo_eur=0.0,
    )

    # Quinto lote de desglose de balance ("Otras deudas" largo/corto plazo) — RNG PROPIO E
    # INDEPENDIENTE, mismo criterio que el resto de perfiles de este bloque. Sin provisiones,
    # deudas con el grupo ni pasivos por impuesto diferido en el año base (ninguno de esos 3
    # mecanismos actúa antes de 2024) — pero las periodificaciones de pasivo (primer lote, `periodi
    # ficacion_pasivo_largo_eur`/`..._corto_eur` calculadas arriba) SÍ pueden tener saldo no nulo ya
    # en el año base (perfil fijo desde 2023), así que se excluyen del residuo igual que en años
    # posteriores — para no re-etiquetar el mismo euro bajo dos epígrafes oficiales distintos. Sin
    # reclasificación tampoco (no hay "año anterior" en el año base), mismo criterio que
    # "Derivados" en el cuarto lote. `aapp_pendiente` usa boost=False/False: los arquetipos 4/7
    # nunca actúan en el año base.
    deudas_socios_activa = sortear_deudas_socios_baseline(sector, segmento, semilla)
    rng_desglose_balance_lote5 = np.random.default_rng(
        [semilla, zlib.crc32(f"{sector}|{segmento}|desglose_balance_lote5".encode("utf-8"))]
    )
    otras_deudas_largo_perfil_pct, otras_deudas_corto_resto_perfil_pct, modos_otras_deudas_largo, modos_otras_deudas_corto = (
        generar_perfil_otras_deudas(rng_desglose_balance_lote5, deudas_socios_activa)
    )
    aapp_pendiente_corto_pct, modo_aapp_pendiente = sortear_aapp_pendiente_corto_pct(
        sector, segmento, semilla, deterioro_ciclo_caja_activo=False, dependencia_clientes_activo=False,
    )
    otras_deudas_largo_desglose_eur, otras_deudas_corto_desglose_eur = calcular_desglose_otras_deudas(
        otras_deudas_largo_perfil_pct, otras_deudas_corto_resto_perfil_pct, aapp_pendiente_corto_pct,
        balance_eur["otras_deudas_largo"] - periodificacion_pasivo_largo_eur,
        max(0.0, balance_eur["otras_deudas_corto"] - periodificacion_pasivo_corto_eur),
        acreedores_inmovilizado_largo_anterior_eur=0.0,
    )

    parcial_pyg = _generar_pyg_hasta_baii(rng, fila, ventas_objetivo, _AÑO_BASE_AMORTIZACION, amortizaciones_eur=amortizacion_eur_2023)
    pyg_pct, pyg_eur = _completar_pyg_con_deuda(parcial_pyg, deuda_financiera_eur)

    # "Hacienda Pública, deudora/acreedora por impuesto sobre beneficios" (7ª sub-partida oficial
    # de deudores/acreedores comerciales, ver bloque "Impuesto sobre Sociedades" y el docstring
    # de PERFIL_DEUDORES_BASE/PERFIL_ACREEDORES_POR_CATEGORIA más arriba) — residuo entre los
    # pagos a cuenta (art. 40 LIS) y el impuesto real del ejercicio. En el año base (2023, sin
    # "año -1" real generado por este motor) se usa el propio impuesto de 2023 como proxy del año
    # anterior (ver FRACCION_PAGOS_A_CUENTA_IS) — da sistemáticamente una posición "Hacienda
    # acreedora" (nunca "deudora") en el año base, por construcción de la propia proxy. Carve-out
    # desde "clientes"/"proveedores" (nunca aditivo sobre el total ya cuadrado de `realizable`/
    # `acreedores_comerciales`), con techo defensivo si el residuo dejara esa sub-partida en
    # negativo — mismo patrón que el resto de este lote.
    impuesto_beneficios_2023_eur = pyg_eur["impuesto_beneficios"]
    pagos_a_cuenta_is_eur = FRACCION_PAGOS_A_CUENTA_IS * max(0.0, impuesto_beneficios_2023_eur)
    hacienda_neta_is_eur = pagos_a_cuenta_is_eur - impuesto_beneficios_2023_eur
    hacienda_publica_deudora_eur = min(
        max(0.0, hacienda_neta_is_eur), max(0.0, deudores_desglose_eur["clientes"]),
    )
    hacienda_publica_acreedora_eur = min(
        max(0.0, -hacienda_neta_is_eur), max(0.0, acreedores_desglose_eur["proveedores"]),
    )
    deudores_desglose_eur["clientes"] -= hacienda_publica_deudora_eur
    deudores_desglose_eur["hacienda_publica_deudora"] = hacienda_publica_deudora_eur
    acreedores_desglose_eur["proveedores"] -= hacienda_publica_acreedora_eur
    acreedores_desglose_eur["hacienda_publica_acreedora"] = hacienda_publica_acreedora_eur

    # Desglose de PyG en líneas oficiales del PGC — RNG PROPIO E INDEPENDIENTE, mismo criterio
    # que el resto de perfiles de este bloque: no desplaza ningún sorteo ya existente. En el año
    # base ni provisiones ni insolvencia se dotan nunca (año_dotacion siempre 2024/2025) ni el
    # arquetipo 20 está activo (los arquetipos solo actúan desde 2024) — el "resto" de otros_
    # gastos_explot/gastos_personal es el agregado completo, y a) de ingresos_financieros es 0.
    rng_desglose_pyg_oficial = np.random.default_rng(
        [semilla, zlib.crc32(f"{sector}|{segmento}|desglose_pyg_oficial".encode("utf-8"))]
    )
    perfil_cifra_negocios, modos_cifra_negocios = generar_perfil_cifra_negocios(rng_desglose_pyg_oficial, categoria)
    perfil_consumos_explotacion, modos_consumos_explotacion = generar_perfil_consumos_explotacion(rng_desglose_pyg_oficial, categoria)
    perfil_otros_gastos_explot, modos_otros_gastos_explot = generar_perfil_otros_gastos_explot(rng_desglose_pyg_oficial, categoria)
    pyg_cifra_negocios_desglose_eur = {
        componente: fraccion * pyg_eur["cifra_negocios"] for componente, fraccion in perfil_cifra_negocios.items()
    }
    pyg_consumos_explotacion_desglose_eur = {
        componente: fraccion * pyg_eur["consumos_explotacion"] for componente, fraccion in perfil_consumos_explotacion.items()
    }
    pyg_otros_gastos_explot_desglose_eur = calcular_desglose_otros_gastos_explot(
        perfil_otros_gastos_explot, pyg_eur["otros_gastos_explot"], 0.0
    )
    pyg_gastos_personal_desglose_eur = calcular_desglose_gastos_personal(
        _AÑO_BASE_AMORTIZACION, categoria, pyg_eur["gastos_personal"], 0.0
    )
    pyg_ingresos_financieros_desglose_eur = calcular_desglose_ingresos_financieros(
        pyg_eur["ingresos_financieros"], 0.0, parcial_pyg.tipo_interes
    )

    # Hallazgo de auditoría de trazabilidad (sección 2.15/resumen de particularidades): los
    # perfiles "sorteados una vez por caso, fijos desde 2023" de los lotes de desglose de balance
    # (existencias, deudores/acreedores, deudas financieras) descartaban el modo típico/atípico de
    # cada componente con `_generar_partida(...) -> valor, _`, a diferencia de las masas de nivel
    # superior (`modos_balance`, diseño original) y de las primitivas de PyG (`parcial_pyg.modos`)
    # — inconsistencia corregida en origen, mismo namespace de claves con prefijo por lote.
    # `activo_no_corriente`/periodificaciones/capital_social (decisiones #24-25, ANTERIORES a los
    # lotes) tenían el MISMO problema — corregido igual, ver docstring de `_generar_capital_social`.
    modos = {
        **modos_balance,
        "rotacion_activo": modo_rotacion,
        **parcial_pyg.modos,
        **{f"activo_no_corriente.{componente}": modo for componente, modo in modos_activo_no_corriente.items()},
        "periodificacion_activo": modo_periodificacion_activo,
        "periodificacion_pasivo_corto": modo_periodificacion_pasivo_corto,
        "periodificacion_pasivo_largo": modo_periodificacion_pasivo_largo,
        **{f"existencias.{componente}": modo for componente, modo in modos_existencias.items()},
        **{f"deudores.{componente}": modo for componente, modo in modos_deudores.items()},
        **{f"acreedores.{componente}": modo for componente, modo in modos_acreedores.items()},
        **{f"deudas_fin_fraccion_total.{tipo}": modo for tipo, modo in modos_deudas_fin_total.items()},
        **{f"deudas_fin_fraccion_largo.{tipo}": modo for tipo, modo in modos_deudas_fin_largo.items()},
        **{f"otras_deudas_largo.{c}": m for c, m in modos_otras_deudas_largo.items()},
        **{f"otras_deudas_corto_resto.{c}": m for c, m in modos_otras_deudas_corto.items()},
        "otras_deudas_aapp_pendiente_corto": modo_aapp_pendiente,
        **{f"pyg_cifra_negocios.{c}": m for c, m in modos_cifra_negocios.items()},
        **{f"pyg_consumos_explotacion.{c}": m for c, m in modos_consumos_explotacion.items()},
        **{f"pyg_otros_gastos_explot.{c}": m for c, m in modos_otros_gastos_explot.items()},
        "pyg_gastos_personal": "derivado",
        "pyg_ingresos_financieros": "derivado",
    }

    # Desagregación de PN (ver docstrings de las constantes arriba) — sorteo AÑADIDO AL FINAL de
    # la secuencia de rng ya existente, después de todo lo demás: no desplaza ningún sorteo
    # anterior, así que no cambia ningún valor de balance/PyG previo a este punto.
    capital_social_eur, modo_capital_social = _generar_capital_social(rng, balance_eur["patrimonio_neto"])
    modos["capital_social"] = modo_capital_social
    reservas_eur = balance_eur["patrimonio_neto"] - capital_social_eur - pyg_eur["resultado_ejercicio"]

    return EmpresaBase(
        sector_codigo=sector,
        sector_nombre=sector_nombre,
        segmento=segmento,
        ventas_objetivo=ventas_objetivo,
        semilla=semilla,
        rotacion_activo=rotacion_activo,
        activo_total_eur=activo_total_eur,
        balance_pct=balance_pct,
        balance_eur=balance_eur,
        pyg_pct=pyg_pct,
        pyg_eur=pyg_eur,
        modos=modos,
        ajuste_cuadre_eur=ajuste_cuadre_eur,
        capital_social_eur=capital_social_eur,
        reservas_eur=reservas_eur,
        activo_no_corriente_perfil_pct=perfil_activo_no_corriente,
        activo_no_corriente_desglose_eur=activo_no_corriente_desglose_eur,
        coleccion_activos_amortizables=coleccion_activos_amortizables,
        perfil_subtipos_material_pct=perfil_subtipos_material,
        perfil_subtipos_intangible_pct=perfil_subtipos_intangible,
        tipo_interes=parcial_pyg.tipo_interes,
        tipo_impuesto_efectivo=parcial_pyg.tipo_impuesto_efectivo,
        existencias_perfil_pct=perfil_existencias,
        existencias_desglose_eur=existencias_desglose_eur,
        periodificacion_activo_pct=periodificacion_activo_pct,
        periodificacion_pasivo_corto_pct=periodificacion_pasivo_corto_pct,
        periodificacion_pasivo_largo_pct=periodificacion_pasivo_largo_pct,
        periodificacion_activo_eur=periodificacion_activo_eur,
        periodificacion_pasivo_corto_eur=periodificacion_pasivo_corto_eur,
        periodificacion_pasivo_largo_eur=periodificacion_pasivo_largo_eur,
        deudores_perfil_pct=perfil_deudores,
        deudores_desglose_eur=deudores_desglose_eur,
        acreedores_perfil_pct=perfil_acreedores,
        acreedores_desglose_eur=acreedores_desglose_eur,
        deudas_fin_fraccion_total=deudas_fin_fraccion_total,
        deudas_fin_fraccion_largo=deudas_fin_fraccion_largo,
        deudas_fin_largo_desglose_eur=deudas_fin_largo_desglose_eur,
        deudas_fin_corto_desglose_eur=deudas_fin_corto_desglose_eur,
        deudas_socios_activa=deudas_socios_activa,
        otras_deudas_largo_perfil_pct=otras_deudas_largo_perfil_pct,
        otras_deudas_corto_resto_perfil_pct=otras_deudas_corto_resto_perfil_pct,
        otras_deudas_largo_desglose_eur=otras_deudas_largo_desglose_eur,
        otras_deudas_corto_desglose_eur=otras_deudas_corto_desglose_eur,
        aapp_pendiente_corto_pct=aapp_pendiente_corto_pct,
        pyg_cifra_negocios_perfil_pct=perfil_cifra_negocios,
        pyg_cifra_negocios_desglose_eur=pyg_cifra_negocios_desglose_eur,
        pyg_consumos_explotacion_perfil_pct=perfil_consumos_explotacion,
        pyg_consumos_explotacion_desglose_eur=pyg_consumos_explotacion_desglose_eur,
        pyg_otros_gastos_explot_perfil_pct=perfil_otros_gastos_explot,
        pyg_otros_gastos_explot_desglose_eur=pyg_otros_gastos_explot_desglose_eur,
        pyg_gastos_personal_desglose_eur=pyg_gastos_personal_desglose_eur,
        pyg_ingresos_financieros_desglose_eur=pyg_ingresos_financieros_desglose_eur,
    )
