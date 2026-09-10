"""Carga y validación del catálogo de ratios sectoriales (Fase 1 de la especificación).

No genera empresas ni valida cuadre contable: solo garantiza que el catálogo de
referencia (27 sectores x 2 segmentos, estimador de Huber a 9 años) es utilizable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

RUTA_CATALOGO_POR_DEFECTO = (
    Path(__file__).resolve().parent.parent / "data" / "catalogo_ratios_masas_27sectores_huber9y.csv"
)

COLUMNAS_ID = ("sector", "segmento")
SEGMENTOS_ESPERADOS = frozenset({"grandes_medianas", "pequeñas"})
NUM_SECTORES_ESPERADOS = 27
NUM_FILAS_ESPERADAS = NUM_SECTORES_ESPERADOS * len(SEGMENTOS_ESPERADOS)


class CatalogoInvalidoError(ValueError):
    """El catálogo no cumple la estructura o integridad esperadas."""


def version_catalogo(ruta: str | Path = RUTA_CATALOGO_POR_DEFECTO) -> str:
    """Identificador corto (SHA-256, 12 caracteres) del contenido del CSV del catálogo.

    Se deriva del propio archivo, no de un número de versión mantenido a mano, para que no
    se pueda desincronizar si el catálogo cambia sin actualizar ese número (trazabilidad de
    cada caso generado, sección 2.15 de la especificación).
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el catálogo de ratios en: {ruta}")
    return hashlib.sha256(ruta.read_bytes()).hexdigest()[:12]


def cargar_catalogo(ruta: str | Path = RUTA_CATALOGO_POR_DEFECTO) -> pd.DataFrame:
    """Lee el CSV del catálogo de ratios sectoriales.

    Adjunta la versión del catálogo (ver `version_catalogo`) en `df.attrs["catalogo_version"]`,
    para que viaje junto con el DataFrame sin tener que volver a tocar el archivo.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el catálogo de ratios en: {ruta}")
    df = pd.read_csv(ruta, encoding="utf-8-sig")
    df.attrs["catalogo_version"] = version_catalogo(ruta)
    return df


def validar_catalogo(df: pd.DataFrame) -> None:
    """Valida estructura (27 sectores x 2 segmentos) e integridad numérica del catálogo.

    Recoge todos los problemas encontrados antes de lanzar la excepción, para que un
    catálogo con varios defectos se pueda corregir en una sola pasada.
    """
    errores: list[str] = []

    columnas_faltantes = [c for c in COLUMNAS_ID if c not in df.columns]
    if columnas_faltantes:
        raise CatalogoInvalidoError(f"Faltan columnas obligatorias: {columnas_faltantes}")

    if len(df) != NUM_FILAS_ESPERADAS:
        errores.append(
            f"Se esperaban {NUM_FILAS_ESPERADAS} filas ({NUM_SECTORES_ESPERADOS} sectores x "
            f"{len(SEGMENTOS_ESPERADOS)} segmentos) y hay {len(df)}."
        )

    sectores = df["sector"].dropna().unique()
    if len(sectores) != NUM_SECTORES_ESPERADOS:
        errores.append(f"Se esperaban {NUM_SECTORES_ESPERADOS} sectores distintos y hay {len(sectores)}.")

    segmentos = set(df["segmento"].dropna().unique())
    segmentos_inesperados = segmentos - SEGMENTOS_ESPERADOS
    if segmentos_inesperados:
        errores.append(f"Segmentos no reconocidos en el catálogo: {sorted(segmentos_inesperados)}")

    combinaciones = df.groupby(["sector", "segmento"]).size()
    combinaciones_duplicadas = combinaciones[combinaciones > 1]
    if not combinaciones_duplicadas.empty:
        errores.append(f"Combinaciones sector/segmento duplicadas: {list(combinaciones_duplicadas.index)}")

    combinaciones_esperadas = {(s, seg) for s in sectores for seg in SEGMENTOS_ESPERADOS}
    combinaciones_presentes = set(combinaciones.index)
    combinaciones_faltantes = combinaciones_esperadas - combinaciones_presentes
    if combinaciones_faltantes:
        errores.append(f"Faltan combinaciones sector/segmento: {sorted(combinaciones_faltantes)}")

    columnas_datos = [c for c in df.columns if c not in COLUMNAS_ID]
    for columna in columnas_datos:
        valores_no_numericos = pd.to_numeric(df[columna], errors="coerce").isna() & df[columna].notna()
        if valores_no_numericos.any():
            filas = df.index[valores_no_numericos].tolist()
            errores.append(f"Valores no numéricos en '{columna}', filas: {filas}")

    columnas_n_anios = [c for c in columnas_datos if c.endswith(".n_años")]
    for columna in columnas_n_anios:
        n_anios = pd.to_numeric(df[columna], errors="coerce")
        fuera_de_rango = n_anios.notna() & ~n_anios.between(1, 9)
        if fuera_de_rango.any():
            filas = df.index[fuera_de_rango].tolist()
            errores.append(f"'{columna}' fuera del rango 1-9 años en filas: {filas}")

    if errores:
        raise CatalogoInvalidoError("Catálogo inválido:\n- " + "\n- ".join(errores))


def cargar_y_validar_catalogo(ruta: str | Path = RUTA_CATALOGO_POR_DEFECTO) -> pd.DataFrame:
    """Atajo: carga el catálogo y lo valida antes de devolverlo."""
    df = cargar_catalogo(ruta)
    validar_catalogo(df)
    return df


if __name__ == "__main__":
    catalogo = cargar_y_validar_catalogo()
    print(
        f"Catálogo válido: {len(catalogo)} filas, {catalogo['sector'].nunique()} sectores. "
        f"Versión: {catalogo.attrs['catalogo_version']}"
    )
