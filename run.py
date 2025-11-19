#!/usr/bin/env python3
"""
Punto de entrada para ejecutar SIPAC
"""
import os
from app.factory import create_app

# Determinar entorno
env = os.environ.get('FLASK_ENV', 'development')

# Crear aplicación
app = create_app(env)

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("SIPAC - Sistema de Procesamiento de Auxiliares Contables")
    print("=" * 80)
    print(f"✓ Entorno: {env}")
    print(f"✓ Puerto: 5020")
    print(f"✓ Debug: {app.config.get('DEBUG', False)}")
    print("\nPáginas disponibles:")
    print("  → http://localhost:5020             (Carga de archivos)")
    print("  → http://localhost:5020/reporte-online  (Generación de reportes)")
    print("  → http://localhost:5020/catalogo-entes  (Catálogo de entes)")
    print("=" * 80 + "\n")

    app.run(
        host="0.0.0.0",
        port=5020,
        debug=app.config.get('DEBUG', False),
        threaded=True
    )
