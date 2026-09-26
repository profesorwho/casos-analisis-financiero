"""Cliente de la API de Anthropic, verificador numérico y caché — encargo #114 (modo narrativo
del documento de solución). Módulo agnóstico del caso concreto: no importa nada de `motor/` ni
de `mapeo_solucion.py`, solo trabaja con el "paquete de verdad" (un dict serializable) que le
pasa `renderer/mapeo_solucion_narrativo.py`.

**Qué NO es esta verificación (documentado explícitamente, sin venderla como más de lo que es)**:
es una criba de errores GRUESOS — números inventados, de otro caso, o de un orden de magnitud
distinto al que corresponde. NO es una prueba de exactitud perfecta del lenguaje natural: un LLM
que redondea razonablemente ("ronda el 70%", "supera el millón de euros") debe pasar; un LLM que
inventa una cifra, cita una cifra de otro ejercicio/caso, o se equivoca de orden de magnitud, debe
fallar. La tolerancia (ver `TOLERANCIA_RELATIVA` abajo) está calibrada para eso, no para detectar
errores de precisión de un decimal."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------------------------
# Configuración de acceso al modelo — nunca hardcodear la clave, nunca imprimirla en logs.
# --------------------------------------------------------------------------------------------
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODELO_POR_DEFECTO = "claude-sonnet-5"
MAX_TOKENS_RESPUESTA = 8000
TIMEOUT_SEGUNDOS = 120

MAX_INTENTOS = 3

DIRECTORIO_CACHE = Path(__file__).resolve().parent / "narrativa_cache"

# --------------------------------------------------------------------------------------------
# Tolerancia del verificador numérico — hipótesis de diseño explícita, sin ancla externa (no hay
# ningún catálogo que diga "qué tolerancia de redondeo del lenguaje natural es razonable").
#
# TOLERANCIA_RELATIVA = 5%: cubre aproximaciones habituales del lenguaje natural sobre una cifra
# real ("ronda el 70%" sobre un 71,7% real, "cerca de 900.000€" sobre 921.926€ real) sin admitir
# una cifra de otro orden de magnitud (una desviación del 5% nunca convierte, p. ej., un 8% real
# en un 15% citado, ni 900.000€ reales en 1.500.000€ citados — ambos casos se prueban en
# tests/test_narrativa_llm.py con textos sintéticos construidos a mano, no solo argumentado).
# TOLERANCIA_ABSOLUTA = 0.5: suelo defensivo para comparaciones cerca de cero (un ratio real de
# 0,02 con una tolerancia puramente relativa del 5% solo perdonaría +-0,001 — demasiado estricto
# para lenguaje natural que redondea "casi cero" a "0" o "1"); también cubre pequeños enteros
# estructurales (recuento de arquetipos/señales) frente a un error de redondeo de un decimal.
# --------------------------------------------------------------------------------------------
TOLERANCIA_RELATIVA = 0.05
TOLERANCIA_ABSOLUTA = 0.5

# Los 3 años del caso (2023/2024/2025) — SIEMPRE válidos, no arriesgan colar un número inventado
# porque no son una magnitud económica (nadie "inventa" que 2024 es un año del caso, es una
# constante del diseño del motor). Deliberadamente NO se añade un rango de "números de sección"
# (1-9) ni de "número de arquetipo" aquí — eso debilitaría el verificador para cualquier entero
# pequeño (exactamente el tipo de error grueso que debe seguir cazando, p. ej. "12 señales" en
# vez de las 6 reales). Las referencias legítimas a "sección 7"/"arquetipo 6" que el LLM necesite
# citar deben poder resolverse porque esos números YA están en el paquete de verdad (número de
# arquetipo, sector, semilla, etc. — ver `mapeo_solucion_narrativo.construir_paquete_verdad`), no
# porque se les dé un pase genérico aquí.
NUMEROS_ESTRUCTURALES = frozenset({2023.0, 2024.0, 2025.0})


class NarrativaLLMError(RuntimeError):
    """Error genérico del cliente de la API (fallo de red, respuesta mal formada, etc.)."""


class VerificacionNumericaError(RuntimeError):
    """La narrativa del LLM no superó la verificación numérica tras `MAX_INTENTOS` — lista las
    cifras concretas que no encajaron con ningún valor del banco de verdad, por sección."""

    def __init__(self, cifras_no_verificadas_por_seccion: dict[str, list[float]]):
        self.cifras_no_verificadas_por_seccion = cifras_no_verificadas_por_seccion
        detalle = "; ".join(
            f"{seccion}: {cifras}" for seccion, cifras in cifras_no_verificadas_por_seccion.items() if cifras
        )
        super().__init__(f"Verificación numérica fallida tras {MAX_INTENTOS} intentos — cifras sin respaldo: {detalle}")


# --------------------------------------------------------------------------------------------
# Banco de verdad — aplana el paquete de verdad (dict anidado con listas/dicts/números) en un
# conjunto de floats contra el que comparar cualquier cifra que aparezca en el texto del LLM.
# --------------------------------------------------------------------------------------------

RANGO_DUPLICACION_PORCENTAJE = 3.0  # |v| <= esto también se añade x100 (0.114 -> 11.4, para "11,4%")


def _aplanar_numeros(objeto) -> list[float]:
    numeros: list[float] = []
    if isinstance(objeto, bool):
        return numeros
    if isinstance(objeto, (int, float)):
        numeros.append(float(objeto))
    elif isinstance(objeto, dict):
        for valor in objeto.values():
            numeros.extend(_aplanar_numeros(valor))
    elif isinstance(objeto, (list, tuple)):
        for elemento in objeto:
            numeros.extend(_aplanar_numeros(elemento))
    return numeros


def construir_banco_de_verdad(paquete_verdad: dict) -> set[float]:
    """Todos los números del paquete de verdad, más sus variantes en base 100 (para las
    fracciones/ratios que el texto citará como porcentaje) y los estructurales (años, nº de
    sección) — ver docstring del módulo para la justificación de la tolerancia que se aplica
    después, en `verificar_cifras`."""
    banco: set[float] = set(NUMEROS_ESTRUCTURALES)
    for numero in _aplanar_numeros(paquete_verdad):
        banco.add(numero)
        if abs(numero) <= RANGO_DUPLICACION_PORCENTAJE:
            banco.add(numero * 100)
    return banco


# --------------------------------------------------------------------------------------------
# Extracción de tokens numéricos del texto en lenguaje natural — español (miles con punto,
# decimales con coma) e inglés/plano (decimales con punto, como ya produce `mapeo_solucion.py`
# en sus propias tablas, p. ej. "8.2%") — ambos formatos conviven en este proyecto, así que el
# extractor acepta los dos en vez de asumir uno solo.
# --------------------------------------------------------------------------------------------

_PATRON_NUMERO = re.compile(
    r"(?P<num>-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+,\d+|-?\d+\.\d+|-?\d+)"
    r"\s*(?P<mult>mill(?:ón|on|ones)?\.?|mil\b|k€|k\b|M€)?",
    re.IGNORECASE,
)

_MULTIPLICADORES = {
    "mill": 1_000_000, "millon": 1_000_000, "millón": 1_000_000, "millones": 1_000_000, "mill.": 1_000_000,
    "mil": 1_000, "k€": 1_000, "k": 1_000, "m€": 1_000_000,
}


_RE_MILES_SOLO = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_RE_MILES_CON_DECIMAL = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d+$")


def _parsear_numero_es(token: str) -> float:
    """Interpreta un token numérico distinguiendo por ESTRUCTURA (no solo por qué separador
    aparece), para no confundir "900.000" (miles, sin decimal — sería un bug tratarlo como
    900,0) con "8.2" (decimal plano, como ya producen las propias tablas de `mapeo_solucion.py`,
    p. ej. "8.2%"): (a) miles con coma decimal ("1.234.567,89") -> quita los puntos, la coma pasa
    a punto; (b) miles sin decimal ("900.000", 3 dígitos por grupo) -> quita los puntos, entero;
    (c) coma decimal simple ("11,4") -> coma a punto; (d) punto decimal simple ("8.2") -> tal
    cual; (e) entero plano."""
    token = token.strip()
    negativo = token.startswith("-")
    token = token.lstrip("-")
    if _RE_MILES_CON_DECIMAL.match(token):
        token = token.replace(".", "").replace(",", ".")
    elif _RE_MILES_SOLO.match(token):
        token = token.replace(".", "")
    elif "," in token:
        token = token.replace(",", ".")
    valor = float(token)
    return -valor if negativo else valor


def extraer_numeros_del_texto(texto: str) -> list[float]:
    numeros = []
    for match in _PATRON_NUMERO.finditer(texto):
        valor = _parsear_numero_es(match.group("num"))
        mult_texto = (match.group("mult") or "").strip().lower().rstrip(".")
        if mult_texto:
            factor = _MULTIPLICADORES.get(mult_texto) or _MULTIPLICADORES.get(mult_texto + ".")
            if factor:
                valor *= factor
        numeros.append(valor)
    return numeros


def _dentro_de_tolerancia(valor: float, banco: set[float]) -> bool:
    for referencia in banco:
        limite = max(TOLERANCIA_RELATIVA * abs(referencia), TOLERANCIA_ABSOLUTA)
        if abs(valor - referencia) <= limite:
            return True
    return False


def verificar_cifras(texto: str, banco: set[float]) -> list[float]:
    """Devuelve la lista de números del texto que NO caen dentro de tolerancia de ningún valor
    del banco — lista vacía si todo cuadra. Ver docstring del módulo: esto es una criba de
    errores gruesos, no una prueba de exactitud perfecta."""
    sin_respaldo = []
    for numero in extraer_numeros_del_texto(texto):
        if not _dentro_de_tolerancia(numero, banco):
            sin_respaldo.append(numero)
    return sin_respaldo


# --------------------------------------------------------------------------------------------
# Caché — clave = hash(parámetros del caso) + hash(paquete de verdad serializado de forma
# determinista). Si el motor cambia y las cifras de un caso ya cacheado cambian, la clave
# cambia y la caché deja de usarse (nunca sirve una narrativa desincronizada de los datos).
# --------------------------------------------------------------------------------------------

def calcular_clave_cache(sector: str, segmento: str, ventas_objetivo: float, semilla: int,
                          arquetipos_intensidades: dict[str, str], paquete_verdad: dict) -> str:
    parametros_ordenados = {
        "sector": sector, "segmento": segmento, "ventas_objetivo": ventas_objetivo, "semilla": semilla,
        "arquetipos_intensidades": dict(sorted(arquetipos_intensidades.items())),
    }
    parametros_json = json.dumps(parametros_ordenados, sort_keys=True, ensure_ascii=False)
    verdad_json = json.dumps(paquete_verdad, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((parametros_json + "|" + verdad_json).encode("utf-8")).hexdigest()


def ruta_cache(clave: str) -> Path:
    return DIRECTORIO_CACHE / f"{clave}.json"


def leer_cache(clave: str) -> dict | None:
    ruta = ruta_cache(clave)
    if not ruta.exists():
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def escribir_cache(clave: str, secciones: dict[str, str], modelo: str, intentos: int) -> None:
    DIRECTORIO_CACHE.mkdir(parents=True, exist_ok=True)
    contenido = {
        "clave": clave,
        "secciones": secciones,
        "modelo": modelo,
        "intentos": intentos,
        "generado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(ruta_cache(clave), "w", encoding="utf-8") as f:
        json.dump(contenido, f, ensure_ascii=False, indent=2, sort_keys=True)


# --------------------------------------------------------------------------------------------
# Cliente de la API — función pura, sin estado: manda el prompt, exige una respuesta JSON con
# las 9 claves de sección, y devuelve el dict ya parseado.
# --------------------------------------------------------------------------------------------

NOMBRES_SECCIONES = tuple(f"seccion_{i}" for i in range(1, 10))


def _leer_api_key() -> str:
    clave = os.environ.get("ANTHROPIC_API_KEY")
    if not clave:
        raise NarrativaLLMError(
            "ANTHROPIC_API_KEY no está definida en el entorno — no se puede llamar a la API. "
            "Nunca se lee de ningún otro sitio (ni hardcodeada, ni de un fichero de config)."
        )
    return clave


def llamar_llm(mensajes: list[dict], modelo: str | None = None) -> dict[str, str]:
    """Llama a la API de mensajes de Anthropic con la conversación `mensajes` (lista de turnos
    `{"role": "user"|"assistant", "content": str}`) y devuelve el dict `{seccion_1: texto, ...,
    seccion_9: texto}` ya parseado del JSON de la última respuesta. `mensajes` permite encadenar
    un reintento (turno de usuario adicional con las cifras que fallaron) sin repetir el prompt
    original completo — ver `generar_narrativa_con_verificacion`. Nunca imprime ni registra la
    clave de API."""
    api_key = _leer_api_key()
    modelo = modelo or os.environ.get("NARRATIVA_MODELO", MODELO_POR_DEFECTO)

    cuerpo = json.dumps({
        "model": modelo,
        "max_tokens": MAX_TOKENS_RESPUESTA,
        "messages": mensajes,
    }).encode("utf-8")

    peticion = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=cuerpo,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            cuerpo_respuesta = json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")
        raise NarrativaLLMError(f"La API de Anthropic devolvió {e.code}: {detalle}") from e
    except urllib.error.URLError as e:
        raise NarrativaLLMError(f"No se pudo contactar con la API de Anthropic: {e}") from e

    texto_respuesta = "".join(bloque.get("text", "") for bloque in cuerpo_respuesta.get("content", []))
    return _parsear_json_secciones(texto_respuesta)


def _parsear_json_secciones(texto_respuesta: str) -> dict[str, str]:
    texto = texto_respuesta.strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin == -1:
        raise NarrativaLLMError(f"La respuesta del LLM no contiene un objeto JSON reconocible: {texto[:500]!r}")
    try:
        datos = json.loads(texto[inicio:fin + 1])
    except json.JSONDecodeError as e:
        raise NarrativaLLMError(f"La respuesta del LLM no es JSON válido: {e}") from e
    faltantes = [s for s in NOMBRES_SECCIONES if s not in datos]
    if faltantes:
        raise NarrativaLLMError(f"La respuesta del LLM no incluye las secciones: {faltantes}")
    return {seccion: str(datos[seccion]) for seccion in NOMBRES_SECCIONES}


# --------------------------------------------------------------------------------------------
# Orquestación: prompt inicial + verificación + reintentos con las cifras concretas que fallaron.
# --------------------------------------------------------------------------------------------

@dataclass
class ResultadoNarrativa:
    secciones: dict[str, str]
    intentos: int
    modelo: str


def generar_narrativa_con_verificacion(
    prompt_inicial: str, paquete_verdad: dict, modelo: str | None = None,
) -> ResultadoNarrativa:
    modelo_resuelto = modelo or os.environ.get("NARRATIVA_MODELO", MODELO_POR_DEFECTO)
    banco = construir_banco_de_verdad(paquete_verdad)

    mensajes = [{"role": "user", "content": prompt_inicial}]
    cifras_no_verificadas_por_seccion: dict[str, list[float]] = {}
    for intento in range(1, MAX_INTENTOS + 1):
        secciones = llamar_llm(mensajes, modelo=modelo_resuelto)
        cifras_no_verificadas_por_seccion = {
            seccion: verificar_cifras(texto, banco) for seccion, texto in secciones.items()
        }
        if not any(cifras_no_verificadas_por_seccion.values()):
            return ResultadoNarrativa(secciones=secciones, intentos=intento, modelo=modelo_resuelto)

        if intento == MAX_INTENTOS:
            break

        mensajes.append({"role": "assistant", "content": json.dumps(secciones, ensure_ascii=False)})
        detalle_fallos = "\n".join(
            f"- {seccion}: {cifras}" for seccion, cifras in cifras_no_verificadas_por_seccion.items() if cifras
        )
        mensajes.append({
            "role": "user",
            "content": (
                "Las siguientes cifras de tu respuesta anterior NO coinciden (ni siquiera con un "
                "margen de redondeo razonable) con ningún dato del paquete de hechos que te di. "
                "Corrígelas usando SOLO números que aparezcan en el paquete de hechos original "
                "(puedes redondearlos o expresarlos como porcentaje, pero no inventar ni tomar "
                "cifras de otro ejercicio o de otro caso). Devuelve de nuevo el JSON COMPLETO con "
                "las 9 secciones.\n\nCifras sin respaldo, por sección:\n" + detalle_fallos
            ),
        })

    raise VerificacionNumericaError(cifras_no_verificadas_por_seccion)
