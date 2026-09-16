"""Tests del segundo lote de desglose de balance según el mapeo oficial del PGC: Deudores
comerciales y otras cuentas a cobrar / Acreedores comerciales y otras cuentas a pagar (7
sub-partidas oficiales cada uno, carve-out de `realizable`/`acreedores_comerciales` — mismo
patrón "perfil fijo, desglose recalculado cada año" que el lote 1, ver
test_desglose_existencias_periodificaciones.py) y las dos masas nuevas que el arquetipo 20
("Operaciones vinculadas") puede activar cuando selecciona una de sus 2 operaciones FINANCIERAS:
"Inversiones en empresas del grupo y asociadas a l/p" (préstamo a matriz) y "Deudas con empresas
del grupo y asociadas a l/p" (financiación recibida de grupo) — ver motor/evolucion_arquetipo.py,
`ParametrosOperacionVinculada`.

Deudores usa un perfil ÚNICO (no por sector): verificado contra `ratios.cobro_dias` del catálogo
que "Clientes" domina con fuerza uniforme en los 27 sectores (ver decisiones_plausibilidad.md).
Acreedores usa un perfil por categoría (las 9 de CATEGORIA_SECTOR), con la lección de
`ratios.coste_deuda`/`pago_dias` ya aplicada: solo dirección cualitativa (mano de obra vs.
compra de materiales), nunca un anclaje literal al dato distorsionado.

"Combinaciones ilógicas" reforzado (lección explícita del lote 1, ver ahí #52-53): no solo se
verifica que la categoría dominante tenga sentido, también que las sub-partidas de "empresas del
grupo"/"accionistas" queden en CERO cuando el arquetipo 20 no está activo (Tipo 2 puro, sin
probabilidad de fondo — a diferencia de provisiones).
"""

import re

import pytest

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.efe import generar_efe
from motor.empresa_base import (
    CATEGORIA_SECTOR,
    PERFIL_ACREEDORES_POR_CATEGORIA,
    PERFIL_DEUDORES_BASE,
    categoria_de_sector,
    generar_empresa_base,
)
from motor.evolucion_arquetipo import (
    COMPONENTE_DESGLOSE_POR_TIPO,
    MAGNITUD_REFERENCIA_POR_TIPO,
    TIPO_OPERACION_POR_INDICE,
    generar_evolucion_arquetipo,
)
from motor.memoria import generar_caso_combinado, generar_nota_operaciones_vinculadas

VENTAS_OBJETIVO_2023 = 15_000_000.0


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


@pytest.fixture(scope="module")
def arquetipos():
    return cargar_arquetipos()


def _sectores(catalogo):
    return [re.search(r"\(([^()]+)\)\s*$", s).group(1) for s in catalogo["sector"].unique()]


COMPONENTES_DEUDORES = tuple(PERFIL_DEUDORES_BASE)
COMPONENTES_ACREEDORES = tuple(next(iter(PERFIL_ACREEDORES_POR_CATEGORIA.values())))


# --------------------------------------------------------------------------------------------
# Suma a 100% — deudores/acreedores, empresa base y evolución (sin arquetipo 20).
# --------------------------------------------------------------------------------------------


def test_deudores_acreedores_desglose_suma_100_por_ciento_en_empresa_base(catalogo):
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            assert sum(empresa.deudores_perfil_pct.values()) == pytest.approx(1.0, abs=1e-9)
            assert sum(empresa.acreedores_perfil_pct.values()) == pytest.approx(1.0, abs=1e-9)
            assert sum(empresa.deudores_desglose_eur.values()) == pytest.approx(empresa.balance_eur["realizable"], abs=0.01)
            assert sum(empresa.acreedores_desglose_eur.values()) == pytest.approx(
                empresa.balance_eur["acreedores_comerciales"], abs=0.01
            )
            for valor in empresa.deudores_perfil_pct.values():
                assert valor >= 0
            for valor in empresa.acreedores_perfil_pct.values():
                assert valor >= 0


def test_deudores_acreedores_desglose_suma_100_por_ciento_en_evolucion_con_exceso_stock(catalogo, arquetipos):
    """El arquetipo 5 (exceso de stock) no toca realizable/acreedores_comerciales directamente,
    pero ambas masas SÍ varían año a año por crecimiento proporcional de ventas — el desglose
    debe seguir sumando exactamente el total, los 3 años, con el perfil (%) constante desde 2023
    (sin arquetipo 20 activo: ninguna sub-partida de grupo se fuerza)."""
    for codigo in ("24.1", "47.1", "62"):
        for semilla in range(3):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad="fuerte",
                arquetipo_id="exceso_stock", catalogo=catalogo, arquetipos=arquetipos,
            )
            perfil_deudores_2023 = evolucion.ejercicios[2023].deudores_perfil_pct
            perfil_acreedores_2023 = evolucion.ejercicios[2023].acreedores_perfil_pct
            for ejercicio in evolucion.ejercicios.values():
                assert ejercicio.deudores_perfil_pct == perfil_deudores_2023
                assert ejercicio.acreedores_perfil_pct == perfil_acreedores_2023
                assert sum(ejercicio.deudores_desglose_eur.values()) == pytest.approx(
                    ejercicio.balance_eur["realizable"], abs=0.01
                )
                assert sum(ejercicio.acreedores_desglose_eur.values()) == pytest.approx(
                    ejercicio.balance_eur["acreedores_comerciales"], abs=0.01
                )
                # Sin arquetipo 20 activo: Tipo 2 puro, sin probabilidad de fondo.
                assert ejercicio.deudores_desglose_eur["clientes_empresas_grupo"] == pytest.approx(0.0, abs=0.01)
                assert ejercicio.acreedores_desglose_eur["proveedores_empresas_grupo"] == pytest.approx(0.0, abs=0.01)
                assert ejercicio.inversion_grupo_largo_eur == 0.0
                assert ejercicio.deuda_grupo_largo_eur == 0.0
                assert not ejercicio.operacion_vinculada_activa


def test_todos_los_27_sectores_tienen_perfil_de_deudores_y_acreedores(catalogo):
    for codigo in _sectores(catalogo):
        categoria = categoria_de_sector(codigo)
        assert categoria in PERFIL_ACREEDORES_POR_CATEGORIA
    assert set(PERFIL_ACREEDORES_POR_CATEGORIA) == set(CATEGORIA_SECTOR.values())


def test_perfil_deudores_base_y_todos_los_perfiles_de_acreedores_suman_100_por_ciento():
    assert sum(PERFIL_DEUDORES_BASE.values()) == pytest.approx(1.0, abs=1e-9)
    for perfil in PERFIL_ACREEDORES_POR_CATEGORIA.values():
        assert sum(perfil.values()) == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------------------------
# "Combinaciones ilógicas" reforzado (lección del lote 1): no solo la categoría dominante tiene
# sentido, también qué sub-partidas deben quedar en cero/marginal para qué tipo de sector.
# --------------------------------------------------------------------------------------------


def test_clientes_domina_con_claridad_en_los_27_sectores(catalogo):
    """Verificación cuantificada del hallazgo de cobro_dias (ver docstring de
    PERFIL_DEUDORES_BASE en motor/empresa_base.py): "Clientes" debe ser, con claridad, la
    sub-partida dominante en TODOS los sectores (no solo "la más grande por poco") — perfil
    único, sin excepción sectorial, a diferencia de existencias."""
    for codigo in _sectores(catalogo):
        for semilla in range(3):
            empresa = generar_empresa_base(codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
            d = empresa.deudores_desglose_eur
            otras = sum(v for k, v in d.items() if k != "clientes")
            assert d["clientes"] > otras, f"{codigo} semilla={semilla}: clientes no domina: {d}"


def test_proveedores_domina_y_personal_pendiente_es_mayor_en_sectores_intensivos_en_mano_de_obra(catalogo):
    """Reforzado: no solo "proveedores domina en todas las categorías" sino la relación
    COMPARATIVA que motivó el perfil por categoría — sectores intensivos en mano de obra
    (servicios profesionales/TIC, administración/educación/sanidad) deben llevar una fracción de
    "Personal (remuneraciones pendientes)" mayor, y de "Proveedores" menor, que sectores
    intensivos en compra de materiales/mercancía (industria, comercio, construcción)."""
    intensivos_mano_obra = ("servicios_profesionales", "servicios_tic", "administracion_educacion_sanidad")
    intensivos_materiales = ("industria", "comercio_hosteleria", "construccion")
    for categoria in PERFIL_ACREEDORES_POR_CATEGORIA:
        perfil = PERFIL_ACREEDORES_POR_CATEGORIA[categoria]
        assert perfil["proveedores"] > sum(v for k, v in perfil.items() if k not in ("proveedores", "proveedores_empresas_grupo")), (
            f"{categoria}: proveedores no domina: {perfil}"
        )
    personal_mano_obra = [PERFIL_ACREEDORES_POR_CATEGORIA[c]["personal"] for c in intensivos_mano_obra]
    personal_materiales = [PERFIL_ACREEDORES_POR_CATEGORIA[c]["personal"] for c in intensivos_materiales]
    proveedores_mano_obra = [PERFIL_ACREEDORES_POR_CATEGORIA[c]["proveedores"] for c in intensivos_mano_obra]
    proveedores_materiales = [PERFIL_ACREEDORES_POR_CATEGORIA[c]["proveedores"] for c in intensivos_materiales]
    assert min(personal_mano_obra) > max(personal_materiales), (
        f"personal (mano de obra) {personal_mano_obra} vs. (materiales) {personal_materiales}"
    )
    assert max(proveedores_mano_obra) < min(proveedores_materiales), (
        f"proveedores (mano de obra) {proveedores_mano_obra} vs. (materiales) {proveedores_materiales}"
    )


def test_sub_partidas_de_grupo_y_accionistas_en_cero_sin_arquetipo_20(catalogo, arquetipos):
    """Reforzado (lección del lote 1): "clientes_empresas_grupo", "proveedores_empresas_grupo" y
    "accionistas_desembolsos_exigidos" deben quedar en CERO (o residuo marginal de ruido, para el
    último) en cualquier caso SIN el arquetipo 20 activo — Tipo 2 puro, sin probabilidad de
    fondo, a diferencia de provisiones (arquetipo 6)."""
    for codigo in _sectores(catalogo):
        for arquetipo_id in ("exceso_stock", "apalancamiento", "capex_elevado"):
            evolucion = generar_evolucion_arquetipo(
                codigo, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, intensidad="fuerte",
                arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
            )
            for ejercicio in evolucion.ejercicios.values():
                assert ejercicio.deudores_desglose_eur["clientes_empresas_grupo"] == pytest.approx(0.0, abs=0.01)
                assert ejercicio.acreedores_desglose_eur["proveedores_empresas_grupo"] == pytest.approx(0.0, abs=0.01)
                assert ejercicio.inversion_grupo_largo_eur == 0.0
                assert ejercicio.deuda_grupo_largo_eur == 0.0


# --------------------------------------------------------------------------------------------
# Arquetipo 20 activo — las 5 operaciones aterrizan en la línea correcta, con el MISMO importe
# que cita la nota de memoria (requisito explícito: "no generar un número nuevo independiente").
# --------------------------------------------------------------------------------------------


def _ejercicio_2025_operacion_vinculada(catalogo, arquetipos, sector, intensidad, semilla):
    evolucion = generar_evolucion_arquetipo(
        sector, "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, intensidad=intensidad,
        arquetipo_id="operaciones_vinculadas", catalogo=catalogo, arquetipos=arquetipos,
    )
    return evolucion


def test_el_importe_aterrizado_en_balance_es_el_mismo_que_cita_la_nota(catalogo, arquetipos):
    for codigo in ("24.1", "62", "47.1", "68", "86.1"):
        for semilla in range(6):
            evolucion = _ejercicio_2025_operacion_vinculada(catalogo, arquetipos, codigo, "fuerte", semilla)
            ejercicio = evolucion.ejercicios[2025]
            assert ejercicio.operacion_vinculada_activa
            nota = generar_nota_operaciones_vinculadas(ejercicio)
            importe_texto = float(re.search(r"([\d\.]+) euros", nota.texto).group(1).replace(".", ""))
            assert importe_texto == pytest.approx(round(ejercicio.operacion_vinculada_importe_eur / 1000) * 1000, abs=1)


def test_cada_uno_de_los_5_tipos_aterriza_en_la_linea_oficial_correcta(catalogo, arquetipos):
    """Barrido de semillas hasta observar los 5 tipos (barajados, no garantizado en pocas
    semillas) — para cada uno, confirma la línea PGC concreta donde debe aparecer."""
    tipos_vistos: dict[str, object] = {}
    for semilla in range(60):
        evolucion = _ejercicio_2025_operacion_vinculada(catalogo, arquetipos, "24.1", "fuerte", semilla)
        ejercicio = evolucion.ejercicios[2025]
        tipo = ejercicio.operacion_vinculada_tipo
        if tipo not in tipos_vistos:
            tipos_vistos[tipo] = ejercicio
        if len(tipos_vistos) == len(TIPO_OPERACION_POR_INDICE):
            break
    assert set(tipos_vistos) == set(TIPO_OPERACION_POR_INDICE), f"solo se vieron: {sorted(tipos_vistos)}"

    ej = tipos_vistos["prestamo_matriz"]
    assert ej.inversion_grupo_largo_eur == pytest.approx(ej.operacion_vinculada_importe_eur, rel=1e-6)
    assert ej.deuda_grupo_largo_eur == 0.0

    ej = tipos_vistos["financiacion_recibida_grupo"]
    assert ej.deuda_grupo_largo_eur == pytest.approx(ej.operacion_vinculada_importe_eur, rel=1e-6)
    assert ej.inversion_grupo_largo_eur == 0.0
    # Sin gastos financieros adicionales: nunca dentro de deudas_fin_largo/corto (las únicas que
    # alimentan gastos_financieros = deuda_financiera_media x tipo_interes).
    assert ej.balance_eur["deudas_fin_largo"] + ej.balance_eur["deudas_fin_corto"] < ej.balance_eur["otras_deudas_largo"] + 1

    ej = tipos_vistos["facturacion_servicios_grupo"]
    assert ej.deudores_desglose_eur["clientes_empresas_grupo"] == pytest.approx(ej.operacion_vinculada_importe_eur, rel=1e-6)

    ej = tipos_vistos["asistencia_tecnica_matriz"]
    assert ej.acreedores_desglose_eur["proveedores_empresas_grupo"] == pytest.approx(ej.operacion_vinculada_importe_eur, rel=1e-6)

    ej = tipos_vistos["arrendamiento_socio"]
    # "No es realmente empresas del grupo" (criterio explícito del encargo): aterriza en
    # Acreedores varios, NUNCA en la línea de "empresas del grupo".
    assert ej.acreedores_desglose_eur["proveedores_empresas_grupo"] == pytest.approx(0.0, abs=0.01)


def test_balance_cuadra_con_cada_uno_de_los_5_tipos_activos(catalogo, arquetipos):
    for codigo in ("24.1", "62", "47.1", "68"):
        for semilla in range(10):
            evolucion = _ejercicio_2025_operacion_vinculada(catalogo, arquetipos, codigo, "fuerte", semilla)
            for ejercicio in evolucion.ejercicios.values():
                activo = ejercicio.balance_eur["activo_no_corriente"] + ejercicio.balance_eur["activo_corriente"]
                pn_pasivo = (
                    ejercicio.balance_eur["patrimonio_neto"]
                    + ejercicio.balance_eur["pasivo_no_corriente"]
                    + ejercicio.balance_eur["pasivo_corriente"]
                )
                assert activo == pytest.approx(pn_pasivo, abs=1.0), f"{codigo} semilla={semilla} año={ejercicio.año}"


# --------------------------------------------------------------------------------------------
# Punto 1 de la confirmación del usuario: "financiación recibida de grupo" pasa por la MISMA
# contención de endeudamiento que ya protege a 9/14/17/18 (señalizada, sin palanca de
# amortiguación propia — el arquetipo 20 no toca ninguna masa de circulante).
# --------------------------------------------------------------------------------------------


def test_financiacion_recibida_de_grupo_entra_en_el_calculo_de_endeudamiento(catalogo, arquetipos):
    from motor.evolucion_arquetipo import _endeudamiento

    encontrado = False
    for semilla in range(30):
        evolucion = _ejercicio_2025_operacion_vinculada(catalogo, arquetipos, "24.1", "fuerte", semilla)
        ejercicio = evolucion.ejercicios[2025]
        if ejercicio.operacion_vinculada_tipo != "financiacion_recibida_grupo":
            continue
        encontrado = True
        endeudamiento_con = _endeudamiento(ejercicio.balance_eur)
        balance_sin_deuda_grupo = dict(ejercicio.balance_eur)
        balance_sin_deuda_grupo["otras_deudas_largo"] -= ejercicio.deuda_grupo_largo_eur
        balance_sin_deuda_grupo["pasivo_no_corriente"] -= ejercicio.deuda_grupo_largo_eur
        endeudamiento_sin = _endeudamiento(balance_sin_deuda_grupo)
        assert ejercicio.endeudamiento == pytest.approx(endeudamiento_con, rel=1e-9)
        assert endeudamiento_con > endeudamiento_sin, "la deuda de grupo debe subir el endeudamiento medido"
    assert encontrado, "ninguna de las 30 semillas activó 'financiacion_recibida_grupo' — ampliar el barrido"


def test_riesgo_endeudamiento_se_activa_igual_que_en_apalancamiento_al_combinar_con_9(catalogo, arquetipos):
    """Combina operaciones_vinculadas + apalancamiento (9) — si la combinación empuja el
    endeudamiento sobre el techo del sector, debe señalizarse `riesgo_endeudamiento=True` y
    `contencion_al_limite=True` (sin palanca de amortiguación: ninguno de los dos toca
    circulante), exactamente el mismo patrón ya aceptado para 9/14/17/18 en solitario."""
    from motor.evolucion_arquetipo import generar_evolucion_combinada

    activaciones = 0
    for semilla in range(20):
        evolucion = generar_evolucion_combinada(
            "43.2", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"operaciones_vinculadas": "fuerte", "apalancamiento": "fuerte"}, catalogo=catalogo, arquetipos=arquetipos,
        )
        for ejercicio in (evolucion.ejercicios[2024], evolucion.ejercicios[2025]):
            if ejercicio.riesgo_endeudamiento:
                activaciones += 1
                assert ejercicio.contencion_al_limite
    assert activaciones > 0, "ninguna activación de riesgo_endeudamiento en 20 semillas — ampliar el barrido/sector"


# --------------------------------------------------------------------------------------------
# Punto 2 de la confirmación del usuario: el préstamo a matriz y la financiación recibida fluyen
# a sus líneas propias del EFE (B.6.c / C.10.c), nunca a "entidades de crédito" ni a una
# genérica, y la reconciliación exacta se mantiene con estas 2 masas moviendo caja de verdad.
# --------------------------------------------------------------------------------------------


def test_efe_cuadra_y_usa_las_lineas_propias_con_cada_uno_de_los_5_tipos(catalogo, arquetipos):
    for codigo in ("24.1", "62", "68"):
        for semilla in range(10):
            evolucion = _ejercicio_2025_operacion_vinculada(catalogo, arquetipos, codigo, "fuerte", semilla)
            for año in (2024, 2025):
                anterior = evolucion.ejercicios[año - 1]
                actual = evolucion.ejercicios[año]
                efe = generar_efe(anterior, actual, obligatorio=True)
                assert efe.cuadra, f"{codigo} semilla={semilla} año={año}: descuadre={efe.descuadre_eur}"
                delta_inversion_grupo = actual.inversion_grupo_largo_eur - anterior.inversion_grupo_largo_eur
                delta_deuda_grupo = actual.deuda_grupo_largo_eur - anterior.deuda_grupo_largo_eur
                assert efe.b6c_prestamo_empresas_grupo == pytest.approx(-delta_inversion_grupo, abs=1.0)
                assert efe.c10c_empresas_grupo == pytest.approx(delta_deuda_grupo, abs=1.0)
                if delta_deuda_grupo != 0:
                    # La financiación de grupo NUNCA se mezcla con la línea de entidades de
                    # crédito (c10, que sí alimenta gastos_financieros vía tipo_interes).
                    deuda_financiera_delta = (
                        actual.balance_eur["deudas_fin_largo"] + actual.balance_eur["deudas_fin_corto"]
                    ) - (anterior.balance_eur["deudas_fin_largo"] + anterior.balance_eur["deudas_fin_corto"])
                    assert efe.c10_variacion_neta_deuda_financiera == pytest.approx(deuda_financiera_delta, abs=1.0)


def test_regresion_efe_grupo89_y_adquisicion_sigue_cuadrando_combinado_con_operaciones_vinculadas(catalogo, arquetipos):
    """Combo E completo (adquisicion + activo_mantenido_venta + operaciones_vinculadas +
    coberturas, ver tests/test_combinacion_arquetipos.py) — el EFE debe seguir cuadrando con las
    2 masas nuevas de este lote conviviendo con el resto de mecanismos que ya mueven caja real
    (adquisición, cobertura/subvención)."""
    for semilla in range(6):
        evolucion = generar_caso_combinado(
            "24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla,
            {"adquisicion": "fuerte", "activo_mantenido_venta": "fuerte", "operaciones_vinculadas": "fuerte", "coberturas": "fuerte"},
            catalogo=catalogo, arquetipos=arquetipos,
        )
        for año in (2024, 2025):
            efe = generar_efe(evolucion.ejercicios[año - 1], evolucion.ejercicios[año], obligatorio=True)
            assert efe.cuadra, f"semilla={semilla} año={año}: descuadre={efe.descuadre_eur}"


# --------------------------------------------------------------------------------------------
# Magnitud de referencia — coherente con el tipo de operación (mismo mapeo en motor.memoria y
# motor.evolucion_arquetipo, verificado estructuralmente aquí).
# --------------------------------------------------------------------------------------------


def test_magnitud_referencia_cubre_los_5_tipos():
    assert set(MAGNITUD_REFERENCIA_POR_TIPO) == set(TIPO_OPERACION_POR_INDICE)
    assert set(MAGNITUD_REFERENCIA_POR_TIPO.values()) <= {"ventas", "patrimonio_neto", "deuda_financiera"}


def test_componente_desglose_cubre_exactamente_los_3_tipos_comerciales_varios():
    esperados = {"facturacion_servicios_grupo", "arrendamiento_socio", "asistencia_tecnica_matriz"}
    assert set(COMPONENTE_DESGLOSE_POR_TIPO) == esperados


# --------------------------------------------------------------------------------------------
# Hallazgo de auditoría de trazabilidad (Ronda 1, Fase 4, ver motor/resumen_caso.py): el modo
# típico/atípico de cada sub-partida de deudores/acreedores se descartaba con `_generar_partida(
# ...) -> valor, _`, a diferencia de las masas de nivel superior (diseño original). Corregido.
# --------------------------------------------------------------------------------------------


def test_generar_perfil_deudores_y_acreedores_exponen_el_modo_de_cada_componente(catalogo):
    import numpy as np

    from motor.empresa_base import generar_perfil_acreedores, generar_perfil_deudores

    perfil_deudores, modos_deudores = generar_perfil_deudores(np.random.default_rng(1))
    assert set(perfil_deudores) == set(modos_deudores)
    assert set(modos_deudores.values()) <= {"tipico", "atipico"}

    perfil_acreedores, modos_acreedores = generar_perfil_acreedores(np.random.default_rng(1), "industria")
    assert set(perfil_acreedores) == set(modos_acreedores)
    assert set(modos_acreedores.values()) <= {"tipico", "atipico"}

    empresa = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=1, catalogo=catalogo)
    assert {k for k in empresa.modos if k.startswith("deudores.")} == {
        f"deudores.{componente}" for componente in empresa.deudores_perfil_pct
    }
    assert {k for k in empresa.modos if k.startswith("acreedores.")} == {
        f"acreedores.{componente}" for componente in empresa.acreedores_perfil_pct
    }

    vistos_atipico = 0
    for semilla in range(30):
        e = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO_2023, semilla=semilla, catalogo=catalogo)
        vistos_atipico += sum(
            1 for k, v in e.modos.items() if k.startswith(("deudores.", "acreedores.")) and v == "atipico"
        )
    assert vistos_atipico > 0
