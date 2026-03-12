from flask import Flask, render_template, request, jsonify, Response, send_file, session, redirect, url_for
from flask_cors import CORS
import io, os, time, json, threading, uuid, logging, re
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from werkzeug.security import check_password_hash
from config import config
from scripts.utils import db, Transaccion, LoteCarga, Usuario, ReporteGenerado, Ente
from scripts.utils import process_files_to_database
from sqlalchemy import func, and_, or_, inspect, text
from sqlalchemy.exc import IntegrityError
import pandas as pd

def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    def _get_active_user(username):
        normalized = (username or "").strip().lower()
        if not normalized:
            return None
        return (
            Usuario.query
            .filter(
                func.lower(Usuario.username) == normalized,
                Usuario.activo.is_(True)
            )
            .first()
        )

    def _is_authenticated():
        return _get_active_user(session.get("auth_user")) is not None

    def _safe_next_url(raw_url):
        url = (raw_url or "").strip()
        if not url.startswith("/") or url.startswith("//"):
            return ""
        return url

    @app.before_request
    def require_login():
        if request.method == "OPTIONS":
            return None
        if request.endpoint in {"login", "logout", "static"}:
            return None
        if request.path.startswith("/static/") or request.endpoint is None:
            return None
        if session.get("auth_user") and not _is_authenticated():
            session.clear()
        if _is_authenticated():
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "Sesión requerida"}), 401
        next_url = request.full_path.rstrip("?")
        return redirect(url_for("login", next=next_url))

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

            def _normalize_nombre(value):
                s = str(value or "").strip().lower()
                rep = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
                for k, v in rep.items():
                    s = s.replace(k, v)
                s = re.sub(r"\s+", " ", s)
                return s

            def _ensure_entes_dd_column():
                inspector = inspect(db.engine)
                if "entes" not in inspector.get_table_names():
                    return
                columns = {col["name"] for col in inspector.get_columns("entes")}
                if "dd" in columns:
                    return
                db.session.execute(text("ALTER TABLE entes ADD COLUMN dd VARCHAR(10)"))
                db.session.commit()

            def _ensure_lotes_tipo_archivo_column():
                inspector = inspect(db.engine)
                if "lotes_carga" not in inspector.get_table_names():
                    return
                columns = {col["name"] for col in inspector.get_columns("lotes_carga")}
                if "tipo_archivo" in columns:
                    return
                db.session.execute(
                    text("ALTER TABLE lotes_carga ADD COLUMN tipo_archivo VARCHAR(20)")
                )
                db.session.commit()

            def _catalog_value(value):
                if pd.isna(value):
                    return ""
                if isinstance(value, float):
                    if value.is_integer():
                        return str(int(value))
                    return str(value).rstrip("0").rstrip(".")
                return str(value).strip()

            def _catalog_codigo(value):
                return _catalog_value(value).rstrip(".")

            def _seed_entes_catalogo():
                if Ente.query.count() > 0:
                    return

                catalog_specs = [
                    ("Estatales.xlsx", "EST", "ESTATAL"),
                    ("Municipales.xlsx", "MUN", "MUNICIPAL"),
                ]
                pending_entes = []

                for filename, prefix, ambito in catalog_specs:
                    catalog_path = Path(app.root_path) / "catalogos" / filename
                    if not catalog_path.exists():
                        continue

                    df = pd.read_excel(catalog_path, dtype=object)
                    for row in df.to_dict(orient="records"):
                        codigo = _catalog_codigo(row.get("NUM"))
                        nombre = _catalog_value(row.get("NOMBRE"))
                        if not codigo or not nombre:
                            continue

                        pending_entes.append({
                            "clave": f"{prefix}-{codigo}",
                            "codigo": codigo,
                            "dd": "0A" if ambito == "MUNICIPAL" else "",
                            "nombre": nombre,
                            "siglas": _catalog_value(row.get("SIGLAS")),
                            "tipo": _catalog_value(row.get("CLASIFICACION")),
                            "ambito": ambito,
                            "activo": True,
                        })

                if not pending_entes:
                    return

                for payload in pending_entes:
                    db.session.add(Ente(**payload))

                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    for payload in pending_entes:
                        if Ente.query.filter_by(clave=payload["clave"]).first():
                            continue
                        db.session.add(Ente(**payload))
                    db.session.commit()

            def _seed_entes_dd():
                dd_rules = [
                    (_normalize_nombre("PODER LEGISLATIVO DEL ESTADO DE TLAXCALA"), "01"),
                    (_normalize_nombre("PODER JUDICIAL DEL ESTADO DE TLAXCALA"), "02"),
                    (_normalize_nombre("UNIVERSIDAD AUTÓNOMA DE TLAXCALA"), "3"),
                    (_normalize_nombre("DESPACHO DE LA GOBERNADORA"), "4"),
                    (_normalize_nombre("SECRETARÍA DE GOBIERNO"), "5"),
                    (_normalize_nombre("OFICIALÍA MAYOR DE GOBIERNO"), "6"),
                    (_normalize_nombre("SECRETARÍA DE FINANZAS"), "8"),
                    (_normalize_nombre("SECRETARÍA DE DESARROLLO ECONÓMICO"), "0B"),
                    (_normalize_nombre("SECRETARÍA DE TURISMO"), "0C"),
                    (_normalize_nombre("SECRETARÍA DE INFRAESTRUCTURA"), "0D"),
                    (_normalize_nombre("SECRETARÍA DE EDUCACIÓN PÚBLICA"), "0E"),
                    (_normalize_nombre("SECRETARÍA DE MOVILIDAD Y TRANSPORTE"), "0F"),
                    (_normalize_nombre("O.P.D SALUD DE TLAXCALA"), "0G"),
                    (_normalize_nombre("SECRETARÍA ANTICORRUPCIÓN Y BUEN GOBIERNO"), "0H"),
                    (_normalize_nombre("SECRETARÍA DE IMPULSO AGROPECUARIO"), "0I"),
                    (_normalize_nombre("COORDINACIÓN DE COMUNICACIÓN"), "0K"),
                    (_normalize_nombre("SECRETARÍA DE MEDIO AMBIENTE"), "0L"),
                    (_normalize_nombre("COMISIÓN ESTATAL DE DERECHOS HUMANOS"), "0N"),
                    (_normalize_nombre("INSTITUTO TLAXCALTECA DE ELECCIONES"), "0O"),
                    (_normalize_nombre("COORDINACIÓN ESTATAL DE PROTECCIÓN CIVIL"), "0P"),
                    (_normalize_nombre("CONSEJO ESTATAL DE POBLACIÓN"), "0Q"),
                    (_normalize_nombre("SECRETARIADO EJECUTIVO DEL SISTEMA ESTATAL DE SEGURIDAD PÚBLICA"), "0R"),
                    (_normalize_nombre("EL COLEGIO DE TLAXCALA A.C."), "1A"),
                    (_normalize_nombre("CENTRO DE CONCILIACIÓN LABORAL DEL ESTADO DE TLAXCALA"), "20"),
                    (_normalize_nombre("SECRETARÍA DE BIENESTAR"), "21"),
                    (_normalize_nombre("SECRETARÍA DE TRABAJO Y COMPETITIVIDAD"), "22"),
                    (_normalize_nombre("MUNICIPIOS"), "0A"),
                    (_normalize_nombre("TRIBUNAL DE JUSTICIA ADMINISTRATIVA"), "23"),
                    (_normalize_nombre("PROCURADURÍA DE PROTECCIÓN AL AMBIENTE DEL ESTADO DE TLAXCALA"), "24"),
                    (_normalize_nombre("COMISIÓN ESTATAL DEL AGUA Y SANEAMIENTO DEL ESTADO DE TLAXCALA"), "25"),
                    (_normalize_nombre("INSTITUTO DE FAUNA SILVESTRE PARA EL ESTADO DE TLAXCALA"), "26"),
                    (_normalize_nombre("UNIVERSIDAD INTERCULTURAL DE TLAXCALA"), "27"),
                    (_normalize_nombre("ARCHIVO GENERAL E HISTÓRICO DEL ESTADO DE TLAXCALA"), "28"),
                    (_normalize_nombre("FISCALÍA GENERAL DE JUSTICIA DEL ESTADO DE TLAXCALA"), "2A"),
                    (_normalize_nombre("CONSEJERÍA JURÍDICA DEL EJECUTIVO"), "2B"),
                    (_normalize_nombre("ALL MUNICIPIOS"), "0A"),
                ]
                dd_siglas_map = {
                    _normalize_nombre("CORACYT"): "0X",
                    _normalize_nombre("COLTLAX"): "1A",
                    _normalize_nombre("CEAVIT"): "1H",
                    _normalize_nombre("FOMTLAX"): "0W",
                    _normalize_nombre("ICATLAX"): "1K",
                    _normalize_nombre("ITST"): "16",
                    _normalize_nombre("ITIFE"): "14",
                    _normalize_nombre("SFP"): "0H",
                    _normalize_nombre("UPT"): "15",
                    _normalize_nombre("SMET"): "1C",
                    _normalize_nombre("SOTyV"): "1Q",
                    _normalize_nombre("SSC"): "1R",
                    _normalize_nombre("CGPI"): "1Y",
                    _normalize_nombre("ITDT"): "0Y",
                    _normalize_nombre("ITAES"): "1F",
                    _normalize_nombre("CEAM"): "1G",
                    _normalize_nombre("CAT"): "1X",
                    _normalize_nombre("ITJ"): "1I",
                    _normalize_nombre("ITEA"): "18",
                    _normalize_nombre("OPD"): "0G",
                    _normalize_nombre("SEDIF"): "1D",
                    _normalize_nombre("USET"): "1M",
                    _normalize_nombre("UTT"): "17",
                    _normalize_nombre("TCyA"): "1P",
                    _normalize_nombre("SESAET"): "1Z",
                    _normalize_nombre("COBAT"): "13",
                    _normalize_nombre("CECYTE"): "12",
                    _normalize_nombre("IDET"): "10",
                    _normalize_nombre("FIDECIX"): "0U",
                    _normalize_nombre("IDC"): "0S",
                    _normalize_nombre("SECRETARÍA DE CULTURA"): "0Z",
                    _normalize_nombre("OPD_SALUD"): "06",
                    _normalize_nombre("UPTREP"): "1U",
                    _normalize_nombre("TET"): "1W",
                    _normalize_nombre("IAIP"): "1O",
                    _normalize_nombre("CONALEP"): "1N",
                    _normalize_nombre("CRI-ESCUELA"): "06",
                    _normalize_nombre("SC"): "0Z",
                    _normalize_nombre("LA_LIBERTAD"): "0Z",
                    _normalize_nombre("PCET"): "06",
                }
                entes = Ente.query.all()
                changed = False
                for ente in entes:
                    normalized_nombre = _normalize_nombre(ente.nombre)
                    dd = None
                    for needle, dd_value in dd_rules:
                        if needle and needle in normalized_nombre:
                            dd = dd_value
                            break
                    if not dd and ente.ambito and ente.ambito.strip().upper() == "MUNICIPAL":
                        dd = "0A"
                    if not dd and ente.siglas:
                        dd = dd_siglas_map.get(_normalize_nombre(ente.siglas))
                    if dd and len(dd) == 1 and dd.isdigit():
                        dd = dd.zfill(2)
                    if not dd and ente.dd:
                        current_dd = str(ente.dd).strip()
                        if len(current_dd) == 1 and current_dd.isdigit():
                            dd = current_dd.zfill(2)
                    if dd and ente.dd != dd:
                        ente.dd = dd
                        changed = True
                if changed:
                    db.session.commit()

            _ensure_entes_dd_column()
            _ensure_lotes_tipo_archivo_column()
            _seed_entes_catalogo()
            _seed_entes_dd()
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

    TRANSACTION_FACET_FIELDS = {
        "cuenta_contable": {
            "column": Transaccion.cuenta_contable,
            "match": "prefix",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "genero": {
            "column": Transaccion.genero,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "grupo": {
            "column": Transaccion.grupo,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "rubro": {
            "column": Transaccion.rubro,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "cuenta": {
            "column": Transaccion.cuenta,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "subcuenta": {
            "column": Transaccion.subcuenta,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "dependencia": {
            "column": Transaccion.dependencia,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "unidad_responsable": {
            "column": Transaccion.unidad_responsable,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "centro_costo": {
            "column": Transaccion.centro_costo,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "proyecto_presupuestario": {
            "column": Transaccion.proyecto_presupuestario,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "fuente": {
            "column": Transaccion.fuente,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "subfuente": {
            "column": Transaccion.subfuente,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "tipo_recurso": {
            "column": Transaccion.tipo_recurso,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
        "partida_presupuestal": {
            "column": Transaccion.partida_presupuestal,
            "match": "exact",
            "search_match": "prefix",
            "kind": "facet",
            "multiple": True,
        },
    }

    TRANSACTION_TEXT_FIELDS = {
        "nombre_cuenta": {
            "column": Transaccion.nombre_cuenta,
            "match": "contains",
            "search_match": "contains",
            "kind": "text",
            "multiple": True,
        },
        "beneficiario": {
            "column": Transaccion.beneficiario,
            "match": "contains",
            "search_match": "contains",
            "kind": "text",
            "multiple": True,
        },
        "descripcion": {
            "column": Transaccion.descripcion,
            "match": "contains",
            "search_match": "contains",
            "kind": "text",
            "multiple": True,
        },
        "orden_pago": {
            "column": Transaccion.orden_pago,
            "match": "contains",
            "search_match": "contains",
            "kind": "text",
            "multiple": True,
        },
        "poliza": {
            "column": Transaccion.poliza,
            "match": "contains",
            "search_match": "contains",
            "kind": "text",
            "multiple": True,
        },
    }

    TRANSACTION_RANGE_FIELDS = {
        "fecha_inicio": {
            "column": Transaccion.fecha_transaccion,
            "op": "gte",
            "kind": "range",
        },
        "fecha_fin": {
            "column": Transaccion.fecha_transaccion,
            "op": "lte",
            "kind": "range",
        },
    }

    TRANSACTION_FILTERS = {
        **TRANSACTION_FACET_FIELDS,
        **TRANSACTION_TEXT_FIELDS,
        **TRANSACTION_RANGE_FIELDS,
    }
    TRANSACTION_OPTION_FIELDS = [
        *TRANSACTION_FACET_FIELDS.keys(),
        *TRANSACTION_TEXT_FIELDS.keys(),
    ]

    def _sanitize_filter_values(raw_values):
        if isinstance(raw_values, (list, tuple, set)):
            candidates = raw_values
        else:
            candidates = [raw_values]

        sanitized = []
        seen = set()

        for raw_value in candidates:
            if raw_value is None:
                continue

            value = str(raw_value).strip()
            if not value:
                continue

            comparable = value.casefold()
            if comparable in seen:
                continue

            seen.add(comparable)
            sanitized.append(value)

        return sanitized

    def _get_filter_values(filters, key):
        if not filters:
            return []

        raw_value = filters.get(key)
        if raw_value is None:
            return []

        return _sanitize_filter_values(raw_value)

    def _sanitize_transaccion_filters(source):
        sanitized = {}
        if not source:
            return sanitized

        for key, config in TRANSACTION_FILTERS.items():
            raw_values = []
            if hasattr(source, "getlist"):
                raw_values = source.getlist(key)
                if not raw_values and key in source:
                    raw_values = [source.get(key)]
            else:
                raw_values = source.get(key)

            values = _sanitize_filter_values(raw_values)
            if not values:
                continue

            if config["kind"] == "range" or not config.get("multiple"):
                sanitized[key] = values[-1]
            else:
                sanitized[key] = values

        return sanitized

    def _sanitize_transaccion_search_terms(source):
        search_terms = {}
        if not source:
            return search_terms

        for key in TRANSACTION_OPTION_FIELDS:
            raw_value = source.get(f"search_{key}")
            if raw_value is None:
                continue
            value = str(raw_value).strip()
            if value:
                search_terms[key] = value

        return search_terms

    def _parse_filter_date(value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    def _build_string_match_expression(column, value, match_mode):
        if match_mode == "exact":
            return column == value
        if match_mode == "prefix":
            return column.like(f"{value}%")
        return column.like(f"%{value}%")

    def _apply_string_match(query, column, value, match_mode):
        return query.filter(_build_string_match_expression(column, value, match_mode))

    def _apply_transaccion_filters(query, filters, exclude_field=None):
        for key, value in (filters or {}).items():
            if key == exclude_field:
                continue

            config = TRANSACTION_FILTERS.get(key)
            if not config:
                continue

            if config["kind"] == "range":
                parsed_date = _parse_filter_date(value)
                if not parsed_date:
                    continue
                if config["op"] == "gte":
                    query = query.filter(config["column"] >= parsed_date)
                elif config["op"] == "lte":
                    query = query.filter(config["column"] <= parsed_date)
                continue

            values = _get_filter_values(filters, key)
            if not values:
                continue

            if len(values) == 1:
                query = _apply_string_match(query, config["column"], values[0], config["match"])
                continue

            query = query.filter(
                or_(
                    *[
                        _build_string_match_expression(config["column"], item, config["match"])
                        for item in values
                    ]
                )
            )

        return query

    def _build_filter_options(field_key, filters, search_term="", limit=None):
        config = TRANSACTION_FILTERS.get(field_key)
        if not config or config["kind"] == "range":
            return [], False

        option_limit = limit or (100 if config["kind"] == "facet" else 12)
        base_query = _apply_transaccion_filters(
            Transaccion.query,
            filters,
            exclude_field=field_key,
        )
        column = config["column"]

        grouped_query = base_query.filter(
            column.isnot(None),
            func.length(func.trim(column)) > 0,
        )

        normalized_search = (search_term or "").strip()
        if normalized_search:
            grouped_query = _apply_string_match(
                grouped_query,
                column,
                normalized_search,
                config.get("search_match", "contains"),
            )

        grouped_query = (
            grouped_query.with_entities(
                column.label("value"),
                func.count(Transaccion.id).label("count"),
            )
            .group_by(column)
            .order_by(func.count(Transaccion.id).desc(), column.asc())
        )

        rows = grouped_query.limit(option_limit + 1).all()
        items = [
            {
                "value": value,
                "label": value,
                "count": int(count or 0),
            }
            for value, count in rows[:option_limit]
            if value is not None and str(value).strip()
        ]

        current_values = _get_filter_values(filters, field_key)
        existing_values = {item["value"] for item in items}
        missing_selected = []

        for current_value in current_values:
            if current_value in existing_values:
                continue

            current_count = _apply_string_match(
                base_query.filter(
                    column.isnot(None),
                    func.length(func.trim(column)) > 0,
                ),
                column,
                current_value,
                config["match"],
            ).count()
            if current_count:
                missing_selected.append(
                    {
                        "value": current_value,
                        "label": current_value,
                        "count": int(current_count),
                    }
                )

        if missing_selected:
            items = missing_selected + items

        return items, len(rows) > option_limit

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if _is_authenticated():
            return redirect(url_for("index"))

        error = None
        next_url = _safe_next_url(request.values.get("next", ""))
        user_priority = {"luis": 0, "juan": 1}
        usuarios_activos = sorted(
            Usuario.query.filter(Usuario.activo.is_(True)).all(),
            key=lambda usuario: (
                user_priority.get((usuario.username or "").strip().lower(), 99),
                (usuario.nombre_completo or usuario.username or "").strip().lower(),
                (usuario.username or "").strip().lower(),
            ),
        )
        selected_username = ""
        selected_display = "usuario"

        if request.method == "POST":
            selected_username = request.form.get("username", "").strip().lower()
            for usuario_activo in usuarios_activos:
                current_username = (usuario_activo.username or "").strip().lower()
                if current_username == selected_username:
                    selected_display = usuario_activo.nombre_completo or usuario_activo.username
                    break

        if request.method == "POST":
            username = selected_username
            password = request.form.get("password", "")
            user = _get_active_user(username)

            if not usuarios_activos:
                error = "No hay usuarios activos configurados."
            elif not user or not user.password_hash or not check_password_hash(user.password_hash, password):
                error = "Usuario o contraseña incorrectos."
            else:
                session.clear()
                session.permanent = True
                session["auth_user"] = user.username
                return redirect(next_url or url_for("index"))

        return render_template(
            "login.html",
            error=error,
            next_url=next_url,
            usuarios_activos=usuarios_activos,
            selected_username=selected_username,
            selected_display=selected_display,
        )

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

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

    @app.route("/catalogo-fuentes")
    def catalogo_fuentes():
        return render_template("catalogo_fuentes.html")

    # ==================== API DE CARGA ====================

    @app.route("/api/process", methods=["POST"])
    def process():
        try:
            files = request.files.getlist("archivo")
            usuario = request.form.get("usuario", "sistema")
            tipo_archivo = request.form.get("tipo_archivo", "auxiliar").lower()
            allow_duplicates = request.form.get("allow_duplicates", "false").lower() in (
                "1",
                "true",
                "yes",
            )

            if tipo_archivo not in {"auxiliar", "macro"}:
                return jsonify({"error": "Tipo de archivo no válido"}), 400

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

            loaded = _get_loaded_archivos()
            duplicates = []
            files_to_process = []
            for f in valid_files:
                filename = Path(f.filename).name
                if filename in loaded:
                    duplicates.append(filename)
                else:
                    files_to_process.append(f)

            if duplicates and not files_to_process and not allow_duplicates:
                return jsonify({
                    "error": "Estos archivos ya fueron procesados anteriormente.",
                    "duplicate_files": duplicates,
                }), 409
            if allow_duplicates:
                files_to_process = valid_files

            job_id = str(uuid.uuid4())
            with jobs_lock:
                jobs[job_id] = {
                    "progress": 0,
                    "message": "Iniciando...",
                    "done": False,
                    "error": None,
                    "current_file": None,
                    "lote_id": None,
                    "total_registros": 0,
                }

            def progress_callback(pct, msg, current_file=None):
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]["progress"] = pct
                        jobs[job_id]["message"] = msg
                        if current_file is not None:
                            jobs[job_id]["current_file"] = current_file

            files_in_memory = []
            for f in files_to_process:
                f.seek(0)
                content = io.BytesIO(f.read())
                files_in_memory.append((f.filename, content))

            def process_files():
                try:
                    with app.app_context():
                        lote_id, total = process_files_to_database(
                            files_in_memory,
                            usuario,
                            progress_callback,
                            tipo_archivo=tipo_archivo,
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

            response_payload = {"job_id": job_id}
            if duplicates:
                response_payload["duplicate_files"] = duplicates
            return jsonify(response_payload)

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
                    "current_file": None,
                    "lote_id": None,
                    "total_registros": 0,
                }

            def progress_callback(pct, msg, current_file=None):
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]["progress"] = pct
                        jobs[job_id]["message"] = msg
                        if current_file is not None:
                            jobs[job_id]["current_file"] = current_file

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
                current_file = job.get("current_file")
                lote_id = job.get("lote_id")
                total_registros = job.get("total_registros", 0)

                if current_progress != last_progress or done or error:
                    data = {
                        "progress": current_progress,
                        "message": message,
                        "done": done,
                        "error": error,
                        "current_file": current_file,
                        "lote_id": lote_id,
                        "total_registros": total_registros,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                    last_progress = current_progress

                if done or error:
                    break

                time.sleep(0.2)

        return Response(generate(), mimetype="text/event-stream")

    @app.route("/api/archivos-procesados")
    def archivos_procesados():
        try:
            lotes = LoteCarga.query.order_by(LoteCarga.fecha_carga.desc()).all()
            archivos = []
            archivos_map = {}
            for lote in lotes:
                tipo_archivo = getattr(lote, "tipo_archivo", None)
                if not lote.archivos:
                    continue
                for archivo in lote.archivos:
                    if not archivo:
                        continue
                    nombre = Path(archivo).name
                    if nombre in archivos_map:
                        continue
                    payload = {
                        "archivo": nombre,
                        "tipo_archivo": tipo_archivo,
                        "fecha_carga": (
                            lote.fecha_carga.isoformat() if lote.fecha_carga else None
                        ),
                        "lote_id": lote.lote_id,
                    }
                    archivos_map[nombre] = payload
                    archivos.append(payload)

            loaded = _get_loaded_archivos()
            for example_file in _get_example_files():
                nombre = example_file.name
                if nombre not in loaded or nombre in archivos_map:
                    continue
                archivos.append({
                    "archivo": nombre,
                    "tipo_archivo": "auxiliar",
                    "fecha_carga": None,
                    "lote_id": None,
                })
            return jsonify({"archivos": archivos})
        except Exception as e:
            return (
                jsonify(
                    {
                        "error": "Error al obtener archivos procesados",
                        "detalle": str(e),
                    }
                ),
                500,
            )

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
            filtros = _sanitize_transaccion_filters(request.args)
            base_query = _apply_transaccion_filters(Transaccion.query, filtros)
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

    @app.route("/api/transacciones/filtros")
    def get_transacciones_filtros():
        try:
            filtros = _sanitize_transaccion_filters(request.args)
            search_terms = _sanitize_transaccion_search_terms(request.args)
            requested_fields = [
                field.strip()
                for field in request.args.get("fields", "").split(",")
                if field.strip() in TRANSACTION_OPTION_FIELDS
            ]

            if not requested_fields:
                requested_fields = list(TRANSACTION_OPTION_FIELDS)

            options = {}
            for field_key in requested_fields:
                items, truncated = _build_filter_options(
                    field_key,
                    filtros,
                    search_term=search_terms.get(field_key, ""),
                )
                options[field_key] = {
                    "kind": TRANSACTION_FILTERS[field_key]["kind"],
                    "items": items,
                    "truncated": truncated,
                }

            return jsonify({
                "filtros_aplicados": filtros,
                "options": options,
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
            filtros = _sanitize_transaccion_filters(request.json or {})
            query = _apply_transaccion_filters(Transaccion.query, filtros)

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
                dd=data.get('dd', ''),
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
            ente.dd = data.get('dd', ente.dd)

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

    # ==================== API CATÁLOGO DE FUENTES ====================

    @app.route("/api/fuentes")
    def get_fuentes():
        try:
            catalogo_path = Path(app.root_path) / "catalogos" / "Fuentes_de_Financiamientos.xlsx"
            if not catalogo_path.exists():
                return jsonify({"error": "No se encontró el archivo de catálogo"}), 404

            df = pd.read_excel(catalogo_path)
            df = df.rename(columns={
                "FF": "ff",
                "FUENTE DE FINANCIAMIENTO": "fuente",
                "ID": "id_fuente",
                "ALFA": "alfa",
                "DESCRIPCION": "descripcion",
                "RAMO FEDERAL": "ramo_federal",
                "FONDO DE INGRESO": "fondo_ingreso",
            })
            df = df[
                [
                    "ff",
                    "fuente",
                    "id_fuente",
                    "alfa",
                    "descripcion",
                    "ramo_federal",
                    "fondo_ingreso",
                ]
            ]
            df = df.astype(object).where(pd.notna(df), None)

            return jsonify({
                "fuentes": df.to_dict(orient="records"),
                "total": len(df),
            })
        except Exception as e:
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

    @app.errorhandler(405)
    def method_not_allowed(e):
        return (
            jsonify(
                {
                    "error": "Método no permitido",
                    "detalle": str(e.description)
                    if hasattr(e, "description")
                    else "Método no permitido",
                }
            ),
            405,
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
