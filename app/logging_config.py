"""
Configuración centralizada de logging para SIPAC
"""
import logging
import os
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime


def setup_logging(app):
    """
    Configura el sistema de logging para la aplicación

    Crea logs en:
    - logs/sipac.log (general, rotación diaria)
    - logs/sipac_errors.log (solo errores, rotación diaria)
    - logs/data_processing.log (procesamiento de datos, rotación por tamaño)
    """

    # Crear directorio de logs si no existe
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # Formato de logs
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler para archivo general (rotación diaria, mantiene 30 días)
    general_log_file = os.path.join(log_dir, 'sipac.log')
    general_handler = TimedRotatingFileHandler(
        general_log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(detailed_formatter)
    general_handler.suffix = "%Y-%m-%d"

    # Handler para errores (rotación diaria, mantiene 60 días)
    error_log_file = os.path.join(log_dir, 'sipac_errors.log')
    error_handler = TimedRotatingFileHandler(
        error_log_file,
        when='midnight',
        interval=1,
        backupCount=60,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    error_handler.suffix = "%Y-%m-%d"

    # Handler para procesamiento de datos (rotación por tamaño)
    processing_log_file = os.path.join(log_dir, 'data_processing.log')
    processing_handler = RotatingFileHandler(
        processing_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,
        encoding='utf-8'
    )
    processing_handler.setLevel(logging.DEBUG)
    processing_handler.setFormatter(detailed_formatter)

    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # Configurar logger raíz de la aplicación
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(general_handler)
    app.logger.addHandler(error_handler)
    app.logger.addHandler(console_handler)

    # Configurar logger para data_processor
    processing_logger = logging.getLogger('app.services.data_processor')
    processing_logger.setLevel(logging.DEBUG)
    processing_logger.addHandler(processing_handler)
    processing_logger.addHandler(error_handler)
    processing_logger.addHandler(console_handler)

    # Configurar logger para rutas/API
    api_logger = logging.getLogger('app.routes')
    api_logger.setLevel(logging.INFO)
    api_logger.addHandler(general_handler)
    api_logger.addHandler(error_handler)

    # Configurar logger para modelos
    models_logger = logging.getLogger('app.models')
    models_logger.setLevel(logging.INFO)
    models_logger.addHandler(general_handler)
    models_logger.addHandler(error_handler)

    # Reducir verbosidad de SQLAlchemy
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)

    # Reducir verbosidad de Werkzeug (servidor Flask)
    logging.getLogger('werkzeug').setLevel(logging.INFO)

    # Log inicial
    app.logger.info("=" * 80)
    app.logger.info("SIPAC - Sistema de Procesamiento de Auxiliares Contables")
    app.logger.info(f"Inicio de sesión: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    app.logger.info(f"Directorio de logs: {log_dir}")
    app.logger.info("=" * 80)

    return app.logger


def get_logger(name):
    """
    Obtiene un logger configurado para un módulo específico

    Args:
        name: Nombre del módulo (ej: 'app.services.data_processor')

    Returns:
        Logger configurado
    """
    return logging.getLogger(name)
