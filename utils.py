"""
Utilidades comunes para el proyecto SIPAC
"""
import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal
import pandas as pd


def normalize_text(text: str) -> str:
    """
    Normaliza texto para comparación eliminando acentos y espacios extras

    Args:
        text: Texto a normalizar

    Returns:
        Texto normalizado en minúsculas
    """
    if not text:
        return ""

    text = str(text).strip().lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ü": "u", "ñ": "n"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"\s+", " ", text)


def to_numeric(value: Any, default: float = 0.0) -> float:
    """
    Convierte un valor a numérico de forma segura

    Args:
        value: Valor a convertir
        default: Valor por defecto si la conversión falla

    Returns:
        Valor numérico o default
    """
    if pd.isna(value):
        return default

    if isinstance(value, (int, float, Decimal)):
        return float(value)

    try:
        # Limpiar string y convertir
        cleaned = str(value).replace(",", "").replace(" ", "")
        return float(cleaned) if cleaned else default
    except (ValueError, AttributeError):
        return default


def to_numeric_series(series: pd.Series) -> pd.Series:
    """
    Convierte una serie de pandas a numérico de forma eficiente

    Args:
        series: Serie de pandas

    Returns:
        Serie con valores numéricos
    """
    return pd.to_numeric(
        series.astype(str).str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce"
    ).fillna(0.0)


def parse_date(date_value: Any, format_str: str = "%d/%m/%Y") -> Optional[datetime]:
    """
    Convierte un valor a fecha de forma segura

    Args:
        date_value: Valor a convertir
        format_str: Formato de fecha esperado

    Returns:
        Objeto datetime o None
    """
    if pd.isna(date_value):
        return None

    try:
        return pd.to_datetime(date_value, format=format_str, errors='coerce')
    except:
        try:
            return pd.to_datetime(date_value, errors='coerce')
        except:
            return None


def format_currency(amount: float) -> str:
    """
    Formatea un monto como moneda

    Args:
        amount: Monto a formatear

    Returns:
        String formateado como moneda
    """
    return f"${amount:,.2f}"


def is_monetary_value(value: str) -> bool:
    """
    Determina si un string representa un valor monetario

    Args:
        value: String a evaluar

    Returns:
        True si parece un valor monetario
    """
    if not value:
        return False

    # Tiene coma de miles o punto decimal
    if "," in value or "." in value or value.strip() == "0":
        try:
            cleaned = value.replace(",", "").replace(" ", "")
            float(cleaned)
            return True
        except ValueError:
            return False

    return False


def extract_cuenta_components(cuenta_str: str) -> Dict[str, str]:
    """
    Extrae los componentes de una cuenta contable de 21 caracteres

    Args:
        cuenta_str: Cuenta contable completa

    Returns:
        Diccionario con componentes de la cuenta
    """
    # Limpiar y normalizar
    cuenta = str(cuenta_str).strip().upper()
    cuenta = re.sub(r"[^0-9A-Z]", "", cuenta).ljust(21, "0")

    return {
        "genero": cuenta[0],
        "grupo": cuenta[1],
        "rubro": cuenta[2],
        "cuenta": cuenta[3],
        "subcuenta": cuenta[4],
        "dependencia": cuenta[5:7],
        "unidad_responsable": cuenta[7:9],
        "centro_costo": cuenta[9:11],
        "proyecto_presupuestario": cuenta[11:13],
        "fuente": cuenta[13],
        "subfuente": cuenta[14:16],
        "tipo_recurso": cuenta[16],
        "partida_presupuestal": cuenta[17:21],
    }


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Configura un logger con formato estructurado

    Args:
        name: Nombre del logger
        level: Nivel de logging

    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def validate_excel_file(filename: str, allowed_extensions: set) -> bool:
    """
    Valida que un archivo tenga extensión permitida

    Args:
        filename: Nombre del archivo
        allowed_extensions: Conjunto de extensiones permitidas

    Returns:
        True si es válido
    """
    import os
    ext = os.path.splitext(filename)[1].lower()
    return ext in allowed_extensions


def calculate_running_balance(
    transactions: List[Dict],
    amount_fields: tuple = ('saldo_inicial', 'cargos', 'abonos')
) -> List[Dict]:
    """
    Calcula saldos acumulativos para un conjunto de transacciones

    Args:
        transactions: Lista de diccionarios de transacciones
        amount_fields: Tupla con nombres de campos (inicial, cargos, abonos)

    Returns:
        Lista de transacciones con saldo_final calculado
    """
    if not transactions:
        return []

    inicial_field, cargos_field, abonos_field = amount_fields
    saldo_actual = 0.0

    for i, trans in enumerate(transactions):
        if i == 0:
            saldo_actual = (
                to_numeric(trans.get(inicial_field, 0)) +
                to_numeric(trans.get(cargos_field, 0)) -
                to_numeric(trans.get(abonos_field, 0))
            )
        else:
            trans[inicial_field] = saldo_actual
            saldo_actual = (
                saldo_actual +
                to_numeric(trans.get(cargos_field, 0)) -
                to_numeric(trans.get(abonos_field, 0))
            )

        trans['saldo_final'] = saldo_actual

    return transactions


class ProgressReporter:
    """Clase helper para reportar progreso de forma consistente"""

    def __init__(self, callback=None):
        """
        Args:
            callback: Función callback(percent, message)
        """
        self.callback = callback
        self.logger = setup_logger(self.__class__.__name__)

    def report(self, percent: int, message: str):
        """
        Reporta progreso

        Args:
            percent: Porcentaje completado (0-100)
            message: Mensaje descriptivo
        """
        if self.callback:
            self.callback(percent, message)
        else:
            self.logger.info(f"[{percent}%] {message}")

    def info(self, message: str):
        """Log info sin callback"""
        self.logger.info(message)

    def error(self, message: str):
        """Log error sin callback"""
        self.logger.error(message)

    def warning(self, message: str):
        """Log warning sin callback"""
        self.logger.warning(message)
