"""
Modelos de base de datos para SIPAC
"""
from flask_sqlalchemy import SQLAlchemy

# Instancia global de SQLAlchemy
db = SQLAlchemy()

# Importar modelos
from app.models.transaccion import Transaccion
from app.models.lote_carga import LoteCarga
from app.models.usuario import Usuario
from app.models.reporte_generado import ReporteGenerado
from app.models.ente import Ente

__all__ = [
    'db',
    'Transaccion',
    'LoteCarga',
    'Usuario',
    'ReporteGenerado',
    'Ente'
]
