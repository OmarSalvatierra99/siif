"""
Modelo de transacciones contables
"""
from datetime import datetime
from sqlalchemy import Index
from app.models import db


class Transaccion(db.Model):
    """
    Modelo para transacciones contables

    Almacena las transacciones procesadas de los archivos Excel,
    incluyendo la descomposición de la cuenta contable de 21 caracteres
    en sus componentes individuales.
    """
    __tablename__ = 'transacciones'

    id = db.Column(db.Integer, primary_key=True)

    # Información de carga
    lote_id = db.Column(db.String(36), nullable=False, index=True)
    archivo_origen = db.Column(db.String(255), nullable=False)
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    usuario_carga = db.Column(db.String(100))

    # Cuenta contable completa (21 caracteres)
    cuenta_contable = db.Column(db.String(21), nullable=False, index=True)
    nombre_cuenta = db.Column(db.Text)

    # Componentes de cuenta contable (formato vertical)
    genero = db.Column(db.String(1), index=True)
    grupo = db.Column(db.String(1), index=True)
    rubro = db.Column(db.String(1), index=True)
    cuenta = db.Column(db.String(1), index=True)
    subcuenta = db.Column(db.String(1), index=True)
    dependencia = db.Column(db.String(2), index=True)
    unidad_responsable = db.Column(db.String(2), index=True)
    centro_costo = db.Column(db.String(2), index=True)
    proyecto_presupuestario = db.Column(db.String(2), index=True)
    fuente = db.Column(db.String(1), index=True)
    subfuente = db.Column(db.String(2), index=True)
    tipo_recurso = db.Column(db.String(1), index=True)
    partida_presupuestal = db.Column(db.String(4), index=True)

    # Datos de transacción
    fecha_transaccion = db.Column(db.Date, nullable=False, index=True)
    poliza = db.Column(db.String(50), index=True)
    beneficiario = db.Column(db.Text)
    descripcion = db.Column(db.Text)
    orden_pago = db.Column(db.String(50))

    # Montos
    saldo_inicial = db.Column(db.Numeric(15, 2), default=0)
    cargos = db.Column(db.Numeric(15, 2), default=0)
    abonos = db.Column(db.Numeric(15, 2), default=0)
    saldo_final = db.Column(db.Numeric(15, 2), default=0)

    # Índices compuestos para optimizar consultas comunes
    __table_args__ = (
        Index('idx_cuenta_fecha', 'cuenta_contable', 'fecha_transaccion'),
        Index('idx_dependencia_fecha', 'dependencia', 'fecha_transaccion'),
        Index('idx_lote_cuenta', 'lote_id', 'cuenta_contable'),
    )

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'lote_id': self.lote_id,
            'archivo_origen': self.archivo_origen,
            'fecha_carga': self.fecha_carga.isoformat() if self.fecha_carga else None,
            'cuenta_contable': self.cuenta_contable,
            'nombre_cuenta': self.nombre_cuenta,
            'genero': self.genero,
            'grupo': self.grupo,
            'rubro': self.rubro,
            'cuenta': self.cuenta,
            'subcuenta': self.subcuenta,
            'dependencia': self.dependencia,
            'unidad_responsable': self.unidad_responsable,
            'centro_costo': self.centro_costo,
            'proyecto_presupuestario': self.proyecto_presupuestario,
            'fuente': self.fuente,
            'subfuente': self.subfuente,
            'tipo_recurso': self.tipo_recurso,
            'partida_presupuestal': self.partida_presupuestal,
            'fecha_transaccion': self.fecha_transaccion.strftime('%d/%m/%Y') if self.fecha_transaccion else None,
            'poliza': self.poliza,
            'beneficiario': self.beneficiario,
            'descripcion': self.descripcion,
            'orden_pago': self.orden_pago,
            'saldo_inicial': float(self.saldo_inicial) if self.saldo_inicial else 0,
            'cargos': float(self.cargos) if self.cargos else 0,
            'abonos': float(self.abonos) if self.abonos else 0,
            'saldo_final': float(self.saldo_final) if self.saldo_final else 0,
        }

    def __repr__(self):
        return f'<Transaccion {self.cuenta_contable} - {self.fecha_transaccion}>'
