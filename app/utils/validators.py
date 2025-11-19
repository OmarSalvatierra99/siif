"""
Validadores de datos
"""
import os
import re
from typing import Tuple, Optional


def validate_file_extension(filename: str, allowed_extensions: set) -> Tuple[bool, Optional[str]]:
    """
    Valida la extensión de un archivo

    Args:
        filename: Nombre del archivo
        allowed_extensions: Set de extensiones permitidas (ej: {'.xlsx', '.xls'})

    Returns:
        Tupla (es_válido, mensaje_error)
    """
    if not filename:
        return False, "Nombre de archivo vacío"

    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_extensions:
        return False, f"Extensión {ext} no permitida. Use: {', '.join(allowed_extensions)}"

    return True, None


def validate_cuenta_contable(cuenta: str) -> Tuple[bool, Optional[str]]:
    """
    Valida el formato de una cuenta contable (21 caracteres)

    Args:
        cuenta: Cuenta contable a validar

    Returns:
        Tupla (es_válida, mensaje_error)
    """
    if not cuenta:
        return False, "Cuenta contable vacía"

    # Limpiar y validar
    cuenta_limpia = re.sub(r"[^0-9A-Z]", "", str(cuenta).strip().upper())

    if len(cuenta_limpia) > 21:
        return False, f"Cuenta contable muy larga ({len(cuenta_limpia)} caracteres, máximo 21)"

    # Validar que sea alfanumérica
    if not cuenta_limpia.replace(" ", "").isalnum():
        return False, "Cuenta contable debe ser alfanumérica"

    return True, None


def validate_date_format(date_str: str) -> Tuple[bool, Optional[str]]:
    """
    Valida el formato de una fecha

    Args:
        date_str: String de fecha a validar

    Returns:
        Tupla (es_válida, mensaje_error)
    """
    if not date_str:
        return False, "Fecha vacía"

    # Patrones comunes de fecha
    patterns = [
        r'^\d{2}/\d{2}/\d{4}$',  # DD/MM/YYYY
        r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
        r'^\d{2}-\d{2}-\d{4}$',  # DD-MM-YYYY
    ]

    for pattern in patterns:
        if re.match(pattern, date_str):
            return True, None

    return False, f"Formato de fecha inválido: {date_str}"


def validate_numeric_range(value: float, min_val: float = None, max_val: float = None) -> Tuple[bool, Optional[str]]:
    """
    Valida que un valor numérico esté en un rango

    Args:
        value: Valor a validar
        min_val: Valor mínimo permitido
        max_val: Valor máximo permitido

    Returns:
        Tupla (es_válido, mensaje_error)
    """
    try:
        val = float(value)
    except (ValueError, TypeError):
        return False, f"Valor no numérico: {value}"

    if min_val is not None and val < min_val:
        return False, f"Valor {val} menor que el mínimo {min_val}"

    if max_val is not None and val > max_val:
        return False, f"Valor {val} mayor que el máximo {max_val}"

    return True, None
