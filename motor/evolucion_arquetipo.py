"""Evolución de una empresa a lo largo de 3 ejercicios (2023-2025) aplicando UN arquetipo.

Motor GENÉRICO: qué arquetipo se aplica es un dato (`data/arquetipos.json`, cargado por
`motor.arquetipos`), no código hardcodeado por arquetipo. Este módulo separa dos cosas:

- **Mecanismo general** (reutilizable para cualquier arquetipo cuantitativo que encaje en una
  de las 4 formas de efecto soportadas): modelo de continuidad año a año de un ratio, cascada
  de PyG, enlace deuda-interés, contención de plausibilidad del endeudamiento, cuadre del
  balance. Vive en funciones de este módulo que no mencionan ningún arquetipo por su nombre.
- **Lo específico de cada arquetipo**: qué variable mueve, en qué dirección y contra qué
  ratio ancla — vive SOLO en `data/arquetipos.json`, no en código.

No todos los arquetipos cuantitativos de la sección 2.24 encajan en las 4 formas ya
implementadas (masa_circulante, pyg_primitiva, apalancamiento, tesoreria) — ver el informe de
clasificación en el mensaje que acompaña a este commit para el detalle de cuáles sí y cuáles
necesitarían una forma nueva. Los arquetipos cualitativos puros (7, 19, 20, 21, 22) no pasan
por este mecanismo en absoluto.

Sin matriz de compatibilidad (combinación de varios arquetipos a la vez), sin EFE/ECPN
completos, sin dividendos.

Diseño del mecanismo (decisiones no explícitas en la fórmula general de la sección 2.24, que
había que fijar para poder implementar):

- **2023 es el único ejercicio que usa el catálogo + ruido** (vía `motor.empresa_base` tal
  cual). 2024 y 2025 no vuelven a sortear existencias/clientes/tesorería desde el catálogo:
  se derivan del ejercicio anterior + el efecto del arquetipo ese año.
- **Ventas**: si el arquetipo define su propio `rango_crecimiento_pleno` (solo el arquetipo 1,
  por ahora — es el único cuya huella incluye "Ventas" en la sección 2.24), se sortea una vez
  por empresa dentro de ese rango (según intensidad) y se escala por la fracción del año (60%
  en 2024, 100% en 2025), exactamente como antes. Si el arquetipo NO define uno (5, 9, 11, 15:
  ninguno tiene "Ventas" en su huella), la empresa sigue necesitando alguna trayectoria de
  ventas para tener una historia de varios años — se usa un crecimiento orgánico modesto fijo
  (`RANGO_CRECIMIENTO_ORGANICO`), sorteado una vez, SIN escalar por intensidad ni por fracción
  del año (no es el efecto del arquetipo, es solo el telón de fondo sobre el que actúa).
- **Ratios de continuidad (masa_circulante, pyg_primitiva)**: se mueven cada año un
  `intensidad_base x fracción_año` respecto al propio valor del año anterior de la empresa (no
  respecto al valor Huber directamente): se descartó anclar directamente al Huber del sector
  como haría la fórmula general de la sección 2.24 (`Valor_simulado = Huber x
  (1+intensidad*dirección)`) porque, al ser 2023 ya un sorteo con ruido propio, la distancia
  entre el ratio real de 2023 y el Huber del sector puede ser grande por simple variabilidad
  estadística — anclar ahí habría provocado un salto brusco en 2024 dominado por "volver a la
  media del sector" y no por el arquetipo. El valor Huber del sector se conserva como
  referencia de plausibilidad (suelo/techo defensivo), no como objetivo al que saltar.
- **Tesorería y deuda a corto**: el resto de las masas del balance (inmovilizado, patrimonio
  neto vía resultado retenido, deuda a largo, otras partidas de pasivo corriente) crecen en
  línea con las ventas. La diferencia entre ese crecimiento "neutro" de existencias+clientes
  y el crecimiento real (mayor, si el arquetipo las toca) es la "NOF extra" del año: se resta
  primero de la tesorería; si la tesorería no basta, el resto se cubre con deuda a corto nueva.
- **Patrimonio neto**: PN(año) = PN(año-1) + resultado del ejercicio(año) − lo que financie el
  efecto "apalancamiento" ese año (ver más abajo), sin más dividendos (hasta que exista ECPN).
- **Cuadre final**: el ajuste sobre "otras deudas a corto plazo" es el mecanismo habitual de
  cuadre en 2024 y 2025 (no una excepción rara como en `empresa_base.py`): cada masa evoluciona
  con su propia regla y no hay renormalización conjunta, así que el plug absorbe la diferencia
  residual cada año — incluida la pequeña aproximación de segundo orden del efecto
  "apalancamiento" (ver abajo).

- **Control de plausibilidad del endeudamiento.** Cuando el déficit de caja se traslada a
  deudas financieras a corto plazo, se comprueba el endeudamiento resultante (pasivo
  total/activo total) contra `ratios.endeudamiento.huber_9y + 3 x huber_scale_mad` del sector.
  Si lo superaría, NO se deja crecer la deuda sin límite: se amortigua el propio exceso de las
  masas de circulante que el arquetipo haya tocado (en el orden en que aparecen en su
  definición), limitado como máximo a revertir el exceso por encima del crecimiento
  proporcional a ventas — nunca por debajo. El patrimonio neto no se toca como palanca de
  contención: con el activo fijado por el arquetipo, la identidad contable Activo = PN + Pasivo
  implica endeudamiento = 1 − PN/Activo — bajar el PN, con el activo fijo, exige MÁS pasivo, no
  menos (se verificó derivando la identidad a mano antes de implementar). Si el arquetipo no
  toca ninguna masa de circulante (9, 11, 15), no hay nada que amortiguar: el caso queda
  marcado igualmente (`riesgo_endeudamiento=True`, `contencion_al_limite=True`,
  `deterioro_aplicado_eur=0.0`) como señal, sin poder corregirse por esta vía.
  Es un punto fijo (menos deuda -> menos interés -> más PN -> hace falta amortiguar menos), no
  una fórmula cerrada de una sola pasada: se itera acotado (`MAX_ITERACIONES_CONTENCION`).

- **Gastos financieros = deuda financiera media x tipo de interés del sector**, no un % de PyG
  sorteado de forma independiente (ver `motor.empresa_base._generar_pyg_hasta_baii` /
  `_completar_pyg_con_deuda`). La deuda financiera media de un ejercicio es el promedio entre
  el saldo de deudas financieras (largo + corto plazo) al inicio y al final del propio
  ejercicio. Esto crea una dependencia circular con la contención de endeudamiento (la deuda
  financiera final depende de si hay contención, contener depende del PN, el PN depende de los
  gastos financieros, que dependen de la deuda financiera final): se resuelve evaluando primero
  el escenario sin contener (deuda, interés, resultado, PN, balance ya cuadrado) y, solo si
  hace falta contener, reevaluando el escenario completo con las cifras ya amortiguadas — sin
  reabrir la decisión de contención.

- **Arquetipo 9 (apalancamiento) — mecanismo específico, no una forma más del molde genérico
  de "ratio de continuidad".** Sube el endeudamiento objetivo (continuidad desde el propio
  endeudamiento del año anterior, topado al mismo techo de plausibilidad de la sección
  anterior) y resuelve en forma cerrada (sin iterar: ni el activo ni el pasivo "base" dependen
  del interés) cuánta deuda financiera a largo plazo extra (W) hace falta para llegar a ese
  endeudamiento objetivo, dado el activo y el resto del pasivo de ese ejercicio. Esa W se suma
  a deudas_fin_largo, y se resta de patrimonio neto — la deuda nueva financia una distribución,
  no una compra de activo (si no se restara del PN, el plug general de cuadre simplemente
  movería la misma W desde "otras deudas a corto" a "deudas a largo": el endeudamiento total no
  cambiaría nada, solo la composición de la deuda — se detectó exactamente así al derivar la
  identidad contable antes de implementar). La W calculada ignora el pequeño efecto de segundo
  orden de que la deuda nueva también sube el gasto financiero (y por tanto baja algo más el
  PN de lo que la fórmula asume): se deja que el plug de cuadre general absorba ese residuo,
  igual que ya hace con otras aproximaciones de este módulo. La distribución nunca reparte más
  PN del que hay ese ejercicio (`apalancamiento_extra_eur` se topa a `max(0, PN antes de
  distribuir)`), pero esto NO impide que el PN acabe en negativo en ejercicios posteriores por
  pérdidas normales: el interés de la deuda ya acumulada de un año sube el gasto financiero del
  siguiente, y si el resultado operativo de ese año es débil (sector volátil + sorteo de base
  ya débil), el PN puede erosionarse hasta negativo sin que haya una distribución nueva ese
  año. Verificado en pruebas de estrés: ocurre en 4 de 3.000 combinaciones (todas del mismo
  sector pequeño y volátil, Restaurantes). No se trata como valor absurdo — a diferencia de una
  masa físicamente imposible (existencias negativas), un patrimonio neto negativo es un estado
  contable real (empresa descapitalizada) — pero es una limitación a tener presente: este
  modelo mínimo no marca todavía una alerta de insolvencia/continuidad para ese caso.

  **Efecto de segundo año — "espiral de deuda" (detectado en pruebas, no buscado a propósito;
  SÍ se detecta y se señaliza, aunque no siempre se pueda corregir del todo).** El interés de
  la deuda YA acumulada de un año anterior sigue devengando en los siguientes: si ese interés
  es alto (deuda grande) y el resultado operativo del año es flojo, el PN crece poco o
  retrocede, mientras el resto del pasivo (que sí crece con ventas, incluida la propia deuda
  heredada) no se frena — el endeudamiento de un año puede acabar por encima del techo sin que
  se añada ni un euro de deuda nueva ESE año (`apalancamiento_extra_eur=0`). La comprobación de
  plausibilidad de endeudamiento (ver más arriba) se ejecuta SIEMPRE, no solo cuando hay
  déficit de NOF o deuda nueva de apalancamiento ese año concreto — así que este caso sí se
  detecta (`riesgo_endeudamiento=True`). Lo que NO puede es corregirlo por la vía habitual: el
  arquetipo "apalancamiento" no toca ninguna masa de circulante, así que no hay nada que
  amortiguar (`contencion_al_limite=True`, `deterioro_aplicado_eur=0`) — queda marcado como
  caso de riesgo, no arreglado en silencio. Corregirlo de verdad exigiría tocar el patrimonio
  neto como palanca, que ya se ha descartado por la misma razón de siempre (empeoraría el
  propio ratio que se quiere contener). Es una "espiral de deuda" real (el interés de la deuda
  existente erosiona el patrimonio, empeorando el ratio sin decisión nueva alguna) — coherente
  con lo que le pasa a una empresa realmente sobreapalancada, aunque no era el objetivo
  explícito de este arquetipo. Cuantificado en pruebas de estrés (1.296 combinaciones del
  arquetipo, sector x segmento x intensidad x semilla): 130 (10%) terminan 2025 con un
  patrimonio neto por debajo del 15% del activo partiendo de una base sana en 2023 (>=15% en
  2023) — los 130 quedan señalizados por esta vía, 0 pasan desapercibidos.

- **Techo/suelo de plausibilidad sectorial para subtotales de PyG (arquetipo 11 y cualquier
  otro efecto pyg_primitiva futuro).** El suelo/techo que ya tenía la propia primitiva
  (`FRACCION_MINIMA/MAXIMA_VS_HUBER`, frente al Huber de LA MISMA variable, p. ej.
  `pyg.consumos_explotacion_pct`) no acota de forma realista lo que le pasa al SUBTOTAL que esa
  primitiva alimenta (`pyg.margen_bruto_pct`): son columnas del catálogo distintas, con Huber y
  MAD propios — el margen bruto puede rebasar su propio techo sectorial mucho antes de que la
  primitiva llegue al suyo. Medido en pruebas de estrés (mismo método que con el arquetipo 9):
  de 2.592 ejercicios evaluados del arquetipo "mejora_margen" (1.296 combinaciones x 2 años),
  **1.796 (69%) superaban huber_9y + 3·MAD de `margen_bruto` del sector sin ninguna señal** — ya
  en intensidad "leve" (no hacía falta "fuerte" para desbordarlo). Corregido con
  `_limitar_por_subtotal`: además del suelo/techo de la propia primitiva, se calcula qué
  subtotal alimenta (`SUBTOTAL_PYG_DE_PRIMITIVA`, mapeo estructural de la cascada, no dato de
  arquetipo) y se topa el objetivo de la primitiva para que ESE subtotal no rebase su propio
  huber_9y +/- N·MAD. Solo válido hoy para relaciones "subtotal = 100 − primitiva" (la única
  que existe: margen_bruto = ingresos_explotacion(100) − consumos_explotacion) — no hacía falta
  ningún punto fijo ni iteración, a diferencia del endeudamiento: aquí no hay dependencia
  circular con la deuda/interés, así que se resuelve con una sola operación algebraica. El caso
  queda marcado (`riesgo_plausibilidad_pyg=True`, `pyg_subtotales_sin_contener` con el valor
  antes de topar) igual que el resto de contenciones de este módulo. Verificado tras el fix: 0
  de 2.592 ejercicios por encima del techo, y los 1.796 que antes pasaban desapercibidos quedan
  ahora señalizados exactamente.

- **Arquetipo 15 (riesgo de liquidez pese a beneficio) — limitación documentada.** Se decidió
  tras probarlo que SÍ encaja en el mecanismo general si se modela como "la tesorería (variable
  `disponible`) crece por debajo de lo proporcional a ventas, un intensidad_efectiva" —
  reutiliza el pipeline de déficit/deuda ya existente sin cambios (la tesorería más baja de lo
  normal simplemente hace más probable que aparezca déficit, financiado con deuda a corto,
  exactamente el mecanismo que ya había). El resultado del ejercicio no se toca en absoluto
  (sigue la cascada de PyG normal), lo que produce justo la divergencia "beneficio sano, caja
  tensa" de la huella del arquetipo. La limitación real: `ratios.tesoreria` del catálogo es
  (realizable+disponible)/pasivo_corriente (se comprobó numéricamente contra las masas del
  balance), no disponible/ventas — que es la unidad que usa esta implementación, por
  consistencia con existencias/realizable y para no tener que mover realizable también (lo que
  reabriría el problema de "dos variables a la vez"). Por eso este efecto NO usa el Huber de
  `ratios.tesoreria` como suelo/techo de plausibilidad (las unidades no son comparables): solo
  el suelo genérico de "disponible no puede ser negativo" que ya tenía el pipeline general.

- **Trazabilidad (sección 2.15).** `EvolucionArquetipo` guarda `arquetipo`, `intensidad`,
  `semilla`, `catalogo_version` (hash del CSV del catálogo usado — se deriva del propio
  archivo, no de un número mantenido a mano) y `pgc_version` (fijo por ahora: solo hay una
  versión normativa en juego). Falta la versión normativa "de verdad" variable y el ID del
  caso/variante — se añadirán cuando exista un repositorio de casos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from motor.arquetipos import (
    DefinicionArquetipo,
    EfectoApalancamiento,
    EfectoMasaCirculante,
    EfectoPygPrimitiva,
    EfectoTesoreria,
    cargar_arquetipos,
)
from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import (
    TOLERANCIA_CUADRE_EUR,
    EmpresaBase,
    EmpresaBaseError,
    generar_empresa_base,
    resolver_fila_sector,
)
from motor.empresa_base import _completar_pyg_con_deuda, _generar_pyg_hasta_baii  # reutiliza la cascada de PyG

AÑOS = (2023, 2024, 2025)
AÑO_BASE = 2023

# Trazabilidad (sección 2.15): única versión normativa en juego por ahora.
PGC_VERSION = "PGC RD 1514/2007"

INTENSIDADES_VALIDAS = frozenset({"leve", "moderado", "fuerte"})
INTENSIDAD_BASE = {"leve": 0.15, "moderado": 0.30, "fuerte": 0.50}
FRACCION_AÑO = {2024: 0.6, 2025: 1.0}

# Crecimiento de ventas para arquetipos que no definen su propio rango_crecimiento_pleno (ver
# docstring del módulo). Fijo, no escalado por intensidad ni por fracción del año.
RANGO_CRECIMIENTO_ORGANICO = (0.01, 0.04)

DIAS_AÑO = 365.0

# Suelo/techo defensivo frente al valor Huber del sector para cualquier ratio de continuidad
# (masa_circulante, pyg_primitiva). Evita valores absurdos en casos extremos; en escenarios
# moderado/fuerte normales no debería llegar a activarse casi nunca.
FRACCION_MINIMA_VS_HUBER = 0.10
FRACCION_MAXIMA_VS_HUBER = 3.0

# Techo de plausibilidad del endeudamiento: huber_9y + N desviaciones (huber_scale_mad) del
# sector, recortado a este tope absoluto. Además de evitar que la fórmula de contención (que
# divide por 1-techo_endeudamiento) degenere si un sector tuviera huber+N*mad >= 1, es un
# límite de capitalización mínima razonable: 0.85 de endeudamiento equivale a un patrimonio
# neto de solo el 15% del activo. Se bajó de 0,95 (un valor puesto solo por la razón numérica
# de arriba, sin calibrar como límite económico) tras comprobar en pruebas de estrés que 26 de
# 1.296 combinaciones del arquetipo "apalancamiento" quedaban con PN/Activo por debajo del 15%
# en 2025 sin que el mecanismo de contención llegara a activarse — precisamente porque, para
# los sectores cuyo huber+3mad ya supera 0,95, el endeudamiento real (0,85-0,95) quedaba
# "dentro" de ese techo tan laxo.
N_DESVIACIONES_TECHO_ENDEUDAMIENTO = 3.0
TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO = 0.85

# La contención de endeudamiento es un punto fijo (menos deuda -> menos interés -> más PN ->
# hace falta amortiguar menos), no una fórmula cerrada de una sola pasada: se itera acotado.
MAX_ITERACIONES_CONTENCION = 50
TOLERANCIA_CONVERGENCIA_DETERIORO_EUR = 1.0

# Techo/suelo de plausibilidad sectorial para subtotales de la PyG que un efecto pyg_primitiva
# pueda empujar de forma acumulativa (mismo método que el techo de endeudamiento: huber_9y +/-
# N desviaciones del catálogo). Se añadió tras comprobar en pruebas de estrés que, sin él, el
# suelo/techo de FRACCION_MINIMA/MAXIMA_VS_HUBER sobre la propia primitiva (consumos_explotacion)
# no acota de forma realista el subtotal derivado (margen_bruto): 1.796 de 2.592 ejercicios
# evaluados del arquetipo "mejora_margen" (69%) superaban huber+3*MAD de margen_bruto del
# sector sin ninguna señal — ya en intensidad "leve".
N_DESVIACIONES_TECHO_PYG = 3.0

# Mapeo ESTRUCTURAL (no específico de ningún arquetipo, no es dato de data/arquetipos.json): a
# qué subtotal de la cascada de PyG (motor.empresa_base._completar_pyg_con_deuda) alimenta de
# forma directa cada primitiva, para poder acotar ESE subtotal a su propio techo/suelo
# sectorial — no solo el de la propia primitiva. Vive en el motor, no en los datos, porque es
# una propiedad fija de la fórmula de la cascada (margen_bruto = ingresos_explotacion -
# consumos_explotacion), no una elección del arquetipo. Ampliar aquí, no en el JSON, cuando se
# implementen arquetipos que toquen otras primitivas con un subtotal directo claro (p. ej.
# gastos_personal/amortizaciones -> baii para el arquetipo 10 "mejora de EBITDA").
SUBTOTAL_PYG_DE_PRIMITIVA = {
    "consumos_explotacion": "margen_bruto",
}


class EvolucionArquetipoError(ValueError):
    """Parámetros de entrada inválidos."""


@dataclass(frozen=True)
class EjercicioEmpresa:
    año: int
    ventas: float
    crecimiento_ventas: float | None  # None en el año base (2023)
    balance_eur: dict[str, float]
    pyg_eur: dict[str, float]
    pyg_pct: dict[str, float]
    modos: dict[str, str]
    ajuste_cuadre_eur: float
    deuda_extra_por_nof_eur: float  # 0.0 salvo cuando la tesorería no basta para absorber la NOF
    endeudamiento: float  # pasivo total / activo total, ya con cualquier contención aplicada
    cobertura_gastos_financieros: float  # BAII / gastos financieros
    riesgo_endeudamiento: bool = False
    endeudamiento_sin_contener: float | None = None  # solo si riesgo_endeudamiento=True
    deterioro_aplicado_eur: float = 0.0  # exceso de circulante amortiguado por plausibilidad
    contencion_al_limite: bool = False  # True si no se pudo llegar al techo (nada que amortiguar, o se agotó)
    apalancamiento_extra_eur: float = 0.0  # deuda a largo extra por el efecto "apalancamiento", si lo hay
    riesgo_plausibilidad_pyg: bool = False  # True si algún efecto pyg_primitiva topó el techo/suelo de su subtotal
    pyg_subtotales_sin_contener: dict[str, float] = field(default_factory=dict)  # {subtotal: valor antes de topar}

    @property
    def rotacion_existencias(self) -> float:
        return self.ventas / self.balance_eur["existencias"]

    @property
    def cobro_dias(self) -> float:
        return self.balance_eur["realizable"] / self.ventas * DIAS_AÑO


@dataclass(frozen=True)
class EvolucionArquetipo:
    sector_codigo: str
    sector_nombre: str
    segmento: str
    arquetipo: str
    intensidad: str
    semilla: int
    crecimiento_pleno_objetivo: float
    ejercicios: dict[int, EjercicioEmpresa]
    catalogo_version: str  # hash del CSV del catálogo usado para generar el caso (sección 2.15)
    pgc_version: str = PGC_VERSION


def _endeudamiento(balance_eur: dict[str, float]) -> float:
    activo_total = balance_eur["activo_no_corriente"] + balance_eur["activo_corriente"]
    pasivo_total = balance_eur["pasivo_no_corriente"] + balance_eur["pasivo_corriente"]
    return pasivo_total / activo_total


def _cobertura_gastos_financieros(pyg_eur: dict[str, float]) -> float:
    gastos_financieros_eur = pyg_eur["gastos_financieros"]
    if gastos_financieros_eur <= 0:
        return float("inf")
    return pyg_eur["baii"] / gastos_financieros_eur


def _ejercicio_desde_empresa_base(empresa: EmpresaBase) -> EjercicioEmpresa:
    return EjercicioEmpresa(
        año=AÑO_BASE,
        ventas=empresa.ventas_objetivo,
        crecimiento_ventas=None,
        balance_eur=dict(empresa.balance_eur),
        pyg_eur=dict(empresa.pyg_eur),
        pyg_pct=dict(empresa.pyg_pct),
        modos=dict(empresa.modos),
        ajuste_cuadre_eur=empresa.ajuste_cuadre_eur,
        deuda_extra_por_nof_eur=0.0,
        endeudamiento=_endeudamiento(empresa.balance_eur),
        cobertura_gastos_financieros=_cobertura_gastos_financieros(empresa.pyg_eur),
    )


# --------------------------------------------------------------------------------------------
# Mecanismo general: mover un ratio un intensidad_efectiva respecto a su propio valor anterior.
# --------------------------------------------------------------------------------------------


def _mover_ratio_continuo(valor_anterior: float, direccion: int, intensidad_efectiva: float, huber: float) -> float:
    """Desplaza un ratio un `intensidad_efectiva` respecto a su propio valor del año anterior,
    con suelo/techo de plausibilidad frente al Huber del sector (nunca el objetivo en sí — ver
    docstring del módulo)."""
    nuevo = valor_anterior * (1 + direccion * intensidad_efectiva)
    if direccion < 0:
        return max(nuevo, FRACCION_MINIMA_VS_HUBER * huber)
    return min(nuevo, FRACCION_MAXIMA_VS_HUBER * huber)


def _masa_circulante_objetivo(
    efecto: EfectoMasaCirculante, anterior: EjercicioEmpresa, ventas: float, fila: pd.Series, intensidad_efectiva: float
) -> float:
    huber = fila[f"{efecto.ratio_catalogo}.huber_9y"]
    if efecto.formula == "rotacion":
        ratio_anterior = anterior.ventas / anterior.balance_eur[efecto.variable]
        nuevo_ratio = _mover_ratio_continuo(ratio_anterior, efecto.direccion, intensidad_efectiva, huber)
        return ventas / nuevo_ratio
    ratio_anterior = anterior.balance_eur[efecto.variable] / anterior.ventas * DIAS_AÑO
    nuevo_ratio = _mover_ratio_continuo(ratio_anterior, efecto.direccion, intensidad_efectiva, huber)
    return nuevo_ratio / DIAS_AÑO * ventas


def _pyg_primitiva_objetivo(
    efecto: EfectoPygPrimitiva, anterior: EjercicioEmpresa, fila: pd.Series, intensidad_efectiva: float
) -> float:
    huber = fila[f"{efecto.ratio_catalogo}.huber_9y"]
    valor_anterior = anterior.pyg_pct[efecto.primitiva]
    return _mover_ratio_continuo(valor_anterior, efecto.direccion, intensidad_efectiva, huber)


def _limitar_por_subtotal(
    primitiva: str, valor_objetivo: float, fila: pd.Series, direccion: int
) -> tuple[float, str | None, float | None]:
    """Si `primitiva` alimenta un subtotal de la cascada de PyG (SUBTOTAL_PYG_DE_PRIMITIVA),
    topa `valor_objetivo` para que ESE subtotal no rebase su propio techo/suelo de
    plausibilidad sectorial (huber_9y +/- N desviaciones) — no solo el de la propia primitiva
    (que usa el Huber de otra variable del catálogo y en la práctica no acota nada realista:
    ver docstring del módulo). Solo válido para relaciones "subtotal = 100 - primitiva"
    (la única que existe hoy: margen_bruto = ingresos_explotacion(100) - consumos_explotacion).

    Devuelve (valor_final, nombre_subtotal_si_se_activó, valor_sin_contener_del_subtotal)."""
    subtotal = SUBTOTAL_PYG_DE_PRIMITIVA.get(primitiva)
    if subtotal is None:
        return valor_objetivo, None, None

    huber_subtotal = fila[f"pyg.{subtotal}_pct.huber_9y"]
    mad_subtotal = fila[f"pyg.{subtotal}_pct.huber_scale_mad"]
    subtotal_sin_contener = 100.0 - valor_objetivo

    if direccion < 0:
        # La primitiva baja => el subtotal (100 - primitiva) sube: topar el subtotal a su
        # techo equivale a ponerle un SUELO a la propia primitiva.
        techo_subtotal = huber_subtotal + N_DESVIACIONES_TECHO_PYG * mad_subtotal
        if subtotal_sin_contener <= techo_subtotal:
            return valor_objetivo, None, None
        return 100.0 - techo_subtotal, subtotal, subtotal_sin_contener
    else:
        suelo_subtotal = huber_subtotal - N_DESVIACIONES_TECHO_PYG * mad_subtotal
        if subtotal_sin_contener >= suelo_subtotal:
            return valor_objetivo, None, None
        return 100.0 - suelo_subtotal, subtotal, subtotal_sin_contener


def _disponible_proporcional_con_efecto(
    efecto: EfectoTesoreria | None, disponible_proporcional_eur: float, intensidad_efectiva: float
) -> float:
    if efecto is None:
        return disponible_proporcional_eur
    factor = max(0.0, 1 + efecto.direccion * intensidad_efectiva)
    return disponible_proporcional_eur * factor


def _evolucionar_un_año(
    año: int,
    anterior: EjercicioEmpresa,
    fila: pd.Series,
    rng_pyg: np.random.Generator,
    crecimiento_ventas: float,
    intensidad_efectiva: float,
    definicion: DefinicionArquetipo,
) -> EjercicioEmpresa:
    ventas = anterior.ventas * (1 + crecimiento_ventas)

    efectos_masa_circulante = [e for e in definicion.efectos if isinstance(e, EfectoMasaCirculante)]
    efectos_pyg = [e for e in definicion.efectos if isinstance(e, EfectoPygPrimitiva)]
    efectos_apalancamiento = [e for e in definicion.efectos if isinstance(e, EfectoApalancamiento)]
    efectos_tesoreria = [e for e in definicion.efectos if isinstance(e, EfectoTesoreria)]
    efecto_tesoreria = efectos_tesoreria[0] if efectos_tesoreria else None

    # --- Masas de circulante: proporcional a ventas por defecto, desviadas si el arquetipo
    # las toca (existencias/realizable son las únicas variables soportadas por ahora). ---
    variables_circulante = {"existencias": anterior.balance_eur["existencias"], "realizable": anterior.balance_eur["realizable"]}
    proporcional_circulante = {
        variable: valor * (1 + crecimiento_ventas) for variable, valor in variables_circulante.items()
    }
    objetivos_circulante = dict(proporcional_circulante)
    for efecto in efectos_masa_circulante:
        objetivos_circulante[efecto.variable] = _masa_circulante_objetivo(efecto, anterior, ventas, fila, intensidad_efectiva)
    existencias_eur = objetivos_circulante["existencias"]
    realizable_eur = objetivos_circulante["realizable"]
    existencias_proporcional_eur = proporcional_circulante["existencias"]
    realizable_proporcional_eur = proporcional_circulante["realizable"]

    # --- Resto de masas: crecen en línea con las ventas (patrimonio neto se trata aparte) ---
    activo_no_corriente_eur = anterior.balance_eur["activo_no_corriente"] * (1 + crecimiento_ventas)
    deudas_fin_largo_proporcional_eur = anterior.balance_eur["deudas_fin_largo"] * (1 + crecimiento_ventas)
    otras_deudas_largo_eur = anterior.balance_eur["otras_deudas_largo"] * (1 + crecimiento_ventas)
    acreedores_comerciales_eur = anterior.balance_eur["acreedores_comerciales"] * (1 + crecimiento_ventas)
    otras_deudas_corto_eur = anterior.balance_eur["otras_deudas_corto"] * (1 + crecimiento_ventas)
    deudas_fin_corto_proporcional_eur = anterior.balance_eur["deudas_fin_corto"] * (1 + crecimiento_ventas)
    disponible_proporcional_eur = _disponible_proporcional_con_efecto(
        efecto_tesoreria, anterior.balance_eur["disponible"] * (1 + crecimiento_ventas), intensidad_efectiva
    )
    deuda_financiera_inicio_eur = anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"]

    # --- PyG: primitivas no financieras + tipo de interés, sorteadas UNA sola vez. Las que el
    # arquetipo toca (efecto pyg_primitiva) se fuerzan por continuidad en vez de sortearse, y
    # además se topan para que el subtotal que alimentan no rebase su propio techo/suelo de
    # plausibilidad sectorial (ver _limitar_por_subtotal). ---
    primitivas_forzadas: dict[str, float] = {}
    riesgo_plausibilidad_pyg = False
    pyg_subtotales_sin_contener: dict[str, float] = {}
    for efecto in efectos_pyg:
        objetivo = _pyg_primitiva_objetivo(efecto, anterior, fila, intensidad_efectiva)
        objetivo, subtotal_topado, subtotal_sin_contener = _limitar_por_subtotal(
            efecto.primitiva, objetivo, fila, efecto.direccion
        )
        primitivas_forzadas[efecto.primitiva] = objetivo
        if subtotal_topado is not None:
            riesgo_plausibilidad_pyg = True
            pyg_subtotales_sin_contener[subtotal_topado] = subtotal_sin_contener
    parcial_pyg = _generar_pyg_hasta_baii(rng_pyg, fila, ventas, primitivas_forzadas=primitivas_forzadas)

    def _deficit_y_deuda_corto(existencias_eur: float, realizable_eur: float) -> tuple[float, float, float]:
        nof_extra_eur = max(0.0, existencias_eur - existencias_proporcional_eur) + max(
            0.0, realizable_eur - realizable_proporcional_eur
        )
        disponible_bruto_eur = disponible_proporcional_eur - nof_extra_eur
        if disponible_bruto_eur >= 0:
            disponible_eur = disponible_bruto_eur
            deuda_extra_por_nof_eur = 0.0
        else:
            disponible_eur = 0.0
            deuda_extra_por_nof_eur = -disponible_bruto_eur
        deudas_fin_corto_eur = deudas_fin_corto_proporcional_eur + deuda_extra_por_nof_eur
        return disponible_eur, deudas_fin_corto_eur, deuda_extra_por_nof_eur

    def _construir_balance(
        existencias_eur: float,
        realizable_eur: float,
        disponible_eur: float,
        deudas_fin_corto_eur: float,
        deudas_fin_largo_eur: float,
        patrimonio_neto_eur: float,
    ) -> tuple[dict[str, float], float]:
        balance = {
            "activo_no_corriente": activo_no_corriente_eur,
            "activo_corriente": existencias_eur + realizable_eur + disponible_eur,
            "existencias": existencias_eur,
            "realizable": realizable_eur,
            "disponible": disponible_eur,
            "patrimonio_neto": patrimonio_neto_eur,
            "pasivo_no_corriente": deudas_fin_largo_eur + otras_deudas_largo_eur,
            "deudas_fin_largo": deudas_fin_largo_eur,
            "otras_deudas_largo": otras_deudas_largo_eur,
            "pasivo_corriente": acreedores_comerciales_eur + deudas_fin_corto_eur + otras_deudas_corto_eur,
            "acreedores_comerciales": acreedores_comerciales_eur,
            "deudas_fin_corto": deudas_fin_corto_eur,
            "otras_deudas_corto": otras_deudas_corto_eur,
        }

        activo_total_eur = balance["activo_no_corriente"] + balance["activo_corriente"]
        pn_pasivo_total_eur = balance["patrimonio_neto"] + balance["pasivo_no_corriente"] + balance["pasivo_corriente"]
        diferencia_cuadre = activo_total_eur - pn_pasivo_total_eur
        ajuste_cuadre_eur = 0.0
        if abs(diferencia_cuadre) > TOLERANCIA_CUADRE_EUR:
            ajuste_cuadre_eur = diferencia_cuadre
            otras_deudas_corto_ajustado = balance["otras_deudas_corto"] + diferencia_cuadre
            if otras_deudas_corto_ajustado < 0:
                # El cuadre pediría dejar "otras deudas a corto" en negativo (valor absurdo):
                # el exceso de patrimonio neto + pasivo sobre el activo se trata como caja de
                # más en vez de como una deuda negativa. Red de seguridad barata.
                remanente = -otras_deudas_corto_ajustado
                balance["otras_deudas_corto"] = 0.0
                balance["disponible"] += remanente
                balance["activo_corriente"] += remanente
            else:
                balance["otras_deudas_corto"] = otras_deudas_corto_ajustado
            balance["pasivo_corriente"] = (
                balance["acreedores_comerciales"] + balance["deudas_fin_corto"] + balance["otras_deudas_corto"]
            )

        return balance, ajuste_cuadre_eur

    def _evaluar(
        existencias_eur: float, realizable_eur: float, extra_deuda_largo_eur: float = 0.0
    ) -> tuple[dict[str, float], float, float, dict[str, float], dict[str, float]]:
        """Evalúa un escenario de forma autoconsistente: la deuda financiera final de ESE
        escenario (incluida la extra por apalancamiento, si la hay) determina sus propios
        gastos financieros. `extra_deuda_largo_eur` financia una distribución a PN por el
        mismo importe (ver docstring del módulo, sección "Arquetipo 9")."""
        disponible_eur, deudas_fin_corto_eur, deuda_extra_por_nof_eur = _deficit_y_deuda_corto(
            existencias_eur, realizable_eur
        )
        deudas_fin_largo_eur = deudas_fin_largo_proporcional_eur + extra_deuda_largo_eur
        deuda_financiera_fin_eur = deudas_fin_largo_eur + deudas_fin_corto_eur
        deuda_financiera_media_eur = (deuda_financiera_inicio_eur + deuda_financiera_fin_eur) / 2
        pyg_pct, pyg_eur = _completar_pyg_con_deuda(parcial_pyg, deuda_financiera_media_eur)
        patrimonio_neto_eur = (
            anterior.balance_eur["patrimonio_neto"] + pyg_eur["resultado_ejercicio"] - extra_deuda_largo_eur
        )
        balance, ajuste_cuadre_eur = _construir_balance(
            existencias_eur, realizable_eur, disponible_eur, deudas_fin_corto_eur, deudas_fin_largo_eur, patrimonio_neto_eur
        )
        return balance, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur

    huber_endeudamiento = fila["ratios.endeudamiento.huber_9y"]
    mad_endeudamiento = fila["ratios.endeudamiento.huber_scale_mad"]
    techo_endeudamiento = min(
        huber_endeudamiento + N_DESVIACIONES_TECHO_ENDEUDAMIENTO * mad_endeudamiento,
        TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
    )

    # --- Apalancamiento: sube la deuda a largo hasta un endeudamiento objetivo (topado al
    # techo de plausibilidad), resuelto en forma cerrada sobre el balance SIN este efecto. ---
    apalancamiento_extra_eur = 0.0
    if efectos_apalancamiento:
        balance_base, _, _, _, _ = _evaluar(existencias_eur, realizable_eur, extra_deuda_largo_eur=0.0)
        # Topado al techo ANTES de aplicar la intensidad (no solo el objetivo final): si el año
        # anterior ya quedó por encima del techo por el residuo habitual del plug de cuadre
        # (una fracción de euro, normalmente), partir de ese valor ya excedido para multiplicar
        # por (1+intensidad) podía compensarse mal al recortar después, dejando el endeudamiento
        # de este año por DEBAJO del anterior (detectado en pruebas: TIC, Siderurgia). Al topar
        # la propia base, el objetivo de cada año queda siempre <= techo, sin depender de cuánto
        # se hubiera desviado el año anterior.
        endeudamiento_anterior = min(_endeudamiento(anterior.balance_eur), techo_endeudamiento)
        efecto_apalancamiento = efectos_apalancamiento[0]
        endeudamiento_objetivo = min(
            endeudamiento_anterior * (1 + efecto_apalancamiento.direccion * intensidad_efectiva), techo_endeudamiento
        )
        activo_base_eur = balance_base["activo_no_corriente"] + balance_base["activo_corriente"]
        pasivo_base_eur = balance_base["pasivo_no_corriente"] + balance_base["pasivo_corriente"]
        extra_deuda_objetivo_eur = max(0.0, endeudamiento_objetivo * activo_base_eur - pasivo_base_eur)
        # La deuda nueva financia una distribución a PN (ver docstring): no se puede repartir
        # más patrimonio neto del que hay. Sin este tope, en sectores con PN de partida bajo
        # (poco margen entre PN y el endeudamiento objetivo) la distribución podía dejar el PN
        # en negativo — detectado en pruebas de estrés (Restaurantes y puestos de comidas,
        # 4 de 3.000 combinaciones). Techo defensivo, no el mecanismo habitual.
        apalancamiento_extra_eur = min(extra_deuda_objetivo_eur, max(0.0, balance_base["patrimonio_neto"]))

    balance_eur, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur = _evaluar(
        existencias_eur, realizable_eur, extra_deuda_largo_eur=apalancamiento_extra_eur
    )

    deterioro_aplicado_eur = 0.0
    riesgo_endeudamiento = False
    endeudamiento_sin_contener: float | None = None
    contencion_al_limite = False

    # OJO: se comprueba SIEMPRE, no solo "if deuda_extra_por_nof_eur > 0". La primera versión
    # de este mecanismo solo miraba el endeudamiento cuando el déficit de NOF del propio año
    # forzaba deuda nueva — pero un arquetipo como "apalancamiento" nunca genera ese déficit
    # (no toca existencias/realizable) y aun así puede dejar un endeudamiento disparatado por
    # la "espiral de deuda" (ver docstring): la deuda de un año sigue devengando interés en el
    # siguiente, erosiona el PN, y el ratio empeora sin que se añada deuda nueva ESE año. Con
    # el chequeo condicionado a `deuda_extra_por_nof_eur`, esos casos pasaban completamente
    # desapercibidos: verificado en una pasada de estrés de 1.296 combinaciones del arquetipo
    # 9, 130 (10%) terminaban 2025 con patrimonio neto por debajo del 15% del activo (partiendo
    # de una base sana en 2023) sin que `riesgo_endeudamiento` se activase ni una vez.
    deficit_bruto_inicial_eur = deuda_extra_por_nof_eur  # = umbral de autofinanciación, ver más abajo
    endeudamiento_candidato = _endeudamiento(balance_eur)

    if endeudamiento_candidato > techo_endeudamiento:
        # El endeudamiento (YA con el cuadre general incluido) supera el techo de
        # plausibilidad del sector: se amortigua el exceso de las masas de circulante que el
        # arquetipo haya tocado (en el orden de su definición) en vez de seguir cargando todo
        # a deuda sin límite. Nunca se reduce por debajo del crecimiento proporcional a
        # ventas. Si el arquetipo no toca ninguna masa de circulante (9, 11, 15) — o si el
        # exceso disponible no basta, como en la "espiral de deuda" — no hay nada (o no hay
        # suficiente) que amortiguar por esta vía (deterioro máximo = 0 o insuficiente): el
        # caso queda marcado igualmente (`contencion_al_limite=True`), sin poder corregirse
        # del todo — es la señal honesta de que el caso es económicamente implausible, no un
        # intento fallido de arreglarlo silenciosamente.
        riesgo_endeudamiento = True
        endeudamiento_sin_contener = endeudamiento_candidato

        existencias_bruta_eur, realizable_bruta_eur = existencias_eur, realizable_eur
        activo_bruto_sin_amortiguar_eur = activo_no_corriente_eur + existencias_bruta_eur + realizable_bruta_eur
        excesos_eur = {
            efecto.variable: max(
                0.0,
                objetivos_circulante[efecto.variable] - proporcional_circulante[efecto.variable],
            )
            for efecto in efectos_masa_circulante
        }
        # Tope real de amortiguación: el menor entre (a) el exceso del propio arquetipo y
        # (b) el punto en el que el déficit de caja llega a cero (más allá, amortiguar más
        # no cambia ni el activo ni el pasivo: solo mueve valor a tesorería — ver docstring).
        # Si no hubo déficit de NOF este año (deficit_bruto_inicial_eur=0, caso apalancamiento/
        # mejora_margen/tesorería), el tope queda en 0: no hay margen de amortiguación por esta
        # vía y el bucle lo detecta y marca contencion_al_limite en su primera iteración.
        deterioro_maximo_eur = min(sum(excesos_eur.values()), deficit_bruto_inicial_eur)

        for _ in range(MAX_ITERACIONES_CONTENCION):
            patrimonio_neto_actual_eur = balance_eur["patrimonio_neto"]
            deterioro_objetivo_eur = activo_bruto_sin_amortiguar_eur - patrimonio_neto_actual_eur / (
                1 - techo_endeudamiento
            )
            nuevo_deterioro_aplicado_eur = min(max(deterioro_objetivo_eur, 0.0), deterioro_maximo_eur)
            cambio_eur = abs(nuevo_deterioro_aplicado_eur - deterioro_aplicado_eur)
            al_limite = nuevo_deterioro_aplicado_eur >= deterioro_maximo_eur
            deterioro_aplicado_eur = nuevo_deterioro_aplicado_eur

            # Reparte el deterioro entre las variables tocadas, en el orden de la
            # definición, agotando cada una antes de pasar a la siguiente.
            restante = deterioro_aplicado_eur
            objetivos_circulante_amortiguados = dict(objetivos_circulante)
            for variable, exceso in excesos_eur.items():
                aplicado = min(restante, exceso)
                objetivos_circulante_amortiguados[variable] = objetivos_circulante[variable] - aplicado
                restante -= aplicado
            existencias_eur = objetivos_circulante_amortiguados["existencias"]
            realizable_eur = objetivos_circulante_amortiguados["realizable"]

            balance_eur, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur = _evaluar(
                existencias_eur, realizable_eur, extra_deuda_largo_eur=apalancamiento_extra_eur
            )

            if al_limite:
                contencion_al_limite = True
                break  # se agotó el margen de amortiguación posible sin llegar al techo
            if cambio_eur < TOLERANCIA_CONVERGENCIA_DETERIORO_EUR:
                break  # convergido al techo

    return EjercicioEmpresa(
        año=año,
        ventas=ventas,
        crecimiento_ventas=crecimiento_ventas,
        balance_eur=balance_eur,
        pyg_eur=pyg_eur,
        pyg_pct=pyg_pct,
        modos=parcial_pyg.modos,
        ajuste_cuadre_eur=ajuste_cuadre_eur,
        deuda_extra_por_nof_eur=deuda_extra_por_nof_eur,
        endeudamiento=_endeudamiento(balance_eur),
        cobertura_gastos_financieros=_cobertura_gastos_financieros(pyg_eur),
        riesgo_endeudamiento=riesgo_endeudamiento,
        endeudamiento_sin_contener=endeudamiento_sin_contener,
        deterioro_aplicado_eur=deterioro_aplicado_eur,
        contencion_al_limite=contencion_al_limite,
        apalancamiento_extra_eur=apalancamiento_extra_eur,
        riesgo_plausibilidad_pyg=riesgo_plausibilidad_pyg,
        pyg_subtotales_sin_contener=pyg_subtotales_sin_contener,
    )


def generar_evolucion_arquetipo(
    sector: str,
    segmento: str,
    ventas_objetivo_2023: float,
    semilla: int,
    intensidad: str,
    arquetipo_id: str,
    catalogo: pd.DataFrame | None = None,
    arquetipos: dict[str, DefinicionArquetipo] | None = None,
) -> EvolucionArquetipo:
    """Genera 3 ejercicios (2023 base, 2024 y 2025 con `arquetipo_id` aplicado de forma
    progresiva: 60% de la intensidad en 2024, 100% en 2025), encadenados entre sí.

    `arquetipo_id` es una clave de `data/arquetipos.json` (ver `motor.arquetipos`)."""
    if intensidad not in INTENSIDADES_VALIDAS:
        raise EvolucionArquetipoError(
            f"Intensidad '{intensidad}' no válida. Debe ser una de: {sorted(INTENSIDADES_VALIDAS)}"
        )

    if arquetipos is None:
        arquetipos = cargar_arquetipos()
    if arquetipo_id not in arquetipos:
        raise EvolucionArquetipoError(
            f"Arquetipo '{arquetipo_id}' no reconocido. Disponibles: {sorted(arquetipos)}"
        )
    definicion = arquetipos[arquetipo_id]

    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    fila = resolver_fila_sector(catalogo, sector, segmento)

    empresa_2023 = generar_empresa_base(sector, segmento, ventas_objetivo_2023, semilla, catalogo=catalogo)
    ejercicios: dict[int, EjercicioEmpresa] = {AÑO_BASE: _ejercicio_desde_empresa_base(empresa_2023)}

    semilla_secuencia = np.random.SeedSequence(semilla)
    hijo_tendencia, hijo_2024, hijo_2025 = semilla_secuencia.spawn(3)
    rng_tendencia = np.random.default_rng(hijo_tendencia)
    rngs_pyg = {2024: np.random.default_rng(hijo_2024), 2025: np.random.default_rng(hijo_2025)}

    if definicion.rango_crecimiento_pleno is not None:
        bajo, alto = definicion.rango_crecimiento_pleno[intensidad]
        crecimiento_pleno_objetivo = bajo + rng_tendencia.random() * (alto - bajo)
    else:
        bajo, alto = RANGO_CRECIMIENTO_ORGANICO
        crecimiento_pleno_objetivo = bajo + rng_tendencia.random() * (alto - bajo)

    anterior = ejercicios[AÑO_BASE]
    for año in (2024, 2025):
        fraccion = FRACCION_AÑO[año]
        intensidad_efectiva = INTENSIDAD_BASE[intensidad] * fraccion
        crecimiento_ventas = (
            crecimiento_pleno_objetivo * fraccion if definicion.rango_crecimiento_pleno is not None else crecimiento_pleno_objetivo
        )
        ejercicio = _evolucionar_un_año(
            año, anterior, fila, rngs_pyg[año], crecimiento_ventas, intensidad_efectiva, definicion
        )
        ejercicios[año] = ejercicio
        anterior = ejercicio

    return EvolucionArquetipo(
        sector_codigo=sector,
        sector_nombre=fila["sector"],
        segmento=segmento,
        arquetipo=arquetipo_id,
        intensidad=intensidad,
        semilla=semilla,
        crecimiento_pleno_objetivo=crecimiento_pleno_objetivo,
        ejercicios=ejercicios,
        catalogo_version=catalogo.attrs.get("catalogo_version", "desconocida"),
    )
