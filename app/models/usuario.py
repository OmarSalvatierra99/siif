"""
Modelo de usuarios del sistema
"""
from datetime import datetime
from app.models import db


class Usuario(db.Model):
    """
    Modelo para usuarios del sistema

    Gestiona usuarios con diferentes roles:
    - admin: Administrador con acceso completo
    - auditor: Puede revisar y generar reportes
    - consulta: Solo lectura
    """
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    nombre_completo = db.Column(db.String(200))
    email = db.Column(db.String(200))
    password_hash = db.Column(db.String(255))
    rol = db.Column(db.String(50), default='consulta')  # admin, auditor, consulta
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_acceso = db.Column(db.DateTime)

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON (sin password)"""
        return {
            'id': self.id,
            'username': self.username,
            'nombre_completo': self.nombre_completo,
            'email': self.email,
            'rol': self.rol,
            'activo': self.activo,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'ultimo_acceso': self.ultimo_acceso.isoformat() if self.ultimo_acceso else None
        }

    def __repr__(self):
        return f'<Usuario {self.username} - {self.rol}>'
