from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import Index

db = SQLAlchemy()

class Transaccion(db.Model):
    """Modelo para transacciones contables"""
    __tablename__ = 'transacciones'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Información de carga
    lote_id = db.Column(db.String(36), nullable=False, index=True)
    archivo_origen = db.Column(db.String(255), nullable=False)
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    usuario_carga = db.Column(db.String(100))
    
    # Cuenta contable completa
    cuenta_contable = db.Column(db.String(21), nullable=False, index=True)
    nombre_cuenta = db.Column(db.Text)
    
    # Componentes de cuenta (formato vertical)
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
    
    # Índices compuestos para consultas comunes
    __table_args__ = (
        Index('idx_cuenta_fecha', 'cuenta_contable', 'fecha_transaccion'),
        Index('idx_dependencia_fecha', 'dependencia', 'fecha_transaccion'),
        Index('idx_lote_cuenta', 'lote_id', 'cuenta_contable'),
    )
    
    def to_dict(self):
        """Convierte el modelo a diccionario"""
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


class LoteCarga(db.Model):
    """Modelo para rastrear lotes de carga"""
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


class Usuario(db.Model):
    """Modelo para usuarios del sistema"""
    __tablename__ = 'usuarios'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    nombre_completo = db.Column(db.String(200))
    email = db.Column(db.String(200))
    password_hash = db.Column(db.String(255))
    rol = db.Column(db.String(50), default='auditor')  # admin, auditor, consulta
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_acceso = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nombre_completo': self.nombre_completo,
            'email': self.email,
            'rol': self.rol,
            'activo': self.activo
        }


class ReporteGenerado(db.Model):
    """Modelo para rastrear reportes generados"""
    __tablename__ = 'reportes_generados'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    fecha_generacion = db.Column(db.DateTime, default=datetime.utcnow)
    tipo_reporte = db.Column(db.String(50))
    filtros_aplicados = db.Column(db.JSON)
    total_registros = db.Column(db.Integer)
    nombre_archivo = db.Column(db.String(255))

    usuario = db.relationship('Usuario', backref='reportes')

    def to_dict(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'fecha_generacion': self.fecha_generacion.isoformat() if self.fecha_generacion else None,
            'tipo_reporte': self.tipo_reporte,
            'filtros_aplicados': self.filtros_aplicados,
            'total_registros': self.total_registros,
            'nombre_archivo': self.nombre_archivo
        }


class Ente(db.Model):
    """Modelo para catálogo de entes públicos"""
    __tablename__ = 'entes'

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(20), unique=True, nullable=False, index=True)
    codigo = db.Column(db.String(50), nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    siglas = db.Column(db.String(50))
    tipo = db.Column(db.String(100))
    ambito = db.Column(db.String(50))
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
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
