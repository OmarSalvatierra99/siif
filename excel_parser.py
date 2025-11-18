"""
Módulo especializado para parseo de archivos Excel de auxiliares contables
"""
import pandas as pd
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from io import BytesIO
import traceback

from utils import (
    normalize_text, to_numeric, is_monetary_value,
    setup_logger, parse_date
)


logger = setup_logger(__name__)


@dataclass
class ColumnInfo:
    """Información sobre una columna en el Excel"""
    idx: int
    value: str
    is_empty: bool = False
    is_numeric: bool = False
    is_monetary: bool = False
    numeric_value: Optional[float] = None

    @classmethod
    def from_value(cls, idx: int, value: Any) -> 'ColumnInfo':
        """
        Crea un ColumnInfo analizando un valor

        Args:
            idx: Índice de columna
            value: Valor a analizar

        Returns:
            ColumnInfo con análisis completado
        """
        value_str = str(value).strip() if not pd.isna(value) else ""

        col_info = cls(
            idx=idx,
            value=value_str,
            is_empty=not value_str
        )

        if value_str:
            # Intentar conversión numérica
            cleaned = value_str.replace(",", "").replace(" ", "")
            try:
                num_val = float(cleaned)
                col_info.is_numeric = True
                col_info.numeric_value = num_val

                # Determinar si es monetario
                if is_monetary_value(value_str):
                    col_info.is_monetary = True

            except ValueError:
                pass

        return col_info


class ColumnAnalyzer:
    """Analiza y clasifica columnas de una fila de transacción"""

    @staticmethod
    def analyze_row_columns(row: pd.Series, start_col: int = 2, max_col: int = 15) -> List[ColumnInfo]:
        """
        Analiza las columnas de una fila

        Args:
            row: Serie de pandas con datos de fila
            start_col: Índice de columna inicial
            max_col: Índice de columna máxima

        Returns:
            Lista de ColumnInfo
        """
        columns = []
        for i in range(start_col, min(len(row), max_col)):
            col_info = ColumnInfo.from_value(i, row.iloc[i])
            columns.append(col_info)

        return columns

    @staticmethod
    def classify_columns(columns: List[ColumnInfo]) -> Tuple[List[ColumnInfo], Optional[ColumnInfo], List[ColumnInfo]]:
        """
        Clasifica columnas en texto, orden de pago, y monetarias

        Args:
            columns: Lista de ColumnInfo

        Returns:
            Tupla (columnas_texto, columna_op, columnas_monetarias)
        """
        text_cols = []
        op_col = None
        monetary_cols = []

        for col in columns:
            if col.is_empty:
                continue
            elif col.is_monetary:
                monetary_cols.append(col)
            elif col.is_numeric and not col.is_monetary:
                # Números enteros pequeños podrían ser orden de pago
                if (op_col is None and col.numeric_value and
                    col.numeric_value.is_integer() and col.numeric_value < 10000):
                    op_col = col
                else:
                    monetary_cols.append(col)
            else:
                text_cols.append(col)

        return text_cols, op_col, monetary_cols


class TransactionExtractor:
    """Extrae transacciones de filas procesadas"""

    @staticmethod
    def extract_text_fields(text_cols: List[ColumnInfo]) -> Tuple[str, str]:
        """
        Extrae beneficiario y descripción de columnas de texto

        Args:
            text_cols: Columnas clasificadas como texto

        Returns:
            Tupla (beneficiario, descripcion)
        """
        beneficiario = ""
        descripcion = ""

        if len(text_cols) >= 2:
            beneficiario = text_cols[0].value
            descripcion = " ".join([c.value for c in text_cols[1:]])
        elif len(text_cols) == 1:
            descripcion = text_cols[0].value

        return beneficiario, descripcion

    @staticmethod
    def extract_monetary_fields(
        monetary_cols: List[ColumnInfo],
        current_saldo_inicial: Optional[str]
    ) -> Dict[str, str]:
        """
        Extrae campos monetarios de las columnas

        Args:
            monetary_cols: Columnas monetarias
            current_saldo_inicial: Saldo inicial de la cuenta actual

        Returns:
            Diccionario con saldo_inicial, cargos, abonos, saldo_final
        """
        result = {
            "saldo_inicial": "",
            "cargos": "",
            "abonos": "",
            "saldo_final": ""
        }

        num_monetary = len(monetary_cols)

        if num_monetary >= 4:
            result["saldo_inicial"] = monetary_cols[0].value
            result["cargos"] = monetary_cols[1].value
            result["abonos"] = monetary_cols[2].value
            result["saldo_final"] = monetary_cols[3].value

        elif num_monetary == 3:
            result["saldo_inicial"] = current_saldo_inicial or ""
            result["cargos"] = monetary_cols[0].value
            result["abonos"] = monetary_cols[1].value
            result["saldo_final"] = monetary_cols[2].value

        elif num_monetary == 2:
            result["saldo_inicial"] = current_saldo_inicial or ""
            result["cargos"] = ""
            result["abonos"] = monetary_cols[0].value
            result["saldo_final"] = monetary_cols[1].value

        return result

    @staticmethod
    def build_transaction_record(
        cuenta: str,
        nombre: str,
        fecha: str,
        poliza: str,
        beneficiario: str,
        descripcion: str,
        orden_pago: str,
        monetary_fields: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Construye un registro de transacción completo

        Args:
            cuenta: Cuenta contable
            nombre: Nombre de la cuenta
            fecha: Fecha de transacción
            poliza: Número de póliza
            beneficiario: Beneficiario
            descripcion: Descripción
            orden_pago: Orden de pago
            monetary_fields: Campos monetarios

        Returns:
            Diccionario con todos los campos
        """
        return {
            "cuenta_contable": cuenta,
            "nombre_cuenta": nombre,
            "fecha": fecha,
            "poliza": poliza,
            "beneficiario": beneficiario,
            "descripcion": descripcion,
            "orden_pago": orden_pago,
            **monetary_fields
        }


class ExcelParser:
    """Parser principal para archivos Excel de SIPAC"""

    def __init__(self):
        self.column_analyzer = ColumnAnalyzer()
        self.transaction_extractor = TransactionExtractor()

    def find_header_row(self, df: pd.DataFrame, max_rows: int = 20) -> Optional[int]:
        """
        Encuentra la fila de encabezados en el Excel

        Args:
            df: DataFrame de pandas
            max_rows: Número máximo de filas a buscar

        Returns:
            Índice de fila de encabezado o None
        """
        for idx in range(min(max_rows, len(df))):
            row_text = " ".join(df.iloc[idx].fillna("").astype(str).str.lower())
            if "fecha" in row_text and ("poliza" in row_text or "saldo" in row_text):
                logger.info(f"Encabezado encontrado en fila {idx}")
                return idx

        return None

    def parse_cuenta_line(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Parsea una línea de "CUENTA CONTABLE:"

        Args:
            text: Texto de la línea

        Returns:
            Tupla (cuenta, nombre) o None
        """
        if "CUENTA CONTABLE:" not in text.upper():
            return None

        parts = text.split(":", 1)
        if len(parts) <= 1:
            return None

        cuenta_nombre = parts[1].strip()

        if " - " in cuenta_nombre:
            cuenta, nombre = cuenta_nombre.split(" - ", 1)
            return cuenta.strip(), nombre.strip()
        else:
            return cuenta_nombre.strip(), ""

    def parse_saldo_inicial_line(self, row: pd.Series) -> Optional[str]:
        """
        Extrae el saldo inicial de una línea

        Args:
            row: Serie de pandas con la fila

        Returns:
            Saldo inicial como string o None
        """
        row_text = " ".join(row.fillna("").astype(str)).upper()

        if "SALDO INICIAL CUENTA" not in row_text:
            return None

        # Buscar primer valor numérico
        for col_idx in range(len(row)):
            val = str(row.iloc[col_idx]).strip() if not pd.isna(row.iloc[col_idx]) else ""

            if val and any(c.isdigit() for c in val):
                test_val = val.replace(",", "").replace(".", "").replace("-", "")
                if test_val.replace(".", "").isdigit() or test_val.replace(".", "").replace("-", "").isdigit():
                    return val

        return None

    def should_skip_row(self, row: pd.Series) -> bool:
        """
        Determina si una fila debe ser ignorada

        Args:
            row: Serie de pandas con la fila

        Returns:
            True si debe ignorarse
        """
        if row.isna().all():
            return True

        row_text = " ".join(row.fillna("").astype(str)).lower()
        skip_patterns = ["saldo acumulado", "saldo final cuenta", "total"]

        return any(pattern in row_text for pattern in skip_patterns)

    def is_date_value(self, value: Any) -> bool:
        """
        Determina si un valor es una fecha

        Args:
            value: Valor a verificar

        Returns:
            True si es una fecha
        """
        if value is None or pd.isna(value):
            return False

        value_str = str(value).strip()

        # Tiene formato de fecha
        if "/" in value_str or "-" in value_str:
            return True

        # Intentar parsear como fecha
        try:
            pd.to_datetime(value, errors='raise')
            return True
        except:
            return False

    def parse_transaction_row(
        self,
        row: pd.Series,
        current_cuenta: str,
        current_nombre: str,
        current_saldo_inicial: Optional[str]
    ) -> Optional[Dict[str, str]]:
        """
        Parsea una fila de transacción

        Args:
            row: Serie de pandas con la fila
            current_cuenta: Cuenta contable actual
            current_nombre: Nombre de cuenta actual
            current_saldo_inicial: Saldo inicial actual

        Returns:
            Diccionario con transacción o None
        """
        # Verificar fecha
        fecha_raw = row.iloc[0] if not pd.isna(row.iloc[0]) else None
        if not self.is_date_value(fecha_raw):
            return None

        # Formatear fecha
        try:
            fecha = pd.to_datetime(fecha_raw).strftime("%d/%m/%Y")
        except:
            fecha = str(fecha_raw).strip()

        # Extraer póliza
        poliza = str(row.iloc[1]).strip() if len(row) > 1 and not pd.isna(row.iloc[1]) else ""

        # Analizar columnas
        columns = self.column_analyzer.analyze_row_columns(row)
        text_cols, op_col, monetary_cols = self.column_analyzer.classify_columns(columns)

        # Necesitamos al menos 2 columnas monetarias
        if len(monetary_cols) < 2:
            return None

        # Extraer campos
        beneficiario, descripcion = self.transaction_extractor.extract_text_fields(text_cols)
        orden_pago = op_col.value if op_col else ""
        monetary_fields = self.transaction_extractor.extract_monetary_fields(
            monetary_cols, current_saldo_inicial
        )

        # Construir registro
        return self.transaction_extractor.build_transaction_record(
            cuenta=current_cuenta,
            nombre=current_nombre,
            fecha=fecha,
            poliza=poliza,
            beneficiario=beneficiario,
            descripcion=descripcion,
            orden_pago=orden_pago,
            monetary_fields=monetary_fields
        )

    def parse_excel_file(self, file_data: Tuple[str, BytesIO]) -> Tuple[pd.DataFrame, str]:
        """
        Parsea un archivo Excel completo

        Args:
            file_data: Tupla (filename, file_content)

        Returns:
            Tupla (DataFrame con transacciones, filename)
        """
        filename, file_content = file_data
        logger.info(f"Iniciando parseo de: {filename}")

        file_content.seek(0)

        # Leer archivo
        try:
            df = pd.read_excel(file_content, header=None, dtype=str, engine="openpyxl")
            logger.info(f"Archivo leído: {filename} ({len(df)} filas)")
        except Exception as e:
            logger.error(f"Error leyendo {filename}: {type(e).__name__} - {str(e)}")
            logger.error(traceback.format_exc())
            return pd.DataFrame(), filename

        if df.empty or len(df) < 2:
            logger.warning(f"Archivo muy pequeño: {filename}")
            return pd.DataFrame(), filename

        # Encontrar encabezado
        header_idx = self.find_header_row(df)
        if header_idx is None:
            logger.warning(f"No se encontró encabezado en {filename}")
            return pd.DataFrame(), filename

        # Determinar fila de inicio de datos
        start_idx = header_idx + 1
        if start_idx < len(df):
            next_row_text = " ".join(df.iloc[start_idx].fillna("").astype(str).str.lower())
            if "beneficiario" in next_row_text or "descripcion" in next_row_text:
                start_idx += 1

        # Procesar filas
        records = []
        current_cuenta = None
        current_nombre = None
        current_saldo_inicial = None

        for idx in range(start_idx, len(df)):
            row = df.iloc[idx]
            first_col = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""

            # Detectar nueva cuenta
            cuenta_info = self.parse_cuenta_line(first_col)
            if cuenta_info:
                current_cuenta, current_nombre = cuenta_info
                current_saldo_inicial = None
                continue

            # Detectar saldo inicial
            saldo_inicial = self.parse_saldo_inicial_line(row)
            if saldo_inicial and current_cuenta:
                current_saldo_inicial = saldo_inicial
                continue

            # Saltar filas no deseadas
            if self.should_skip_row(row):
                continue

            # Necesitamos una cuenta actual
            if not current_cuenta:
                continue

            # Intentar parsear transacción
            try:
                transaction = self.parse_transaction_row(
                    row, current_cuenta, current_nombre, current_saldo_inicial
                )
                if transaction:
                    records.append(transaction)
            except Exception as e:
                logger.debug(f"Error en fila {idx} de {filename}: {str(e)}")
                continue

        if not records:
            logger.warning(f"No se extrajeron transacciones de {filename}")
            return pd.DataFrame(), filename

        result_df = pd.DataFrame(records)
        logger.info(f"✓ Extraídas {len(result_df)} transacciones de {filename}")

        return result_df, filename
