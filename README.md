# SIIF

Aplicación Flask para carga y consulta de auxiliares contables (SIIF/SIPAC).

## Requisitos
- Python 3.10+
- PostgreSQL

## Configuración rápida
1. Crea y activa un entorno virtual:
   `python -m venv venv && source venv/bin/activate`
2. Instala dependencias:
   `pip install -r requirements.txt`
3. Exporta variables de entorno mínimas:
   `export DATABASE_URL=postgresql://sipac_user:sipac_password@localhost:5432/sipac_db`
   `export SECRET_KEY=dev`
4. Ejecuta:
   `python app.py`

El servidor se inicia en `http://localhost:5009` (configurable con `PORT`).
