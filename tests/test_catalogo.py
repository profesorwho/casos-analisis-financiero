import pandas as pd
import pytest

from motor.catalogo import (
    NUM_FILAS_ESPERADAS,
    NUM_SECTORES_ESPERADOS,
    RUTA_CATALOGO_POR_DEFECTO,
    CatalogoInvalidoError,
    cargar_catalogo,
    validar_catalogo,
)


def _catalogo_minimo_valido() -> pd.DataFrame:
    filas = []
    for i in range(NUM_SECTORES_ESPERADOS):
        for segmento in ("grandes_medianas", "pequeñas"):
            filas.append({"sector": f"Sector {i}", "segmento": segmento, "ratio.roa.huber_9y": 0.05})
    return pd.DataFrame(filas)


def test_catalogo_real_carga_y_valida():
    df = cargar_catalogo(RUTA_CATALOGO_POR_DEFECTO)
    validar_catalogo(df)
    assert len(df) == NUM_FILAS_ESPERADAS
    assert df["sector"].nunique() == NUM_SECTORES_ESPERADOS


def test_catalogo_minimo_valido_no_lanza_error():
    validar_catalogo(_catalogo_minimo_valido())


def test_detecta_numero_de_filas_incorrecto():
    df = _catalogo_minimo_valido().iloc[:-1]
    with pytest.raises(CatalogoInvalidoError, match="filas"):
        validar_catalogo(df)


def test_detecta_segmento_no_reconocido():
    df = _catalogo_minimo_valido()
    df.loc[0, "segmento"] = "mediana_grande"
    with pytest.raises(CatalogoInvalidoError, match="Segmentos no reconocidos"):
        validar_catalogo(df)


def test_detecta_combinacion_duplicada_y_faltante():
    df = _catalogo_minimo_valido()
    df.loc[1, "segmento"] = df.loc[0, "segmento"]
    with pytest.raises(CatalogoInvalidoError, match="duplicadas"):
        validar_catalogo(df)


def test_detecta_valor_no_numerico():
    df = _catalogo_minimo_valido()
    df["ratio.roa.huber_9y"] = df["ratio.roa.huber_9y"].astype(object)
    df.loc[0, "ratio.roa.huber_9y"] = "no_disponible"
    with pytest.raises(CatalogoInvalidoError, match="no numéricos"):
        validar_catalogo(df)


def test_cargar_catalogo_ruta_inexistente():
    with pytest.raises(FileNotFoundError):
        cargar_catalogo("data/no_existe.csv")
