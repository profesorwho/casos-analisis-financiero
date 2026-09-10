"""Carga de las definiciones de arquetipos (`data/arquetipos.json`) como datos tipados.

Este módulo NO contiene lógica de generación — solo la estructura de datos y su validación.
El mecanismo que interpreta cada tipo de efecto vive en `motor/evolucion_arquetipo.py`, que es
donde se decide, para cada `tipo`, qué función genérica del motor lo aplica.

Por qué JSON y no un diccionario Python embebido en el código: para que un arquetipo nuevo se
pueda añadir editando datos (como ya se hace con el catálogo de ratios en `data/`), sin tocar
ningún `.py` ni arriesgarse a que se cuele lógica de negocio dentro de lo que debería ser una
tabla — que es exactamente lo que pasó con el arquetipo 1 en su primera versión, hardcodeada
en `evolucion_arquetipo.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

RUTA_ARQUETIPOS_POR_DEFECTO = Path(__file__).resolve().parent.parent / "data" / "arquetipos.json"

TIPOS_EFECTO_VALIDOS = frozenset(
    {
        "masa_circulante",
        "pyg_primitiva",
        "apalancamiento",
        "tesoreria",
        "reclasificacion_deuda",
        "evento_puntual",
        "capex",
        "adquisicion",
    }
)
FORMULAS_MASA_CIRCULANTE_VALIDAS = frozenset({"rotacion", "dias"})
VARIABLES_MASA_CIRCULANTE_VALIDAS = frozenset({"existencias", "realizable", "acreedores_comerciales"})


class ArquetipoInvalidoError(ValueError):
    """La definición de un arquetipo no tiene la forma esperada."""


@dataclass(frozen=True)
class EfectoMasaCirculante:
    """Desvía una masa de circulante (existencias, realizable) a través de su ratio ancla.

    formula="rotacion": masa_eur = ventas / ratio (p. ej. rotación de existencias).
    formula="dias": masa_eur = ratio / 365 * ventas (p. ej. plazo de cobro).
    `direccion` se aplica al RATIO, no a la masa (dirección -1 en rotación = existencias suben).
    """

    variable: str
    formula: str
    ratio_catalogo: str
    direccion: int


@dataclass(frozen=True)
class EfectoPygPrimitiva:
    """Desvía una partida primitiva de la PyG (% sobre ingresos de explotación), con
    continuidad año a año igual que las masas de circulante."""

    primitiva: str
    ratio_catalogo: str
    direccion: int


@dataclass(frozen=True)
class EfectoApalancamiento:
    """Empuja el endeudamiento hacia arriba: deuda financiera a largo +W, patrimonio neto -W
    (recapitalización apalancada — la deuda nueva financia una distribución, el activo no
    cambia). Ver motor/evolucion_arquetipo.py para la derivación de por qué esta es la única
    palanca que sube el endeudamiento sin romper el cuadre."""

    ratio_catalogo: str
    direccion: int


@dataclass(frozen=True)
class EfectoTesoreria:
    """Desvía la tesorería (disponible) directamente, vía continuidad sobre disponible/ventas
    (no sobre ratios.tesoreria del catálogo tal cual, que mezcla disponible+realizable/pasivo
    corriente — ver docstring del módulo motor/evolucion_arquetipo.py, sección 'Arquetipo 15',
    para la limitación que esto supone)."""

    ratio_catalogo: str
    direccion: int


@dataclass(frozen=True)
class EfectoReclasificacionDeuda:
    """Reclasifica deuda financiera entre largo y corto plazo (calidad_deuda = deudas_fin_largo
    / deuda_financiera_total) SIN alterar la deuda financiera total — una renegociación cambia
    el vencimiento, no el importe. Distinto de "apalancamiento" (que sí sube la deuda total) y
    de los efectos de circulante: no toca activo, ni PN, ni el total de pasivo, así que no
    interactúa con la contención de endeudamiento (el ratio total no se mueve por este efecto).
    `direccion` +1 = más deuda a largo (mejora la calidad/vencimiento, refinanciación exitosa)."""

    ratio_catalogo: str
    direccion: int


@dataclass(frozen=True)
class EfectoEventoPuntual:
    """Fuerza una primitiva de la PyG a un valor no nulo en UN SOLO ejercicio (2024 o 2025,
    sorteado — ver motor/evolucion_arquetipo.py), volviendo a su comportamiento normal (ruido de
    sector) al año siguiente. Distinto de EfectoPygPrimitiva: ese modela una TENDENCIA progresiva
    (intensidad creciente año a año); este modela un SUCESO puntual y no recurrente, que por
    definición no tiene sentido tratar con el patrón de intensidad progresiva de los demás
    efectos (arquetipo 12, "Resultado extraordinario")."""

    primitiva: str
    ratio_catalogo: str
    direccion: int


@dataclass(frozen=True)
class EfectoCapex:
    """Desvía activo_no_corriente al alza vía continuidad sobre su propia rotación
    (ratios.rotacion_activo_no_corriente), igual mecanismo de forma que EfectoMasaCirculante
    (formula "rotacion") pero en el otro lado del balance — financiado con deuda a largo plazo
    nueva, no con el circulante (arquetipo 17, "Capex elevado"). Ver motor/evolucion_arquetipo.py
    para la justificación de por qué no se reutiliza directamente masa_circulante."""

    ratio_catalogo: str
    direccion: int


@dataclass(frozen=True)
class EfectoAdquisicion:
    """Inyección exógena y puntual de activo_no_corriente (arquetipo 18, "Adquisición") — NO es
    una desviación de continuidad como el resto de efectos, es un salto discreto en un único
    ejercicio fijo (AÑO_ADQUISICION en motor/evolucion_arquetipo.py, siempre 2024, nunca
    sorteado). `ratio_catalogo` (balance.activo_no_corriente) es solo trazabilidad, igual que en
    EfectoTesoreria: la magnitud se calcula como intensidad_base x activo total previo a la
    operación, no como una desviación del Huber de ese ratio. Financiada con caja disponible y,
    lo que no cubra, deuda a largo plazo nueva; añade también una aportación de ventas
    "inorgánica" ese año (ver `_evolucionar_un_año`) y una nota de memoria OBLIGATORIA (a
    diferencia de `nota_memoria` en el resto de arquetipos, que es opcional)."""

    ratio_catalogo: str
    direccion: int


Efecto = (
    EfectoMasaCirculante
    | EfectoPygPrimitiva
    | EfectoApalancamiento
    | EfectoTesoreria
    | EfectoReclasificacionDeuda
    | EfectoEventoPuntual
    | EfectoCapex
    | EfectoAdquisicion
)


@dataclass(frozen=True)
class DefinicionArquetipo:
    id: str
    numero: int
    nombre: str
    efectos: tuple[Efecto, ...]
    rango_crecimiento_pleno: dict[str, tuple[float, float]] | None = None
    # "cuantitativo" (por defecto): tiene efectos numéricos, lo procesa
    # motor.evolucion_arquetipo._evolucionar_un_año. "memoria_pura": arquetipos 7/19/20/21/22 —
    # sin ninguna huella numérica, `efectos` vacío está permitido (ver cargar_arquetipos), la
    # generación de texto vive en motor.memoria. Campo a nivel de ARQUETIPO, distinto del "tipo"
    # de cada efecto individual (que solo tiene sentido para arquetipos cuantitativos).
    clase: str = "cuantitativo"


def _construir_efecto(bruto: dict, arquetipo_id: str, indice: int) -> Efecto:
    tipo = bruto.get("tipo")
    if tipo not in TIPOS_EFECTO_VALIDOS:
        raise ArquetipoInvalidoError(
            f"{arquetipo_id}: efecto #{indice} tiene tipo '{tipo}' no reconocido. "
            f"Debe ser uno de: {sorted(TIPOS_EFECTO_VALIDOS)}"
        )
    direccion = bruto.get("direccion")
    if direccion not in (1, -1):
        raise ArquetipoInvalidoError(f"{arquetipo_id}: efecto #{indice} tiene direccion={direccion!r}, debe ser 1 o -1")
    ratio_catalogo = bruto.get("ratio_catalogo")
    if not ratio_catalogo:
        raise ArquetipoInvalidoError(f"{arquetipo_id}: efecto #{indice} no tiene ratio_catalogo")

    if tipo == "masa_circulante":
        variable = bruto.get("variable")
        formula = bruto.get("formula")
        if variable not in VARIABLES_MASA_CIRCULANTE_VALIDAS:
            raise ArquetipoInvalidoError(f"{arquetipo_id}: efecto #{indice} variable='{variable}' no reconocida")
        if formula not in FORMULAS_MASA_CIRCULANTE_VALIDAS:
            raise ArquetipoInvalidoError(f"{arquetipo_id}: efecto #{indice} formula='{formula}' no reconocida")
        return EfectoMasaCirculante(variable=variable, formula=formula, ratio_catalogo=ratio_catalogo, direccion=direccion)

    if tipo == "pyg_primitiva":
        primitiva = bruto.get("primitiva")
        if not primitiva:
            raise ArquetipoInvalidoError(f"{arquetipo_id}: efecto #{indice} no tiene 'primitiva'")
        return EfectoPygPrimitiva(primitiva=primitiva, ratio_catalogo=ratio_catalogo, direccion=direccion)

    if tipo == "apalancamiento":
        return EfectoApalancamiento(ratio_catalogo=ratio_catalogo, direccion=direccion)

    if tipo == "tesoreria":
        return EfectoTesoreria(ratio_catalogo=ratio_catalogo, direccion=direccion)

    if tipo == "reclasificacion_deuda":
        return EfectoReclasificacionDeuda(ratio_catalogo=ratio_catalogo, direccion=direccion)

    if tipo == "evento_puntual":
        primitiva = bruto.get("primitiva")
        if not primitiva:
            raise ArquetipoInvalidoError(f"{arquetipo_id}: efecto #{indice} no tiene 'primitiva'")
        return EfectoEventoPuntual(primitiva=primitiva, ratio_catalogo=ratio_catalogo, direccion=direccion)

    if tipo == "capex":
        return EfectoCapex(ratio_catalogo=ratio_catalogo, direccion=direccion)

    return EfectoAdquisicion(ratio_catalogo=ratio_catalogo, direccion=direccion)


def cargar_arquetipos(ruta: str | Path = RUTA_ARQUETIPOS_POR_DEFECTO) -> dict[str, DefinicionArquetipo]:
    """Carga y valida `data/arquetipos.json`, devuelve {id: DefinicionArquetipo}."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el archivo de arquetipos en: {ruta}")

    datos = json.loads(ruta.read_text(encoding="utf-8"))
    arquetipos: dict[str, DefinicionArquetipo] = {}
    for bruto in datos.get("arquetipos", []):
        arquetipo_id = bruto.get("id")
        if not arquetipo_id:
            raise ArquetipoInvalidoError("Hay un arquetipo en el JSON sin 'id'")
        if arquetipo_id in arquetipos:
            raise ArquetipoInvalidoError(f"Arquetipo duplicado: '{arquetipo_id}'")

        clase = bruto.get("clase", "cuantitativo")
        if clase not in ("cuantitativo", "memoria_pura"):
            raise ArquetipoInvalidoError(f"{arquetipo_id}: clase '{clase}' no reconocida (debe ser 'cuantitativo' o 'memoria_pura')")

        efectos = tuple(
            _construir_efecto(efecto_bruto, arquetipo_id, i) for i, efecto_bruto in enumerate(bruto.get("efectos", []))
        )
        if not efectos and clase != "memoria_pura":
            raise ArquetipoInvalidoError(f"{arquetipo_id}: no tiene ningún efecto")

        rango_bruto = bruto.get("rango_crecimiento_pleno")
        rango_crecimiento_pleno = None
        if rango_bruto is not None:
            rango_crecimiento_pleno = {k: tuple(v) for k, v in rango_bruto.items()}

        arquetipos[arquetipo_id] = DefinicionArquetipo(
            id=arquetipo_id,
            numero=bruto.get("numero", -1),
            nombre=bruto.get("nombre", arquetipo_id),
            efectos=efectos,
            rango_crecimiento_pleno=rango_crecimiento_pleno,
            clase=clase,
        )

    return arquetipos
