"""Invariante de coherencia interna del renderizador — encargo #106, endurecido en #110.

En el Balance y la PyG generados por `mapear_balance_activo`/`mapear_balance_pn_pasivo`/
`mapear_pyg`, la suma de las líneas de detalle (nivel N+1) debe igualar el subtotal de su línea
padre (nivel N, en negrita) — para cualquier bloque que el renderizador presente como una
descomposición real. La PyG NO se comprueba con el mismo criterio genérico en sus líneas
"RESULTADO..." (nivel 0/1): son subtotales EN CASCADA de las líneas oficiales 1-20 que las
preceden, no un padre cuyos "hijos" sean las líneas de nivel inferior que le siguen
inmediatamente — solo se comprueban ahí las descomposiciones reales (1→a/b, 4→a-d, 6→a-c, 7→a-e,
14→a/b), nivel ≥2.

Único código para dos usos: `tests/test_renderer_coherencia.py` (comprobación exhaustiva por
barrido) y `generar_caso_completo` (guarda en tiempo de generación, #110) importan ambos de aquí.

Tolerancia de 2€ (subida desde 1€ en #110): se observaron descuadres de hasta 1€ por redondeo de
presentación en `fmt_eur` (cada línea se redondea a € entero por separado antes de sumar/restar
para mostrar — p. ej. 703.105€ frente a 703.104€ en el PDF Abreviado de referencia), que no son
una violación real de la identidad contable subyacente.
"""
from __future__ import annotations

from dataclasses import dataclass

TOLERANCIA_SUBTOTAL_EUR = 2.0


class InvarianteSubtotalWarning(UserWarning):
    """Se emite cuando una línea de detalle del Balance o la PyG no suma su propio subtotal
    (dentro de `TOLERANCIA_SUBTOTAL_EUR`) — ver `generar_caso_completo` (#110). El motor no se
    toca: es un límite ya documentado (decisiones_plausibilidad.md #109/#110), no un error de
    cálculo — el Balance total, el EFE y el ECPN siguen cuadrando exactos en estos casos."""


@dataclass
class ViolacionSubtotal:
    bloque: str
    codigo: str
    etiqueta: str
    año: int
    suma: float
    subtotal: float

    @property
    def diferencia(self) -> float:
        return self.suma - self.subtotal


def sub_lineas_suman_subtotal(lineas, años, nivel_min_padre=0, tolerancia=TOLERANCIA_SUBTOTAL_EUR):
    """Para cada línea en negrita (nivel >= nivel_min_padre), suma sus hijos inmediatos (nivel+1,
    hasta la siguiente línea de nivel <= el suyo) y compara contra su propio valor, año a año.
    Devuelve la lista de `ViolacionSubtotal` (vacía si todo cuadra dentro de la tolerancia)."""
    violaciones = []
    for i, linea in enumerate(lineas):
        if not linea.negrita or linea.nivel < nivel_min_padre:
            continue
        hijos = []
        j = i + 1
        while j < len(lineas) and lineas[j].nivel > linea.nivel:
            if lineas[j].nivel == linea.nivel + 1:
                hijos.append(lineas[j])
            j += 1
        if not hijos:
            continue
        for año in años:
            suma = sum(h.valores.get(año, 0.0) for h in hijos)
            subtotal = linea.valores.get(año, 0.0)
            if abs(suma - subtotal) > tolerancia:
                violaciones.append(ViolacionSubtotal(
                    bloque="", codigo=linea.codigo, etiqueta=linea.etiqueta, año=año,
                    suma=suma, subtotal=subtotal,
                ))
    return violaciones


def verificar_invariantes_balance_pyg(ejercicios, modelo, años=(2023, 2024, 2025),
                                       tolerancia=TOLERANCIA_SUBTOTAL_EUR):
    """Ejecuta el invariante "sub-líneas == subtotal" sobre el Balance (Activo y PN+Pasivo) y la
    PyG de un caso ya generado. Devuelve la lista de `ViolacionSubtotal` con el campo `bloque` ya
    etiquetado ("Balance — Activo" / "Balance — Patrimonio Neto y Pasivo" / "Cuenta de Pérdidas y
    Ganancias"), vacía si todo cuadra."""
    from mapeo_balance import mapear_balance_activo, mapear_balance_pn_pasivo
    from mapeo_pyg import mapear_pyg

    bloques = (
        ("Balance — Activo", mapear_balance_activo(ejercicios, modelo), 0),
        ("Balance — Patrimonio Neto y Pasivo", mapear_balance_pn_pasivo(ejercicios, modelo), 0),
        ("Cuenta de Pérdidas y Ganancias", mapear_pyg(ejercicios, modelo), 2),
    )
    return verificar_invariantes_lineas(bloques, años, tolerancia=tolerancia)


def verificar_invariantes_lineas(bloques, años=(2023, 2024, 2025), tolerancia=TOLERANCIA_SUBTOTAL_EUR):
    """Variante de bajo nivel: recibe los bloques YA construidos como
    `[(nombre_bloque, lineas, nivel_min_padre), ...]` — para cuando el llamador (p. ej.
    `generar_caso_completo`) ya tiene esas líneas calculadas y no quiere reconstruirlas."""
    violaciones = []
    for nombre_bloque, lineas, nivel_min_padre in bloques:
        for v in sub_lineas_suman_subtotal(lineas, años, nivel_min_padre=nivel_min_padre, tolerancia=tolerancia):
            v.bloque = nombre_bloque
            violaciones.append(v)
    return violaciones
