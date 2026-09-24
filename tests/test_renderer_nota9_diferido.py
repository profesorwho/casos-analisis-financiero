"""Nota 9 — texto del impuesto diferido (activo/pasivo) — encargo #111.

El #108 pedía un test de 3 escenarios para el impuesto diferido (solo subvención, solo
cobertura, ambas) y no se escribió — los 4 tests de `test_renderer_nota9.py` cubren solo
Hacienda deudora/acreedora. Este test cierra ese hueco (con un 4º escenario, "sin diferido") y
protege el defecto 1 del #111: con SOLO activo diferido (cobertura con saldo negativo, sin
subvención ni cobertura positiva), el párrafo antes decía "Existe ADEMÁS ... por signo contrario
A LA ANTERIOR" sin que existiera ningún párrafo anterior — texto colgante, referido a algo que
no está en la Nota.
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

from clasificacion import clasificar_caso  # noqa: E402
from mapeo_balance import mapear_balance_activo, mapear_balance_pn_pasivo  # noqa: E402
from mapeo_memoria import nota_9_situacion_fiscal  # noqa: E402

AÑOS_DIFERIDO = (2024, 2025)

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


def _texto_plano_nota9(ejercicios) -> str:
    flow = nota_9_situacion_fiscal(ejercicios)
    trozos = [re.sub(r"<[^>]+>", "", getattr(e, "text", "")) for e in flow if hasattr(e, "text")]
    return "\n".join(trozos)


def _importes_diferido_balance(ejercicios, modelo):
    activo = next(l for l in mapear_balance_activo(ejercicios, modelo) if l.etiqueta == "Activos por impuesto diferido")
    pasivo = next(l for l in mapear_balance_pn_pasivo(ejercicios, modelo) if l.etiqueta == "Pasivos por impuesto diferido")
    return (
        {a: activo.valores[a] for a in AÑOS_DIFERIDO},
        {a: pasivo.valores[a] for a in AÑOS_DIFERIDO},
    )


def _generar(nombre_escenario):
    p = ESCENARIOS[nombre_escenario]
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(
        p["sector"], p["segmento"], p["ventas_objetivo"], p["semilla"], p["arquetipos"],
        catalogo=catalogo, arquetipos=arquetipos,
    )
    ejercicios = evolucion.ejercicios
    modelo = clasificar_caso(evolucion, p["sector"], p["segmento"], catalogo)
    return ejercicios, modelo


@pytest.mark.parametrize("nombre_escenario", list(ESCENARIOS))
def test_importes_de_diferido_citados_igualan_el_balance(nombre_escenario):
    ejercicios, modelo = _generar(nombre_escenario)
    texto = _texto_plano_nota9(ejercicios)
    activo_balance, pasivo_balance = _importes_diferido_balance(ejercicios, modelo)

    for año, importe in activo_balance.items():
        if importe != 0:
            assert _cifra_en_texto(texto, importe), (
                f"{nombre_escenario}/{año}: activo diferido {importe} no aparece en la Nota 9:\n{texto}"
            )
    for año, importe in pasivo_balance.items():
        if importe != 0:
            assert _cifra_en_texto(texto, importe), (
                f"{nombre_escenario}/{año}: pasivo diferido {importe} no aparece en la Nota 9:\n{texto}"
            )


def _cifra_en_texto(texto, importe, tolerancia=1.0):
    """Busca cualquier cifra con formato `fmt_eur` en el texto que esté a <=tolerancia del
    importe esperado (fmt_eur redondea a € entero)."""
    for cifra_str in re.findall(r"\d[\d.]*\d|\d", texto):
        cifra = float(cifra_str.replace(".", ""))
        if abs(cifra - importe) <= tolerancia:
            return True
    return False


def test_solo_cobertura_no_tiene_texto_colgante():
    ejercicios, _ = _generar("solo_cobertura")
    texto = _texto_plano_nota9(ejercicios)
    assert "además" not in texto.lower()
    # "por signo contrario a la anterior" (frase completa) — no basta con buscar la sub-cadena
    # "la anterior": el párrafo de pagos a cuenta/tipo efectivo, presente en CUALQUIER Nota 9 con
    # diferido, ya menciona "la tabla anterior" (la tabla de Resultado/tipo efectivo de arriba,
    # sin relación con el defecto 1) — "tabla" termina en "la", así que "la anterior" aparece
    # como sub-cadena de "tabla anterior" incluso sin el texto colgante del defecto.
    assert "por signo contrario a la anterior" not in texto.lower()
    assert "activo por impuesto diferido" in texto
    assert "pasivo por impuesto diferido" not in texto


def test_solo_subvencion_solo_menciona_pasivo():
    ejercicios, _ = _generar("solo_subvencion")
    texto = _texto_plano_nota9(ejercicios)
    assert "pasivo por impuesto diferido" in texto
    assert "activo por impuesto diferido" not in texto


def test_ambas_contienen_los_dos_parrafos():
    ejercicios, _ = _generar("ambas")
    texto = _texto_plano_nota9(ejercicios)
    assert "pasivo por impuesto diferido" in texto
    assert "activo por impuesto diferido" in texto
    assert "además" in texto.lower()
    assert "la anterior" in texto.lower()


def test_sin_diferido_mantiene_la_frase_generica():
    ejercicios, _ = _generar("sin_diferido")
    texto = _texto_plano_nota9(ejercicios)
    assert "No existen diferencias significativas" in texto
    assert "activo por impuesto diferido" not in texto
    assert "pasivo por impuesto diferido" not in texto
