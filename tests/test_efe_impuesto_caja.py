"""#118 — EFE A.4.d en caja real: pago de impuesto = devengado − Δ Hacienda acreedora + Δ deudora;
la reclasificación sale de a3d/a3b sin cambiar la suma ni A.5/e."""
from __future__ import annotations

import pytest

from motor.efe import generar_efe
from motor.memoria import generar_caso_combinado

CASOS = [
    ("46", "pequeñas", 5e6, 1447, {"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "moderado", "informacion_relevante_memoria": "leve"}),
    ("28", "grandes_medianas", 28e6, 238, {"crecimiento_destruccion_caja": "leve", "dependencia_pocos_clientes": "moderado", "coberturas": "moderado", "operaciones_vinculadas": "moderado"}),
]


@pytest.mark.parametrize("caso", CASOS)
def test_a4d_es_pago_real_y_la_suma_a3b_a3d_a4d_no_cambia(caso):
    e = generar_caso_combinado(*caso)
    for año in (2024, 2025):
        ant, act = e.ejercicios[año - 1], e.ejercicios[año]
        f = generar_efe(ant, act, True)
        assert f.cuadra
        d_acr = act.acreedores_desglose_eur.get("hacienda_publica_acreedora", 0.0) - ant.acreedores_desglose_eur.get("hacienda_publica_acreedora", 0.0)
        d_deu = act.deudores_desglose_eur.get("hacienda_publica_deudora", 0.0) - ant.deudores_desglose_eur.get("hacienda_publica_deudora", 0.0)
        assert f.a4d_impuesto_beneficios == pytest.approx(-act.pyg_eur["impuesto_beneficios"] + d_acr - d_deu, abs=0.01)
        a3b_o = -(act.balance_eur["realizable"] - ant.balance_eur["realizable"])
        a3d_o = act.balance_eur["acreedores_comerciales"] - ant.balance_eur["acreedores_comerciales"]
        suma_antigua = a3b_o + a3d_o - act.pyg_eur["impuesto_beneficios"]
        assert f.a3b_deudores + f.a3d_acreedores + f.a4d_impuesto_beneficios == pytest.approx(suma_antigua, abs=0.01)
        assert f.e_variacion_neta_efectivo == pytest.approx(act.balance_eur["disponible"] - ant.balance_eur["disponible"], abs=0.01)
        # coherencia con la Nota 9: pago real = pagos a cuenta del ejercicio + saldo acreedor anterior
        pagos_a_cuenta = act.pyg_eur["impuesto_beneficios"] - act.acreedores_desglose_eur.get("hacienda_publica_acreedora", 0.0) + act.deudores_desglose_eur.get("hacienda_publica_deudora", 0.0)
        assert -f.a4d_impuesto_beneficios == pytest.approx(
            pagos_a_cuenta + ant.acreedores_desglose_eur.get("hacienda_publica_acreedora", 0.0) - ant.deudores_desglose_eur.get("hacienda_publica_deudora", 0.0), abs=0.01)


def test_valores_de_referencia_caso_a_2024():
    e = generar_caso_combinado(*CASOS[0])
    f = generar_efe(e.ejercicios[2023], e.ejercicios[2024], False)
    assert f.a4d_impuesto_beneficios == pytest.approx(-29808.51, abs=0.01)
    assert f.a3d_acreedores == pytest.approx(-3317.96, abs=0.01)
