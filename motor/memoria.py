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

**Etiquetado temático y resolución de colisiones (combinación de arquetipos, sección 2.12).**
Cada `NotaMemoria` (definida en `motor.evolucion_arquetipo`, no aquí — la generan también los
arquetipos 10/16/18 de ese módulo, así que vive donde ambos la puedan importar sin dependencia
circular) lleva `etiquetas: tuple[str, ...]` — qué temas toca (p. ej. `("clientes",
"concentracion")`). Es un conjunto FIJO por arquetipo en 7/19/20/21 y en 10/16/18 (no varía
plantilla a plantilla), salvo en el 22 ("comodín narrativo"), donde cada una de las 10
redacciones trata un tema distinto y por tanto lleva su propia etiqueta.

Esto tiene una consecuencia importante para `resolver_colisiones_notas` (más abajo): la
"amortiguación eligiendo otra plantilla" solo puede evitar una colisión para un arquetipo cuyo
POOL de candidatos tenga etiquetas que varíen según la plantilla — hoy, únicamente el 22. Para
el resto (7/19/20/21/10/16/18), cambiar de plantilla no cambia sus etiquetas fijas, así que si
colisionan, colisionan pase lo que pase — no hay "otra opción" que probar (ni por diseño ni por
casualidad: comprobado programáticamente en `tests/test_combinacion_arquetipos.py`, no
solo revisado a mano). El algoritmo es el MISMO para los 8 arquetipos, sin ningún caso especial
en el código — la diferencia de comportamiento sale de los DATOS (qué pools tienen variedad de
etiquetas), no de una rama condicional para "el caso 7/22". Esto es deliberado y generaliza sin
tocar código: cualquier arquetipo futuro con un pool de etiquetas variables participará en la
resolución automáticamente; uno con etiquetas fijas seguirá sin tener "otra opción" que probar,
y esa ausencia de alternativa es, en sí misma, información para la futura matriz de
compatibilidad (sección 2.25) — qué parejas de arquetipos NUNCA deberían combinarse porque
comparten un tema sin salida.

**Formato de cifras en el texto**: importes en euros redondeados al millar más cercano,
porcentajes al entero más cercano — una memoria real no mostraría "34.728.193,47 €" ni
"47,3826 %", y una precisión falsa así sería, además, un candidato a "cifra absurda" percibida
por quien lea el caso.
"""

from __future__ import annotations

import zlib

import numpy as np

from motor.evolucion_arquetipo import EjercicioEmpresa, NotaMemoria


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


def _elegir_indice_evitando_colision(
    rng: np.random.Generator, etiquetas_por_indice: list[tuple[str, ...]], etiquetas_ya_usadas: frozenset[str]
) -> int:
    """Núcleo genérico de la resolución de colisiones (sección 2.12) — el MISMO para los 8
    arquetipos que generan notas (7/19/20/21/22 aquí, 10/16/18 en evolucion_arquetipo.py, que
    llaman a esta misma función). Baraja los índices posibles con `rng` (reproducible por
    semilla, no aleatorio en cada ejecución) y devuelve el primero cuyas etiquetas NO intersequen
    con `etiquetas_ya_usadas`. Si ninguno libra la colisión — incluidos los arquetipos con
    etiquetas FIJAS (7/19/20/21/10/16/18: `etiquetas_por_indice` repite la misma tupla en las N
    posiciones, así que o colisionan todas o ninguna) — se devuelve el primero del orden
    barajado igualmente: una nota redundante es preferible a bloquear la generación del caso, y
    es el mismo patrón ya establecido en todo el proyecto (señal honesta cuando no se puede
    corregir del todo, nunca un fallo silencioso ni una excepción que rompe el caso)."""
    orden = rng.permutation(len(etiquetas_por_indice))
    for indice in orden:
        if not (set(etiquetas_por_indice[indice]) & etiquetas_ya_usadas):
            return int(indice)
    return int(orden[0])


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
    sector: str,
    segmento: str,
    intensidad: str,
    semilla: int,
    ejercicio: EjercicioEmpresa,
    etiquetas_ya_usadas: frozenset[str] = frozenset(),
) -> NotaMemoria:
    """Arquetipo 7. `ejercicio` no se usa (la concentración se expresa en % de ventas, no en
    euros) — se mantiene en la firma por consistencia con el resto de funciones de este módulo
    y por si una plantilla futura quisiera citar la cifra de ventas absoluta. `etiquetas_ya_usadas`:
    ver `resolver_colisiones_notas` — las etiquetas de este arquetipo son FIJAS (no varían con
    la plantilla), así que no hay "otra opción" que probar si colisiona (ver docstring del
    módulo)."""
    del ejercicio
    rng = _rng_memoria(sector, segmento, intensidad, "dependencia_pocos_clientes", semilla)
    rango = RANGOS_CONCENTRACION_CLIENTES[intensidad]
    n_clientes = int(rng.integers(rango["clientes"][0], rango["clientes"][1] + 1))
    pct = round(rng.uniform(*rango["pct"]))
    etiquetas_por_indice = [("clientes", "concentracion")] * len(PLANTILLAS_DEPENDENCIA_CLIENTES)
    indice = _elegir_indice_evitando_colision(rng, etiquetas_por_indice, etiquetas_ya_usadas)
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
    sector: str,
    segmento: str,
    intensidad: str,
    semilla: int,
    ejercicio: EjercicioEmpresa,
    etiquetas_ya_usadas: frozenset[str] = frozenset(),
) -> NotaMemoria:
    """Arquetipo 19. `ejercicio` no se usa (el tipo de activo y el motivo son cualitativos, sin
    cifra asociada) — se mantiene en la firma por la misma razón que en el arquetipo 7.
    Etiquetas FIJAS — ver `generar_nota_dependencia_clientes`."""
    del ejercicio
    rng = _rng_memoria(sector, segmento, intensidad, "activo_mantenido_venta", semilla)
    etiquetas_por_indice = [("activo", "desinversion")] * len(PLANTILLAS_ACTIVO_MANTENIDO_VENTA)
    indice = _elegir_indice_evitando_colision(rng, etiquetas_por_indice, etiquetas_ya_usadas)
    texto = PLANTILLAS_ACTIVO_MANTENIDO_VENTA[indice]
    return NotaMemoria(arquetipo_id="activo_mantenido_venta", numero=19, texto=texto, etiquetas=("activo", "desinversion"))


# --------------------------------------------------------------------------------------------
# Arquetipo 20 — Operaciones vinculadas. Desde el segundo lote de desglose de balance, el
# arquetipo 20 es `clase="cuantitativo"` (promovido, mismo criterio que "coberturas" en el
# encargo de grupo 8/9): el sorteo de QUÉ operación y de QUÉ IMPORTE ya no ocurre aquí, sino en
# `motor.evolucion_arquetipo` (ver `ParametrosOperacionVinculada`/`_sortear_operacion_vinculada`),
# porque ese importe tiene que aterrizar en el balance (préstamo/financiación de grupo, o una
# sub-partida de deudores/acreedores comerciales), no solo en el texto de esta nota. Esta función
# se reduce a FORMATEAR el importe/% ya calculados y guardados en `EjercicioEmpresa` — nunca
# sortea nada de nuevo (mismo importe citado en la nota y aterrizado en el balance, requisito
# explícito de este lote: "no generar un número nuevo independiente").
# --------------------------------------------------------------------------------------------

# Cada entrada: plantilla con {importe}/{pct} — mismo orden que
# `motor.evolucion_arquetipo.TIPO_OPERACION_POR_INDICE` (el índice selecciona la misma entrada
# en ambos módulos).
_OPERACIONES_VINCULADAS = (
    "La sociedad mantiene con su empresa matriz un préstamo intragrupo por importe de "
    "{importe} euros, equivalente al {pct}% de su patrimonio neto a cierre del ejercicio, "
    "formalizado en condiciones de mercado según la política de precios de transferencia "
    "del grupo.",
    "Durante el ejercicio la sociedad ha facturado servicios de gestión a una sociedad del "
    "grupo por importe de {importe} euros, equivalente al {pct}% de la cifra de negocio del "
    "ejercicio.",
    "La sociedad satisface a uno de sus socios/administradores una renta anual de "
    "arrendamiento por el uso de un inmueble afecto a la actividad, por importe de "
    "{importe} euros, equivalente al {pct}% de la cifra de negocio del ejercicio.",
    "La sociedad ha recibido financiación de una sociedad del grupo por importe de "
    "{importe} euros, equivalente al {pct}% de su deuda financiera total a cierre del "
    "ejercicio, sin que se hayan devengado gastos financieros adicionales a los ya "
    "reconocidos en la cuenta de pérdidas y ganancias.",
    "La empresa matriz ha prestado a la sociedad servicios de asistencia técnica y "
    "administrativa por importe de {importe} euros durante el ejercicio, equivalente al "
    "{pct}% de la cifra de negocio, facturados en condiciones de mercado.",
)


def generar_nota_operaciones_vinculadas(ejercicio: EjercicioEmpresa) -> NotaMemoria:
    """Arquetipo 20 — formatea el importe/% YA calculados por `motor.evolucion_arquetipo` sobre
    `ejercicio` (normalmente el de 2025, igual que el resto de notas de memoria pura: ver
    `generar_caso_combinado`) — `ejercicio.operacion_vinculada_indice` selecciona la plantilla,
    `..._importe_eur`/`..._pct_mostrado` ya vienen topados/recalculados (ver docstring del
    bloque arriba). Requiere `ejercicio.operacion_vinculada_activa` — el llamador (
    `generar_caso_combinado`) solo la invoca cuando el arquetipo 20 está activo en el caso."""
    plantilla = _OPERACIONES_VINCULADAS[ejercicio.operacion_vinculada_indice]
    texto = plantilla.format(
        importe=_fmt_eur(ejercicio.operacion_vinculada_importe_eur), pct=_fmt_pct(ejercicio.operacion_vinculada_pct_mostrado)
    )
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
    sector: str,
    segmento: str,
    intensidad: str,
    semilla: int,
    ejercicio: EjercicioEmpresa,
    etiquetas_ya_usadas: frozenset[str] = frozenset(),
) -> NotaMemoria:
    """Arquetipo 21. El nocional se calcula como % (rango por intensidad) de la deuda financiera
    total real de la empresa generada — nunca un importe desconectado de cuánta deuda tiene la
    empresa que, en teoría, se está cubriendo. Topado por abajo en SUELO_NOCIONAL_COBERTURA_EUR;
    el `{pct}` mostrado se recalcula sobre el nocional ya topado, por la misma razón de
    consistencia interna que en `generar_nota_operaciones_vinculadas`. Etiquetas FIJAS — ver
    `generar_nota_dependencia_clientes`."""
    rng = _rng_memoria(sector, segmento, intensidad, "coberturas", semilla)
    rango_pct = RANGOS_COBERTURA_PCT_DEUDA[intensidad]
    pct_objetivo = rng.uniform(*rango_pct)
    deuda_financiera_total = ejercicio.balance_eur["deudas_fin_largo"] + ejercicio.balance_eur["deudas_fin_corto"]
    importe = max(deuda_financiera_total * pct_objetivo / 100, SUELO_NOCIONAL_COBERTURA_EUR)
    pct_mostrado = importe / deuda_financiera_total * 100
    etiquetas_por_indice = [("deuda", "cobertura_riesgo")] * len(PLANTILLAS_COBERTURAS)
    indice_plantilla = _elegir_indice_evitando_colision(rng, etiquetas_por_indice, etiquetas_ya_usadas)
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
    sector: str,
    segmento: str,
    intensidad: str,
    semilla: int,
    ejercicio: EjercicioEmpresa,
    etiquetas_ya_usadas: frozenset[str] = frozenset(),
) -> NotaMemoria:
    """Arquetipo 22 (comodín). `ejercicio` no se usa: ninguno de los 10 temas necesita una cifra
    de la empresa generada — se mantiene en la firma por consistencia con el resto del módulo.
    A diferencia de los otros 4 arquetipos de memoria pura, SUS etiquetas SÍ varían plantilla a
    plantilla — es el único arquetipo hoy donde `etiquetas_ya_usadas` puede cambiar de verdad
    qué tema se elige (ver docstring del módulo)."""
    del ejercicio
    rng = _rng_memoria(sector, segmento, intensidad, "informacion_relevante_memoria", semilla)
    etiquetas_por_indice = [etiquetas for _, etiquetas in _NOTAS_COMODIN]
    indice = _elegir_indice_evitando_colision(rng, etiquetas_por_indice, etiquetas_ya_usadas)
    texto, etiquetas = _NOTAS_COMODIN[indice]
    return NotaMemoria(arquetipo_id="informacion_relevante_memoria", numero=22, texto=texto, etiquetas=etiquetas)


# --------------------------------------------------------------------------------------------
# Despachador por arquetipo_id — ver docstring del módulo.
# --------------------------------------------------------------------------------------------

_GENERADORES = {
    "dependencia_pocos_clientes": generar_nota_dependencia_clientes,
    "activo_mantenido_venta": generar_nota_activo_mantenido_venta,
    "coberturas": generar_nota_coberturas,
    "informacion_relevante_memoria": generar_nota_informacion_relevante,
}


def generar_nota_memoria_pura(
    arquetipo_id: str,
    sector: str,
    segmento: str,
    intensidad: str,
    semilla: int,
    ejercicio: EjercicioEmpresa,
    etiquetas_ya_usadas: frozenset[str] = frozenset(),
) -> NotaMemoria:
    """Despacha a la función concreta según `arquetipo_id` (uno de los 4 arquetipos de
    `clase="memoria_pura"` en data/arquetipos.json: 7, 19, 21, 22 — el 20, "operaciones
    vinculadas", pasó a `clase="cuantitativo"` en el segundo lote de desglose de balance, ver
    `generar_nota_operaciones_vinculadas`/`generar_caso_combinado`). Lanza KeyError si
    `arquetipo_id` no es ninguno de los 4 — igual de explícito que dejar que el lookup del dict
    falle."""
    return _GENERADORES[arquetipo_id](sector, segmento, intensidad, semilla, ejercicio, etiquetas_ya_usadas)


def generar_caso_combinado(
    sector: str,
    segmento: str,
    ventas_objetivo_2023: float,
    semilla: int,
    arquetipos_intensidades: dict[str, str],
    catalogo=None,
    arquetipos=None,
):
    """Punto de entrada general para un caso con uno o varios arquetipos activos, de cualquier
    clase — orquesta `motor.evolucion_arquetipo.generar_evolucion_combinada` para los
    `clase="cuantitativo"` y las funciones de este módulo para los `clase="memoria_pura"`,
    resolviendo colisiones temáticas sobre el conjunto COMPLETO de notas resultantes (las de
    10/16/18 en `EjercicioEmpresa.notas_memoria`, si las hay, más las de 7/19/20/21/22), en orden
    de número de arquetipo — no solo por parejas (sección 2.12). Requiere al menos un arquetipo
    `cuantitativo` activo (necesario para tener una empresa de referencia sobre la que anclar los
    importes de 20/21); para generar un arquetipo de memoria pura en solitario sin ninguno
    numérico, usar `generar_nota_memoria_pura` directamente sobre una `EjercicioEmpresa` ya
    generada (p. ej. con cualquier arquetipo cuantitativo "neutro", como hace
    `tests/test_memoria.py`).

    Devuelve el `EvolucionArquetipo` de los arquetipos cuantitativos, con `notas_memoria_pura`
    ya poblado con las notas de los arquetipos de memoria pura (vacío si no hay ninguno activo)."""
    import dataclasses

    from motor.arquetipos import cargar_arquetipos
    from motor.catalogo import cargar_y_validar_catalogo
    from motor.evolucion_arquetipo import generar_evolucion_combinada

    if arquetipos is None:
        arquetipos = cargar_arquetipos()
    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    ids_cuantitativos = {aid: i for aid, i in arquetipos_intensidades.items() if arquetipos[aid].clase == "cuantitativo"}
    ids_memoria_pura = {aid: i for aid, i in arquetipos_intensidades.items() if arquetipos[aid].clase == "memoria_pura"}
    if not ids_cuantitativos:
        raise ValueError(
            "generar_caso_combinado requiere al menos un arquetipo cuantitativo activo — "
            "ver docstring de la función"
        )

    # "dependencia_pocos_clientes" (arquetipo 7) es `clase="memoria_pura"` — no evoluciona en
    # `generar_evolucion_combinada`, pero SÍ debe subir la probabilidad/magnitud del deterioro de
    # insolvencias de clientes (cuenta 490, motor/insolvencias.py) cuando está activo, igual que
    # el arquetipo 4 ("deterioro_ciclo_caja", ese sí `cuantitativo` y detectado internamente). Es
    # la única señal que este orquestador pasa a la evolución numérica sobre los arquetipos de
    # memoria pura — ver docstring de `sortear_insolvencia_baseline`.
    dependencia_pocos_clientes_activo = "dependencia_pocos_clientes" in ids_memoria_pura
    evolucion = generar_evolucion_combinada(
        sector,
        segmento,
        ventas_objetivo_2023,
        semilla,
        ids_cuantitativos,
        catalogo=catalogo,
        arquetipos=arquetipos,
        dependencia_pocos_clientes_activo=dependencia_pocos_clientes_activo,
    )

    # Etiquetas ya "ocupadas" por las notas numéricas (10/16/18, si las hay, en 2024 y/o 2025):
    # cuentan como ya usadas para las de memoria pura que se generan a continuación, en orden de
    # número de arquetipo — pero (ver docstring del módulo) esas notas numéricas YA están
    # comprometidas en este punto: si colisionan entre sí, no se pueden volver a sortear aquí
    # (eso ocurriría, como mucho, dentro de la propia evolución numérica — no pasa en los 6
    # combos recomendados, ninguno activa dos de 10/16/18 a la vez).
    etiquetas_usadas: set[str] = set()
    for ejercicio in evolucion.ejercicios.values():
        for nota in ejercicio.notas_memoria:
            etiquetas_usadas.update(nota.etiquetas)

    ejercicio_referencia = evolucion.ejercicios[2025]
    notas_memoria_pura: list[NotaMemoria] = []
    for arquetipo_id in sorted(ids_memoria_pura, key=lambda aid: arquetipos[aid].numero):
        nota = generar_nota_memoria_pura(
            arquetipo_id,
            sector,
            segmento,
            ids_memoria_pura[arquetipo_id],
            semilla,
            ejercicio_referencia,
            etiquetas_ya_usadas=frozenset(etiquetas_usadas),
        )
        notas_memoria_pura.append(nota)
        etiquetas_usadas.update(nota.etiquetas)

    # "coberturas" (21) es `clase="cuantitativo"` desde el encargo de coberturas/subvenciones
    # (dispara el ajuste numérico de PN vía EfectoCobertura, ver motor.evolucion_arquetipo) pero
    # SIGUE generando la nota de memoria cualitativa de siempre (motor.memoria.
    # generar_nota_coberturas) — no pasa por `ids_memoria_pura`, así que se añade aquí como caso
    # especial en vez de perder la nota. El % del nocional citado en la nota se sortea de forma
    # independiente del nocional realmente modelado en el balance (ver decisiones_
    # plausibilidad.md): ambos plausibles dentro del mismo rango, no forzados a coincidir.
    if "coberturas" in ids_cuantitativos:
        nota_cobertura = generar_nota_coberturas(
            sector,
            segmento,
            ids_cuantitativos["coberturas"],
            semilla,
            ejercicio_referencia,
            etiquetas_ya_usadas=frozenset(etiquetas_usadas),
        )
        notas_memoria_pura.append(nota_cobertura)
        etiquetas_usadas.update(nota_cobertura.etiquetas)

    # "operaciones_vinculadas" (20) es `clase="cuantitativo"` desde este segundo lote de
    # desglose de balance (mismo criterio que "coberturas" arriba): el importe/tipo de operación
    # ya se sortearon UNA vez dentro de `generar_evolucion_combinada` (ver
    # `ParametrosOperacionVinculada`) y quedaron aterrizados en el balance — aquí solo se
    # formatea la nota con ESE mismo importe (`generar_nota_operaciones_vinculadas` ya no
    # sortea nada, no necesita `etiquetas_ya_usadas`: las 5 plantillas comparten etiqueta fija,
    # así que no hay colisión que resolver eligiendo otra).
    if "operaciones_vinculadas" in ids_cuantitativos:
        nota_vinculadas = generar_nota_operaciones_vinculadas(ejercicio_referencia)
        notas_memoria_pura.append(nota_vinculadas)
        etiquetas_usadas.update(nota_vinculadas.etiquetas)

    notas_memoria_pura.sort(key=lambda n: n.numero)

    # Trazabilidad (sección 2.15) — hallazgo de auditoría: `evolucion.arquetipo`/`.intensidad`
    # solo reflejan `ids_cuantitativos` (así los calcula `generar_evolucion_combinada`, que no
    # conoce la clase `memoria_pura` en absoluto) — para un caso combinado con algún arquetipo de
    # memoria pura activo (7/19/22), esos 2 campos quedarían INCOMPLETOS como registro de "qué
    # arquetipos están activos en el caso". Se recalculan aquí, con el MISMO formato ya
    # establecido para combinaciones ("id1+id2", "id1:intensidad1+id2:intensidad2", orden
    # alfabético de id — igual criterio que `generar_evolucion_combinada`), pero sobre el
    # diccionario COMPLETO `arquetipos_intensidades` (ambas clases). Si no hay ningún arquetipo de
    # memoria pura activo, los campos quedan EXACTAMENTE igual que ya los devolvía
    # `generar_evolucion_combinada` (ningún caso ya existente cambia).
    if ids_memoria_pura:
        arquetipo_str = "+".join(sorted(arquetipos_intensidades))
        intensidad_str = "+".join(f"{aid}:{arquetipos_intensidades[aid]}" for aid in sorted(arquetipos_intensidades))
    else:
        arquetipo_str, intensidad_str = evolucion.arquetipo, evolucion.intensidad

    return dataclasses.replace(
        evolucion, notas_memoria_pura=tuple(notas_memoria_pura), arquetipo=arquetipo_str, intensidad=intensidad_str
    )
