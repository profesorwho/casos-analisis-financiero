"""Carga de la rúbrica de corrección del diagnóstico (`data/rubrica_diagnostico.json`, sección
2.19 de la especificación) como datos tipados — mismo criterio que `motor.arquetipos`: NINGUNA
lógica de generación ni de cálculo financiero aquí, solo la estructura de datos y su validación.
La rúbrica puntúa la ficha de diagnóstico ya existente (HECHO → CÁLCULO → HIPÓTESIS → EVIDENCIA
NECESARIA → IMPACTO → PRIORIDAD → RECOMENDACIÓN, sección 2.10) — es contenido estructurado
genérico (una única rúbrica, no una por arquetipo); la conexión con el arquetipo concreto de cada
caso vive en `SECCIONES_ESPERADAS`/`conexion_conclusion_esperada`, que remite a `docs/guia_
docente_arquetipos.md` en vez de duplicar su contenido aquí."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

RUTA_RUBRICA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "data" / "rubrica_diagnostico.json"

# Los 7 pasos de la ficha de diagnóstico (sección 2.10) — toda la rúbrica debe cubrir EXACTAMENTE
# estos 7, ni de más ni de menos, en este orden.
SECCIONES_ESPERADAS = ("hecho", "calculo", "hipotesis", "evidencia_necesaria", "impacto", "prioridad", "recomendacion")

TOLERANCIA_SUMA_PUNTOS = 1e-6


class RubricaInvalidaError(ValueError):
    """La rúbrica de diagnóstico no tiene la forma esperada, o sus puntos no cuadran."""


@dataclass(frozen=True)
class NivelRubrica:
    nivel: str  # "completo" | "parcial" | "insuficiente" (u otro nombre, no se restringe la lista)
    fraccion_puntos: float  # ∈ [0, 1] — se multiplica por `SeccionRubrica.puntos_maximos`
    descripcion: str


@dataclass(frozen=True)
class SeccionRubrica:
    id: str
    nombre: str
    orden: int
    puntos_maximos: float
    descripcion: str
    niveles: tuple[NivelRubrica, ...]

    def puntos_de(self, nivel: str) -> float:
        """Puntuación de esta sección para el nivel indicado (`nivel` debe ser uno de los
        `NivelRubrica.nivel` de esta sección) — helper puro, sin corregir nada por sí mismo (la
        corrección la hace el formador o una capa futura, no este módulo)."""
        for n in self.niveles:
            if n.nivel == nivel:
                return n.fraccion_puntos * self.puntos_maximos
        raise RubricaInvalidaError(f"Sección '{self.id}': nivel '{nivel}' no existe. Disponibles: {[n.nivel for n in self.niveles]}")


@dataclass(frozen=True)
class RubricaDiagnostico:
    version: int
    puntuacion_total: float
    secciones: tuple[SeccionRubrica, ...]
    conexion_conclusion_esperada: dict
    error_habitual_como_penalizacion: dict
    notas_de_aplicacion: tuple[str, ...]

    def seccion(self, id_seccion: str) -> SeccionRubrica:
        for s in self.secciones:
            if s.id == id_seccion:
                return s
        raise RubricaInvalidaError(f"Sección '{id_seccion}' no existe. Disponibles: {[s.id for s in self.secciones]}")

    def puntuacion_maxima_posible(self) -> float:
        return sum(s.puntos_maximos for s in self.secciones)


def _construir_nivel(bruto: dict, seccion_id: str, indice: int) -> NivelRubrica:
    nivel = bruto.get("nivel")
    fraccion = bruto.get("fraccion_puntos")
    descripcion = bruto.get("descripcion")
    if not nivel:
        raise RubricaInvalidaError(f"Sección '{seccion_id}': nivel #{indice} sin 'nivel'")
    if fraccion is None or not (0.0 <= float(fraccion) <= 1.0):
        raise RubricaInvalidaError(f"Sección '{seccion_id}', nivel '{nivel}': fraccion_puntos={fraccion!r} debe estar en [0, 1]")
    if not descripcion:
        raise RubricaInvalidaError(f"Sección '{seccion_id}', nivel '{nivel}' sin 'descripcion'")
    return NivelRubrica(nivel=nivel, fraccion_puntos=float(fraccion), descripcion=descripcion)


def _construir_seccion(bruto: dict) -> SeccionRubrica:
    seccion_id = bruto.get("id")
    if seccion_id not in SECCIONES_ESPERADAS:
        raise RubricaInvalidaError(f"Sección con id='{seccion_id}' no reconocida. Debe ser una de: {SECCIONES_ESPERADAS}")
    puntos_maximos = bruto.get("puntos_maximos")
    if puntos_maximos is None or float(puntos_maximos) <= 0:
        raise RubricaInvalidaError(f"Sección '{seccion_id}': puntos_maximos={puntos_maximos!r} debe ser positivo")
    niveles_brutos = bruto.get("niveles", [])
    if not niveles_brutos:
        raise RubricaInvalidaError(f"Sección '{seccion_id}': no tiene ningún nivel")
    niveles = tuple(_construir_nivel(n, seccion_id, i) for i, n in enumerate(niveles_brutos))
    if not any(n.fraccion_puntos == 1.0 for n in niveles):
        raise RubricaInvalidaError(f"Sección '{seccion_id}': ningún nivel alcanza fraccion_puntos=1.0 (el máximo de la sección sería inalcanzable)")
    return SeccionRubrica(
        id=seccion_id,
        nombre=bruto.get("nombre", seccion_id),
        orden=bruto.get("orden", -1),
        puntos_maximos=float(puntos_maximos),
        descripcion=bruto.get("descripcion", ""),
        niveles=niveles,
    )


def cargar_rubrica_diagnostico(ruta: str | Path = RUTA_RUBRICA_POR_DEFECTO) -> RubricaDiagnostico:
    """Carga y valida `data/rubrica_diagnostico.json`. Comprueba, además de la forma de cada
    campo: que están las 7 secciones de la ficha de diagnóstico (ni de más ni de menos, sección
    2.10), sin duplicados, en orden 1-7 consecutivo, y que la suma de `puntos_maximos` coincide
    EXACTO con `puntuacion_total` (si no, la rúbrica no sumaría 100 aunque cada respuesta fuera
    'completo' en todo — un error de diseño de la rúbrica, no algo que deba descubrirse corrigiendo
    exámenes)."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra la rúbrica de diagnóstico en: {ruta}")

    datos = json.loads(ruta.read_text(encoding="utf-8"))

    puntuacion_total = datos.get("puntuacion_total")
    if puntuacion_total is None or float(puntuacion_total) <= 0:
        raise RubricaInvalidaError(f"puntuacion_total={puntuacion_total!r} debe ser positivo")

    secciones = tuple(_construir_seccion(bruto) for bruto in datos.get("secciones", []))

    ids_vistos = [s.id for s in secciones]
    if len(ids_vistos) != len(set(ids_vistos)):
        raise RubricaInvalidaError(f"Hay secciones duplicadas: {ids_vistos}")
    if set(ids_vistos) != set(SECCIONES_ESPERADAS):
        faltan = set(SECCIONES_ESPERADAS) - set(ids_vistos)
        sobran = set(ids_vistos) - set(SECCIONES_ESPERADAS)
        raise RubricaInvalidaError(f"La rúbrica no cubre exactamente las 7 secciones esperadas. Faltan: {faltan or 'ninguna'}. Sobran: {sobran or 'ninguna'}")

    ordenes = sorted(s.orden for s in secciones)
    if ordenes != list(range(1, len(SECCIONES_ESPERADAS) + 1)):
        raise RubricaInvalidaError(f"Los campos 'orden' de las secciones deben ser 1..{len(SECCIONES_ESPERADAS)} sin huecos ni repetidos: {ordenes}")

    suma_puntos = sum(s.puntos_maximos for s in secciones)
    if abs(suma_puntos - float(puntuacion_total)) > TOLERANCIA_SUMA_PUNTOS:
        raise RubricaInvalidaError(
            f"La suma de puntos_maximos de las secciones ({suma_puntos}) no coincide con puntuacion_total ({puntuacion_total})"
        )

    secciones_ordenadas = tuple(sorted(secciones, key=lambda s: s.orden))

    return RubricaDiagnostico(
        version=datos.get("version", -1),
        puntuacion_total=float(puntuacion_total),
        secciones=secciones_ordenadas,
        conexion_conclusion_esperada=datos.get("conexion_conclusion_esperada", {}),
        error_habitual_como_penalizacion=datos.get("error_habitual_como_penalizacion", {}),
        notas_de_aplicacion=tuple(datos.get("notas_de_aplicacion", [])),
    )
