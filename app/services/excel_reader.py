"""
Servicio para lectura y procesamiento de archivos Excel
"""
import pandas as pd
import traceback
from typing import Tuple
from io import BytesIO
from app.logging_config import get_logger
from app.utils.excel_parser import parse_cuenta_contable, detect_header_row, is_date_like
from app.utils.helpers import normalize_string

logger = get_logger('app.services.excel_reader')


class ExcelReader:
    """
    Clase para leer y procesar archivos Excel de auxiliares contables

    Esta clase maneja el formato específico de Excel usado en SIPAC donde:
    - "CUENTA CONTABLE:" headers identifican secciones de cuenta
    - "SALDO INICIAL CUENTA" filas proveen balances iniciales
    - Las filas de transacciones siguen con fechas, pólizas, beneficiarios y columnas monetarias
    """

    def __init__(self):
        self.logger = logger

    def read_excel_file(self, file_data: Tuple[str, BytesIO]) -> Tuple[pd.DataFrame, str]:
        """
        Lee un archivo Excel y extrae las transacciones

        Args:
            file_data: Tupla de (nombre_archivo, contenido_BytesIO)

        Returns:
            Tupla de (DataFrame con transacciones, nombre_archivo)
        """
        filename, file_content = file_data
        self.logger.info(f"Iniciando lectura de archivo: {filename}")
        file_content.seek(0)

        try:
            raw = pd.read_excel(file_content, header=None, dtype=str, engine="openpyxl")
            self.logger.info(f"Archivo leído exitosamente: {filename} ({len(raw)} filas)")
        except Exception as e:
            self.logger.error(f"Error al leer archivo {filename}: {type(e).__name__} - {str(e)}")
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return pd.DataFrame(), filename

        if raw.empty or len(raw) < 2:
            self.logger.warning(f"Archivo vacío o muy pequeño: {filename} ({len(raw)} filas)")
            return pd.DataFrame(), filename

        # Buscar la fila de encabezados
        header_row_idx = detect_header_row(raw)

        if header_row_idx is None:
            self.logger.warning(f"No se encontró fila de encabezados en {filename}. Primeras 5 filas:")
            for i in range(min(5, len(raw))):
                row_sample = ' | '.join(raw.iloc[i].fillna('').astype(str).tolist()[:5])
                self.logger.warning(f"  Fila {i}: {row_sample}")
            return pd.DataFrame(), filename

        self.logger.info(f"Encabezado encontrado en fila {header_row_idx} de {filename}")

        # Procesar transacciones
        records = self._extract_transactions(raw, header_row_idx, filename)

        if not records:
            self.logger.warning(f"No se encontraron transacciones válidas en {filename}")
            return pd.DataFrame(), filename

        df = pd.DataFrame(records)
        self.logger.info(f"✓ Extraídas {len(df)} transacciones de {filename}")
        return df, filename

    def _extract_transactions(self, raw: pd.DataFrame, header_row_idx: int, filename: str) -> list:
        """
        Extrae transacciones del DataFrame crudo

        Args:
            raw: DataFrame crudo de Excel
            header_row_idx: Índice de la fila de encabezados
            filename: Nombre del archivo (para logging)

        Returns:
            Lista de diccionarios con transacciones
        """
        # Determinar fila de inicio
        start_idx = header_row_idx + 1
        next_row_text = " ".join(raw.iloc[start_idx].fillna("").astype(str).str.lower()) if start_idx < len(raw) else ""
        if "beneficiario" in next_row_text or "descripcion" in next_row_text or "no." in next_row_text:
            start_idx += 1

        records = []
        current_cuenta = None
        current_nombre = None
        current_saldo_inicial = None

        for idx in range(start_idx, len(raw)):
            row = raw.iloc[idx]
            first_col = str(row.iloc[0] if not pd.isna(row.iloc[0]) else "").strip()

            # Detectar línea de cuenta contable
            if "CUENTA CONTABLE:" in first_col.upper():
                current_cuenta, current_nombre = self._parse_cuenta_line(first_col)
                current_saldo_inicial = None
                continue

            # Detectar línea de saldo inicial
            row_text_upper = " ".join(row.fillna("").astype(str)).upper()
            if "SALDO INICIAL CUENTA" in row_text_upper and current_cuenta:
                current_saldo_inicial = self._extract_saldo_inicial(row)
                continue

            # Ignorar filas vacías y totales
            if row.isna().all():
                continue
            row_text = " ".join(row.fillna("").astype(str)).lower()
            if any(skip in row_text for skip in ["saldo acumulado", "saldo final cuenta"]):
                continue

            if not current_cuenta:
                continue

            # Extraer datos de transacción
            record = self._parse_transaction_row(
                row, current_cuenta, current_nombre, current_saldo_inicial, filename, idx
            )
            if record:
                records.append(record)

        return records

    def _parse_cuenta_line(self, line: str) -> Tuple[str, str]:
        """
        Parsea una línea de "CUENTA CONTABLE: ..."

        Args:
            line: Línea a parsear

        Returns:
            Tupla de (cuenta, nombre)
        """
        parts = line.split(":", 1)
        if len(parts) > 1:
            cuenta_nombre = parts[1].strip()
            if " - " in cuenta_nombre:
                cuenta, nombre = cuenta_nombre.split(" - ", 1)
                return cuenta.strip(), nombre.strip()
            else:
                return cuenta_nombre, ""
        return "", ""

    def _extract_saldo_inicial(self, row: pd.Series) -> str:
        """
        Extrae el saldo inicial de una fila

        Args:
            row: Fila de pandas

        Returns:
            Saldo inicial como string
        """
        for col_idx in range(len(row)):
            val = str(row.iloc[col_idx] if not pd.isna(row.iloc[col_idx]) else "").strip()
            if val and any(c.isdigit() for c in val):
                test_val = val.replace(",", "").replace(".", "").replace("-", "")
                if test_val.replace(".", "").isdigit() or test_val.replace(".", "").replace("-", "").isdigit():
                    return val
        return ""

    def _parse_transaction_row(self, row: pd.Series, current_cuenta: str, current_nombre: str,
                                current_saldo_inicial: str, filename: str, idx: int) -> dict:
        """
        Parsea una fila de transacción

        Args:
            row: Fila de pandas
            current_cuenta: Cuenta contable actual
            current_nombre: Nombre de la cuenta actual
            current_saldo_inicial: Saldo inicial de la cuenta
            filename: Nombre del archivo (para logging)
            idx: Índice de la fila (para logging)

        Returns:
            Diccionario con datos de transacción o None si no es válida
        """
        try:
            # Validar fecha
            fecha_raw = row.iloc[0] if not pd.isna(row.iloc[0]) else None
            if not fecha_raw or pd.isna(fecha_raw):
                return None

            if not is_date_like(fecha_raw):
                return None

            # Convertir fecha
            try:
                fecha = pd.to_datetime(fecha_raw).strftime("%d/%m/%Y")
            except:
                fecha = str(fecha_raw).strip()

            # Obtener póliza
            poliza = str(row.iloc[1] if len(row) > 1 and not pd.isna(row.iloc[1]) else "").strip()

            # Analizar columnas para clasificarlas
            col_data = self._analyze_columns(row)

            # Separar columnas por tipo
            text_cols, op_col, monetary_cols = self._classify_columns(col_data)

            # Validar que tengamos suficientes columnas monetarias
            if len(monetary_cols) < 2:
                return None

            # Extraer campos de texto
            beneficiario, descripcion = self._extract_text_fields(text_cols)
            op = op_col['value'] if op_col else ""

            # Determinar columnas monetarias
            saldo_inicial, cargos, abonos, saldo_final = self._extract_monetary_fields(
                monetary_cols, current_saldo_inicial
            )

            # Crear registro
            return {
                "cuenta_contable": current_cuenta,
                "nombre_cuenta": current_nombre,
                "fecha": fecha,
                "poliza": poliza,
                "beneficiario": beneficiario,
                "descripcion": descripcion,
                "orden_pago": op,
                "saldo_inicial": saldo_inicial,
                "cargos": cargos,
                "abonos": abonos,
                "saldo_final": saldo_final,
            }
        except Exception as e:
            self.logger.debug(f"Error procesando fila {idx} en {filename}: {str(e)}")
            return None

    def _analyze_columns(self, row: pd.Series) -> list:
        """
        Analiza las columnas de una fila para clasificarlas

        Args:
            row: Fila de pandas

        Returns:
            Lista de diccionarios con información de cada columna
        """
        col_data = []
        for i in range(2, min(len(row), 15)):
            val = str(row.iloc[i] if not pd.isna(row.iloc[i]) else "").strip()
            col_info = {
                'idx': i,
                'value': val,
                'is_empty': not val,
                'is_numeric': False,
                'is_monetary': False,
                'numeric_value': None
            }

            if val:
                cleaned = val.replace(",", "").replace(" ", "")
                try:
                    num_val = float(cleaned)
                    col_info['is_numeric'] = True
                    col_info['numeric_value'] = num_val

                    # Determinar si es monetario
                    has_comma = "," in val
                    has_decimal = "." in cleaned
                    is_zero_str = val.strip() == "0"

                    if has_comma or has_decimal or is_zero_str:
                        col_info['is_monetary'] = True
                except ValueError:
                    pass

            col_data.append(col_info)

        return col_data

    def _classify_columns(self, col_data: list) -> Tuple[list, dict, list]:
        """
        Clasifica columnas en texto, orden de pago y monetarias

        Args:
            col_data: Lista de información de columnas

        Returns:
            Tupla de (text_cols, op_col, monetary_cols)
        """
        text_cols = []
        op_col = None
        monetary_cols = []

        for col in col_data:
            if col['is_empty']:
                continue
            elif col['is_monetary']:
                monetary_cols.append(col)
            elif col['is_numeric'] and not col['is_monetary']:
                if op_col is None and col['numeric_value'] and col['numeric_value'].is_integer():
                    op_col = col
                else:
                    monetary_cols.append(col)
            else:
                text_cols.append(col)

        return text_cols, op_col, monetary_cols

    def _extract_text_fields(self, text_cols: list) -> Tuple[str, str]:
        """
        Extrae beneficiario y descripción de las columnas de texto

        Args:
            text_cols: Lista de columnas de texto

        Returns:
            Tupla de (beneficiario, descripcion)
        """
        beneficiario = ""
        descripcion = ""

        if len(text_cols) >= 2:
            beneficiario = text_cols[0]['value']
            descripcion = " ".join([c['value'] for c in text_cols[1:]])
        elif len(text_cols) == 1:
            descripcion = text_cols[0]['value']

        return beneficiario, descripcion

    def _extract_monetary_fields(self, monetary_cols: list, current_saldo_inicial: str) -> Tuple[str, str, str, str]:
        """
        Extrae los campos monetarios

        Args:
            monetary_cols: Lista de columnas monetarias
            current_saldo_inicial: Saldo inicial de la cuenta

        Returns:
            Tupla de (saldo_inicial, cargos, abonos, saldo_final)
        """
        if len(monetary_cols) >= 4:
            return (
                monetary_cols[0]['value'],
                monetary_cols[1]['value'],
                monetary_cols[2]['value'],
                monetary_cols[3]['value']
            )
        elif len(monetary_cols) == 3:
            return (
                current_saldo_inicial if current_saldo_inicial else "",
                monetary_cols[0]['value'],
                monetary_cols[1]['value'],
                monetary_cols[2]['value']
            )
        elif len(monetary_cols) == 2:
            return (
                current_saldo_inicial if current_saldo_inicial else "",
                "",
                monetary_cols[0]['value'],
                monetary_cols[1]['value']
            )
        else:
            return "", "", "", ""
