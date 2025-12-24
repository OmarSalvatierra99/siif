import os
from datetime import timedelta

class Config:
    """Configuración base de la aplicación"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    PORT = int(os.environ.get('PORT', 5009))
    
    # Base de datos
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://sipac_user:sipac_password@localhost:5432/sipac_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # Archivos
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB
    UPLOAD_EXTENSIONS = {'.xlsx', '.xls'}
    UPLOAD_FOLDER = '/tmp/sipac_uploads'
    
    # Sesiones
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Procesamiento
    MAX_WORKERS = 4
    CHUNK_SIZE = 1000  # Registros por lote para inserción
    
    # Paginación
    ITEMS_PER_PAGE = 50
    MAX_ITEMS_PER_PAGE = 1000

class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    SQLALCHEMY_ECHO = False  # Desactivado para reducir logging excesivo

class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    # En producción, usar variables de entorno
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SECRET_KEY = os.environ.get('SECRET_KEY')

# Selección de configuración según entorno
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
