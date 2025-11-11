#!/usr/bin/env python
"""Script simple para probar la conexión a la base de datos"""

import sys
from sqlalchemy import create_engine, text
from config import config

def test_conexion():
    """Prueba la conexión a la base de datos"""
    try:
        cfg = config['development']
        db_uri = cfg.SQLALCHEMY_DATABASE_URI

        print("Probando conexión a la base de datos...")
        print(f"URI: {db_uri.replace(db_uri.split('@')[0].split('//')[1], '***')}")

        engine = create_engine(db_uri)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✓ Conexión exitosa")
            print(f"✓ PostgreSQL version: {version.split(',')[0]}")

            # Verificar tablas
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """))
            tablas = [row[0] for row in result]
            print(f"✓ Tablas encontradas: {', '.join(tablas)}")

            # Contar registros
            if 'transacciones' in tablas:
                result = conn.execute(text("SELECT COUNT(*) FROM transacciones"))
                count = result.fetchone()[0]
                print(f"✓ Transacciones en BD: {count:,}")

        return True

    except Exception as e:
        print(f"❌ Error de conexión: {type(e).__name__}")
        print(f"   Detalle: {str(e)}")
        return False

if __name__ == "__main__":
    if test_conexion():
        print("\n¡Todo listo para usar SIPAC!")
        sys.exit(0)
    else:
        print("\nPor favor verifica la configuración de la base de datos")
        sys.exit(1)
