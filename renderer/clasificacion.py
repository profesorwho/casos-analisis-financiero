"""Clasificación legal Normal/Abreviado de un caso — calculada aquí porque el motor la expone
(`motor.clasificacion_legal`) pero no la invoca desde ningún sitio (ver especificaciones,
tarea 82). Usa el par de años más reciente (2024-2025), igual que haría una empresa real."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.clasificacion_legal import (
    clasificar_ejercicio,
    clasificar_par_ejercicios,
    estimar_plantilla,
    estimar_ventas_por_empleado,
)


def clasificar_caso(evolucion, sector: str, segmento: str, catalogo) -> str:
    """Devuelve 'normal' o 'abreviado' para el caso, usando el par 2024-2025."""
    resultados = {}
    for año in (2024, 2025):
        ej = evolucion.ejercicios[año]
        v_emp, _ = estimar_ventas_por_empleado(sector, segmento, 1, catalogo)
        plantilla = estimar_plantilla(ej.ventas, v_emp)
        activo_total = ej.balance_eur["activo_no_corriente"] + ej.balance_eur["activo_corriente"]
        resultados[año] = clasificar_ejercicio(año, activo_total, ej.ventas, plantilla)
    return clasificar_par_ejercicios(resultados[2024], resultados[2025])
