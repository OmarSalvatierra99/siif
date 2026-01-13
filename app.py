from flask import Flask, render_template, request, jsonify, Response, send_file, session
from flask_cors import CORS
import io, os, time, json, threading, uuid, logging
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from config import config
from scripts.utils import db, Transaccion, LoteCarga, Usuario, ReporteGenerado, Ente
from scripts.utils import process_files_to_database
from sqlalchemy import func, and_, or_
import pandas as pd


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Configurar logging
    log_dir = Path('log')
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler('log/app.log', maxBytes=10*1024*1024, backupCount=10)
    handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # Inicializar extensiones
    db.init_app(app)
    CORS(app)

    # Crear tablas con manejo de errores
    with app.app_context():
        try:
            db.create_all()
            print("✓ Base de datos conectada")
        except Exception as e:
            print(f"❌ Error al conectar con la base de datos: {str(e)}")
            print(f"   Verifica: DATABASE_URL en .env")
            raise

    # Jobs para tracking de progreso
    jobs = {}
    jobs_lock = threading.Lock()

    stats_cache = {
        "resumen": {"ts": 0, "data": None},
        "dashboard": {"ts": 0, "data": None},
    }
    stats_cache_lock = threading.Lock()

    def _invalidate_stats_cache():
        with stats_cache_lock:
            for key in stats_cache:
                stats_cache[key]["ts"] = 0
                stats_cache[key]["data"] = None

    def _get_cached_stats(key, ttl, compute_fn):
        now = time.time()
        with stats_cache_lock:
            cached = stats_cache.get(key)
            if cached and cached["data"] is not None and (now - cached["ts"]) < ttl:
                return cached["data"]

        data = compute_fn()
        with stats_cache_lock:
            stats_cache[key] = {"ts": now, "data": data}
        return data

    def _get_example_files():
        example_dir = Path("example")
        if not example_dir.exists():
            return []
        files = []
        for pattern in ("*.xlsx", "*.xls", "*.xlsm"):
            files.extend(sorted(example_dir.glob(pattern)))
        return files

    def _get_loaded_archivos():
        loaded = set()
        for (archivos,) in db.session.query(LoteCarga.archivos).all():
            if not archivos:
                continue
            for archivo in archivos:
                if archivo:
                    loaded.add(Path(archivo).name)

        for (archivo_origen,) in db.session.query(Transaccion.archivo_origen).distinct().all():
            if archivo_origen:
                loaded.add(Path(archivo_origen).name)

        return loaded

    # ==================== RUTAS PRINCIPALES ====================

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/reporte-online")
    def reporte_online():
        return render_template("reporte_online.html")

    @app.route("/reporte-resumen")
    def reporte_resumen():
        return render_template("reporte_resumen.html")

    @app.route("/catalogo-entes")
    def catalogo_entes():
        return render_template("catalogo_entes.html")

    # ==================== API DE CARGA ====================

    @app.route("/api/process", methods=["POST"])
    def process():
        try:
            files = request.files.getlist("archivo")
            usuario = request.form.get("usuario", "sistema")

            if not files or all(f.filename == "" for f in files):
                return jsonify({"error": "No se subieron archivos"}), 400

            valid_files = []
            for f in files:
                if f.filename:
                    ext = os.path.splitext(f.filename)[1].lower()
                    if ext not in app.config["UPLOAD_EXTENSIONS"]:
                        return jsonify(
                            {"error": f"Archivo {f.filename} tiene extensión no válida"}
                        ), 400
                    valid_files.append(f)

            if not valid_files:
                return jsonify({"error": "No hay archivos válidos"}), 400

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

            def progress_callback(pct, msg):
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]["progress"] = pct
                        jobs[job_id]["message"] = msg

            files_in_memory = []
            for f in valid_files:
                f.seek(0)
                content = io.BytesIO(f.read())
                files_in_memory.append((f.filename, content))

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
                            jobs[job_id]["message"] = (
                                f"✅ {total:,} registros guardados en BD"
                            )
                        _invalidate_stats_cache()

                except Exception as e:
                    with jobs_lock:
                        jobs[job_id]["error"] = str(e)
                        jobs[job_id]["done"] = True

            thread = threading.Thread(target=process_files)
            thread.daemon = True
            thread.start()

            return jsonify({"job_id": job_id})

        except Exception as e:
            print(f"❌ Error procesando archivos: {str(e)}")
            return (
                jsonify(
                    {
                        "error": "Error al procesar archivos",
                        "detalle": str(e),
                        "tipo": type(e).__name__,
                    }
                ),
                500,
            )

    @app.route("/api/example/missing")
    def example_missing():
        try:
            example_files = _get_example_files()
            loaded = _get_loaded_archivos()

            missing = [f.name for f in example_files if f.name not in loaded]

            return jsonify({
                "example_total": len(example_files),
                "loaded_total": len(loaded),
                "missing": missing,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/example/process", methods=["POST"])
    def process_example():
        try:
            include_loaded = request.args.get("include_loaded", "false").lower() in (
                "1",
                "true",
                "yes",
            )
            usuario = "sistema"
            if request.is_json:
                usuario = request.json.get("usuario", usuario)
            else:
                usuario = request.form.get("usuario", usuario)

            example_files = _get_example_files()
            if not example_files:
                return jsonify({"error": "No hay archivos en example/"}), 400

            loaded = _get_loaded_archivos()
            files_to_process = [
                f for f in example_files if include_loaded or f.name not in loaded
            ]

            if not files_to_process:
                return jsonify({"message": "No hay archivos pendientes por cargar"}), 200

            files_in_memory = []
            for path in files_to_process:
                with path.open("rb") as handle:
                    files_in_memory.append((path.name, io.BytesIO(handle.read())))

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

            def progress_callback(pct, msg):
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]["progress"] = pct
                        jobs[job_id]["message"] = msg

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
                            jobs[job_id]["message"] = (
                                f"✅ {total:,} registros guardados en BD"
                            )

                except Exception as e:
                    with jobs_lock:
                        jobs[job_id]["error"] = str(e)
                        jobs[job_id]["done"] = True

            thread = threading.Thread(target=process_files)
            thread.daemon = True
            thread.start()

            return jsonify({
                "job_id": job_id,
                "archivos": [p.name for p in files_to_process],
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==================== STREAM DE PROGRESO ====================

    @app.route("/api/progress/<job_id>")
    def progress_stream(job_id):
        def generate():
            last_progress = -1
            max_wait = 300
            start_time = time.time()

            while True:
                if time.time() - start_time > max_wait:
                    yield f"data: {json.dumps({'progress': 100, 'message': 'Timeout', 'done': True})}\n\n"
                    break

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
        try:
            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 50, type=int)
            include_totals = request.args.get("include_totals", "false").lower() in (
                "1",
                "true",
                "yes",
            )
            base_query = Transaccion.query

            def apply_filters(filtered_query):
                if cuenta := request.args.get("cuenta_contable"):
                    filtered_query = filtered_query.filter(Transaccion.cuenta_contable.like(f"{cuenta}%"))
                if dependencia := request.args.get("dependencia"):
                    filtered_query = filtered_query.filter(Transaccion.dependencia == dependencia)
                if fecha_inicio := request.args.get("fecha_inicio"):
                    filtered_query = filtered_query.filter(Transaccion.fecha_transaccion >= fecha_inicio)
                if fecha_fin := request.args.get("fecha_fin"):
                    filtered_query = filtered_query.filter(Transaccion.fecha_transaccion <= fecha_fin)
                if poliza := request.args.get("poliza"):
                    filtered_query = filtered_query.filter(Transaccion.poliza.like(f"%{poliza}%"))

                # Filtros por componentes de cuenta
                if genero := request.args.get("genero"):
                    filtered_query = filtered_query.filter(Transaccion.genero == genero)
                if grupo := request.args.get("grupo"):
                    filtered_query = filtered_query.filter(Transaccion.grupo == grupo)
                if rubro := request.args.get("rubro"):
                    filtered_query = filtered_query.filter(Transaccion.rubro == rubro)
                if cuenta_num := request.args.get("cuenta"):
                    filtered_query = filtered_query.filter(Transaccion.cuenta == cuenta_num)
                if subcuenta := request.args.get("subcuenta"):
                    filtered_query = filtered_query.filter(Transaccion.subcuenta == subcuenta)
                if unidad_responsable := request.args.get("unidad_responsable"):
                    filtered_query = filtered_query.filter(Transaccion.unidad_responsable == unidad_responsable)
                if centro_costo := request.args.get("centro_costo"):
                    filtered_query = filtered_query.filter(Transaccion.centro_costo == centro_costo)
                if proyecto_presupuestario := request.args.get("proyecto_presupuestario"):
                    filtered_query = filtered_query.filter(Transaccion.proyecto_presupuestario == proyecto_presupuestario)
                if fuente := request.args.get("fuente"):
                    filtered_query = filtered_query.filter(Transaccion.fuente == fuente)
                if subfuente := request.args.get("subfuente"):
                    filtered_query = filtered_query.filter(Transaccion.subfuente == subfuente)
                if tipo_recurso := request.args.get("tipo_recurso"):
                    filtered_query = filtered_query.filter(Transaccion.tipo_recurso == tipo_recurso)
                if partida_presupuestal := request.args.get("partida_presupuestal"):
                    filtered_query = filtered_query.filter(Transaccion.partida_presupuestal == partida_presupuestal)

                # Filtros de texto con búsqueda parcial
                if nombre_cuenta := request.args.get("nombre_cuenta"):
                    filtered_query = filtered_query.filter(Transaccion.nombre_cuenta.like(f"%{nombre_cuenta}%"))
                if beneficiario := request.args.get("beneficiario"):
                    filtered_query = filtered_query.filter(Transaccion.beneficiario.like(f"%{beneficiario}%"))
                if descripcion := request.args.get("descripcion"):
                    filtered_query = filtered_query.filter(Transaccion.descripcion.like(f"%{descripcion}%"))
                if orden_pago := request.args.get("orden_pago"):
                    filtered_query = filtered_query.filter(Transaccion.orden_pago.like(f"%{orden_pago}%"))
                return filtered_query

            base_query = apply_filters(base_query)
            query = base_query.order_by(Transaccion.fecha_transaccion.desc())
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)

            response_payload = {
                "transacciones": [t.to_dict() for t in paginated.items],
                "total": paginated.total,
                "pages": paginated.pages,
                "page": page,
            }

            if include_totals:
                totales = base_query.with_entities(
                    func.coalesce(func.sum(Transaccion.cargos), 0),
                    func.coalesce(func.sum(Transaccion.abonos), 0),
                ).first()
                total_cargos = float(totales[0] or 0)
                total_abonos = float(totales[1] or 0)
                response_payload.update({
                    "total_cargos": total_cargos,
                    "total_abonos": total_abonos,
                    "total_diferencia": total_cargos - total_abonos,
                })

            return jsonify(response_payload)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dependencias/lista")
    def get_dependencias():
        try:
            deps = db.session.query(Transaccion.dependencia).distinct().filter(
                Transaccion.dependencia.isnot(None)
            ).order_by(Transaccion.dependencia).all()
            return jsonify({"dependencias": [d[0] for d in deps if d[0]]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/transacciones/resumen")
    def get_transacciones_resumen():
        try:
            def compute_resumen():
                totales = db.session.query(
                    func.count(Transaccion.id),
                    func.coalesce(func.sum(Transaccion.cargos), 0),
                    func.coalesce(func.sum(Transaccion.abonos), 0),
                ).first()

                total_registros = int(totales[0] or 0)
                total_cargos = float(totales[1] or 0)
                total_abonos = float(totales[2] or 0)
                diferencia = total_cargos - total_abonos
                coincide = abs(diferencia) < 0.005

                return {
                    "total_registros": total_registros,
                    "total_cargos": total_cargos,
                    "total_abonos": total_abonos,
                    "diferencia": diferencia,
                    "coincide": coincide,
                }

            payload = _get_cached_stats("resumen", 30, compute_resumen)
            return jsonify(payload)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/reportes/generar", methods=["POST"])
    def generar_reporte():
        try:
            filtros = request.json
            query = Transaccion.query

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

            # Filtros por componentes de cuenta
            if genero := filtros.get("genero"):
                query = query.filter(Transaccion.genero == genero)
            if grupo := filtros.get("grupo"):
                query = query.filter(Transaccion.grupo == grupo)
            if rubro := filtros.get("rubro"):
                query = query.filter(Transaccion.rubro == rubro)
            if cuenta_num := filtros.get("cuenta"):
                query = query.filter(Transaccion.cuenta == cuenta_num)
            if subcuenta := filtros.get("subcuenta"):
                query = query.filter(Transaccion.subcuenta == subcuenta)
            if unidad_responsable := filtros.get("unidad_responsable"):
                query = query.filter(Transaccion.unidad_responsable == unidad_responsable)
            if centro_costo := filtros.get("centro_costo"):
                query = query.filter(Transaccion.centro_costo == centro_costo)
            if proyecto_presupuestario := filtros.get("proyecto_presupuestario"):
                query = query.filter(Transaccion.proyecto_presupuestario == proyecto_presupuestario)
            if fuente := filtros.get("fuente"):
                query = query.filter(Transaccion.fuente == fuente)
            if subfuente := filtros.get("subfuente"):
                query = query.filter(Transaccion.subfuente == subfuente)
            if tipo_recurso := filtros.get("tipo_recurso"):
                query = query.filter(Transaccion.tipo_recurso == tipo_recurso)
            if partida_presupuestal := filtros.get("partida_presupuestal"):
                query = query.filter(Transaccion.partida_presupuestal == partida_presupuestal)

            # Filtros de texto con búsqueda parcial
            if nombre_cuenta := filtros.get("nombre_cuenta"):
                query = query.filter(Transaccion.nombre_cuenta.like(f"%{nombre_cuenta}%"))
            if beneficiario := filtros.get("beneficiario"):
                query = query.filter(Transaccion.beneficiario.like(f"%{beneficiario}%"))
            if descripcion := filtros.get("descripcion"):
                query = query.filter(Transaccion.descripcion.like(f"%{descripcion}%"))
            if orden_pago := filtros.get("orden_pago"):
                query = query.filter(Transaccion.orden_pago.like(f"%{orden_pago}%"))

            query = query.order_by(Transaccion.fecha_transaccion, Transaccion.cuenta_contable)
            transacciones = query.limit(100000).all()

            # Crear Excel
            output = io.BytesIO()
            df = pd.DataFrame([{
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
            } for t in transacciones])

            df.to_excel(output, index=False, sheet_name='Reporte')
            output.seek(0)

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'reporte_sipac_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dashboard/stats")
    def dashboard_stats():
        try:
            def compute_dashboard():
                stats = db.session.query(
                    func.count(Transaccion.id),
                    func.count(func.distinct(Transaccion.cuenta_contable)),
                    func.count(func.distinct(Transaccion.dependencia)),
                    func.coalesce(func.sum(Transaccion.cargos), 0),
                    func.coalesce(func.sum(Transaccion.abonos), 0),
                ).first()

                total_transacciones = int(stats[0] or 0)
                total_cuentas = int(stats[1] or 0)
                total_dependencias = int(stats[2] or 0)
                suma_cargos = float(stats[3] or 0)
                suma_abonos = float(stats[4] or 0)

                ultimos_lotes = (
                    LoteCarga.query.order_by(LoteCarga.fecha_carga.desc()).limit(5).all()
                )

                transacciones_mes = (
                    db.session.query(
                        func.date_trunc("month", Transaccion.fecha_transaccion).label("mes"),
                        func.count(Transaccion.id).label("total"),
                    )
                    .group_by("mes")
                    .order_by("mes")
                    .all()
                )

                return {
                    "total_transacciones": total_transacciones,
                    "total_cuentas": total_cuentas,
                    "total_dependencias": total_dependencias,
                    "suma_cargos": suma_cargos,
                    "suma_abonos": suma_abonos,
                    "ultimos_lotes": [l.to_dict() for l in ultimos_lotes],
                    "transacciones_mes": [
                        {"mes": str(mes), "total": total}
                        for mes, total in transacciones_mes
                    ],
                }

            payload = _get_cached_stats("dashboard", 30, compute_dashboard)
            return jsonify(payload)
        except Exception as e:
            print(f"❌ Error en dashboard/stats: {str(e)}")
            return (
                jsonify(
                    {"error": "Error al obtener estadísticas", "detalle": str(e)}
                ),
                500,
            )

    # ==================== API CATÁLOGO DE ENTES ====================

    @app.route("/api/entes")
    def get_entes():
        try:
            entes = Ente.query.filter_by(activo=True).order_by(Ente.clave).all()
            return jsonify({
                "entes": [e.to_dict() for e in entes],
                "total": len(entes)
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entes", methods=["POST"])
    def create_ente():
        try:
            data = request.json

            # Validar que la clave no exista
            if Ente.query.filter_by(clave=data['clave']).first():
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

            return jsonify({"success": True, "ente": ente.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entes/<int:ente_id>", methods=["PUT"])
    def update_ente(ente_id):
        try:
            ente = Ente.query.get_or_404(ente_id)
            data = request.json

            ente.nombre = data.get('nombre', ente.nombre)
            ente.siglas = data.get('siglas', ente.siglas)
            ente.tipo = data.get('tipo', ente.tipo)
            ente.ambito = data.get('ambito', ente.ambito)

            db.session.commit()
            return jsonify({"success": True, "ente": ente.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/entes/<int:ente_id>", methods=["DELETE"])
    def delete_ente(ente_id):
        try:
            ente = Ente.query.get_or_404(ente_id)
            ente.activo = False
            db.session.commit()
            return jsonify({"success": True})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    # ==================== ERRORES ====================

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "El archivo es demasiado grande. Máximo 500 MB"}), 413

    @app.errorhandler(404)
    def not_found(e):
        return (
            jsonify(
                {
                    "error": str(e.description)
                    if hasattr(e, "description")
                    else "No encontrado"
                }
            ),
            404,
        )

    @app.errorhandler(500)
    def internal_error(e):
        print(f"❌ Error 500: {str(e)}")
        return (
            jsonify({"error": "Error interno del servidor", "detalle": str(e)}),
            500,
        )

    return app


if __name__ == "__main__":
    app = create_app("development")

    print("\n" + "=" * 50)
    print("SIIF - Sistema de Procesamiento de Auxiliares Contables")
    print("=" * 50)
    print(f"✓ Servidor iniciado en puerto {config['development'].PORT}")
    print("\nPáginas disponibles:")
    print("  → http://localhost:5009          (Carga)")
    print("  → http://localhost:5009/dashboard (Dashboard)")
    print("  → http://localhost:5009/reportes  (Reportes)")
    print("=" * 50 + "\n")

    app.run(host="0.0.0.0", port=config["development"].PORT, debug=True, threaded=True)
