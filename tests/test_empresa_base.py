import pytest

from motor.catalogo import cargar_y_validar_catalogo
from motor.empresa_base import (
    MASAS_BALANCE,
    PRIMITIVAS_PYG_NO_NEGATIVAS,
    EmpresaBaseError,
    generar_empresa_base,
)

TOLERANCIA = 1e-6

# Un sector industrial, uno de servicios y uno de comercio del catálogo de 27 sectores.
SECTORES_A_PROBAR = [
    pytest.param("24.1", id="industrial-siderurgia"),
    pytest.param("62", id="servicios-tic"),
    pytest.param("47.1", id="comercio-supermercados"),
]

N_EMPRESAS = 20
VENTAS_OBJETIVO = 8_000_000.0


@pytest.fixture(scope="module")
def catalogo():
    return cargar_y_validar_catalogo()


def _generar_lote(catalogo, sector, segmento="grandes_medianas", n=N_EMPRESAS):
    return [
        generar_empresa_base(sector, segmento, VENTAS_OBJETIVO, semilla=i, catalogo=catalogo)
        for i in range(n)
    ]


@pytest.mark.parametrize("sector", SECTORES_A_PROBAR)
def test_balance_cuadra_siempre(catalogo, sector):
    for empresa in _generar_lote(catalogo, sector):
        activo_eur = empresa.balance_eur["activo_no_corriente"] + empresa.balance_eur["activo_corriente"]
        pn_pasivo_eur = (
            empresa.balance_eur["patrimonio_neto"]
            + empresa.balance_eur["pasivo_no_corriente"]
            + empresa.balance_eur["pasivo_corriente"]
        )
        assert abs(activo_eur - pn_pasivo_eur) <= 0.01, f"semilla {empresa.semilla}: descuadre de balance"


@pytest.mark.parametrize("sector", SECTORES_A_PROBAR)
def test_bloques_de_balance_suman_correctamente(catalogo, sector):
    for empresa in _generar_lote(catalogo, sector):
        pct = empresa.balance_pct
        assert pct["activo_no_corriente"] + pct["activo_corriente"] == pytest.approx(100.0, abs=TOLERANCIA)
        assert pct["patrimonio_neto"] + pct["pasivo_no_corriente"] + pct["pasivo_corriente"] == pytest.approx(
            100.0, abs=TOLERANCIA
        )
        assert pct["existencias"] + pct["realizable"] + pct["disponible"] == pytest.approx(
            pct["activo_corriente"], abs=TOLERANCIA
        )
        assert pct["deudas_fin_largo"] + pct["otras_deudas_largo"] == pytest.approx(
            pct["pasivo_no_corriente"], abs=TOLERANCIA
        )
        assert pct["acreedores_comerciales"] + pct["deudas_fin_corto"] + pct["otras_deudas_corto"] == pytest.approx(
            pct["pasivo_corriente"], abs=TOLERANCIA
        )


@pytest.mark.parametrize("sector", SECTORES_A_PROBAR)
def test_cascada_pyg_consistente_con_formula(catalogo, sector):
    for empresa in _generar_lote(catalogo, sector):
        eur = empresa.pyg_eur
        assert eur["ingresos_explotacion"] == pytest.approx(
            eur["cifra_negocios"] + eur["otros_ingresos_explot"], abs=0.01
        )
        assert eur["margen_bruto"] == pytest.approx(
            eur["ingresos_explotacion"] - eur["consumos_explotacion"], abs=0.01
        )
        assert eur["valor_añadido"] == pytest.approx(eur["margen_bruto"] - eur["otros_gastos_explot"], abs=0.01)
        assert eur["baii"] == pytest.approx(
            eur["valor_añadido"] - eur["gastos_personal"] - eur["amortizaciones"] + eur["resultado_extraordinario"],
            abs=0.01,
        )
        assert eur["bai"] == pytest.approx(
            eur["baii"] + eur["ingresos_financieros"] - eur["gastos_financieros"], abs=0.01
        )
        assert eur["resultado_ejercicio"] == pytest.approx(eur["bai"] - eur["impuesto_beneficios"], abs=0.01)
        assert eur["cifra_negocios"] == pytest.approx(VENTAS_OBJETIVO, abs=0.01)


@pytest.mark.parametrize("sector", SECTORES_A_PROBAR)
def test_hay_variabilidad_real_entre_empresas(catalogo, sector):
    empresas = _generar_lote(catalogo, sector)
    huellas = {
        (round(e.activo_total_eur, 4), round(e.balance_pct["existencias"], 6), round(e.pyg_eur["resultado_ejercicio"], 4))
        for e in empresas
    }
    assert len(huellas) == N_EMPRESAS, "hay empresas generadas con cifras idénticas entre sí"


@pytest.mark.parametrize("sector", SECTORES_A_PROBAR)
def test_aparece_al_menos_un_modo_atipico(catalogo, sector):
    empresas = _generar_lote(catalogo, sector)
    algun_atipico = any(modo == "atipico" for e in empresas for modo in e.modos.values())
    assert algun_atipico, "ninguna de las 20 empresas generó ninguna partida en modo atípico"


@pytest.mark.parametrize("sector", SECTORES_A_PROBAR)
def test_sin_valores_absurdos(catalogo, sector):
    for empresa in _generar_lote(catalogo, sector):
        for nombre in MASAS_BALANCE:
            valor = empresa.balance_pct[nombre]
            assert 0.0 <= valor <= 100.0, f"{nombre} fuera de 0-100%: {valor}"
            assert empresa.balance_eur[nombre] >= 0.0, f"{nombre} en euros es negativo"

        for nombre in PRIMITIVAS_PYG_NO_NEGATIVAS:
            assert empresa.pyg_eur[nombre] >= 0.0, f"{nombre} en euros es negativo"

        assert empresa.pyg_eur["ingresos_explotacion"] >= 0.0
        assert empresa.activo_total_eur > 0.0
        assert empresa.rotacion_activo > 0.0


def test_reproducibilidad_misma_semilla(catalogo):
    a = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO, semilla=42, catalogo=catalogo)
    b = generar_empresa_base("24.1", "grandes_medianas", VENTAS_OBJETIVO, semilla=42, catalogo=catalogo)
    assert a.balance_pct == b.balance_pct
    assert a.pyg_eur == b.pyg_eur
    assert a.modos == b.modos


def test_segmento_pequeñas_tambien_funciona(catalogo):
    empresa = generar_empresa_base("47.1", "pequeñas", 1_500_000.0, semilla=7, catalogo=catalogo)
    activo_eur = empresa.balance_eur["activo_no_corriente"] + empresa.balance_eur["activo_corriente"]
    pn_pasivo_eur = (
        empresa.balance_eur["patrimonio_neto"]
        + empresa.balance_eur["pasivo_no_corriente"]
        + empresa.balance_eur["pasivo_corriente"]
    )
    assert abs(activo_eur - pn_pasivo_eur) <= 0.01


def test_segmento_invalido_lanza_error(catalogo):
    with pytest.raises(EmpresaBaseError, match="Segmento"):
        generar_empresa_base("24.1", "mediana", VENTAS_OBJETIVO, semilla=1, catalogo=catalogo)


def test_sector_desconocido_lanza_error(catalogo):
    with pytest.raises(EmpresaBaseError, match="no reconocido"):
        generar_empresa_base("99.9", "grandes_medianas", VENTAS_OBJETIVO, semilla=1, catalogo=catalogo)


def test_ventas_objetivo_no_positivas_lanza_error(catalogo):
    with pytest.raises(EmpresaBaseError, match="ventas_objetivo"):
        generar_empresa_base("24.1", "grandes_medianas", 0, semilla=1, catalogo=catalogo)
