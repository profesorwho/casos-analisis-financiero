"""Coherencia interna del renderizador de PDF (`renderer/`) — encargo #106.

`renderer/` es una capa de presentación pura: vive fuera del paquete `motor` y sus módulos se
importan entre sí con nombres sueltos (`from tipos import ...`), así que este test añade
`renderer/` a `sys.path` antes de importar los mapeos, igual que hacen los propios drivers de
`renderer/` (ver `Path(__file__).resolve().parent` en cada uno).

Invariante comprobado: en el Balance y la PyG generados por `mapear_balance_activo`/
`mapear_balance_pn_pasivo`/`mapear_pyg`, la suma de las líneas de detalle (nivel N+1) debe
igualar el subtotal de su línea padre (nivel N, en negrita), con tolerancia 1€ — para cualquier
bloque que el renderizador presente como una descomposición real. La PyG NO se comprueba con el
mismo criterio genérico en sus líneas "RESULTADO..." (nivel 0/1): son subtotales EN CASCADA de
las líneas oficiales 1-20 que las preceden, no un padre cuyos "hijos" sean las líneas de nivel
inferior que le siguen inmediatamente — solo se comprueban ahí las descomposiciones reales
(1→a/b, 4→a-d, 6→a-c, 7→a-e, 14→a/b), nivel ≥2.

Bug real que este test habría detectado antes del fix de #106.1: `mapeo_balance.py` buscaba la
clave `activos_impuesto_corriente`/`pasivos_impuesto_corriente` en `deudores_desglose_eur`/
`acreedores_desglose_eur`, pero el motor expone `hacienda_publica_deudora`/
`hacienda_publica_acreedora` — la sub-línea salía siempre a 0 y "III Deudores.../V Acreedores..."
no sumaban su propio subtotal.

La lógica de comprobación vive en `renderer/invariantes.py` (movida ahí en #110 para que
`generar_caso_completo` pueda reutilizarla como guarda en tiempo de generación, sin duplicar
código) — este test solo la importa y la ejercita sobre un barrido de casos concretos.
"""
import sys
from pathlib import Path

import pytest

_RENDERER_DIR = Path(__file__).resolve().parent.parent / "renderer"
sys.path.insert(0, str(_RENDERER_DIR))

from motor.arquetipos import cargar_arquetipos  # noqa: E402
from motor.catalogo import cargar_y_validar_catalogo  # noqa: E402
from motor.memoria import generar_caso_combinado  # noqa: E402

from clasificacion import clasificar_caso  # noqa: E402
from invariantes import verificar_invariantes_balance_pyg  # noqa: E402

ARQUETIPOS_INTENSIDADES = {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"}

CASOS = [
    pytest.param("28", "grandes_medianas", 15_000_000.0, 15, "normal", id="28-grandes_medianas-sem15"),
    pytest.param("28", "pequeñas", 5_000_000.0, 15, "abreviado", id="28-pequeñas-sem15"),
    pytest.param("10.1", "pequeñas", 5_000_000.0, 1, "abreviado", id="10.1-pequeñas-sem1"),
    pytest.param("47.1", "grandes_medianas", 15_000_000.0, 3, "normal", id="47.1-grandes_medianas-sem3"),
]


@pytest.mark.parametrize("sector, segmento, ventas_objetivo, semilla, modelo_esperado", CASOS)
def test_balance_y_pyg_sub_lineas_suman_su_subtotal(sector, segmento, ventas_objetivo, semilla, modelo_esperado):
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(
        sector, segmento, ventas_objetivo, semilla, ARQUETIPOS_INTENSIDADES,
        catalogo=catalogo, arquetipos=arquetipos,
    )
    ejercicios = evolucion.ejercicios
    modelo = clasificar_caso(evolucion, sector, segmento, catalogo)
    assert modelo == modelo_esperado, f"Clasificación legal inesperada: {modelo} != {modelo_esperado}"

    violaciones = verificar_invariantes_balance_pyg(ejercicios, modelo)

    assert not violaciones, (
        f"Sub-líneas que no suman su subtotal en {sector}/{segmento}/sem{semilla}/{modelo}: {violaciones}"
    )
