"""
SIPAC - Sistema de Procesamiento de Auxiliares Contables
Aplicación Flask refactorizada con arquitectura modular
"""
from flask import Flask, render_template, request, jsonify, Response, send_file
from flask_cors import CORS
import io
import os
import time
import json
import threading
import uuid
from datetime import datetime

from config import config
from models import db
from data_processor import process_files_to_database
from services import (
    TransaccionService, ReporteService,
    DashboardService, EnteService
)
from validators import (
    FileValidator, FiltrosValidator, EnteValidator,
    ValidationError, safe_int
)
from utils import setup_logger


logger = setup_logger(__name__)


def create_app(config_name="default"):
    """
    Factory para crear la aplicación Flask

    Args:
        config_name: Nombre de configuración a usar

    Returns:
        Aplicación Flask configurada
    """
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Inicializar extensiones
    db.init_app(app)
    CORS(app)

    # Crear tablas
    with app.app_context():
        try:
            db.create_all()
            logger.info("✓ Base de datos conectada exitosamente")
        except Exception as e:
            logger.error(f"Error conectando a base de datos: {str(e)}")
            logger.error("Verifica DATABASE_URL en .env")
            raise

    # Sistema de tracking de jobs para procesamiento asíncrono
    jobs = {}
    jobs_lock = threading.Lock()

    # ==================== RUTAS DE VISTAS ====================

    @app.route("/")
    def index():
        """Página principal de carga de archivos"""
        return render_template("index.html")

    @app.route("/reporte-online")
    def reporte_online():
        """Página de generación de reportes en línea"""
        return render_template("reporte_online.html")

    @app.route("/catalogo-entes")
    def catalogo_entes():
        """Página de catálogo de entes públicos"""
        return render_template("catalogo_entes.html")

    # ==================== API DE CARGA DE ARCHIVOS ====================

    @app.route("/api/process", methods=["POST"])
    def process():
        """
        Procesa archivos Excel subidos

        Returns:
            JSON con job_id para tracking de progreso
        """
        try:
            # Obtener archivos
            files = request.files.getlist("archivo")
            usuario = request.form.get("usuario", "sistema")

            # Validar que se subieron archivos
            if not files or all(f.filename == "" for f in files):
                return jsonify({"error": "No se subieron archivos"}), 400

            # Filtrar y validar archivos
            valid_files = []
            for f in files:
                if f.filename:
                    try:
                        FileValidator.validate_file(
                            f.filename,
                            f.content_length
                        )
                        valid_files.append(f)
                    except ValidationError as e:
                        return jsonify({"error": str(e)}), 400

            if not valid_files:
                return jsonify({"error": "No hay archivos válidos"}), 400

            # Crear job para tracking
            job_id = str(uuid.uuid4())
            with jobs_lock:
                jobs[job_id] = {
                    "progress": 0,
                    "message": "Iniciando procesamiento...",
                    "done": False,
                    "error": None,
                    "lote_id": None,
                    "total_registros": 0,
                }

            # Callback para actualizar progreso
            def progress_callback(pct, msg):
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]["progress"] = pct
                        jobs[job_id]["message"] = msg

            # Leer archivos en memoria
            files_in_memory = []
            for f in valid_files:
                f.seek(0)
                content = io.BytesIO(f.read())
                files_in_memory.append((f.filename, content))

            # Procesar en thread separado
            def process_files():
                try:
                    with app.app_context():
                        lote_id, total = process_files_to_database(
                            files_in_memory, usuario, progress_callback
                        )

                        with jobs_lock:
                            jobs[job_id]["lote_id"] = lote_id
                            jobs[job_id]["total_registros"] = total
                            jobs[job_id]["done"] = True
                            jobs[job_id]["progress"] = 100
                            jobs[job_id]["message"] = f"✅ {total:,} registros guardados"

                except Exception as e:
                    logger.error(f"Error en procesamiento: {str(e)}")
                    with jobs_lock:
                        jobs[job_id]["error"] = str(e)
                        jobs[job_id]["done"] = True

            thread = threading.Thread(target=process_files)
            thread.daemon = True
            thread.start()

            return jsonify({"job_id": job_id})

        except Exception as e:
            logger.error(f"Error en /api/process: {str(e)}")
            return jsonify({
                "error": "Error procesando solicitud",
                "detalle": str(e)
            }), 500

    @app.route("/api/progress/<job_id>")
    def progress_stream(job_id):
        """
        Stream de Server-Sent Events para tracking de progreso

        Args:
            job_id: ID del job a monitorear

        Returns:
            Response con stream de eventos
        """
        def generate():
            last_progress = -1
            max_wait = 300  # 5 minutos timeout
            start_time = time.time()

            while True:
                # Timeout
                if time.time() - start_time > max_wait:
                    yield f"data: {json.dumps({'progress': 100, 'message': 'Timeout', 'done': True})}\n\n"
                    break

                # Obtener estado del job
                with jobs_lock:
                    job = jobs.get(job_id)

                if not job:
                    time.sleep(0.1)
                    continue

                current_progress = job.get("progress", 0)
                message = job.get("message", "")
                done = job.get("done", False)
                error = job.get("error", None)
                lote_id = job.get("lote_id")
                total_registros = job.get("total_registros", 0)

                # Enviar update si cambió
                if current_progress != last_progress or done or error:
                    data = {
                        "progress": current_progress,
                        "message": message,
                        "done": done,
                        "error": error,
                        "lote_id": lote_id,
                        "total_registros": total_registros,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                    last_progress = current_progress

                if done or error:
                    break

                time.sleep(0.2)

        return Response(generate(), mimetype="text/event-stream")

    # ==================== API DE CONSULTAS ====================

    @app.route("/api/transacciones")
    def get_transacciones():
        """
        Obtiene transacciones con paginación y filtros

        Query params:
            - page: Número de página
            - per_page: Registros por página
            - Filtros diversos (ver FiltrosValidator)

        Returns:
            JSON con transacciones y metadata de paginación
        """
        try:
            # Obtener parámetros de paginación
            page = safe_int(request.args.get("page", 1), default=1, min_value=1)
            per_page = safe_int(request.args.get("per_page", 50), default=50, min_value=1)

            # Validar paginación
            FiltrosValidator.validate_pagination(
                page, per_page,
                app.config.get('MAX_ITEMS_PER_PAGE', 1000)
            )

            # Construir filtros
            filtros = {k: v for k, v in request.args.items()
                      if k not in ('page', 'per_page') and v}

            # Obtener transacciones
            result = TransaccionService.get_transacciones_paginated(
                page=page,
                per_page=per_page,
                filters=filtros if filtros else None
            )

            return jsonify(result)

        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"Error en /api/transacciones: {str(e)}")
            return jsonify({"error": "Error obteniendo transacciones"}), 500

    @app.route("/api/dependencias/lista")
    def get_dependencias():
        """
        Obtiene lista de dependencias únicas

        Returns:
            JSON con lista de dependencias
        """
        try:
            dependencias = TransaccionService.get_dependencias()
            return jsonify({"dependencias": dependencias})
        except Exception as e:
            logger.error(f"Error obteniendo dependencias: {str(e)}")
            return jsonify({"error": "Error obteniendo dependencias"}), 500

    # ==================== API DE REPORTES ====================

    @app.route("/api/reportes/generar", methods=["POST"])
    def generar_reporte():
        """
        Genera un reporte Excel con filtros aplicados

        Body:
            JSON con filtros opcionales

        Returns:
            Archivo Excel para descarga
        """
        try:
            filtros = request.json or {}

            # Validar filtros
            if filtros:
                FiltrosValidator.validate_filtros(filtros)

            # Obtener transacciones
            transacciones = TransaccionService.get_transacciones_for_export(
                filters=filtros if filtros else None,
                limit=100000
            )

            if not transacciones:
                return jsonify({"error": "No se encontraron transacciones"}), 404

            # Generar Excel con resumen
            output = ReporteService.generar_reporte_excel(
                transacciones,
                incluir_resumen=True
            )

            # Generar nombre de archivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f'reporte_sipac_{timestamp}.xlsx'

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )

        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"Error generando reporte: {str(e)}")
            return jsonify({"error": "Error generando reporte"}), 500

    # ==================== API DE DASHBOARD ====================

    @app.route("/api/dashboard/stats")
    def dashboard_stats():
        """
        Obtiene estadísticas para el dashboard

        Returns:
            JSON con estadísticas generales
        """
        try:
            stats = DashboardService.get_estadisticas_generales()
            return jsonify(stats)
        except Exception as e:
            logger.error(f"Error en dashboard/stats: {str(e)}")
            return jsonify({
                "error": "Error obteniendo estadísticas",
                "detalle": str(e)
            }), 500

    @app.route("/api/dashboard/distribuciones")
    def dashboard_distribuciones():
        """
        Obtiene distribuciones de datos para visualización

        Returns:
            JSON con distribuciones por diferentes dimensiones
        """
        try:
            distribuciones = DashboardService.get_distribuciones()
            return jsonify(distribuciones)
        except Exception as e:
            logger.error(f"Error obteniendo distribuciones: {str(e)}")
            return jsonify({"error": "Error obteniendo distribuciones"}), 500

    # ==================== API DE CATÁLOGO DE ENTES ====================

    @app.route("/api/entes")
    def get_entes():
        """
        Obtiene todos los entes activos

        Returns:
            JSON con lista de entes
        """
        try:
            entes = EnteService.get_entes_activos()
            return jsonify({
                "entes": entes,
                "total": len(entes)
            })
        except Exception as e:
            logger.error(f"Error obteniendo entes: {str(e)}")
            return jsonify({"error": "Error obteniendo entes"}), 500

    @app.route("/api/entes", methods=["POST"])
    def create_ente():
        """
        Crea un nuevo ente

        Body:
            JSON con datos del ente (clave, codigo, nombre, etc.)

        Returns:
            JSON con ente creado
        """
        try:
            data = request.json

            # Validar datos
            EnteValidator.validate_ente_data(data, es_creacion=True)

            # Crear ente
            ente = EnteService.crear_ente(data)

            return jsonify({
                "success": True,
                "ente": ente.to_dict()
            }), 201

        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"Error creando ente: {str(e)}")
            db.session.rollback()
            return jsonify({"error": "Error creando ente"}), 500

    @app.route("/api/entes/<int:ente_id>", methods=["PUT"])
    def update_ente(ente_id):
        """
        Actualiza un ente existente

        Args:
            ente_id: ID del ente

        Body:
            JSON con datos a actualizar

        Returns:
            JSON con ente actualizado
        """
        try:
            data = request.json

            # Validar datos
            EnteValidator.validate_ente_data(data, es_creacion=False)

            # Actualizar ente
            ente = EnteService.actualizar_ente(ente_id, data)

            return jsonify({
                "success": True,
                "ente": ente.to_dict()
            })

        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            logger.error(f"Error actualizando ente: {str(e)}")
            db.session.rollback()
            return jsonify({"error": "Error actualizando ente"}), 500

    @app.route("/api/entes/<int:ente_id>", methods=["DELETE"])
    def delete_ente(ente_id):
        """
        Elimina (soft delete) un ente

        Args:
            ente_id: ID del ente

        Returns:
            JSON con confirmación
        """
        try:
            EnteService.eliminar_ente(ente_id)
            return jsonify({"success": True})

        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            logger.error(f"Error eliminando ente: {str(e)}")
            db.session.rollback()
            return jsonify({"error": "Error eliminando ente"}), 500

    # ==================== MANEJO DE ERRORES ====================

    @app.errorhandler(413)
    def too_large(e):
        """Maneja archivos demasiado grandes"""
        return jsonify({
            "error": "Archivo demasiado grande",
            "detalle": "Tamaño máximo: 500 MB"
        }), 413

    @app.errorhandler(404)
    def not_found(e):
        """Maneja recursos no encontrados"""
        return jsonify({
            "error": str(e.description) if hasattr(e, "description") else "No encontrado"
        }), 404

    @app.errorhandler(500)
    def internal_error(e):
        """Maneja errores internos del servidor"""
        logger.error(f"Error 500: {str(e)}")
        return jsonify({
            "error": "Error interno del servidor",
            "detalle": str(e) if app.debug else "Contacte al administrador"
        }), 500

    @app.errorhandler(ValidationError)
    def handle_validation_error(e):
        """Maneja errores de validación"""
        return jsonify({"error": str(e)}), 400

    return app


if __name__ == "__main__":
    app = create_app("development")

    print("\n" + "=" * 60)
    print("SIPAC - Sistema de Procesamiento de Auxiliares Contables")
    print("=" * 60)
    print("✓ Servidor iniciado en puerto 5020")
    print("\nPáginas disponibles:")
    print("  → http://localhost:5020/              (Carga de archivos)")
    print("  → http://localhost:5020/reporte-online (Reportes en línea)")
    print("  → http://localhost:5020/catalogo-entes (Catálogo de entes)")
    print("\nAPI Endpoints:")
    print("  → POST /api/process                    (Procesar archivos)")
    print("  → GET  /api/transacciones              (Consultar transacciones)")
    print("  → POST /api/reportes/generar           (Generar reportes)")
    print("  → GET  /api/dashboard/stats            (Estadísticas)")
    print("  → GET  /api/entes                      (Catálogo de entes)")
    print("=" * 60 + "\n")

    app.run(host="0.0.0.0", port=5020, debug=True, threaded=True)
