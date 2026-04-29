"""
Script para importar los archivos de EJECUTIVO_DANNY directamente a la base de datos.
Uso: python import_ejecutivo_danny.py
"""
import os
import sys
from io import BytesIO

# Necesario para que funcione fuera del contexto de Flask
os.environ.setdefault("FLASK_ENV", "development")

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from scripts.utils import process_files_to_database

FILES_DIR = os.path.join(os.path.dirname(__file__), "example_SIIF", "input", "EJECUTIVO_DANNY")

FILES = [
    "INGRESOS ENE MARZO CONTABLE.xlsx",
    "ING - ABRIL - JUN.xlsx",
    "INGRESOSCON_SEP.xlsx",
    "INGR-SEP-DIC.xlsx",
]

ENTE = {
    "num": "1",
    "nombre": "PODER EJECUTIVO DEL ESTADO DE TLAXCALA",
    "siglas": "EJECUTIVO",
    "clasificacion": "PODER DEL ESTADO",
}


def main():
    app = create_app()
    with app.app_context():
        available_files = []
        for fname in FILES:
            path = os.path.join(FILES_DIR, fname)
            if not os.path.exists(path):
                print(f"[WARN] No encontrado: {path}")
                continue
            available_files.append((fname, path))
            print(f"[OK]   Disponible: {fname}")

        if not available_files:
            print("ERROR: No se encontró ningún archivo.")
            sys.exit(1)

        print(f"\nProcesando {len(available_files)} archivos para ente: {ENTE['siglas']} - {ENTE['nombre']}")
        print("-" * 60)

        def progress(pct, msg, current_file=None):
            marker = f" ({current_file})" if current_file else ""
            print(f"  [{pct:3d}%] {msg}{marker}")

        total_insertados = 0
        lotes = []

        for fname, path in available_files:
            print(f"\n>>> Importando archivo: {fname}")
            with open(path, "rb") as fh:
                file_list = [(fname, BytesIO(fh.read()))]

            try:
                lote_id, total = process_files_to_database(
                    file_list=file_list,
                    usuario="admin",
                    progress_callback=progress,
                    tipo_archivo="macro",
                    enforce_contable_balance=False,
                    seed_historical_opening_balances=True,
                    selected_ente=ENTE["num"],
                    selected_ente_siglas=ENTE["siglas"],
                    selected_ente_nombre=ENTE["nombre"],
                    selected_ente_grupo=ENTE["clasificacion"],
                )
            except Exception as e:
                print(f"\nERROR EN {fname}: {e}")
                sys.exit(1)

            total_insertados += total
            lotes.append((fname, lote_id, total))
            print(f"Archivo completado: {fname}")
            print(f"Lote ID: {lote_id}")
            print(f"Registros insertados: {total}")

        print("-" * 60)
        print("\nIMPORTACION EXITOSA")
        print(f"Archivos procesados: {len(lotes)}")
        print(f"Registros insertados totales: {total_insertados}")
        for fname, lote_id, total in lotes:
            print(f" - {fname}: lote={lote_id} registros={total}")


if __name__ == "__main__":
    main()
