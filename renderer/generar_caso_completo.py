import sys
import warnings
from pathlib import Path

_RENDERER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RENDERER_DIR.parent))  # raíz del repo, para motor.*
sys.path.insert(0, str(_RENDERER_DIR))  # renderer/, para los módulos hermanos (tipos, mapeo_*, render_pdf)

from motor.arquetipos import cargar_arquetipos
from motor.catalogo import cargar_y_validar_catalogo
from motor.memoria import generar_caso_combinado
from motor.efe import generar_efe
from motor.ecpn import generar_ecpn, generar_eigr
from motor.clasificacion_legal import estimar_ventas_por_empleado, estimar_plantilla

from clasificacion import clasificar_caso
from mapeo_balance import mapear_balance_activo, mapear_balance_pn_pasivo
from mapeo_pyg import mapear_pyg
from mapeo_efe import mapear_efe
from mapeo_ecpn import mapear_eigr, mapear_ecpn_documento_b
from mapeo_memoria import generar_memoria
from invariantes import InvarianteSubtotalWarning, verificar_invariantes_lineas
from render_pdf import construir_tabla_estado, construir_ecpn_documento_b, generar_pdf

SECTOR_NOMBRES = {"28": "Fabricación de maquinaria y equipo"}


def _verificar_invariantes_o_avisar(bloques_balance_pyg, sector, segmento, semilla, estricto):
    """Guarda de invariantes "sub-líneas == subtotal" (#106, movida a `renderer/invariantes.py`
    en #110) — un caso con violación NO es necesariamente un error de cálculo (ver
    decisiones_plausibilidad.md #109: el plug de cuadre puede vaciar `otras_deudas_corto` cuando
    aloja una provisión a corto, dejando "II Provisiones a corto plazo" sin sitio en su propio
    subtotal — el motor no se toca, es un límite ya documentado), pero no debe generarse en
    SILENCIO. Con `estricto=True` se convierte en excepción; por defecto, solo avisa (el PDF se
    genera igual)."""
    violaciones = verificar_invariantes_lineas(bloques_balance_pyg)
    if not violaciones:
        return
    lineas_aviso = [
        f"  - {v.bloque} / {v.codigo} {v.etiqueta} / ejercicio {v.año}: "
        f"suma sub-líneas {v.suma:,.2f}€ != subtotal {v.subtotal:,.2f}€ "
        f"(diferencia {v.diferencia:,.2f}€)"
        for v in violaciones
    ]
    mensaje = (
        f"Sub-líneas que no suman su subtotal en {sector}/{segmento}/sem{semilla}:\n"
        + "\n".join(lineas_aviso)
    )
    if estricto:
        raise InvarianteSubtotalWarning(mensaje)
    print(f"AVISO: {mensaje}")
    warnings.warn(mensaje, InvarianteSubtotalWarning, stacklevel=2)


def generar_caso_completo(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades,
                           nombre_empresa, ruta_salida, estricto: bool = False):
    catalogo = cargar_y_validar_catalogo()
    arquetipos = cargar_arquetipos()
    evolucion = generar_caso_combinado(sector, segmento, ventas_objetivo, semilla, arquetipos_intensidades,
                                        catalogo=catalogo, arquetipos=arquetipos)
    ejercicios = evolucion.ejercicios
    modelo = clasificar_caso(evolucion, sector, segmento, catalogo)
    obligatorio = modelo == "normal"

    for año in (2023, 2024, 2025):
        ej = ejercicios[año]
        activo = ej.balance_eur["activo_no_corriente"] + ej.balance_eur["activo_corriente"]
        pn_pasivo = ej.balance_eur["patrimonio_neto"] + ej.balance_eur["pasivo_no_corriente"] + ej.balance_eur["pasivo_corriente"]
        assert abs(activo - pn_pasivo) < 1.0, f"Balance {año} no cuadra"

    efes = {2024: generar_efe(ejercicios[2023], ejercicios[2024], obligatorio),
            2025: generar_efe(ejercicios[2024], ejercicios[2025], obligatorio)}
    for año, efe in efes.items():
        assert efe.cuadra, f"EFE {año} no cuadra"
    ecpns = {2024: generar_ecpn(ejercicios[2023], ejercicios[2024], obligatorio),
             2025: generar_ecpn(ejercicios[2024], ejercicios[2025], obligatorio)}
    eigrs = {2024: generar_eigr(ejercicios[2024], obligatorio), 2025: generar_eigr(ejercicios[2025], obligatorio)}

    v_emp, _ = estimar_ventas_por_empleado(sector, segmento, 1, catalogo)
    plantilla_estimada = estimar_plantilla(ejercicios[2025].ventas, v_emp)

    columnas_3, etq_3 = [2023, 2024, 2025], ["2023", "2024", "2025"]
    columnas_2, etq_2 = [2024, 2025], ["2024", "2025"]

    lineas_balance_activo = mapear_balance_activo(ejercicios, modelo)
    lineas_balance_pn_pasivo = mapear_balance_pn_pasivo(ejercicios, modelo)
    lineas_pyg = mapear_pyg(ejercicios, modelo)

    # Guarda de invariantes (#110, ver decisiones_plausibilidad.md #109/#110): comprobación PURA
    # sobre las líneas YA construidas del Balance/PyG — nunca cambia su contenido ni el del PDF,
    # solo avisa (o, con estricto=True, lanza excepción) si alguna no cuadra con su subtotal.
    _verificar_invariantes_o_avisar(
        (
            ("Balance — Activo", lineas_balance_activo, 0),
            ("Balance — Patrimonio Neto y Pasivo", lineas_balance_pn_pasivo, 0),
            ("Cuenta de Pérdidas y Ganancias", lineas_pyg, 2),
        ),
        sector, segmento, semilla, estricto,
    )

    secciones = []
    secciones.append(construir_tabla_estado("Balance — Activo", f"Modelo {modelo.capitalize()} · Importes en euros",
                       lineas_balance_activo, columnas_3, etq_3))
    secciones.append(construir_tabla_estado("Balance — Patrimonio Neto y Pasivo", f"Modelo {modelo.capitalize()} · Importes en euros",
                       lineas_balance_pn_pasivo, columnas_3, etq_3))
    secciones.append(construir_tabla_estado("Cuenta de Pérdidas y Ganancias", f"Modelo {modelo.capitalize()} · Importes en euros",
                       lineas_pyg, columnas_3, etq_3))
    nota_no_exigido = " · Incluido con fines didácticos, no exigido en Abreviado" if modelo == "abreviado" else ""
    secciones.append(construir_tabla_estado("Estado de Flujos de Efectivo", f"Modelo {modelo.capitalize()} · Importes en euros{nota_no_exigido}",
                       mapear_efe(efes), columnas_2, etq_2))
    secciones.append(construir_tabla_estado("ECPN — Documento A: Estado de Ingresos y Gastos Reconocidos",
                       f"Modelo {modelo.capitalize()} · Importes en euros{nota_no_exigido}",
                       mapear_eigr(eigrs), columnas_2, etq_2))
    secciones.append(construir_ecpn_documento_b("ECPN — Documento B: Estado Total de Cambios en el Patrimonio Neto",
                       f"Modelo {modelo.capitalize()} · Importes en euros", mapear_ecpn_documento_b(ecpns)))
    secciones.append(generar_memoria(evolucion, ejercicios, modelo, nombre_empresa,
                       SECTOR_NOMBRES.get(sector, f"sector {sector}"), plantilla_estimada))

    generar_pdf(ruta_salida, nombre_empresa, sector, modelo, secciones)
    return modelo


if __name__ == "__main__":
    modelo = generar_caso_completo(
        sector="28", segmento="pequeñas", ventas_objetivo=5_000_000.0, semilla=15,
        arquetipos_intensidades={"aumento_clientes": "fuerte", "dependencia_pocos_clientes": "fuerte"},
        nombre_empresa="Herramientas de Precisión Ibérica, S.L.",
        ruta_salida=str(_RENDERER_DIR / "output" / "caso_completo_con_memoria.pdf"),
    )
    print("Modelo:", modelo)
