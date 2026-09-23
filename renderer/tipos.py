"""Tipo de línea compartido por los 4 mapeos (Balance, PyG, EFE, ECPN)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LineaEstado:
    codigo: str          # "A", "I", "1", "a)" — como aparece en el modelo oficial
    etiqueta: str
    nivel: int            # 0=letra mayúscula, 1=número romano, 2=número arábigo, 3=letra minúscula
    valores: dict         # clave de periodo (año int, o "2024"/"2025" str para EFE/ECPN) -> float
    negrita: bool = False  # subtotal / total
    nota: int | None = None
    solo_normal: bool = False   # si True, se omite por completo en Abreviado
    es_signo_flexible: bool = False  # EFE/ECPN: True si el signo (+/-) se muestra explícito
