"""Provisiones a largo y corto plazo (subgrupo 14 del PGC + 4994/4999) — tercer lote de desglose
de balance. Epígrafes propios del balance oficial (B.I "Provisiones a largo plazo", C.II
"Provisiones a corto plazo"), hoy completamente ausentes del motor.

**Provisión vs. contingencia — distinción normativa que este módulo respeta, NO confundir con
el arquetipo 22.** Una PROVISIÓN (este módulo) es una obligación probable Y estimable con
fiabilidad — SÍ se reconoce como pasivo real en balance (PGC, marco conceptual, criterio de
reconocimiento de pasivos). Una CONTINGENCIA (arquetipo 22 "informacion_relevante_memoria",
`motor/memoria.py` — sin ningún cambio en este lote) es una obligación posible, o no estimable
con fiabilidad — NO se reconoce en balance, solo se menciona en memoria (ver el texto literal de
sus notas: "no se ha dotado provisión alguna al considerar la Dirección... que el riesgo de
pérdida no es probable"). Son dos mecanismos DISTINTOS e independientes: pueden coexistir en el
mismo caso sin ninguna relación causal entre ellos — este módulo no toca ni conecta con el 22.

**Categorías incluidas (subgrupo 14, verificado contra el cuadro de cuentas del PGC) y su
naturaleza en PyG** — la dotación es un gasto dentro de "Gastos de personal" (línea 6 del modelo
oficial) si es una obligación de personal, o "Otros gastos de explotación" (línea 7) el resto:
  - **140** Retribuciones a largo plazo al personal (indemnizaciones, compromisos post-empleo no
    externalizados) — `gastos_personal`.
  - **141** Impuestos (contingencias fiscales, litigios con la AEAT) — `otros_gastos_explot`.
  - **142** Otras responsabilidades (litigios/reclamaciones de terceros, cajón general) —
    `otros_gastos_explot`.
  - **143** Desmantelamiento, retiro o rehabilitación del inmovilizado — `otros_gastos_explot`;
    más plausible en sectores con activo material pesado (industria, construcción).
  - **145** Actuaciones medioambientales — `otros_gastos_explot`.
  - **146** Reestructuraciones — `otros_gastos_explot`.
  - **4994** Contratos onerosos (proyecto en curso cuyo coste de cumplimiento supera lo que va a
    cobrarse) — `otros_gastos_explot`; más plausible en sectores "por proyecto" (tier
    `producto_en_curso` del lote 1: 69.2/70.2/62/71/72) y en construcción.
  - **4999** Provisión para otras operaciones comerciales (devoluciones, garantías de producto,
    revisiones) — `otros_gastos_explot`; más plausible en industria y comercio con garantía de
    producto.

**147 (pagos basados en instrumentos de patrimonio propio) DESCARTADA explícitamente** —
retribución variable ligada al valor de acciones/participaciones propias, mecanismo típico de
empresas cotizadas o startups con planes de incentivos sofisticados, ajeno al perfil de
PYME/empresa mediana que representan los 27 sectores de este motor — mismo criterio de
plausibilidad ya aplicado al descartar piezas de baja relevancia del grupo 8/9.

**Largo vs. corto plazo: NO son catálogos distintos, es una reclasificación** — el subgrupo 529
es literalmente el mismo catálogo de arriba, reclasificado a corto plazo cuando el vencimiento
previsto cae dentro del año. Cada provisión lleva un `plazo_total_años` FIJO desde su dotación;
se clasifica ÍNTEGRA como largo o corto según si le queda más o menos de 1 año para su horizonte
de aplicación estimado — con el paso natural largo→corto según se acerca la fecha, año a año.
Mismo ESPÍRITU que `EfectoReclasificacionDeuda` (mover saldo entre plazos sin alterar el total),
pero sin su mecanismo de continuidad-contra-huber: no existe ningún ratio de catálogo al que
anclar el vencimiento de una provisión, así que se usa en su lugar un horizonte determinista por
instancia, sorteado una vez.

**Probabilidad de fondo, independiente de cualquier arquetipo** (mismo patrón ya construido para
`sortear_subvencion_baseline` en `motor/coberturas_subvenciones.py`) — pedido explícitamente para
que las provisiones puedan aparecer también con el arquetipo 6 ("Aumento de clientes (base)",
línea base sana), sin depender de que haya un arquetipo de riesgo activo. Probabilidad PLANA
(no por categoría de sector, a diferencia de subvención): `PROBABILIDAD_PROVISION = 0.25`, dentro
del rango 20%-30% pedido explícitamente para que sea fácil de encontrar por búsqueda de semilla,
sin necesitar probar decenas.

**Movimiento anual** (saldo inicial / dotación / aplicación / exceso / saldo final) — mismo
patrón "fórmula continua por instancia" ya usado en `motor/amortizacion.py`
(`SubLoteActivo.acumulada_en`): la dotación ocurre ÍNTEGRA en el año de dotación (sorteado, 2024
o 2025 — igual que `año_concesion` de la subvención de fondo); a partir de ahí, el saldo se
libera linealmente sobre `plazo_total_años` (tasa anual = importe dotado / plazo), repartida
entre APLICACIÓN (uso real de la provisión para su fin — salida de caja, `FRACCION_APLICACION`
del total liberado ese año) y EXCESO (la estimación resultó alta — ingreso de PyG, "Excesos de
provisiones", línea 10 del modelo oficial, sin flujo de caja)."""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

CATEGORIAS_PROVISION = ("140", "141", "142", "143", "145", "146", "4994", "4999")

NATURALEZA_PYG_POR_CATEGORIA: dict[str, str] = {
    "140": "gastos_personal",
    "141": "otros_gastos_explot",
    "142": "otros_gastos_explot",
    "143": "otros_gastos_explot",
    "145": "otros_gastos_explot",
    "146": "otros_gastos_explot",
    "4994": "otros_gastos_explot",
    "4999": "otros_gastos_explot",
}

# Probabilidad de fondo PLANA (no por categoría de sector) de que el caso tenga UNA provisión
# activa — independiente de cualquier arquetipo, ver docstring del módulo.
PROBABILIDAD_PROVISION = 0.25

# Peso BASE (antes de los multiplicadores sectoriales de abajo) de cada categoría al elegir CUÁL
# se activa, una vez que el sorteo de PROBABILIDAD_PROVISION ya decidió que hay una — refleja
# frecuencia relativa genérica en una PYME/empresa mediana española: "Otras responsabilidades"
# (litigios/reclamaciones, cajón general) y garantías comerciales son las más habituales;
# reestructuraciones y medioambiente las menos, salvo boost sectorial.
PESO_BASE_CATEGORIA_PROVISION: dict[str, float] = {
    "140": 0.14,
    "141": 0.13,
    "142": 0.22,
    "143": 0.05,
    "145": 0.08,
    "146": 0.08,
    "4994": 0.10,
    "4999": 0.20,
}

# Multiplicadores sectoriales explícitos (ver docstring): 143 (desmantelamiento) mucho más
# plausible en sectores con activo material pesado; 4994 (contratos onerosos) en sectores "por
# proyecto" (tier producto_en_curso del lote 1) y construcción; 4999 (garantías) en industria y
# comercio/hostelería con producto físico entregable.
MULTIPLICADOR_143_POR_CATEGORIA: dict[str, float] = {"industria": 6.0, "construccion": 6.0}
MULTIPLICADOR_4994_POR_CATEGORIA: dict[str, float] = {"construccion": 6.0}
MULTIPLICADOR_4994_TIER_PRODUCTO_EN_CURSO = 6.0
MULTIPLICADOR_4999_POR_CATEGORIA: dict[str, float] = {"industria": 3.0, "comercio_hosteleria": 3.0}

# Magnitud (% de patrimonio_neto del año anterior a la dotación — mismo criterio de anclaje ya
# usado para el "préstamo a matriz" del arquetipo 20: sin dato de catálogo que lo ancle, se usa
# una fracción moderada del tamaño de la empresa, más pequeña que la de operaciones vinculadas
# porque una provisión rutinaria de una PYME no suele ser una magnitud tan grande como un
# préstamo intragrupo deliberado) y suelo defensivo en euros.
RANGO_IMPORTE_PROVISION_PCT_PN = (0.01, 0.06)
SUELO_IMPORTE_PROVISION_EUR = 15_000.0

# Horizonte total de la provisión desde su dotación — rango que garantiza, dentro de la ventana
# de 3 años del motor, una mezcla real de casos que permanecen a largo plazo todo el caso y casos
# que transicionan a corto plazo antes de 2025 (ver docstring, "paso natural largo→corto").
RANGO_PLAZO_TOTAL_AÑOS = (1.5, 4.0)

# Fracción de cada liberación anual que es aplicación (uso real, salida de caja) frente a exceso
# (reversión a resultados, sin caja) — hipótesis de diseño: una provisión rutinaria se aplica
# mayoritariamente para el fin que la originó, con una fracción menor de sobre-estimación.
FRACCION_APLICACION = 0.70


def _entropia_provision(sector: str, segmento: str, sufijo: str = "") -> int:
    return zlib.crc32(f"{sector}|{segmento}|provision{sufijo}".encode("utf-8"))


def _pesos_categoria_provision(categoria_sector: str, tier_existencias_sector: str) -> dict[str, float]:
    pesos = dict(PESO_BASE_CATEGORIA_PROVISION)
    pesos["143"] *= MULTIPLICADOR_143_POR_CATEGORIA.get(categoria_sector, 1.0)
    pesos["4994"] *= MULTIPLICADOR_4994_POR_CATEGORIA.get(categoria_sector, 1.0)
    if tier_existencias_sector == "producto_en_curso":
        pesos["4994"] *= MULTIPLICADOR_4994_TIER_PRODUCTO_EN_CURSO
    pesos["4999"] *= MULTIPLICADOR_4999_POR_CATEGORIA.get(categoria_sector, 1.0)
    total = sum(pesos.values())
    return {categoria: peso / total for categoria, peso in pesos.items()}


@dataclass(frozen=True)
class ParametrosProvision:
    """Rasgos ESTRUCTURALES de la provisión del caso, sorteados UNA vez (no por año) — mismo
    criterio que `ParametrosGrupo89`/`ParametrosOperacionVinculada`. `activa=False` dispensa el
    resto de campos (0/""). Como con la subvención de fondo, la MAGNITUD (`importe_dotado_eur`)
    no se sortea aquí: depende de `patrimonio_neto`, que no se conoce hasta que el año de
    dotación se resuelve — ver `sortear_importe_provision_eur`."""

    activa: bool = False
    categoria: str = ""
    naturaleza_pyg: str = ""
    año_dotacion: int = 0
    plazo_total_años: float = 0.0


def sortear_provision_baseline(
    sector: str, segmento: str, semilla: int, categoria_sector: str, tier_existencias_sector: str
) -> ParametrosProvision:
    """Sorteo ÚNICO por caso, independiente de cualquier arquetipo — ver docstring del módulo."""
    rng = np.random.default_rng([semilla, _entropia_provision(sector, segmento, "_baseline")])
    activa = rng.random() < PROBABILIDAD_PROVISION
    if not activa:
        # Aun sin activarse, se consumen los mismos draws que la rama activa (permutation +
        # 2 floats) para que la posición de CUALQUIER sorteo posterior en el motor que reutilice
        # esta semilla+sector+segmento no dependa de si la provisión salió activa o no — mismo
        # cuidado ya aplicado al índice de operaciones vinculadas (rng.permutation consumido
        # siempre, se use o no el resultado).
        pesos = _pesos_categoria_provision(categoria_sector, tier_existencias_sector)
        rng.choice(CATEGORIAS_PROVISION, p=[pesos[c] for c in CATEGORIAS_PROVISION])
        rng.integers(2)
        rng.uniform(*RANGO_PLAZO_TOTAL_AÑOS)
        return ParametrosProvision()

    pesos = _pesos_categoria_provision(categoria_sector, tier_existencias_sector)
    categoria = rng.choice(CATEGORIAS_PROVISION, p=[pesos[c] for c in CATEGORIAS_PROVISION])
    año_dotacion = 2024 if rng.integers(2) == 0 else 2025
    plazo_total_años = rng.uniform(*RANGO_PLAZO_TOTAL_AÑOS)
    return ParametrosProvision(
        activa=True,
        categoria=str(categoria),
        naturaleza_pyg=NATURALEZA_PYG_POR_CATEGORIA[str(categoria)],
        año_dotacion=año_dotacion,
        plazo_total_años=plazo_total_años,
    )


def sortear_importe_provision_eur(sector: str, segmento: str, semilla: int, patrimonio_neto_referencia_eur: float) -> float:
    rng = np.random.default_rng([semilla, _entropia_provision(sector, segmento, "_magnitud")])
    bajo, alto = RANGO_IMPORTE_PROVISION_PCT_PN
    bruto_eur = rng.uniform(bajo, alto) * patrimonio_neto_referencia_eur
    return max(bruto_eur, SUELO_IMPORTE_PROVISION_EUR)


@dataclass(frozen=True)
class PasoProvision:
    saldo_eur: float
    dotacion_eur: float  # solo > 0 en el año de dotación
    aplicacion_eur: float  # salida de caja real
    exceso_eur: float  # ingreso de PyG ("Excesos de provisiones"), sin caja
    es_largo: bool  # clasificación de `saldo_eur` este año — True=largo plazo, False=corto


def evolucionar_provision(
    parametros: ParametrosProvision, importe_dotado_eur: float, saldo_anterior_eur: float, año: int
) -> PasoProvision:
    """Un paso anual — ver docstring del módulo para la fórmula de liberación lineal y el
    criterio de clasificación largo/corto. `saldo_anterior_eur` es 0.0 antes del año de dotación
    (y el propio parámetro por caso, `PARAMETROS_PROVISION_INACTIVA`, ya deja `activa=False` para
    cuando no hay ninguna provisión en el caso)."""
    if not parametros.activa or año < parametros.año_dotacion:
        return PasoProvision(0.0, 0.0, 0.0, 0.0, es_largo=False)

    if año == parametros.año_dotacion:
        saldo_eur = importe_dotado_eur
        dotacion_eur = importe_dotado_eur
        aplicacion_eur = 0.0
        exceso_eur = 0.0
    else:
        tasa_anual_eur = importe_dotado_eur / parametros.plazo_total_años
        reduccion_eur = min(saldo_anterior_eur, tasa_anual_eur)
        aplicacion_eur = reduccion_eur * FRACCION_APLICACION
        exceso_eur = reduccion_eur - aplicacion_eur
        saldo_eur = saldo_anterior_eur - reduccion_eur
        dotacion_eur = 0.0

    plazo_restante_años = parametros.año_dotacion + parametros.plazo_total_años - año
    es_largo = plazo_restante_años > 1.0

    return PasoProvision(saldo_eur, dotacion_eur, aplicacion_eur, exceso_eur, es_largo)
