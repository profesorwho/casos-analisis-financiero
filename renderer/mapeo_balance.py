"""Mapeo del Balance (Activo + Patrimonio Neto y Pasivo) a las líneas oficiales del PGC.

3 años (2023-2025), decisión ya tomada (tarea 82). `modelo` es "normal" o "abreviado": el
Abreviado se queda en el nivel de epígrafe romano salvo en Deudores/Acreedores comerciales y
Deudas LP/CP, que sí bajan un nivel (ver modelo_abreviado_pgc.md).
"""
from __future__ import annotations

from tipos import LineaEstado
from notas_memoria import NOTA_POR_LINEA

AÑOS = (2023, 2024, 2025)


def _v(ejercicios, extractor):
    return {año: extractor(ejercicios[año]) for año in AÑOS}


def mapear_balance_activo(ejercicios: dict, modelo: str) -> list[LineaEstado]:
    L = []
    nota = lambda k: NOTA_POR_LINEA.get(k)

    # A) ACTIVO NO CORRIENTE
    L.append(LineaEstado("A", "ACTIVO NO CORRIENTE", 0,
              _v(ejercicios, lambda e: e.balance_eur["activo_no_corriente"]), negrita=True))
    L.append(LineaEstado("I", "Inmovilizado intangible", 1,
              _v(ejercicios, lambda e: e.activo_no_corriente_desglose_eur["intangible"]), nota=nota("activo_no_corriente.intangible")))
    L.append(LineaEstado("II", "Inmovilizado material", 1,
              _v(ejercicios, lambda e: e.activo_no_corriente_desglose_eur["material"]), nota=nota("activo_no_corriente.material")))
    L.append(LineaEstado("III", "Inversiones inmobiliarias", 1,
              _v(ejercicios, lambda e: e.activo_no_corriente_desglose_eur["inversiones_inmobiliarias"]), nota=nota("activo_no_corriente.inversiones_inmobiliarias")))
    L.append(LineaEstado("IV", "Inversiones en empresas del grupo y asociadas a largo plazo", 1,
              _v(ejercicios, lambda e: e.inversion_grupo_largo_eur), nota=nota("activo_no_corriente.inversion_grupo_largo")))
    L.append(LineaEstado("V", "Inversiones financieras a largo plazo", 1,
              _v(ejercicios, lambda e: (
                  e.activo_no_corriente_desglose_eur["otros_financieros"]
                  + max(0.0, e.cobertura_valor_swap_eur)
              )), nota=nota("activo_no_corriente.otros_financieros")))
    L.append(LineaEstado("VI", "Activos por impuesto diferido", 1,
              _v(ejercicios, lambda e: e.activos_por_impuesto_diferido_eur)))

    # B) ACTIVO CORRIENTE
    L.append(LineaEstado("B", "ACTIVO CORRIENTE", 0,
              _v(ejercicios, lambda e: e.balance_eur["activo_corriente"]), negrita=True))
    if modelo == "normal":
        # El motor no modela activos no corrientes mantenidos para la venta — se muestra a 0,
        # misma convención que "IV Inversiones en empresas del grupo... a largo plazo" (activo
        # no corriente) cuando el arquetipo 20 no está activo (#106.5).
        L.append(LineaEstado("I", "Activos no corrientes mantenidos para la venta", 1, _v(ejercicios, lambda e: 0.0)))
    L.append(LineaEstado("II", "Existencias", 1,
              _v(ejercicios, lambda e: e.balance_eur["existencias"]), negrita=(modelo == "normal")))
    if modelo == "normal":
        etiquetas_exist = {
            "comerciales": "Comerciales", "materias_primas": "Materias primas y otros aprovisionamientos",
            "productos_curso": "Productos en curso", "productos_terminados": "Productos terminados",
            "subproductos_residuos": "Subproductos, residuos y materiales recuperados",
            "anticipos_proveedores": "Anticipos a proveedores",
        }
        for i, (clave, etq) in enumerate(etiquetas_exist.items(), start=1):
            L.append(LineaEstado(str(i), etq, 2, _v(ejercicios, lambda e, c=clave: e.existencias_desglose_eur.get(c, 0.0))))

    L.append(LineaEstado("III", "Deudores comerciales y otras cuentas a cobrar", 1,
              _v(ejercicios, lambda e: e.balance_eur["realizable"] - e.periodificacion_activo_eur), negrita=True))
    etiquetas_deud = {
        "clientes": "Clientes por ventas y prestaciones de servicios",
        "clientes_empresas_grupo": "Clientes, empresas del grupo y asociadas",
        "deudores_varios": "Deudores varios", "personal": "Personal",
        "hacienda_publica_deudora": "Activos por impuesto corriente",
        "otros_creditos_aapp": "Otros créditos con las Administraciones Públicas",
        "accionistas_desembolsos_exigidos": "Accionistas (socios) por desembolsos exigidos",
    }
    nivel_deud = 2 if modelo == "normal" else 2
    for i, (clave, etq) in enumerate(etiquetas_deud.items(), start=1):
        L.append(LineaEstado(str(i), etq, nivel_deud,
                  _v(ejercicios, lambda e, c=clave: e.deudores_desglose_eur.get(c, 0.0)),
                  nota=nota("realizable.clientes_empresas_grupo") if clave == "clientes_empresas_grupo" else None))

    if modelo == "normal":
        # El motor solo modela "préstamo a matriz" (arquetipo 20) como Inversiones en empresas
        # del grupo a LARGO plazo (activo no corriente) — no hay masa a corto plazo equivalente
        # ni inversiones financieras a corto plazo fuera de `disponible`; se muestran a 0 (#106.5).
        L.append(LineaEstado("IV", "Inversiones en empresas del grupo y asociadas a corto plazo", 1, _v(ejercicios, lambda e: 0.0)))
        L.append(LineaEstado("V", "Inversiones financieras a corto plazo", 1, _v(ejercicios, lambda e: 0.0)))
    L.append(LineaEstado("VI", "Periodificaciones a corto plazo", 1,
              _v(ejercicios, lambda e: e.periodificacion_activo_eur)))
    L.append(LineaEstado("VII", "Efectivo y otros activos líquidos equivalentes", 1,
              _v(ejercicios, lambda e: e.balance_eur["disponible"]), negrita=True))

    L.append(LineaEstado("", "TOTAL ACTIVO (A + B)", 0,
              _v(ejercicios, lambda e: e.balance_eur["activo_no_corriente"] + e.balance_eur["activo_corriente"]),
              negrita=True))
    return L


def mapear_balance_pn_pasivo(ejercicios: dict, modelo: str) -> list[LineaEstado]:
    L = []
    nota = lambda k: NOTA_POR_LINEA.get(k)

    # A) PATRIMONIO NETO
    L.append(LineaEstado("A", "PATRIMONIO NETO", 0,
              _v(ejercicios, lambda e: e.balance_eur["patrimonio_neto"]), negrita=True))
    L.append(LineaEstado("A-1", "Fondos propios", 1,
              _v(ejercicios, lambda e: e.capital_social_eur + e.reservas_eur + e.pyg_eur["resultado_ejercicio"]),
              negrita=True))
    L.append(LineaEstado("I", "Capital", 2, _v(ejercicios, lambda e: e.capital_social_eur), nota=nota("pn.capital")))
    L.append(LineaEstado("III", "Reservas", 2, _v(ejercicios, lambda e: e.reservas_eur), nota=nota("pn.reservas")))
    L.append(LineaEstado("VII", "Resultado del ejercicio", 2,
              _v(ejercicios, lambda e: e.pyg_eur["resultado_ejercicio"]), nota=nota("pn.resultado_ejercicio")))
    L.append(LineaEstado("A-2", "Ajustes por cambios de valor", 1,
              _v(ejercicios, lambda e: e.ajustes_cambio_valor_pn_eur)))
    L.append(LineaEstado("A-3", "Subvenciones, donaciones y legados recibidos", 1,
              _v(ejercicios, lambda e: e.subvenciones_pn_eur)))

    # B) PASIVO NO CORRIENTE
    L.append(LineaEstado("B", "PASIVO NO CORRIENTE", 0,
              _v(ejercicios, lambda e: e.balance_eur["pasivo_no_corriente"]), negrita=True))
    L.append(LineaEstado("I", "Provisiones a largo plazo", 1,
              _v(ejercicios, lambda e: e.provision_saldo_largo_eur), nota=nota("pasivo_no_corriente.provisiones_largo")))
    L.append(LineaEstado("II", "Deudas a largo plazo", 1,
              _v(ejercicios, lambda e: e.balance_eur["deudas_fin_largo"]), negrita=True,
              nota=nota("pasivo_no_corriente.deudas_fin_largo")))
    if modelo == "normal":
        etq_dfin = {"entidades_credito": "Deudas con entidades de crédito",
                    "obligaciones": "Obligaciones y otros valores negociables",
                    "arrendamiento_financiero": "Acreedores por arrendamiento financiero",
                    "derivados": "Derivados", "otros_pasivos_financieros": "Otros pasivos financieros"}
        for i, (clave, etq) in enumerate(etq_dfin.items(), start=1):
            L.append(LineaEstado(str(i), etq, 2, _v(ejercicios, lambda e, c=clave: e.deudas_fin_largo_desglose_eur.get(c, 0.0))))
    L.append(LineaEstado("III", "Deudas con empresas del grupo y asociadas a largo plazo", 1,
              _v(ejercicios, lambda e: e.deuda_grupo_largo_eur), nota=nota("pasivo_no_corriente.deuda_grupo_largo")))
    L.append(LineaEstado("IV", "Pasivos por impuesto diferido", 1,
              _v(ejercicios, lambda e: e.pasivos_por_impuesto_diferido_eur), nota=nota("pasivo_no_corriente.impuesto_diferido")))
    L.append(LineaEstado("V", "Periodificaciones a largo plazo", 1,
              _v(ejercicios, lambda e: e.periodificacion_pasivo_largo_eur)))
    L.append(LineaEstado("VI", "Otras deudas a largo plazo", 1,
              _v(ejercicios, lambda e: (
                  e.otras_deudas_largo_desglose_eur.get("acreedores_inmovilizado", 0.0)
                  + e.otras_deudas_largo_desglose_eur.get("fianzas_depositos", 0.0)
                  + e.otras_deudas_largo_desglose_eur.get("deudas_socios", 0.0)
                  + e.otras_deudas_largo_desglose_eur.get("remanente", 0.0)
              )), negrita=True))
    if modelo == "normal":
        etq_od_largo = {"acreedores_inmovilizado": "Acreedores por adquisición de inmovilizado a largo plazo",
                         "fianzas_depositos": "Fianzas y depósitos recibidos a largo plazo",
                         "deudas_socios": "Deudas con socios y administradores a largo plazo",
                         "remanente": "Otras deudas a largo plazo"}
        for i, (clave, etq) in enumerate(etq_od_largo.items(), start=1):
            L.append(LineaEstado(str(i), etq, 2, _v(ejercicios, lambda e, c=clave: e.otras_deudas_largo_desglose_eur.get(c, 0.0))))

    # C) PASIVO CORRIENTE
    L.append(LineaEstado("C", "PASIVO CORRIENTE", 0,
              _v(ejercicios, lambda e: e.balance_eur["pasivo_corriente"]), negrita=True))
    L.append(LineaEstado("II", "Provisiones a corto plazo", 1,
              _v(ejercicios, lambda e: e.provision_saldo_corto_eur), nota=nota("pasivo_corriente.provisiones_corto")))
    L.append(LineaEstado("III", "Deudas a corto plazo", 1,
              _v(ejercicios, lambda e: e.balance_eur["deudas_fin_corto"]), negrita=True,
              nota=nota("pasivo_corriente.deudas_fin_corto")))
    if modelo == "normal":
        for i, (clave, etq) in enumerate(etq_dfin.items(), start=1):
            L.append(LineaEstado(str(i), etq, 2, _v(ejercicios, lambda e, c=clave: e.deudas_fin_corto_desglose_eur.get(c, 0.0))))
        # El motor solo modela "financiación recibida de grupo" (arquetipo 20) como deuda a
        # LARGO plazo — no hay masa a corto plazo equivalente; se muestra a 0, misma convención
        # que "III Deudas con empresas del grupo... a largo plazo" cuando no está activa (#106.5).
        L.append(LineaEstado("IV", "Deudas con empresas del grupo y asociadas a corto plazo", 1,
                  _v(ejercicios, lambda e: 0.0), nota=nota("pasivo_corriente.deuda_grupo_corto")))
    L.append(LineaEstado("V", "Acreedores comerciales y otras cuentas a pagar", 1,
              _v(ejercicios, lambda e: e.balance_eur["acreedores_comerciales"]), negrita=True))
    etq_acree = {"proveedores": "Proveedores", "proveedores_empresas_grupo": "Proveedores, empresas del grupo",
                 "acreedores_varios": "Acreedores varios", "personal": "Personal",
                 "hacienda_publica_acreedora": "Pasivos por impuesto corriente",
                 "otras_deudas_aapp": "Otras deudas con las Administraciones Públicas",
                 "anticipos_clientes": "Anticipos de clientes"}
    for i, (clave, etq) in enumerate(etq_acree.items(), start=1):
        L.append(LineaEstado(str(i), etq, 2, _v(ejercicios, lambda e, c=clave: e.acreedores_desglose_eur.get(c, 0.0))))
    L.append(LineaEstado("VI", "Periodificaciones a corto plazo", 1,
              _v(ejercicios, lambda e: e.periodificacion_pasivo_corto_eur)))
    L.append(LineaEstado("VII", "Otras deudas a corto plazo", 1,
              _v(ejercicios, lambda e: (
                  e.otras_deudas_corto_desglose_eur.get("acreedores_inmovilizado", 0.0)
                  + e.otras_deudas_corto_desglose_eur.get("fianzas_depositos", 0.0)
                  + e.otras_deudas_corto_desglose_eur.get("aapp_pendiente", 0.0)
                  + e.otras_deudas_corto_desglose_eur.get("remanente", 0.0)
              )), negrita=True))
    if modelo == "normal":
        etq_od_corto = {"acreedores_inmovilizado": "Acreedores por adquisición de inmovilizado a corto plazo",
                         "fianzas_depositos": "Fianzas y depósitos recibidos a corto plazo",
                         "aapp_pendiente": "Deudas pendientes con las Administraciones Públicas",
                         "remanente": "Otras deudas a corto plazo"}
        for i, (clave, etq) in enumerate(etq_od_corto.items(), start=1):
            L.append(LineaEstado(str(i), etq, 2, _v(ejercicios, lambda e, c=clave: e.otras_deudas_corto_desglose_eur.get(c, 0.0))))

    L.append(LineaEstado("", "TOTAL PATRIMONIO NETO Y PASIVO (A + B + C)", 0,
              _v(ejercicios, lambda e: (
                  e.balance_eur["patrimonio_neto"] + e.balance_eur["pasivo_no_corriente"] + e.balance_eur["pasivo_corriente"]
              )), negrita=True))
    return L
