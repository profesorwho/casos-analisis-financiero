"""Paso 1 del flujo MANUAL de narrativa (encargo #115) — sin `ANTHROPIC_API_KEY` disponible, la
consulta al LLM se hace a mano en claude.ai: este módulo genera el caso, construye el paquete de
verdad y el prompt EXACTOS del #114 (mismas funciones, sin tocarlas) y los escribe en un fichero
de texto listo para copiar y pegar. El paso 2 (`renderer/construir_solucion_narrativa.py`)
recupera la respuesta pegada por la persona y construye el PDF.

No se modifica ni un carácter de `mapeo_solucion_narrativo.py`/`narrativa_llm.py` — este módulo
solo los importa."""
import json
import sys
from pathlib import Path

_RENDERER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RENDERER_DIR.parent))
sys.path.insert(0, str(_RENDERER_DIR))

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.memoria import generar_caso_combinado
from motor.efe import generar_efe
from motor.calendario_deuda import calcular_calendario_deuda

from generar_solucion_caso import EvolucionSinPlausibilidadError
from mapeo_solucion_narrativo import construir_paquete_verdad, construir_prompt
from narrativa_llm import calcular_clave_cache, leer_cache

CABECERA_INSTRUCCIONES = """\
========================================================================
INSTRUCCIONES — narrativa manual del documento de solución (encargo #115)
========================================================================
1. Copia TODO el texto de abajo, desde "Eres un profesor...", y pégalo en
   una conversación NUEVA con Claude en claude.ai (o en el asistente que
   uses, cualquiera vale — el paquete de hechos y las instrucciones no
   dependen de un proveedor concreto).
2. Cuando responda, copia su respuesta COMPLETA —incluido cualquier
   bloque de código, con sus ``` si los lleva— en un fichero de texto
   nuevo (por ejemplo, "respuesta_pegada.txt").
3. Ejecuta el paso 2 (`renderer.construir_solucion_narrativa.importar_
   respuesta`) con ese fichero y el fichero de metadatos que se ha
   guardado junto a este prompt (mismo nombre, sufijo ".meta.json").
========================================================================

""".rstrip("\n") + "\n\n"


def exportar_prompt(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades, ruta_salida) -> dict:
    """Genera el caso, construye el paquete de verdad + el prompt (funciones EXACTAS del #114) y
    escribe el fichero de prompt + su `.meta.json` (necesario para el paso 2, que no debe tener
    que regenerar el caso desde cero). Si el caso YA está en caché, NO repite el proceso: escribe
    un aviso corto en `ruta_salida` en su lugar y no crea ningún `.meta.json` (no hay nada que
    importar). Devuelve un dict con el estado (`ya_en_cache`, `clave`, rutas escritas)."""
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades,
                                        catalogo=catalogo, arquetipos=arquetipos)
    if evolucion.plausibilidad is None:
        raise EvolucionSinPlausibilidadError(
            f"evolucion.plausibilidad es None para {sector}/{segmento}/semilla {semilla} — "
            "protocolo de parada, no se exporta ningún prompt."
        )
    ejercicios = evolucion.ejercicios
    efes = {
        2024: generar_efe(ejercicios[2023], ejercicios[2024], True),
        2025: generar_efe(ejercicios[2024], ejercicios[2025], True),
    }
    calendario = calcular_calendario_deuda(evolucion)
    paquete_verdad = construir_paquete_verdad(evolucion, ejercicios, efes, calendario, arquetipos)
    clave = calcular_clave_cache(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades, paquete_verdad)

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)

    if leer_cache(clave) is not None:
        ruta_salida.write_text(
            f"Ya existe una narrativa verificada en caché para este caso (clave {clave}).\n"
            "No hace falta repetir el proceso manual — usa esa narrativa directamente "
            "(renderer/narrativa_cache/" + clave + ".json) para construir el PDF.\n",
            encoding="utf-8",
        )
        return {"ya_en_cache": True, "clave": clave, "ruta_prompt": None, "ruta_meta": None}

    prompt = construir_prompt(paquete_verdad)
    ruta_salida.write_text(CABECERA_INSTRUCCIONES + prompt, encoding="utf-8")

    ruta_meta = ruta_salida.with_suffix(".meta.json")
    metadatos = {
        "clave": clave,
        "sector": sector,
        "segmento": segmento,
        "ventas_objetivo": ventas_objetivo,
        "semilla": semilla,
        "arquetipos_intensidades": arquetipos_intensidades,
        "paquete_verdad": paquete_verdad,
    }
    ruta_meta.write_text(json.dumps(metadatos, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return {"ya_en_cache": False, "clave": clave, "ruta_prompt": str(ruta_salida), "ruta_meta": str(ruta_meta)}


if __name__ == "__main__":
    resultado = exportar_prompt(
        sector="28", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=15,
        arquetipos_intensidades={"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        ruta_salida=str(_RENDERER_DIR / "output" / "prompt_ejemplo.txt"),
    )
    print(resultado)
