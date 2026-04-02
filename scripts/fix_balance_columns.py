from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from scripts.utils import CONTABLE_GENEROS, _hash_transaccion_row, _infer_account_balance_side


TOLERANCE = 0.01
BATCH_SIZE = 5000


SELECT_SQL = """
SELECT
    id,
    archivo_origen,
    cuenta_contable,
    nombre_cuenta,
    genero,
    grupo,
    rubro,
    cuenta,
    subcuenta,
    dependencia,
    unidad_responsable,
    centro_costo,
    proyecto_presupuestario,
    fuente,
    subfuente,
    tipo_recurso,
    partida_presupuestal,
    fecha_transaccion,
    poliza,
    beneficiario,
    descripcion,
    orden_pago,
    ente_siglas_catalogo,
    ente_grupo_catalogo,
    saldo_inicial,
    cargos,
    abonos,
    saldo_final
FROM transacciones
ORDER BY cuenta_contable, fecha_transaccion, id
"""


UPDATE_SQL = """
UPDATE transacciones
SET
    saldo_inicial = ?,
    cargos = ?,
    abonos = ?,
    saldo_final = ?,
    hash_registro = ?
WHERE id = ?
"""


def _resolve_sqlite_path(app) -> Path:
    database = app.config["SQLALCHEMY_DATABASE_URI"].removeprefix("sqlite:///")
    db_path = Path(database)
    if db_path.is_absolute():
        return db_path
    if str(db_path).startswith("instance/"):
        return Path(app.root_path) / db_path
    return Path(app.instance_path) / db_path.name


def _build_corrected_rows(account_rows: list[dict]) -> tuple[list[tuple], float, float]:
    if not account_rows:
        return [], 0.0, 0.0

    inference = pd.DataFrame(
        {
            "genero": [row["genero"] for row in account_rows],
            "saldo_inicial": [float(row["abonos"] or 0) for row in account_rows],
            "cargos": [float(row["saldo_inicial"] or 0) for row in account_rows],
            "abonos": [float(row["cargos"] or 0) for row in account_rows],
            "saldo_final_origen": [float(row["saldo_final"] or 0) for row in account_rows],
        }
    )
    balance_side = _infer_account_balance_side(inference, tolerance=TOLERANCE)

    saldo_actual = None
    total_cargos = 0.0
    total_abonos = 0.0
    updates = []

    for position, row in enumerate(account_rows):
        saldo_inicial = float(row["abonos"] or 0)
        cargos = float(row["saldo_inicial"] or 0)
        abonos = float(row["cargos"] or 0)
        saldo_final_origen = float(row["saldo_final"] or 0)

        if position > 0 and saldo_actual is not None:
            saldo_inicial = saldo_actual

        if balance_side == "acreedora":
            saldo_actual = saldo_inicial - cargos + abonos
        else:
            saldo_actual = saldo_inicial + cargos - abonos

        diff = abs(saldo_actual - saldo_final_origen)
        if diff > TOLERANCE:
            raise ValueError(
                "No se pudo reconstruir la cuenta "
                f"{row['cuenta_contable']} (id={row['id']}, fecha={row['fecha_transaccion']}, "
                f"poliza={row['poliza'] or 'sin poliza'}). "
                f"Calculado={saldo_actual:,.2f} Origen={saldo_final_origen:,.2f} Diff={diff:,.2f}"
            )

        payload = dict(row)
        payload.update(
            {
                "saldo_inicial": saldo_inicial,
                "cargos": cargos,
                "abonos": abonos,
                "saldo_final": saldo_actual,
            }
        )

        updates.append(
            (
                saldo_inicial,
                cargos,
                abonos,
                saldo_actual,
                _hash_transaccion_row(payload),
                row["id"],
            )
        )

        if str(row["genero"] or "").strip() in CONTABLE_GENEROS:
            total_cargos += cargos
            total_abonos += abonos

    return updates, total_cargos, total_abonos


def main() -> None:
    app = create_app("default")
    db_path = _resolve_sqlite_path(app)
    if not db_path.exists():
        raise FileNotFoundError(f"No se encontró la base SQLite en {db_path}")

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f"{db_path.suffix}.backup_{timestamp}")
    shutil.copy2(db_path, backup_path)
    print(f"Respaldo creado: {backup_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        total_rows = conn.execute("SELECT COUNT(*) FROM transacciones").fetchone()[0]
        print(f"Registros a corregir: {total_rows:,}")

        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE transacciones SET hash_registro = 'tmp:' || id")

        read_cursor = conn.cursor()
        write_cursor = conn.cursor()
        read_cursor.execute(SELECT_SQL)

        current_account = None
        account_rows: list[dict] = []
        pending_updates: list[tuple] = []
        processed_rows = 0
        total_cargos = 0.0
        total_abonos = 0.0

        def flush_account() -> None:
            nonlocal account_rows, pending_updates, processed_rows, total_cargos, total_abonos
            if not account_rows:
                return
            updates, account_cargos, account_abonos = _build_corrected_rows(account_rows)
            pending_updates.extend(updates)
            total_cargos += account_cargos
            total_abonos += account_abonos
            processed_rows += len(account_rows)
            account_rows = []

            if len(pending_updates) >= BATCH_SIZE:
                write_cursor.executemany(UPDATE_SQL, pending_updates)
                pending_updates = []
                print(f"Corregidos {processed_rows:,} / {total_rows:,} registros...")

        for row in read_cursor:
            cuenta_contable = row["cuenta_contable"]
            if current_account is None:
                current_account = cuenta_contable
            if cuenta_contable != current_account:
                flush_account()
                current_account = cuenta_contable
            account_rows.append(dict(row))

        flush_account()

        if pending_updates:
            write_cursor.executemany(UPDATE_SQL, pending_updates)

        diff = abs(total_cargos - total_abonos)
        if diff > TOLERANCE:
            raise ValueError(
                "El balance contable corregido sigue desbalanceado. "
                f"Cargos={total_cargos:,.2f} Abonos={total_abonos:,.2f} Diff={diff:,.2f}"
            )

        conn.commit()
        print(
            "Corrección aplicada. "
            f"Cargos contables={total_cargos:,.2f} "
            f"Abonos contables={total_abonos:,.2f}"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
