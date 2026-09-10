"""Tests de motor/memoria.py — los 5 arquetipos de memoria pura (7, 19, 20, 21, 22, sección
2.24). No hay stress test cuantificado de plausibilidad NUMÉRICA (estos arquetipos no mueven
ninguna cifra del balance/PyG), pero sí se verifica: reproducibilidad por semilla, variedad real
de redacciones (χ² sobre la distribución de plantillas, mismo método que ya destapó el sesgo de
`nota_memoria`), y que las cifras citadas en el texto (arquetipos 20 y 21) se mantengan dentro de
cotas de plausibilidad — ni por encima del tamaño de la empresa, ni tan pequeñas que suenen poco
creíbles como hecho "relevante" de memoria.
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.memoria import (
    PLANTILLAS_ACTIVO_MANTENIDO_VENTA,
    PLANTILLAS_COBERTURAS,
    PLANTILLAS_DEPENDENCIA_CLIENTES,
    RANGOS_CONCENTRACION_CLIENTES,
    SUELO_IMPORTE_VINCULADAS_EUR,
    SUELO_NOCIONAL_COBERTURA_EUR,
    _NOTAS_COMODIN,
    _OPERACIONES_VINCULADAS,
    generar_nota_activo_mantenido_venta,
    generar_nota_coberturas,
    generar_nota_dependencia_clientes,
    generar_nota_informacion_relevante,
    generar_nota_memoria_pura,
    generar_nota_operaciones_vinculadas,
)

VENTAS_OBJETIVO_2023 = 8_000_000.0
SEMILLAS = range(8)

SECTORES = [
    pytest.param("24.1", id="industrial-siderurgia"),
    pytest.param("62", id="servicios-tic"),
    pytest.param("47.1", id="comercio-supermercados"),
]


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _ejercicio(catalogo, arquetipos, sector, intensidad, semilla):
    # Los arquetipos de memoria pura no generan su propia evolución (no tienen efectos
    # numéricos): se apoyan en un caso cuantitativo cualquiera ya cerrado para tener datos reales
    # de empresa a los que referenciar cifras — "exceso_stock" (5) por ser el más simple.
    evolucion = generar_evolucion_arquetipo(
        sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    return evolucion.ejercicios[2025]


def _prefijo(plantilla: str) -> str:
    return plantilla.split("{")[0]


PREFIJOS = {
    "dependencia_pocos_clientes": [_prefijo(p) for p in PLANTILLAS_DEPENDENCIA_CLIENTES],
    "activo_mantenido_venta": [_prefijo(p) for p in PLANTILLAS_ACTIVO_MANTENIDO_VENTA],
    "operaciones_vinculadas": [_prefijo(p) for p, _ in _OPERACIONES_VINCULADAS],
    "coberturas": [_prefijo(p) for p in PLANTILLAS_COBERTURAS],
    "informacion_relevante_memoria": [_prefijo(t) for t, _ in _NOTAS_COMODIN],
}


def _indice_plantilla(arquetipo_id: str, texto: str) -> int:
    coincidencias = [i for i, p in enumerate(PREFIJOS[arquetipo_id]) if texto.startswith(p)]
    assert len(coincidencias) == 1, f"{arquetipo_id}: {len(coincidencias)} prefijos coinciden con: {texto[:60]}"
    return coincidencias[0]


# --------------------------------------------------------------------------------------------
# Reproducibilidad — los 5 arquetipos.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("arquetipo_id", list(PREFIJOS))
@pytest.mark.parametrize("sector", SECTORES)
def test_memoria_pura_reproducible(catalogo, arquetipos, arquetipo_id, sector):
    for semilla in SEMILLAS:
        ejercicio = _ejercicio(catalogo, arquetipos, sector, "fuerte", semilla)
        nota_a = generar_nota_memoria_pura(arquetipo_id, sector, "grandes_medianas", "fuerte", semilla, ejercicio)
        nota_b = generar_nota_memoria_pura(arquetipo_id, sector, "grandes_medianas", "fuerte", semilla, ejercicio)
        assert nota_a.texto == nota_b.texto


# --------------------------------------------------------------------------------------------
# Variedad de redacciones (χ²) — barrido representativo (27 sectores x 3 intensidades x 4
# semillas = 324 casos), mismo método que destapó el sesgo de nota_memoria.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("arquetipo_id", list(PREFIJOS))
def test_memoria_pura_distribucion_de_plantillas_no_esta_sesgada(catalogo, arquetipos, arquetipo_id):
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    n_plantillas = len(PREFIJOS[arquetipo_id])
    conteo = {i: 0 for i in range(n_plantillas)}
    total = 0
    for codigo in codigos:
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                ejercicio = _ejercicio(catalogo, arquetipos, codigo, intensidad, semilla)
                nota = generar_nota_memoria_pura(arquetipo_id, codigo, "grandes_medianas", intensidad, semilla, ejercicio)
                conteo[_indice_plantilla(arquetipo_id, nota.texto)] += 1
                total += 1
    esperado = total / n_plantillas
    chi2 = sum((conteo[i] - esperado) ** 2 / esperado for i in range(n_plantillas))
    # Crítico de chi-cuadrado a p=0.01: ~13.3 (df=4) / ~21.7 (df=9) — margen amplio sobre el
    # crítico a p=0.05 (9.49 / 16.92) para evitar falsos positivos por variabilidad de muestra.
    critico_p01 = {4: 13.3, 9: 21.7}[n_plantillas - 1]
    assert chi2 < critico_p01, f"{arquetipo_id}: chi2={chi2:.2f} (df={n_plantillas-1}), distribución {conteo}"
    assert all(v > 0 for v in conteo.values()), f"{arquetipo_id}: alguna plantilla nunca se eligió: {conteo}"


# --------------------------------------------------------------------------------------------
# Arquetipo 7 — rangos de concentración por intensidad.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_dependencia_clientes_respeta_los_rangos_por_intensidad(catalogo, arquetipos, sector):
    for intensidad in ("leve", "moderado", "fuerte"):
        rango = RANGOS_CONCENTRACION_CLIENTES[intensidad]
        for semilla in SEMILLAS:
            ejercicio = _ejercicio(catalogo, arquetipos, sector, intensidad, semilla)
            nota = generar_nota_dependencia_clientes(sector, "grandes_medianas", intensidad, semilla, ejercicio)
            n_clientes = int(re.search(r"(\d+) (?:principales clientes|clientes)", nota.texto).group(1))
            pct = int(re.search(r"(\d+)%", nota.texto).group(1))
            assert rango["clientes"][0] <= n_clientes <= rango["clientes"][1]
            assert rango["pct"][0] <= pct <= rango["pct"][1]
    assert nota.etiquetas == ("clientes", "concentracion")


# --------------------------------------------------------------------------------------------
# Arquetipos 20 y 21 — cotas de plausibilidad del importe citado (techo Y suelo).
# --------------------------------------------------------------------------------------------


def test_operaciones_vinculadas_importe_dentro_de_cotas_de_plausibilidad(catalogo, arquetipos):
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    fuera_de_cota = []
    for codigo in codigos:
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                ejercicio = _ejercicio(catalogo, arquetipos, codigo, intensidad, semilla)
                nota = generar_nota_operaciones_vinculadas(codigo, "grandes_medianas", intensidad, semilla, ejercicio)
                importe = float(re.search(r"([\d\.]+) euros", nota.texto).group(1).replace(".", ""))
                activo_total = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
                if importe < SUELO_IMPORTE_VINCULADAS_EUR - 1 or importe > activo_total:
                    fuera_de_cota.append((codigo, intensidad, semilla, importe, activo_total))
    assert not fuera_de_cota, f"{len(fuera_de_cota)} casos fuera de cota: {fuera_de_cota[:10]}"


def test_coberturas_nocional_dentro_de_cotas_de_plausibilidad(catalogo, arquetipos):
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    fuera_de_cota = []
    for codigo in codigos:
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                ejercicio = _ejercicio(catalogo, arquetipos, codigo, intensidad, semilla)
                nota = generar_nota_coberturas(codigo, "grandes_medianas", intensidad, semilla, ejercicio)
                importe = float(re.search(r"([\d\.]+) euros", nota.texto).group(1).replace(".", ""))
                activo_total = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
                if importe < SUELO_NOCIONAL_COBERTURA_EUR - 1 or importe > activo_total:
                    fuera_de_cota.append((codigo, intensidad, semilla, importe, activo_total))
    assert not fuera_de_cota, f"{len(fuera_de_cota)} casos fuera de cota: {fuera_de_cota[:10]}"


# --------------------------------------------------------------------------------------------
# Etiquetado — consistente por arquetipo (fijo), salvo el 22 (temáticamente variado a propósito).
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sector", SECTORES)
def test_etiquetas_fijas_por_arquetipo(catalogo, arquetipos, sector):
    ejercicio = _ejercicio(catalogo, arquetipos, sector, "fuerte", 0)
    assert generar_nota_activo_mantenido_venta(sector, "grandes_medianas", "fuerte", 0, ejercicio).etiquetas == (
        "activo", "desinversion",
    )
    assert generar_nota_operaciones_vinculadas(sector, "grandes_medianas", "fuerte", 0, ejercicio).etiquetas == (
        "vinculadas", "partes_relacionadas",
    )
    assert generar_nota_coberturas(sector, "grandes_medianas", "fuerte", 0, ejercicio).etiquetas == (
        "deuda", "cobertura_riesgo",
    )


def test_arquetipo_22_tiene_etiquetas_distintas_entre_temas(catalogo, arquetipos):
    ejercicio = _ejercicio(catalogo, arquetipos, "24.1", "fuerte", 0)
    etiquetas_vistas = set()
    for semilla in range(20):
        nota = generar_nota_informacion_relevante("24.1", "grandes_medianas", "fuerte", semilla, ejercicio)
        etiquetas_vistas.add(nota.etiquetas)
    assert len(etiquetas_vistas) > 1, "el arquetipo 22 debería mostrar temas (etiquetas) distintos entre sí"


# --------------------------------------------------------------------------------------------
# Despachador.
# --------------------------------------------------------------------------------------------


def test_despachador_generar_nota_memoria_pura_cubre_los_5_arquetipos(catalogo, arquetipos):
    ejercicio = _ejercicio(catalogo, arquetipos, "24.1", "fuerte", 0)
    for arquetipo_id in PREFIJOS:
        nota = generar_nota_memoria_pura(arquetipo_id, "24.1", "grandes_medianas", "fuerte", 0, ejercicio)
        assert nota.arquetipo_id == arquetipo_id


def test_despachador_lanza_key_error_para_id_desconocido(catalogo, arquetipos):
    ejercicio = _ejercicio(catalogo, arquetipos, "24.1", "fuerte", 0)
    with pytest.raises(KeyError):
        generar_nota_memoria_pura("no_existe", "24.1", "grandes_medianas", "fuerte", 0, ejercicio)
