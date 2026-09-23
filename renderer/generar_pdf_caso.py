import sys
from pathlib import Path

_RENDERER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RENDERER_DIR.parent))  # raíz del repo, para motor.*
sys.path.insert(0, str(_RENDERER_DIR))  # renderer/, para los módulos hermanos (mapeo_*, render_pdf)

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.evolucion_arquetipo import generar_evolucion_arquetipo
from motor.efe import generar_efe
from motor.ecpn import generar_ecpn, generar_eigr

from clasificacion import clasificar_caso
from mapeo_balance import mapear_balance_activo, mapear_balance_pn_pasivo
from mapeo_pyg import mapear_pyg
from mapeo_efe import mapear_efe
from mapeo_ecpn import mapear_eigr, mapear_ecpn_documento_b
from render_pdf import construir_tabla_estado, construir_ecpn_documento_b, generar_pdf


def generar_caso_pdf(sector, segmento, ventas_objetivo, semilla, intensidad, arquetipo_id, nombre_empresa, ruta_salida):
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_evolucion_arquetipo(
        sector, segmento, ventas_objetivo, semilla=semilla, intensidad=intensidad,
        arquetipo_id=arquetipo_id, catalogo=catalogo, arquetipos=arquetipos,
    )
    ejercicios = evolucion.ejercicios
    modelo = clasificar_caso(evolucion, sector, segmento, catalogo)
    obligatorio = modelo == "normal"

    efes = {
        2024: generar_efe(ejercicios[2023], ejercicios[2024], obligatorio),
        2025: generar_efe(ejercicios[2024], ejercicios[2025], obligatorio),
    }
    ecpns = {
        2024: generar_ecpn(ejercicios[2023], ejercicios[2024], obligatorio),
        2025: generar_ecpn(ejercicios[2024], ejercicios[2025], obligatorio),
    }
    eigrs = {
        2024: generar_eigr(ejercicios[2024], obligatorio),
        2025: generar_eigr(ejercicios[2025], obligatorio),
    }

    # --- verificaciones de cuadre antes de renderizar, no después ---
    for año, efe in efes.items():
        assert efe.cuadra, f"EFE {año} no cuadra: descuadre {efe.descuadre_eur}"
    for año, ecpn in ecpns.items():
        assert ecpn.cuadra, f"ECPN {año} no cuadra: descuadre {ecpn.descuadre_eur}"
    for año in (2023, 2024, 2025):
        ej = ejercicios[año]
        activo = ej.balance_eur["activo_no_corriente"] + ej.balance_eur["activo_corriente"]
        pn_pasivo = ej.balance_eur["patrimonio_neto"] + ej.balance_eur["pasivo_no_corriente"] + ej.balance_eur["pasivo_corriente"]
        assert abs(activo - pn_pasivo) < 1.0, f"Balance {año} no cuadra: activo={activo} pn+pasivo={pn_pasivo}"

    lineas_balance_activo = mapear_balance_activo(ejercicios, modelo)
    lineas_balance_pasivo = mapear_balance_pn_pasivo(ejercicios, modelo)
    lineas_pyg = mapear_pyg(ejercicios, modelo)
    lineas_efe = mapear_efe(efes)
    lineas_eigr = mapear_eigr(eigrs)
    tabla_ecpn_b = mapear_ecpn_documento_b(ecpns)

    columnas_3 = [2023, 2024, 2025]
    etq_3 = ["2023", "2024", "2025"]
    columnas_2 = [2024, 2025]
    etq_2 = ["2024", "2025"]

    secciones = []
    secciones.append(construir_tabla_estado("Balance — Activo", f"Modelo {modelo.capitalize()} · Importes en euros",
                       lineas_balance_activo, columnas_3, etq_3))
    secciones.append(construir_tabla_estado("Balance — Patrimonio Neto y Pasivo", f"Modelo {modelo.capitalize()} · Importes en euros",
                       lineas_balance_pasivo, columnas_3, etq_3))
    secciones.append(construir_tabla_estado("Cuenta de Pérdidas y Ganancias", f"Modelo {modelo.capitalize()} · Importes en euros",
                       lineas_pyg, columnas_3, etq_3))
    secciones.append(construir_tabla_estado("Estado de Flujos de Efectivo", f"Modelo {modelo.capitalize()} · Importes en euros" +
                       (" · Incluido con fines didácticos, no exigido en Abreviado" if modelo == "abreviado" else ""),
                       lineas_efe, columnas_2, etq_2))
    secciones.append(construir_tabla_estado("ECPN — Documento A: Estado de Ingresos y Gastos Reconocidos",
                       f"Modelo {modelo.capitalize()} · Importes en euros" +
                       (" · Incluido con fines didácticos, no exigido en Abreviado" if modelo == "abreviado" else ""),
                       lineas_eigr, columnas_2, etq_2))
    secciones.append(construir_ecpn_documento_b("ECPN — Documento B: Estado Total de Cambios en el Patrimonio Neto",
                       f"Modelo {modelo.capitalize()} · Importes en euros", tabla_ecpn_b))

    generar_pdf(ruta_salida, nombre_empresa, sector, modelo, secciones)
    return modelo


if __name__ == "__main__":
    modelo = generar_caso_pdf(
        sector="24.1", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=1,
        intensidad="fuerte", arquetipo_id="aumento_clientes",
        nombre_empresa="Ejemplo Abreviado, S.L.",
        ruta_salida=str(_RENDERER_DIR / "output" / "caso_abreviado_ejemplo.pdf"),
    )
    print("Caso 1 (pequeñas):", modelo)

    modelo2 = generar_caso_pdf(
        sector="24.1", segmento="grandes_medianas", ventas_objetivo=15_000_000.0, semilla=2,
        intensidad="fuerte", arquetipo_id="operaciones_vinculadas",
        nombre_empresa="Ejemplo Normal, S.A.",
        ruta_salida=str(_RENDERER_DIR / "output" / "caso_normal_ejemplo.pdf"),
    )
    print("Caso 2 (grandes_medianas):", modelo2)
