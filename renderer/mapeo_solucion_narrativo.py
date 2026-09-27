"""Modo narrativo del documento de solución (encargo #114) — el mismo documento del #113, pero
con la prosa redactada por un LLM a partir de un "paquete de verdad" ya calculado y verificado.
Las TABLAS nunca las escribe el LLM: se reutilizan exactamente las funciones `tabla_*` de
`renderer/mapeo_solucion.py`, sin tocarlas. Este módulo solo construye los hechos (paquete de
verdad), el prompt, y ensambla el flow de reportlab intercalando tablas (deterministas) con
prosa (LLM, verificada contra el propio paquete de verdad antes de aceptarla)."""
from __future__ import annotations

import json

from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import cm

from catalogo_narrativo_arquetipos import CATALOGO_NARRATIVO_ARQUETIPOS
from mapeo_solucion import (
    AÑOS,
    ARQUETIPO_RATIOS_RELACIONADOS,
    RATIO_NOMBRE_LEGIBLE,
    RATIOS_ECONOMICO,
    RATIOS_ENDEUDAMIENTO,
    RATIOS_LIQUIDEZ,
    RATIOS_RENTABILIDAD,
    calcular_apalancamiento_financiero,
    calcular_concentracion_vencimientos_1año,
    calcular_fondo_maniobra,
    calcular_pmm,
    calcular_rf_dupont,
    cuerpo,
    parsear_arquetipos_activos,
    tabla_balance_horizontal,
    tabla_balance_vertical,
    tabla_dupont,
    tabla_economico,
    tabla_efe,
    tabla_endeudamiento,
    tabla_estructura_gastos,
    tabla_fondo_maniobra,
    tabla_liquidez,
    tabla_pmm,
    tabla_rentabilidad,
    tabla_semaforo,
    tabla_señales,
    titulo_seccion,
)
from narrativa_llm import (
    NOMBRES_SECCIONES,
    calcular_clave_cache,
    construir_banco_de_verdad,
    escribir_cache,
    generar_narrativa_con_verificacion,
    leer_cache,
)

TITULOS_SECCIONES = {
    "seccion_1": "1. Resumen ejecutivo",
    "seccion_2": "2. Análisis patrimonial",
    "seccion_3": "3. Análisis financiero a corto plazo (liquidez)",
    "seccion_4": "4. Análisis financiero a largo plazo (endeudamiento y solvencia)",
    "seccion_5": "5. Análisis económico (cuenta de resultados)",
    "seccion_6": "6. Análisis de la rentabilidad",
    "seccion_7": "7. Análisis del Estado de Flujos de Efectivo",
    "seccion_8": "8. Señales de alerta (banderas rojas)",
    "seccion_9": "9. Diagnóstico integrado",
}


def _redondear(valor, decimales: int = 6):
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, float):
        return round(valor, decimales)
    return valor


# --------------------------------------------------------------------------------------------
# Paquete de verdad — TODOS los números que el LLM puede necesitar citar, y contra los que se
# verifica su prosa (ver `narrativa_llm.construir_banco_de_verdad`). Debe ser serializable a
# JSON de forma determinista (mismo caso -> mismo dict -> misma clave de caché).
# --------------------------------------------------------------------------------------------

def construir_paquete_verdad(evolucion, ejercicios, efes, calendario, arquetipos_definiciones) -> dict:
    arquetipos_activos = parsear_arquetipos_activos(evolucion)

    ratios_por_año = {
        str(año): {clave: _redondear(valor) for clave, valor in evolucion.plausibilidad.valores_por_año[año].items()}
        for año in AÑOS
    }
    pmm_por_año = {}
    for año in AÑOS:
        eco, fin = calcular_pmm(evolucion.plausibilidad.valores_por_año[año])
        pmm_por_año[str(año)] = {"economico_dias": _redondear(eco, 1), "financiero_dias": _redondear(fin, 1)}

    dupont_por_año = {}
    for año in AÑOS:
        valores = evolucion.plausibilidad.valores_por_año[año]
        apalancamiento = calcular_apalancamiento_financiero(ejercicios[año].balance_eur)
        rf = calcular_rf_dupont(valores.get("ratios.roi"), ejercicios[año].balance_eur, ejercicios[año].pyg_eur)
        dupont_por_año[str(año)] = {"apalancamiento": _redondear(apalancamiento), "rf_calculada": _redondear(rf)}

    balance_vertical = {}
    for año in AÑOS:
        b = ejercicios[año].balance_eur
        total = b["activo_no_corriente"] + b["activo_corriente"]
        balance_vertical[str(año)] = {
            clave: _redondear(b[clave] / total) if total else None
            for clave in (
                "activo_no_corriente", "activo_corriente", "existencias", "realizable", "disponible",
                "patrimonio_neto", "pasivo_no_corriente", "pasivo_corriente",
            )
        }
    balance_horizontal = {}
    for a0, a1 in ((2023, 2024), (2024, 2025)):
        clave_periodo = f"{a0}_{a1}"
        b0, b1 = ejercicios[a0].balance_eur, ejercicios[a1].balance_eur
        balance_horizontal[clave_periodo] = {
            clave: (_redondear((b1[clave] - b0[clave]) / b0[clave]) if b0[clave] else None)
            for clave in (
                "activo_no_corriente", "activo_corriente", "existencias", "realizable", "disponible",
                "patrimonio_neto", "pasivo_no_corriente", "pasivo_corriente",
            )
        }

    fondo_maniobra_por_año = {str(año): _redondear(calcular_fondo_maniobra(ejercicios[año].balance_eur), 2) for año in AÑOS}

    pyg_por_año = {
        str(año): {
            "resultado_ejercicio_eur": _redondear(ejercicios[año].pyg_eur["resultado_ejercicio"], 2),
            "consumos_explotacion_pct": _redondear(ejercicios[año].pyg_pct["consumos_explotacion"]),
            "gastos_personal_pct": _redondear(ejercicios[año].pyg_pct["gastos_personal"]),
            "otros_gastos_explot_pct": _redondear(ejercicios[año].pyg_pct["otros_gastos_explot"]),
            "amortizaciones_pct": _redondear(ejercicios[año].pyg_pct["amortizaciones"]),
        }
        for año in AÑOS
    }

    efe_por_año = {
        str(año): {
            "flujo_explotacion_eur": _redondear(efes[año].a5_flujo_explotacion, 2),
            "flujo_inversion_eur": _redondear(efes[año].b8_flujo_inversion, 2),
            "flujo_financiacion_eur": _redondear(efes[año].c12_flujo_financiacion, 2),
            "variacion_neta_eur": _redondear(efes[año].e_variacion_neta_efectivo, 2),
        }
        for año in (2024, 2025)
    }

    señales = [
        {
            "ratio": s.ratio, "año": s.año, "valor": _redondear(s.valor, 4), "huber_9y": _redondear(s.huber_9y, 4),
            "desviaciones": None if s.desviaciones in (float("inf"), float("-inf")) else _redondear(s.desviaciones, 2),
            "direccion": s.direccion,
        }
        for s in sorted(evolucion.plausibilidad.señales, key=lambda s: (s.año, s.ratio))
    ]

    concentracion_vencimientos = calcular_concentracion_vencimientos_1año(calendario)

    try:
        ventas_objetivo_num = float(ejercicios[2023].ventas)
    except (TypeError, ValueError):
        ventas_objetivo_num = None
    try:
        sector_num = float(evolucion.sector_codigo)
    except (TypeError, ValueError):
        sector_num = None

    return {
        "meta": {
            "sector_codigo": evolucion.sector_codigo,
            "sector_codigo_num": sector_num,
            "sector_nombre": evolucion.sector_nombre,
            "segmento": evolucion.segmento,
            "semilla": evolucion.semilla,
            "ventas_2023_eur": _redondear(ventas_objetivo_num, 2),
            "arquetipos_activos": [
                {"id": aid, "intensidad": intensidad, "numero": arquetipos_definiciones[aid].numero}
                for aid, intensidad in arquetipos_activos
            ],
            "n_arquetipos": len(arquetipos_activos),
            "n_señales": len(señales),
        },
        "ratios_por_año": ratios_por_año,
        "pmm_por_año": pmm_por_año,
        "dupont_por_año": dupont_por_año,
        "balance_pct_vertical_por_año": balance_vertical,
        "balance_pct_horizontal": balance_horizontal,
        "fondo_maniobra_eur_por_año": fondo_maniobra_por_año,
        "pyg_por_año": pyg_por_año,
        "efe_por_año": efe_por_año,
        "señales": señales,
        "concentracion_vencimientos_2025_pct": _redondear(concentracion_vencimientos),
    }


# --------------------------------------------------------------------------------------------
# Prompt — hechos + catálogo de arquetipos como datos de entrada (nunca a reinventar), la
# estructura de 9 secciones ya fijada por el #113, e instrucciones explícitas de no contradecir
# el catálogo ni citar números que no estén en el paquete de hechos.
# --------------------------------------------------------------------------------------------

def construir_prompt(paquete_verdad: dict) -> str:
    arquetipos_activos = paquete_verdad["meta"]["arquetipos_activos"]
    fichas_arquetipos = "\n".join(
        f"- {a['id']} (nº {a['numero']}, intensidad {a['intensidad']}): "
        f"{CATALOGO_NARRATIVO_ARQUETIPOS.get(a['id'], '(sin descripción)')} "
        f"Ratios habitualmente asociados a este arquetipo: "
        f"{', '.join(ARQUETIPO_RATIOS_RELACIONADOS.get(a['id'], ())) or '(ninguno — declarado explícitamente sin efecto claro en los ratios de este informe)'}."
        for a in arquetipos_activos
    )
    hechos_json = json.dumps(paquete_verdad, ensure_ascii=False, indent=2, sort_keys=True)

    return f"""Eres un profesor de análisis económico-financiero redactando la prosa de un informe de
solución para un caso de estudio. Las TABLAS del informe ya están hechas (no las escribes tú,
no las reproduzcas en tu respuesta) — tu trabajo es escribir el texto que las acompaña y las
conecta, para las 9 secciones siguientes (usa exactamente estos títulos, ya numerados):

1. Resumen ejecutivo
2. Análisis patrimonial
3. Análisis financiero a corto plazo (liquidez)
4. Análisis financiero a largo plazo (endeudamiento y solvencia)
5. Análisis económico (cuenta de resultados)
6. Análisis de la rentabilidad
7. Análisis del Estado de Flujos de Efectivo
8. Señales de alerta (banderas rojas)
9. Diagnóstico integrado

REGLAS ESTRICTAS (se van a verificar automáticamente, cifra por cifra):
- SOLO puedes citar números que aparezcan en el "paquete de hechos" JSON de abajo. Puedes
  redondearlos, expresarlos como porcentaje (multiplicando por 100) o en miles/millones, pero
  NUNCA inventar una cifra ni usar la de otro ejercicio o de otro caso.
- El catálogo de arquetipos (más abajo) es un HECHO verificado, no algo que puedas reinterpretar:
  si dice que un arquetipo NO tiene un efecto claro en los ratios de este informe, NO afirmes lo
  contrario en tu prosa (puedes decir que su efecto no es apreciable en estos ratios).
  Puedes parafrasear las descripciones, no contradecirlas.
- Conecta las secciones entre sí donde tenga sentido (p. ej. retoma el fondo de maniobra de la
  sección 2 al hablar de liquidez en la 3).
- Sé conciso: 2-5 párrafos cortos por sección, tono profesional y didáctico, en español.

Arquetipos incorporados al caso (hecho verificado, no lo reinterpretes):
{fichas_arquetipos}

Paquete de hechos (JSON) — la única fuente de cifras que puedes citar:
```json
{hechos_json}
```

Devuelve tu respuesta como un único objeto JSON con exactamente estas 9 claves de texto:
{{"seccion_1": "...", "seccion_2": "...", "seccion_3": "...", "seccion_4": "...",
"seccion_5": "...", "seccion_6": "...", "seccion_7": "...", "seccion_8": "...", "seccion_9": "..."}}
No incluyas nada fuera de ese objeto JSON."""


# --------------------------------------------------------------------------------------------
# Bancos de verdad POR SECCIÓN (encargo #115-fix, ver docstring de `narrativa_llm.py`) — un banco
# global contra los ~278 valores del paquete de verdad completo dejaba pasar por COLISIÓN cifras
# inventadas sin relación con la sección citada (92/101 porcentajes arbitrarios colaban contra un
# caso real). Cada sección solo puede verificarse contra los datos que esa sección puede citar
# legítimamente — las listas de claves de ratios son las MISMAS que usan las funciones `tabla_*`
# de `mapeo_solucion.py` (importadas arriba, no duplicadas), para que tabla y verificador nunca
# diverjan silenciosamente.
# --------------------------------------------------------------------------------------------

def _ratios_filtrados_por_año(ratios_por_año: dict, claves: tuple[str, ...]) -> dict:
    return {año: {clave: ratios_por_año[año].get(clave) for clave in claves} for año in ratios_por_año}


def construir_bancos_de_verdad_por_seccion(paquete_verdad: dict) -> dict[str, set[float]]:
    """Un banco de verdad MÁS PEQUEÑO por cada una de las secciones 1-8 — `meta` (recuentos,
    años, sector/semilla) es global a todas (son datos que cualquier sección puede citar), el
    resto es EXCLUSIVO de la sección que legítimamente lo usa.

    La sección 9 (diagnóstico integrado) NO tiene entrada aquí — a diferencia del primer diseño
    del #115-fix, que le daba la UNIÓN ESTÁTICA de los bancos de 1-8 (seguía dejando pasar ~90%
    de un barrido de porcentajes arbitrarios: la unión incluye TODO lo que esas 8 secciones
    PODRÍAN citar, no solo lo que de verdad citaron), su banco se construye DINÁMICAMENTE, por
    ejecución, en `narrativa_llm.verificar_secciones` — acumulando las cifras que REALMENTE
    aparecieron en el texto generado de las secciones 1-8 de esa misma generación y pasaron su
    propia verificación. Este módulo no puede anticipar eso (no ve ningún texto todavía, solo el
    paquete de verdad), así que no intenta construir un banco de referencia para la sección 9."""
    banco_meta = construir_banco_de_verdad(paquete_verdad["meta"])

    # Sección 1 (resumen ejecutivo) — AMPLIACIÓN ACOTADA sobre `meta`, no el banco global (arreglo
    # del encargo #115, verificación 4): el prompt no prohíbe que el resumen ejecutivo adelante la
    # cifra clave de rentabilidad del caso —estilo habitual de un resumen ejecutivo real—, y los 3
    # casos de referencia lo hicieron (ROE en 2 de ellos, BAII% en el tercero). Se añaden SOLO
    # ROI/ROE (`RATIOS_RENTABILIDAD`) y BAII%/margen bruto (`RATIOS_ECONOMICO`) — los 2 pares de
    # cifras que de verdad aparecieron en esos 3 casos — no los 25 ratios del paquete completo:
    # sigue siendo un banco pequeño y con criterio, no un banco global bajo otro nombre.
    banco_seccion_1 = banco_meta | construir_banco_de_verdad({
        "ratios": _ratios_filtrados_por_año(paquete_verdad["ratios_por_año"], RATIOS_RENTABILIDAD + RATIOS_ECONOMICO),
    })

    banco_seccion_2 = banco_meta | construir_banco_de_verdad({
        "balance_pct_vertical_por_año": paquete_verdad["balance_pct_vertical_por_año"],
        "balance_pct_horizontal": paquete_verdad["balance_pct_horizontal"],
        "fondo_maniobra_eur_por_año": paquete_verdad["fondo_maniobra_eur_por_año"],
    })

    banco_seccion_3 = banco_meta | construir_banco_de_verdad({
        "ratios": _ratios_filtrados_por_año(paquete_verdad["ratios_por_año"], RATIOS_LIQUIDEZ),
        "pmm_por_año": paquete_verdad["pmm_por_año"],
        # Cruce explícito permitido con la sección 2 (fondo de maniobra), ver docstring del módulo.
        "fondo_maniobra_eur_por_año": paquete_verdad["fondo_maniobra_eur_por_año"],
    })

    banco_seccion_4 = banco_meta | construir_banco_de_verdad({
        "ratios": _ratios_filtrados_por_año(paquete_verdad["ratios_por_año"], RATIOS_ENDEUDAMIENTO),
        "concentracion_vencimientos_2025_pct": paquete_verdad["concentracion_vencimientos_2025_pct"],
    })

    banco_seccion_5 = banco_meta | construir_banco_de_verdad({
        "ratios": _ratios_filtrados_por_año(paquete_verdad["ratios_por_año"], RATIOS_ECONOMICO),
        "pyg_por_año": paquete_verdad["pyg_por_año"],
    })

    banco_seccion_6 = banco_meta | construir_banco_de_verdad({
        "ratios": _ratios_filtrados_por_año(paquete_verdad["ratios_por_año"], RATIOS_RENTABILIDAD),
        "dupont_por_año": paquete_verdad["dupont_por_año"],
    })

    banco_seccion_7 = banco_meta | construir_banco_de_verdad({"efe_por_año": paquete_verdad["efe_por_año"]})

    banco_seccion_8 = banco_meta | construir_banco_de_verdad({"señales": paquete_verdad["señales"]})

    return {
        "seccion_1": banco_seccion_1,
        "seccion_2": banco_seccion_2,
        "seccion_3": banco_seccion_3,
        "seccion_4": banco_seccion_4,
        "seccion_5": banco_seccion_5,
        "seccion_6": banco_seccion_6,
        "seccion_7": banco_seccion_7,
        "seccion_8": banco_seccion_8,
    }


# --------------------------------------------------------------------------------------------
# Ensamblado del documento — intercala las tablas del #113 (sin tocarlas) con la prosa del LLM.
# --------------------------------------------------------------------------------------------

TABLAS_POR_SECCION = {
    "seccion_1": lambda ev, ej, ef, cal: [tabla_semaforo(ev)],
    "seccion_2": lambda ev, ej, ef, cal: [tabla_balance_vertical(ej), tabla_balance_horizontal(ej), tabla_fondo_maniobra(ej)],
    "seccion_3": lambda ev, ej, ef, cal: [tabla_liquidez(ev), tabla_pmm(ev)],
    "seccion_4": lambda ev, ej, ef, cal: [tabla_endeudamiento(ev)],
    "seccion_5": lambda ev, ej, ef, cal: [tabla_economico(ej, ev), tabla_estructura_gastos(ej)],
    "seccion_6": lambda ev, ej, ef, cal: [tabla_rentabilidad(ev), tabla_dupont(ev, ej)],
    "seccion_7": lambda ev, ej, ef, cal: [tabla_efe(ef)],
    "seccion_8": lambda ev, ej, ef, cal: [t for t in [tabla_señales(ev)] if t is not None],
    "seccion_9": lambda ev, ej, ef, cal: [],
}


def ensamblar_documento_narrativo(evolucion, ejercicios, efes, calendario, textos_por_seccion: dict[str, str]) -> list[list]:
    """Construye las 9 secciones del flow de reportlab: título + tabla(s) del #113 (idénticas,
    reutilizadas tal cual) + un único párrafo de prosa del LLM por sección. El orden
    tabla-antes-que-prosa es deliberado — las tablas dan el dato exacto, la prosa lo interpreta."""
    secciones = []
    for clave in NOMBRES_SECCIONES:
        flow = [Paragraph(TITULOS_SECCIONES[clave], titulo_seccion)]
        flow.extend(TABLAS_POR_SECCION[clave](evolucion, ejercicios, efes, calendario))
        flow.append(Spacer(1, 0.15 * cm))
        flow.append(Paragraph(textos_por_seccion[clave], cuerpo))
        secciones.append(flow)
    return secciones


# --------------------------------------------------------------------------------------------
# Punto de entrada de alto nivel: caché -> (llamada real + verificación) -> ensamblado.
# --------------------------------------------------------------------------------------------

def obtener_narrativa(
    sector: str, segmento: str, ventas_objetivo: float, semilla: int, arquetipos_intensidades: dict[str, str],
    paquete_verdad: dict, modelo: str | None = None, forzar_regeneracion: bool = False,
) -> tuple[dict[str, str], dict]:
    """Devuelve `(textos_por_seccion, metadatos_cache)`. Usa la caché salvo `forzar_regeneracion`
    — la clave incluye el paquete de verdad completo, así que un cambio en el motor que altere
    cualquier cifra ya cacheada invalida la caché automáticamente (nunca sirve una narrativa
    desincronizada de los datos)."""
    clave = calcular_clave_cache(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades, paquete_verdad)
    if not forzar_regeneracion:
        cacheado = leer_cache(clave)
        if cacheado is not None:
            return cacheado["secciones"], {"clave": clave, "desde_cache": True, "intentos": cacheado["intentos"], "modelo": cacheado["modelo"]}

    prompt = construir_prompt(paquete_verdad)
    bancos_por_seccion = construir_bancos_de_verdad_por_seccion(paquete_verdad)
    resultado = generar_narrativa_con_verificacion(prompt, bancos_por_seccion, modelo=modelo)
    escribir_cache(clave, resultado.secciones, resultado.modelo, resultado.intentos)
    return resultado.secciones, {"clave": clave, "desde_cache": False, "intentos": resultado.intentos, "modelo": resultado.modelo}
