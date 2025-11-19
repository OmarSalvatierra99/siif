"""
Funciones auxiliares generales
"""
import re
import pandas as pd
from typing import Union


def normalize_string(s: Union[str, None]) -> str:
    """
    Normaliza strings para comparación

    Args:
        s: String a normalizar

    Returns:
        String normalizado en minúsculas, sin acentos y espacios normalizados
    """
    s = str(s or "").strip().lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ü": "u", "ñ": "n"
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    s = re.sub(r"\s+", " ", s)
    return s


def to_numeric_fast(series: pd.Series) -> pd.Series:
    """
    Convierte una serie de pandas a numérico de forma rápida

    Args:
        series: Serie de pandas a convertir

    Returns:
        Serie convertida a numérico con valores inválidos reemplazados por 0
    """
    return pd.to_numeric(
        series.astype(str).str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce"
    ).fillna(0.0)


def format_currency(value: float) -> str:
    """
    Formatea un valor como moneda

    Args:
        value: Valor numérico

    Returns:
        String formateado como moneda (ej: "$1,234.56")
    """
    return f"${value:,.2f}"


def safe_float(value, default=0.0):
    """
    Convierte un valor a float de forma segura

    Args:
        value: Valor a convertir
        default: Valor por defecto si la conversión falla

    Returns:
        Float o valor por defecto
    """
    try:
        if value is None or value == '' or pd.isna(value):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default
