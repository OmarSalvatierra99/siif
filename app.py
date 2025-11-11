from flask import Flask, render_template, request, jsonify, Response, send_file, session
from flask_cors import CORS
import io, os, time, json, threading, uuid
from datetime import datetime
from config import config
from models import db, Transaccion, LoteCarga, Usuario, ReporteGenerado
from data_processor import process_files_to_database
from sqlalchemy import func, and_, or_
import pandas as pd


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

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

    # ==================== RUTAS PRINCIPALES ====================

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/reportes")
    def reportes():
        return render_template("reportes.html")

    @app.route("/reporte-online")
    def reporte_online():
        return render_template("reporte_online.html")

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
            query = Transaccion.query

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

            query = query.order_by(Transaccion.fecha_transaccion.desc())
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)

            return jsonify({
                "transacciones": [t.to_dict() for t in paginated.items],
                "total": paginated.total,
                "pages": paginated.pages,
                "page": page,
            })
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
            total_transacciones = db.session.query(func.count(Transaccion.id)).scalar()
            total_cuentas = db.session.query(
                func.count(func.distinct(Transaccion.cuenta_contable))
            ).scalar()
            total_dependencias = db.session.query(
                func.count(func.distinct(Transaccion.dependencia))
            ).scalar()

            suma_cargos = db.session.query(func.sum(Transaccion.cargos)).scalar() or 0
            suma_abonos = db.session.query(func.sum(Transaccion.abonos)).scalar() or 0

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

            return jsonify(
                {
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
                }
            )
        except Exception as e:
            print(f"❌ Error en dashboard/stats: {str(e)}")
            return (
                jsonify(
                    {"error": "Error al obtener estadísticas", "detalle": str(e)}
                ),
                500,
            )

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
    print("SIPAC - Sistema de Procesamiento de Auxiliares Contables")
    print("=" * 50)
    print("✓ Servidor iniciado en puerto 5020")
    print("\nPáginas disponibles:")
    print("  → http://localhost:5020          (Carga)")
    print("  → http://localhost:5020/dashboard (Dashboard)")
    print("  → http://localhost:5020/reportes  (Reportes)")
    print("=" * 50 + "\n")

    app.run(host="0.0.0.0", port=5020, debug=True, threaded=True)

