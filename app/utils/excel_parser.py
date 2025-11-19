"""
Utilidades para parseo de Excel y cuentas contables
"""
import re
from typing import Dict


def parse_cuenta_contable(cuenta_str: str) -> Dict[str, str]:
    """
    Divide la cuenta contable de 21 caracteres en sus componentes

    Formato de cuenta contable (21 caracteres):
    - [0]: Género
    - [1]: Grupo
    - [2]: Rubro
    - [3]: Cuenta
    - [4]: Subcuenta
    - [5:7]: Dependencia (2 dígitos)
    - [7:9]: Unidad Responsable (2 dígitos)
    - [9:11]: Centro de Costo (2 dígitos)
    - [11:13]: Proyecto Presupuestario (2 dígitos)
    - [13]: Fuente
    - [14:16]: SubFuente (2 dígitos)
    - [16]: Tipo de Recurso
    - [17:21]: Partida Presupuestal (4 dígitos)

    Args:
        cuenta_str: Cuenta contable como string

    Returns:
        Diccionario con los componentes de la cuenta
    """
    # Normalizar: quitar caracteres no alfanuméricos y convertir a mayúsculas
    s = str(cuenta_str).strip().upper()
    s = re.sub(r"[^0-9A-Z]", "", s)

    # Rellenar con ceros a la derecha si es más corta
    s = s.ljust(21, "0")

    return {
        "genero": s[0],
        "grupo": s[1],
        "rubro": s[2],
        "cuenta": s[3],
        "subcuenta": s[4],
        "dependencia": s[5:7],
        "unidad_responsable": s[7:9],
        "centro_costo": s[9:11],
        "proyecto_presupuestario": s[11:13],
        "fuente": s[13],
        "subfuente": s[14:16],
        "tipo_recurso": s[16],
        "partida_presupuestal": s[17:21],
    }


def detect_header_row(df, max_rows=20):
    """
    Detecta la fila de encabezados en un DataFrame

    Args:
        df: DataFrame de pandas
        max_rows: Número máximo de filas a revisar

    Returns:
        Índice de la fila de encabezados o None si no se encuentra
    """
    for idx in range(min(max_rows, len(df))):
        row_text = " ".join(df.iloc[idx].fillna("").astype(str).str.lower())
        if "fecha" in row_text and ("poliza" in row_text or "saldo" in row_text):
            return idx
    return None


def is_date_like(value) -> bool:
    """
    Determina si un valor parece una fecha

    Args:
        value: Valor a evaluar

    Returns:
        True si parece una fecha, False en caso contrario
    """
    if value is None or str(value).strip() == '':
        return False

    value_str = str(value).strip()

    # Revisar si tiene separadores de fecha
    if "/" in value_str or "-" in value_str:
        return True

    # Intentar patrones comunes
    date_patterns = [
        r'^\d{1,2}/\d{1,2}/\d{2,4}$',
        r'^\d{4}-\d{2}-\d{2}$',
        r'^\d{1,2}-\d{1,2}-\d{2,4}$'
    ]

    for pattern in date_patterns:
        if re.match(pattern, value_str):
            return True

    return False
