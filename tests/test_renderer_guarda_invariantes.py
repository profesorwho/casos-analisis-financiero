"""Guarda de invariantes en `generar_caso_completo` — encargo #110.

La investigación #109 dejó documentado, sin tocar el motor, que el caso
47.1/grandes_medianas/ventas 15M€/semilla 2/{aumento_clientes:fuerte,
dependencia_pocos_clientes:fuerte}, ejercicio 2025, genera un Balance cuya sub-línea "II
Provisiones a corto plazo" no cabe en su propio subtotal "C PASIVO CORRIENTE" (el plug de cuadre
vacía `otras_deudas_corto`) — diferencia de 47.723,11€. Decisión ya tomada: el motor no se toca;
lo que se pide es que ese caso no se genere en silencio. `generar_caso_completo` ahora ejecuta
`renderer/invariantes.py` tras construir las líneas del Balance/PyG y avisa (`warnings.warn`,
`InvarianteSubtotalWarning`) o, con `estricto=True`, lanza excepción.

Este test comprueba el comportamiento observable de la guarda, no solo el cálculo de
`invariantes.py` (ya cubierto por `test_renderer_coherencia.py`): que el aviso se emite en el
caso #109 y no en los 2 casos de referencia habituales, y que `estricto=True` convierte el aviso
en excepción — y que todo esto desaparece si se revierte el código de la guarda (demostrado
manualmente con `git stash`, documentado en decisiones_plausibilidad.md #110).
"""
import sys
import warnings
from pathlib import Path

import pytest

_RENDERER_DIR = Path(__file__).resolve().parent.parent / "renderer"
sys.path.insert(0, str(_RENDERER_DIR))

from generar_caso_completo import generar_caso_completo  # noqa: E402
from invariantes import InvarianteSubtotalWarning  # noqa: E402

CASO_109 = dict(
    sector="47.1", segmento="grandes_medianas", ventas_objetivo=15_000_000.0, semilla=2,
    arquetipos_intensidades={"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
    nombre_empresa="Test SA",
)
CASOS_REFERENCIA = [
    pytest.param("28", "grandes_medianas", 15_000_000.0, 15, id="28-grandes_medianas-sem15"),
    pytest.param("28", "pequeñas", 5_000_000.0, 15, id="28-pequeñas-sem15"),
]
ARQUETIPOS_REFERENCIA = {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}


def test_guarda_avisa_en_el_caso_109(tmp_path):
    ruta = tmp_path / "caso_109.pdf"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        modelo = generar_caso_completo(**CASO_109, ruta_salida=str(ruta))
    assert modelo == "normal"
    avisos = [x for x in w if issubclass(x.category, InvarianteSubtotalWarning)]
    assert len(avisos) == 1, f"Se esperaba exactamente 1 aviso, hubo {len(avisos)}"
    mensaje = str(avisos[0].message)
    assert "C PASIVO CORRIENTE" in mensaje
    assert "2025" in mensaje
    assert "47,723.11" in mensaje or "47723.11" in mensaje
    assert ruta.exists(), "El PDF debe generarse igual, con o sin aviso"


def test_guarda_estricto_lanza_excepcion_en_el_caso_109(tmp_path):
    ruta = tmp_path / "caso_109_estricto.pdf"
    with pytest.raises(InvarianteSubtotalWarning):
        generar_caso_completo(**CASO_109, ruta_salida=str(ruta), estricto=True)


@pytest.mark.parametrize("sector, segmento, ventas_objetivo, semilla", CASOS_REFERENCIA)
def test_guarda_no_avisa_en_los_casos_de_referencia(tmp_path, sector, segmento, ventas_objetivo, semilla):
    ruta = tmp_path / "caso_referencia.pdf"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        generar_caso_completo(
            sector, segmento, ventas_objetivo, semilla, ARQUETIPOS_REFERENCIA,
            "Test SA", str(ruta),
        )
    avisos = [x for x in w if issubclass(x.category, InvarianteSubtotalWarning)]
    assert not avisos, f"No se esperaba ningún aviso en {sector}/{segmento}/sem{semilla}: {avisos}"
