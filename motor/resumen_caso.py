"""Resumen consolidado de particularidades de un caso ya generado — capa de AGREGACIÓN pura,
mismo criterio que `motor.clasificacion_legal`/`motor.efe`/`motor.ecpn`: no genera ni corrige
ningún dato, solo lee lo que `EvolucionArquetipo`/`EjercicioEmpresa` ya exponen y lo consolida en
un único objeto por caso, para que el formador pueda ver de un vistazo qué particularidades tiene
sin saber dónde busca cada dato por separado.

Nace de una auditoría explícita (sección 2.15 de la especificación + Ronda 1, Fase 4) sobre lo
que ya existía disperso por el motor:

1. **Señales de riesgo por mecanismo** (`riesgo_endeudamiento`, `contencion_al_limite`,
   `riesgo_plausibilidad_pyg`, `pyg_contencion_al_limite`) — las únicas 4 señales de riesgo
   booleanas de `EjercicioEmpresa` (auditadas explícitamente, no solo las 2 más conocidas).
   `contencion_al_limite`/`pyg_contencion_al_limite` NUNCA aparecen sin su señal "padre" (son
   `True` solo dentro de la rama de código que ya puso `riesgo_endeudamiento`/`riesgo_
   plausibilidad_pyg` a `True` — verificado en el propio código, no asumido), así que se
   representan como contexto de la señal, no como una señal independiente.
2. **`PlausibilidadCaso`** (sección 2.13) — expuesto tal cual, sin reprocesar.
3. **Notas de memoria** — combina `EjercicioEmpresa.notas_memoria` (10/16/18, por año) y
   `EvolucionArquetipo.notas_memoria_pura` (7/19/20/21/22, a nivel de caso — vacío si el caso se
   generó con `generar_evolucion_combinada`/`generar_evolucion_arquetipo` en vez de `motor.
   memoria.generar_caso_combinado`, que es quien las puebla).
4. **Movimiento anual** de provisiones, insolvencias y bienes totalmente amortizados — ya
   expuesto en `EjercicioEmpresa`, aquí solo se filtra a los casos donde el mecanismo está
   realmente activo (evita listar 3 años de ceros para un caso que nunca tuvo provisión).
5. **Modo típico/atípico por partida** — auditoría que SÍ encontró una inconsistencia real (no
   solo una ausencia de agregación): los perfiles de existencias/deudores/acreedores/deudas
   financieras de los lotes de desglose de balance, `ROE_caso` del payout de dividendos, y
   (encontrados de paso, ANTERIORES a los lotes — decisiones #24-25) el perfil de `activo_no_
   corriente`, las 3 periodificaciones y `capital_social`, descartaban el modo con
   `_generar_partida(...) -> valor, _`, mientras que las masas de nivel superior y las
   primitivas de PyG (diseño original) sí lo exponían en `modos`. **Corregido en origen, los 8
   sitios** (`motor/empresa_base.py`, `motor/evolucion_arquetipo.py`) — ver CLAUDE.md, sección
   "Trazabilidad, resumen de particularidades, rúbrica de diagnóstico y similitud entre casos",
   para el detalle completo de la auditoría. Provisiones/insolvencias/subvenciones de fondo NO
   tienen este problema: sortean con `rng.uniform`/`rng.choice` directos (sin ancla de catálogo
   Huber/MAD), así que no existe un "modo típico/atípico" que exponer para ellos — no es una
   ausencia, es que el concepto no aplica a ese tipo de sorteo.

Solo se listan las partidas **atípicas** (no las tres decenas de partidas típicas de cualquier
caso) — es lo que hace que la lista sea una lista de "particularidades", no una copia de `modos`
entero. Las partidas forzadas por un arquetipo (modo `"arquetipo"`) o derivadas (`"derivado"`,
amortización) no se listan aquí: no son un sorteo atípico, son una huella ya visible a través del
propio arquetipo activo o del cálculo derivado — listarlas duplicaría información sin añadir
nada que el formador no supiera ya.

Base de datos para la futura ficha de solución del formador (sección 2.9): esa ficha necesitará,
para cada caso, exactamente esta consolidación (qué salió atípico y dónde, qué señales de riesgo
se activaron y por qué, qué notas de memoria aparecen y a qué se deben) — este módulo es la
capa que la alimentará, no una funcionalidad aparte."""

from __future__ import annotations

from dataclasses import dataclass

from motor.amortizacion import BienTotalmenteAmortizado, bienes_totalmente_amortizados_en
from motor.evolucion_arquetipo import EjercicioEmpresa, EvolucionArquetipo, NotaMemoria, PlausibilidadCaso

# Prefijos de `EjercicioEmpresa.modos` que son PER-AÑO (un sorteo nuevo cada ejercicio — hoy,
# solo las primitivas de PyG, incluido `pyg.tipo_interes`). Cualquier otro prefijo es un rasgo
# "sorteado una vez por caso, fijo desde 2023" (masas de balance de nivel superior, perfiles de
# los lotes de desglose, `rotacion_activo`, `caso.roe`, `activo_no_corriente.*`,
# `periodificacion_*`, `capital_social`) — se reporta con `año=None`, no con el año del ejercicio
# que por casualidad lo trae en su propio `modos` (año base, o el año en que se creó el objeto):
# etiquetarlo con un año concreto sugeriría un fenómeno de ESE año, cuando en realidad describe a
# la empresa entera durante los 3 ejercicios.
_PREFIJO_MODO_POR_AÑO = "pyg."


@dataclass(frozen=True)
class ItemModoAtipico:
    """Una partida cuyo sorteo salió atípico (85%/15% típico/atípico, ver `motor.ruido`) — nunca
    un error, es el propio diseño del ruido mixto esperando atípicos reales; se reporta aquí
    porque es justo el tipo de particularidad que un formador querría ver de un vistazo."""

    partida: str  # clave de `EjercicioEmpresa.modos`, p.ej. "pyg.consumos_explotacion" o "existencias.materias_primas"
    año: int | None  # año concreto (partidas de PyG) o None (rasgo fijo desde 2023, ver arriba)


@dataclass(frozen=True)
class SeñalRiesgoCaso:
    """Una activación de una de las 4 señales de riesgo booleanas de `EjercicioEmpresa` (ver
    docstring del módulo) — `detalle` trae el contexto numérico que explica el "por qué", para no
    obligar a volver a `EjercicioEmpresa` a buscarlo."""

    tipo: str  # "riesgo_endeudamiento" | "riesgo_plausibilidad_pyg"
    año: int
    detalle: dict[str, object]


@dataclass(frozen=True)
class NotaMemoriaCaso:
    """Una nota de memoria con su año de origen — `año=None` para las de `clase="memoria_pura"`
    (7/19/20/21/22, `EvolucionArquetipo.notas_memoria_pura`): no pertenecen a un ejercicio
    concreto, describen al caso completo (mismo criterio que `NotaMemoria` en el propio motor)."""

    nota: NotaMemoria
    año: int | None


@dataclass(frozen=True)
class MovimientoProvisionAño:
    año: int
    categoria: str
    naturaleza_pyg: str
    saldo_largo_eur: float
    saldo_corto_eur: float
    dotacion_eur: float
    aplicacion_eur: float
    exceso_eur: float


@dataclass(frozen=True)
class MovimientoInsolvenciaAño:
    año: int
    saldo_eur: float
    dotacion_eur: float
    aplicacion_eur: float
    exceso_eur: float
    deduccion_realizable_eur: float  # lo que de verdad resta de `realizable` (ver motor.insolvencias)


@dataclass(frozen=True)
class BienAmortizadoCasoAño:
    año: int  # año en que el bien quedó totalmente amortizado
    bien: BienTotalmenteAmortizado


@dataclass(frozen=True)
class ResumenParticularidadesCaso:
    """Objeto único por caso — ver docstring del módulo. Los 5 primeros campos (además de
    `semilla`) son los 5 exigidos por la sección 2.15 (trazabilidad): `arquetipo`/`intensidad` ya
    vienen del propio `EvolucionArquetipo`, que desde la corrección de esta misma auditoría
    incluye TAMBIÉN los arquetipos de `clase="memoria_pura"` cuando el caso se generó con
    `motor.memoria.generar_caso_combinado` (antes, un caso combinado con algún arquetipo de
    memoria pura activo dejaba esos 2 campos incompletos — ver `motor/memoria.py`)."""

    sector_codigo: str
    sector_nombre: str
    segmento: str
    arquetipo: str
    intensidad: str
    semilla: int
    catalogo_version: str
    pgc_version: str

    atipicos: tuple[ItemModoAtipico, ...]
    señales_riesgo: tuple[SeñalRiesgoCaso, ...]
    plausibilidad: PlausibilidadCaso | None
    notas_memoria: tuple[NotaMemoriaCaso, ...]
    movimiento_provision: tuple[MovimientoProvisionAño, ...]
    movimiento_insolvencia: tuple[MovimientoInsolvenciaAño, ...]
    bienes_totalmente_amortizados: tuple[BienAmortizadoCasoAño, ...]

    @property
    def tiene_particularidades(self) -> bool:
        return bool(
            self.atipicos
            or self.señales_riesgo
            or (self.plausibilidad is not None and self.plausibilidad.tiene_señales)
            or self.notas_memoria
            or self.movimiento_provision
            or self.movimiento_insolvencia
            or self.bienes_totalmente_amortizados
        )


def _atipicos_de_ejercicio(año: int, ejercicio: EjercicioEmpresa) -> list[ItemModoAtipico]:
    return [
        ItemModoAtipico(partida=partida, año=(año if partida.startswith(_PREFIJO_MODO_POR_AÑO) else None))
        for partida, modo in ejercicio.modos.items()
        if modo == "atipico"
    ]


def _señales_de_ejercicio(año: int, ejercicio: EjercicioEmpresa) -> list[SeñalRiesgoCaso]:
    señales: list[SeñalRiesgoCaso] = []
    if ejercicio.riesgo_endeudamiento:
        señales.append(
            SeñalRiesgoCaso(
                tipo="riesgo_endeudamiento",
                año=año,
                detalle={
                    "endeudamiento_sin_contener": ejercicio.endeudamiento_sin_contener,
                    "endeudamiento_final": ejercicio.endeudamiento,
                    "deterioro_aplicado_eur": ejercicio.deterioro_aplicado_eur,
                    "contencion_al_limite": ejercicio.contencion_al_limite,
                },
            )
        )
    if ejercicio.riesgo_plausibilidad_pyg:
        señales.append(
            SeñalRiesgoCaso(
                tipo="riesgo_plausibilidad_pyg",
                año=año,
                detalle={
                    "pyg_subtotales_sin_contener": dict(ejercicio.pyg_subtotales_sin_contener),
                    "pyg_contencion_al_limite": ejercicio.pyg_contencion_al_limite,
                },
            )
        )
    return señales


def resumen_particularidades_caso(evolucion: EvolucionArquetipo) -> ResumenParticularidadesCaso:
    """Consolida las particularidades de un caso YA generado — ver docstring del módulo. Acepta
    tanto el resultado de `generar_evolucion_combinada`/`generar_evolucion_arquetipo` (sin
    `notas_memoria_pura`, campo vacío por defecto) como el de `motor.memoria.generar_caso_
    combinado` (con `notas_memoria_pura` ya poblado, si el caso tenía algún arquetipo de esa
    clase activo)."""
    atipicos: list[ItemModoAtipico] = []
    señales_riesgo: list[SeñalRiesgoCaso] = []
    notas: list[NotaMemoriaCaso] = []
    movimiento_provision: list[MovimientoProvisionAño] = []
    movimiento_insolvencia: list[MovimientoInsolvenciaAño] = []
    bienes_amortizados: list[BienAmortizadoCasoAño] = []

    provision_en_el_caso = any(ej.provision_activa for ej in evolucion.ejercicios.values())
    insolvencia_en_el_caso = any(ej.insolvencia_activa for ej in evolucion.ejercicios.values())
    año_base = min(evolucion.ejercicios)  # nunca hay provisión/insolvencia dotada ahí — se excluye del movimiento anual

    for año, ejercicio in sorted(evolucion.ejercicios.items()):
        atipicos.extend(_atipicos_de_ejercicio(año, ejercicio))
        señales_riesgo.extend(_señales_de_ejercicio(año, ejercicio))
        notas.extend(NotaMemoriaCaso(nota=nota, año=año) for nota in ejercicio.notas_memoria)

        if provision_en_el_caso and año != año_base:
            movimiento_provision.append(
                MovimientoProvisionAño(
                    año=año,
                    categoria=ejercicio.provision_categoria,
                    naturaleza_pyg=ejercicio.provision_naturaleza_pyg,
                    saldo_largo_eur=ejercicio.provision_saldo_largo_eur,
                    saldo_corto_eur=ejercicio.provision_saldo_corto_eur,
                    dotacion_eur=ejercicio.provision_dotacion_eur,
                    aplicacion_eur=ejercicio.provision_aplicacion_eur,
                    exceso_eur=ejercicio.provision_exceso_eur,
                )
            )
        if insolvencia_en_el_caso and año != año_base:
            movimiento_insolvencia.append(
                MovimientoInsolvenciaAño(
                    año=año,
                    saldo_eur=ejercicio.insolvencia_saldo_eur,
                    dotacion_eur=ejercicio.insolvencia_dotacion_eur,
                    aplicacion_eur=ejercicio.insolvencia_aplicacion_eur,
                    exceso_eur=ejercicio.insolvencia_exceso_eur,
                    deduccion_realizable_eur=ejercicio.insolvencia_deduccion_realizable_eur,
                )
            )

        for bien in bienes_totalmente_amortizados_en(ejercicio.coleccion_activos_amortizables, año):
            if bien.año_amortizacion_total == año:
                bienes_amortizados.append(BienAmortizadoCasoAño(año=año, bien=bien))

    notas.extend(NotaMemoriaCaso(nota=nota, año=None) for nota in evolucion.notas_memoria_pura)
    notas.sort(key=lambda n: (n.año if n.año is not None else -1, n.nota.numero))

    return ResumenParticularidadesCaso(
        sector_codigo=evolucion.sector_codigo,
        sector_nombre=evolucion.sector_nombre,
        segmento=evolucion.segmento,
        arquetipo=evolucion.arquetipo,
        intensidad=evolucion.intensidad,
        semilla=evolucion.semilla,
        catalogo_version=evolucion.catalogo_version,
        pgc_version=evolucion.pgc_version,
        atipicos=tuple(atipicos),
        señales_riesgo=tuple(señales_riesgo),
        plausibilidad=evolucion.plausibilidad,
        notas_memoria=tuple(notas),
        movimiento_provision=tuple(movimiento_provision),
        movimiento_insolvencia=tuple(movimiento_insolvencia),
        bienes_totalmente_amortizados=tuple(bienes_amortizados),
    )
