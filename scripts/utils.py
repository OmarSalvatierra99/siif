from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
import hashlib
import zipfile
import xml.etree.ElementTree as ET
from typing import Callable, List, Optional, Tuple
import logging
import re
import traceback
import uuid

import numpy as np
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
    ente_siglas_catalogo = db.Column(db.String(80), index=True)
    ente_nombre_catalogo = db.Column(db.String(255))
    ente_grupo_catalogo = db.Column(db.String(20), index=True)

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
    hash_registro = db.Column(db.String(64), unique=True, index=True)

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
            'ente_siglas_catalogo': self.ente_siglas_catalogo,
            'ente_nombre_catalogo': self.ente_nombre_catalogo,
            'ente_grupo_catalogo': self.ente_grupo_catalogo,
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
    tipo_archivo = db.Column(db.String(20))
    ente_siglas_catalogo = db.Column(db.String(80), index=True)
    ente_nombre_catalogo = db.Column(db.String(255))
    ente_grupo_catalogo = db.Column(db.String(20), index=True)
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
            'tipo_archivo': self.tipo_archivo,
            'ente_siglas_catalogo': self.ente_siglas_catalogo,
            'ente_nombre_catalogo': self.ente_nombre_catalogo,
            'ente_grupo_catalogo': self.ente_grupo_catalogo,
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
    dd = db.Column(db.String(10))
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
            'dd': self.dd,
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


def _norm_header_label(value):
    return re.sub(r"[^a-z0-9]+", "", _norm(value))


def _header_label_matches(value, options):
    token = _norm_header_label(value)
    if not token:
        return False

    for option in options:
        candidate = _norm_header_label(option)
        if token == candidate or token.startswith(candidate):
            return True
    return False


def _normalize_dependency_code(value):
    code = str(value or "").strip().upper().rstrip(".")
    if len(code) == 1 and code.isdigit():
        return code.zfill(2)
    return code


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


def _format_amount(val):
    try:
        return f"{float(val):.2f}"
    except Exception:
        return "0.00"


def _extract_period_start(text):
    match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", str(text or ""))
    return match.group(1) if match else ""


def _infer_account_balance_side(account_rows, tolerance=0.01):
    best_side = None
    best_diff = None

    for _, row in account_rows.iterrows():
        if "_saldo_inicial_origen_present" in account_rows.columns and not bool(row.get("_saldo_inicial_origen_present")):
            continue

        saldo_inicial = float(row.get("saldo_inicial") or 0)
        cargos = float(row.get("cargos") or 0)
        abonos = float(row.get("abonos") or 0)
        saldo_final_origen = float(row.get("saldo_final_origen") or 0)

        if abs(cargos) <= tolerance and abs(abonos) <= tolerance:
            continue

        saldo_deudor = saldo_inicial + cargos - abonos
        saldo_acreedor = saldo_inicial - cargos + abonos
        diff_deudor = abs(saldo_deudor - saldo_final_origen)
        diff_acreedor = abs(saldo_acreedor - saldo_final_origen)

        if diff_deudor <= tolerance and diff_acreedor > tolerance:
            return "deudora"
        if diff_acreedor <= tolerance and diff_deudor > tolerance:
            return "acreedora"

        current_diff = min(diff_deudor, diff_acreedor)
        if best_diff is None or current_diff < best_diff:
            best_diff = current_diff
            best_side = "deudora" if diff_deudor <= diff_acreedor else "acreedora"

    if best_side:
        return best_side

    genero = str(account_rows["genero"].iloc[0] if not account_rows.empty else "").strip()
    if genero in {"2", "3", "4", "9"}:
        return "acreedora"
    return "deudora"


def _rebuild_account_balances(base):
    if base.empty:
        return base

    sort_columns = ["cuenta_contable", "_periodo_inicio_dt", "_archivo_orden", "_orden_auxiliar"]
    base = base.sort_values(sort_columns, kind="stable").reset_index(drop=True).copy()

    saldo_inicial_values = base["saldo_inicial"].to_numpy(dtype=float, copy=True)
    cargos_values = base["cargos"].to_numpy(dtype=float, copy=False)
    abonos_values = base["abonos"].to_numpy(dtype=float, copy=False)
    saldo_final_origen_values = base["saldo_final_origen"].to_numpy(dtype=float, copy=False)
    saldo_final_values = np.zeros(len(base), dtype=float)

    if "_saldo_inicial_origen_present" in base.columns:
        has_source_initial_values = base["_saldo_inicial_origen_present"].to_numpy(dtype=bool, copy=False)
    else:
        has_source_initial_values = np.ones(len(base), dtype=bool)

    if "_saldo_final_origen_present" in base.columns:
        has_source_final_values = base["_saldo_final_origen_present"].to_numpy(dtype=bool, copy=False)
    else:
        has_source_final_values = np.zeros(len(base), dtype=bool)

    for _, account_rows in base.groupby("cuenta_contable", sort=False):
        balance_side = _infer_account_balance_side(account_rows)
        idx = account_rows.index.to_numpy(dtype=int)
        account_saldo_inicial = saldo_inicial_values[idx].copy()
        account_cargos = cargos_values[idx]
        account_abonos = abonos_values[idx]
        account_saldo_final = np.zeros(len(idx), dtype=float)

        if len(idx) == 0:
            continue

        if not has_source_initial_values[idx[0]] and has_source_final_values[idx[0]]:
            if balance_side == "acreedora":
                account_saldo_inicial[0] = round(
                    saldo_final_origen_values[idx[0]] + account_cargos[0] - account_abonos[0],
                    2,
                )
            else:
                account_saldo_inicial[0] = round(
                    saldo_final_origen_values[idx[0]] - account_cargos[0] + account_abonos[0],
                    2,
                )

        if balance_side == "acreedora":
            account_saldo_final[0] = round(
                account_saldo_inicial[0] - account_cargos[0] + account_abonos[0],
                2,
            )
            for pos in range(1, len(idx)):
                account_saldo_inicial[pos] = round(account_saldo_final[pos - 1], 2)
                account_saldo_final[pos] = round(
                    account_saldo_inicial[pos] - account_cargos[pos] + account_abonos[pos],
                    2,
                )
        else:
            account_saldo_final[0] = round(
                account_saldo_inicial[0] + account_cargos[0] - account_abonos[0],
                2,
            )
            for pos in range(1, len(idx)):
                account_saldo_inicial[pos] = round(account_saldo_final[pos - 1], 2)
                account_saldo_final[pos] = round(
                    account_saldo_inicial[pos] + account_cargos[pos] - account_abonos[pos],
                    2,
                )

        saldo_inicial_values[idx] = account_saldo_inicial
        saldo_final_values[idx] = account_saldo_final

    base["saldo_inicial"] = np.round(saldo_inicial_values, 2)
    base["saldo_final"] = np.round(saldo_final_values, 2)

    return base


def _detect_fixed_auxiliar_layout(raw, header_row_idx):
    if header_row_idx is None or raw.shape[1] < 9:
        return None

    header_row = raw.iloc[header_row_idx]
    required_headers = {
        0: ["fecha"],
        1: ["poliza", "póliza"],
        4: ["o.p.", "o.p", "op", "orden pago", "orden de pago"],
        5: ["saldo inicial"],
        6: ["cargos", "cargo", "debe"],
        7: ["abonos", "abono", "haber"],
        8: ["saldo final"],
    }

    for col_idx, options in required_headers.items():
        if not _header_label_matches(header_row.iloc[col_idx], options):
            return None

    return {
        "beneficiario": 2,
        "descripcion": 3,
        "orden_pago": 4,
        "saldo_inicial": 5,
        "cargos": 6,
        "abonos": 7,
        "saldo_final": 8,
    }


CONTABLE_GENEROS = {"1", "2", "3", "4", "5"}


def _build_balance_error_message(
    total_cargos,
    total_abonos,
    balance_diff,
    invalid_polizas,
    scope_label="La carga contable",
):
    parts = [
        (
            f"{scope_label} esta desbalanceada. "
            f"Cargos={total_cargos:,.2f} Abonos={total_abonos:,.2f} "
            f"Diferencia={balance_diff:,.2f}"
        )
    ]

    if invalid_polizas:
        detalles = []
        for row in invalid_polizas[:10]:
            detalles.append(
                f"{row['fecha']} | {row['poliza']}: "
                f"Cargos={row['cargos']:,.2f} Abonos={row['abonos']:,.2f} "
                f"Diff={row['diff']:,.2f}"
            )
        if len(invalid_polizas) > 10:
            detalles.append(f"{len(invalid_polizas) - 10} poliza(s) adicional(es)")
        parts.append("Polizas desbalanceadas: " + " ; ".join(detalles))

    return " ".join(parts)


def _build_rollforward_error_message(invalid_rows):
    parts = [
        (
            "La secuencia de saldos del auxiliar no coincide con los saldos "
            "finales reportados en el origen."
        )
    ]

    detalles = []
    for row in invalid_rows[:10]:
        fecha = str(row.get("fecha") or "").strip() or "sin fecha"
        poliza = str(row.get("poliza") or "").strip() or "sin poliza"
        detalles.append(
            f"{row['archivo_origen']} | {row['cuenta_contable']} | {fecha} | {poliza}: "
            f"Calculado={row['saldo_final']:,.2f} "
            f"Origen={row['saldo_final_origen']:,.2f} "
            f"Diff={row['diff']:,.2f}"
        )

    if len(invalid_rows) > 10:
        detalles.append(f"{len(invalid_rows) - 10} movimiento(s) adicional(es)")

    if detalles:
        parts.append("Ejemplos: " + " ; ".join(detalles))

    return " ".join(parts)


def _validate_reconstructed_rollforwards(base, lote_id, tolerance=0.3):
    validation_rows = base[base["_saldo_final_origen_present"]].copy()
    if validation_rows.empty:
        logger.info(f"Sin saldos finales origen para validar en lote {lote_id}")
        return

    validation_rows["diff"] = (
        validation_rows["saldo_final"] - validation_rows["saldo_final_origen"]
    ).abs()
    invalid_rows = validation_rows[validation_rows["diff"] > tolerance]

    if invalid_rows.empty:
        logger.info(
            f"Rollforward OK en lote {lote_id}: "
            f"{len(validation_rows):,} movimientos conciliados contra el auxiliar"
        )
        return

    invalid_rows = invalid_rows.sort_values("diff", ascending=False)
    logger.error(
        f"Inconsistencia de saldos detectada en lote {lote_id}: "
        f"{len(invalid_rows):,} movimiento(s) con diferencia"
    )
    raise ValueError(
        _build_rollforward_error_message(invalid_rows.to_dict("records"))
    )


def _validate_contable_balance(base, lote_id, tolerance=0.01):
    contable = base[base["genero"].isin(CONTABLE_GENEROS)].copy()
    if contable.empty:
        logger.info(
            f"Sin movimientos contables de generos 1-5 en lote {lote_id}; "
            "se omite validación de pólizas balanceadas"
        )
        return

    total_cargos = float(contable["cargos"].sum())
    total_abonos = float(contable["abonos"].sum())
    balance_diff = total_cargos - total_abonos

    polizas = contable.copy()
    polizas["poliza"] = polizas["poliza"].fillna("").astype(str).str.strip()
    polizas["fecha"] = polizas["fecha"].fillna("").astype(str).str.strip()
    polizas = polizas[polizas["poliza"] != ""]

    invalid_polizas = []
    if not polizas.empty:
        poliza_totals = (
            polizas.groupby(["fecha", "poliza"], sort=False)[["cargos", "abonos"]]
            .sum()
            .reset_index()
        )
        poliza_totals["diff"] = poliza_totals["cargos"] - poliza_totals["abonos"]
        invalid_polizas = (
            poliza_totals[poliza_totals["diff"].abs() > tolerance]
            .sort_values("diff", key=lambda series: series.abs(), ascending=False)
            .to_dict("records")
        )

    if abs(balance_diff) <= tolerance and not invalid_polizas:
        logger.info(
            f"Validación contable OK en lote {lote_id}: "
            f"Cargos={total_cargos:,.2f} Abonos={total_abonos:,.2f}"
        )
        return

    logger.error(
        f"Desbalance contable detectado en lote {lote_id}: "
        f"Cargos={total_cargos:,.2f} Abonos={total_abonos:,.2f} "
        f"Diferencia={balance_diff:,.2f}"
    )
    for arch, grp in contable.groupby("archivo_origen"):
        fc = float(grp["cargos"].sum())
        fa = float(grp["abonos"].sum())
        logger.info(f"  {arch}: Cargos={fc:,.2f} Abonos={fa:,.2f} Diff={fc - fa:,.2f}")

    raise ValueError(
        _build_balance_error_message(
            total_cargos,
            total_abonos,
            balance_diff,
            invalid_polizas,
            scope_label="La carga contable de generos 1-5",
        )
    )


def _seed_historical_opening_balances(base, ente_siglas, tolerance=0.3):
    if base.empty or not ente_siglas:
        return base

    sort_columns = ["cuenta_contable", "_periodo_inicio_dt", "_archivo_orden", "_orden_auxiliar"]
    base = base.sort_values(sort_columns, kind="stable").copy()
    adjusted_accounts = []

    for cuenta_contable, account_rows in base.groupby("cuenta_contable", sort=False):
        first_idx = account_rows.index[0]
        first_row = base.loc[first_idx]
        first_date = first_row.get("fecha_transaccion")
        if pd.isna(first_date):
            continue

        saldo_final_origen = float(first_row.get("saldo_final_origen") or 0)
        if not bool(first_row.get("_saldo_final_origen_present")):
            continue

        saldo_inicial_actual = float(first_row.get("saldo_inicial") or 0)
        saldo_inicial_present = bool(first_row.get("_saldo_inicial_origen_present"))
        if saldo_inicial_present and abs(saldo_inicial_actual) > tolerance:
            continue

        cargos = float(first_row.get("cargos") or 0)
        abonos = float(first_row.get("abonos") or 0)
        genero = str(first_row.get("genero") or "").strip()
        balance_side = "acreedora" if genero in {"2", "3", "4", "9"} else "deudora"

        if balance_side == "acreedora":
            saldo_final_desde_actual = round(saldo_inicial_actual - cargos + abonos, 2)
        else:
            saldo_final_desde_actual = round(saldo_inicial_actual + cargos - abonos, 2)

        if abs(saldo_final_desde_actual - saldo_final_origen) <= tolerance:
            continue

        previous = (
            db.session.query(
                Transaccion.saldo_final,
                Transaccion.fecha_transaccion,
                Transaccion.id,
            )
            .filter(
                Transaccion.ente_siglas_catalogo == ente_siglas,
                Transaccion.cuenta_contable == cuenta_contable,
                Transaccion.fecha_transaccion < first_date,
            )
            .order_by(Transaccion.fecha_transaccion.desc(), Transaccion.id.desc())
            .first()
        )
        if not previous:
            continue

        saldo_inicial_historico = round(float(previous[0] or 0), 2)
        if balance_side == "acreedora":
            saldo_final_desde_historico = round(saldo_inicial_historico - cargos + abonos, 2)
        else:
            saldo_final_desde_historico = round(saldo_inicial_historico + cargos - abonos, 2)

        if abs(saldo_final_desde_historico - saldo_final_origen) > tolerance:
            continue

        base.loc[first_idx, "saldo_inicial"] = saldo_inicial_historico
        base.loc[first_idx, "_saldo_inicial_origen_present"] = True
        base.loc[first_idx, "_saldo_inicial_origen_text"] = f"{saldo_inicial_historico:.2f}"
        adjusted_accounts.append(
            (
                cuenta_contable,
                saldo_inicial_historico,
                saldo_final_origen,
                first_row.get("fecha"),
                first_row.get("poliza"),
            )
        )

    if adjusted_accounts:
        logger.info(
            "Saldos iniciales historicos aplicados para %s cuenta(s) del ente %s",
            len(adjusted_accounts),
            ente_siglas,
        )
        for cuenta_contable, saldo_inicial_historico, saldo_final_origen, fecha, poliza in adjusted_accounts[:10]:
            logger.info(
                "  %s | %s | %s: saldo inicial historico=%0.2f -> saldo final origen=%0.2f",
                cuenta_contable,
                fecha,
                poliza,
                saldo_inicial_historico,
                saldo_final_origen,
            )
    return base


def _hash_transaccion_row(row):
    # Include running balances so repeated source lines remain distinct after normalization.
    parts = [
        _norm(row.get("archivo_origen")),
        _norm(row.get("cuenta_contable")),
        _norm(row.get("nombre_cuenta")),
        _norm(row.get("genero")),
        _norm(row.get("grupo")),
        _norm(row.get("rubro")),
        _norm(row.get("cuenta")),
        _norm(row.get("subcuenta")),
        _norm(row.get("dependencia")),
        _norm(row.get("unidad_responsable")),
        _norm(row.get("centro_costo")),
        _norm(row.get("proyecto_presupuestario")),
        _norm(row.get("fuente")),
        _norm(row.get("subfuente")),
        _norm(row.get("tipo_recurso")),
        _norm(row.get("partida_presupuestal")),
        _norm(row.get("poliza")),
        _norm(row.get("beneficiario")),
        _norm(row.get("descripcion")),
        _norm(row.get("orden_pago")),
        _norm(row.get("ente_siglas_catalogo")),
        _norm(row.get("ente_grupo_catalogo")),
        _format_amount(row.get("saldo_inicial")),
        _format_amount(row.get("cargos")),
        _format_amount(row.get("abonos")),
        _format_amount(row.get("saldo_final")),
    ]

    fecha = row.get("fecha_transaccion")
    if pd.isna(fecha):
        parts.append("")
    else:
        try:
            parts.append(fecha.strftime("%Y-%m-%d"))
        except Exception:
            parts.append(str(fecha))

    fingerprint = "|".join(parts).encode("utf-8")
    return hashlib.sha256(fingerprint).hexdigest()


_STRICT_NS_MAP = {
    "http://purl.oclc.org/ooxml/spreadsheetml/main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://purl.oclc.org/ooxml/officeDocument/relationships": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://purl.oclc.org/ooxml/drawingml/main": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://purl.oclc.org/ooxml/officeDocument/sharedTypes": "http://schemas.openxmlformats.org/officeDocument/2006/sharedTypes",
}


def _convert_strict_ooxml(file_bytes: bytes) -> bytes:
    """Convierte archivos OOXML Strict al formato Transitional que soporta openpyxl."""
    src = BytesIO(file_bytes)
    dst = BytesIO()
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml") or item.filename.endswith(".rels"):
                try:
                    text = data.decode("utf-8")
                    for old, new in _STRICT_NS_MAP.items():
                        text = text.replace(old, new)
                    text = re.sub(r' conformance="strict"', "", text)
                    data = text.encode("utf-8")
                except Exception:
                    pass
            zout.writestr(item, data)
    return dst.getvalue()


def _is_strict_ooxml(file_bytes: bytes) -> bool:
    """Detecta si un archivo xlsx usa el formato OOXML Strict."""
    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
            if "xl/workbook.xml" in zf.namelist():
                content = zf.read("xl/workbook.xml").decode("utf-8", errors="ignore")
                return "purl.oclc.org/ooxml" in content
    except Exception:
        pass
    return False


def _read_one_excel(file_data):
    """Lee un archivo Excel y extrae las transacciones"""
    filename, file_content = file_data
    logger.info(f"Iniciando lectura de archivo: {filename}")
    file_content.seek(0)

    try:
        raw_bytes = file_content.read()
        is_strict = _is_strict_ooxml(raw_bytes)
        raw = None

        if is_strict:
            logger.info(
                f"Detectado formato OOXML Strict en {filename}, "
                "usando lector XML optimizado..."
            )
            raw = _read_xlsx_xml_to_dataframe(BytesIO(raw_bytes))

        if raw is None:
            read_bytes = raw_bytes
            if is_strict:
                logger.info(
                    f"Fallback a conversion OOXML Strict en {filename} "
                    "para compatibilidad con openpyxl..."
                )
                read_bytes = _convert_strict_ooxml(raw_bytes)
            raw = pd.read_excel(BytesIO(read_bytes), header=None, dtype=str, engine="openpyxl")

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
        row_text = _norm(" ".join(raw.iloc[idx].fillna("").astype(str)))
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

    fixed_layout = _detect_fixed_auxiliar_layout(raw, header_row_idx)
    if fixed_layout:
        _pos_benef = fixed_layout["beneficiario"]
        _pos_desc = fixed_layout["descripcion"]
        _pos_op = fixed_layout["orden_pago"]
        _pos_si = fixed_layout["saldo_inicial"]
        _pos_cargos = fixed_layout["cargos"]
        _pos_abonos = fixed_layout["abonos"]
        _pos_sf = fixed_layout["saldo_final"]
        _use_mapped = True
        logger.info(
            f"Detectado layout auxiliar fijo de 9 columnas en {filename}: "
            f"op=col{_pos_op} si=col{_pos_si} cargos=col{_pos_cargos} "
            f"abonos=col{_pos_abonos} sf=col{_pos_sf}"
        )
    else:
        # --- Position-based column mapping from header row ---
        header_cells = raw.iloc[header_row_idx].fillna("").astype(str)
        _hdr_map = {}
        for _ci in range(len(header_cells)):
            _cn = header_cells.iloc[_ci]
            if str(_cn).strip():
                _hdr_map[_ci] = _cn
        # Also merge sub-header row (beneficiario, descripcion)
        if start_idx == header_row_idx + 2:
            sub_cells = raw.iloc[header_row_idx + 1].fillna("").astype(str)
            for _ci in range(len(sub_cells)):
                _cn = sub_cells.iloc[_ci]
                if str(_cn).strip() and _ci not in _hdr_map:
                    _hdr_map[_ci] = _cn

        def _find_hdr_pos(options):
            for ci, cn in _hdr_map.items():
                if _header_label_matches(cn, options):
                    return ci
            return None

        _pos_op = _find_hdr_pos(["o.p.", "o.p", "op", "orden pago", "orden de pago"])
        _pos_si = _find_hdr_pos(["saldo inicial"])
        _pos_cargos = _find_hdr_pos(["cargos", "cargo", "debe"])
        _pos_abonos = _find_hdr_pos(["abonos", "abono", "haber"])
        _pos_sf = _find_hdr_pos(["saldo final"])
        _pos_benef = _find_hdr_pos(["beneficiario", "proveedor"])
        _pos_desc = _find_hdr_pos(["descripcion", "concepto", "detalle"])
        _use_mapped = _pos_cargos is not None and _pos_abonos is not None
        if _use_mapped:
            logger.info(
                f"Usando mapeo por encabezado en {filename}: "
                f"cargos=col{_pos_cargos} abonos=col{_pos_abonos} "
                f"op=col{_pos_op} si=col{_pos_si} sf=col{_pos_sf}"
            )

    # Procesar todas las filas
    records = []
    current_cuenta = None
    current_nombre = None
    current_saldo_inicial = None
    current_period_start = ""

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
            current_period_start = ""
            continue

        # Detectar línea de saldo inicial
        row_text_full = " ".join(row.fillna("").astype(str))
        row_text_upper = row_text_full.upper()
        if "SALDO INICIAL CUENTA" in row_text_upper and current_cuenta:
            period_start = _extract_period_start(row_text_full)
            if period_start:
                current_period_start = period_start
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

            def _cell(ci):
                if ci is None or ci >= len(row):
                    return ""
                v = row.iloc[ci]
                return "" if pd.isna(v) else str(v).strip()

            if _use_mapped:
                # ── Position-based extraction (reliable) ──
                beneficiario = _cell(_pos_benef)
                descripcion = _cell(_pos_desc)
                op = _cell(_pos_op)
                saldo_inicial = _cell(_pos_si) or (current_saldo_inicial if current_saldo_inicial else "")
                cargos = _cell(_pos_cargos)
                abonos = _cell(_pos_abonos)
                saldo_final = _cell(_pos_sf)

                # Need at least one non-empty monetary value
                if not cargos and not abonos and not saldo_final:
                    continue
            else:
                # ── Heuristic-based extraction (fallback) ──
                col_data = []
                for i in range(2, min(len(row), 15)):
                    val = _cell(i)
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
                "periodo_inicio": current_period_start or fecha,
                "orden_auxiliar": idx,
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


def _xml_local_name(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _estimate_stream_size(file_obj):
    try:
        current = file_obj.tell()
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(current)
        return size
    except Exception:
        return 0


def _extract_xlsx_shared_strings(zip_file):
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []

    shared = []

    try:
        with zip_file.open("xl/sharedStrings.xml") as shared_file:
            current_text = []
            for event, elem in ET.iterparse(shared_file, events=("start", "end")):
                tag = _xml_local_name(elem.tag)

                if event == "start" and tag == "si":
                    current_text = []
                    continue

                if event != "end":
                    continue

                if tag == "t":
                    current_text.append(elem.text or "")
                elif tag == "si":
                    shared.append("".join(current_text))
                    elem.clear()

        return shared
    except Exception:
        return []


def _extract_xlsx_cell_value(cell_elem, shared_strings):
    cell_type = cell_elem.attrib.get("t")

    if cell_type == "inlineStr":
        inline_text = []
        for child in cell_elem.iter():
            if _xml_local_name(child.tag) == "t":
                inline_text.append(child.text or "")
        return "".join(inline_text)

    value = ""
    for child in cell_elem:
        if _xml_local_name(child.tag) == "v":
            value = child.text or ""
            break

    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except Exception:
            return value

    return value


def _iter_xlsx_sheet_rows(zip_file, sheet_path, shared_strings):
    max_col_idx = 0

    with zip_file.open(sheet_path) as sheet_file:
        for event, elem in ET.iterparse(sheet_file, events=("end",)):
            if _xml_local_name(elem.tag) != "row":
                continue

            cells = {}
            for child in elem:
                if _xml_local_name(child.tag) != "c":
                    continue

                ref = child.attrib.get("r", "")
                letters = "".join(ch for ch in ref if ch.isalpha())
                if not letters:
                    continue

                col_idx = _col_to_index(letters)
                value = _extract_xlsx_cell_value(child, shared_strings)
                if value == "":
                    continue

                max_col_idx = max(max_col_idx, col_idx)
                cells[col_idx] = value

            if cells:
                yield cells, max_col_idx

            elem.clear()


def _get_xlsx_sheet_candidates(zip_file):
    return sorted(
        [
            name
            for name in zip_file.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        ],
        key=lambda name: int(re.search(r"sheet(\d+)\.xml$", name).group(1))
    )


def _read_xlsx_xml_sheet_frames(file_content):
    file_content.seek(0)
    try:
        z = zipfile.ZipFile(file_content)
    except Exception:
        return

    sheet_candidates = _get_xlsx_sheet_candidates(z)
    if not sheet_candidates:
        return

    shared = _extract_xlsx_shared_strings(z)

    for sheet_path in sheet_candidates:
        row_dicts = []
        max_col_idx = 0

        try:
            for cells, current_max_col_idx in _iter_xlsx_sheet_rows(z, sheet_path, shared):
                row_dicts.append({idx - 1: value for idx, value in cells.items()})
                max_col_idx = max(max_col_idx, current_max_col_idx)
        except Exception:
            continue

        if not row_dicts or max_col_idx == 0:
            continue

        frame = pd.DataFrame.from_records(row_dicts)
        frame = frame.reindex(columns=range(max_col_idx), fill_value="").fillna("")
        yield sheet_path, frame.astype(str)


def _read_xlsx_xml_to_dataframe(file_content):
    for _, frame in _read_xlsx_xml_sheet_frames(file_content):
        return frame
    return None


def _read_one_excel_macro_xml(zip_file, sheet_path, shared_strings, filename):
    def _clean_cell(value):
        if pd.isna(value):
            return ""
        return str(value).strip()

    header_positions = None
    periodo_inicio_base = ""
    records = []

    for row_number, (cells, current_max_col_idx) in enumerate(
        _iter_xlsx_sheet_rows(zip_file, sheet_path, shared_strings),
        start=1,
    ):
        if header_positions is None:
            if row_number > 30:
                break

            raw_headers = [
                _clean_cell(cells.get(col_idx, ""))
                for col_idx in range(1, current_max_col_idx + 1)
            ]
            row_text = " ".join(raw_headers).lower()
            if not ("cuenta" in row_text and "fecha" in row_text and ("poliza" in row_text or "póliza" in row_text)):
                continue

            headers = _unique_headers(raw_headers)
            col_map = {col: _norm(col) for col in headers}
            header_positions = {header: idx for idx, header in enumerate(headers, start=1)}

            cuenta_col = _select_column(col_map, ["cuenta contable", "cuenta", "cta contable"])
            if not cuenta_col:
                logger.warning(f"No se encontró columna de cuenta en {filename} ({sheet_path})")
                return None

            header_positions = {
                "cuenta": header_positions.get(cuenta_col),
                "nombre": header_positions.get(_select_column(col_map, ["nombre cuenta", "nombre de la cuenta", "descripcion cuenta", "nombre"])),
                "fecha": header_positions.get(_select_column(col_map, ["fecha", "fecha transaccion", "fecha movimiento"])),
                "poliza": header_positions.get(_select_column(col_map, ["poliza", "póliza", "no poliza", "no. poliza", "numero poliza"])),
                "beneficiario": header_positions.get(_select_column(col_map, ["beneficiario", "proveedor", "razon social"])),
                "descripcion": header_positions.get(_select_column(col_map, ["descripcion", "concepto", "detalle", "observaciones"])),
                "op": header_positions.get(_select_column(col_map, ["o.p.", "op", "orden pago", "orden de pago", "orden_pago"])),
                "saldo_inicial": header_positions.get(_select_column(col_map, ["saldo inicial", "saldo inicial cuenta", "saldo ini"])),
                "cargos": header_positions.get(_select_column(col_map, ["cargos", "cargo", "debe"])),
                "abonos": header_positions.get(_select_column(col_map, ["abonos", "abono", "haber"])),
                "saldo_final": header_positions.get(_select_column(col_map, ["saldo final", "saldo final cuenta", "saldo"])),
            }
            continue

        cuenta_pos = header_positions.get("cuenta")
        fecha_pos = header_positions.get("fecha")
        if not cuenta_pos or not fecha_pos:
            continue

        cuenta_val = _clean_cell(cells.get(cuenta_pos, ""))
        if not cuenta_val:
            continue

        fecha_raw = cells.get(fecha_pos, "")
        if pd.isna(fecha_raw) or str(fecha_raw).strip() == "":
            continue

        try:
            fecha = pd.to_datetime(fecha_raw).strftime("%d/%m/%Y")
        except Exception:
            fecha = _clean_cell(fecha_raw)

        if not periodo_inicio_base:
            periodo_inicio_base = fecha

        nombre_val = _clean_cell(cells.get(header_positions.get("nombre"), ""))
        if not nombre_val and " - " in cuenta_val:
            parts = cuenta_val.split(" - ", 1)
            cuenta_val = parts[0].strip()
            nombre_val = parts[1].strip()

        records.append({
            "cuenta_contable": cuenta_val,
            "nombre_cuenta": nombre_val,
            "fecha": fecha,
            "poliza": _clean_cell(cells.get(header_positions.get("poliza"), "")),
            "beneficiario": _clean_cell(cells.get(header_positions.get("beneficiario"), "")),
            "descripcion": _clean_cell(cells.get(header_positions.get("descripcion"), "")),
            "orden_pago": _clean_cell(cells.get(header_positions.get("op"), "")),
            "saldo_inicial": _clean_cell(cells.get(header_positions.get("saldo_inicial"), "")),
            "cargos": _clean_cell(cells.get(header_positions.get("cargos"), "")),
            "abonos": _clean_cell(cells.get(header_positions.get("abonos"), "")),
            "saldo_final": _clean_cell(cells.get(header_positions.get("saldo_final"), "")),
            "periodo_inicio": periodo_inicio_base or fecha,
            "orden_auxiliar": len(records),
        })

        if records and len(records) % 50000 == 0:
            logger.info(
                "Extracción macro XML en %s (%s): %s movimientos",
                filename,
                sheet_path,
                len(records),
            )

    if not records:
        return None

    return pd.DataFrame(records)


def _read_one_excel_macro(file_data):
    """Lee archivos ya procesados por macro y normaliza columnas"""
    filename, file_content = file_data
    logger.info(f"Iniciando lectura macro de archivo: {filename}")
    file_content.seek(0)

    def build_from_raw(raw):
        if raw.empty or len(raw) < 2:
            return None

        def _clean_cell(value):
            if pd.isna(value):
                return ""
            return str(value).strip()

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

        periodo_inicio_base = ""
        if fecha_col:
            for raw_value in data[fecha_col].tolist():
                if pd.isna(raw_value) or str(raw_value).strip() == "":
                    continue
                try:
                    periodo_inicio_base = pd.to_datetime(raw_value).strftime("%d/%m/%Y")
                except Exception:
                    periodo_inicio_base = str(raw_value).strip()
                if periodo_inicio_base:
                    break

        records = []
        for order_idx, (_, row) in enumerate(data.iterrows()):
            cuenta_val = _clean_cell(row.get(cuenta_col, "")) if cuenta_col else ""
            if not cuenta_val:
                continue

            nombre_val = _clean_cell(row.get(nombre_col, "")) if nombre_col else ""
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
                fecha = _clean_cell(fecha_raw)

            poliza = _clean_cell(row.get(poliza_col, "")) if poliza_col else ""
            beneficiario = _clean_cell(row.get(beneficiario_col, "")) if beneficiario_col else ""
            descripcion = _clean_cell(row.get(descripcion_col, "")) if descripcion_col else ""
            op = _clean_cell(row.get(op_col, "")) if op_col else ""
            saldo_inicial = _clean_cell(row.get(saldo_inicial_col, "")) if saldo_inicial_col else ""
            cargos = _clean_cell(row.get(cargos_col, "")) if cargos_col else ""
            abonos = _clean_cell(row.get(abonos_col, "")) if abonos_col else ""
            saldo_final = _clean_cell(row.get(saldo_final_col, "")) if saldo_final_col else ""

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
                "periodo_inicio": periodo_inicio_base or fecha,
                "orden_auxiliar": order_idx,
            })

        if not records:
            return None

        return pd.DataFrame(records)

    try:
        raw_bytes = file_content.read()
        is_strict = _is_strict_ooxml(raw_bytes)
        if is_strict:
            logger.info(
                f"Detectado formato OOXML Strict en {filename}, "
                "usando lector XML optimizado para archivos macro..."
            )
            with zipfile.ZipFile(BytesIO(raw_bytes)) as zf:
                shared = _extract_xlsx_shared_strings(zf)
                for sheet_path in _get_xlsx_sheet_candidates(zf):
                    logger.info(
                        f"Probando hoja XML {sheet_path} en {filename}"
                    )
                    df = _read_one_excel_macro_xml(zf, sheet_path, shared, filename)
                    if df is not None and not df.empty:
                        logger.info(
                            f"✓ Extraídas {len(df)} transacciones macro de {filename} "
                            f"({sheet_path}, xml)"
                        )
                        return df, filename

        if is_strict:
            logger.info(f"Fallback a conversion OOXML Strict en {filename} para openpyxl...")
            raw_bytes = _convert_strict_ooxml(raw_bytes)
        xl = pd.ExcelFile(BytesIO(raw_bytes), engine="openpyxl")
        sheets = xl.sheet_names
    except Exception as e:
        logger.error(f"Error al leer archivo macro {filename}: {type(e).__name__} - {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        sheets = []
        xl = None

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
    tipo_archivo: str = "auxiliar",
    enforce_contable_balance: bool = True,
    seed_historical_opening_balances: bool = False,
    expected_dependency: Optional[str] = None,
    selected_ente: Optional[str] = None,
    selected_ente_siglas: Optional[str] = None,
    selected_ente_nombre: Optional[str] = None,
    selected_ente_grupo: Optional[str] = None,
):
    """
    Procesa archivos Excel y guarda en base de datos
    Retorna el lote_id para tracking
    """
    def report(p, m, current_file=None):
        if progress_callback:
            progress_callback(p, m, current_file)
        else:
            print(f"[{p}%] {m}")

    lote_id = str(uuid.uuid4())
    expected_dependency = _normalize_dependency_code(expected_dependency)
    selected_ente_siglas = str(selected_ente_siglas or "").strip()
    selected_ente_nombre = str(selected_ente_nombre or "").strip()
    selected_ente_grupo = str(selected_ente_grupo or "").strip()
    file_sizes = [_estimate_stream_size(file_info[1]) for file_info in file_list]
    total_input_bytes = sum(file_sizes)
    max_input_bytes = max(file_sizes, default=0)
    worker_count = min(4, len(file_list))

    if max_input_bytes >= 20 * 1024 * 1024 or total_input_bytes >= 40 * 1024 * 1024:
        worker_count = 1

    # Crear registro de lote
    lote = LoteCarga(
        lote_id=lote_id,
        usuario=usuario,
        archivos=[f[0] for f in file_list],
        tipo_archivo=tipo_archivo,
        ente_siglas_catalogo=selected_ente_siglas,
        ente_nombre_catalogo=selected_ente_nombre,
        ente_grupo_catalogo=selected_ente_grupo,
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
        total_files = len(file_list)
        completed_files = 0
        file_order = {file_info[0]: idx for idx, file_info in enumerate(file_list)}

        reader = _read_one_excel_macro if tipo_archivo == "macro" else _read_one_excel
        logger.info(
            f"Procesando lote {lote_id} con {worker_count} worker(s). "
            f"Tamaño total={total_input_bytes:,} bytes, archivo mayor={max_input_bytes:,} bytes"
        )
        with ThreadPoolExecutor(max_workers=worker_count) as ex:
            futures = {ex.submit(reader, f): f for f in file_list}
            for f in as_completed(futures):
                completed_files += 1
                try:
                    df, filename = f.result()
                    if not df.empty:
                        df['archivo_origen'] = filename
                        df["_archivo_orden"] = file_order.get(filename, completed_files - 1)
                        frames.append(df)
                        archivos_procesados.append(filename)
                        logger.info(f"Archivo procesado exitosamente: {filename}")
                        progress_pct = 5 + int((completed_files / total_files) * 20)
                        report(progress_pct, f"Archivo procesado: {filename}", filename)
                    else:
                        archivos_fallidos.append(filename)
                        logger.warning(f"Archivo no generó registros: {filename}")
                        progress_pct = 5 + int((completed_files / total_files) * 20)
                        report(progress_pct, f"Archivo sin registros: {filename}", filename)
                except Exception as e:
                    file_info = futures[f]
                    logger.error(
                        f"Error procesando archivo {file_info[0]}: {type(e).__name__} - {str(e)}"
                    )
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    archivos_fallidos.append(file_info[0])
                    progress_pct = 5 + int((completed_files / total_files) * 20)
                    report(progress_pct, f"Error en archivo: {file_info[0]}", file_info[0])
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
        base["ente_siglas_catalogo"] = selected_ente_siglas
        base["ente_nombre_catalogo"] = selected_ente_nombre
        base["ente_grupo_catalogo"] = selected_ente_grupo

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
        base["dependencia"] = base["dependencia"].apply(_normalize_dependency_code)

        if expected_dependency:
            report(40, "Validando selección del Catálogo General...")
            dependencias_por_archivo = (
                base.groupby("archivo_origen")["dependencia"]
                .apply(lambda series: sorted({code for code in series if code}))
                .to_dict()
            )
            archivos_invalidos = []
            for filename, detected_codes in dependencias_por_archivo.items():
                if not detected_codes or any(code != expected_dependency for code in detected_codes):
                    archivos_invalidos.append((filename, detected_codes))

            if archivos_invalidos:
                selected_label = selected_ente or "el ente seleccionado"
                detalles = []
                for filename, detected_codes in archivos_invalidos[:6]:
                    detected_text = ", ".join(detected_codes) if detected_codes else "sin dependencia identificada"
                    detalles.append(f"{filename}: {detected_text}")
                if len(archivos_invalidos) > 6:
                    detalles.append(f"{len(archivos_invalidos) - 6} archivo(s) adicional(es)")

                error_msg = (
                    f"Los archivos no corresponden a {selected_label}. "
                    f"Dependencia esperada: {expected_dependency}. "
                    f"Detectadas: {' | '.join(detalles)}"
                )
                logger.error(error_msg)
                lote.estado = 'error'
                lote.mensaje = error_msg
                db.session.commit()
                raise ValueError(error_msg)

        # Convertir columnas monetarias
        report(50, "Convirtiendo valores monetarios...")
        base["_saldo_inicial_origen_text"] = base["saldo_inicial"].fillna("").astype(str).str.strip()
        base["_saldo_final_origen_text"] = base["saldo_final"].fillna("").astype(str).str.strip()
        base["saldo_inicial"] = _to_numeric_fast(base["saldo_inicial"]).astype(float)
        base["cargos"] = _to_numeric_fast(base["cargos"]).astype(float)
        base["abonos"] = _to_numeric_fast(base["abonos"]).astype(float)
        base["_saldo_inicial_origen_present"] = base["_saldo_inicial_origen_text"] != ""
        base["saldo_final_origen"] = _to_numeric_fast(base["saldo_final"]).astype(float)
        base["_saldo_final_origen_present"] = base["_saldo_final_origen_text"] != ""
        for money_col in ["saldo_inicial", "cargos", "abonos", "saldo_final_origen"]:
            base[money_col] = base[money_col].round(2)
        base["_archivo_orden"] = pd.to_numeric(base.get("_archivo_orden", 0), errors="coerce").fillna(0).astype(int)
        base["_orden_auxiliar"] = pd.to_numeric(base.get("orden_auxiliar", 0), errors="coerce").fillna(0).astype(int)
        periodo_inicio_series = base["periodo_inicio"] if "periodo_inicio" in base.columns else base["fecha"]
        base["_periodo_inicio_dt"] = pd.to_datetime(
            periodo_inicio_series,
            format="%d/%m/%Y",
            errors="coerce"
        )
        base["fecha_transaccion"] = pd.to_datetime(
            base["fecha"], format="%d/%m/%Y", errors="coerce"
        )

        if seed_historical_opening_balances:
            report(55, "Sembrando saldos iniciales desde historial...")
            base = _seed_historical_opening_balances(
                base,
                selected_ente_siglas,
            )

        # Reconstruir el auxiliar en orden estable y respetando la naturaleza de la cuenta.
        report(60, "Calculando saldos acumulativos...")
        base = _rebuild_account_balances(base)

        report(65, "Validando integridad del auxiliar...")
        _validate_reconstructed_rollforwards(base, lote_id)
        if enforce_contable_balance:
            _validate_contable_balance(base, lote_id)
        else:
            logger.info(
                f"Se omite validación contable de cargos/abonos para lote {lote_id}"
            )

        # Generar hash por registro para evitar duplicados
        report(70, "Generando firmas de registros...")
        base["hash_registro"] = base.apply(_hash_transaccion_row, axis=1)

        total_before_dedupe = len(base)
        base = base.drop_duplicates(subset=["hash_registro"])

        existing_hashes = set()
        hash_list = base["hash_registro"].dropna().unique().tolist()
        for i in range(0, len(hash_list), 900):
            batch = hash_list[i:i + 900]
            existing_hashes.update(
                h for (h,) in db.session.query(Transaccion.hash_registro)
                .filter(Transaccion.hash_registro.in_(batch))
                .all()
            )

        if existing_hashes:
            base = base[~base["hash_registro"].isin(existing_hashes)]

        skipped_duplicates = total_before_dedupe - len(base)

        if base.empty:
            lote.total_registros = 0
            lote.estado = 'completado'
            lote.mensaje = "No se insertaron registros nuevos (todos duplicados)."
            db.session.commit()
            report(100, "✅ No se insertaron registros nuevos (todos duplicados).")
            return lote_id, 0

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
                    ente_siglas_catalogo=row['ente_siglas_catalogo'],
                    ente_nombre_catalogo=row['ente_nombre_catalogo'],
                    ente_grupo_catalogo=row['ente_grupo_catalogo'],
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
                    saldo_final=row['saldo_final'],
                    hash_registro=row['hash_registro']
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
        if skipped_duplicates:
            lote.mensaje = (
                f'Procesados {len(base):,} registros nuevos de {len(archivos_procesados)} archivos '
                f'({skipped_duplicates:,} duplicados omitidos)'
            )
        else:
            lote.mensaje = (
                f'Procesados {len(base):,} registros de {len(archivos_procesados)} archivos'
            )
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
