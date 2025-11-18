"""
Servicios de negocio para SIPAC
Contiene lógica reutilizable para consultas, filtros y reportes
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from io import BytesIO

import pandas as pd
from sqlalchemy import func

from models import db, Transaccion, LoteCarga, Ente
from utils import setup_logger


logger = setup_logger(__name__)


class QueryBuilder:
    """Constructor de queries con filtros dinámicos"""

    @staticmethod
    def apply_filters(query, filters: Dict[str, Any]):
        """
        Aplica filtros dinámicos a un query de Transaccion

        Args:
            query: Query de SQLAlchemy
            filters: Diccionario con filtros a aplicar

        Returns:
            Query con filtros aplicados
        """
        # Filtros de búsqueda parcial
        if cuenta := filters.get("cuenta_contable"):
            query = query.filter(Transaccion.cuenta_contable.like(f"{cuenta}%"))

        if dependencia := filters.get("dependencia"):
            query = query.filter(Transaccion.dependencia == dependencia)

        if poliza := filters.get("poliza"):
            query = query.filter(Transaccion.poliza.like(f"%{poliza}%"))

        # Filtros de fecha
        if fecha_inicio := filters.get("fecha_inicio"):
            query = query.filter(Transaccion.fecha_transaccion >= fecha_inicio)

        if fecha_fin := filters.get("fecha_fin"):
            query = query.filter(Transaccion.fecha_transaccion <= fecha_fin)

        # Filtros de componentes de cuenta (exactos)
        component_filters = [
            "genero", "grupo", "rubro", "cuenta", "subcuenta",
            "unidad_responsable", "centro_costo", "proyecto_presupuestario",
            "fuente", "subfuente", "tipo_recurso", "partida_presupuestal"
        ]

        for component in component_filters:
            if value := filters.get(component):
                query = query.filter(getattr(Transaccion, component) == value)

        # Filtros de texto con búsqueda parcial
        text_filters = {
            "nombre_cuenta": Transaccion.nombre_cuenta,
            "beneficiario": Transaccion.beneficiario,
            "descripcion": Transaccion.descripcion,
            "orden_pago": Transaccion.orden_pago
        }

        for key, column in text_filters.items():
            if value := filters.get(key):
                query = query.filter(column.like(f"%{value}%"))

        return query


class TransaccionService:
    """Servicio para operaciones con transacciones"""

    @staticmethod
    def get_transacciones_paginated(
        page: int = 1,
        per_page: int = 50,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Obtiene transacciones paginadas con filtros

        Args:
            page: Número de página
            per_page: Registros por página
            filters: Diccionario con filtros opcionales

        Returns:
            Diccionario con transacciones y metadata de paginación
        """
        query = Transaccion.query

        if filters:
            query = QueryBuilder.apply_filters(query, filters)

        query = query.order_by(Transaccion.fecha_transaccion.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            "transacciones": [t.to_dict() for t in paginated.items],
            "total": paginated.total,
            "pages": paginated.pages,
            "page": page,
            "per_page": per_page
        }

    @staticmethod
    def get_transacciones_for_export(
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100000
    ) -> List[Transaccion]:
        """
        Obtiene transacciones para exportación

        Args:
            filters: Diccionario con filtros opcionales
            limit: Número máximo de registros

        Returns:
            Lista de objetos Transaccion
        """
        query = Transaccion.query

        if filters:
            query = QueryBuilder.apply_filters(query, filters)

        query = query.order_by(
            Transaccion.fecha_transaccion,
            Transaccion.cuenta_contable
        )

        return query.limit(limit).all()

    @staticmethod
    def get_dependencias() -> List[str]:
        """
        Obtiene lista de dependencias únicas

        Returns:
            Lista de códigos de dependencia
        """
        deps = db.session.query(Transaccion.dependencia)\
            .distinct()\
            .filter(Transaccion.dependencia.isnot(None))\
            .order_by(Transaccion.dependencia)\
            .all()

        return [d[0] for d in deps if d[0]]

    @staticmethod
    def get_valores_unicos(campo: str) -> List[str]:
        """
        Obtiene valores únicos de un campo

        Args:
            campo: Nombre del campo

        Returns:
            Lista de valores únicos
        """
        if not hasattr(Transaccion, campo):
            raise ValueError(f"Campo {campo} no existe en Transaccion")

        column = getattr(Transaccion, campo)
        valores = db.session.query(column)\
            .distinct()\
            .filter(column.isnot(None))\
            .order_by(column)\
            .all()

        return [v[0] for v in valores if v[0]]


class ReporteService:
    """Servicio para generación de reportes"""

    @staticmethod
    def generar_reporte_excel(
        transacciones: List[Transaccion],
        incluir_resumen: bool = True
    ) -> BytesIO:
        """
        Genera un archivo Excel con transacciones y opcionalmente un resumen

        Args:
            transacciones: Lista de transacciones
            incluir_resumen: Si se incluye hoja de resumen

        Returns:
            BytesIO con archivo Excel
        """
        output = BytesIO()

        # Crear DataFrame principal
        data = []
        for t in transacciones:
            data.append({
                'Cuenta Contable': t.cuenta_contable,
                'Nombre de la Cuenta': t.nombre_cuenta,
                'Género': t.genero,
                'Grupo': t.grupo,
                'Rubro': t.rubro,
                'Cuenta': t.cuenta,
                'Subcuenta': t.subcuenta,
                'Dependencia': t.dependencia,
                'Unidad Responsable': t.unidad_responsable,
                'Centro de Costo': t.centro_costo,
                'Proyecto Presupuestario': t.proyecto_presupuestario,
                'Fuente': t.fuente,
                'SubFuente': t.subfuente,
                'Tipo de Recurso': t.tipo_recurso,
                'Partida Presupuestal': t.partida_presupuestal,
                'Fecha': t.fecha_transaccion.strftime('%d/%m/%Y') if t.fecha_transaccion else '',
                'Póliza': t.poliza,
                'Beneficiario': t.beneficiario,
                'Descripción': t.descripcion,
                'O.P.': t.orden_pago,
                'Saldo Inicial': float(t.saldo_inicial) if t.saldo_inicial else 0,
                'Cargos': float(t.cargos) if t.cargos else 0,
                'Abonos': float(t.abonos) if t.abonos else 0,
                'Saldo Final': float(t.saldo_final) if t.saldo_final else 0,
                'Archivo Origen': t.archivo_origen,
                'Lote ID': t.lote_id
            })

        df = pd.DataFrame(data)

        # Crear Excel writer
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Escribir hoja de transacciones
            df.to_excel(writer, index=False, sheet_name='Transacciones')

            # Agregar hoja de resumen si se solicita
            if incluir_resumen:
                resumen = ReporteService._generar_resumen(df)
                resumen.to_excel(writer, index=False, sheet_name='Resumen')

        output.seek(0)
        return output

    @staticmethod
    def _generar_resumen(df: pd.DataFrame) -> pd.DataFrame:
        """
        Genera un resumen estadístico de las transacciones

        Args:
            df: DataFrame con transacciones

        Returns:
            DataFrame con resumen
        """
        resumen_data = []

        # Resumen general
        resumen_data.append({
            'Métrica': 'Total de Transacciones',
            'Valor': f'{len(df):,}'
        })

        resumen_data.append({
            'Métrica': 'Total de Cuentas Únicas',
            'Valor': f'{df["Cuenta Contable"].nunique():,}'
        })

        resumen_data.append({
            'Métrica': 'Total de Dependencias',
            'Valor': f'{df["Dependencia"].nunique():,}'
        })

        # Resumen monetario
        total_cargos = df['Cargos'].sum()
        total_abonos = df['Abonos'].sum()

        resumen_data.append({
            'Métrica': 'Suma Total de Cargos',
            'Valor': f'${total_cargos:,.2f}'
        })

        resumen_data.append({
            'Métrica': 'Suma Total de Abonos',
            'Valor': f'${total_abonos:,.2f}'
        })

        resumen_data.append({
            'Métrica': 'Diferencia (Cargos - Abonos)',
            'Valor': f'${(total_cargos - total_abonos):,.2f}'
        })

        # Rango de fechas
        if 'Fecha' in df.columns and not df['Fecha'].empty:
            fechas = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
            fechas = fechas.dropna()

            if not fechas.empty:
                resumen_data.append({
                    'Métrica': 'Fecha Mínima',
                    'Valor': fechas.min().strftime('%d/%m/%Y')
                })

                resumen_data.append({
                    'Métrica': 'Fecha Máxima',
                    'Valor': fechas.max().strftime('%d/%m/%Y')
                })

        # Top 5 cuentas por monto
        resumen_data.append({'Métrica': '', 'Valor': ''})
        resumen_data.append({
            'Métrica': 'TOP 5 CUENTAS POR CARGOS',
            'Valor': ''
        })

        top_cuentas = df.groupby('Cuenta Contable')['Cargos'].sum()\
            .sort_values(ascending=False)\
            .head(5)

        for i, (cuenta, monto) in enumerate(top_cuentas.items(), 1):
            resumen_data.append({
                'Métrica': f'{i}. {cuenta}',
                'Valor': f'${monto:,.2f}'
            })

        # Top 5 dependencias
        resumen_data.append({'Métrica': '', 'Valor': ''})
        resumen_data.append({
            'Métrica': 'TOP 5 DEPENDENCIAS POR MONTO',
            'Valor': ''
        })

        top_deps = df.groupby('Dependencia')['Cargos'].sum()\
            .sort_values(ascending=False)\
            .head(5)

        for i, (dep, monto) in enumerate(top_deps.items(), 1):
            resumen_data.append({
                'Métrica': f'{i}. Dependencia {dep}',
                'Valor': f'${monto:,.2f}'
            })

        return pd.DataFrame(resumen_data)


class DashboardService:
    """Servicio para estadísticas del dashboard"""

    @staticmethod
    def get_estadisticas_generales() -> Dict[str, Any]:
        """
        Obtiene estadísticas generales del sistema

        Returns:
            Diccionario con estadísticas
        """
        stats = {}

        # Conteos generales
        stats['total_transacciones'] = db.session.query(
            func.count(Transaccion.id)
        ).scalar() or 0

        stats['total_cuentas'] = db.session.query(
            func.count(func.distinct(Transaccion.cuenta_contable))
        ).scalar() or 0

        stats['total_dependencias'] = db.session.query(
            func.count(func.distinct(Transaccion.dependencia))
        ).scalar() or 0

        # Sumas monetarias
        stats['suma_cargos'] = float(
            db.session.query(func.sum(Transaccion.cargos)).scalar() or 0
        )

        stats['suma_abonos'] = float(
            db.session.query(func.sum(Transaccion.abonos)).scalar() or 0
        )

        # Últimos lotes
        ultimos_lotes = LoteCarga.query\
            .order_by(LoteCarga.fecha_carga.desc())\
            .limit(5)\
            .all()

        stats['ultimos_lotes'] = [l.to_dict() for l in ultimos_lotes]

        # Transacciones por mes
        transacciones_mes = db.session.query(
            func.date_trunc('month', Transaccion.fecha_transaccion).label('mes'),
            func.count(Transaccion.id).label('total')
        ).group_by('mes').order_by('mes').all()

        stats['transacciones_mes'] = [
            {'mes': str(mes), 'total': total}
            for mes, total in transacciones_mes
        ]

        return stats

    @staticmethod
    def get_distribuciones() -> Dict[str, Any]:
        """
        Obtiene distribuciones de datos para visualización

        Returns:
            Diccionario con distribuciones
        """
        distribuciones = {}

        # Distribución por género
        por_genero = db.session.query(
            Transaccion.genero,
            func.count(Transaccion.id).label('count'),
            func.sum(Transaccion.cargos).label('total_cargos')
        ).group_by(Transaccion.genero).all()

        distribuciones['por_genero'] = [
            {
                'genero': g,
                'count': c,
                'total_cargos': float(tc or 0)
            }
            for g, c, tc in por_genero
        ]

        # Distribución por tipo de recurso
        por_tipo_recurso = db.session.query(
            Transaccion.tipo_recurso,
            func.count(Transaccion.id).label('count'),
            func.sum(Transaccion.cargos).label('total_cargos')
        ).group_by(Transaccion.tipo_recurso).all()

        distribuciones['por_tipo_recurso'] = [
            {
                'tipo_recurso': tr,
                'count': c,
                'total_cargos': float(tc or 0)
            }
            for tr, c, tc in por_tipo_recurso
        ]

        return distribuciones


class EnteService:
    """Servicio para catálogo de entes"""

    @staticmethod
    def get_entes_activos() -> List[Dict]:
        """
        Obtiene todos los entes activos

        Returns:
            Lista de diccionarios con entes
        """
        entes = Ente.query.filter_by(activo=True).order_by(Ente.clave).all()
        return [e.to_dict() for e in entes]

    @staticmethod
    def crear_ente(data: Dict) -> Ente:
        """
        Crea un nuevo ente

        Args:
            data: Diccionario con datos del ente

        Returns:
            Ente creado

        Raises:
            ValueError: Si la clave ya existe
        """
        # Validar que la clave no exista
        if Ente.query.filter_by(clave=data['clave']).first():
            raise ValueError("La clave ya existe")

        ente = Ente(
            clave=data['clave'],
            codigo=data['codigo'],
            nombre=data['nombre'],
            siglas=data.get('siglas', ''),
            tipo=data.get('tipo', ''),
            ambito=data.get('ambito', 'ESTATAL')
        )

        db.session.add(ente)
        db.session.commit()

        return ente

    @staticmethod
    def actualizar_ente(ente_id: int, data: Dict) -> Ente:
        """
        Actualiza un ente existente

        Args:
            ente_id: ID del ente
            data: Diccionario con datos a actualizar

        Returns:
            Ente actualizado

        Raises:
            ValueError: Si el ente no existe
        """
        ente = Ente.query.get(ente_id)
        if not ente:
            raise ValueError("Ente no encontrado")

        ente.nombre = data.get('nombre', ente.nombre)
        ente.siglas = data.get('siglas', ente.siglas)
        ente.tipo = data.get('tipo', ente.tipo)
        ente.ambito = data.get('ambito', ente.ambito)

        db.session.commit()
        return ente

    @staticmethod
    def eliminar_ente(ente_id: int) -> None:
        """
        Elimina (soft delete) un ente

        Args:
            ente_id: ID del ente

        Raises:
            ValueError: Si el ente no existe
        """
        ente = Ente.query.get(ente_id)
        if not ente:
            raise ValueError("Ente no encontrado")

        ente.activo = False
        db.session.commit()
