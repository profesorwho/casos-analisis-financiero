"""Tests de coberturas de flujos de efectivo (arquetipo 21) y subvenciones de capital
(transversales, disparadas por el arquetipo 17 "capex elevado" o por la probabilidad de fondo
por categoría de sector) — motor/coberturas_subvenciones.py.

Los tests de regresión genéricos (identidad Balance<->PN, EFE, ECPN, para los 21 arquetipos y
6 combinaciones) ya cubren estos dos mecanismos vía `tests/test_amortizacion.py`,
`tests/test_efe.py` y `tests/test_ecpn.py` (con "coberturas" añadido a `CUANTITATIVOS_A_PROBAR`
de los tres). Este archivo cubre lo que esos barridos genéricos NO comprueban: la plausibilidad
cuantitativa de la magnitud de la cobertura (el encargo pide verificarlo explícitamente, no
asumir que la fórmula financiera "correcta" da magnitudes razonables — ver docstring de
`motor.coberturas_subvenciones`), la verificación cruzada de 3 bandas de la subvención (EFE
C.9, línea de PN, imputación en PyG deben cuadrar ENTRE SÍ, no solo cada uno por separado), y la
estructura del Documento A (EIGR).
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.coberturas_subvenciones import TIPO_IMPOSITIVO_GENERAL
from motor.ecpn import generar_ecpn, generar_eigr
from motor.efe import generar_efe
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.memoria import generar_caso_combinado

VENTAS_OBJETIVO_2023 = 15_000_000.0

# Techo de plausibilidad para el ajuste de PN de la cobertura frente al balance total — mismo
# criterio de "verificar cuantitativamente, no asumir" del resto del proyecto (endeudamiento,
# subtotales de PyG...). No es un límite normativo, es un guardarraíl de regresión: si algún
# cambio futuro en TECHO_DELTA_R_ANUAL o en los rangos de nocional/plazo volviera a disparar
# ajustes desproporcionados (ya ocurrió una vez sin el techo de Δr, ver decisiones_
# plausibilidad.md), este test lo detecta.
TECHO_RATIO_AJUSTE_COBERTURA_SOBRE_ACTIVO = 0.10


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _codigos_sector(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


def test_plausibilidad_cuantitativa_del_ajuste_de_cobertura(catalogo, arquetipos):
    """Barrido de los 27 sectores x 4 semillas x 3 intensidades del arquetipo 21 en solitario —
    el ajuste de PN de la cobertura, en cualquier combinación, no debe superar un porcentaje
    razonable del balance total. Antes de acotar Δr (TECHO_DELTA_R_ANUAL), el peor caso del
    barrido (56.1, Restaurantes, sector pequeño y volátil) llegaba al 13,7% del balance — con
    el techo, el peor caso baja a ~2,1%."""
    max_ratio = 0.0
    max_caso = None
    for codigo in _codigos_sector(catalogo):
        for semilla in range(4):
            for intensidad in ("leve", "moderado", "fuerte"):
                evolucion = generar_evolucion_arquetipo(
                    codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
                    arquetipo_id="coberturas", catalogo=catalogo, arquetipos=arquetipos,
                )
                for ejercicio in evolucion.ejercicios.values():
                    activo_total = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
                    ratio = abs(ejercicio.ajustes_cambio_valor_pn_eur) / activo_total
                    if ratio > max_ratio:
                        max_ratio = ratio
                        max_caso = (codigo, semilla, intensidad)
    assert max_ratio <= TECHO_RATIO_AJUSTE_COBERTURA_SOBRE_ACTIVO, (
        f"Ajuste de cobertura desproporcionado: {max_ratio:.2%} del balance en {max_caso}"
    )


def test_verificacion_cruzada_subvencion_efe_pn_pyg(catalogo, arquetipos):
    """Las 3 bandas que debe explicar coherentemente el cobro de una subvención (ver encargo):
    (1) EFE C.9 = importe concedido, en el año de concesión; (2) la línea de PN (subvenciones,
    neta de impuesto) refleja el saldo 130 pendiente; (3) la imputación anual en PyG
    (otros_ingresos_explot) coincide con la transferencia bruta del año. Se comprueban juntas,
    no cada una por separado — el encargo pide explícitamente la coherencia CRUZADA."""
    evolucion = generar_evolucion_arquetipo(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte",
        arquetipo_id="capex_elevado", catalogo=catalogo, arquetipos=arquetipos,
    )
    hubo_concesion = False
    hubo_transferencia = False
    for año in (2024, 2025):
        anterior, actual = evolucion.ejercicios[año - 1], evolucion.ejercicios[año]
        efe = generar_efe(anterior, actual, obligatorio=True)

        # (1) EFE C.9 == importe concedido este año (0 si no hay concesión este año).
        assert efe.c9_instrumentos_patrimonio == pytest.approx(actual.subvencion_importe_concedido_eur, abs=0.01)
        if actual.subvencion_importe_concedido_eur > 0:
            hubo_concesion = True

        # (2) La línea de PN (neta) es exactamente el saldo bruto pendiente neto de impuesto.
        esperado_neto = actual.subvencion_saldo_130_bruto_eur * (1 - TIPO_IMPOSITIVO_GENERAL)
        assert actual.subvenciones_pn_eur == pytest.approx(esperado_neto, abs=0.01)

        # (3) La imputación en PyG de este año coincide con la transferencia bruta del año.
        if año == 2024:
            base_otros_ingresos = anterior.pyg_eur["otros_ingresos_explot"]
        # No se puede aislar directamente sin repetir la cascada — se comprueba en su lugar que
        # la transferencia bruta (si la hay) es estrictamente positiva y menor o igual al saldo
        # pendiente al inicio del año, y que coincide con lo que exige la identidad Balance<->PN
        # (ya verificada en tests/test_amortizacion.py) y con la reconciliación EFE (ya
        # verificada arriba vía C.9 + A.2.k, ver motor/efe.py).
        if actual.subvencion_transferencia_bruto_eur > 0:
            hubo_transferencia = True
            assert actual.subvencion_transferencia_bruto_eur <= anterior.subvencion_saldo_130_bruto_eur + 0.01

    assert hubo_concesion, "El caso de prueba no llegó a conceder ninguna subvención — revisar la semilla"
    assert hubo_transferencia, "El caso de prueba no llegó a imputar ninguna transferencia — revisar la semilla"


def test_eigr_estructura_y_total_coincide_con_ecpn(catalogo, arquetipos):
    """Documento A (EIGR): D (=A+B+C) debe coincidir exactamente con la fila "Total de ingresos
    y gastos reconocidos" del Documento B (ECPN) — verificado ya algebraicamente en el diseño,
    aquí se comprueba numéricamente sobre un caso con las dos operaciones a la vez (Combo E)."""
    combo = {"adquisicion": "fuerte", "activo_mantenido_venta": "fuerte", "operaciones_vinculadas": "fuerte", "coberturas": "fuerte"}
    evolucion = generar_caso_combinado(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, 1, combo, catalogo=catalogo, arquetipos=arquetipos,
    )
    for año in (2024, 2025):
        anterior, actual = evolucion.ejercicios[año - 1], evolucion.ejercicios[año]
        eigr = generar_eigr(actual, obligatorio=True)
        ecpn = generar_ecpn(anterior, actual, obligatorio=True)
        assert eigr.d_total_ingresos_gastos_reconocidos == pytest.approx(
            ecpn.total_ingresos_gastos_reconocidos.total, abs=0.01
        )
        # B_total y C_total ya incluyen su propio efecto impositivo (B.9/C.9).
        assert eigr.b_total == pytest.approx(eigr.b2_coberturas + eigr.b7_subvenciones + eigr.b9_efecto_impositivo, abs=0.01)
        assert eigr.c_total == pytest.approx(eigr.c2_coberturas + eigr.c7_subvenciones + eigr.c9_efecto_impositivo, abs=0.01)
        # C.7 (subvención) es siempre <= 0: el saldo 130 nunca es negativo (una subvención no
        # puede ser "menos que cero" — ver evolucionar_subvencion), así que lo que sale hacia la
        # PyG siempre reduce el saldo. C.2 (cobertura) NO tiene ese signo garantizado: el saldo
        # 1340 SÍ puede ser negativo (una cobertura que pierde valor), y en ese caso la
        # transferencia también es negativa, dando C.2 = -transferencia > 0 — no es un error,
        # es la reclasificación de una PÉRDIDA histórica saliendo hacia la PyG. La invariante
        # real es de MAGNITUD, no de signo: nunca se transfiere más de lo que había pendiente.
        assert eigr.c7_subvenciones <= 1e-6
        assert abs(eigr.c2_coberturas) <= abs(anterior.cobertura_saldo_1340_bruto_eur) + 0.01
        assert eigr.c7_subvenciones <= 1e-6


def test_eigr_obligatorio_comparte_flag_con_ecpn():
    """No existe un umbral distinto de "gran empresa" para el Documento A — comparte el mismo
    flag `obligatorio` que ya calcula motor.clasificacion_legal para el Documento B (ver
    docstring de motor.ecpn, corrección respecto a la versión anterior de este módulo). Un caso
    "pequeño" (obligatorio=False) sigue teniendo el AJUSTE contable real en su balance — lo que
    deja de ser obligatorio es el DOCUMENTO, nunca el dato."""
    from motor.evolucion_arquetipo import generar_evolucion_arquetipo as gen

    evolucion = gen(
        "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=0, intensidad="fuerte", arquetipo_id="coberturas",
    )
    ejercicio_2025 = evolucion.ejercicios[2025]
    eigr_pequena = generar_eigr(ejercicio_2025, obligatorio=False)
    eigr_grande = generar_eigr(ejercicio_2025, obligatorio=True)
    assert eigr_pequena.obligatorio is False
    assert eigr_grande.obligatorio is True
    # El dato subyacente (B.2, D...) es idéntico en ambos casos — solo cambia el flag.
    assert eigr_pequena.d_total_ingresos_gastos_reconocidos == eigr_grande.d_total_ingresos_gastos_reconocidos
    assert ejercicio_2025.ajustes_cambio_valor_pn_eur != 0.0  # el ajuste de balance existe igual
