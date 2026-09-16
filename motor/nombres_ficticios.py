"""Generador de nombres ficticios de empresa (sección 2.17 de la especificación) — nombre +
forma jurídica + breve descripción de actividad, por caso. Capa INDEPENDIENTE del resto del
motor: no toca `EmpresaBase`/`EjercicioEmpresa`, no genera balance ni PyG, no se sortea dentro de
`generar_empresa_base`/`generar_evolucion_combinada` — se invoca aparte, con los mismos 3
parámetros (sector, segmento, semilla) que identifican "la empresa" en el resto del motor.

**Por qué NO por arquetipo/combo, solo por sector+segmento+semilla**: mismo criterio ya
establecido en todo el proyecto ("misma semilla+sector+segmento, misma empresa, sea cual sea el
arquetipo o la combinación que se le aplique encima" — ver CLAUDE.md, "Combinación de
arquetipos") — el nombre identifica a LA EMPRESA, no la historia concreta que se cuenta sobre
ella. Un mismo caso base (24.1/grandes_medianas/semilla=5) debe llamarse igual tanto si se genera
con "apalancamiento" como combinado con "dependencia_pocos_clientes".

**Sin parecido con empresas españolas reales**: combina un término genérico de actividad DEL
SECTOR real del caso (nunca una marca, nunca un nombre propio/apellido — el riesgo de coincidir
por azar con una razón social real es mucho más alto ahí que con vocabulario descriptivo genérico)
con un calificador geográfico genérico (ríos/cordilleras españolas de uso extendido en
denominaciones sociales reales — "del Duero", "del Cantábrico" — un patrón de nomenclatura
estándar, no la copia de ninguna empresa concreta) y la forma jurídica. **Coherente con el sector
real**: vocabulario propio por cada uno de los 27 sectores del catálogo (no por las 9 categorías
de `CATEGORIA_SECTOR`, insuficientemente específicas para esto — Siderurgia y Aeroespacial son
ambos "industria" pero necesitan vocabulario de actividad completamente distinto).

**Forma jurídica coherente con el tamaño** (`PROBABILIDAD_SA_POR_SEGMENTO`) — HIPÓTESIS DE
DISEÑO razonada, no un dato del catálogo ACCID (que no distingue forma jurídica en absoluto): en
España la S.L. es la forma jurídica ampliamente mayoritaria en cualquier tamaño de empresa, pero
la S.A. es proporcionalmente más común cuanto mayor es la empresa (necesidades de capital,
posible cotización, tradición en grandes compañías) — "pequeñas" sortea S.A. con probabilidad
baja (10%), "grandes_medianas" con probabilidad más alta pero SIN llegar a ser mayoritaria (45%,
la S.L. sigue siendo la forma más común incluso en el segmento grande del catálogo).

**Modo típico/atípico — verificado explícitamente que NO aplica, no solo asumido** (mismo
estándar que la Ronda 1 de la Fase 4 pidió aplicar a cualquier pieza nueva, ver `motor/
resumen_caso.py`): todos los sorteos de este módulo son elecciones discretas (`rng.choice` sobre
vocabulario, `rng.random()` de forma jurídica) — NINGUNO pasa por `_generar_partida` (el
mecanismo Huber/MAD que sí tiene un concepto de "típico"/"atípico"). Mismo caso que provisiones/
insolvencias/subvención de fondo (`rng.uniform`/`rng.choice` directos, sin ancla de catálogo): el
concepto de modo típico/atípico no existe para un sorteo discreto sin magnitud continua que
comparar contra un centro estadístico — no hay nada que exponer en `motor/resumen_caso.py` para
esta pieza, verificado (no solo declarado)."""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from motor.empresa_base import SEGMENTOS_VALIDOS

# Calificador geográfico genérico — gramaticalmente INVARIANTE (no necesita concordancia de
# género/número con el término de actividad que lo precede, a diferencia de un adjetivo como
# "Ibérica"/"Ibérico") — ríos y cordilleras españolas de uso extendido en denominaciones
# sociales reales, sin identificar ninguna empresa concreta.
CALIFICADORES_LUGAR = (
    "del Cantábrico", "del Duero", "del Ebro", "del Atlántico", "de Levante",
    "del Pirineo", "del Segura", "del Miño", "de la Meseta", "del Guadiana",
    "del Tajo", "del Genil",
)

# Probabilidad de que la forma jurídica sea S.A. (el resto, S.L.) — ver docstring del módulo.
PROBABILIDAD_SA_POR_SEGMENTO: dict[str, float] = {
    "pequeñas": 0.10,
    "grandes_medianas": 0.45,
}

# Probabilidad de que el nombre incluya el calificador geográfico (si no, queda solo el término
# de actividad) — variedad de longitud/estilo entre casos, sin que ningún sector dependa de él.
PROBABILIDAD_CALIFICADOR_LUGAR = 0.70

# Vocabulario de actividad por sector (los 27 códigos de CATEGORIA_SECTOR) — términos genéricos
# de negocio, nunca marcas ni nombres propios. Descripción de actividad FIJA por sector (no
# sorteada: la actividad real de la empresa es el propio sector del caso, no una variable más).
TERMINOS_SECTOR: dict[str, tuple[str, ...]] = {
    "24.1": ("Aceros", "Laminados", "Fundiciones", "Metalurgias", "Forjados"),
    "29": ("Componentes de Automoción", "Piezas del Automóvil", "Recambios", "Ensamblajes"),
    "10.1": ("Cárnicas", "Embutidos", "Carnes", "Charcutería"),
    "20.1": ("Química", "Químicos Industriales", "Compuestos Químicos", "Derivados Químicos"),
    "28": ("Maquinaria", "Equipos Industriales", "Mecánica", "Ingeniería Mecánica"),
    "30.3": ("Aeroespacial", "Aeronáutica", "Componentes Aeroespaciales"),
    "30.2": ("Material Ferroviario", "Construcciones Ferroviarias", "Rodante"),
    "19": ("Refino", "Petroquímica", "Combustibles"),
    "35.1": ("Energía", "Eléctrica", "Generación Eléctrica"),
    "33.1": ("Reparaciones Industriales", "Mantenimiento Industrial", "Talleres Industriales"),
    "33.2": ("Instalaciones Industriales", "Montajes Industriales", "Ensamblajes Industriales"),
    "71": ("Ingeniería", "Estudios Técnicos", "Proyectos de Ingeniería"),
    "72": ("Investigación", "Desarrollo Tecnológico", "Innovación"),
    "69.2": ("Auditores", "Asesoría Contable", "Contabilidad"),
    "70.2": ("Consultores de Gestión", "Consultoría Empresarial", "Estrategia Empresarial"),
    "62": ("Software", "Sistemas Informáticos", "Tecnología", "Soluciones Digitales"),
    "52": ("Almacenaje", "Logística", "Distribución Logística"),
    "4941": ("Transportes", "Transporte de Mercancías", "Portes"),
    "47.1": ("Supermercados", "Distribución Alimentaria", "Alimentación"),
    "46": ("Distribuciones", "Mayoristas", "Suministros"),
    "56.1": ("Restauración", "Hostelería", "Gastronomía"),
    "55.1": ("Hoteles", "Hostelería", "Alojamientos"),
    "41.2": ("Construcciones", "Obras", "Edificaciones"),
    "43.2": ("Instalaciones", "Electricidad y Fontanería", "Climatización"),
    "85": ("Formación", "Educación", "Enseñanza"),
    "86.1": ("Sanitaria", "Clínicas", "Salud"),
    "68": ("Inmobiliaria", "Patrimonio Inmobiliario", "Promociones Inmobiliarias"),
}

DESCRIPCION_ACTIVIDAD_SECTOR: dict[str, str] = {
    "24.1": "Producción y transformación de productos siderúrgicos (acero, laminados y fundiciones) para clientes industriales.",
    "29": "Fabricación de componentes y piezas para la industria del automóvil.",
    "10.1": "Elaboración y comercialización de carne y productos cárnicos.",
    "20.1": "Fabricación de productos químicos básicos e industriales.",
    "28": "Diseño y fabricación de maquinaria y bienes de equipo industrial.",
    "30.3": "Fabricación de componentes y sistemas para la industria aeroespacial.",
    "30.2": "Fabricación de locomotoras y material rodante ferroviario.",
    "19": "Refino de petróleo y producción de combustibles y derivados.",
    "35.1": "Generación, distribución y comercialización de energía eléctrica.",
    "33.1": "Reparación y mantenimiento de maquinaria y equipo industrial.",
    "33.2": "Instalación y montaje de maquinaria y equipos industriales.",
    "71": "Servicios de ingeniería técnica y consultoría de proyectos.",
    "72": "Investigación y desarrollo tecnológico aplicado.",
    "69.2": "Servicios de auditoría, contabilidad y asesoría fiscal.",
    "70.2": "Consultoría de gestión y estrategia empresarial.",
    "62": "Desarrollo de software y servicios de tecnologías de la información.",
    "52": "Almacenamiento y distribución logística de mercancías.",
    "4941": "Transporte de mercancías por carretera.",
    "47.1": "Comercio al por menor de productos de alimentación.",
    "46": "Comercio al por mayor y distribución de mercancías.",
    "56.1": "Servicios de restauración y hostelería.",
    "55.1": "Servicios de alojamiento hotelero.",
    "41.2": "Construcción y promoción de edificios.",
    "43.2": "Instalaciones eléctricas, de fontanería y climatización en obras.",
    "85": "Servicios de educación y formación.",
    "86.1": "Prestación de servicios sanitarios y hospitalarios.",
    "68": "Gestión y promoción de activos inmobiliarios.",
}


class NombreFicticioError(ValueError):
    """Sector no reconocido o segmento inválido al generar un nombre ficticio."""


@dataclass(frozen=True)
class NombreFicticio:
    nombre_completo: str  # p. ej. "Aceros del Cantábrico, S.L."
    forma_juridica: str  # "S.L." | "S.A."
    descripcion_actividad: str


def _entropia_nombre(sector: str, segmento: str) -> int:
    return zlib.crc32(f"{sector}|{segmento}|nombre_ficticio".encode("utf-8"))


def generar_nombre_ficticio(sector: str, segmento: str, semilla: int) -> NombreFicticio:
    """Sorteo determinista por (sector, segmento, semilla) — mismo patrón de hash estable
    (`zlib.crc32`) ya usado en todo el motor. RNG propio e independiente (entropía
    `"nombre_ficticio"`), no desplaza ningún sorteo existente. NO depende del arquetipo/
    intensidad ni de `catalogo` — ver docstring del módulo."""
    if sector not in TERMINOS_SECTOR:
        raise NombreFicticioError(f"Sector '{sector}' no reconocido. Códigos disponibles: {sorted(TERMINOS_SECTOR)}")
    if segmento not in SEGMENTOS_VALIDOS:
        raise NombreFicticioError(f"Segmento '{segmento}' no válido. Debe ser uno de: {sorted(SEGMENTOS_VALIDOS)}")

    rng = np.random.default_rng([semilla, _entropia_nombre(sector, segmento)])

    termino = str(rng.choice(TERMINOS_SECTOR[sector]))
    if rng.random() < PROBABILIDAD_CALIFICADOR_LUGAR:
        calificador = str(rng.choice(CALIFICADORES_LUGAR))
        nombre_base = f"{termino} {calificador}"
    else:
        nombre_base = termino

    forma_juridica = "S.A." if rng.random() < PROBABILIDAD_SA_POR_SEGMENTO[segmento] else "S.L."

    return NombreFicticio(
        nombre_completo=f"{nombre_base}, {forma_juridica}",
        forma_juridica=forma_juridica,
        descripcion_actividad=DESCRIPCION_ACTIVIDAD_SECTOR[sector],
    )
