#!/usr/bin/env python3
"""
Script para importar catálogo de entes desde archivos Excel
"""
import sys
import os
from pathlib import Path

# Añadir el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from app import create_app
from scripts.utils import db, Ente


def import_entes_from_excel():
    """Importa entes desde archivos Excel de catálogos"""

    app = create_app()

    with app.app_context():
        print("\n" + "="*60)
        print("IMPORTACIÓN DE CATÁLOGO DE ENTES")
        print("="*60 + "\n")

        # Rutas a los archivos de catálogo
        catalogos_dir = Path('../05-sasp/catalogos')

        if not catalogos_dir.exists():
            print(f"❌ Error: No se encontró el directorio {catalogos_dir}")
            return

        archivos = [
            ('Estatales.xlsx', 'ESTATAL'),
            ('Municipales.xlsx', 'MUNICIPAL')
        ]

        total_importados = 0
        total_actualizados = 0
        total_errores = 0

        for archivo, ambito in archivos:
            archivo_path = catalogos_dir / archivo

            if not archivo_path.exists():
                print(f"⚠ Archivo no encontrado: {archivo_path}")
                continue

            print(f"\n📄 Procesando: {archivo} ({ambito})")
            print("-" * 60)

            try:
                # Leer archivo Excel
                df = pd.read_excel(archivo_path)
                print(f"  ✓ Leídas {len(df)} filas del archivo")

                # Procesar cada registro
                for idx, row in df.iterrows():
                    try:
                        num = str(row['NUM']).strip()
                        nombre = str(row['NOMBRE']).strip()
                        siglas = str(row['SIGLAS']).strip() if pd.notna(row['SIGLAS']) else ''
                        clasificacion = str(row['CLASIFICACION']).strip() if pd.notna(row['CLASIFICACION']) else ''

                        # Generar clave única (ambito + num)
                        clave = f"{ambito[0]}-{num}"

                        # Buscar si ya existe
                        ente_existente = Ente.query.filter_by(clave=clave).first()

                        if ente_existente:
                            # Actualizar registro existente
                            ente_existente.nombre = nombre
                            ente_existente.siglas = siglas
                            ente_existente.tipo = clasificacion
                            ente_existente.ambito = ambito
                            ente_existente.activo = True
                            total_actualizados += 1
                        else:
                            # Crear nuevo registro
                            nuevo_ente = Ente(
                                clave=clave,
                                codigo=num,
                                nombre=nombre,
                                siglas=siglas,
                                tipo=clasificacion,
                                ambito=ambito,
                                activo=True
                            )
                            db.session.add(nuevo_ente)
                            total_importados += 1

                    except Exception as e:
                        print(f"  ❌ Error en fila {idx}: {str(e)}")
                        total_errores += 1
                        continue

                # Commit después de procesar cada archivo
                db.session.commit()
                print(f"  ✓ Archivo procesado exitosamente")

            except Exception as e:
                print(f"  ❌ Error procesando archivo {archivo}: {str(e)}")
                db.session.rollback()
                total_errores += 1
                continue

        # Resumen final
        print("\n" + "="*60)
        print("RESUMEN DE IMPORTACIÓN")
        print("="*60)
        print(f"✅ Registros nuevos importados: {total_importados}")
        print(f"🔄 Registros actualizados: {total_actualizados}")
        print(f"❌ Errores: {total_errores}")
        print(f"📊 Total procesado: {total_importados + total_actualizados}")

        # Mostrar estadísticas por ámbito
        print("\n" + "-"*60)
        print("ESTADÍSTICAS POR ÁMBITO")
        print("-"*60)

        for ambito in ['ESTATAL', 'MUNICIPAL']:
            count = Ente.query.filter_by(ambito=ambito, activo=True).count()
            print(f"  {ambito}: {count} entes activos")

        total = Ente.query.filter_by(activo=True).count()
        print(f"\n  TOTAL: {total} entes activos")
        print("="*60 + "\n")


if __name__ == '__main__':
    import_entes_from_excel()
