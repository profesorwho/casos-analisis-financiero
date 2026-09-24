"""Nota 4 coherente con la Nota 9 — encargo #111, defecto 3.

`nota_4_normas_registro` afirmaba siempre "sin diferencias significativas entre resultado
contable y base imponible" aunque el caso tuviera subvención/cobertura con impuesto diferido —
en ese caso la Nota 9 SÍ explica una diferencia temporaria en detalle, contradiciendo a la Nota 4.
Corregido: la frase de la Nota 4 pasa a ser condicional (mismo criterio que activa el párrafo de
diferido en la Nota 9) y remite a la nota 9 cuando aplica.
"""
import re
import sys
from pathlib import Path

import pytest

_RENDERER_DIR = Path(__file__).resolve().parent.parent / "renderer"
sys.path.insert(0, str(_RENDERER_DIR))

from motor.arquetipos import cargar_arquetipos  # noqa: E402
from motor.catalogo import cargar_y_validar_catalogo  # noqa: E402
from motor.memoria import generar_caso_combinado  # noqa: E402

from mapeo_memoria import nota_4_normas_registro, nota_9_situacion_fiscal  # noqa: E402

ESCENARIOS = {
    "sin_diferido": dict(sector="85", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=0,
                          arquetipos={"aumento_clientes": "leve"}),
    "solo_subvencion": dict(sector="46", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=1,
                             arquetipos={"aumento_clientes": "leve"}),
    "solo_cobertura": dict(sector="85", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=0,
                            arquetipos={"coberturas": "fuerte"}),
    "ambas": dict(sector="46", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=1,
                  arquetipos={"coberturas": "fuerte"}),
}


def _texto_plano(flow) -> str:
    return "\n".join(re.sub(r"<[^>]+>", "", getattr(e, "text", "")) for e in flow if hasattr(e, "text"))


def _generar_ejercicios(nombre_escenario):
    p = ESCENARIOS[nombre_escenario]
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(
        p["sector"], p["segmento"], p["ventas_objetivo"], p["semilla"], p["arquetipos"],
        catalogo=catalogo, arquetipos=arquetipos,
    )
    return evolucion.ejercicios


@pytest.mark.parametrize("nombre_escenario", list(ESCENARIOS))
def test_nota_4_coherente_con_nota_9(nombre_escenario):
    """Nota 4 y Nota 9 deben coincidir en si HAY o NO diferencias temporarias que mencionar."""
    ejercicios = _generar_ejercicios(nombre_escenario)
    texto_n9 = _texto_plano(nota_9_situacion_fiscal(ejercicios))
    texto_n4 = _texto_plano(nota_4_normas_registro(ejercicios))

    n9_habla_de_diferencias = "diferencia temporaria" in texto_n9
    n4_habla_de_diferencias = "diferencias temporarias descritas en la nota 9" in texto_n4
    n4_dice_sin_diferencias = "sin diferencias significativas" in texto_n4

    assert n9_habla_de_diferencias == n4_habla_de_diferencias, (
        f"{nombre_escenario}: Nota 9 {'sí' if n9_habla_de_diferencias else 'no'} habla de "
        f"diferencias temporarias, Nota 4 {'sí' if n4_habla_de_diferencias else 'no'}"
    )
    assert n4_habla_de_diferencias != n4_dice_sin_diferencias, "Nota 4 no puede decir ambas cosas a la vez"
