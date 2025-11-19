"""
Rutas para carga y procesamiento de archivos
"""
import io
import os
import time
import json
import uuid
import threading
from flask import Blueprint, request, jsonify, Response, current_app
from app.logging_config import get_logger
from app.services.data_processor import DataProcessor

logger = get_logger('app.routes.upload')

upload_bp = Blueprint('upload', __name__, url_prefix='/api')

# Jobs para tracking de progreso
jobs = {}
jobs_lock = threading.Lock()


@upload_bp.route("/process", methods=["POST"])
def process():
    """
    Endpoint para procesar archivos Excel

    Acepta múltiples archivos y los procesa en background,
    retornando un job_id para tracking de progreso
    """
    try:
        files = request.files.getlist("archivo")
        usuario = request.form.get("usuario", "sistema")

        logger.info(f"Nueva solicitud de procesamiento de {len(files)} archivos por usuario: {usuario}")

        # Validar que se subieron archivos
        if not files or all(f.filename == "" for f in files):
            logger.warning("Solicitud sin archivos")
            return jsonify({"error": "No se subieron archivos"}), 400

        # Validar extensiones
        valid_files = []
        allowed_extensions = current_app.config["UPLOAD_EXTENSIONS"]

        for f in files:
            if f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext not in allowed_extensions:
                    logger.warning(f"Archivo rechazado por extensión inválida: {f.filename}")
                    return jsonify(
                        {"error": f"Archivo {f.filename} tiene extensión no válida. Use: {', '.join(allowed_extensions)}"}
                    ), 400
                valid_files.append(f)

        if not valid_files:
            logger.warning("No hay archivos válidos después de filtrar")
            return jsonify({"error": "No hay archivos válidos"}), 400

        # Crear job
        job_id = str(uuid.uuid4())
        with jobs_lock:
            jobs[job_id] = {
                "progress": 0,
                "message": "Iniciando...",
                "done": False,
                "error": None,
                "lote_id": None,
                "total_registros": 0,
            }

        logger.info(f"Job creado: {job_id}")

        # Callback de progreso
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

        logger.info(f"Archivos cargados en memoria: {[f[0] for f in files_in_memory]}")

        # Procesar en thread separado
        def process_files():
            try:
                with current_app.app_context():
                    processor = DataProcessor(
                        max_workers=current_app.config.get('MAX_WORKERS', 4),
                        chunk_size=current_app.config.get('CHUNK_SIZE', 1000)
                    )

                    lote_id, total = processor.process_files(
                        files_in_memory, usuario, progress_callback
                    )

                    with jobs_lock:
                        jobs[job_id]["lote_id"] = lote_id
                        jobs[job_id]["total_registros"] = total
                        jobs[job_id]["done"] = True
                        jobs[job_id]["progress"] = 100
                        jobs[job_id]["message"] = f"✅ {total:,} registros guardados en BD"

                    logger.info(f"Job {job_id} completado exitosamente: {total} registros")

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error en job {job_id}: {error_msg}")
                with jobs_lock:
                    jobs[job_id]["error"] = error_msg
                    jobs[job_id]["done"] = True

        thread = threading.Thread(target=process_files)
        thread.daemon = True
        thread.start()

        return jsonify({"job_id": job_id})

    except Exception as e:
        logger.error(f"Error procesando solicitud: {type(e).__name__} - {str(e)}")
        return jsonify({
            "error": "Error al procesar archivos",
            "detalle": str(e),
            "tipo": type(e).__name__,
        }), 500


@upload_bp.route("/progress/<job_id>")
def progress_stream(job_id):
    """
    Endpoint de Server-Sent Events para streaming de progreso

    Args:
        job_id: ID del job a monitorear

    Returns:
        Stream de eventos con progreso
    """
    logger.info(f"Cliente conectado al stream de progreso: {job_id}")

    def generate():
        last_progress = -1
        max_wait = 300  # 5 minutos de timeout
        start_time = time.time()

        while True:
            # Timeout de seguridad
            if time.time() - start_time > max_wait:
                logger.warning(f"Timeout en stream de progreso: {job_id}")
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

            # Enviar actualización si hay cambios
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
                logger.info(f"Stream finalizado para job {job_id}")
                break

            time.sleep(0.2)

    return Response(generate(), mimetype="text/event-stream")
