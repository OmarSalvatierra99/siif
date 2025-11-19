"""
Application factory para SIPAC
"""
from flask import Flask, jsonify
from flask_cors import CORS
from config import config
from app.models import db
from app.logging_config import setup_logging


def create_app(config_name="default"):
    """
    Factory para crear la aplicación Flask

    Args:
        config_name: Nombre de la configuración ('development', 'production', 'default')

    Returns:
        Aplicación Flask configurada
    """
    app = Flask(__name__)

    # Cargar configuración
    app.config.from_object(config[config_name])

    # Configurar logging
    app_logger = setup_logging(app)

    # Inicializar extensiones
    db.init_app(app)
    CORS(app)

    # Crear tablas con manejo de errores
    with app.app_context():
        try:
            db.create_all()
            app_logger.info("✓ Base de datos conectada y tablas creadas/verificadas")
            app_logger.info(f"✓ Base de datos: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1]}")
        except Exception as e:
            app_logger.error(f"❌ Error al conectar con la base de datos: {str(e)}")
            app_logger.error(f"   Verifica: DATABASE_URL en .env")
            raise

    # Registrar blueprints
    register_blueprints(app)
    app_logger.info("✓ Blueprints registrados")

    # Registrar manejadores de errores
    register_error_handlers(app)
    app_logger.info("✓ Manejadores de errores registrados")

    app_logger.info("✓ Aplicación inicializada correctamente")

    return app


def register_blueprints(app):
    """Registra todos los blueprints de la aplicación"""
    from app.routes import main_bp, upload_bp, reports_bp, entes_bp, api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(entes_bp)
    app.register_blueprint(api_bp)


def register_error_handlers(app):
    """Registra manejadores de errores globales"""

    @app.errorhandler(413)
    def too_large(e):
        """Archivo muy grande"""
        app.logger.warning(f"Archivo rechazado por tamaño: {e}")
        return jsonify({
            "error": "El archivo es demasiado grande",
            "detalle": f"Máximo permitido: {app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024)} MB"
        }), 413

    @app.errorhandler(404)
    def not_found(e):
        """Recurso no encontrado"""
        app.logger.warning(f"Recurso no encontrado: {e}")
        return jsonify({
            "error": str(e.description) if hasattr(e, "description") else "No encontrado"
        }), 404

    @app.errorhandler(500)
    def internal_error(e):
        """Error interno del servidor"""
        app.logger.error(f"Error interno del servidor: {str(e)}")
        return jsonify({
            "error": "Error interno del servidor",
            "detalle": str(e) if app.config.get('DEBUG') else "Contacte al administrador"
        }), 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        """Captura errores no manejados"""
        app.logger.error(f"Error no manejado: {type(e).__name__} - {str(e)}")
        return jsonify({
            "error": "Error inesperado",
            "tipo": type(e).__name__,
            "detalle": str(e) if app.config.get('DEBUG') else "Contacte al administrador"
        }), 500
