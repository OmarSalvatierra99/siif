"""
Modelo para catálogo de entes públicos
"""
from datetime import datetime
from app.models import db


class Ente(db.Model):
    """
    Modelo para catálogo de entes públicos

    Almacena información de entidades gubernamentales
    que pueden ser referenciadas en las transacciones.
    """
    __tablename__ = 'entes'

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(20), unique=True, nullable=False, index=True)
    codigo = db.Column(db.String(50), nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    siglas = db.Column(db.String(50))
    tipo = db.Column(db.String(100))
    ambito = db.Column(db.String(50))  # ESTATAL, MUNICIPAL, etc.
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'clave': self.clave,
            'codigo': self.codigo,
            'nombre': self.nombre,
            'siglas': self.siglas,
            'tipo': self.tipo,
            'ambito': self.ambito,
            'activo': self.activo,
            'fecha_registro': self.fecha_registro.isoformat() if self.fecha_registro else None
        }

    def __repr__(self):
        return f'<Ente {self.clave} - {self.nombre}>'
