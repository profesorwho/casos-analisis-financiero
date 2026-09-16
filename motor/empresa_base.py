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
    PROB_ATIPICO,
    _generar_partida,
    _generar_partida_con_memoria,
    _normal_truncada,
    _renormalizar_a_total,
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
PRIMITIVAS_PYG = {
    "cifra_negocios": "cifra_negocios_pct",
    "otros_ingresos_explot": "otros_ingresos_explot_pct",
    "consumos_explotacion": "consumos_explotacion_pct",
    "otros_gastos_explot": "otros_gastos_explot_pct",
    "gastos_personal": "gastos_personal_pct",
    "amortizaciones": "amortizaciones_pct",
    "resultado_extraordinario": "resultado_extraordinario_pct",
    "ingresos_financieros": "ingresos_financieros_pct",
    "impuesto_beneficios": "impuesto_beneficios_pct",
}

# Primitivas de PyG que no pueden ser negativas (importes de ingreso/gasto en sí mismos).
# resultado_extraordinario e impuesto_beneficios sí pueden serlo (crédito fiscal, extraordinario
# negativo): el propio catálogo tiene valores Huber negativos para ambas en algunos sectores.
PRIMITIVAS_PYG_NO_NEGATIVAS = frozenset(PRIMITIVAS_PYG) - {"resultado_extraordinario", "impuesto_beneficios"}

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
# Segundo lote de desglose de balance: "Deudores comerciales y otras cuentas a cobrar" (7
# sub-partidas oficiales, carve-out de `realizable`) y "Acreedores comerciales y otras cuentas a
# pagar" (7 sub-partidas oficiales, carve-out de `acreedores_comerciales`) — HIPÓTESIS DE DISEÑO,
# el catálogo ACCID nunca desglosó ninguna de las dos masas más allá del agregado. Mismo patrón
# de ruido mixto/renormalizado que el resto de perfiles de este bloque.
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
    "activos_impuesto_corriente": 0.025,
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
        "pasivos_impuesto_corriente": 0.03, "otras_deudas_aapp": 0.03, "anticipos_clientes": 0.035,
        "proveedores_empresas_grupo": 0.0,
    },
    "servicios_industriales": {
        "proveedores": 0.72, "personal": 0.06, "acreedores_varios": 0.06,
        "pasivos_impuesto_corriente": 0.035, "otras_deudas_aapp": 0.035, "anticipos_clientes": 0.09,
        "proveedores_empresas_grupo": 0.0,
    },
    "servicios_profesionales": {
        "proveedores": 0.55, "personal": 0.16, "acreedores_varios": 0.09,
        "pasivos_impuesto_corriente": 0.05, "otras_deudas_aapp": 0.045, "anticipos_clientes": 0.105,
        "proveedores_empresas_grupo": 0.0,
    },
    "servicios_tic": {
        "proveedores": 0.52, "personal": 0.15, "acreedores_varios": 0.08,
        "pasivos_impuesto_corriente": 0.045, "otras_deudas_aapp": 0.04, "anticipos_clientes": 0.165,
        "proveedores_empresas_grupo": 0.0,
    },
    "transporte_logistica": {
        "proveedores": 0.75, "personal": 0.08, "acreedores_varios": 0.05,
        "pasivos_impuesto_corriente": 0.03, "otras_deudas_aapp": 0.03, "anticipos_clientes": 0.06,
        "proveedores_empresas_grupo": 0.0,
    },
    "comercio_hosteleria": {
        "proveedores": 0.80, "personal": 0.065, "acreedores_varios": 0.045,
        "pasivos_impuesto_corriente": 0.03, "otras_deudas_aapp": 0.03, "anticipos_clientes": 0.03,
        "proveedores_empresas_grupo": 0.0,
    },
    "construccion": {
        "proveedores": 0.68, "personal": 0.05, "acreedores_varios": 0.05,
        "pasivos_impuesto_corriente": 0.03, "otras_deudas_aapp": 0.03, "anticipos_clientes": 0.16,
        "proveedores_empresas_grupo": 0.0,
    },
    "administracion_educacion_sanidad": {
        "proveedores": 0.58, "personal": 0.14, "acreedores_varios": 0.055,
        "pasivos_impuesto_corriente": 0.035, "otras_deudas_aapp": 0.04, "anticipos_clientes": 0.15,
        "proveedores_empresas_grupo": 0.0,
    },
    "inmobiliario": {
        "proveedores": 0.65, "personal": 0.05, "acreedores_varios": 0.06,
        "pasivos_impuesto_corriente": 0.035, "otras_deudas_aapp": 0.035, "anticipos_clientes": 0.17,
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


def categoria_de_sector(sector_codigo: str) -> str:
    if sector_codigo not in CATEGORIA_SECTOR:
        raise EmpresaBaseError(f"Sector '{sector_codigo}' no tiene categoría asignada en CATEGORIA_SECTOR.")
    return CATEGORIA_SECTOR[sector_codigo]


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
    resultado_extraordinario_eur: float
    baii_eur: float
    ingresos_financieros_eur: float
    impuesto_beneficios_eur: float
    tipo_interes: float
    modos: dict[str, str]


def _generar_pyg_hasta_baii(
    rng: np.random.Generator,
    fila: pd.Series,
    ventas_objetivo: float,
    año: int,
    primitivas_forzadas: dict[str, float] | None = None,
    amortizaciones_eur: float | None = None,
    anterior_pyg_pct: dict[str, float] | None = None,
    anterior_tipo_interes: float | None = None,
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

    `anterior_pyg_pct`/`anterior_tipo_interes`: SOLO se pasan al generar 2024/2025 (el año base
    no tiene "año anterior" al que agarrarse — sigue siendo un sorteo limpio contra el Huber del
    sector, ver `generar_empresa_base`, que no los pasa). Cuando están presentes, cualquier
    primitiva NO forzada por un arquetipo usa `_generar_partida_con_memoria` en vez de
    `_generar_partida` — continuidad con el valor REAL del año anterior y varianza reducida, en
    vez de un sorteo limpio nuevo cada año (ver decisiones_plausibilidad.md #75/#77/#78 y
    docstring de `_generar_partida_con_memoria` en motor/ruido.py). No afecta en absoluto a las
    primitivas SÍ forzadas por un arquetipo (siguen su propio mecanismo, `_mover_ratio_continuo`,
    completamente aparte de este).
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
    impuesto_beneficios_eur = brutos["impuesto_beneficios"] / 100 * ingresos_explotacion_eur

    margen_bruto_eur = ingresos_explotacion_eur - consumos_explotacion_eur
    valor_añadido_eur = margen_bruto_eur - otros_gastos_explot_eur
    baii_eur = valor_añadido_eur - gastos_personal_eur - amortizaciones_eur_final + resultado_extraordinario_eur

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
        resultado_extraordinario_eur=resultado_extraordinario_eur,
        baii_eur=baii_eur,
        ingresos_financieros_eur=ingresos_financieros_eur,
        impuesto_beneficios_eur=impuesto_beneficios_eur,
        tipo_interes=tipo_interes,
        modos=modos,
    )


def _completar_pyg_con_deuda(
    parcial: _PygParcial, deuda_financiera_media_eur: float
) -> tuple[dict[str, float], dict[str, float]]:
    """Termina la cascada (BAI y resultado del ejercicio) usando la deuda financiera media
    (largo + corto plazo, promedio inicio/fin del ejercicio) para calcular gastos financieros
    = deuda financiera media x tipo de interés del sector."""
    gastos_financieros_eur = deuda_financiera_media_eur * parcial.tipo_interes
    bai_eur = parcial.baii_eur + parcial.ingresos_financieros_eur - gastos_financieros_eur
    resultado_ejercicio_eur = bai_eur - parcial.impuesto_beneficios_eur

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
        "resultado_extraordinario": parcial.resultado_extraordinario_eur,
        "baii": parcial.baii_eur,
        "ingresos_financieros": parcial.ingresos_financieros_eur,
        "gastos_financieros": gastos_financieros_eur,
        "bai": bai_eur,
        "impuesto_beneficios": parcial.impuesto_beneficios_eur,
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
) -> EmpresaBase:
    """Genera el balance y la PyG base (un ejercicio, sin arquetipos) de una empresa ficticia.

    `sector` es el código entre paréntesis del catálogo (p. ej. "24.1", "4941"). `segmento` es
    "grandes_medianas" o "pequeñas". El resultado es reproducible: misma semilla+sector+segmento,
    mismo caso (ver docstring del módulo sobre por qué la semilla del RNG mezcla sector+segmento,
    no solo `semilla`)."""
    if segmento not in SEGMENTOS_VALIDOS:
        raise EmpresaBaseError(f"Segmento '{segmento}' no válido. Debe ser uno de: {sorted(SEGMENTOS_VALIDOS)}")
    if ventas_objetivo <= 0:
        raise EmpresaBaseError(f"ventas_objetivo debe ser positivo, recibido: {ventas_objetivo}")

    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

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
    # sobrescribe en el año base si el arquetipo 20 está activo, ver ese módulo.
    rng_desglose_balance_lote2 = np.random.default_rng(
        [semilla, zlib.crc32(f"{sector}|{segmento}|desglose_balance_lote2".encode("utf-8"))]
    )
    perfil_deudores, modos_deudores = generar_perfil_deudores(rng_desglose_balance_lote2)
    perfil_acreedores, modos_acreedores = generar_perfil_acreedores(rng_desglose_balance_lote2, categoria)
    deudores_desglose_eur = {
        componente: fraccion * balance_eur["realizable"] for componente, fraccion in perfil_deudores.items()
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

    parcial_pyg = _generar_pyg_hasta_baii(rng, fila, ventas_objetivo, _AÑO_BASE_AMORTIZACION, amortizaciones_eur=amortizacion_eur_2023)
    pyg_pct, pyg_eur = _completar_pyg_con_deuda(parcial_pyg, deuda_financiera_eur)

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
    )
