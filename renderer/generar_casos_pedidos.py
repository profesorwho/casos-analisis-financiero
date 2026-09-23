import sys
from pathlib import Path

_RENDERER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RENDERER_DIR.parent))  # raíz del repo, para motor.*
sys.path.insert(0, str(_RENDERER_DIR))  # renderer/, para los módulos hermanos (mapeo_*, render_pdf)

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import generar_evolucion_combinada
from motor.efe import generar_efe

from clasificacion import clasificar_caso
from mapeo_balance import mapear_balance_activo, mapear_balance_pn_pasivo
from mapeo_pyg import mapear_pyg
from mapeo_efe import mapear_efe
from render_pdf import construir_tabla_estado, generar_pdf


def generar_caso(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades, dependencia_pocos_clientes_activo,
                  nombre_empresa, ruta_salida, incluir_efe):
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_evolucion_combinada(
        sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades,
        catalogo=catalogo, arquetipos=arquetipos,
        dependencia_pocos_clientes_activo=dependencia_pocos_clientes_activo,
    )
    ejercicios = evolucion.ejercicios
    modelo = clasificar_caso(evolucion, sector, segmento, catalogo)
    obligatorio = modelo == "normal"

    for año in (2023, 2024, 2025):
        ej = ejercicios[año]
        activo = ej.balance_eur["activo_no_corriente"] + ej.balance_eur["activo_corriente"]
        pn_pasivo = ej.balance_eur["patrimonio_neto"] + ej.balance_eur["pasivo_no_corriente"] + ej.balance_eur["pasivo_corriente"]
        assert abs(activo - pn_pasivo) < 1.0, f"Balance {año} no cuadra: activo={activo} pn+pasivo={pn_pasivo}"

    columnas_3 = [2023, 2024, 2025]
    etq_3 = ["2023", "2024", "2025"]

    secciones = []
    secciones.append(construir_tabla_estado("Balance — Activo", f"Modelo {modelo.capitalize()} · Importes en euros",
                       mapear_balance_activo(ejercicios, modelo), columnas_3, etq_3))
    secciones.append(construir_tabla_estado("Balance — Patrimonio Neto y Pasivo", f"Modelo {modelo.capitalize()} · Importes en euros",
                       mapear_balance_pn_pasivo(ejercicios, modelo), columnas_3, etq_3))
    secciones.append(construir_tabla_estado("Cuenta de Pérdidas y Ganancias", f"Modelo {modelo.capitalize()} · Importes en euros",
                       mapear_pyg(ejercicios, modelo), columnas_3, etq_3))

    if incluir_efe:
        efes = {
            2024: generar_efe(ejercicios[2023], ejercicios[2024], obligatorio),
            2025: generar_efe(ejercicios[2024], ejercicios[2025], obligatorio),
        }
        for año, efe in efes.items():
            assert efe.cuadra, f"EFE {año} no cuadra: descuadre {efe.descuadre_eur}"
        columnas_2 = [2024, 2025]
        etq_2 = ["2024", "2025"]
        nota_efe = " · Incluido con fines didácticos, no exigido en Abreviado" if modelo == "abreviado" else ""
        secciones.append(construir_tabla_estado("Estado de Flujos de Efectivo", f"Modelo {modelo.capitalize()} · Importes en euros{nota_efe}",
                           mapear_efe(efes), columnas_2, etq_2))

    generar_pdf(ruta_salida, nombre_empresa, sector, modelo, secciones)
    return modelo


if __name__ == "__main__":
    modelo1 = generar_caso(
        sector="28", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=15,
        arquetipos_intensidades={"aumento_clientes": "fuerte"}, dependencia_pocos_clientes_activo=True,
        nombre_empresa="Herramientas de Precisión Ibérica, S.L.",
        ruta_salida=str(_RENDERER_DIR / "output" / "caso1_empresa_trampa.pdf"),
        incluir_efe=True,
    )
    print("Caso 1 (máquina herramienta, pequeña):", modelo1)

    modelo2 = generar_caso(
        sector="46", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=43,
        arquetipos_intensidades={"aumento_clientes": "fuerte"}, dependencia_pocos_clientes_activo=True,
        nombre_empresa="Distribuciones Comerciales del Norte, S.L.",
        ruta_salida=str(_RENDERER_DIR / "output" / "caso2_comercial_pequeña.pdf"),
        incluir_efe=False,
    )
    print("Caso 2 (comercio al por mayor, pequeña):", modelo2)
