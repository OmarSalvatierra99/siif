"""
Modelo para reportes generados
"""
from datetime import datetime
from app.models import db


class ReporteGenerado(db.Model):
    """
    Modelo para rastrear reportes generados

    Registra cada reporte Excel generado con sus filtros
    y metadatos para auditoría.
    """
    __tablename__ = 'reportes_generados'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    fecha_generacion = db.Column(db.DateTime, default=datetime.utcnow)
    tipo_reporte = db.Column(db.String(50))
    filtros_aplicados = db.Column(db.JSON)
    total_registros = db.Column(db.Integer)
    nombre_archivo = db.Column(db.String(255))

    # Relación con Usuario
    usuario = db.relationship('Usuario', backref='reportes')

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'fecha_generacion': self.fecha_generacion.isoformat() if self.fecha_generacion else None,
            'tipo_reporte': self.tipo_reporte,
            'filtros_aplicados': self.filtros_aplicados,
            'total_registros': self.total_registros,
            'nombre_archivo': self.nombre_archivo
        }

    def __repr__(self):
        return f'<ReporteGenerado {self.nombre_archivo}>'
