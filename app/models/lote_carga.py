"""
Modelo para lotes de carga
"""
from datetime import datetime
from app.models import db


class LoteCarga(db.Model):
    """
    Modelo para rastrear lotes de carga de archivos

    Cada vez que se procesan archivos, se crea un registro de lote
    que agrupa todas las transacciones cargadas en ese proceso.
    """
    __tablename__ = 'lotes_carga'

    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow)
    usuario = db.Column(db.String(100))
    archivos = db.Column(db.JSON)  # Lista de archivos procesados
    total_registros = db.Column(db.Integer, default=0)
    estado = db.Column(db.String(20), default='procesando')  # procesando, completado, error
    mensaje = db.Column(db.Text)

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'lote_id': self.lote_id,
            'fecha_carga': self.fecha_carga.isoformat() if self.fecha_carga else None,
            'usuario': self.usuario,
            'archivos': self.archivos,
            'total_registros': self.total_registros,
            'estado': self.estado,
            'mensaje': self.mensaje
        }

    def __repr__(self):
        return f'<LoteCarga {self.lote_id} - {self.estado}>'
