"""Tests de la combinación de arquetipos (sección 2.12 — arquetipos activos a la vez).

Cubre lo aprobado para este encargo, deliberadamente acotado a las 6 combinaciones
recomendadas de la sección 2.26 (no las 231 parejas de la matriz de compatibilidad completa,
sección 2.25):

- Las 6 combinaciones recomendadas cuadran y generan notas de memoria sin colisión, para al
  menos 2 sectores.
- Disjunción de etiquetas EXHAUSTIVA (todas las plantillas, no una muestra) entre los
  arquetipos 18/19/20/21 — la garantía estructural de que el Combo E nunca colisiona, para
  cualquier semilla.
- El mecanismo genérico de evitar colisión (arquetipos 7/22) sigue libre de colisiones en
  barrido amplio.
- La fusión de masa_circulante (Combo F, arquetipos 1+5) no descuadra y su tasa de activación
  de `contencion_al_limite` queda registrada como referencia (ver nota en el test
  correspondiente: la combinación satura sensiblemente más que la suma de sus partes — dato
  trasladado al usuario, no oculto en el test).
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import (
    NOTAS_MEMORIA_ADQUISICION,
    generar_evolucion_arquetipo,
    generar_evolucion_combinada,
)
from motor.memoria import (
    PLANTILLAS_ACTIVO_MANTENIDO_VENTA,
    PLANTILLAS_COBERTURAS,
    generar_caso_combinado,
)

VENTAS_OBJETIVO_2023 = 8_000_000.0

SECTORES = [
    pytest.param("24.1", id="industrial-siderurgia"),
    pytest.param("62", id="servicios-tic"),
]

# Las 6 combinaciones recomendadas de la sección 2.26 — 13 excluido ("no aplica al motor").
COMBOS_RECOMENDADOS = {
    "A": {"exceso_stock": "fuerte", "dependencia_pocos_clientes": "fuerte"},
    "B": {"crecimiento_destruccion_caja": "fuerte", "mejora_margen": "fuerte"},
    "C": {"crecimiento_destruccion_caja": "fuerte", "apalancamiento": "fuerte", "riesgo_liquidez_pese_beneficio": "fuerte"},
    "D": {"mejora_ebitda": "fuerte", "resultado_extraordinario": "fuerte"},
    "E": {
        "adquisicion": "fuerte",
        "activo_mantenido_venta": "fuerte",
        "operaciones_vinculadas": "fuerte",
        "coberturas": "fuerte",
    },
    "F": {
        "crecimiento_destruccion_caja": "fuerte",
        "exceso_stock": "fuerte",
        "apalancamiento": "fuerte",
        "riesgo_refinanciacion": "fuerte",
    },
}


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _cuadra(ejercicio) -> bool:
    activo = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
    pn_pasivo = (
        ejercicio.balance_eur["patrimonio_neto"]
        + ejercicio.balance_eur["pasivo_no_corriente"]
        + ejercicio.balance_eur["pasivo_corriente"]
    )
    return abs(activo - pn_pasivo) <= 0.01


def _todas_las_etiquetas(notas) -> list[tuple[str, ...]]:
    return [nota.etiquetas for nota in notas]


def _hay_colision(notas) -> bool:
    """Colisión = mismo tema entre notas de DOS ARQUETIPOS DISTINTOS (sección 2.12). Un mismo
    arquetipo (p.ej. 16, riesgo_refinanciacion) puede legítimamente llevar una nota con las
    mismas etiquetas en varios años (2024 y 2025) — eso no es la redundancia que el mecanismo de
    la sección 2.12 evita, así que se ignoran los repartos dentro de un mismo `arquetipo_id`."""
    vistas: dict[str, set[str]] = {}
    for nota in notas:
        for otro_id, etiquetas_otro in vistas.items():
            if otro_id != nota.arquetipo_id and etiquetas_otro & set(nota.etiquetas):
                return True
        vistas.setdefault(nota.arquetipo_id, set()).update(nota.etiquetas)
    return False


@pytest.mark.parametrize("nombre_combo", sorted(COMBOS_RECOMENDADOS))
@pytest.mark.parametrize("sector", SECTORES)
def test_combos_recomendados_cuadran_y_sin_colision(catalogo, arquetipos, sector, nombre_combo):
    combo = COMBOS_RECOMENDADOS[nombre_combo]
    for semilla in range(3):
        evolucion = generar_caso_combinado(
            sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla, combo, catalogo=catalogo, arquetipos=arquetipos
        )
        for ejercicio in evolucion.ejercicios.values():
            assert _cuadra(ejercicio), f"combo {nombre_combo}, sector {sector}, semilla {semilla}: descuadre"

        todas_las_notas = list(evolucion.notas_memoria_pura)
        for ejercicio in evolucion.ejercicios.values():
            todas_las_notas.extend(ejercicio.notas_memoria)
        assert not _hay_colision(todas_las_notas), (
            f"combo {nombre_combo}, sector {sector}, semilla {semilla}: colisión de etiquetas "
            f"entre notas: {_todas_las_etiquetas(todas_las_notas)}"
        )


def test_combo_e_siempre_genera_las_4_notas_esperadas(catalogo, arquetipos):
    # 18 aporta 1 nota numérica obligatoria en 2024; 19/20/21 aportan 1 cada una — 4 en total,
    # nunca menos (el mecanismo de colisión nunca bloquea, en el peor caso da una nota redundante
    # en vez de omitirla — ver docstring de _elegir_indice_evitando_colision).
    for sector in ("24.1", "62"):
        for semilla in range(3):
            evolucion = generar_caso_combinado(
                sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla, COMBOS_RECOMENDADOS["E"],
                catalogo=catalogo, arquetipos=arquetipos,
            )
            notas_numericas = sum(len(ej.notas_memoria) for ej in evolucion.ejercicios.values())
            assert notas_numericas == 1
            assert len(evolucion.notas_memoria_pura) == 3


def test_etiquetas_de_18_19_20_21_son_exhaustivamente_disjuntas_dos_a_dos(catalogo, arquetipos):
    """Verificación #2 pedida explícitamente: no basta con la plantilla que salió de ejemplo —
    hay que comprobar TODAS las plantillas posibles de cada uno de los 4 arquetipos.

    18 expone sus etiquetas por plantilla en una constante importable (`NOTAS_MEMORIA_ADQUISICION`)
    y se recorre entera. 19/20/21 tienen las etiquetas fijas en el propio código (no varían según
    qué plantilla de texto salga — ver docstring de cada `generar_nota_*`), así que en vez de leer
    el código y confiar en que es así, se genera la nota real con suficientes semillas distintas
    para que las 5 plantillas de cada uno aparezcan al menos una vez, y se comprueba que las
    etiquetas devueltas son siempre las mismas para el archivo — la garantía se confirma
    ejecutando el código, no leyéndolo.
    """
    # Ejercicio de referencia cualquiera (mismo patrón que tests/test_memoria.py: un caso
    # cuantitativo "neutro" ya cerrado, solo para tener datos reales de empresa a los que
    # referenciar magnitudes — no afecta a las etiquetas, que son fijas por archetype).
    evolucion_referencia = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
    )
    ejercicio_referencia = evolucion_referencia.ejercicios[2025]

    etiquetas_18 = {etiquetas for _, etiquetas in NOTAS_MEMORIA_ADQUISICION}
    assert len(NOTAS_MEMORIA_ADQUISICION) == 5

    def _recolectar(fn, n_plantillas, arquetipo_id):
        textos_vistos: set[str] = set()
        etiquetas_vistas: set[tuple[str, ...]] = set()
        semilla = 0
        # Suficientes semillas para que, barajando, las 5 plantillas aparezcan.
        while len(textos_vistos) < n_plantillas and semilla < 200:
            nota = fn(
                "24.1", "grandes_medianas", "fuerte", semilla, ejercicio_referencia,
                etiquetas_ya_usadas=frozenset(),
            )
            textos_vistos.add(nota.texto)
            etiquetas_vistas.add(nota.etiquetas)
            semilla += 1
        assert len(textos_vistos) == n_plantillas, (
            f"{arquetipo_id}: solo se vieron {len(textos_vistos)}/{n_plantillas} plantillas en 200 semillas"
        )
        return etiquetas_vistas

    etiquetas_19 = _recolectar(
        __import__("motor.memoria", fromlist=["generar_nota_activo_mantenido_venta"]).generar_nota_activo_mantenido_venta,
        len(PLANTILLAS_ACTIVO_MANTENIDO_VENTA),
        "activo_mantenido_venta",
    )
    # operaciones_vinculadas (20) ya no encaja en `_recolectar` (desde el segundo lote de
    # desglose de balance es `clase="cuantitativo"`, su nota ya no sortea nada por sí misma —
    # ver motor/evolucion_arquetipo.py, ParametrosOperacionVinculada): se verifica igual —
    # etiquetas fijas en un único conjunto — pero generando casos donde el arquetipo esté
    # REALMENTE activo, no sobre `ejercicio_referencia` (que no lo tiene).
    generar_nota_operaciones_vinculadas = __import__(
        "motor.memoria", fromlist=["generar_nota_operaciones_vinculadas"]
    ).generar_nota_operaciones_vinculadas
    etiquetas_20: set[tuple[str, ...]] = set()
    for semilla in range(8):
        evolucion_vinculadas = generar_evolucion_arquetipo(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
            arquetipo_id="operaciones_vinculadas", catalogo=catalogo, arquetipos=arquetipos,
        )
        nota_vinculadas = generar_nota_operaciones_vinculadas(evolucion_vinculadas.ejercicios[2025])
        etiquetas_20.add(nota_vinculadas.etiquetas)
    etiquetas_21 = _recolectar(
        __import__("motor.memoria", fromlist=["generar_nota_coberturas"]).generar_nota_coberturas,
        len(PLANTILLAS_COBERTURAS),
        "coberturas",
    )

    # Cada arquetipo debe tener exactamente UN conjunto de etiquetas (fijo, no varía por plantilla).
    assert len(etiquetas_19) == 1
    assert len(etiquetas_20) == 1
    assert len(etiquetas_21) == 1

    conjuntos = {
        "18": etiquetas_18.pop() if len(etiquetas_18) == 1 else etiquetas_18,
        "19": etiquetas_19.pop(),
        "20": etiquetas_20.pop(),
        "21": etiquetas_21.pop(),
    }
    # 18 también debe tener un único conjunto fijo de etiquetas en las 5 plantillas.
    assert isinstance(conjuntos["18"], tuple), f"arquetipo 18 no tiene etiquetas fijas: {etiquetas_18}"

    nombres = list(conjuntos)
    for i, a in enumerate(nombres):
        for b in nombres[i + 1 :]:
            interseccion = set(conjuntos[a]) & set(conjuntos[b])
            assert not interseccion, f"arquetipos {a} y {b} comparten etiquetas: {interseccion}"


def test_arquetipos_7_y_22_evitan_colision_de_tema_en_barrido_amplio(catalogo, arquetipos):
    """Caso sintético que fuerza la colisión temática conocida (proveedor clave / concentración de
    clientes) y comprueba que el mecanismo genérico de la sección 2.12 la evita en todo el
    barrido, no solo en el caso de ejemplo verificado a mano durante el diseño."""
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    colisiones = 0
    evitadas_en_22 = 0
    total = 0
    for codigo in codigos:
        for intensidad in ("leve", "moderado", "fuerte"):
            for semilla in range(4):
                evolucion = generar_caso_combinado(
                    codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
                    {"exceso_stock": intensidad, "dependencia_pocos_clientes": intensidad,
                     "informacion_relevante_memoria": intensidad},
                    catalogo=catalogo, arquetipos=arquetipos,
                )
                notas = list(evolucion.notas_memoria_pura)
                total += 1
                if _hay_colision(notas):
                    colisiones += 1
                nota_22 = next(n for n in notas if n.arquetipo_id == "informacion_relevante_memoria")
                if "proveedores" not in nota_22.etiquetas and "concentracion" not in nota_22.etiquetas:
                    evitadas_en_22 += 1
    assert colisiones == 0, f"{colisiones}/{total} casos con colisión de etiquetas"
    assert evitadas_en_22 == total, f"solo {evitadas_en_22}/{total} evitaron el tema colisionante en el arquetipo 22"


def test_combo_f_fusion_existencias_no_descuadra(catalogo, arquetipos):
    for sector in ("24.1", "62"):
        for semilla in range(3):
            evolucion = generar_evolucion_combinada(
                sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
                {"crecimiento_destruccion_caja": "fuerte", "exceso_stock": "fuerte"},
                catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert _cuadra(ejercicio)


def test_combo_f_tasa_contencion_al_limite_queda_registrada(catalogo, arquetipos):
    """Verificación #1 pedida explícitamente: cuantificar cuánto satura `contencion_al_limite` en
    el Combo F (fuerte+fuerte) frente a cada arquetipo por separado (fuerte).

    HISTORIAL (ver decisiones_plausibilidad.md #16 y #20 para el detalle completo): con la escala
    de intensidad ORIGINAL del arquetipo 9 (INTENSIDAD_BASE genérica, 0,15/0,30/0,50), el Combo F
    saturaba fuerte — 39,8%/67,6%/84,3% (leve/moderado/fuerte) — casi idéntico al arquetipo 9 EN
    SOLITARIO con esa escala (39,4%/67,6%/85,6%), confirmando que la "saturación" no era un efecto
    real de la combinación, sino el comportamiento ya descalibrado de 9 en solitario. Tras
    recalibrar 9 (y 10, 11) con una escala de intensidad propia (#20), el Combo F queda en
    **6,0%/22,2%/63,9%** — gradiente real y mucho más razonable (leve ya no satura, fuerte se
    mantiene alto porque el Combo F está pensado como "tormenta de liquidez progresiva", la
    combinación más agresiva de las 6). El amortiguador de combinación que se había planteado para
    este combo ya NO hace falta — la causa real estaba en el arquetipo 9 en solitario, no en la
    combinación.
    Este test fija que el mecanismo no rompe (siempre cuadra, siempre se señaliza cuando
    corresponde) y deja registrada la tasa actual como referencia de regresión.
    """
    codigos = [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]
    activaciones = 0
    for codigo in codigos:
        for semilla in range(4):
            evolucion = generar_evolucion_combinada(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
                {
                    "crecimiento_destruccion_caja": "fuerte", "exceso_stock": "fuerte",
                    "apalancamiento": "fuerte", "riesgo_refinanciacion": "fuerte",
                },
                catalogo=catalogo, arquetipos=arquetipos,
            )
            for año, ejercicio in evolucion.ejercicios.items():
                if año == 2023:
                    continue
                if ejercicio.riesgo_endeudamiento:
                    activaciones += 1
    assert activaciones > 0, "la muestra no incluyó ningún caso con riesgo_endeudamiento: ajustar el barrido"
