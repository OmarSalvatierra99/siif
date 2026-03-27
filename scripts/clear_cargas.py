#!/usr/bin/env python3
"""Limpia transacciones y lotes de carga del proyecto SIIF."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from scripts.utils import LoteCarga, Transaccion, db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Elimina todos los registros de transacciones y lotes de carga."
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("SIIF_CONFIG", "default"),
        choices=("default", "development", "production"),
        help="Configuracion de la app a usar. Default: %(default)s",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra el conteo actual sin borrar registros.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Omite la confirmacion interactiva.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app(args.config)

    with app.app_context():
        db_url = db.engine.url.render_as_string(hide_password=True)
        transacciones_count = Transaccion.query.count()
        lotes_count = LoteCarga.query.count()

        print(f"Base de datos: {db_url}")
        print(f"Transacciones actuales: {transacciones_count}")
        print(f"Lotes de carga actuales: {lotes_count}")

        if args.dry_run:
            print("Dry-run: no se realizaron cambios.")
            return 0

        if not args.yes:
            confirmation = input(
                "Escribe LIMPIAR para borrar todas las transacciones y lotes de carga: "
            ).strip()
            if confirmation != "LIMPIAR":
                print("Operacion cancelada.")
                return 0

        try:
            deleted_transacciones = db.session.query(Transaccion).delete(
                synchronize_session=False
            )
            deleted_lotes = db.session.query(LoteCarga).delete(
                synchronize_session=False
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"Error al limpiar la base: {exc}", file=sys.stderr)
            return 1

        print(f"Transacciones eliminadas: {deleted_transacciones}")
        print(f"Lotes de carga eliminados: {deleted_lotes}")
        print("Limpieza completada.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
