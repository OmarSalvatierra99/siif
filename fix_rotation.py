"""
Fix the column rotation in the database.
The data was loaded with saldo_inicial/cargos/abonos rotated:
  DB.saldo_inicial = Excel.abonos
  DB.cargos = Excel.saldo_inicial
  DB.abonos = Excel.cargos

This script:
1. Rotates the three columns back to their correct positions
2. Recalculates saldo_final using _rebuild_account_balances logic
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from scripts.utils import db, Transaccion

app = create_app()

with app.app_context():
    # Step 1: Rotate columns back
    # new saldo_inicial = old cargos (was Excel's saldo_inicial)
    # new cargos = old abonos (was Excel's cargos)
    # new abonos = old saldo_inicial (was Excel's abonos)
    print("Step 1: Rotating columns back...")

    # SQLite handles this atomically - RHS reads original values
    db.session.execute(db.text("""
        UPDATE transacciones SET
            saldo_inicial = cargos,
            cargos = abonos,
            abonos = saldo_inicial
    """))
    db.session.commit()
    print("  Columns rotated.")

    # Verify totals
    result = db.session.execute(db.text("""
        SELECT ROUND(SUM(cargos),2), ROUND(SUM(abonos),2), ROUND(SUM(saldo_inicial),2)
        FROM transacciones WHERE genero IN ('1','2','3','4','5')
    """)).fetchone()
    print(f"  Generos 1-5: Cargos={result[0]:,.2f}  Abonos={result[1]:,.2f}  SI={result[2]:,.2f}")

    # Step 2: Recalculate saldo_final per account
    print("\nStep 2: Recalculating saldo_final per account...")

    cuentas = db.session.execute(db.text(
        "SELECT DISTINCT cuenta_contable FROM transacciones ORDER BY cuenta_contable"
    )).fetchall()

    total_cuentas = len(cuentas)
    print(f"  {total_cuentas} cuentas a procesar...")

    DEUDORA_GENEROS = {'1', '5', '8'}  # activo, gastos, presupuestal
    ACREEDORA_GENEROS = {'2', '3', '4'}  # pasivo, hacienda publica, ingresos

    batch_count = 0
    for i, (cuenta,) in enumerate(cuentas):
        rows = db.session.execute(db.text("""
            SELECT id, saldo_inicial, cargos, abonos, genero
            FROM transacciones
            WHERE cuenta_contable = :cuenta
            ORDER BY fecha_transaccion, id
        """), {"cuenta": cuenta}).fetchall()

        if not rows:
            continue

        # Determine account nature from genero
        genero = rows[0][4] or ''
        if genero in DEUDORA_GENEROS:
            # deudora: saldo_final = saldo_inicial + cargos - abonos
            sign_cargo, sign_abono = 1, -1
        elif genero in ACREEDORA_GENEROS:
            # acreedora: saldo_final = saldo_inicial - cargos + abonos
            sign_cargo, sign_abono = -1, 1
        else:
            # default to deudora
            sign_cargo, sign_abono = 1, -1

        saldo_actual = None
        for row_id, si, cargos, abonos, _ in rows:
            si = float(si or 0)
            cargos = float(cargos or 0)
            abonos = float(abonos or 0)

            if saldo_actual is not None:
                si = saldo_actual

            saldo_actual = si + (sign_cargo * cargos) + (sign_abono * abonos)

            db.session.execute(db.text("""
                UPDATE transacciones
                SET saldo_inicial = :si, saldo_final = :sf
                WHERE id = :id
            """), {"si": round(si, 2), "sf": round(saldo_actual, 2), "id": row_id})

        batch_count += 1
        if batch_count % 500 == 0:
            db.session.commit()
            print(f"  Procesadas {i+1}/{total_cuentas} cuentas...")

    db.session.commit()
    print(f"  Completado: {total_cuentas} cuentas recalculadas.")

    # Final verification
    result = db.session.execute(db.text("""
        SELECT ROUND(SUM(cargos),2), ROUND(SUM(abonos),2)
        FROM transacciones WHERE genero IN ('1','2','3','4','5')
    """)).fetchone()
    print(f"\nVerificación final (generos 1-5):")
    print(f"  Cargos: ${result[0]:,.2f}")
    print(f"  Abonos: ${result[1]:,.2f}")
    print(f"  Diferencia: ${result[0] - result[1]:,.2f}")

    # Also check all generos
    result_all = db.session.execute(db.text("""
        SELECT ROUND(SUM(cargos),2), ROUND(SUM(abonos),2)
        FROM transacciones
    """)).fetchone()
    print(f"\nTodos los generos:")
    print(f"  Cargos: ${result_all[0]:,.2f}")
    print(f"  Abonos: ${result_all[1]:,.2f}")
    print(f"  Diferencia: ${result_all[0] - result_all[1]:,.2f}")
