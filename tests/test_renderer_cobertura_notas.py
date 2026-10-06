"""Cobertura permanente de notas de memoria en el PDF (#120-A) y nombre de sector (#120-D).

Falla si el filtro de ids de `renderer/mapeo_memoria.py` se desalinea de los ids reales con que
el motor etiqueta cada `NotaMemoria` (bug original: "informacion_relevante" vs.
"informacion_relevante_memoria", la nota se descartaba en silencio)."""
from __future__ import annotations

import re

import pdfplumber
import pytest

from motor.catalogo import cargar_y_validar_catalogo
from motor.memoria import generar_caso_combinado
from renderer.generar_caso_completo import generar_caso_completo, nombre_sector
from renderer.mapeo_memoria import _notas_narrativas_por_tema

BASE = {"aumento_clientes": "leve"}  # arquetipo cuantitativo mínimo exigido por generar_caso_combinado

CASOS = [
    ("dependencia_pocos_clientes", "moderado", BASE, "28", "pequeñas", 5e6, 1),
    ("activo_mantenido_venta", "moderado", BASE, "28", "pequeñas", 5e6, 1),
    ("operaciones_vinculadas", "moderado", {}, "28", "grandes_medianas", 15e6, 1),
    ("coberturas", "moderado", {}, "28", "grandes_medianas", 15e6, 1),
    ("informacion_relevante_memoria", "leve", BASE, "46", "pequeñas", 5e6, 1447),
    ("informacion_relevante_memoria", "moderado", BASE, "28", "pequeñas", 5e6, 1),
    ("informacion_relevante_memoria", "fuerte", BASE, "28", "pequeñas", 5e6, 1),
    ("adquisicion", "moderado", {}, "28", "grandes_medianas", 15e6, 1),
    ("riesgo_refinanciacion", "moderado", {}, "28", "grandes_medianas", 15e6, 1),
    ("mejora_ebitda", "fuerte", {}, "28", "pequeñas", 5e6, 3),  # caso límite, nota opcional
]


def _plano(texto: str) -> str:
    return re.sub(r"\s+", "", texto)


def _texto_pdf(ruta) -> str:
    with pdfplumber.open(ruta) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


@pytest.mark.parametrize("arq,intensidad,extra,sector,segmento,ventas,semilla", CASOS)
def test_toda_nota_de_memoria_del_motor_llega_al_pdf(tmp_path, arq, intensidad, extra, sector, segmento, ventas, semilla):
    arqs = {arq: intensidad, **extra}
    evolucion = generar_caso_combinado(sector, segmento, ventas, semilla, arqs)
    notas = [n for n in _notas_narrativas_por_tema(evolucion, evolucion.ejercicios) if n.arquetipo_id == arq]
    assert notas, f"el caso de prueba no genera nota para {arq}"
    ruta = tmp_path / "caso.pdf"
    generar_caso_completo(sector, segmento, ventas, semilla, arqs, "Empresa Ficticia, S.L.", str(ruta), estricto=True)
    texto = _plano(_texto_pdf(ruta))
    for n in notas:
        assert _plano(n.texto) in texto, f"la nota de {n.arquetipo_id} no aparece en el PDF"


def test_nombre_sector_de_los_27_sectores_no_cae_en_el_fallback():
    catalogo = cargar_y_validar_catalogo()
    codigos = {re.search(r"\(([^()]*)\)\s*$", s).group(1) for s in catalogo["sector"].unique()}
    assert len(codigos) == 27
    for c in codigos:
        nombre = nombre_sector(c, catalogo)
        assert not re.search(r"sector \d", nombre) and not re.search(r"\(.*\)", nombre) and nombre.strip()
    assert nombre_sector("28", catalogo) == "Fabricación de maquinaria y equipo"
    assert nombre_sector("46", catalogo) == "Comercio al por mayor"


def test_ecpn_documento_b_lleva_el_aviso_de_no_exigido_solo_en_abreviado(tmp_path):
    """#120-B — art. 257.3 LSC vigente (Ley 22/2015): con balance abreviado ni el ECPN ni el EFE
    son obligatorios; el aviso debe cubrir los dos documentos del ECPN (A y B)."""
    aviso = "Incluido con fines didácticos, no exigido en Abreviado"
    casos = {
        "abreviado": ("46", "pequeñas", 5e6, 1447, {"aumento_clientes": "fuerte"}),
        "normal": ("28", "grandes_medianas", 28e6, 238, {"crecimiento_destruccion_caja": "leve"}),
    }
    for modelo, (sector, seg, ventas, semilla, arqs) in casos.items():
        ruta = tmp_path / f"{modelo}.pdf"
        assert generar_caso_completo(sector, seg, ventas, semilla, arqs, "E, S.L.", str(ruta)) == modelo
        texto = _texto_pdf(ruta)
        # Subtítulo de la tabla que sigue a cada título de documento
        for titulo in ("ECPN — Documento A", "ECPN — Documento B"):
            i = texto.index(titulo)
            cabecera = " ".join(texto[i:i + 400].split("\n")[:4])
            assert (aviso in cabecera) == (modelo == "abreviado"), (modelo, titulo, cabecera)
