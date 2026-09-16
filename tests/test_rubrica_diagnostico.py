"""Tests de `motor/rubrica_diagnostico.py` — carga y validación de `data/rubrica_diagnostico.json`
(sección 2.19). Contenido estructurado, no código de generación: los tests comprueban la FORMA y
la consistencia interna de la rúbrica (secciones esperadas, puntos que cuadran, niveles
alcanzables), no ningún cálculo financiero."""

import json

import pytest

from motor.rubrica_diagnostico import (
    RUTA_RUBRICA_POR_DEFECTO,
    SECCIONES_ESPERADAS,
    RubricaInvalidaError,
    cargar_rubrica_diagnostico,
)


@pytest.fixture(scope="module")
def rubrica():
    return cargar_rubrica_diagnostico()


def test_carga_sin_errores_y_tiene_las_7_secciones(rubrica):
    assert len(rubrica.secciones) == 7
    assert {s.id for s in rubrica.secciones} == set(SECCIONES_ESPERADAS)


def test_secciones_en_orden_1_a_7(rubrica):
    assert [s.orden for s in rubrica.secciones] == list(range(1, 8))
    # Y el orden de la tupla ya devuelta coincide con el campo `orden` (sin necesidad de re-ordenar).
    assert [s.id for s in rubrica.secciones] == list(SECCIONES_ESPERADAS)


def test_la_suma_de_puntos_maximos_es_exactamente_la_puntuacion_total(rubrica):
    assert sum(s.puntos_maximos for s in rubrica.secciones) == pytest.approx(rubrica.puntuacion_total)
    assert rubrica.puntuacion_maxima_posible() == pytest.approx(rubrica.puntuacion_total)
    assert rubrica.puntuacion_total == pytest.approx(100.0)


def test_cada_seccion_tiene_al_menos_2_niveles_y_uno_alcanza_el_maximo(rubrica):
    for s in rubrica.secciones:
        assert len(s.niveles) >= 2
        nivel_maximo = next((n.nivel for n in s.niveles if n.fraccion_puntos == 1.0), None)
        assert nivel_maximo is not None
        assert s.puntos_de(nivel_maximo) == pytest.approx(s.puntos_maximos)


def test_cada_nivel_tiene_fraccion_en_0_1_y_descripcion_no_vacia(rubrica):
    for s in rubrica.secciones:
        for n in s.niveles:
            assert 0.0 <= n.fraccion_puntos <= 1.0
            assert n.descripcion and len(n.descripcion) > 10


def test_hipotesis_es_la_seccion_de_mayor_peso(rubrica):
    # Pedido explícitamente: la sección HIPÓTESIS es la que conecta con la "Conclusión esperada"
    # del arquetipo (capacidad de diagnóstico real) — debe pesar más que cualquier otra sección.
    hipotesis = rubrica.seccion("hipotesis")
    assert all(hipotesis.puntos_maximos >= s.puntos_maximos for s in rubrica.secciones if s.id != "hipotesis")


def test_seccion_desconocida_lanza_error(rubrica):
    with pytest.raises(RubricaInvalidaError):
        rubrica.seccion("no_existe")


def test_nivel_desconocido_lanza_error(rubrica):
    with pytest.raises(RubricaInvalidaError):
        rubrica.seccion("hecho").puntos_de("excelente")


def test_conexion_conclusion_esperada_remite_a_la_guia_docente(rubrica):
    conexion = rubrica.conexion_conclusion_esperada
    assert conexion.get("fuente") == "docs/guia_docente_arquetipos.md"
    assert conexion.get("campo_origen") == "Conclusión esperada"
    assert conexion.get("criterio")


def test_notas_de_aplicacion_no_vacias(rubrica):
    assert len(rubrica.notas_de_aplicacion) > 0
    assert all(isinstance(n, str) and n for n in rubrica.notas_de_aplicacion)


def test_ruta_por_defecto_apunta_al_json_real():
    assert RUTA_RUBRICA_POR_DEFECTO.name == "rubrica_diagnostico.json"
    assert RUTA_RUBRICA_POR_DEFECTO.exists()


def test_json_crudo_es_valido_y_carga_sin_transformar(rubrica):
    datos = json.loads(RUTA_RUBRICA_POR_DEFECTO.read_text(encoding="utf-8"))
    assert datos["puntuacion_total"] == rubrica.puntuacion_total
    assert len(datos["secciones"]) == len(rubrica.secciones)


def test_falta_una_seccion_lanza_error(tmp_path):
    datos = json.loads(RUTA_RUBRICA_POR_DEFECTO.read_text(encoding="utf-8"))
    datos["secciones"] = [s for s in datos["secciones"] if s["id"] != "prioridad"]
    ruta = tmp_path / "rubrica_incompleta.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(RubricaInvalidaError, match="prioridad"):
        cargar_rubrica_diagnostico(ruta)


def test_seccion_duplicada_lanza_error(tmp_path):
    datos = json.loads(RUTA_RUBRICA_POR_DEFECTO.read_text(encoding="utf-8"))
    datos["secciones"].append(datos["secciones"][0])
    ruta = tmp_path / "rubrica_duplicada.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(RubricaInvalidaError, match="duplicadas"):
        cargar_rubrica_diagnostico(ruta)


def test_puntos_maximos_que_no_cuadran_con_el_total_lanza_error(tmp_path):
    datos = json.loads(RUTA_RUBRICA_POR_DEFECTO.read_text(encoding="utf-8"))
    datos["secciones"][0]["puntos_maximos"] = 999
    ruta = tmp_path / "rubrica_descuadrada.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(RubricaInvalidaError, match="no coincide"):
        cargar_rubrica_diagnostico(ruta)


def test_ruta_inexistente_lanza_file_not_found_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        cargar_rubrica_diagnostico(tmp_path / "no_existe.json")
