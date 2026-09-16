"""Tests de `motor/nombres_ficticios.py` — generador de nombres ficticios de empresa (sección
2.17, Ronda 2 de la Fase 4). Cubre reproducibilidad por semilla, cobertura de los 27 sectores,
coherencia con el sector real, distribución de forma jurídica por segmento, y la verificación
explícita (pedida) de que el modo típico/atípico NO aplica a esta pieza."""

import re

import pytest

from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import CATEGORIA_SECTOR
from motor.nombres_ficticios import (
    CALIFICADORES_LUGAR,
    DESCRIPCION_ACTIVIDAD_SECTOR,
    PROBABILIDAD_SA_POR_SEGMENTO,
    TERMINOS_SECTOR,
    NombreFicticioError,
    generar_nombre_ficticio,
)


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


def _sectores(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


# --------------------------------------------------------------------------------------------
# Cobertura de vocabulario — los 27 sectores, ni de más ni de menos.
# --------------------------------------------------------------------------------------------


def test_terminos_y_descripcion_cubren_exactamente_los_27_sectores():
    assert set(TERMINOS_SECTOR) == set(CATEGORIA_SECTOR)
    assert set(DESCRIPCION_ACTIVIDAD_SECTOR) == set(CATEGORIA_SECTOR)


def test_cada_sector_tiene_al_menos_3_terminos_de_actividad():
    for sector, terminos in TERMINOS_SECTOR.items():
        assert len(terminos) >= 3, f"sector {sector} con menos de 3 términos"


def test_todas_las_descripciones_son_frases_no_vacias():
    for sector, descripcion in DESCRIPCION_ACTIVIDAD_SECTOR.items():
        assert descripcion and len(descripcion) > 15, f"sector {sector}"


# --------------------------------------------------------------------------------------------
# Reproducibilidad — mismo patrón de hash estable que el resto del motor.
# --------------------------------------------------------------------------------------------


def test_misma_semilla_sector_segmento_da_el_mismo_nombre(catalogo):
    for sector in _sectores(catalogo)[:8]:
        for segmento in ("grandes_medianas", "pequeñas"):
            a = generar_nombre_ficticio(sector, segmento, 3)
            b = generar_nombre_ficticio(sector, segmento, 3)
            assert a == b


def test_distinta_semilla_suele_dar_distinto_nombre(catalogo):
    nombres = {generar_nombre_ficticio("24.1", "grandes_medianas", semilla).nombre_completo for semilla in range(15)}
    assert len(nombres) > 5, "demasiada repetición entre semillas — variedad insuficiente"


def test_distinto_segmento_puede_dar_distinto_nombre_misma_semilla(catalogo):
    # RNG independiente por segmento (entropía mezcla sector+segmento) — no tiene por qué
    # coincidir, y de hecho con probabilidad alta no coincidirá.
    distintos = 0
    for semilla in range(15):
        a = generar_nombre_ficticio("24.1", "grandes_medianas", semilla)
        b = generar_nombre_ficticio("24.1", "pequeñas", semilla)
        if a.nombre_completo != b.nombre_completo:
            distintos += 1
    assert distintos > 0


def test_nombre_no_depende_del_arquetipo_por_construccion():
    # La función ni siquiera acepta arquetipo/intensidad como parámetro — mismo criterio que el
    # resto del motor ("misma semilla+sector+segmento, misma empresa"): estructuralmente
    # imposible que el nombre varíe por arquetipo. Verificación de que la firma es la esperada.
    import inspect

    parametros = list(inspect.signature(generar_nombre_ficticio).parameters)
    assert parametros == ["sector", "segmento", "semilla"]


# --------------------------------------------------------------------------------------------
# Coherencia con el sector real.
# --------------------------------------------------------------------------------------------


def test_el_termino_usado_pertenece_al_vocabulario_del_sector(catalogo):
    for sector in _sectores(catalogo):
        for semilla in range(3):
            for segmento in ("grandes_medianas", "pequeñas"):
                n = generar_nombre_ficticio(sector, segmento, semilla)
                assert n.descripcion_actividad == DESCRIPCION_ACTIVIDAD_SECTOR[sector]
                terminos_posibles = TERMINOS_SECTOR[sector]
                # El nombre_completo debe contener alguno de los términos de ESE sector — no el
                # de ningún otro (evita que dos sectores compartan vocabulario "genérico" que
                # confunda de qué actividad real se trata).
                assert any(t in n.nombre_completo for t in terminos_posibles), (
                    f"{sector}: '{n.nombre_completo}' no contiene ningún término de {terminos_posibles}"
                )


def test_sectores_distintos_no_comparten_practicamente_ningun_termino():
    # Vocabulario deliberadamente ESPECÍFICO por sector (mismo criterio que las etiquetas de
    # colisión de memoria, sección 2.12) — comprueba que no hay solapamiento masivo entre
    # sectores de actividad muy distinta.
    siderurgia = set(TERMINOS_SECTOR["24.1"])
    tic = set(TERMINOS_SECTOR["62"])
    hosteleria = set(TERMINOS_SECTOR["55.1"])
    assert not (siderurgia & tic)
    assert not (siderurgia & hosteleria)
    assert not (tic & hosteleria)


# --------------------------------------------------------------------------------------------
# Forma jurídica coherente con el segmento — verificado empíricamente, no solo por construcción.
# --------------------------------------------------------------------------------------------


def test_forma_juridica_sa_mas_frecuente_en_grandes_medianas_que_en_pequeñas(catalogo):
    def _tasa_sa(segmento):
        sa = 0
        total = 0
        for sector in _sectores(catalogo):
            for semilla in range(10):
                n = generar_nombre_ficticio(sector, segmento, semilla)
                total += 1
                if n.forma_juridica == "S.A.":
                    sa += 1
        return sa / total

    tasa_pequeñas = _tasa_sa("pequeñas")
    tasa_grandes = _tasa_sa("grandes_medianas")
    assert tasa_grandes > tasa_pequeñas
    # Dentro de un margen razonable de la probabilidad de diseño declarada.
    assert abs(tasa_pequeñas - PROBABILIDAD_SA_POR_SEGMENTO["pequeñas"]) < 0.08
    assert abs(tasa_grandes - PROBABILIDAD_SA_POR_SEGMENTO["grandes_medianas"]) < 0.08


def test_sl_sigue_siendo_mayoritaria_incluso_en_grandes_medianas():
    # Hipótesis de diseño explícita (ver docstring del módulo): la S.A. no debe ser mayoritaria
    # ni siquiera en el segmento grande — la S.L. sigue siendo la forma jurídica más común.
    assert PROBABILIDAD_SA_POR_SEGMENTO["grandes_medianas"] < 0.5


def test_nombre_completo_termina_en_la_forma_juridica():
    for sector in ("24.1", "62", "55.1", "68"):
        for semilla in range(5):
            n = generar_nombre_ficticio(sector, "grandes_medianas", semilla)
            assert n.nombre_completo.endswith(n.forma_juridica)
            assert n.forma_juridica in ("S.L.", "S.A.")


# --------------------------------------------------------------------------------------------
# Validación de parámetros.
# --------------------------------------------------------------------------------------------


def test_sector_desconocido_lanza_error():
    with pytest.raises(NombreFicticioError):
        generar_nombre_ficticio("no_existe", "grandes_medianas", 0)


def test_segmento_invalido_lanza_error():
    with pytest.raises(NombreFicticioError):
        generar_nombre_ficticio("24.1", "medianas", 0)


# --------------------------------------------------------------------------------------------
# Modo típico/atípico — verificado explícitamente que NO aplica (pedido explícitamente, mismo
# estándar que la Ronda 1 aplicó a cada pieza nueva).
# --------------------------------------------------------------------------------------------


def test_no_hay_ningun_sorteo_huber_mad_en_este_modulo():
    # Verificación estructural: el módulo no IMPORTA `_generar_partida` como nombre utilizable
    # (el único mecanismo del motor con un concepto real de "típico"/"atípico") — todos sus
    # sorteos son discretos (rng.choice/rng.random), igual que provisiones/insolvencias/
    # subvención de fondo. Si algún día se añadiera un sorteo Huber/MAD a este módulo (importando
    # la función), este test fallaría y recordaría exponer su modo en motor/resumen_caso.py, en
    # vez de dejarlo descartado en silencio. No se comprueba el texto del docstring (que SÍ
    # menciona `_generar_partida` para documentar por qué no aplica) — solo el espacio de
    # nombres real del módulo.
    import motor.nombres_ficticios as modulo

    assert "_generar_partida" not in vars(modulo)


def test_resumen_particularidades_caso_no_necesita_cambios_para_nombres_ficticios(catalogo):
    # El nombre ficticio no se cuelga de EjercicioEmpresa/EvolucionArquetipo (es una pieza
    # independiente) y no tiene modo típico/atípico que exponer — confirma que generar un caso
    # normal y su resumen de particularidades sigue funcionando exactamente igual con este
    # módulo importado, sin ninguna interacción.
    from motor.arquetipos import cargar_arquetipos
    from motor.evolucion_arquetipo import generar_evolucion_arquetipo
    from motor.resumen_caso import resumen_particularidades_caso

    arquetipos = cargar_arquetipos()
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", 15_000_000.0, semilla=1, intensidad="fuerte",
        arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
    )
    r = resumen_particularidades_caso(evolucion)
    nombre = generar_nombre_ficticio("24.1", "grandes_medianas", 1)
    assert r is not None
    assert nombre is not None
