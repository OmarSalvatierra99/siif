from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
import zipfile
import xml.etree.ElementTree as ET
from typing import Callable, List, Optional, Tuple
import logging
import re
import traceback
import uuid

import pandas as pd
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index

# Base de datos

db = SQLAlchemy()


class Transaccion(db.Model):
    """Modelo para transacciones contables"""
    __tablename__ = 'transacciones'

    id = db.Column(db.Integer, primary_key=True)

    # Información de carga
    lote_id = db.Column(db.String(36), nullable=False, index=True)
    archivo_origen = db.Column(db.String(255), nullable=False)
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    usuario_carga = db.Column(db.String(100))

    # Cuenta contable completa
    cuenta_contable = db.Column(db.String(21), nullable=False, index=True)
    nombre_cuenta = db.Column(db.Text)

    # Componentes de cuenta (formato vertical)
    genero = db.Column(db.String(1), index=True)
    grupo = db.Column(db.String(1), index=True)
    rubro = db.Column(db.String(1), index=True)
    cuenta = db.Column(db.String(1), index=True)
    subcuenta = db.Column(db.String(1), index=True)
    dependencia = db.Column(db.String(2), index=True)
    unidad_responsable = db.Column(db.String(2), index=True)
    centro_costo = db.Column(db.String(2), index=True)
    proyecto_presupuestario = db.Column(db.String(2), index=True)
    fuente = db.Column(db.String(1), index=True)
    subfuente = db.Column(db.String(2), index=True)
    tipo_recurso = db.Column(db.String(1), index=True)
    partida_presupuestal = db.Column(db.String(4), index=True)

    # Datos de transacción
    fecha_transaccion = db.Column(db.Date, nullable=False, index=True)
    poliza = db.Column(db.String(50), index=True)
    beneficiario = db.Column(db.Text)
    descripcion = db.Column(db.Text)
    orden_pago = db.Column(db.String(50))

    # Montos
    saldo_inicial = db.Column(db.Numeric(15, 2), default=0)
    cargos = db.Column(db.Numeric(15, 2), default=0)
    abonos = db.Column(db.Numeric(15, 2), default=0)
    saldo_final = db.Column(db.Numeric(15, 2), default=0)

    # Índices compuestos para consultas comunes
    __table_args__ = (
        Index('idx_cuenta_fecha', 'cuenta_contable', 'fecha_transaccion'),
        Index('idx_dependencia_fecha', 'dependencia', 'fecha_transaccion'),
        Index('idx_lote_cuenta', 'lote_id', 'cuenta_contable'),
    )

    def to_dict(self):
        """Convierte el modelo a diccionario"""
        return {
            'id': self.id,
            'lote_id': self.lote_id,
            'archivo_origen': self.archivo_origen,
            'fecha_carga': self.fecha_carga.isoformat() if self.fecha_carga else None,
            'cuenta_contable': self.cuenta_contable,
            'nombre_cuenta': self.nombre_cuenta,
            'genero': self.genero,
            'grupo': self.grupo,
            'rubro': self.rubro,
            'cuenta': self.cuenta,
            'subcuenta': self.subcuenta,
            'dependencia': self.dependencia,
            'unidad_responsable': self.unidad_responsable,
            'centro_costo': self.centro_costo,
            'proyecto_presupuestario': self.proyecto_presupuestario,
            'fuente': self.fuente,
            'subfuente': self.subfuente,
            'tipo_recurso': self.tipo_recurso,
            'partida_presupuestal': self.partida_presupuestal,
            'fecha_transaccion': self.fecha_transaccion.strftime('%d/%m/%Y') if self.fecha_transaccion else None,
            'poliza': self.poliza,
            'beneficiario': self.beneficiario,
            'descripcion': self.descripcion,
            'orden_pago': self.orden_pago,
            'saldo_inicial': float(self.saldo_inicial) if self.saldo_inicial else 0,
            'cargos': float(self.cargos) if self.cargos else 0,
            'abonos': float(self.abonos) if self.abonos else 0,
            'saldo_final': float(self.saldo_final) if self.saldo_final else 0,
        }


class LoteCarga(db.Model):
    """Modelo para rastrear lotes de carga"""
    __tablename__ = 'lotes_carga'

    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow)
    usuario = db.Column(db.String(100))
    archivos = db.Column(db.JSON)  # Lista de archivos procesados
    total_registros = db.Column(db.Integer, default=0)
    estado = db.Column(db.String(20), default='procesando')  # procesando, completado, error
    mensaje = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'lote_id': self.lote_id,
            'fecha_carga': self.fecha_carga.isoformat() if self.fecha_carga else None,
            'usuario': self.usuario,
            'archivos': self.archivos,
            'total_registros': self.total_registros,
            'estado': self.estado,
            'mensaje': self.mensaje
        }


class Usuario(db.Model):
    """Modelo para usuarios del sistema"""
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    nombre_completo = db.Column(db.String(200))
    email = db.Column(db.String(200))
    password_hash = db.Column(db.String(255))
    rol = db.Column(db.String(50), default='auditor')  # admin, auditor, consulta
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_acceso = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nombre_completo': self.nombre_completo,
            'email': self.email,
            'rol': self.rol,
            'activo': self.activo
        }


class ReporteGenerado(db.Model):
    """Modelo para rastrear reportes generados"""
    __tablename__ = 'reportes_generados'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    fecha_generacion = db.Column(db.DateTime, default=datetime.utcnow)
    tipo_reporte = db.Column(db.String(50))
    filtros_aplicados = db.Column(db.JSON)
    total_registros = db.Column(db.Integer)
    nombre_archivo = db.Column(db.String(255))

    usuario = db.relationship('Usuario', backref='reportes')

    def to_dict(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'fecha_generacion': self.fecha_generacion.isoformat() if self.fecha_generacion else None,
            'tipo_reporte': self.tipo_reporte,
            'filtros_aplicados': self.filtros_aplicados,
            'total_registros': self.total_registros,
            'nombre_archivo': self.nombre_archivo
        }


class Ente(db.Model):
    """Modelo para catálogo de entes públicos"""
    __tablename__ = 'entes'

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(20), unique=True, nullable=False, index=True)
    codigo = db.Column(db.String(50), nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    siglas = db.Column(db.String(50))
    tipo = db.Column(db.String(100))
    ambito = db.Column(db.String(50))
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'clave': self.clave,
            'codigo': self.codigo,
            'nombre': self.nombre,
            'siglas': self.siglas,
            'tipo': self.tipo,
            'ambito': self.ambito,
            'activo': self.activo,
            'fecha_registro': self.fecha_registro.isoformat() if self.fecha_registro else None
        }


# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _norm(s):
    """Normaliza strings para comparación"""
    s = str(s or "").strip().lower()
    rep = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for k, v in rep.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", " ", s)
    return s


def _split_cuenta_contable_vertical(cuenta_str):
    """Divide la cuenta contable en componentes"""
    s = str(cuenta_str).strip().upper()
    s = re.sub(r"[^0-9A-Z]", "", s).ljust(21, "0")

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


def _to_numeric_fast(s):
    """Convierte series a numérico de forma rápida"""
    return pd.to_numeric(
        s.astype(str).str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce"
    ).fillna(0.0)


def _read_one_excel(file_data):
    """Lee un archivo Excel y extrae las transacciones"""
    filename, file_content = file_data
    logger.info(f"Iniciando lectura de archivo: {filename}")
    file_content.seek(0)

    try:
        raw = pd.read_excel(file_content, header=None, dtype=str, engine="openpyxl")
        logger.info(f"Archivo leído exitosamente: {filename} ({len(raw)} filas)")
    except Exception as e:
        logger.error(f"Error al leer archivo {filename}: {type(e).__name__} - {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return pd.DataFrame(), filename

    if raw.empty or len(raw) < 2:
        logger.warning(f"Archivo vacío o muy pequeño: {filename} ({len(raw)} filas)")
        return pd.DataFrame(), filename

    # Buscar la fila de encabezados
    header_row_idx = None
    for idx in range(min(20, len(raw))):
        row_text = " ".join(raw.iloc[idx].fillna("").astype(str).str.lower())
        if "fecha" in row_text and ("poliza" in row_text or "saldo" in row_text):
            header_row_idx = idx
            logger.info(f"Encabezado encontrado en fila {idx} de {filename}")
            break

    if header_row_idx is None:
        logger.warning(f"No se encontró fila de encabezados en {filename}. Primeras 5 filas:")
        for i in range(min(5, len(raw))):
            logger.warning(
                f"  Fila {i}: {' | '.join(raw.iloc[i].fillna('').astype(str).tolist()[:5])}"
            )
        return pd.DataFrame(), filename

    # Saltar las filas de encabezado
    start_idx = header_row_idx + 1
    next_row_text = " ".join(
        raw.iloc[start_idx].fillna("").astype(str).str.lower()
    ) if start_idx < len(raw) else ""
    if "beneficiario" in next_row_text or "descripcion" in next_row_text or "no." in next_row_text:
        start_idx += 1

    # Procesar todas las filas
    records = []
    current_cuenta = None
    current_nombre = None
    current_saldo_inicial = None

    for idx in range(start_idx, len(raw)):
        row = raw.iloc[idx]
        first_col = str(row.iloc[0] if not pd.isna(row.iloc[0]) else "").strip()

        # Detectar línea de cuenta contable
        if "CUENTA CONTABLE:" in first_col.upper():
            parts = first_col.split(":", 1)
            if len(parts) > 1:
                cuenta_nombre = parts[1].strip()
                if " - " in cuenta_nombre:
                    current_cuenta, current_nombre = cuenta_nombre.split(" - ", 1)
                    current_cuenta = current_cuenta.strip()
                    current_nombre = current_nombre.strip()
                else:
                    current_cuenta = cuenta_nombre
                    current_nombre = ""
            current_saldo_inicial = None
            continue

        # Detectar línea de saldo inicial
        row_text_upper = " ".join(row.fillna("").astype(str)).upper()
        if "SALDO INICIAL CUENTA" in row_text_upper and current_cuenta:
            for col_idx in range(len(row)):
                val = str(row.iloc[col_idx] if not pd.isna(row.iloc[col_idx]) else "").strip()
                if val and any(c.isdigit() for c in val):
                    test_val = val.replace(",", "").replace(".", "").replace("-", "")
                    if test_val.replace(".", "").isdigit() or test_val.replace(".", "").replace("-", "").isdigit():
                        current_saldo_inicial = val
                        break
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
        try:
            fecha_raw = row.iloc[0] if not pd.isna(row.iloc[0]) else None
            if fecha_raw is None or pd.isna(fecha_raw):
                continue

            fecha = str(fecha_raw).strip()
            is_date = False
            if "/" in fecha or "-" in fecha:
                is_date = True
            else:
                try:
                    pd.to_datetime(fecha_raw, errors='raise')
                    is_date = True
                except Exception:
                    pass

            if not is_date:
                continue

            try:
                fecha = pd.to_datetime(fecha_raw).strftime("%d/%m/%Y")
            except Exception:
                pass

            poliza = str(row.iloc[1] if len(row) > 1 and not pd.isna(row.iloc[1]) else "").strip()

            # Analizar columnas
            col_data = []
            for i in range(2, min(len(row), 15)):
                val = str(row.iloc[i] if not pd.isna(row.iloc[i]) else "").strip()
                col_data.append({
                    'idx': i,
                    'value': val,
                    'is_empty': not val,
                    'is_numeric': False,
                    'is_monetary': False,
                    'numeric_value': None
                })

                if val:
                    cleaned = val.replace(",", "").replace(" ", "")
                    try:
                        num_val = float(cleaned)
                        col_data[-1]['is_numeric'] = True
                        col_data[-1]['numeric_value'] = num_val
                        has_comma = "," in val
                        has_decimal = "." in cleaned
                        is_zero_str = val.strip() == "0"

                        if has_comma or has_decimal or is_zero_str:
                            col_data[-1]['is_monetary'] = True
                    except ValueError:
                        pass

            # Separar columnas
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

            if len(monetary_cols) < 2:
                continue

            # Extraer campos de texto
            beneficiario = ""
            descripcion = ""
            if len(text_cols) >= 2:
                beneficiario = text_cols[0]['value']
                descripcion = " ".join([c['value'] for c in text_cols[1:]])
            elif len(text_cols) == 1:
                descripcion = text_cols[0]['value']

            op = op_col['value'] if op_col else ""

            # Determinar columnas monetarias
            if len(monetary_cols) >= 4:
                saldo_inicial = monetary_cols[0]['value']
                cargos = monetary_cols[1]['value']
                abonos = monetary_cols[2]['value']
                saldo_final = monetary_cols[3]['value']
            elif len(monetary_cols) == 3:
                saldo_inicial = current_saldo_inicial if current_saldo_inicial else ""
                cargos = monetary_cols[0]['value']
                abonos = monetary_cols[1]['value']
                saldo_final = monetary_cols[2]['value']
            elif len(monetary_cols) == 2:
                saldo_inicial = current_saldo_inicial if current_saldo_inicial else ""
                cargos = ""
                abonos = monetary_cols[0]['value']
                saldo_final = monetary_cols[1]['value']
            else:
                continue

            # Crear registro
            record = {
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
            records.append(record)
        except Exception:
            logger.debug(f"Error procesando fila {idx} en {filename}")
            continue

    if not records:
        logger.warning(f"No se encontraron transacciones válidas en {filename}")
        logger.warning(f"Total de filas procesadas: {len(raw) - start_idx}")
        return pd.DataFrame(), filename

    df = pd.DataFrame(records)
    logger.info(f"✓ Extraídas {len(df)} transacciones de {filename}")
    return df, filename


def _select_column(col_map, options):
    for option in options:
        option_norm = _norm(option)
        for col, col_norm in col_map.items():
            if col_norm == option_norm or col_norm.startswith(option_norm):
                return col
    return None


def _col_to_index(col):
    idx = 0
    for ch in col:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx


def _unique_headers(headers):
    seen = set()
    result = []
    for i, header in enumerate(headers, start=1):
        name = str(header or "").strip()
        if not name:
            name = f"_col_{i}"
        if name in seen:
            base = name
            suffix = 1
            while f"{base}_{suffix}" in seen:
                suffix += 1
            name = f"{base}_{suffix}"
        seen.add(name)
        result.append(name)
    return result


def _read_xlsx_xml_to_dataframe(file_content):
    file_content.seek(0)
    data = file_content.read()
    try:
        z = zipfile.ZipFile(BytesIO(data))
    except Exception:
        return None

    if "xl/worksheets/sheet1.xml" not in z.namelist():
        return None

    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        try:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            ns = {"s": root.tag.split("}")[0].strip("{")}
            for si in root.findall("s:si", ns):
                texts = []
                for t in si.findall(".//s:t", ns):
                    texts.append(t.text or "")
                shared.append("".join(texts))
        except Exception:
            shared = []

    try:
        sheet_root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    except Exception:
        return None

    ns = {"s": sheet_root.tag.split("}")[0].strip("{")}
    row_dicts = []
    max_col_idx = 0

    for row in sheet_root.findall(".//s:sheetData/s:row", ns):
        cells = {}
        for c in row.findall("s:c", ns):
            ref = c.attrib.get("r", "")
            letters = "".join(ch for ch in ref if ch.isalpha())
            if not letters:
                continue
            col_idx = _col_to_index(letters)
            max_col_idx = max(max_col_idx, col_idx)
            t = c.attrib.get("t")
            v = c.find("s:v", ns)
            val = v.text if v is not None else ""

            if t == "s":
                try:
                    val = shared[int(val)]
                except Exception:
                    pass
            elif t == "inlineStr":
                is_node = c.find("s:is", ns)
                if is_node is not None:
                    t_node = is_node.find("s:t", ns)
                    if t_node is not None and t_node.text is not None:
                        val = t_node.text

            cells[col_idx] = val

        if cells:
            row_dicts.append(cells)

    if not row_dicts or max_col_idx == 0:
        return None

    rows = []
    for cells in row_dicts:
        row_list = [""] * max_col_idx
        for idx, val in cells.items():
            row_list[idx - 1] = val
        rows.append(row_list)

    return pd.DataFrame(rows)


def _read_one_excel_macro(file_data):
    """Lee archivos ya procesados por macro y normaliza columnas"""
    filename, file_content = file_data
    logger.info(f"Iniciando lectura macro de archivo: {filename}")
    file_content.seek(0)

    try:
        xl = pd.ExcelFile(file_content, engine="openpyxl")
        sheets = xl.sheet_names
    except Exception as e:
        logger.error(f"Error al leer archivo macro {filename}: {type(e).__name__} - {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        sheets = []
        xl = None

    def build_from_raw(raw):
        if raw.empty or len(raw) < 2:
            return None

        header_row_idx = None
        for idx in range(min(30, len(raw))):
            row_text = " ".join(raw.iloc[idx].fillna("").astype(str).str.lower())
            if "cuenta" in row_text and "fecha" in row_text and ("poliza" in row_text or "póliza" in row_text):
                header_row_idx = idx
                break

        if header_row_idx is None:
            return None

        headers = _unique_headers(raw.iloc[header_row_idx].fillna("").astype(str).tolist())
        col_map = {col: _norm(col) for col in headers}

        data = raw.iloc[header_row_idx + 1:].copy()
        data.columns = headers
        data = data.dropna(how="all")
        if data.empty:
            return None

        cuenta_col = _select_column(col_map, ["cuenta contable", "cuenta", "cta contable"])
        if not cuenta_col:
            logger.warning(f"No se encontró columna de cuenta en {filename}")
            return None

        nombre_col = _select_column(col_map, ["nombre cuenta", "nombre de la cuenta", "descripcion cuenta", "nombre"])
        fecha_col = _select_column(col_map, ["fecha", "fecha transaccion", "fecha movimiento"])
        poliza_col = _select_column(col_map, ["poliza", "póliza", "no poliza", "no. poliza", "numero poliza"])
        beneficiario_col = _select_column(col_map, ["beneficiario", "proveedor", "razon social"])
        descripcion_col = _select_column(col_map, ["descripcion", "concepto", "detalle", "observaciones"])
        op_col = _select_column(col_map, ["o.p.", "op", "orden pago", "orden de pago", "orden_pago"])
        saldo_inicial_col = _select_column(col_map, ["saldo inicial", "saldo inicial cuenta", "saldo ini"])
        cargos_col = _select_column(col_map, ["cargos", "cargo", "debe"])
        abonos_col = _select_column(col_map, ["abonos", "abono", "haber"])
        saldo_final_col = _select_column(col_map, ["saldo final", "saldo final cuenta", "saldo"])

        records = []
        for _, row in data.iterrows():
            cuenta_val = str(row.get(cuenta_col, "")).strip() if cuenta_col else ""
            if not cuenta_val:
                continue

            nombre_val = str(row.get(nombre_col, "")).strip() if nombre_col else ""
            if not nombre_val and " - " in cuenta_val:
                parts = cuenta_val.split(" - ", 1)
                cuenta_val = parts[0].strip()
                nombre_val = parts[1].strip()

            fecha_raw = row.get(fecha_col, "") if fecha_col else ""
            if pd.isna(fecha_raw) or str(fecha_raw).strip() == "":
                continue

            try:
                fecha = pd.to_datetime(fecha_raw).strftime("%d/%m/%Y")
            except Exception:
                fecha = str(fecha_raw).strip()

            poliza = str(row.get(poliza_col, "")).strip() if poliza_col else ""
            beneficiario = str(row.get(beneficiario_col, "")).strip() if beneficiario_col else ""
            descripcion = str(row.get(descripcion_col, "")).strip() if descripcion_col else ""
            op = str(row.get(op_col, "")).strip() if op_col else ""
            saldo_inicial = str(row.get(saldo_inicial_col, "")).strip() if saldo_inicial_col else ""
            cargos = str(row.get(cargos_col, "")).strip() if cargos_col else ""
            abonos = str(row.get(abonos_col, "")).strip() if abonos_col else ""
            saldo_final = str(row.get(saldo_final_col, "")).strip() if saldo_final_col else ""

            records.append({
                "cuenta_contable": cuenta_val,
                "nombre_cuenta": nombre_val,
                "fecha": fecha,
                "poliza": poliza,
                "beneficiario": beneficiario,
                "descripcion": descripcion,
                "orden_pago": op,
                "saldo_inicial": saldo_inicial,
                "cargos": cargos,
                "abonos": abonos,
                "saldo_final": saldo_final,
            })

        if not records:
            return None

        return pd.DataFrame(records)

    for sheet in sheets:
        try:
            raw = pd.read_excel(xl, sheet_name=sheet, header=None, dtype=str)
        except Exception:
            continue
        df = build_from_raw(raw)
        if df is not None and not df.empty:
            logger.info(f"✓ Extraídas {len(df)} transacciones macro de {filename}")
            return df, filename

    raw_xml = _read_xlsx_xml_to_dataframe(file_content)
    if raw_xml is not None:
        df = build_from_raw(raw_xml)
        if df is not None and not df.empty:
            logger.info(f"✓ Extraídas {len(df)} transacciones macro de {filename} (xml)")
            return df, filename

    logger.warning(f"No se encontraron transacciones macro válidas en {filename}")
    return pd.DataFrame(), filename


def process_files_to_database(
    file_list: List[Tuple[str, BytesIO]],
    usuario: str = "sistema",
    progress_callback: Optional[Callable[[int, str], None]] = None,
    tipo_archivo: str = "auxiliar"
):
    """
    Procesa archivos Excel y guarda en base de datos
    Retorna el lote_id para tracking
    """
    def report(p, m):
        if progress_callback:
            progress_callback(p, m)
        else:
            print(f"[{p}%] {m}")

    lote_id = str(uuid.uuid4())

    # Crear registro de lote
    lote = LoteCarga(
        lote_id=lote_id,
        usuario=usuario,
        archivos=[f[0] for f in file_list],
        estado='procesando'
    )
    db.session.add(lote)
    db.session.commit()

    try:
        logger.info(f"Iniciando procesamiento de {len(file_list)} archivo(s)")
        report(5, f"Leyendo {len(file_list)} archivo(s)...")
        frames = []
        archivos_procesados = []
        archivos_fallidos = []

        reader = _read_one_excel_macro if tipo_archivo == "macro" else _read_one_excel
        with ThreadPoolExecutor(max_workers=min(4, len(file_list))) as ex:
            futures = {ex.submit(reader, f): f for f in file_list}
            for f in as_completed(futures):
                try:
                    df, filename = f.result()
                    if not df.empty:
                        df['archivo_origen'] = filename
                        frames.append(df)
                        archivos_procesados.append(filename)
                        logger.info(f"Archivo procesado exitosamente: {filename}")
                    else:
                        archivos_fallidos.append(filename)
                        logger.warning(f"Archivo no generó registros: {filename}")
                except Exception as e:
                    file_info = futures[f]
                    logger.error(
                        f"Error procesando archivo {file_info[0]}: {type(e).__name__} - {str(e)}"
                    )
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    archivos_fallidos.append(file_info[0])
                    continue

        logger.info(
            f"Resumen: {len(archivos_procesados)} exitosos, {len(archivos_fallidos)} fallidos"
        )

        if not frames:
            error_msg = (
                "No se pudo procesar ningún archivo válido. "
                f"Archivos fallidos: {', '.join(archivos_fallidos)}"
            )
            logger.error(error_msg)
            lote.estado = 'error'
            lote.mensaje = error_msg
            db.session.commit()
            raise ValueError(error_msg)

        base = pd.concat(frames, ignore_index=True)

        base["poliza"] = base["poliza"].fillna("").astype(str).str.strip()
        base["orden_pago"] = base["orden_pago"].fillna("").astype(str).str.strip()
        invalid_op = {"", "n/a", "na", "n.d.", "nd", "none"}
        base["orden_pago"] = base["orden_pago"].where(
            ~base["orden_pago"].str.lower().isin(invalid_op),
            ""
        )

        def _first_non_empty(series):
            for value in series:
                if value:
                    return value
            return ""

        op_por_poliza = base.groupby("poliza")["orden_pago"].apply(_first_non_empty)
        base["orden_pago"] = base["poliza"].map(op_por_poliza).where(
            base["poliza"] != "",
            base["orden_pago"]
        )

        # Dividir cuenta contable
        report(30, "Procesando cuentas contables...")
        componentes = base["cuenta_contable"].apply(_split_cuenta_contable_vertical)
        for key in [
            "genero",
            "grupo",
            "rubro",
            "cuenta",
            "subcuenta",
            "dependencia",
            "unidad_responsable",
            "centro_costo",
            "proyecto_presupuestario",
            "fuente",
            "subfuente",
            "tipo_recurso",
            "partida_presupuestal",
        ]:
            base[key] = componentes.apply(lambda x: x[key])

        # Convertir columnas monetarias
        report(50, "Convirtiendo valores monetarios...")
        base["saldo_inicial"] = _to_numeric_fast(base["saldo_inicial"])
        base["cargos"] = _to_numeric_fast(base["cargos"])
        base["abonos"] = _to_numeric_fast(base["abonos"])

        # Calcular saldo final acumulativo por cuenta
        report(65, "Calculando saldos acumulativos...")
        base["saldo_final"] = 0.0

        for cuenta in base["cuenta_contable"].unique():
            mask = base["cuenta_contable"] == cuenta
            indices = base[mask].index

            saldo_actual = 0.0
            for i, idx in enumerate(indices):
                if i == 0:
                    saldo_actual = (
                        base.loc[idx, "saldo_inicial"]
                        + base.loc[idx, "cargos"]
                        - base.loc[idx, "abonos"]
                    )
                else:
                    base.loc[idx, "saldo_inicial"] = saldo_actual
                    saldo_actual = saldo_actual + base.loc[idx, "cargos"] - base.loc[idx, "abonos"]

                base.loc[idx, "saldo_final"] = saldo_actual

        # Convertir fechas
        base["fecha_transaccion"] = pd.to_datetime(
            base["fecha"], format="%d/%m/%Y", errors="coerce"
        )

        # Insertar en base de datos en lotes
        report(80, f"Insertando {len(base):,} registros en base de datos...")
        logger.info(f"Iniciando inserción de {len(base)} registros en lotes de {1000}")

        chunk_size = 1000
        total_insertados = 0

        for i in range(0, len(base), chunk_size):
            chunk = base.iloc[i:i + chunk_size]

            transacciones = []
            for _, row in chunk.iterrows():
                trans = Transaccion(
                    lote_id=lote_id,
                    archivo_origen=row['archivo_origen'],
                    usuario_carga=usuario,
                    cuenta_contable=row['cuenta_contable'],
                    nombre_cuenta=row['nombre_cuenta'],
                    genero=row['genero'],
                    grupo=row['grupo'],
                    rubro=row['rubro'],
                    cuenta=row['cuenta'],
                    subcuenta=row['subcuenta'],
                    dependencia=row['dependencia'],
                    unidad_responsable=row['unidad_responsable'],
                    centro_costo=row['centro_costo'],
                    proyecto_presupuestario=row['proyecto_presupuestario'],
                    fuente=row['fuente'],
                    subfuente=row['subfuente'],
                    tipo_recurso=row['tipo_recurso'],
                    partida_presupuestal=row['partida_presupuestal'],
                    fecha_transaccion=row['fecha_transaccion'],
                    poliza=row['poliza'],
                    beneficiario=row['beneficiario'],
                    descripcion=row['descripcion'],
                    orden_pago=row['orden_pago'],
                    saldo_inicial=row['saldo_inicial'],
                    cargos=row['cargos'],
                    abonos=row['abonos'],
                    saldo_final=row['saldo_final']
                )
                transacciones.append(trans)

            try:
                db.session.bulk_save_objects(transacciones)
                db.session.commit()
                logger.debug(
                    f"Lote {i // chunk_size + 1} insertado correctamente ({len(chunk)} registros)"
                )
            except Exception as e:
                logger.error(
                    f"Error insertando lote {i // chunk_size + 1}: {type(e).__name__} - {str(e)}"
                )
                logger.error(f"Traceback: {traceback.format_exc()}")
                db.session.rollback()
                raise

            total_insertados += len(chunk)
            progress_pct = 80 + int((total_insertados / len(base)) * 15)
            report(progress_pct, f"Insertados {total_insertados:,} de {len(base):,} registros")

        # Actualizar lote
        lote.total_registros = len(base)
        lote.estado = 'completado'
        lote.mensaje = f'Procesados {len(base):,} registros de {len(archivos_procesados)} archivos'
        db.session.commit()

        report(100, f"✅ Completado: {len(base):,} registros insertados en BD")

        logger.info(f"✓ Procesamiento completado: {len(base)} registros, lote_id={lote_id}")
        return lote_id, len(base)

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error fatal en procesamiento: {error_msg}")
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        lote.estado = 'error'
        lote.mensaje = error_msg
        db.session.commit()
        raise
