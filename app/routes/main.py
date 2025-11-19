"""
Rutas principales de la aplicación (páginas HTML)
"""
from flask import Blueprint, render_template
from app.logging_config import get_logger

logger = get_logger('app.routes.main')

main_bp = Blueprint('main', __name__)


@main_bp.route("/")
def index():
    """Página principal de carga de archivos"""
    logger.info("Acceso a página principal")
    return render_template("index.html")


@main_bp.route("/reporte-online")
def reporte_online():
    """Página de generación de reportes en línea"""
    logger.info("Acceso a página de reporte online")
    return render_template("reporte_online.html")


@main_bp.route("/catalogo-entes")
def catalogo_entes():
    """Página de catálogo de entes"""
    logger.info("Acceso a página de catálogo de entes")
    return render_template("catalogo_entes.html")
