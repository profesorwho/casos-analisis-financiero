"""Nota 9 (situación fiscal) == Balance — encargo #108.

La Nota 9 (`renderer/mapeo_memoria.py::nota_9_situacion_fiscal`) recalculaba "Hacienda Pública,
deudora/acreedora por impuesto sobre beneficios" con su propia fórmula (constante
`FRACCION_PAGOS_A_CUENTA_IS` duplicada, sin el techo defensivo que el motor sí aplica contra el
presupuesto disponible de "clientes"/"proveedores" — ver `motor/empresa_base.py` y
`motor/evolucion_arquetipo.py`) — divergía del Balance en 5/648 ejercicios de un barrido de 216
casos × 3 años (aumento_clientes:moderado). El arreglo: la Nota 9 lee el mismo dato que el
Balance (`deudores_desglose_eur["hacienda_publica_deudora"]`/
`acreedores_desglose_eur["hacienda_publica_acreedora"]"), sin recalcular nada.

Este test extrae el valor RENDERIZADO de la tabla de la Nota 9 (no solo el dato crudo del motor,
que sería trivialmente igual por construcción) y lo compara contra la línea correspondiente del
Balance generado por `mapeo_balance.py` — ambos módulos leen la misma fuente, pero de forma
independiente. Incluye 2 de los 5 casos de la tabla del encargo (19/pequeñas/sem0 y
85/grandes_medianas/sem1) que SÍ activaban el techo defensivo del motor, divergiendo con la
fórmula antigua.
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

AÑOS = (2023, 2024, 2025)
ARQUETIPOS_INTENSIDADES = {"aumento_clientes": "moderado"}

CASOS = [
    # Los 2 que activaban el techo defensivo con la fórmula antigua (tabla del encargo #108).
    pytest.param("19", "pequeñas", 5_000_000.0, 0, id="19-pequeñas-sem0-techo"),
    pytest.param("85", "grandes_medianas", 15_000_000.0, 1, id="85-grandes_medianas-sem1-techo"),
    # 2 adicionales sin techo activado, para no proteger solo el caso límite.
    pytest.param("28", "grandes_medianas", 15_000_000.0, 15, id="28-grandes_medianas-sem15"),
    pytest.param("47.1", "grandes_medianas", 15_000_000.0, 3, id="47.1-grandes_medianas-sem3"),
]


def _parsear_eur(texto: str) -> float:
    m = re.search(r"\(?([\d.]+)\)?\s*$", texto.strip())
    valor = float(m.group(1).replace(".", ""))
    return -valor if texto.strip().startswith("(") else valor


def _hacienda_de_la_nota9(ejercicios) -> dict:
    """Extrae, por año, el importe de la fila "Hacienda Pública..." de la tabla RENDERIZADA de
    la Nota 9 (no el dato crudo del motor — así detecta una regresión si la Nota volviera a
    recalcular en vez de leer)."""
    flow = nota_9_situacion_fiscal(ejercicios)
    valores = {}
    año_actual = None
    for elem in flow:
        texto = getattr(elem, "text", None)
        if texto and texto.startswith("<b>Ejercicio"):
            año_actual = int(re.search(r"\d{4}", texto).group())
        if hasattr(elem, "_cellvalues") and año_actual is not None:
            for fila in elem._cellvalues:
                if fila[0].startswith("Hacienda Pública"):
                    signo = -1.0 if "acreedora" in fila[0] else 1.0
                    valores[año_actual] = signo * _parsear_eur(fila[1])
    return valores


def _hacienda_del_balance(ejercicios, modelo) -> dict:
    """Neta (deudora - acreedora) según las líneas "Activos/Pasivos por impuesto corriente" del
    Balance, calculadas por `mapeo_balance.py` de forma independiente a `mapeo_memoria.py`."""
    activo_lineas = mapear_balance_activo(ejercicios, modelo)
    pasivo_lineas = mapear_balance_pn_pasivo(ejercicios, modelo)
    deudora = next(l for l in activo_lineas if l.etiqueta == "Activos por impuesto corriente")
    acreedora = next(l for l in pasivo_lineas if l.etiqueta == "Pasivos por impuesto corriente")
    return {año: deudora.valores[año] - acreedora.valores[año] for año in AÑOS}


@pytest.mark.parametrize("sector, segmento, ventas_objetivo, semilla", CASOS)
def test_nota_9_hacienda_iguala_balance(sector, segmento, ventas_objetivo, semilla):
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(
        sector, segmento, ventas_objetivo, semilla, ARQUETIPOS_INTENSIDADES,
        catalogo=catalogo, arquetipos=arquetipos,
    )
    ejercicios = evolucion.ejercicios
    modelo = clasificar_caso(evolucion, sector, segmento, catalogo)

    nota9 = _hacienda_de_la_nota9(ejercicios)
    balance = _hacienda_del_balance(ejercicios, modelo)

    for año in AÑOS:
        assert abs(nota9[año] - balance[año]) < 1.0, (
            f"{sector}/{segmento}/sem{semilla}/{año}: Nota 9 ({nota9[año]}) != Balance ({balance[año]})"
        )
