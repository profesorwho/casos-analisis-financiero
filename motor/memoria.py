"""Generación de notas de memoria puramente cualitativas (arquetipos 7, 19, 20, 21, 22 —
sección 2.24). A diferencia de todo lo construido en `motor.evolucion_arquetipo`, estos
arquetipos NO mueven ninguna cifra del balance o la PyG: son texto, seleccionado y — cuando
aplica — parametrizado con cifras derivadas de una empresa ya generada, pero sin desviar nada.
Por eso viven en un módulo aparte, no como un `Efecto` más de `motor.arquetipos`.

**Una función por arquetipo, no una genérica parametrizada.** Se decidió así (y no una única
función con un `if arquetipo_id == ...` interno) porque el CONTENIDO de cada arquetipo es
distinto de verdad — parámetros distintos (nº de clientes, tipo de activo, contraparte
vinculada, nocional de cobertura), rangos distintos, plantillas distintas — no una variación
menor de una misma forma, a diferencia de `masa_circulante` o `pyg_primitiva`, donde sí hay una
forma común real que generalizar. Forzar una función genérica aquí habría significado un `if`
por arquetipo dentro de una función con nombre genérico, sin ganar nada sobre 5 funciones con
nombre propio. `generar_nota_memoria_pura()` al final del módulo sí ofrece un despachador por
`arquetipo_id`, para el código que solo tiene el id y no sabe (ni le importa) la función
concreta — internamente solo hace ese `if`/lookup, no duplica lógica de contenido.

**Reproducibilidad — mismo patrón ya validado y corregido en `motor.evolucion_arquetipo`
(hash estable `zlib.crc32`, RNG independiente, NUNCA un generador compartido con otro
propósito).** Cada función siembra su propio `np.random.Generator` mezclando `semilla` con un
hash de sector+segmento+intensidad+`arquetipo_id` — incluye el `arquetipo_id` (a diferencia de
`rng_tendencia`/`rngs_pyg` en evolucion_arquetipo.py, que deliberadamente NO mezclan intensidad
ni arquetipo) porque aquí el objetivo es el opuesto: estas notas podrán combinarse varias a la
vez sobre el mismo caso en una fase futura (sección 2.12), y cada arquetipo de memoria debe
sortear su propio texto de forma independiente de los demás, no compartir estado con ellos.

**Etiquetado temático.** Cada `NotaMemoria` lleva `etiquetas: tuple[str, ...]` — qué temas o
variables toca (p. ej. `("clientes", "concentracion")`). Es deliberadamente un conjunto FIJO
por arquetipo (no varía plantilla a plantilla dentro del mismo arquetipo), salvo en el 22
("comodín narrativo"), donde cada una de las 10 redacciones trata un tema distinto y por tanto
lleva su propia etiqueta — es la naturaleza del propio arquetipo, no una inconsistencia. Estas
etiquetas NO se usan todavía para detectar contradicciones entre notas activas a la vez (eso es
el siguiente paso, sección 2.12) — aquí solo se garantiza que queden asignadas de forma
consistente y reutilizable para cuando se construya esa lógica.

**Formato de cifras en el texto**: importes en euros redondeados al millar más cercano,
porcentajes al entero más cercano — una memoria real no mostraría "34.728.193,47 €" ni
"47,3826 %", y una precisión falsa así sería, además, un candidato a "cifra absurda" percibida
por quien lea el caso.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from motor.evolucion_arquetipo import EjercicioEmpresa


@dataclass(frozen=True)
class NotaMemoria:
    arquetipo_id: str
    numero: int
    texto: str
    etiquetas: tuple[str, ...]


def _rng_memoria(sector: str, segmento: str, intensidad: str, arquetipo_id: str, semilla: int) -> np.random.Generator:
    """RNG dedicado e independiente por (sector, segmento, intensidad, arquetipo_id, semilla) —
    ver docstring del módulo, sección "Reproducibilidad"."""
    entropia = zlib.crc32(f"{sector}|{segmento}|{intensidad}|{arquetipo_id}".encode("utf-8"))
    return np.random.default_rng([semilla, entropia])


def _fmt_eur(valor: float) -> str:
    redondeado = round(valor / 1000) * 1000
    return f"{redondeado:,.0f}".replace(",", ".")


def _fmt_pct(valor: float) -> str:
    return f"{round(valor)}"


# --------------------------------------------------------------------------------------------
# Arquetipo 7 — Dependencia de pocos clientes.
# --------------------------------------------------------------------------------------------

# Rangos de concentración por intensidad (nº de clientes principales, % de la cifra de negocio
# que representan) — sección 2.24 no fija cifras, criterio propio: a mayor intensidad, MENOS
# clientes concentran MÁS ventas (ambos ejes se mueven juntos, no solo uno).
RANGOS_CONCENTRACION_CLIENTES = {
    "leve": {"clientes": (3, 4), "pct": (35, 45)},
    "moderado": {"clientes": (2, 3), "pct": (45, 60)},
    "fuerte": {"clientes": (1, 2), "pct": (60, 75)},
}

PLANTILLAS_DEPENDENCIA_CLIENTES = (
    "Los {n_clientes} principales clientes de la sociedad concentran el {pct}% de la cifra de "
    "negocio del ejercicio, lo que expone el resultado a la evolución comercial de un número "
    "reducido de contrapartes.",
    "La cartera de clientes presenta un grado de concentración relevante: el {pct}% de las "
    "ventas del ejercicio corresponde a {n_clientes} clientes, sin que exista a la fecha de "
    "formulación de las cuentas un plan formalizado de diversificación comercial.",
    "El {pct}% de la cifra de negocio del ejercicio procede de {n_clientes} clientes, "
    "circunstancia que la Dirección atribuye a la naturaleza del sector de actividad y que "
    "viene manteniéndose en ejercicios anteriores.",
    "La sociedad mantiene una dependencia comercial significativa de {n_clientes} clientes, "
    "que en conjunto representan el {pct}% de las ventas del ejercicio, sin que existan "
    "contratos de suministro a largo plazo que garanticen la continuidad de la relación.",
    "Del total de la cifra de negocio del ejercicio, el {pct}% corresponde a {n_clientes} "
    "clientes principales, superando el umbral que la Dirección considera relevante a efectos "
    "de seguimiento del riesgo de concentración comercial.",
)


def generar_nota_dependencia_clientes(
    sector: str, segmento: str, intensidad: str, semilla: int, ejercicio: EjercicioEmpresa
) -> NotaMemoria:
    """Arquetipo 7. `ejercicio` no se usa (la concentración se expresa en % de ventas, no en
    euros) — se mantiene en la firma por consistencia con el resto de funciones de este módulo
    y por si una plantilla futura quisiera citar la cifra de ventas absoluta."""
    del ejercicio
    rng = _rng_memoria(sector, segmento, intensidad, "dependencia_pocos_clientes", semilla)
    rango = RANGOS_CONCENTRACION_CLIENTES[intensidad]
    n_clientes = int(rng.integers(rango["clientes"][0], rango["clientes"][1] + 1))
    pct = round(rng.uniform(*rango["pct"]))
    indice = rng.integers(len(PLANTILLAS_DEPENDENCIA_CLIENTES))
    texto = PLANTILLAS_DEPENDENCIA_CLIENTES[indice].format(n_clientes=n_clientes, pct=pct)
    return NotaMemoria(
        arquetipo_id="dependencia_pocos_clientes", numero=7, texto=texto, etiquetas=("clientes", "concentracion")
    )


# --------------------------------------------------------------------------------------------
# Arquetipo 19 — Activo mantenido para la venta.
# --------------------------------------------------------------------------------------------

# Cada plantilla combina ya un tipo de activo + motivo coherente entre sí (no se sustituyen por
# separado): evita combinaciones extrañas de tipo de activo y motivo elegidos independientemente.
PLANTILLAS_ACTIVO_MANTENIDO_VENTA = (
    "La sociedad mantiene clasificada como activo no corriente mantenido para la venta una nave "
    "industrial actualmente sin uso productivo, cuya comercialización se ha iniciado dentro del "
    "ejercicio como parte del plan de racionalización de activos no operativos.",
    "Se ha reclasificado a activo mantenido para la venta una participación financiera "
    "minoritaria no estratégica, cuya desinversión responde a la decisión de la Dirección de "
    "centrar los recursos disponibles en la actividad principal del grupo.",
    "La maquinaria de producción sustituida durante el ejercicio como consecuencia de la "
    "renovación del proceso productivo permanece clasificada como activo mantenido para la "
    "venta, a la espera de formalizar su enajenación.",
    "Un inmueble de oficinas no afecto a la actividad principal figura clasificado como activo "
    "mantenido para la venta, tras la decisión de la Dirección de desinvertir en activos "
    "inmobiliarios no operativos.",
    "La sociedad mantiene clasificado como activo mantenido para la venta un local comercial "
    "procedente de una línea de negocio discontinuada en ejercicios anteriores, cuya venta se "
    "considera altamente probable dentro de los doce meses siguientes al cierre.",
)


def generar_nota_activo_mantenido_venta(
    sector: str, segmento: str, intensidad: str, semilla: int, ejercicio: EjercicioEmpresa
) -> NotaMemoria:
    """Arquetipo 19. `ejercicio` no se usa (el tipo de activo y el motivo son cualitativos, sin
    cifra asociada) — se mantiene en la firma por la misma razón que en el arquetipo 7."""
    del ejercicio
    rng = _rng_memoria(sector, segmento, intensidad, "activo_mantenido_venta", semilla)
    indice = rng.integers(len(PLANTILLAS_ACTIVO_MANTENIDO_VENTA))
    texto = PLANTILLAS_ACTIVO_MANTENIDO_VENTA[indice]
    return NotaMemoria(arquetipo_id="activo_mantenido_venta", numero=19, texto=texto, etiquetas=("activo", "desinversion"))


# --------------------------------------------------------------------------------------------
# Arquetipo 20 — Operaciones vinculadas.
# --------------------------------------------------------------------------------------------

# % del importe de la operación sobre la magnitud del balance/PyG que le corresponda (ver
# _BASE_IMPORTE_VINCULADAS por plantilla) — rango propio (no lo fija la sección 2.24): topado
# por debajo del 20% en todas las intensidades para que la cifra nunca deje de ser plausible
# frente al tamaño de la empresa (comprobado además en el barrido de verificación).
RANGOS_IMPORTE_VINCULADAS_PCT = {"leve": (2, 5), "moderado": (5, 10), "fuerte": (10, 18)}

# Suelo defensivo del importe citado, en euros — mismo tipo de cota (huber+techo, o aquí un
# suelo absoluto) ya usada en otros arquetipos para evitar valores implausibles, aplicado tras
# comprobar en pruebas de estrés (324 casos) que el % puro, sin suelo, podía dar cifras
# ridículamente pequeñas para una "operación vinculada relevante" de memoria: mínimo observado
# 8.000 €, 1 caso por debajo de 10.000 €, 5 por debajo de 20.000 €, 17 por debajo de 50.000 €.
SUELO_IMPORTE_VINCULADAS_EUR = 30_000.0

# Cada entrada: (plantilla con {importe}/{pct}, magnitud de referencia para calcular el importe).
_OPERACIONES_VINCULADAS = (
    (
        "La sociedad mantiene con su empresa matriz un préstamo intragrupo por importe de "
        "{importe} euros, equivalente al {pct}% de su patrimonio neto a cierre del ejercicio, "
        "formalizado en condiciones de mercado según la política de precios de transferencia "
        "del grupo.",
        "patrimonio_neto",
    ),
    (
        "Durante el ejercicio la sociedad ha facturado servicios de gestión a una sociedad del "
        "grupo por importe de {importe} euros, equivalente al {pct}% de la cifra de negocio del "
        "ejercicio.",
        "ventas",
    ),
    (
        "La sociedad satisface a uno de sus socios/administradores una renta anual de "
        "arrendamiento por el uso de un inmueble afecto a la actividad, por importe de "
        "{importe} euros, equivalente al {pct}% de la cifra de negocio del ejercicio.",
        "ventas",
    ),
    (
        "La sociedad ha recibido financiación de una sociedad del grupo por importe de "
        "{importe} euros, equivalente al {pct}% de su deuda financiera total a cierre del "
        "ejercicio, sin que se hayan devengado gastos financieros adicionales a los ya "
        "reconocidos en la cuenta de pérdidas y ganancias.",
        "deuda_financiera",
    ),
    (
        "La empresa matriz ha prestado a la sociedad servicios de asistencia técnica y "
        "administrativa por importe de {importe} euros durante el ejercicio, equivalente al "
        "{pct}% de la cifra de negocio, facturados en condiciones de mercado.",
        "ventas",
    ),
)


def _magnitud_referencia(ejercicio: EjercicioEmpresa, nombre: str) -> float:
    if nombre == "ventas":
        return ejercicio.ventas
    if nombre == "patrimonio_neto":
        return ejercicio.balance_eur["patrimonio_neto"]
    return ejercicio.balance_eur["deudas_fin_largo"] + ejercicio.balance_eur["deudas_fin_corto"]


def generar_nota_operaciones_vinculadas(
    sector: str, segmento: str, intensidad: str, semilla: int, ejercicio: EjercicioEmpresa
) -> NotaMemoria:
    """Arquetipo 20. El importe se calcula como % (rango por intensidad) de la magnitud de
    balance/PyG que corresponda al tipo de operación de la plantilla elegida — así el importe
    siempre queda coherente con el tamaño real de la empresa generada, nunca un número
    arbitrario. Topado por abajo en SUELO_IMPORTE_VINCULADAS_EUR: el `{pct}` mostrado en el
    texto se RECALCULA sobre el importe ya topado (no el % originalmente sorteado), para que el
    texto nunca sea internamente inconsistente (un importe y un % que no se correspondan)."""
    rng = _rng_memoria(sector, segmento, intensidad, "operaciones_vinculadas", semilla)
    indice = rng.integers(len(_OPERACIONES_VINCULADAS))
    plantilla, magnitud_nombre = _OPERACIONES_VINCULADAS[indice]
    rango_pct = RANGOS_IMPORTE_VINCULADAS_PCT[intensidad]
    pct_objetivo = rng.uniform(*rango_pct)
    magnitud = _magnitud_referencia(ejercicio, magnitud_nombre)
    importe = max(magnitud * pct_objetivo / 100, SUELO_IMPORTE_VINCULADAS_EUR)
    pct_mostrado = importe / magnitud * 100
    texto = plantilla.format(importe=_fmt_eur(importe), pct=_fmt_pct(pct_mostrado))
    return NotaMemoria(
        arquetipo_id="operaciones_vinculadas", numero=20, texto=texto, etiquetas=("vinculadas", "partes_relacionadas")
    )


# --------------------------------------------------------------------------------------------
# Arquetipo 21 — Coberturas.
# --------------------------------------------------------------------------------------------

# % de la deuda financiera total cubierta por intensidad — una cobertura típica cubre una
# fracción SUSTANCIAL de la exposición, no un importe simbólico (a diferencia de las operaciones
# vinculadas del arquetipo 20, que sí deben quedar acotadas a una fracción pequeña del balance).
RANGOS_COBERTURA_PCT_DEUDA = {"leve": (30, 45), "moderado": (45, 65), "fuerte": (65, 90)}

# Suelo defensivo del nocional citado, en euros — no se observó ningún caso por debajo en las
# pruebas de estrés (324 casos, mínimo 60.000 €, 0 por debajo de 50.000 €; deuda financiera
# mínima observada 151.500 €, muy por encima de este suelo, así que nunca puede empujar el %
# mostrado por encima del 100%), pero se añade por el mismo criterio defensivo que
# SUELO_IMPORTE_VINCULADAS_EUR: una cobertura de unos pocos miles de euros tampoco sonaría
# "relevante" en una memoria.
SUELO_NOCIONAL_COBERTURA_EUR = 50_000.0

TIPOS_REFERENCIA_COBERTURA = ("Euríbor a 3 meses", "Euríbor a 6 meses", "Euríbor a 12 meses")

PLANTILLAS_COBERTURAS = (
    "La sociedad tiene contratado un instrumento de cobertura de tipos de interés (IRS) sobre "
    "un nocional de {importe} euros, equivalente al {pct}% de su deuda financiera a tipo "
    "variable, referenciado a {tipo_referencia}, con el objetivo de mitigar el riesgo de subida "
    "de tipos.",
    "Con el fin de cubrir el riesgo de variación de {tipo_referencia}, la sociedad ha suscrito "
    "un contrato de permuta de tipos de interés sobre un importe nocional de {importe} euros, "
    "equivalente al {pct}% de la deuda financiera viva a cierre del ejercicio.",
    "La sociedad cubre parcialmente su exposición a la evolución de {tipo_referencia} mediante "
    "un instrumento financiero derivado sobre un nocional de {importe} euros ({pct}% de la "
    "deuda financiera total), cuyo valor razonable se registra en patrimonio neto conforme a la "
    "contabilidad de coberturas.",
    "Como consecuencia del incremento de tipos de interés, la sociedad contrató durante el "
    "ejercicio una cobertura sobre {tipo_referencia} por un nocional de {importe} euros, "
    "equivalente al {pct}% de su deuda financiera, limitando su exposición futura a subidas "
    "adicionales del tipo de referencia.",
    "La política de gestión de riesgo financiero de la sociedad incluye la cobertura de una "
    "parte de la deuda a tipo variable: a cierre del ejercicio, el {pct}% de la deuda "
    "financiera ({importe} euros) está cubierto mediante un derivado referenciado a "
    "{tipo_referencia}.",
)


def generar_nota_coberturas(
    sector: str, segmento: str, intensidad: str, semilla: int, ejercicio: EjercicioEmpresa
) -> NotaMemoria:
    """Arquetipo 21. El nocional se calcula como % (rango por intensidad) de la deuda financiera
    total real de la empresa generada — nunca un importe desconectado de cuánta deuda tiene la
    empresa que, en teoría, se está cubriendo. Topado por abajo en SUELO_NOCIONAL_COBERTURA_EUR;
    el `{pct}` mostrado se recalcula sobre el nocional ya topado, por la misma razón de
    consistencia interna que en `generar_nota_operaciones_vinculadas`."""
    rng = _rng_memoria(sector, segmento, intensidad, "coberturas", semilla)
    rango_pct = RANGOS_COBERTURA_PCT_DEUDA[intensidad]
    pct_objetivo = rng.uniform(*rango_pct)
    deuda_financiera_total = ejercicio.balance_eur["deudas_fin_largo"] + ejercicio.balance_eur["deudas_fin_corto"]
    importe = max(deuda_financiera_total * pct_objetivo / 100, SUELO_NOCIONAL_COBERTURA_EUR)
    pct_mostrado = importe / deuda_financiera_total * 100
    indice_plantilla = rng.integers(len(PLANTILLAS_COBERTURAS))
    indice_referencia = rng.integers(len(TIPOS_REFERENCIA_COBERTURA))
    tipo_referencia = TIPOS_REFERENCIA_COBERTURA[indice_referencia]
    texto = PLANTILLAS_COBERTURAS[indice_plantilla].format(
        importe=_fmt_eur(importe), pct=_fmt_pct(pct_mostrado), tipo_referencia=tipo_referencia
    )
    return NotaMemoria(arquetipo_id="coberturas", numero=21, texto=texto, etiquetas=("deuda", "cobertura_riesgo"))


# --------------------------------------------------------------------------------------------
# Arquetipo 22 — Información relevante en memoria (comodín narrativo).
# --------------------------------------------------------------------------------------------

# A diferencia de los 4 arquetipos anteriores, este es intencionadamente variado: cada entrada
# es un tema distinto, con su propia etiqueta — no variaciones de una misma idea.
_NOTAS_COMODIN = (
    (
        "Con posterioridad al cierre del ejercicio, la sociedad ha formalizado la venta de una "
        "nave industrial no afecta a la actividad, operación que no estaba prevista a la fecha "
        "de cierre y que no tiene efecto en las presentes cuentas anuales.",
        ("hechos_posteriores",),
    ),
    (
        "La sociedad es parte demandada en un procedimiento judicial de naturaleza mercantil, "
        "cuyo desenlace no puede preverse con certeza a la fecha de formulación de las cuentas "
        "anuales; no se ha dotado provisión alguna al considerar la Dirección, con el "
        "asesoramiento de sus letrados, que el riesgo de pérdida no es probable.",
        ("contingencias", "legal"),
    ),
    (
        "Durante el ejercicio la sociedad ha modificado el criterio de amortización aplicado a "
        "un elemento del inmovilizado material, ajustándolo a su nueva vida útil estimada, sin "
        "que el efecto de dicho cambio sea significativo sobre las cuentas anuales.",
        ("criterio_contable",),
    ),
    (
        "La sociedad se encuentra sometida a una actuación de comprobación por parte de la "
        "Administración tributaria correspondiente a ejercicios no prescritos, sin que a la "
        "fecha de formulación de las cuentas anuales se haya recibido liquidación alguna "
        "derivada de dicha actuación.",
        ("fiscal", "contingencias"),
    ),
    (
        "Existe un litigio de carácter laboral de escasa cuantía en curso con un antiguo "
        "empleado de la sociedad, cuyo efecto potencial sobre las cuentas anuales se considera "
        "no significativo.",
        ("litigios", "legal"),
    ),
    (
        "Durante el ejercicio se ha producido un cambio en la composición del órgano de "
        "administración de la sociedad, sin que ello haya afectado a la continuidad de la "
        "actividad ni a las políticas contables aplicadas.",
        ("gobierno_corporativo",),
    ),
    (
        "La sociedad ha asumido durante el ejercicio compromisos de inversión en mejoras "
        "medioambientales en sus instalaciones productivas, cuyo calendario de ejecución se "
        "extiende a los próximos ejercicios.",
        ("medioambiente",),
    ),
    (
        "La sociedad ha otorgado avales bancarios a favor de terceros por un importe no "
        "significativo en relación con el conjunto de su balance, sin que existan indicios de "
        "que vayan a ser ejecutados.",
        ("avales", "contingencias"),
    ),
    (
        "La sociedad mantiene una relación comercial relevante con un único proveedor para el "
        "suministro de una materia prima esencial en su proceso productivo, sin que existan a "
        "la fecha de cierre alternativas de aprovisionamiento plenamente desarrolladas.",
        ("proveedores", "concentracion"),
    ),
    (
        "La sociedad ha sido beneficiaria durante el ejercicio de una subvención de capital "
        "concedida por una administración pública, vinculada al cumplimiento de determinadas "
        "condiciones futuras de mantenimiento de la inversión y el empleo.",
        ("subvenciones",),
    ),
)


def generar_nota_informacion_relevante(
    sector: str, segmento: str, intensidad: str, semilla: int, ejercicio: EjercicioEmpresa
) -> NotaMemoria:
    """Arquetipo 22 (comodín). `ejercicio` no se usa: ninguno de los 10 temas necesita una cifra
    de la empresa generada — se mantiene en la firma por consistencia con el resto del módulo."""
    del ejercicio
    rng = _rng_memoria(sector, segmento, intensidad, "informacion_relevante_memoria", semilla)
    indice = rng.integers(len(_NOTAS_COMODIN))
    texto, etiquetas = _NOTAS_COMODIN[indice]
    return NotaMemoria(arquetipo_id="informacion_relevante_memoria", numero=22, texto=texto, etiquetas=etiquetas)


# --------------------------------------------------------------------------------------------
# Despachador por arquetipo_id — ver docstring del módulo.
# --------------------------------------------------------------------------------------------

_GENERADORES = {
    "dependencia_pocos_clientes": generar_nota_dependencia_clientes,
    "activo_mantenido_venta": generar_nota_activo_mantenido_venta,
    "operaciones_vinculadas": generar_nota_operaciones_vinculadas,
    "coberturas": generar_nota_coberturas,
    "informacion_relevante_memoria": generar_nota_informacion_relevante,
}


def generar_nota_memoria_pura(
    arquetipo_id: str, sector: str, segmento: str, intensidad: str, semilla: int, ejercicio: EjercicioEmpresa
) -> NotaMemoria:
    """Despacha a la función concreta según `arquetipo_id` (uno de los 5 arquetipos de
    `clase="memoria_pura"` en data/arquetipos.json). Lanza KeyError si `arquetipo_id` no es
    ninguno de los 5 — igual de explícito que dejar que el lookup del dict falle."""
    return _GENERADORES[arquetipo_id](sector, segmento, intensidad, semilla, ejercicio)
