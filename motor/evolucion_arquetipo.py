"""Evolución de una empresa a lo largo de 3 ejercicios (2023-2025) aplicando UN arquetipo.

Implementa únicamente el arquetipo 1 ("Crecimiento con destrucción de caja", sección 2.24 de
la especificación) como prueba de concepto del mecanismo de evolución causal año a año, antes
de generalizarlo a los otros 21 arquetipos. Sin matriz de compatibilidad, sin EFE/ECPN
completos, sin dividendos.

Diseño del mecanismo (decisiones no explícitas en la fórmula general de la sección 2.24, que
había que fijar para poder implementar):

- **2023 es el único ejercicio que usa el catálogo + ruido** (vía `motor.empresa_base` tal
  cual). 2024 y 2025 no vuelven a sortear existencias/clientes/tesorería desde el catálogo:
  se derivan del ejercicio anterior + el efecto del arquetipo ese año.
- **Ventas**: crecen cada año según un "crecimiento pleno" (objetivo a intensidad 100%, un
  único valor por empresa, sorteado una vez dentro de un rango por intensidad) escalado por la
  fracción del año (60% en 2024, 100% en 2025):
    leve: 3%-8% · moderado: 8%-15% · fuerte: 15%-25% (punto medio ~ criterio informal ACCID
    de crecimiento "moderado" citado en la especificación; rango completo para dar variabilidad).
- **Existencias y clientes (= partida "realizable")**: la rotación de existencias y el plazo
  de cobro se mueven cada año en un `intensidad_base x fracción_año` respecto al propio ratio
  del año anterior de la empresa (no respecto al valor Huber directamente): rotación de
  existencias × (1 − intensidad_efectiva), plazo de cobro × (1 + intensidad_efectiva). Se
  descartó anclar directamente al valor Huber del sector como haría la fórmula general de la
  sección 2.24 (`Valor_simulado = Huber x (1+intensidad*dirección)`) porque, al ser 2023 ya un
  sorteo con ruido propio, la distancia entre el ratio real de 2023 y el Huber del sector
  puede ser grande por simple variabilidad estadística — anclar ahí habría provocado un salto
  brusco en 2024 dominado por "volver a la media del sector" y no por el arquetipo, rompiendo
  la progresión pedida (2024 más suave que 2025). El valor Huber del sector se conserva como
  referencia de plausibilidad (suelo/techo defensivo: no se permite bajar de un 10% del Huber
  ni superar 3x el Huber), no como objetivo al que saltar.
- **Tesorería y deuda a corto**: el resto de las masas del balance (inmovilizado, patrimonio
  neto vía resultado retenido, deuda a largo, otras partidas de pasivo corriente) crecen en
  línea con las ventas. La diferencia entre ese crecimiento "neutro" de existencias+clientes
  y el crecimiento real (mayor, por el arquetipo) es la "NOF extra" del año: se resta primero
  de la tesorería; si la tesorería no basta (no puede quedar negativa), el resto se cubre con
  un aumento de deudas financieras a corto plazo. Es la forma de mantener la coherencia de
  "un aumento de circulante no financiado con caja se financia con deuda nueva" sin tener
  todavía el EFE completo.
- **Patrimonio neto**: PN(año) = PN(año-1) + resultado del ejercicio(año), reparto de
  dividendos cero (hasta que exista ECPN completo).
- **Cuadre final**: a diferencia de `empresa_base.py` (donde la renormalización porcentual ya
  deja el balance cuadrado y el ajuste es una excepción rara), aquí el ajuste sobre "otras
  deudas a corto plazo" SÍ es el mecanismo habitual de cuadre en 2024 y 2025: cada masa
  evoluciona con su propia regla (ventas, arquetipo, o resultado retenido) y no hay
  renormalización conjunta, así que el plug absorbe la diferencia residual cada año.

- **Control de plausibilidad del endeudamiento.** Cuando el déficit de caja se traslada a
  deudas financieras a corto plazo, se comprueba el endeudamiento resultante (pasivo
  total/activo total) contra `ratios.endeudamiento.huber_9y + 3 x huber_scale_mad` del sector.
  Si lo superaría, NO se deja crecer la deuda sin límite. **Decisión de diseño importante,
  distinta de lo pedido inicialmente:** se descartó reducir directamente el patrimonio neto
  como palanca de contención. Con el activo fijado por el propio arquetipo, la identidad
  contable Activo = PN + Pasivo implica endeudamiento = 1 − PN/Activo — bajar el PN, con el
  activo fijo, **exige más pasivo, no menos**: habría empeorado el endeudamiento que se quería
  contener, no solo habría sido "un efecto secundario sin control" sino matemáticamente
  contrario al objetivo (se verificó derivando la identidad a mano antes de implementar; ver
  `_evolucionar_un_año`). La palanca que sí reduce el endeudamiento resultante manteniendo el
  cuadre es amortiguar el propio exceso de circulante del arquetipo ese año (existencias
  primero, clientes si no basta), limitado como máximo a revertir el exceso por encima del
  crecimiento proporcional a ventas — nunca por debajo de lo que habría crecido sin arquetipo.
  El patrimonio neto no se toca: en este modelo mínimo no existe todavía una partida de
  "deterioro de existencias" en la cascada de PyG que conecte esa amortiguación con una pérdida
  contable — inventarlo habría sido una pérdida no trazable en las cuentas, así que se deja
  fuera hasta que el modelo tenga esa partida. El caso queda marcado explícitamente
  (`riesgo_endeudamiento=True`, con el endeudamiento sin contener y el importe amortiguado) como
  señal para el alumnado, se haya podido contener del todo o no.

- **Gastos financieros = deuda financiera media x tipo de interés del sector**, no un % de PyG
  sorteado de forma independiente (ver `motor.empresa_base._generar_pyg_hasta_baii` /
  `_completar_pyg_con_deuda`). La deuda financiera media de un ejercicio es el promedio entre
  el saldo de deudas financieras (largo + corto plazo) al inicio (= balance del año anterior) y
  al final del propio ejercicio. Esto crea una dependencia circular con la contención de
  endeudamiento: la deuda financiera final depende de si hay contención (que amortigua
  existencias/clientes y por tanto la deuda a corto necesaria), pero decidir si hay contención
  exige conocer el patrimonio neto, que exige conocer el resultado del ejercicio, que exige
  conocer los gastos financieros, que exigen conocer la deuda financiera final.

  Se resuelve en como mucho dos pasadas, sin bucle abierto: (1) se sortean las primitivas de
  PyG y el tipo de interés UNA sola vez (no dependen de deuda); (2) se evalúa el escenario
  "bruto" (existencias/clientes al objetivo pleno del arquetipo, sin contener) calculando su
  deuda financiera final, su coste financiero, su resultado y su PN, y con eso el balance
  candidato ya cuadrado; (3) se comprueba el endeudamiento de ese candidato contra el techo; si
  no lo supera, ese candidato ES el resultado final (deuda usada para el interés = deuda del
  balance final, sin aproximación). Si lo supera, se amortigua existencias/clientes como ya se
  describe arriba, y se vuelve a evaluar el escenario completo (deuda financiera, gastos
  financieros, resultado, PN, balance) una segunda vez con las cifras ya amortiguadas — sin
  volver a comprobar si la contención sigue siendo necesaria tras este ajuste fino (evitaría
  un bucle sin garantía de terminar). El importe a amortiguar se calcula con el patrimonio neto
  del escenario bruto (no el final, que aún no existe en ese momento): es una aproximación de
  segundo orden — el efecto de "menos deuda → menos interés → más beneficio → más PN" sobre el
  propio importe de contención es pequeño frente al efecto principal del arquetipo, y aceptarlo
  evita convertir esto en un solver iterativo.

- **Trazabilidad (sección 2.15).** `EvolucionArquetipo` guarda `arquetipo`, `intensidad`,
  `semilla`, `catalogo_version` (hash del CSV del catálogo usado — se deriva del propio
  archivo, no de un número mantenido a mano, para que no se desincronice si el catálogo
  cambia sin querer) y `pgc_version` (fijo por ahora: solo hay una versión normativa en
  juego). Falta la versión normativa "de verdad" variable y el ID del caso/variante — se
  añadirán cuando exista un repositorio de casos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import (
    TOLERANCIA_CUADRE_EUR,
    EmpresaBase,
    EmpresaBaseError,
    generar_empresa_base,
    resolver_fila_sector,
)
from motor.empresa_base import _completar_pyg_con_deuda, _generar_pyg_hasta_baii  # reutiliza la cascada de PyG

ARQUETIPO_ID = "crecimiento_destruccion_caja"
AÑOS = (2023, 2024, 2025)
AÑO_BASE = 2023

# Trazabilidad (sección 2.15): única versión normativa en juego por ahora.
PGC_VERSION = "PGC RD 1514/2007"

INTENSIDADES_VALIDAS = frozenset({"leve", "moderado", "fuerte"})
INTENSIDAD_BASE = {"leve": 0.15, "moderado": 0.30, "fuerte": 0.50}
FRACCION_AÑO = {2024: 0.6, 2025: 1.0}

# Rango de crecimiento de ventas "a intensidad completa" (100%), por nivel de intensidad.
RANGO_CRECIMIENTO_PLENO = {
    "leve": (0.03, 0.08),
    "moderado": (0.08, 0.15),
    "fuerte": (0.15, 0.25),
}

DIAS_AÑO = 365.0

# Suelo/techo defensivo frente al valor Huber del sector (evita valores absurdos en casos
# extremos; en escenarios moderado/fuerte normales no debería llegar a activarse nunca).
FRACCION_MINIMA_ROTACION_VS_HUBER = 0.10
FRACCION_MAXIMA_COBRO_DIAS_VS_HUBER = 3.0

# Techo de plausibilidad del endeudamiento: huber_9y + N desviaciones (huber_scale_mad) del
# sector. Tope absoluto adicional para que la fórmula de contención (que divide por
# 1-techo_endeudamiento) no degenere si un sector tuviera huber+N*mad >= 1.
N_DESVIACIONES_TECHO_ENDEUDAMIENTO = 3.0
TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO = 0.95

# La contención de endeudamiento es un punto fijo (menos deuda -> menos interés -> más PN ->
# hace falta amortiguar menos), no una fórmula cerrada de una sola pasada: se itera acotado.
MAX_ITERACIONES_CONTENCION = 50
TOLERANCIA_CONVERGENCIA_DETERIORO_EUR = 1.0


class EvolucionArquetipoError(ValueError):
    """Parámetros de entrada inválidos."""


@dataclass(frozen=True)
class EjercicioEmpresa:
    año: int
    ventas: float
    crecimiento_ventas: float | None  # None en el año base (2023)
    balance_eur: dict[str, float]
    pyg_eur: dict[str, float]
    modos: dict[str, str]
    ajuste_cuadre_eur: float
    rotacion_existencias: float
    cobro_dias: float
    deuda_extra_por_nof_eur: float  # 0.0 salvo cuando la tesorería no basta para absorber la NOF
    endeudamiento: float  # pasivo total / activo total, ya con cualquier contención aplicada
    cobertura_gastos_financieros: float  # BAII / gastos financieros
    riesgo_endeudamiento: bool = False
    endeudamiento_sin_contener: float | None = None  # solo si riesgo_endeudamiento=True
    deterioro_aplicado_eur: float = 0.0  # exceso de existencias/clientes amortiguado por plausibilidad
    contencion_al_limite: bool = False  # True si no se pudo llegar al techo: se agotó el margen de amortiguación


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


def _rotacion_existencias(ventas: float, existencias_eur: float) -> float:
    return ventas / existencias_eur


def _cobro_dias(ventas: float, realizable_eur: float) -> float:
    return realizable_eur / ventas * DIAS_AÑO


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
        modos=dict(empresa.modos),
        ajuste_cuadre_eur=empresa.ajuste_cuadre_eur,
        rotacion_existencias=_rotacion_existencias(empresa.ventas_objetivo, empresa.balance_eur["existencias"]),
        cobro_dias=_cobro_dias(empresa.ventas_objetivo, empresa.balance_eur["realizable"]),
        deuda_extra_por_nof_eur=0.0,
        endeudamiento=_endeudamiento(empresa.balance_eur),
        cobertura_gastos_financieros=_cobertura_gastos_financieros(empresa.pyg_eur),
    )


def _evolucionar_un_año(
    año: int,
    anterior: EjercicioEmpresa,
    fila: pd.Series,
    rng_pyg: np.random.Generator,
    crecimiento_ventas: float,
    intensidad_efectiva: float,
) -> EjercicioEmpresa:
    ventas = anterior.ventas * (1 + crecimiento_ventas)

    # --- Existencias: la rotación empeora un intensidad_efectiva respecto al propio año anterior ---
    huber_rotacion_existencias = fila["ratios.rotacion_existencias.huber_9y"]
    rotacion_existencias = anterior.rotacion_existencias * (1 - intensidad_efectiva)
    rotacion_existencias = max(rotacion_existencias, FRACCION_MINIMA_ROTACION_VS_HUBER * huber_rotacion_existencias)
    existencias_eur = ventas / rotacion_existencias

    # --- Clientes (realizable): el plazo de cobro se alarga un intensidad_efectiva respecto al anterior ---
    huber_cobro_dias = fila["ratios.cobro_dias.huber_9y"]
    cobro_dias = anterior.cobro_dias * (1 + intensidad_efectiva)
    cobro_dias = min(cobro_dias, FRACCION_MAXIMA_COBRO_DIAS_VS_HUBER * huber_cobro_dias)
    realizable_eur = cobro_dias / DIAS_AÑO * ventas

    existencias_proporcional_eur = anterior.balance_eur["existencias"] * (1 + crecimiento_ventas)
    realizable_proporcional_eur = anterior.balance_eur["realizable"] * (1 + crecimiento_ventas)

    # --- Resto de masas: crecen en línea con las ventas (patrimonio neto se trata aparte) ---
    activo_no_corriente_eur = anterior.balance_eur["activo_no_corriente"] * (1 + crecimiento_ventas)
    pasivo_no_corriente_eur = {
        "deudas_fin_largo": anterior.balance_eur["deudas_fin_largo"] * (1 + crecimiento_ventas),
        "otras_deudas_largo": anterior.balance_eur["otras_deudas_largo"] * (1 + crecimiento_ventas),
    }
    acreedores_comerciales_eur = anterior.balance_eur["acreedores_comerciales"] * (1 + crecimiento_ventas)
    otras_deudas_corto_eur = anterior.balance_eur["otras_deudas_corto"] * (1 + crecimiento_ventas)
    deudas_fin_corto_proporcional_eur = anterior.balance_eur["deudas_fin_corto"] * (1 + crecimiento_ventas)
    disponible_proporcional_eur = anterior.balance_eur["disponible"] * (1 + crecimiento_ventas)
    deuda_financiera_inicio_eur = anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"]

    # Primitivas de PyG (no dependen de deuda) + tipo de interés del sector: se sortean UNA
    # sola vez: los gastos financieros (y por tanto BAI/resultado) se completan más abajo,
    # dos veces como mucho, según haga falta o no contener el endeudamiento (ver docstring).
    parcial_pyg = _generar_pyg_hasta_baii(rng_pyg, fila, ventas)

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
        existencias_eur: float, realizable_eur: float, disponible_eur: float, deudas_fin_corto_eur: float, patrimonio_neto_eur: float
    ) -> tuple[dict[str, float], float]:
        balance = {
            "activo_no_corriente": activo_no_corriente_eur,
            "activo_corriente": existencias_eur + realizable_eur + disponible_eur,
            "existencias": existencias_eur,
            "realizable": realizable_eur,
            "disponible": disponible_eur,
            "patrimonio_neto": patrimonio_neto_eur,
            "pasivo_no_corriente": pasivo_no_corriente_eur["deudas_fin_largo"] + pasivo_no_corriente_eur["otras_deudas_largo"],
            "deudas_fin_largo": pasivo_no_corriente_eur["deudas_fin_largo"],
            "otras_deudas_largo": pasivo_no_corriente_eur["otras_deudas_largo"],
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
        existencias_eur: float, realizable_eur: float
    ) -> tuple[dict[str, float], float, float, dict[str, float], dict[str, float]]:
        """Evalúa un escenario de existencias/clientes de forma autoconsistente: la deuda
        financiera final de ESE escenario determina los gastos financieros de ESE escenario."""
        disponible_eur, deudas_fin_corto_eur, deuda_extra_por_nof_eur = _deficit_y_deuda_corto(
            existencias_eur, realizable_eur
        )
        deuda_financiera_fin_eur = pasivo_no_corriente_eur["deudas_fin_largo"] + deudas_fin_corto_eur
        deuda_financiera_media_eur = (deuda_financiera_inicio_eur + deuda_financiera_fin_eur) / 2
        pyg_pct, pyg_eur = _completar_pyg_con_deuda(parcial_pyg, deuda_financiera_media_eur)
        patrimonio_neto_eur = anterior.balance_eur["patrimonio_neto"] + pyg_eur["resultado_ejercicio"]
        balance, ajuste_cuadre_eur = _construir_balance(
            existencias_eur, realizable_eur, disponible_eur, deudas_fin_corto_eur, patrimonio_neto_eur
        )
        return balance, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur

    balance_eur, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur = _evaluar(existencias_eur, realizable_eur)

    deterioro_aplicado_eur = 0.0
    riesgo_endeudamiento = False
    endeudamiento_sin_contener: float | None = None
    contencion_al_limite = False

    if deuda_extra_por_nof_eur > 0:
        deficit_bruto_inicial_eur = deuda_extra_por_nof_eur  # = umbral de autofinanciación, ver más abajo
        endeudamiento_candidato = _endeudamiento(balance_eur)
        huber_endeudamiento = fila["ratios.endeudamiento.huber_9y"]
        mad_endeudamiento = fila["ratios.endeudamiento.huber_scale_mad"]
        techo_endeudamiento = min(
            huber_endeudamiento + N_DESVIACIONES_TECHO_ENDEUDAMIENTO * mad_endeudamiento,
            TECHO_ENDEUDAMIENTO_MAXIMO_ABSOLUTO,
        )

        if endeudamiento_candidato > techo_endeudamiento:
            # El endeudamiento con financiación 100% a deuda (YA con el cuadre general
            # incluido, no una cifra a medio calcular) superaría el techo de plausibilidad del
            # sector: se amortigua el propio exceso de circulante del arquetipo (existencias
            # primero, clientes si no basta) en vez de seguir cargando todo a deuda sin límite.
            # Nunca se reduce por debajo del crecimiento proporcional a ventas (el arquetipo,
            # como mucho, se neutraliza ese año, no se revierte). Ver docstring del módulo: el
            # patrimonio neto no se toca — con el activo fijado por el arquetipo, bajar el PN
            # exigiría MÁS pasivo para cuadrar, no menos, empeorando el propio endeudamiento
            # que se quiere contener (Activo=PN+Pasivo => endeudamiento=1-PN/Activo).
            riesgo_endeudamiento = True
            endeudamiento_sin_contener = endeudamiento_candidato

            existencias_bruta_eur, realizable_bruta_eur = existencias_eur, realizable_eur
            activo_bruto_sin_amortiguar_eur = activo_no_corriente_eur + existencias_bruta_eur + realizable_bruta_eur
            exceso_existencias_eur = max(0.0, existencias_bruta_eur - existencias_proporcional_eur)
            exceso_realizable_eur = max(0.0, realizable_bruta_eur - realizable_proporcional_eur)
            # Tope real de amortiguación: el menor entre (a) el exceso del propio arquetipo
            # (no se revierte por debajo del crecimiento proporcional) y (b) el punto en el que
            # el déficit de caja llega a cero. Más allá de (b) la tesorería empieza a quedar en
            # positivo y "amortiguar más" solo mueve valor de existencias/clientes a caja: el
            # activo total, el pasivo total y el PN dejan de cambiar (deudas_fin_corto ya no
            # baja más), así que seguir no reduce el endeudamiento — solo desestabilizaba la
            # fórmula cerrada de abajo, que asume tesorería en cero. Se detectó exactamente así:
            # con una amortiguación mayor que necesaria, el punto fijo convergía a un
            # endeudamiento muy por encima del techo (caso real de prueba: 43,5% vs techo 35,6%).
            deterioro_maximo_eur = min(exceso_existencias_eur + exceso_realizable_eur, deficit_bruto_inicial_eur)

            # El importe a amortiguar depende del PN, que depende de los gastos financieros,
            # que dependen de la deuda financiera final — que baja al amortiguar. Se itera
            # (acotado, no es un bucle abierto) recalculando el importe total (siempre respecto
            # a la base "bruta" sin amortiguar, no de forma incremental) hasta que converge al
            # techo o se agota el margen de amortiguación posible (deterioro_maximo_eur).
            for _ in range(MAX_ITERACIONES_CONTENCION):
                patrimonio_neto_actual_eur = balance_eur["patrimonio_neto"]
                deterioro_objetivo_eur = activo_bruto_sin_amortiguar_eur - patrimonio_neto_actual_eur / (
                    1 - techo_endeudamiento
                )
                nuevo_deterioro_aplicado_eur = min(max(deterioro_objetivo_eur, 0.0), deterioro_maximo_eur)
                cambio_eur = abs(nuevo_deterioro_aplicado_eur - deterioro_aplicado_eur)
                al_limite = nuevo_deterioro_aplicado_eur >= deterioro_maximo_eur
                deterioro_aplicado_eur = nuevo_deterioro_aplicado_eur

                # Se aplica y se reevalúa el balance con el valor de ESTA iteración antes de
                # decidir si parar — si no, al converger se devolvería el balance de la
                # iteración anterior, ligeramente desactualizado.
                deterioro_existencias_eur = min(deterioro_aplicado_eur, exceso_existencias_eur)
                deterioro_realizable_eur = deterioro_aplicado_eur - deterioro_existencias_eur
                existencias_eur = existencias_bruta_eur - deterioro_existencias_eur
                realizable_eur = realizable_bruta_eur - deterioro_realizable_eur

                balance_eur, ajuste_cuadre_eur, deuda_extra_por_nof_eur, pyg_pct, pyg_eur = _evaluar(
                    existencias_eur, realizable_eur
                )

                if al_limite:
                    contencion_al_limite = True
                    break  # se agotó el margen de amortiguación posible sin llegar al techo
                if cambio_eur < TOLERANCIA_CONVERGENCIA_DETERIORO_EUR:
                    break  # convergido al techo

    # Rotación de existencias y plazo de cobro "reales" del año, ya con cualquier contención
    # aplicada (afecta a la continuidad del año siguiente y a lo que se reporta).
    rotacion_existencias = ventas / existencias_eur
    cobro_dias = realizable_eur / ventas * DIAS_AÑO

    return EjercicioEmpresa(
        año=año,
        ventas=ventas,
        crecimiento_ventas=crecimiento_ventas,
        balance_eur=balance_eur,
        pyg_eur=pyg_eur,
        modos=parcial_pyg.modos,
        ajuste_cuadre_eur=ajuste_cuadre_eur,
        rotacion_existencias=rotacion_existencias,
        cobro_dias=cobro_dias,
        deuda_extra_por_nof_eur=deuda_extra_por_nof_eur,
        endeudamiento=_endeudamiento(balance_eur),
        cobertura_gastos_financieros=_cobertura_gastos_financieros(pyg_eur),
        riesgo_endeudamiento=riesgo_endeudamiento,
        endeudamiento_sin_contener=endeudamiento_sin_contener,
        deterioro_aplicado_eur=deterioro_aplicado_eur,
        contencion_al_limite=contencion_al_limite,
    )


def generar_evolucion_arquetipo(
    sector: str,
    segmento: str,
    ventas_objetivo_2023: float,
    semilla: int,
    intensidad: str,
    catalogo: pd.DataFrame | None = None,
) -> EvolucionArquetipo:
    """Genera 3 ejercicios (2023 base, 2024 y 2025 con el arquetipo 1 aplicado de forma
    progresiva: 60% de la intensidad en 2024, 100% en 2025), encadenados entre sí."""
    if intensidad not in INTENSIDADES_VALIDAS:
        raise EvolucionArquetipoError(
            f"Intensidad '{intensidad}' no válida. Debe ser una de: {sorted(INTENSIDADES_VALIDAS)}"
        )

    if catalogo is None:
        catalogo = cargar_y_validar_catalogo()

    fila = resolver_fila_sector(catalogo, sector, segmento)

    empresa_2023 = generar_empresa_base(sector, segmento, ventas_objetivo_2023, semilla, catalogo=catalogo)
    ejercicios: dict[int, EjercicioEmpresa] = {AÑO_BASE: _ejercicio_desde_empresa_base(empresa_2023)}

    semilla_secuencia = np.random.SeedSequence(semilla)
    hijo_tendencia, hijo_2024, hijo_2025 = semilla_secuencia.spawn(3)
    rng_tendencia = np.random.default_rng(hijo_tendencia)
    rngs_pyg = {2024: np.random.default_rng(hijo_2024), 2025: np.random.default_rng(hijo_2025)}

    bajo, alto = RANGO_CRECIMIENTO_PLENO[intensidad]
    crecimiento_pleno_objetivo = bajo + rng_tendencia.random() * (alto - bajo)

    anterior = ejercicios[AÑO_BASE]
    for año in (2024, 2025):
        fraccion = FRACCION_AÑO[año]
        crecimiento_ventas = crecimiento_pleno_objetivo * fraccion
        intensidad_efectiva = INTENSIDAD_BASE[intensidad] * fraccion
        ejercicio = _evolucionar_un_año(
            año, anterior, fila, rngs_pyg[año], crecimiento_ventas, intensidad_efectiva
        )
        ejercicios[año] = ejercicio
        anterior = ejercicio

    return EvolucionArquetipo(
        sector_codigo=sector,
        sector_nombre=fila["sector"],
        segmento=segmento,
        arquetipo=ARQUETIPO_ID,
        intensidad=intensidad,
        semilla=semilla,
        crecimiento_pleno_objetivo=crecimiento_pleno_objetivo,
        ejercicios=ejercicios,
        catalogo_version=catalogo.attrs.get("catalogo_version", "desconocida"),
    )
