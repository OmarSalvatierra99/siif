"""
Rutas y blueprints de la aplicación
"""
from app.routes.main import main_bp
from app.routes.upload import upload_bp
from app.routes.reports import reports_bp
from app.routes.entes import entes_bp
from app.routes.api import api_bp

__all__ = [
    'main_bp',
    'upload_bp',
    'reports_bp',
    'entes_bp',
    'api_bp'
]
