"""
Rutas para generación de reportes
"""
import io
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from app.logging_config import get_logger
from app.models import db, Transaccion

logger = get_logger('app.routes.reports')

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reportes')


@reports_bp.route("/generar", methods=["POST"])
def generar_reporte():
    """
    Genera un reporte Excel con las transacciones filtradas

    Acepta filtros en el body JSON y retorna un archivo Excel
    Límite: 100,000 registros por reporte
    """
    try:
        filtros = request.json
        logger.info(f"Generando reporte con filtros: {filtros}")

        # Construir query con filtros
        query = Transaccion.query

        # Aplicar filtros básicos
        if cuenta := filtros.get("cuenta_contable"):
            query = query.filter(Transaccion.cuenta_contable.like(f"{cuenta}%"))
        if dependencia := filtros.get("dependencia"):
            query = query.filter(Transaccion.dependencia == dependencia)
        if fecha_inicio := filtros.get("fecha_inicio"):
            query = query.filter(Transaccion.fecha_transaccion >= fecha_inicio)
        if fecha_fin := filtros.get("fecha_fin"):
            query = query.filter(Transaccion.fecha_transaccion <= fecha_fin)
        if poliza := filtros.get("poliza"):
            query = query.filter(Transaccion.poliza.like(f"%{poliza}%"))

        # Aplicar filtros por componentes de cuenta
        component_filters = {
            "genero": Transaccion.genero,
            "grupo": Transaccion.grupo,
            "rubro": Transaccion.rubro,
            "cuenta": Transaccion.cuenta,
            "subcuenta": Transaccion.subcuenta,
            "unidad_responsable": Transaccion.unidad_responsable,
            "centro_costo": Transaccion.centro_costo,
            "proyecto_presupuestario": Transaccion.proyecto_presupuestario,
            "fuente": Transaccion.fuente,
            "subfuente": Transaccion.subfuente,
            "tipo_recurso": Transaccion.tipo_recurso,
            "partida_presupuestal": Transaccion.partida_presupuestal,
        }

        for filter_name, model_field in component_filters.items():
            if value := filtros.get(filter_name):
                query = query.filter(model_field == value)

        # Aplicar filtros de texto con búsqueda parcial
        text_filters = {
            "nombre_cuenta": Transaccion.nombre_cuenta,
            "beneficiario": Transaccion.beneficiario,
            "descripcion": Transaccion.descripcion,
            "orden_pago": Transaccion.orden_pago,
        }

        for filter_name, model_field in text_filters.items():
            if value := filtros.get(filter_name):
                query = query.filter(model_field.like(f"%{value}%"))

        # Ordenar y limitar
        query = query.order_by(Transaccion.fecha_transaccion, Transaccion.cuenta_contable)
        transacciones = query.limit(100000).all()

        logger.info(f"Generando Excel con {len(transacciones)} transacciones")

        # Crear DataFrame
        data = []
        for t in transacciones:
            data.append({
                'Cuenta Contable': t.cuenta_contable,
                'Genero': t.genero,
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
                'Nombre de la Cuenta': t.nombre_cuenta,
                'FECHA': t.fecha_transaccion.strftime('%d/%m/%Y') if t.fecha_transaccion else '',
                'POLIZA': t.poliza,
                'BENEFICIARIO': t.beneficiario,
                'DESCRIPCION': t.descripcion,
                'O.P.': t.orden_pago,
                'SALDO INICIAL': float(t.saldo_inicial) if t.saldo_inicial else 0,
                'CARGOS': float(t.cargos) if t.cargos else 0,
                'ABONOS': float(t.abonos) if t.abonos else 0,
                'SALDO FINAL': float(t.saldo_final) if t.saldo_final else 0,
            })

        df = pd.DataFrame(data)

        # Crear archivo Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Reporte')

        output.seek(0)

        filename = f'reporte_sipac_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        logger.info(f"Reporte generado exitosamente: {filename}")

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Error generando reporte: {type(e).__name__} - {str(e)}")
        return jsonify({"error": f"Error generando reporte: {str(e)}"}), 500
