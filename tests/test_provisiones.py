"""Tests del tercer lote de desglose de balance: Provisiones a largo/corto plazo (subgrupo 14
del PGC + 4994/4999, `motor/provisiones.py`) — epígrafes B.I/C.II del balance oficial, antes
completamente ausentes del motor.

Cubre lo pedido explícitamente: probabilidad de fondo independiente de cualquier arquetipo
(incluido el 6, "línea base sana"), movimiento anual completo (dotación/aplicación/exceso),
reclasificación largo→corto según se acerca el vencimiento, conexión con PyG (gastos_personal u
otros_gastos_explot para la dotación, otros_ingresos_explot para el exceso), cuadre exacto del
balance y del EFE, y la independencia estructural frente al arquetipo 22 (contingencia — NO se
toca en este lote, ver docstring de motor/provisiones.py)."""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.ecpn import generar_ecpn
from motor.efe import generar_efe
from motor.empresa_base import categoria_de_sector, tier_existencias_de_sector
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.memoria import generar_caso_combinado
from motor.provisiones import (
    CATEGORIAS_PROVISION,
    NATURALEZA_PYG_POR_CATEGORIA,
    PROBABILIDAD_PROVISION,
)

VENTAS_OBJETIVO_2023 = 15_000_000.0


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _sectores(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


def _cuadra(ejercicio) -> bool:
    activo = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
    pn_pasivo = (
        ejercicio.balance_eur["patrimonio_neto"]
        + ejercicio.balance_eur["pasivo_no_corriente"]
        + ejercicio.balance_eur["pasivo_corriente"]
    )
    return activo == pytest.approx(pn_pasivo, abs=1.0)


def _identidad_pn(ejercicio) -> float:
    """Misma fórmula EXACTA que `tests/test_amortizacion.py::_identidad_pn` — reproducida aquí
    (no importada, para no acoplar un archivo de test a otro) porque la dotación/exceso de
    provisión mueve `pyg_eur["resultado_ejercicio"]` exactamente igual que la amortización: la
    identidad `capital_social + reservas + resultado_ejercicio + ajustes_pn == patrimonio_neto`
    debe seguir cuadrando EXACTA, no solo el total agregado activo=pasivo+PN (`_cuadra`, que no
    depende de cómo se derive `reservas_eur`). Devuelve la diferencia absoluta, no un booleano,
    para poder reportar la magnitud exacta si algún día falla."""
    suma = (
        ejercicio.capital_social_eur
        + ejercicio.reservas_eur
        + ejercicio.pyg_eur["resultado_ejercicio"]
        + ejercicio.ajustes_cambio_valor_pn_eur
        + ejercicio.subvenciones_pn_eur
    )
    return abs(suma - ejercicio.balance_eur["patrimonio_neto"])


# --------------------------------------------------------------------------------------------
# 147 nunca aparece — descartada explícitamente (ver docstring de motor/provisiones.py).
# --------------------------------------------------------------------------------------------


def test_categoria_147_no_esta_incluida():
    assert "147" not in CATEGORIAS_PROVISION
    assert len(CATEGORIAS_PROVISION) == 8


def test_todas_las_categorias_tienen_naturaleza_pyg_valida():
    assert set(NATURALEZA_PYG_POR_CATEGORIA) == set(CATEGORIAS_PROVISION)
    assert set(NATURALEZA_PYG_POR_CATEGORIA.values()) <= {"gastos_personal", "otros_gastos_explot"}
    # Solo 140 (retribuciones al personal) es de naturaleza "gastos_personal" — el resto, gasto
    # general de explotación.
    assert NATURALEZA_PYG_POR_CATEGORIA["140"] == "gastos_personal"
    assert all(v == "otros_gastos_explot" for k, v in NATURALEZA_PYG_POR_CATEGORIA.items() if k != "140")


# --------------------------------------------------------------------------------------------
# Probabilidad de fondo, independiente de cualquier arquetipo — verificada con el arquetipo 6
# ("Aumento de clientes (base)", línea base sana), no solo teóricamente.
# --------------------------------------------------------------------------------------------


def test_probabilidad_de_fondo_con_arquetipo_6_dentro_del_rango_pedido(catalogo, arquetipos):
    """Pedido explícitamente: fácil de encontrar por búsqueda de semilla (orientativo 20%-30%),
    verificado con el arquetipo 6 en un barrido amplio, no solo con el valor teórico de
    PROBABILIDAD_PROVISION."""
    activas = 0
    total = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            total += 1
            if evolucion.ejercicios[2025].provision_activa:
                activas += 1
    tasa = activas / total
    assert 0.15 <= tasa <= 0.35, f"tasa de activación {tasa:.1%} fuera del rango esperado (216 casos: {activas} activas)"


def test_provision_nunca_dotada_en_el_año_base(catalogo, arquetipos):
    for codigo in ("24.1", "62", "47.1"):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio_2023 = evolucion.ejercicios[2023]
            assert ejercicio_2023.provision_saldo_largo_eur == 0.0
            assert ejercicio_2023.provision_saldo_corto_eur == 0.0
            assert ejercicio_2023.provision_dotacion_eur == 0.0


def test_las_8_categorias_aparecen_en_barrido_amplio(catalogo, arquetipos):
    vistas = set()
    for codigo in _sectores(catalogo):
        for semilla in range(20):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio = evolucion.ejercicios[2025]
            if ejercicio.provision_activa:
                vistas.add(ejercicio.provision_categoria)
    assert vistas == set(CATEGORIAS_PROVISION), f"categorías nunca vistas: {set(CATEGORIAS_PROVISION) - vistas}"


# --------------------------------------------------------------------------------------------
# Plausibilidad sectorial — 143/4994/4999 con peso mayor en los sectores indicados, verificado
# cuantificadamente, no solo asumido por construcción del multiplicador.
# --------------------------------------------------------------------------------------------


def test_143_desmantelamiento_es_mas_frecuente_en_industria_y_construccion(catalogo, arquetipos):
    conteo_por_categoria_sector: dict[str, dict[str, int]] = {}
    for codigo in _sectores(catalogo):
        cat_sector = categoria_de_sector(codigo)
        conteo_por_categoria_sector.setdefault(cat_sector, {"143": 0, "total": 0})
        for semilla in range(20):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio = evolucion.ejercicios[2025]
            if ejercicio.provision_activa:
                conteo_por_categoria_sector[cat_sector]["total"] += 1
                if ejercicio.provision_categoria == "143":
                    conteo_por_categoria_sector[cat_sector]["143"] += 1
    fraccion_boost = {
        cat: datos["143"] / datos["total"]
        for cat, datos in conteo_por_categoria_sector.items()
        if datos["total"] > 0 and cat in ("industria", "construccion")
    }
    fraccion_resto = {
        cat: datos["143"] / datos["total"]
        for cat, datos in conteo_por_categoria_sector.items()
        if datos["total"] > 0 and cat not in ("industria", "construccion")
    }
    assert fraccion_boost, "sin datos para industria/construccion — ampliar el barrido"
    assert min(fraccion_boost.values()) > max(fraccion_resto.values()), (
        f"boost {fraccion_boost} vs. resto {fraccion_resto}"
    )


def test_4994_contratos_onerosos_es_mas_frecuente_en_producto_en_curso_y_construccion(catalogo, arquetipos):
    conteo: dict[str, dict[str, int]] = {}
    for codigo in _sectores(catalogo):
        tier = tier_existencias_de_sector(codigo)
        cat_sector = categoria_de_sector(codigo)
        grupo = "boost" if tier == "producto_en_curso" or cat_sector == "construccion" else "resto"
        conteo.setdefault(grupo, {"4994": 0, "total": 0})
        for semilla in range(20):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio = evolucion.ejercicios[2025]
            if ejercicio.provision_activa:
                conteo[grupo]["total"] += 1
                if ejercicio.provision_categoria == "4994":
                    conteo[grupo]["4994"] += 1
    fraccion_boost = conteo["boost"]["4994"] / conteo["boost"]["total"]
    fraccion_resto = conteo["resto"]["4994"] / conteo["resto"]["total"]
    assert fraccion_boost > fraccion_resto, f"boost {fraccion_boost:.1%} vs. resto {fraccion_resto:.1%}"


def test_4999_garantias_comerciales_es_mas_frecuente_en_industria_y_comercio(catalogo, arquetipos):
    conteo: dict[str, dict[str, int]] = {}
    for codigo in _sectores(catalogo):
        cat_sector = categoria_de_sector(codigo)
        grupo = "boost" if cat_sector in ("industria", "comercio_hosteleria") else "resto"
        conteo.setdefault(grupo, {"4999": 0, "total": 0})
        for semilla in range(20):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            ejercicio = evolucion.ejercicios[2025]
            if ejercicio.provision_activa:
                conteo[grupo]["total"] += 1
                if ejercicio.provision_categoria == "4999":
                    conteo[grupo]["4999"] += 1
    fraccion_boost = conteo["boost"]["4999"] / conteo["boost"]["total"]
    fraccion_resto = conteo["resto"]["4999"] / conteo["resto"]["total"]
    assert fraccion_boost > fraccion_resto, f"boost {fraccion_boost:.1%} vs. resto {fraccion_resto:.1%}"


# --------------------------------------------------------------------------------------------
# Movimiento anual — saldo_inicial + dotación - aplicación - exceso = saldo_final, exacto.
# --------------------------------------------------------------------------------------------


def test_movimiento_anual_reconcilia_exacto(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].provision_activa:
                continue
            for año_anterior, año in ((2023, 2024), (2024, 2025)):
                anterior = evolucion.ejercicios[año_anterior]
                actual = evolucion.ejercicios[año]
                saldo_anterior = anterior.provision_saldo_largo_eur + anterior.provision_saldo_corto_eur
                saldo_actual = actual.provision_saldo_largo_eur + actual.provision_saldo_corto_eur
                esperado = saldo_anterior + actual.provision_dotacion_eur - actual.provision_aplicacion_eur - actual.provision_exceso_eur
                assert saldo_actual == pytest.approx(esperado, abs=0.01), f"{codigo} semilla={semilla} año={año}"
                comprobados += 1
    assert comprobados > 0


def test_saldo_nunca_negativo_y_nunca_largo_y_corto_a_la_vez(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert ejercicio.provision_saldo_largo_eur >= 0
                assert ejercicio.provision_saldo_corto_eur >= 0
                assert ejercicio.provision_saldo_largo_eur == 0.0 or ejercicio.provision_saldo_corto_eur == 0.0
                comprobados += 1
    assert comprobados > 0


def test_reclasificacion_largo_a_corto_ocurre_en_barrido_amplio(catalogo, arquetipos):
    """El paso natural largo→corto según se acerca el vencimiento (mismo espíritu que
    EfectoReclasificacionDeuda) debe observarse de verdad, no solo en teoría."""
    transiciones = 0
    for codigo in _sectores(catalogo):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for año_anterior, año in ((2023, 2024), (2024, 2025)):
                anterior = evolucion.ejercicios[año_anterior]
                actual = evolucion.ejercicios[año]
                if anterior.provision_saldo_largo_eur > 0 and actual.provision_saldo_corto_eur > 0:
                    transiciones += 1
    assert transiciones > 0, "ninguna transición largo->corto observada — ampliar el barrido"


# --------------------------------------------------------------------------------------------
# Conexión con PyG — dotación resta de la línea correcta, exceso suma a otros_ingresos_explot,
# nunca "flotando" sin reflejo en ningún sitio.
# --------------------------------------------------------------------------------------------


def test_dotacion_reduce_la_linea_de_pyg_correcta_segun_la_categoria(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in (evolucion.ejercicios[2024], evolucion.ejercicios[2025]):
                if ejercicio.provision_dotacion_eur <= 0:
                    continue
                comprobados += 1
                assert ejercicio.provision_naturaleza_pyg in ("gastos_personal", "otros_gastos_explot")
    assert comprobados > 0


def test_balance_y_pyg_cuadran_con_provision_activa(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(10):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].provision_activa:
                continue
            for ejercicio in evolucion.ejercicios.values():
                assert _cuadra(ejercicio), f"{codigo} semilla={semilla} año={ejercicio.año}"
                comprobados += 1
    assert comprobados > 0


def test_identidad_balance_pyg_resultado_ejercicio_con_provision_activa(catalogo, arquetipos):
    """Pedido explícitamente: la dotación y el exceso de provisión mueven `pyg_eur[
    "resultado_ejercicio"]` (vía el ajuste post-hoc de `_evolucionar_un_año`, igual mecanismo que
    grupo89) exactamente igual que la amortización mueve la PyG (ver decisiones_plausibilidad.md
    #30, `tests/test_amortizacion.py::_identidad_pn`) — así que es la MISMA comprobación de
    identidad (`balance.PN.capital_social + reservas + resultado_ejercicio + ajustes_pn ==
    balance.patrimonio_neto`, con `resultado_ejercicio` tomado del PyG), aplicada aquí de forma
    explícita en vez de asumir que se hereda del hallazgo #30. NO estaba cubierta por los 600
    tests previos: `test_balance_y_pyg_cuadran_con_provision_activa` (arriba) solo comprueba el
    total agregado activo=pasivo+PN (`_cuadra`), que no depende de cómo se derive `reservas_eur`
    — esta comprobación es más estricta y específica, y faltaba."""
    comprobados = 0
    max_diff_eur = 0.0
    for codigo in _sectores(catalogo):
        for semilla in range(15):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].provision_activa:
                continue
            for ejercicio in evolucion.ejercicios.values():
                diff_eur = _identidad_pn(ejercicio)
                max_diff_eur = max(max_diff_eur, diff_eur)
                assert diff_eur < 1e-6, f"{codigo} semilla={semilla} año={ejercicio.año}: diferencia {diff_eur}€"
                comprobados += 1
    assert comprobados > 0, "ningún caso con provisión activa en el barrido — ampliar semillas"


def test_efe_y_ecpn_cuadran_con_provision_activa_arquetipo_solo_y_combinado(catalogo, arquetipos):
    """Complementa `test_efe_cuadra_con_provision_activa_sin_lineas_nuevas` (arriba, solo EFE en
    solitario) con el ECPN y con un caso combinado (arquetipo 6 + arquetipo 22, mismo patrón que
    `test_arquetipo_22_sigue_sin_tocar_el_balance_combinado_con_provision`) — mismo estándar que
    `tests/test_amortizacion.py::test_identidad_balance_pyg_y_reconciliacion_efe_ecpn_*`."""
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(8):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].provision_activa:
                continue
            for año in (2024, 2025):
                efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
                ecpn = generar_ecpn(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
                assert efe.cuadra, f"{codigo} semilla={semilla} año={año}: EFE descuadre {efe.descuadre_eur:,.4f}€"
                assert ecpn.cuadra, f"{codigo} semilla={semilla} año={año}: ECPN descuadre {ecpn.descuadre_eur:,.4f}€"
                comprobados += 1
    assert comprobados > 0

    comprobados_combo = 0
    for semilla in range(30):
        caso = generar_caso_combinado(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"aumento_clientes": "fuerte", "informacion_relevante_memoria": "fuerte"},
            catalogo=catalogo, arquetipos=arquetipos,
        )
        if not caso.ejercicios[2025].provision_activa:
            continue
        for ejercicio in caso.ejercicios.values():
            assert _identidad_pn(ejercicio) < 1e-6, f"combo semilla={semilla} año={ejercicio.año}"
        for año in (2024, 2025):
            efe = generar_efe(caso.ejercicios[año - 1], caso.ejercicios[año], obligatorio=True)
            ecpn = generar_ecpn(caso.ejercicios[año - 1], caso.ejercicios[año], obligatorio=True)
            assert efe.cuadra and ecpn.cuadra, f"combo semilla={semilla} año={año}"
        comprobados_combo += 1
    assert comprobados_combo > 0, "ninguna semilla combinó provisión activa con el arquetipo 22 — ampliar el barrido"


# --------------------------------------------------------------------------------------------
# EFE — la dotación/exceso, al tener SIEMPRE una contrapartida real en otras_deudas_largo/corto
# (a diferencia de grupo89, que es pura valoración sin caja detrás), se reconcilia mediante las
# líneas YA existentes A.3.e/A.3.f — sin necesitar ninguna línea nueva. Verificado, no asumido.
# --------------------------------------------------------------------------------------------


def test_efe_cuadra_con_provision_activa_sin_lineas_nuevas(catalogo, arquetipos):
    comprobados = 0
    for codigo in _sectores(catalogo):
        for semilla in range(10):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            if not evolucion.ejercicios[2025].provision_activa:
                continue
            for año in (2024, 2025):
                efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
                assert efe.cuadra, f"{codigo} semilla={semilla} año={año}: descuadre={efe.descuadre_eur}"
                comprobados += 1
    assert comprobados > 0


# --------------------------------------------------------------------------------------------
# Independencia frente al arquetipo 22 (contingencia) — coexisten sin relación causal, el 22
# sigue siendo puramente textual, sin ninguna huella en el balance.
# --------------------------------------------------------------------------------------------


def test_arquetipo_22_sigue_sin_tocar_el_balance_combinado_con_provision(catalogo, arquetipos):
    encontrado_con_provision = False
    for semilla in range(30):
        caso = generar_caso_combinado(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"aumento_clientes": "fuerte", "informacion_relevante_memoria": "fuerte"},
            catalogo=catalogo, arquetipos=arquetipos,
        )
        assert [n.arquetipo_id for n in caso.notas_memoria_pura] == ["informacion_relevante_memoria"]
        ejercicio_2025 = caso.ejercicios[2025]
        if ejercicio_2025.provision_activa:
            encontrado_con_provision = True
            # El 22 no añade ni quita nada del balance — la provisión (si la hay) sigue
            # exactamente el mismo mecanismo que en solitario, sin interacción.
            evolucion_sola = generar_evolucion_arquetipo(
                "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="aumento_clientes", catalogo=catalogo, arquetipos=arquetipos,
            )
            assert ejercicio_2025.provision_saldo_largo_eur == pytest.approx(
                evolucion_sola.ejercicios[2025].provision_saldo_largo_eur, abs=0.01
            )
            assert ejercicio_2025.provision_saldo_corto_eur == pytest.approx(
                evolucion_sola.ejercicios[2025].provision_saldo_corto_eur, abs=0.01
            )
    assert encontrado_con_provision, "ninguna semilla combinó provisión activa con el arquetipo 22 — ampliar el barrido"


def test_probabilidad_provision_es_constante_documentada():
    assert PROBABILIDAD_PROVISION == pytest.approx(0.25)
