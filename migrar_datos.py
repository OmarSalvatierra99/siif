#!/usr/bin/env python3
"""
Script de migración de datos de SIPAC v1 a v2
Convierte archivos Excel existentes a la nueva base de datos
"""

import sys
import os
from pathlib import Path
from io import BytesIO
from app import create_app
from models import db
from data_processor import process_files_to_database

def migrar_archivos(directorio_excel, usuario="migracion"):
    """
    Migra todos los archivos Excel de un directorio a la base de datos
    
    Args:
        directorio_excel: Ruta al directorio con archivos .xlsx
        usuario: Nombre del usuario que realiza la migración
    """
    app = create_app('production')
    
    with app.app_context():
        # Verificar conexión a BD
        try:
            db.engine.connect()
            print("✓ Conexión a base de datos establecida")
        except Exception as e:
            print(f"✗ Error conectando a la base de datos: {e}")
            print("Asegúrate de que PostgreSQL está corriendo y configurado correctamente")
            return False
        
        # Obtener lista de archivos Excel
        directorio = Path(directorio_excel)
        if not directorio.exists():
            print(f"✗ El directorio {directorio_excel} no existe")
            return False
        
        archivos_excel = list(directorio.glob("*.xlsx")) + list(directorio.glob("*.xls"))
        
        if not archivos_excel:
            print(f"✗ No se encontraron archivos Excel en {directorio_excel}")
            return False
        
        print(f"\nSe encontraron {len(archivos_excel)} archivos para migrar")
        print("=" * 60)
        
        # Confirmar
        respuesta = input("\n¿Deseas continuar con la migración? (s/n): ")
        if respuesta.lower() != 's':
            print("Migración cancelada")
            return False
        
        # Procesar archivos en lotes de 5
        batch_size = 5
        total_procesados = 0
        total_errores = 0
        
        for i in range(0, len(archivos_excel), batch_size):
            batch = archivos_excel[i:i+batch_size]
            print(f"\n--- Procesando lote {i//batch_size + 1} ({len(batch)} archivos) ---")
            
            # Preparar archivos para procesamiento
            files_in_memory = []
            for archivo in batch:
                print(f"  → Leyendo {archivo.name}...")
                try:
                    with open(archivo, 'rb') as f:
                        content = BytesIO(f.read())
                        files_in_memory.append((archivo.name, content))
                except Exception as e:
                    print(f"  ✗ Error leyendo {archivo.name}: {e}")
                    total_errores += 1
                    continue
            
            if not files_in_memory:
                print("  No hay archivos válidos en este lote")
                continue
            
            # Procesar lote
            def progress_callback(pct, msg):
                print(f"  [{pct}%] {msg}")
            
            try:
                lote_id, total_registros = process_files_to_database(
                    files_in_memory,
                    usuario,
                    progress_callback
                )
                
                print(f"  ✓ Lote completado: {total_registros:,} registros insertados")
                print(f"  Lote ID: {lote_id}")
                total_procesados += len(files_in_memory)
                
            except Exception as e:
                print(f"  ✗ Error procesando lote: {e}")
                total_errores += len(files_in_memory)
        
        # Resumen
        print("\n" + "=" * 60)
        print("RESUMEN DE MIGRACIÓN")
        print("=" * 60)
        print(f"Archivos procesados exitosamente: {total_procesados}")
        print(f"Archivos con error: {total_errores}")
        
        # Estadísticas de BD
        from models import Transaccion, LoteCarga
        total_trans = db.session.query(Transaccion).count()
        total_lotes = db.session.query(LoteCarga).count()
        
        print(f"\nEstadísticas de base de datos:")
        print(f"  Total de transacciones: {total_trans:,}")
        print(f"  Total de lotes: {total_lotes}")
        print("=" * 60)
        
        return True


def verificar_base_datos():
    """Verifica el estado de la base de datos"""
    app = create_app('production')
    
    with app.app_context():
        try:
            from models import Transaccion, LoteCarga, Usuario
            
            print("Verificando base de datos...")
            print("=" * 60)
            
            total_trans = db.session.query(Transaccion).count()
            total_lotes = db.session.query(LoteCarga).count()
            total_usuarios = db.session.query(Usuario).count()
            
            print(f"Transacciones: {total_trans:,}")
            print(f"Lotes de carga: {total_lotes}")
            print(f"Usuarios: {total_usuarios}")
            
            if total_trans > 0:
                # Primera y última transacción
                primera = db.session.query(Transaccion).order_by(Transaccion.id).first()
                ultima = db.session.query(Transaccion).order_by(Transaccion.id.desc()).first()
                
                print(f"\nPrimera transacción: {primera.fecha_transaccion}")
                print(f"Última transacción: {ultima.fecha_transaccion}")
                
                # Cuentas únicas
                from sqlalchemy import func
                total_cuentas = db.session.query(
                    func.count(func.distinct(Transaccion.cuenta_contable))
                ).scalar()
                print(f"Cuentas contables únicas: {total_cuentas}")
            
            print("=" * 60)
            return True
            
        except Exception as e:
            print(f"Error verificando base de datos: {e}")
            return False


def limpiar_base_datos():
    """Limpia completamente la base de datos (¡USAR CON PRECAUCIÓN!)"""
    app = create_app('production')
    
    print("=" * 60)
    print("⚠️  ADVERTENCIA: LIMPIEZA COMPLETA DE BASE DE DATOS")
    print("=" * 60)
    print("Esta acción eliminará TODOS los datos del sistema:")
    print("  - Todas las transacciones")
    print("  - Todos los lotes de carga")
    print("  - Todos los reportes generados")
    print("")
    print("Esta acción NO SE PUEDE DESHACER")
    print("=" * 60)
    
    confirmacion = input("\n¿Estás ABSOLUTAMENTE seguro? Escribe 'ELIMINAR TODO' para confirmar: ")
    
    if confirmacion != "ELIMINAR TODO":
        print("Operación cancelada")
        return False
    
    with app.app_context():
        try:
            from models import Transaccion, LoteCarga, ReporteGenerado
            
            print("\nEliminando datos...")
            
            # Eliminar en orden para respetar foreign keys
            ReporteGenerado.query.delete()
            print("  ✓ Reportes eliminados")
            
            Transaccion.query.delete()
            print("  ✓ Transacciones eliminadas")
            
            LoteCarga.query.delete()
            print("  ✓ Lotes eliminados")
            
            db.session.commit()
            print("\n✓ Base de datos limpiada exitosamente")
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Error limpiando base de datos: {e}")
            return False


def mostrar_ayuda():
    """Muestra ayuda del script"""
    print("""
Script de Migración SIPAC v2

USO:
    python migrar_datos.py [comando] [argumentos]

COMANDOS:

    migrar <directorio>
        Migra todos los archivos Excel del directorio a la base de datos
        Ejemplo: python migrar_datos.py migrar /ruta/a/archivos/excel

    verificar
        Verifica el estado actual de la base de datos
        Ejemplo: python migrar_datos.py verificar

    limpiar
        Limpia completamente la base de datos (¡PRECAUCIÓN!)
        Ejemplo: python migrar_datos.py limpiar

    ayuda
        Muestra este mensaje de ayuda

EJEMPLOS:

    # Migrar archivos de un directorio
    python migrar_datos.py migrar /home/usuario/auxiliares

    # Verificar estado de la BD
    python migrar_datos.py verificar

    # Limpiar toda la BD (¡cuidado!)
    python migrar_datos.py limpiar

NOTAS:
    - Asegúrate de que PostgreSQL esté corriendo antes de ejecutar
    - Los archivos deben tener el formato correcto de auxiliares contables
    - La migración procesa archivos en lotes de 5 para optimizar memoria
    - Se recomienda hacer un respaldo antes de limpiar la BD
""")


def main():
    """Función principal del script"""
    if len(sys.argv) < 2:
        print("Error: Se requiere un comando")
        print("Usa 'python migrar_datos.py ayuda' para más información")
        return
    
    comando = sys.argv[1].lower()
    
    if comando == "migrar":
        if len(sys.argv) < 3:
            print("Error: Se requiere especificar el directorio de archivos Excel")
            print("Uso: python migrar_datos.py migrar <directorio>")
            return
        
        directorio = sys.argv[2]
        usuario = sys.argv[3] if len(sys.argv) > 3 else "migracion"
        
        migrar_archivos(directorio, usuario)
        
    elif comando == "verificar":
        verificar_base_datos()
        
    elif comando == "limpiar":
        limpiar_base_datos()
        
    elif comando == "ayuda" or comando == "help":
        mostrar_ayuda()
        
    else:
        print(f"Comando desconocido: {comando}")
        print("Usa 'python migrar_datos.py ayuda' para ver comandos disponibles")


if __name__ == "__main__":
    main()
