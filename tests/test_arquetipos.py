import json

import pytest

from motor.arquetipos import (
    ArquetipoInvalidoError,
    EfectoApalancamiento,
    EfectoCapex,
    EfectoEventoPuntual,
    EfectoMasaCirculante,
    EfectoPygPrimitiva,
    EfectoReclasificacionDeuda,
    EfectoTesoreria,
    RUTA_ARQUETIPOS_POR_DEFECTO,
    cargar_arquetipos,
)

IDS_ESPERADOS = {
    "crecimiento_destruccion_caja": 1,
    "exceso_stock": 5,
    "apalancamiento": 9,
    "mejora_margen": 11,
    "riesgo_liquidez_pese_beneficio": 15,
    "aumento_nof": 3,
    "deterioro_ciclo_caja": 4,
    "aumento_clientes": 6,
    "refinanciacion": 8,
    "mejora_ebitda": 10,
    "beneficio_sin_cash_flow": 2,
    "resultado_extraordinario": 12,
    "roe_elevado_apalancamiento": 14,
    "riesgo_refinanciacion": 16,
    "capex_elevado": 17,
}


def test_carga_los_15_arquetipos_implementados():
    arquetipos = cargar_arquetipos()
    assert set(arquetipos) == set(IDS_ESPERADOS)
    for id_, numero in IDS_ESPERADOS.items():
        assert arquetipos[id_].numero == numero
        assert len(arquetipos[id_].efectos) >= 1


def test_tipos_de_efecto_del_tercer_lote():
    arquetipos = cargar_arquetipos()
    assert all(isinstance(e, EfectoTesoreria) for e in arquetipos["beneficio_sin_cash_flow"].efectos)
    assert all(isinstance(e, EfectoEventoPuntual) for e in arquetipos["resultado_extraordinario"].efectos)
    assert all(isinstance(e, EfectoApalancamiento) for e in arquetipos["roe_elevado_apalancamiento"].efectos)
    assert all(isinstance(e, EfectoReclasificacionDeuda) for e in arquetipos["riesgo_refinanciacion"].efectos)
    assert all(isinstance(e, EfectoCapex) for e in arquetipos["capex_elevado"].efectos)


def test_riesgo_refinanciacion_direccion_es_opuesta_a_refinanciacion():
    arquetipos = cargar_arquetipos()
    assert arquetipos["refinanciacion"].efectos[0].direccion == 1
    assert arquetipos["riesgo_refinanciacion"].efectos[0].direccion == -1


def test_tipos_de_efecto_del_segundo_lote():
    arquetipos = cargar_arquetipos()
    assert all(isinstance(e, EfectoMasaCirculante) for e in arquetipos["aumento_nof"].efectos)
    assert all(isinstance(e, EfectoMasaCirculante) for e in arquetipos["deterioro_ciclo_caja"].efectos)
    assert all(isinstance(e, EfectoMasaCirculante) for e in arquetipos["aumento_clientes"].efectos)
    assert all(isinstance(e, EfectoPygPrimitiva) for e in arquetipos["mejora_ebitda"].efectos)
    assert all(isinstance(e, EfectoReclasificacionDeuda) for e in arquetipos["refinanciacion"].efectos)


def test_deterioro_ciclo_caja_toca_realizable_y_acreedores_con_signos_opuestos():
    arquetipos = cargar_arquetipos()
    efectos = {e.variable: e.direccion for e in arquetipos["deterioro_ciclo_caja"].efectos}
    assert efectos["realizable"] == 1
    assert efectos["acreedores_comerciales"] == -1


def test_tipos_de_efecto_son_los_esperados():
    arquetipos = cargar_arquetipos()
    assert all(isinstance(e, EfectoMasaCirculante) for e in arquetipos["crecimiento_destruccion_caja"].efectos)
    assert all(isinstance(e, EfectoMasaCirculante) for e in arquetipos["exceso_stock"].efectos)
    assert all(isinstance(e, EfectoPygPrimitiva) for e in arquetipos["mejora_margen"].efectos)
    assert all(isinstance(e, EfectoApalancamiento) for e in arquetipos["apalancamiento"].efectos)
    assert all(isinstance(e, EfectoTesoreria) for e in arquetipos["riesgo_liquidez_pese_beneficio"].efectos)


def test_direcciones_coinciden_con_la_seccion_2_24():
    arquetipos = cargar_arquetipos()
    # Arquetipo 1: rotación de existencias baja (-1), plazo de cobro sube (+1).
    efectos_1 = {e.variable: e.direccion for e in arquetipos["crecimiento_destruccion_caja"].efectos}
    assert efectos_1["existencias"] == -1
    assert efectos_1["realizable"] == 1
    # Arquetipo 5: rotación de existencias baja (-1).
    assert arquetipos["exceso_stock"].efectos[0].direccion == -1
    # Arquetipo 11: consumos_explotacion_pct baja (-1) = mejora el margen.
    assert arquetipos["mejora_margen"].efectos[0].direccion == -1
    # Arquetipo 9: endeudamiento sube (+1).
    assert arquetipos["apalancamiento"].efectos[0].direccion == 1
    # Arquetipo 15: tesorería baja (-1).
    assert arquetipos["riesgo_liquidez_pese_beneficio"].efectos[0].direccion == -1


def test_solo_arquetipo_1_define_rango_crecimiento_pleno():
    arquetipos = cargar_arquetipos()
    assert arquetipos["crecimiento_destruccion_caja"].rango_crecimiento_pleno is not None
    for id_ in ("exceso_stock", "apalancamiento", "mejora_margen", "riesgo_liquidez_pese_beneficio"):
        assert arquetipos[id_].rango_crecimiento_pleno is None


def test_ruta_inexistente_lanza_error():
    with pytest.raises(FileNotFoundError):
        cargar_arquetipos("data/no_existe.json")


def test_tipo_de_efecto_no_reconocido(tmp_path):
    archivo = tmp_path / "arquetipos.json"
    archivo.write_text(
        json.dumps({"arquetipos": [{"id": "x", "efectos": [{"tipo": "no_existe", "direccion": 1, "ratio_catalogo": "a"}]}]}),
        encoding="utf-8",
    )
    with pytest.raises(ArquetipoInvalidoError, match="no reconocido"):
        cargar_arquetipos(archivo)


def test_arquetipo_sin_efectos_lanza_error(tmp_path):
    archivo = tmp_path / "arquetipos.json"
    archivo.write_text(json.dumps({"arquetipos": [{"id": "x", "efectos": []}]}), encoding="utf-8")
    with pytest.raises(ArquetipoInvalidoError, match="no tiene ningún efecto"):
        cargar_arquetipos(archivo)


def test_arquetipo_duplicado_lanza_error(tmp_path):
    archivo = tmp_path / "arquetipos.json"
    efecto = {"tipo": "apalancamiento", "direccion": 1, "ratio_catalogo": "ratios.endeudamiento"}
    archivo.write_text(
        json.dumps({"arquetipos": [{"id": "x", "efectos": [efecto]}, {"id": "x", "efectos": [efecto]}]}),
        encoding="utf-8",
    )
    with pytest.raises(ArquetipoInvalidoError, match="duplicado"):
        cargar_arquetipos(archivo)


def test_direccion_invalida_lanza_error(tmp_path):
    archivo = tmp_path / "arquetipos.json"
    archivo.write_text(
        json.dumps({"arquetipos": [{"id": "x", "efectos": [{"tipo": "apalancamiento", "direccion": 2, "ratio_catalogo": "a"}]}]}),
        encoding="utf-8",
    )
    with pytest.raises(ArquetipoInvalidoError, match="direccion"):
        cargar_arquetipos(archivo)


def test_archivo_por_defecto_existe():
    assert RUTA_ARQUETIPOS_POR_DEFECTO.exists()
