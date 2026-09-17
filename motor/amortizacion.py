"""Amortización derivada de una colección real de activos — sustituye el sorteo independiente
de `amortizaciones_pct` (arreglo de raíz pedido explícitamente, no un parche del síntoma
detectado en el EFE: `a2a_amortizacion` siempre a 0€ porque no había ningún activo real detrás
del gasto).

**Marco normativo verificado (no de memoria) antes de generar nada:**

- **Terrenos: NUNCA se amortizan** — ni dentro de `material` ni dentro de `inversiones_
  inmobiliarias` (PGC norma de registro y valoración 2ª, inmovilizado material).
- **Fondo de comercio: SÍ se amortiza sistemáticamente desde el 1-1-2016** (Ley 22/2015 de
  Auditoría de Cuentas + RD 602/2016, que modificó el PGC) — al revés de lo que se planteó al
  proponer este encargo. Antes de 2016 tenía vida indefinida (solo deterioro, alineado con
  NIC/IFRS de la época); desde 2016 el PGC norma 6ª presume vida útil de 10 años con
  recuperación lineal, salvo prueba en contrario. Verificado con 3 fuentes independientes
  (CEF/Udima, ICJCE, foros profesionales) citando la Norma de Registro y Valoración 6ª
  literalmente. Consecuencia práctica: dentro de `intangible`, prácticamente todo es
  amortizable bajo PGC (a diferencia de NIC/IFRS, donde el fondo de comercio de cotizadas sigue
  sin amortizarse).
- **Otros activos financieros: NUNCA se amortizan** — son instrumentos financieros sujetos a
  deterioro/valor razonable, no a amortización por uso.
- **Inversiones inmobiliarias**: mismo criterio que material (PGC norma 4ª remite a la 2ª) — la
  parte de terreno no se amortiza, la de construcción sí.

**Tabla de coeficientes fiscales verificada contra la Agencia Tributaria** (tabla vigente desde
2015, Ley 27/2014 del Impuesto sobre Sociedades — "amortiza siempre al coeficiente máximo
fiscalmente permitido" significa usar la vida MÁS CORTA, `100/coeficiente_máximo`, no el
"período máximo" de la tabla oficial, que es la cifra que corresponde al coeficiente MÍNIMO).

Fuente: sede.agenciatributaria.gob.es, tabla de coeficientes de amortización lineal.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass

import numpy as np

from motor.ruido import _generar_partida, _renormalizar_a_total

AÑO_BASE = 2023


@dataclass(frozen=True)
class TipoActivoAmortizable:
    nombre: str
    coeficiente_fiscal_maximo: float  # p. ej. 0.12 para maquinaria (12%)
    es_construccion: bool  # distinción exacta que pide la nota de memoria del PGC (punto 2.l)

    @property
    def vida_fiscal_años(self) -> float:
        return 1.0 / self.coeficiente_fiscal_maximo


# Vida fiscal = 100/coeficiente máximo (la más CORTA de la tabla, ver docstring del módulo).
TIPOS_ACTIVO_MATERIAL: dict[str, TipoActivoAmortizable] = {
    "construcciones_industriales": TipoActivoAmortizable("Construcciones (uso industrial)", 0.03, True),
    "construcciones_comerciales": TipoActivoAmortizable("Construcciones (uso comercial/administrativo)", 0.02, True),
    "instalaciones_maquinaria": TipoActivoAmortizable("Instalaciones técnicas y maquinaria", 0.12, False),
    "equipos_informaticos": TipoActivoAmortizable("Equipos para procesos de información", 0.25, False),
    "elementos_transporte": TipoActivoAmortizable("Elementos de transporte", 0.16, False),
    "mobiliario": TipoActivoAmortizable("Mobiliario", 0.10, False),
    "otro_inmovilizado_material": TipoActivoAmortizable("Otro inmovilizado material (otros enseres)", 0.15, False),
}

TIPOS_ACTIVO_INTANGIBLE: dict[str, TipoActivoAmortizable] = {
    "aplicaciones_informaticas": TipoActivoAmortizable("Aplicaciones informáticas", 0.33, False),
    # Fondo de comercio: coeficiente NO viene de la tabla fiscal (no es inmovilizado material) —
    # viene directo de la presunción legal del PGC norma 6ª, 10 años, ver docstring del módulo.
    "fondo_comercio_y_otro_intangible": TipoActivoAmortizable("Fondo de comercio y otro intangible", 0.10, False),
}

# `inversiones_inmobiliarias` reutiliza el coeficiente de construcción comercial (oficinas/
# locales en alquiler/inversión son, por defecto, uso terciario, no industrial).
TIPO_INVERSION_INMOBILIARIA = TipoActivoAmortizable("Inversión inmobiliaria (construcción)", 0.02, True)

# Fracción de "terrenos y construcciones" que es terreno (nunca amortizable) — hipótesis de
# diseño (rango típico de tasación en España 20-30%), NO un dato del catálogo ACCID. Fija, sin
# ruido — así se aprobó explícitamente.
FRACCION_TERRENO = 0.25

# --------------------------------------------------------------------------------------------
# Perfil de reparto de sub-tipos de MATERIAL por categoría de sector (hipótesis de diseño
# razonada — el catálogo ACCID no llega a este nivel de detalle; sin acceso en este entorno a la
# Central de Balances del Banco de España para una referencia estadística externa, así que el
# razonamiento es cualitativo, declarado como tal explícitamente, no presentado como dato
# verificado). Cada perfil suma exactamente 1.0. Claves: terrenos_construcciones (se reparte
# luego 25/75 terreno/construcción con FRACCION_TERRENO), instalaciones_maquinaria,
# equipos_informaticos, elementos_transporte, mobiliario, otro_inmovilizado_material.
# --------------------------------------------------------------------------------------------
PERFIL_SUBTIPOS_MATERIAL_POR_CATEGORIA: dict[str, dict[str, float]] = {
    # Industria: naves/líneas de producción dominan; poco vehículo propio; informática mínima
    # (talleres, no oficinas).
    "industria": {
        "terrenos_construcciones": 0.35, "instalaciones_maquinaria": 0.45,
        "equipos_informaticos": 0.03, "elementos_transporte": 0.07,
        "mobiliario": 0.03, "otro_inmovilizado_material": 0.07,
    },
    # Servicios industriales (reparación, instalación, ingeniería, I+D): mezcla de taller y
    # oficina técnica.
    "servicios_industriales": {
        "terrenos_construcciones": 0.25, "instalaciones_maquinaria": 0.40,
        "equipos_informaticos": 0.08, "elementos_transporte": 0.10,
        "mobiliario": 0.05, "otro_inmovilizado_material": 0.12,
    },
    # Servicios profesionales (contabilidad/auditoría/consultoría, 69.2/70.2) y TIC
    # (programación, 62) — sub-divididos (ver #29/#33): el REPARTO de tipos de mobiliario/
    # equipo de oficina es prácticamente el mismo en ambos (mismo perfil de material para las
    # dos claves) — lo que cambia entre ellos es el peso de `material` a nivel superior (ver
    # empresa_base.PERFIL_ACTIVO_NO_CORRIENTE_POR_CATEGORIA), no la mezcla interna de material.
    "servicios_profesionales": {
        "terrenos_construcciones": 0.15, "instalaciones_maquinaria": 0.05,
        "equipos_informaticos": 0.35, "elementos_transporte": 0.05,
        "mobiliario": 0.25, "otro_inmovilizado_material": 0.15,
    },
    "servicios_tic": {
        "terrenos_construcciones": 0.15, "instalaciones_maquinaria": 0.05,
        "equipos_informaticos": 0.35, "elementos_transporte": 0.05,
        "mobiliario": 0.25, "otro_inmovilizado_material": 0.15,
    },
    # Transporte y logística: la flota ES el negocio; naves/almacenes moderados.
    "transporte_logistica": {
        "terrenos_construcciones": 0.25, "instalaciones_maquinaria": 0.15,
        "equipos_informaticos": 0.05, "elementos_transporte": 0.45,
        "mobiliario": 0.03, "otro_inmovilizado_material": 0.07,
    },
    # Comercio y hostelería: locales y mobiliario de punto de venta (tiendas, restaurantes,
    # hoteles) dominan sobre maquinaria.
    "comercio_hosteleria": {
        "terrenos_construcciones": 0.40, "instalaciones_maquinaria": 0.15,
        "equipos_informaticos": 0.08, "elementos_transporte": 0.10,
        "mobiliario": 0.20, "otro_inmovilizado_material": 0.07,
    },
    # Construcción: maquinaria pesada de obra + vehículos/flota de transporte de materiales.
    "construccion": {
        "terrenos_construcciones": 0.15, "instalaciones_maquinaria": 0.45,
        "equipos_informaticos": 0.05, "elementos_transporte": 0.25,
        "mobiliario": 0.03, "otro_inmovilizado_material": 0.07,
    },
    # Administración/educación/sanidad: edificios (colegios, hospitales) son la partida
    # abrumadora.
    "administracion_educacion_sanidad": {
        "terrenos_construcciones": 0.55, "instalaciones_maquinaria": 0.15,
        "equipos_informaticos": 0.10, "elementos_transporte": 0.03,
        "mobiliario": 0.12, "otro_inmovilizado_material": 0.05,
    },
    # Inmobiliario: el material (no las inversiones inmobiliarias, que van aparte) es casi todo
    # el inmueble en uso propio (oficinas del propio operador, no los que comercializa).
    "inmobiliario": {
        "terrenos_construcciones": 0.70, "instalaciones_maquinaria": 0.05,
        "equipos_informaticos": 0.05, "elementos_transporte": 0.03,
        "mobiliario": 0.10, "otro_inmovilizado_material": 0.07,
    },
}

# Perfil de INTANGIBLE (2 buckets): servicios profesionales/TIC con más peso en software propio
# (aplicaciones informáticas); el resto con más peso en fondo de comercio/otro intangible (su
# intangible suele venir más de una adquisición pasada que de desarrollo de software).
PERFIL_SUBTIPOS_INTANGIBLE_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "industria": {"aplicaciones_informaticas": 0.30, "fondo_comercio_y_otro_intangible": 0.70},
    "servicios_industriales": {"aplicaciones_informaticas": 0.35, "fondo_comercio_y_otro_intangible": 0.65},
    # Servicios profesionales (69.2/70.2): el poco intangible que tengan viene más de fondo de
    # comercio (fusiones/absorciones de despachos) que de software propio.
    "servicios_profesionales": {"aplicaciones_informaticas": 0.15, "fondo_comercio_y_otro_intangible": 0.85},
    # TIC (62): software/propiedad intelectual propios, con más peso que en cualquier otra
    # categoría — es el sector que genuinamente encaja con un intangible tecnológico alto.
    "servicios_tic": {"aplicaciones_informaticas": 0.40, "fondo_comercio_y_otro_intangible": 0.60},
    "transporte_logistica": {"aplicaciones_informaticas": 0.30, "fondo_comercio_y_otro_intangible": 0.70},
    "comercio_hosteleria": {"aplicaciones_informaticas": 0.30, "fondo_comercio_y_otro_intangible": 0.70},
    "construccion": {"aplicaciones_informaticas": 0.25, "fondo_comercio_y_otro_intangible": 0.75},
    "administracion_educacion_sanidad": {"aplicaciones_informaticas": 0.30, "fondo_comercio_y_otro_intangible": 0.70},
    "inmobiliario": {"aplicaciones_informaticas": 0.20, "fondo_comercio_y_otro_intangible": 0.80},
}

# Dispersión sintética sobre cada componente del perfil de sub-tipos (mismo criterio que el
# perfil de nivel superior de empresa_base.py) antes de renormalizar a 100%.
DISPERSION_PERFIL_SUBTIPO = 0.20
SUELO_COMPONENTE_SUBTIPO_PCT = 0.005

# --------------------------------------------------------------------------------------------
# Sub-lotes dentro de cada bucket amortizable — corrección aprobada: 3 sub-lotes por bucket, no
# una única cohorte (una empresa no compra toda su flota el mismo día). Reparto de valor entre
# sub-lotes con pesos CENTRO 50/30/20 (un lote grande e histórico, uno mediano, uno pequeño y
# más reciente — patrón de inversión habitual: una compra inicial grande, ampliaciones
# posteriores menores) + el mismo ruido mixto ya usado en el resto del motor, renormalizado.
# --------------------------------------------------------------------------------------------
N_SUBLOTES = 3
PESO_SUBLOTES_CENTRO = (0.50, 0.30, 0.20)
DISPERSION_PESO_SUBLOTE = 0.25
SUELO_PESO_SUBLOTE = 0.02

# Fórmula ya acordada (verificada: vida 3→1/3, vida 5→~1/7,35, vida 20→1/100 exactos).
def probabilidad_ya_amortizado(vida_util_años: float) -> float:
    multiplicador = (4 * vida_util_años + 5) / 17
    return 1.0 / (vida_util_años * multiplicador)


@dataclass(frozen=True)
class SubLoteActivo:
    """Un sub-lote de un tipo de activo — unidad mínima de amortización de este motor (ver
    docstring del módulo sobre la decisión de "cohorte/sub-lote", no activo por activo)."""

    tipo: str  # clave en TIPOS_ACTIVO_MATERIAL / TIPOS_ACTIVO_INTANGIBLE / "inversion_inmobiliaria"
    es_construccion: bool  # distinción exacta PGC nota 2.l ("construcciones" vs "resto de elementos")
    valor_bruto_eur: float
    cuota_anual_eur: float
    # Año de compra FRACCIONAL — no un año entero + una instantánea de acumulada: así
    # `acumulada_en(año)` es una única fórmula continua válida para CUALQUIER año (pasado,
    # presente o futuro respecto al año base), sin distinguir casos — el "gasto del año" sale
    # solo como la diferencia entre dos evaluaciones consecutivas de esa misma fórmula, incluido
    # el propio año base 2023 (ver corrección aplicada tras detectar que la primera versión
    # confundía "acumulada total desde la compra" con "gasto del año 2023").
    año_compra: float

    def acumulada_en(self, año: int) -> float:
        if año < self.año_compra:
            return 0.0
        return min(self.valor_bruto_eur, self.cuota_anual_eur * (año - self.año_compra))

    def gasto_en(self, año: int) -> float:
        return self.acumulada_en(año) - self.acumulada_en(año - 1)

    def totalmente_amortizado_en(self, año: int) -> bool:
        return self.acumulada_en(año) >= self.valor_bruto_eur - 1e-6

    @property
    def año_amortizacion_total(self) -> int | None:
        """Primer año (dentro de 2023-2025) en que este sub-lote queda totalmente amortizado, o
        None si no ocurre en ese rango — alimenta la futura nota de memoria (PGC punto 2.l)."""
        if self.cuota_anual_eur <= 0:
            return None
        año_exacto = self.año_compra + self.valor_bruto_eur / self.cuota_anual_eur
        año_entero = math.ceil(año_exacto - 1e-9)
        if año_entero < AÑO_BASE:
            return AÑO_BASE  # ya estaba amortizado antes de que empezara la serie — se reporta como "desde el año base"
        return año_entero if año_entero <= 2025 else None


@dataclass(frozen=True)
class BienTotalmenteAmortizado:
    """Datos que alimentan la futura nota de memoria del PGC (punto 2.l): "importe y
    características de los bienes totalmente amortizados en uso, distinguiendo entre
    construcciones y resto de elementos". No se redacta la nota en este encargo — solo se deja
    el dato disponible, estructurado, para cuando llegue esa fase."""

    tipo: str
    es_construccion: bool
    valor_bruto_eur: float
    año_amortizacion_total: int


def _entropia_amortizacion(sector: str, segmento: str, sufijo: str = "") -> int:
    return zlib.crc32(f"{sector}|{segmento}|amortizacion{sufijo}".encode("utf-8"))


def _generar_perfil_subtipos(rng: np.random.Generator, perfil_centro: dict[str, float]) -> dict[str, float]:
    """Mismo mecanismo que `empresa_base.generar_perfil_activo_no_corriente` (ruido mixto
    típico/atípico alrededor de un centro, renormalizado a 1.0) — para el reparto de sub-tipos
    dentro de material/intangible."""
    brutos: dict[str, float] = {}
    for componente, centro in perfil_centro.items():
        valor, _ = _generar_partida(rng, centro, centro * DISPERSION_PERFIL_SUBTIPO, suelo=SUELO_COMPONENTE_SUBTIPO_PCT)
        brutos[componente] = valor
    return _renormalizar_a_total(brutos, 1.0)


def _generar_sublotes(
    rng: np.random.Generator,
    tipo_key: str,
    info: TipoActivoAmortizable,
    valor_bucket_eur: float,
    año_ancla: int,
    nuevo: bool,
) -> tuple[SubLoteActivo, ...]:
    """3 sub-lotes independientes por bucket (corrección aprobada, ver docstring del módulo).
    `nuevo=True` (capex/adquisición): sin sorteo de fecha/ya-amortizado, arrancan en `año_ancla`
    con acumulada=0 — son activos recién comprados, no pueden estar ya amortizados. `nuevo=False`
    (cohortes del año base 2023): fecha de compra y "ya totalmente amortizado" sorteados por
    sub-lote, cada uno de forma independiente."""
    if valor_bucket_eur <= 0:
        return ()
    pesos_brutos: dict[int, float] = {}
    for i, centro in enumerate(PESO_SUBLOTES_CENTRO):
        valor, _ = _generar_partida(rng, centro, centro * DISPERSION_PESO_SUBLOTE, suelo=SUELO_PESO_SUBLOTE)
        pesos_brutos[i] = valor
    pesos = _renormalizar_a_total(pesos_brutos, 1.0)

    vida = info.vida_fiscal_años
    sublotes = []
    for i in range(N_SUBLOTES):
        valor_sublote_eur = pesos[i] * valor_bucket_eur
        cuota_anual_eur = valor_sublote_eur / vida
        if nuevo:
            # Capex/adquisición: tratado como comprado al INICIO del propio año del suceso, para
            # que genere un año completo de cuota YA ese año — mismo criterio de "año completo,
            # sin prorratear" que ya usa el arquetipo 18 para `ventas_inorganicas_eur`.
            año_compra = float(año_ancla) - 1.0
        else:
            años_transcurridos = rng.uniform(0.0, vida)
            ya_amortizado = rng.random() < probabilidad_ya_amortizado(vida)
            # "Ya totalmente amortizado" = comprado bastante antes de que ninguna evaluación
            # dentro de 2023-2025 pueda verlo todavía generando gasto (un año más de margen que
            # la propia vida fiscal, para que ni siquiera el año base 2022→2023 implícito lo
            # capture like en curso).
            año_compra = (AÑO_BASE - vida - 1.0) if ya_amortizado else (AÑO_BASE - años_transcurridos)
        sublotes.append(SubLoteActivo(tipo_key, info.es_construccion, valor_sublote_eur, cuota_anual_eur, año_compra))
    return tuple(sublotes)


def _tipo_construccion_material(categoria: str) -> str:
    """Uso industrial (naves) para categorías intensivas en producción/obra/flota física; uso
    comercial/administrativo (oficinas, locales) para el resto."""
    if categoria in {"industria", "construccion", "transporte_logistica"}:
        return "construcciones_industriales"
    return "construcciones_comerciales"


def _generar_bucket_material_e_intangible(
    rng: np.random.Generator,
    categoria: str,
    perfil_material: dict[str, float],
    perfil_intangible: dict[str, float],
    material_eur: float,
    intangible_eur: float,
    inversiones_inmobiliarias_eur: float,
    año_ancla: int,
    nuevo: bool,
) -> tuple[SubLoteActivo, ...]:
    coleccion: list[SubLoteActivo] = []

    valor_terrenos_construcciones_eur = perfil_material["terrenos_construcciones"] * material_eur
    valor_construccion_material_eur = valor_terrenos_construcciones_eur * (1 - FRACCION_TERRENO)
    tipo_construccion = _tipo_construccion_material(categoria)
    coleccion += _generar_sublotes(
        rng, tipo_construccion, TIPOS_ACTIVO_MATERIAL[tipo_construccion], valor_construccion_material_eur, año_ancla, nuevo
    )
    for tipo_key in ("instalaciones_maquinaria", "equipos_informaticos", "elementos_transporte", "mobiliario", "otro_inmovilizado_material"):
        valor_bucket_eur = perfil_material[tipo_key] * material_eur
        coleccion += _generar_sublotes(rng, tipo_key, TIPOS_ACTIVO_MATERIAL[tipo_key], valor_bucket_eur, año_ancla, nuevo)

    for tipo_key in ("aplicaciones_informaticas", "fondo_comercio_y_otro_intangible"):
        valor_bucket_eur = perfil_intangible[tipo_key] * intangible_eur
        coleccion += _generar_sublotes(rng, tipo_key, TIPOS_ACTIVO_INTANGIBLE[tipo_key], valor_bucket_eur, año_ancla, nuevo)

    valor_construccion_ii_eur = inversiones_inmobiliarias_eur * (1 - FRACCION_TERRENO)
    coleccion += _generar_sublotes(
        rng, "inversion_inmobiliaria", TIPO_INVERSION_INMOBILIARIA, valor_construccion_ii_eur, año_ancla, nuevo
    )
    return tuple(coleccion)


def generar_coleccion_y_perfiles_base(
    sector: str, segmento: str, semilla: int, categoria: str, activo_no_corriente_desglose_eur: dict[str, float]
) -> tuple[tuple[SubLoteActivo, ...], dict[str, float], dict[str, float]]:
    """Colección de sub-lotes del año base (2023) + los perfiles de sub-tipo generados (se
    devuelven para reutilizarlos, sin volver a sortear, cuando el arquetipo 18 -adquisición-
    genere cohortes nuevas con "el perfil completo de la categoría"). RNG propio e
    independiente del resto del motor (sector+segmento+semilla) — no desplaza ningún sorteo ya
    existente en `empresa_base.py`/`evolucion_arquetipo.py`."""
    rng = np.random.default_rng([semilla, _entropia_amortizacion(sector, segmento)])
    perfil_material = _generar_perfil_subtipos(rng, PERFIL_SUBTIPOS_MATERIAL_POR_CATEGORIA[categoria])
    perfil_intangible = _generar_perfil_subtipos(rng, PERFIL_SUBTIPOS_INTANGIBLE_POR_CATEGORIA[categoria])
    coleccion = _generar_bucket_material_e_intangible(
        rng, categoria, perfil_material, perfil_intangible,
        activo_no_corriente_desglose_eur["material"],
        activo_no_corriente_desglose_eur["intangible"],
        activo_no_corriente_desglose_eur["inversiones_inmobiliarias"],
        AÑO_BASE, nuevo=False,
    )
    return coleccion, perfil_material, perfil_intangible


def generar_cohortes_capex(sector: str, segmento: str, semilla: int, año: int, incremento_eur: float) -> tuple[SubLoteActivo, ...]:
    """Arquetipo 17 (capex): el 100% del incremento se trata como inversión productiva típica —
    instalaciones técnicas y maquinaria — con `año_ancla` = el propio año del capex (activos
    recién comprados, sin sorteo de fecha/ya-amortizado)."""
    if incremento_eur <= 0:
        return ()
    rng = np.random.default_rng([semilla, _entropia_amortizacion(sector, segmento, f"_capex_{año}")])
    info = TIPOS_ACTIVO_MATERIAL["instalaciones_maquinaria"]
    return _generar_sublotes(rng, "instalaciones_maquinaria", info, incremento_eur, año, nuevo=True)


def generar_cohortes_adquisicion(
    sector: str, segmento: str, semilla: int, año: int, incremento_eur: float, categoria: str,
    perfil_top: dict[str, float], perfil_material: dict[str, float], perfil_intangible: dict[str, float],
) -> tuple[SubLoteActivo, ...]:
    """Arquetipo 18 (adquisición): perfil COMPLETO de la categoría — se compra un negocio
    entero, con la mezcla de activo habitual del sector (los mismos perfiles ya generados para
    el caso, no un sorteo nuevo) — `año_ancla` = AÑO_ADQUISICION, sin sorteo de fecha/ya-
    amortizado (activos recién incorporados vía la operación)."""
    if incremento_eur <= 0:
        return ()
    rng = np.random.default_rng([semilla, _entropia_amortizacion(sector, segmento, f"_adquisicion_{año}")])
    material_eur = perfil_top["material"] * incremento_eur
    intangible_eur = perfil_top["intangible"] * incremento_eur
    inversiones_inmobiliarias_eur = perfil_top["inversiones_inmobiliarias"] * incremento_eur
    # otros_financieros: nunca amortizable — su parte del incremento no genera sub-lotes.
    return _generar_bucket_material_e_intangible(
        rng, categoria, perfil_material, perfil_intangible,
        material_eur, intangible_eur, inversiones_inmobiliarias_eur, año, nuevo=True,
    )


def amortizacion_eur_del_año(coleccion: tuple[SubLoteActivo, ...], año: int) -> float:
    return sum(sl.gasto_en(año) for sl in coleccion)


def amortizacion_acumulada_total_eur(coleccion: tuple[SubLoteActivo, ...], año: int) -> float:
    return sum(sl.acumulada_en(año) for sl in coleccion)


def bienes_totalmente_amortizados_en(coleccion: tuple[SubLoteActivo, ...], año: int) -> tuple[BienTotalmenteAmortizado, ...]:
    resultado = []
    for sl in coleccion:
        if sl.año_amortizacion_total is not None and sl.año_amortizacion_total <= año:
            resultado.append(BienTotalmenteAmortizado(sl.tipo, sl.es_construccion, sl.valor_bruto_eur, sl.año_amortizacion_total))
    return tuple(resultado)


# --------------------------------------------------------------------------------------------
# Bajas anticipadas de sub-lotes — línea oficial "11. Deterioro y resultado por enajenaciones
# del inmovilizado" del modelo PGC de PyG. Discutido y aprobado explícitamente con el usuario
# (sin dato externo que lo ancle, misma honestidad ya aplicada a `FRACCION_TERRENO` o al
# reparto 50/30/20 de sub-lotes): cada año, cada sub-lote TODAVÍA VIVO (valor en libros > 0) de
# la colección YA EXISTENTE al empezar el año (no las cohortes nuevas de capex/adquisición de
# ESE mismo año — un activo recién comprado no está en riesgo de baja el mismo año en que se
# compra, mismo criterio que `nuevo=True` en `_generar_sublotes`) tiene una probabilidad
# pequeña e independiente de sufrir una baja anticipada:
#
# - **Deterioro** (50%): pérdida total del valor en libros, SIN contrapartida de caja.
# - **Enajenación** (50%, elección neutra sin ancla externa — ver arriba): venta por un precio
#   = valor en libros REAL en ese momento (no un % sectorial) x un factor aleatorio simétrico,
#   con contrapartida de caja real.
#
# El sub-lote sigue amortizando con normalidad el propio año de la baja (mismo criterio "año
# completo, sin prorratear" que ya usa este módulo para capex/adquisición) — se retira de la
# colección a partir del año SIGUIENTE, ver `excluir_bajas`.
# --------------------------------------------------------------------------------------------
PROBABILIDAD_BAJA_ANTICIPADA_ANUAL = 0.01
FRACCION_DETERIORO_VS_ENAJENACION = 0.5
RANGO_FACTOR_PRECIO_VENTA = (0.70, 1.30)


@dataclass(frozen=True)
class BajaSubLoteActivo:
    """Una baja anticipada de un sub-lote. `resultado_eur = valor_venta_eur - valor_en_libros_eur`
    (positivo = plusvalía, negativo = minusvalía o deterioro puro, cuando `valor_venta_eur=0.0`)."""

    sublote: SubLoteActivo
    tipo: str  # "deterioro" | "enajenacion"
    valor_en_libros_eur: float
    valor_venta_eur: float  # 0.0 si es deterioro (sin contrapartida de caja)
    resultado_eur: float


def sortear_bajas_del_año(
    sector: str, segmento: str, semilla: int, coleccion: tuple[SubLoteActivo, ...], año: int
) -> tuple[BajaSubLoteActivo, ...]:
    """Sortea qué sub-lotes de `coleccion` (la colección YA EXISTENTE al empezar `año`, sin las
    cohortes nuevas de capex/adquisición de ese mismo año) sufren una baja anticipada este año.
    RNG propio e independiente por año (`_bajas_{año}`, mismo patrón que `_capex_{año}`/
    `_adquisicion_{año}`) — no desplaza ningún otro sorteo del módulo."""
    rng = np.random.default_rng([semilla, _entropia_amortizacion(sector, segmento, f"_bajas_{año}")])
    bajas: list[BajaSubLoteActivo] = []
    for sl in coleccion:
        valor_en_libros_eur = sl.valor_bruto_eur - sl.acumulada_en(año)
        if valor_en_libros_eur <= 1e-6:
            continue  # ya totalmente amortizado: sin magnitud real que dar de baja
        if rng.random() >= PROBABILIDAD_BAJA_ANTICIPADA_ANUAL:
            continue
        if rng.random() < FRACCION_DETERIORO_VS_ENAJENACION:
            tipo = "deterioro"
            valor_venta_eur = 0.0
        else:
            tipo = "enajenacion"
            factor = rng.uniform(*RANGO_FACTOR_PRECIO_VENTA)
            valor_venta_eur = valor_en_libros_eur * factor
        resultado_eur = valor_venta_eur - valor_en_libros_eur
        bajas.append(BajaSubLoteActivo(sl, tipo, valor_en_libros_eur, valor_venta_eur, resultado_eur))
    return tuple(bajas)


def excluir_bajas(coleccion: tuple[SubLoteActivo, ...], bajas: tuple[BajaSubLoteActivo, ...]) -> tuple[SubLoteActivo, ...]:
    """Colección sin los sub-lotes dados de baja este año — dejan de generar gasto de
    amortización a partir del año SIGUIENTE (el propio año de la baja ya cargó su cuota
    completa, calculada con la colección ANTES de excluir — ver `evolucion_arquetipo._evaluar`)."""
    if not bajas:
        return coleccion
    dados_de_baja = {baja.sublote for baja in bajas}
    return tuple(sl for sl in coleccion if sl not in dados_de_baja)


def resultado_bajas_eur(bajas: tuple[BajaSubLoteActivo, ...]) -> float:
    return sum(baja.resultado_eur for baja in bajas)


def valor_en_libros_bajas_eur(bajas: tuple[BajaSubLoteActivo, ...]) -> float:
    return sum(baja.valor_en_libros_eur for baja in bajas)


def valor_venta_bajas_eur(bajas: tuple[BajaSubLoteActivo, ...]) -> float:
    return sum(baja.valor_venta_eur for baja in bajas)
