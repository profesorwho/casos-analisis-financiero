"""Tests del paso 1 del flujo manual de narrativa (encargo #115, `renderer/preparar_solucion_
narrativa.py`) — sin llamar a ninguna API, sin depender de `ANTHROPIC_API_KEY`. Cubre lo pedido
explícitamente: exportar el prompt + el `.meta.json` de un caso nuevo, y el atajo cuando el caso
ya está en caché (no repite el proceso ni escribe un `.meta.json` nuevo)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "renderer"))

from narrativa_llm import calcular_clave_cache, escribir_cache
from preparar_solucion_narrativa import CABECERA_INSTRUCCIONES, exportar_prompt

SECTOR, SEGMENTO, VENTAS, SEMILLA = "28", "grandes_medianas", 15_000_000.0, 15
ARQUETIPOS = {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}


@pytest.fixture(autouse=True)
def _cache_aislada(monkeypatch, tmp_path):
    """Nunca debe tocar `renderer/narrativa_cache/` real — cada test usa su propio directorio.
    `leer_cache`/`escribir_cache` resuelven `DIRECTORIO_CACHE` en cada llamada (vía `ruta_cache`),
    así que basta con parchear el atributo del módulo `narrativa_llm`."""
    import narrativa_llm
    monkeypatch.setattr(narrativa_llm, "DIRECTORIO_CACHE", tmp_path / "narrativa_cache")


def test_exportar_prompt_caso_nuevo_escribe_prompt_y_meta(tmp_path):
    ruta_salida = tmp_path / "prompt.txt"
    resultado = exportar_prompt(SECTOR, SEGMENTO, VENTAS, SEMILLA, ARQUETIPOS, str(ruta_salida))

    assert resultado["ya_en_cache"] is False
    assert Path(resultado["ruta_prompt"]).exists()
    assert Path(resultado["ruta_meta"]).exists()

    contenido_prompt = ruta_salida.read_text(encoding="utf-8")
    assert contenido_prompt.startswith(CABECERA_INSTRUCCIONES)
    assert "Eres un profesor de análisis económico-financiero" in contenido_prompt
    assert '"seccion_9"' in contenido_prompt

    ruta_meta = ruta_salida.with_suffix(".meta.json")
    metadatos = json.loads(ruta_meta.read_text(encoding="utf-8"))
    assert metadatos["sector"] == SECTOR
    assert metadatos["segmento"] == SEGMENTO
    assert metadatos["ventas_objetivo"] == VENTAS
    assert metadatos["semilla"] == SEMILLA
    assert metadatos["arquetipos_intensidades"] == ARQUETIPOS
    assert metadatos["clave"] == resultado["clave"]
    assert "paquete_verdad" in metadatos and isinstance(metadatos["paquete_verdad"], dict)
    assert metadatos["paquete_verdad"]["meta"]["n_arquetipos"] == 2


def test_exportar_prompt_es_deterministico(tmp_path):
    r1 = exportar_prompt(SECTOR, SEGMENTO, VENTAS, SEMILLA, ARQUETIPOS, str(tmp_path / "p1.txt"))
    r2 = exportar_prompt(SECTOR, SEGMENTO, VENTAS, SEMILLA, ARQUETIPOS, str(tmp_path / "p2.txt"))
    assert r1["clave"] == r2["clave"]
    assert (tmp_path / "p1.txt").read_text(encoding="utf-8") == (tmp_path / "p2.txt").read_text(encoding="utf-8")


def test_exportar_prompt_caso_ya_en_cache_no_escribe_meta(tmp_path, monkeypatch):
    """Si la clave YA tiene una narrativa verificada en caché, no repite el proceso: escribe un
    aviso corto y NO crea ningún `.meta.json` (no hay nada que importar en el paso 2)."""
    ruta_salida = tmp_path / "prompt.txt"

    # Averigua la clave sin escribir nada (llamando primero en un directorio de caché vacío no
    # rellena la caché) — reconstruye el paquete de verdad para calcular la MISMA clave.
    from mapeo_solucion_narrativo import construir_paquete_verdad
    from motor.arquetipos import cargar_arquetipos
    from motor.catalogo import cargar_y_validar_catalogo
    from motor.memoria import generar_caso_combinado
    from motor.efe import generar_efe
    from motor.calendario_deuda import calcular_calendario_deuda

    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(SECTOR, SEGMENTO, VENTAS, SEMILLA, ARQUETIPOS, catalogo=catalogo, arquetipos=arquetipos)
    ejercicios = evolucion.ejercicios
    efes = {2024: generar_efe(ejercicios[2023], ejercicios[2024], True), 2025: generar_efe(ejercicios[2024], ejercicios[2025], True)}
    calendario = calcular_calendario_deuda(evolucion)
    paquete_verdad = construir_paquete_verdad(evolucion, ejercicios, efes, calendario, arquetipos)
    clave = calcular_clave_cache(SECTOR, SEGMENTO, VENTAS, SEMILLA, ARQUETIPOS, paquete_verdad)

    escribir_cache(clave, {f"seccion_{i}": "texto ya verificado" for i in range(1, 10)}, "modelo-de-prueba", intentos=1)

    resultado = exportar_prompt(SECTOR, SEGMENTO, VENTAS, SEMILLA, ARQUETIPOS, str(ruta_salida))
    assert resultado == {"ya_en_cache": True, "clave": clave, "ruta_prompt": None, "ruta_meta": None}
    assert ruta_salida.exists()
    assert not ruta_salida.with_suffix(".meta.json").exists()
    assert clave in ruta_salida.read_text(encoding="utf-8")
