"""
Rutas API para consultas y estadísticas
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import func
from app.logging_config import get_logger
from app.models import db, Transaccion, LoteCarga

logger = get_logger('app.routes.api')

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route("/transacciones")
def get_transacciones():
    """
    Obtiene transacciones con filtros y paginación

    Query params:
        - page: Número de página (default: 1)
        - per_page: Registros por página (default: 50)
        - cuenta_contable: Filtro por cuenta (búsqueda con LIKE)
        - dependencia: Filtro por dependencia
        - fecha_inicio: Fecha inicial (YYYY-MM-DD)
        - fecha_fin: Fecha final (YYYY-MM-DD)
        - poliza: Filtro por póliza
        - Otros filtros por componentes de cuenta y campos de texto
    """
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)

        logger.info(f"Consultando transacciones - página {page}, {per_page} por página")

        query = Transaccion.query

        # Filtros básicos
        if cuenta := request.args.get("cuenta_contable"):
            query = query.filter(Transaccion.cuenta_contable.like(f"{cuenta}%"))
        if dependencia := request.args.get("dependencia"):
            query = query.filter(Transaccion.dependencia == dependencia)
        if fecha_inicio := request.args.get("fecha_inicio"):
            query = query.filter(Transaccion.fecha_transaccion >= fecha_inicio)
        if fecha_fin := request.args.get("fecha_fin"):
            query = query.filter(Transaccion.fecha_transaccion <= fecha_fin)
        if poliza := request.args.get("poliza"):
            query = query.filter(Transaccion.poliza.like(f"%{poliza}%"))

        # Filtros por componentes de cuenta
        component_filters = [
            ("genero", Transaccion.genero),
            ("grupo", Transaccion.grupo),
            ("rubro", Transaccion.rubro),
            ("cuenta", Transaccion.cuenta),
            ("subcuenta", Transaccion.subcuenta),
            ("unidad_responsable", Transaccion.unidad_responsable),
            ("centro_costo", Transaccion.centro_costo),
            ("proyecto_presupuestario", Transaccion.proyecto_presupuestario),
            ("fuente", Transaccion.fuente),
            ("subfuente", Transaccion.subfuente),
            ("tipo_recurso", Transaccion.tipo_recurso),
            ("partida_presupuestal", Transaccion.partida_presupuestal),
        ]

        for param_name, model_field in component_filters:
            if value := request.args.get(param_name):
                query = query.filter(model_field == value)

        # Filtros de texto con búsqueda parcial
        text_filters = [
            ("nombre_cuenta", Transaccion.nombre_cuenta),
            ("beneficiario", Transaccion.beneficiario),
            ("descripcion", Transaccion.descripcion),
            ("orden_pago", Transaccion.orden_pago),
        ]

        for param_name, model_field in text_filters:
            if value := request.args.get(param_name):
                query = query.filter(model_field.like(f"%{value}%"))

        # Ordenar y paginar
        query = query.order_by(Transaccion.fecha_transaccion.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        logger.info(f"Retornando {len(paginated.items)} transacciones de {paginated.total} totales")

        return jsonify({
            "transacciones": [t.to_dict() for t in paginated.items],
            "total": paginated.total,
            "pages": paginated.pages,
            "page": page,
        })

    except Exception as e:
        logger.error(f"Error consultando transacciones: {str(e)}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/dependencias/lista")
def get_dependencias():
    """Obtiene lista de dependencias únicas"""
    try:
        deps = db.session.query(Transaccion.dependencia).distinct().filter(
            Transaccion.dependencia.isnot(None)
        ).order_by(Transaccion.dependencia).all()

        dependencias = [d[0] for d in deps if d[0]]
        logger.info(f"Consultadas {len(dependencias)} dependencias únicas")

        return jsonify({"dependencias": dependencias})

    except Exception as e:
        logger.error(f"Error obteniendo dependencias: {str(e)}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/dashboard/stats")
def dashboard_stats():
    """
    Obtiene estadísticas para el dashboard

    Returns:
        JSON con:
        - total_transacciones
        - total_cuentas
        - total_dependencias
        - suma_cargos
        - suma_abonos
        - ultimos_lotes (últimos 5)
        - transacciones_mes (agrupado por mes)
    """
    try:
        logger.info("Generando estadísticas de dashboard")

        # Contadores básicos
        total_transacciones = db.session.query(func.count(Transaccion.id)).scalar()
        total_cuentas = db.session.query(
            func.count(func.distinct(Transaccion.cuenta_contable))
        ).scalar()
        total_dependencias = db.session.query(
            func.count(func.distinct(Transaccion.dependencia))
        ).scalar()

        # Sumas monetarias
        suma_cargos = db.session.query(func.sum(Transaccion.cargos)).scalar() or 0
        suma_abonos = db.session.query(func.sum(Transaccion.abonos)).scalar() or 0

        # Últimos lotes
        ultimos_lotes = (
            LoteCarga.query.order_by(LoteCarga.fecha_carga.desc()).limit(5).all()
        )

        # Transacciones por mes
        transacciones_mes = (
            db.session.query(
                func.date_trunc("month", Transaccion.fecha_transaccion).label("mes"),
                func.count(Transaccion.id).label("total"),
            )
            .group_by("mes")
            .order_by("mes")
            .all()
        )

        logger.info(f"Estadísticas generadas: {total_transacciones} transacciones, {total_cuentas} cuentas")

        return jsonify({
            "total_transacciones": total_transacciones,
            "total_cuentas": total_cuentas,
            "total_dependencias": total_dependencias,
            "suma_cargos": float(suma_cargos),
            "suma_abonos": float(suma_abonos),
            "ultimos_lotes": [l.to_dict() for l in ultimos_lotes],
            "transacciones_mes": [
                {"mes": str(mes), "total": total}
                for mes, total in transacciones_mes
            ],
        })

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {type(e).__name__} - {str(e)}")
        return jsonify({
            "error": "Error al obtener estadísticas",
            "detalle": str(e)
        }), 500
