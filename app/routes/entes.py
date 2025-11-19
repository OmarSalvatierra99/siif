"""
Rutas para gestión del catálogo de entes
"""
from flask import Blueprint, request, jsonify
from app.logging_config import get_logger
from app.models import db, Ente

logger = get_logger('app.routes.entes')

entes_bp = Blueprint('entes', __name__, url_prefix='/api/entes')


@entes_bp.route("", methods=["GET"])
def get_entes():
    """Obtiene lista de entes activos"""
    try:
        entes = Ente.query.filter_by(activo=True).order_by(Ente.clave).all()
        logger.info(f"Consultados {len(entes)} entes activos")
        return jsonify({
            "entes": [e.to_dict() for e in entes],
            "total": len(entes)
        })
    except Exception as e:
        logger.error(f"Error obteniendo entes: {str(e)}")
        return jsonify({"error": str(e)}), 500


@entes_bp.route("", methods=["POST"])
def create_ente():
    """Crea un nuevo ente"""
    try:
        data = request.json
        logger.info(f"Creando nuevo ente: {data.get('clave')}")

        # Validar que la clave no exista
        if Ente.query.filter_by(clave=data['clave']).first():
            logger.warning(f"Intento de crear ente con clave duplicada: {data['clave']}")
            return jsonify({"error": "La clave ya existe"}), 400

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

        logger.info(f"Ente creado exitosamente: {ente.clave}")
        return jsonify({"success": True, "ente": ente.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando ente: {str(e)}")
        return jsonify({"error": str(e)}), 500


@entes_bp.route("/<int:ente_id>", methods=["PUT"])
def update_ente(ente_id):
    """Actualiza un ente existente"""
    try:
        ente = Ente.query.get_or_404(ente_id)
        data = request.json

        logger.info(f"Actualizando ente: {ente.clave}")

        ente.nombre = data.get('nombre', ente.nombre)
        ente.siglas = data.get('siglas', ente.siglas)
        ente.tipo = data.get('tipo', ente.tipo)
        ente.ambito = data.get('ambito', ente.ambito)

        db.session.commit()

        logger.info(f"Ente actualizado exitosamente: {ente.clave}")
        return jsonify({"success": True, "ente": ente.to_dict()})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando ente {ente_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@entes_bp.route("/<int:ente_id>", methods=["DELETE"])
def delete_ente(ente_id):
    """Elimina (desactiva) un ente"""
    try:
        ente = Ente.query.get_or_404(ente_id)
        logger.info(f"Desactivando ente: {ente.clave}")

        ente.activo = False
        db.session.commit()

        logger.info(f"Ente desactivado exitosamente: {ente.clave}")
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error eliminando ente {ente_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500
