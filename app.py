try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, render_template, request, jsonify, Response, send_file, session, redirect, url_for
from flask_cors import CORS
import io, os, sys, time, json, threading, uuid, logging, re
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from werkzeug.security import check_password_hash, generate_password_hash
from config import config
from scripts.utils import db, Transaccion, LoteCarga, Usuario, ReporteGenerado, Ente, CONTABLE_GENEROS
from scripts.utils import process_files_to_database
from sqlalchemy import func, and_, or_, inspect, text
from sqlalchemy.exc import IntegrityError
import pandas as pd

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from shared_user_catalog import get_project_role, list_users

def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    preferred_user_display = {
        user["usuario"]: user["nombre_completo"]
        for user in list_users(project_key="08-siif")
    }
    legacy_dependency_canonical_map = {
        "0G": "06",
    }
    canonical_dependency_aliases = {}
    for alias_code, canonical_code in legacy_dependency_canonical_map.items():
        canonical_dependency_aliases.setdefault(canonical_code, set()).update(
            {canonical_code, alias_code}
        )
    limited_catalog_selection_users = {"juan", "luis"}
    miguel_allowed_catalog_siglas = "OPD_SALUD"
    miguel_allowed_dependency = "06"

    def _normalize_catalog_sigla(value):
        return str(value or "").strip().upper()

    def _matches_opd_salud(siglas="", dependency_code=""):
        return _normalize_catalog_sigla(siglas) == miguel_allowed_catalog_siglas

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

    def _get_user_display_name(username=None, fallback=""):
        normalized = (username or "").strip().lower()
        if not normalized:
            return fallback or ""
        if normalized in preferred_user_display:
            return preferred_user_display[normalized]
        if fallback:
            return fallback
        user = _get_active_user(normalized)
        if user:
            return user.nombre_completo or user.username or normalized
        return normalized

    def _normalize_text(value):
        text_value = str(value or "").strip().lower()
        replacements = {
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ú": "u",
            "ü": "u",
            "ñ": "n",
        }
        for source, target in replacements.items():
            text_value = text_value.replace(source, target)
        return re.sub(r"\s+", " ", text_value)

    def _alphanumeric_sort_key(value):
        normalized = str(value or "").strip()
        if not normalized:
            return ((2, ""),)

        parts = re.split(r"(\d+)", normalized.casefold())
        return tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in parts
            if part != ""
        )

    def _normalize_dd(value):
        normalized = str(value or "").strip().upper().rstrip(".")
        if len(normalized) == 1 and normalized.isdigit():
            return normalized.zfill(2)
        return normalized

    def _canonicalize_dependency_code(value):
        normalized = _normalize_dd(value)
        return legacy_dependency_canonical_map.get(normalized, normalized)

    def _expand_dependency_codes(values):
        candidates = values if isinstance(values, (list, tuple, set)) else [values]
        expanded = []
        seen = set()

        for value in candidates:
            canonical = _canonicalize_dependency_code(value)
            if not canonical:
                continue

            aliases = canonical_dependency_aliases.get(canonical, {canonical})
            for code in sorted(aliases):
                normalized = _normalize_dd(code)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                expanded.append(normalized)

        return expanded

    def _ente_is_opd(ente):
        tipo = _normalize_text(getattr(ente, "tipo", ""))
        nombre = _normalize_text(getattr(ente, "nombre", ""))
        siglas = _normalize_text(getattr(ente, "siglas", ""))
        return (
            "opd" in nombre
            or "opd" in siglas
            or "descentralizado" in tipo
            or "paraestatal" in tipo
        )

    def _get_opd_dependencias():
        """Retorna el conjunto de códigos dd de los entes OPD (Organismo Público Descentralizado).
        Se identifican por clasificación descentralizada/paraestatal o por referencia explícita a OPD.
        """
        opd_entes = [
            ente
            for ente in Ente.query.filter(Ente.activo.is_(True)).all()
            if _ente_is_opd(ente)
        ]
        dependencias = set()
        for ente in opd_entes:
            dependencias.update(_expand_dependency_codes(ente.dd))
        return dependencias

    def _user_hides_municipios(username=None):
        current_username = (username or session.get("auth_user") or "").strip().lower()
        return current_username in {"luis", "juan"}

    def _get_catalog_group_siglas(group_key):
        catalogo_general = _load_catalogo_general()
        return {
            _normalize_catalog_sigla(item.get("siglas"))
            for item in catalogo_general.get(group_key, [])
            if _normalize_catalog_sigla(item.get("siglas"))
        }

    def _user_transaccion_base_query():
        """Retorna Transaccion.query pre-filtrado según los permisos del usuario en sesión.
        - luis y juan: solo entes estatales
        - miguel: solo OPD_SALUD
        """
        username = (session.get("auth_user") or "").strip().lower()
        if _user_hides_municipios(username):
            municipal_siglas = sorted(_get_catalog_group_siglas("municipios"))
            municipal_filters = [
                or_(
                    Transaccion.ente_grupo_catalogo.is_(None),
                    func.lower(Transaccion.ente_grupo_catalogo) != "municipios",
                )
            ]
            if municipal_siglas:
                municipal_filters.append(
                    func.upper(func.coalesce(Transaccion.ente_siglas_catalogo, "")).notin_(municipal_siglas)
                )
            return Transaccion.query.filter(
                and_(*municipal_filters)
            )
        if username == "miguel":
            return Transaccion.query.filter(
                func.upper(func.coalesce(Transaccion.ente_siglas_catalogo, "")) == miguel_allowed_catalog_siglas
            )
        return Transaccion.query

    def _build_balance_metrics(query):
        visible_totals = query.with_entities(
            func.count(Transaccion.id),
            func.coalesce(func.sum(Transaccion.cargos), 0),
            func.coalesce(func.sum(Transaccion.abonos), 0),
        ).first()

        total_registros = int(visible_totals[0] or 0)
        visible_total_cargos = float(visible_totals[1] or 0)
        visible_total_abonos = float(visible_totals[2] or 0)

        contable_query = query.filter(Transaccion.genero.in_(sorted(CONTABLE_GENEROS)))
        contable_totals = contable_query.with_entities(
            func.count(Transaccion.id),
            func.coalesce(func.sum(Transaccion.cargos), 0),
            func.coalesce(func.sum(Transaccion.abonos), 0),
        ).first()

        total_registros_contables = int(contable_totals[0] or 0)
        total_cargos = float(contable_totals[1] or 0)
        total_abonos = float(contable_totals[2] or 0)
        diferencia = total_cargos - total_abonos

        return {
            "total_registros": total_registros,
            "total_registros_contables": total_registros_contables,
            "registros_no_contables": max(total_registros - total_registros_contables, 0),
            "visible_total_cargos": visible_total_cargos,
            "visible_total_abonos": visible_total_abonos,
            "visible_total_diferencia": visible_total_cargos - visible_total_abonos,
            "total_cargos": total_cargos,
            "total_abonos": total_abonos,
            "diferencia": diferencia,
            "coincide": abs(diferencia) < 0.005,
        }

    def _build_visible_balance_payload(transaccion):
        genero = str(transaccion.genero or "").strip()
        if genero in CONTABLE_GENEROS:
            return {
                "saldo_inicial": float(transaccion.saldo_inicial) if transaccion.saldo_inicial else 0,
                "cargos": float(transaccion.cargos) if transaccion.cargos else 0,
                "abonos": float(transaccion.abonos) if transaccion.abonos else 0,
                "saldo_final": float(transaccion.saldo_final) if transaccion.saldo_final else 0,
            }
        return {
            "saldo_inicial": float(transaccion.abonos) if transaccion.abonos else 0,
            "cargos": float(transaccion.saldo_inicial) if transaccion.saldo_inicial else 0,
            "abonos": float(transaccion.cargos) if transaccion.cargos else 0,
            "saldo_final": float(transaccion.saldo_final) if transaccion.saldo_final else 0,
        }

    def _safe_next_url(raw_url):
        url = (raw_url or "").strip()
        if not url.startswith("/") or url.startswith("//"):
            return ""
        return url

    def _load_catalogo_general():
        try:
            catalog_path = Path(app.root_path) / "catalogos" / "catalogo_general.json"
            if catalog_path.exists():
                return json.loads(catalog_path.read_text(encoding='utf-8'))
        except Exception as exc:
            app.logger.error("[catalogo_general] No se pudo leer el catálogo general: %s", exc)
        return {"entes": [], "municipios": []}

    def _catalog_item_is_opd(item):
        ambito = _normalize_text(item.get("ambito"))
        clasificacion = _normalize_text(item.get("clasificacion"))
        nombre = _normalize_text(item.get("nombre"))
        siglas = _normalize_text(item.get("siglas"))
        if ambito == "municipal":
            return False
        return (
            "opd" in nombre
            or "opd" in siglas
            or "descentralizado" in clasificacion
            or "paraestatal" in clasificacion
        )

    def _user_has_restricted_catalog_selection(username=None):
        current_username = (username or session.get("auth_user") or "").strip().lower()
        return current_username in limited_catalog_selection_users or current_username == "miguel"

    def _catalog_item_is_visible_for_limited_selection(item):
        if str(item.get("grupo") or "").strip().lower() != "entes":
            return False

        num = str(item.get("num") or "").strip()
        siglas = _normalize_catalog_sigla(item.get("siglas"))
        if num == "1":
            return True

        branch_match = re.fullmatch(r"1\.(\d+)", num)
        if branch_match:
            return 1 <= int(branch_match.group(1)) <= 29

        return num == "22" and siglas == miguel_allowed_catalog_siglas

    def _catalogo_selection_policy(username=None):
        return {
            "scope": "catalogo_disponible",
            "title": "Catálogo disponible",
            "description": "Consulta y selección de claves para carga y revisión.",
        }

    def _build_ente_lookup():
        by_siglas = {}
        by_nombre = {}
        entes = Ente.query.filter(Ente.activo.is_(True)).all()
        for ente in entes:
            ambito = _normalize_text(ente.ambito)
            siglas = _normalize_text(ente.siglas)
            nombre = _normalize_text(ente.nombre)
            if siglas:
                by_siglas[(ambito, siglas)] = ente
            if nombre:
                by_nombre[(ambito, nombre)] = ente
        return by_siglas, by_nombre

    def _flatten_catalogo_general():
        catalogo_general = _load_catalogo_general()
        by_siglas, by_nombre = _build_ente_lookup()
        items = []
        ordered_groups = [
            ("entes", "ESTATAL", "Entes estatales"),
            ("municipios", "MUNICIPAL", "Municipios y paramunicipales"),
        ]

        order = 0
        for group_key, ambito, group_label in ordered_groups:
            for raw_item in catalogo_general.get(group_key, []):
                order += 1
                siglas = str(raw_item.get("siglas") or "").strip()
                nombre = str(raw_item.get("nombre") or "").strip()
                clasificacion = str(raw_item.get("clasificacion") or "").strip()
                num = str(raw_item.get("num") or "").strip()
                ambito_key = _normalize_text(ambito)
                resolved = None

                if siglas:
                    resolved = by_siglas.get((ambito_key, _normalize_text(siglas)))
                if resolved is None and nombre:
                    resolved = by_nombre.get((ambito_key, _normalize_text(nombre)))

                item = {
                    "id": f"{group_key}:{num}",
                    "num": num,
                    "nombre": nombre,
                    "siglas": siglas,
                    "clasificacion": clasificacion,
                    "ambito": ambito,
                    "grupo": group_key,
                    "grupo_label": group_label,
                    "orden": order,
                    "ente_clave": resolved.clave if resolved else "",
                    "dd": _normalize_dd(
                        resolved.dd if resolved and resolved.dd else ("0A" if ambito == "MUNICIPAL" else "")
                    ),
                }
                item["is_opd"] = _catalog_item_is_opd(item)
                prefix_parts = [part for part in (item["num"], item["siglas"]) if part]
                item["label"] = " · ".join(prefix_parts + [item["nombre"]]) if item["nombre"] else " · ".join(prefix_parts)
                items.append(item)

        return items

    def _filter_catalogo_general_items(username=None):
        current_username = (username or session.get("auth_user") or "").strip().lower()
        all_items = _flatten_catalogo_general()
        if _user_hides_municipios(current_username):
            return [item for item in all_items if item["grupo"] == "entes"]
        if current_username == "miguel":
            return [
                item
                for item in all_items
                if item["grupo"] == "entes"
                and _matches_opd_salud(item.get("siglas"), item.get("dd"))
            ]
        return all_items

    def _filter_catalogo_general_selection_items(username=None):
        current_username = (username or session.get("auth_user") or "").strip().lower()
        all_items = _flatten_catalogo_general()
        if current_username in limited_catalog_selection_users:
            return [
                item
                for item in all_items
                if _catalog_item_is_visible_for_limited_selection(item)
            ]
        if current_username == "miguel":
            return [
                item
                for item in all_items
                if item["grupo"] == "entes"
                and _matches_opd_salud(item.get("siglas"), item.get("dd"))
            ]
        return all_items

    def _build_catalog_index(items):
        indexed_items = {}

        for item in items:
            siglas = str(item.get("siglas") or "").strip()
            normalized_sigla = _normalize_catalog_sigla(siglas)
            if not normalized_sigla:
                continue

            current = indexed_items.get(normalized_sigla)
            payload = {
                "value": siglas,
                "label": item.get("label") or siglas,
                "orden": int(item.get("orden") or 0),
                "num": str(item.get("num") or "").strip(),
                "siglas": siglas,
                "nombre": str(item.get("nombre") or "").strip(),
                "grupo": item.get("grupo") or "",
                "grupo_label": item.get("grupo_label") or "",
                "search_blob": " ".join(
                    str(part or "").strip()
                    for part in (
                        item.get("num"),
                        item.get("siglas"),
                        item.get("nombre"),
                        item.get("clasificacion"),
                        item.get("grupo_label"),
                    )
                ),
            }
            if current is None or payload["orden"] < current["orden"]:
                indexed_items[normalized_sigla] = payload

        return sorted(indexed_items.values(), key=lambda item: (item["orden"], item["label"]))

    def _build_dependencia_catalog_index(username=None):
        return _build_catalog_index(_filter_catalogo_general_items(username=username))

    def _build_catalogo_general_selection_index(username=None):
        return _build_catalog_index(_filter_catalogo_general_selection_items(username=username))

    def _dependencia_catalog_matches_search(item, search_term):
        normalized_search = _normalize_text(search_term)
        if not normalized_search:
            return True

        haystack = " ".join(
            str(part or "").strip()
            for part in (
                item.get("value"),
                item.get("label"),
                item.get("siglas"),
                item.get("nombre"),
                item.get("grupo_label"),
                item.get("search_blob"),
            )
        )
        return normalized_search in _normalize_text(haystack)

    def _get_dependencia_catalog_lookup(username=None):
        lookup = {}
        for item in _build_dependencia_catalog_index(username=username):
            normalized_sigla = _normalize_catalog_sigla(item.get("value"))
            if normalized_sigla:
                lookup[normalized_sigla] = item["label"]
        return lookup

    def _build_ente_catalog_index(username=None):
        return _build_dependencia_catalog_index(username=username)

    def _ente_catalog_matches_search(item, search_term):
        return _dependencia_catalog_matches_search(item, search_term)

    def _get_ente_catalog_lookup(username=None):
        return _get_dependencia_catalog_lookup(username=username)

    def _filter_entes_by_permissions(entes, username=None):
        current_username = (username or session.get("auth_user") or "").strip().lower()
        if current_username == "juan":
            return [
                ente
                for ente in entes
                if _normalize_text(getattr(ente, "ambito", "")) != "municipal"
            ]
        if current_username == "miguel":
            return [
                ente
                for ente in entes
                if _matches_opd_salud(getattr(ente, "siglas", ""), getattr(ente, "dd", ""))
            ]
        return entes

    def _sanitize_ente_catalog_filter_values(values, username=None):
        if not _user_has_restricted_catalog_selection(username=username):
            return values

        allowed_siglas = {
            _normalize_catalog_sigla(item.get("value"))
            for item in _build_catalogo_general_selection_index(username=username)
            if _normalize_catalog_sigla(item.get("value"))
        }
        return [
            value
            for value in values
            if _normalize_catalog_sigla(value) in allowed_siglas
        ]

    def _get_catalogo_general_selection_payload(username=None):
        items = _filter_catalogo_general_selection_items(username=username)
        return {
            "opciones": items,
            "total": len(items),
            "stats": {
                "entes": sum(1 for item in items if item["grupo"] == "entes"),
                "municipios": sum(1 for item in items if item["grupo"] == "municipios"),
                "opd": sum(1 for item in items if item["is_opd"]),
            },
            "scope": _catalogo_selection_policy(username=username),
        }

    catalogos_consulta_definitions = {
        "poder_ejecutivo": {
            "id": "poder_ejecutivo",
            "nombre": "Poder Ejecutivo",
            "descripcion": "Entes de referencia del Poder Ejecutivo y sus dependencias.",
        },
        "opd_salud": {
            "id": "opd_salud",
            "nombre": "OPD Salud",
            "descripcion": "Consulta de referencia del Organismo Público Descentralizado Salud.",
        },
    }

    def _get_allowed_catalogos_consulta(username=None):
        current_username = (username or session.get("auth_user") or "").strip().lower()
        if current_username == "juan":
            allowed_ids = ("poder_ejecutivo",)
        elif current_username == "miguel":
            allowed_ids = ("opd_salud",)
        else:
            allowed_ids = ("poder_ejecutivo", "opd_salud")
        return [catalogos_consulta_definitions[catalog_id] for catalog_id in allowed_ids]

    def _load_fuentes_financiamiento_records():
        catalogo_path = Path(app.root_path) / "catalogos" / "Fuentes_de_Financiamientos.xlsx"
        if not catalogo_path.exists():
            return []

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
        columns = [
            "ff",
            "fuente",
            "id_fuente",
            "alfa",
            "descripcion",
            "ramo_federal",
            "fondo_ingreso",
        ]
        df = df[[column for column in columns if column in df.columns]]
        df = df.astype(object).where(pd.notna(df), None)
        return df.to_dict(orient="records")

    def _serialize_catalogo_consulta_ente(item):
        return {
            "numero_referencia": str(item.get("num") or "").strip(),
            "dd_referencia": str(item.get("dd") or "").strip(),
            "siglas": str(item.get("siglas") or "").strip(),
            "nombre": str(item.get("nombre") or "").strip(),
            "clasificacion": str(item.get("clasificacion") or "").strip(),
            "ambito": str(item.get("ambito") or "").strip(),
        }

    def _get_catalogo_consulta_detail(catalog_id):
        definition = catalogos_consulta_definitions.get(catalog_id)
        if not definition:
            return None

        catalog_items = [
            item for item in _flatten_catalogo_general()
            if item.get("grupo") == "entes"
        ]
        if catalog_id == "poder_ejecutivo":
            entes_referencia = [
                _serialize_catalogo_consulta_ente(item)
                for item in catalog_items
                if item.get("num") == "1"
                or re.fullmatch(r"1\.(?:[1-9]|1[0-6])", str(item.get("num") or ""))
            ]
        elif catalog_id == "opd_salud":
            entes_referencia = [
                _serialize_catalogo_consulta_ente(item)
                for item in catalog_items
                if item.get("num") == "22"
                and _normalize_catalog_sigla(item.get("siglas")) == miguel_allowed_catalog_siglas
            ]
        else:
            entes_referencia = []

        fuentes_referencia = _load_fuentes_financiamiento_records()
        return {
            "catalogo_consulta": {
                **definition,
                "entes_referencia": entes_referencia,
                "fuentes_financiamiento_referencia": fuentes_referencia,
                "totales": {
                    "entes_referencia": len(entes_referencia),
                    "fuentes_financiamiento_referencia": len(fuentes_referencia),
                },
            }
        }

    def _find_allowed_catalog_item(raw_value, username=None):
        candidate = str(raw_value or "").strip()
        if not candidate:
            return None
        for item in _filter_catalogo_general_selection_items(username=username):
            if candidate in {item["id"], item["ente_clave"], item["siglas"]}:
                return item
        return None

    @app.before_request
    def require_login():
        if request.method == "OPTIONS":
            return None
        if request.endpoint in {"login", "logout", "static", "health_check"}:
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

    @app.context_processor
    def inject_auth_context():
        auth_user = session.get("auth_user")
        return {
            "current_username": (auth_user or "").strip().lower(),
            "current_user_display": _get_user_display_name(auth_user),
        }

    # Configurar logging
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler('logs/app.log', maxBytes=10*1024*1024, backupCount=10)
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

            def _ensure_transacciones_catalog_columns():
                inspector = inspect(db.engine)
                if "transacciones" not in inspector.get_table_names():
                    return
                columns = {col["name"] for col in inspector.get_columns("transacciones")}
                pending_columns = [
                    ("ente_siglas_catalogo", "VARCHAR(80)"),
                    ("ente_nombre_catalogo", "VARCHAR(255)"),
                    ("ente_grupo_catalogo", "VARCHAR(20)"),
                ]
                for column_name, column_type in pending_columns:
                    if column_name in columns:
                        continue
                    db.session.execute(
                        text(f"ALTER TABLE transacciones ADD COLUMN {column_name} {column_type}")
                    )
                    db.session.commit()
                    columns.add(column_name)

            def _ensure_lotes_catalog_columns():
                inspector = inspect(db.engine)
                if "lotes_carga" not in inspector.get_table_names():
                    return
                columns = {col["name"] for col in inspector.get_columns("lotes_carga")}
                pending_columns = [
                    ("ente_siglas_catalogo", "VARCHAR(80)"),
                    ("ente_nombre_catalogo", "VARCHAR(255)"),
                    ("ente_grupo_catalogo", "VARCHAR(20)"),
                ]
                for column_name, column_type in pending_columns:
                    if column_name in columns:
                        continue
                    db.session.execute(
                        text(f"ALTER TABLE lotes_carga ADD COLUMN {column_name} {column_type}")
                    )
                    db.session.commit()
                    columns.add(column_name)

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

            def _sync_catalog_users():
                project_usernames = set()
                for catalog_user in list_users(project_key="08-siif"):
                    username = str(catalog_user.get("usuario") or "").strip().lower()
                    if not username:
                        continue

                    project_usernames.add(username)
                    user = (
                        Usuario.query
                        .filter(func.lower(Usuario.username) == username)
                        .first()
                    )
                    if user is None:
                        user = Usuario(username=username)

                    user.nombre_completo = (
                        str(catalog_user.get("nombre_completo") or username).strip()
                    )
                    user.password_hash = generate_password_hash(
                        str(catalog_user.get("clave") or "")
                    )
                    user.rol = get_project_role(catalog_user, "08-siif", "auditor") or "auditor"
                    user.activo = bool(catalog_user.get("activo", True))
                    db.session.add(user)

                # Deactivate users not in this project
                for extra_user in Usuario.query.all():
                    if (extra_user.username or "").strip().lower() not in project_usernames:
                        extra_user.activo = False
                        db.session.add(extra_user)

                db.session.commit()

            _ensure_entes_dd_column()
            _ensure_lotes_tipo_archivo_column()
            _ensure_transacciones_catalog_columns()
            _ensure_lotes_catalog_columns()
            _seed_entes_catalogo()
            _sync_catalog_users()
            _seed_entes_dd()
        except Exception as e:
            print(f"❌ Error al conectar con la base de datos: {str(e)}")
            print(f"   Verifica: DATABASE_URL en .env")
            raise

    # Jobs para tracking de progreso
    jobs = {}
    jobs_lock = threading.Lock()

    def _job_snapshot_dir():
        configured_dir = app.config.get("JOB_STATUS_DIR")
        base_dir = (
            Path(configured_dir)
            if configured_dir
            else Path(app.config.get("UPLOAD_FOLDER", "/tmp/sipac_uploads")) / "jobs"
        )
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _job_snapshot_path(job_id):
        safe_job_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(job_id or ""))
        return _job_snapshot_dir() / f"{safe_job_id or 'unknown'}.json"

    def _serialize_job(job):
        if not job:
            return None
        return {
            "progress": job.get("progress", 0),
            "message": job.get("message", ""),
            "done": job.get("done", False),
            "error": job.get("error", None),
            "current_file": job.get("current_file"),
            "lote_id": job.get("lote_id"),
            "total_registros": job.get("total_registros", 0),
        }

    def _write_job_snapshot(job_id, job):
        payload = _serialize_job(job)
        if payload is None:
            return

        payload["updated_at"] = time.time()
        target = _job_snapshot_path(job_id)
        temp_name = f".{target.name}.{uuid.uuid4().hex}.tmp"
        temp_path = target.with_name(temp_name)

        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(temp_path, target)
        except Exception as exc:
            app.logger.warning(
                "[jobs] No se pudo persistir el estado de %s: %s", job_id, exc
            )
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

    def _read_job_snapshot(job_id):
        target = _job_snapshot_path(job_id)
        if not target.exists():
            return None

        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            app.logger.warning(
                "[jobs] No se pudo leer el estado persistido de %s: %s", job_id, exc
            )
            return None

        return _serialize_job(payload)

    def _register_job(job_id, payload):
        snapshot = dict(payload)
        with jobs_lock:
            jobs[job_id] = snapshot
        _write_job_snapshot(job_id, snapshot)
        return snapshot

    def _update_job(job_id, **changes):
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                return None
            job.update(changes)
            snapshot = dict(job)
        _write_job_snapshot(job_id, snapshot)
        return snapshot

    def _get_job_snapshot(job_id):
        with jobs_lock:
            job = jobs.get(job_id)
            snapshot = dict(job) if job is not None else None

        if snapshot is not None:
            return _serialize_job(snapshot)
        return _read_job_snapshot(job_id)

    stats_cache = {
        "resumen": {"ts": 0, "data": None},
        "dashboard": {"ts": 0, "data": None},
    }
    stats_cache_lock = threading.Lock()

    def _invalidate_stats_cache():
        with stats_cache_lock:
            for key in list(stats_cache.keys()):
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
        "ente_catalogo": {
            "column": Transaccion.ente_siglas_catalogo,
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
            if key == "ente_catalogo":
                values = _sanitize_ente_catalog_filter_values(values)
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

            if key == "ente_catalogo":
                selected_siglas = []
                seen_siglas = set()
                for item in values:
                    normalized_sigla = _normalize_catalog_sigla(item)
                    if not normalized_sigla or normalized_sigla in seen_siglas:
                        continue
                    seen_siglas.add(normalized_sigla)
                    selected_siglas.append(normalized_sigla)

                if not selected_siglas:
                    continue

                column_expr = func.upper(func.coalesce(Transaccion.ente_siglas_catalogo, ""))
                if len(selected_siglas) == 1:
                    query = query.filter(column_expr == selected_siglas[0])
                else:
                    query = query.filter(column_expr.in_(selected_siglas))
                continue

            if key == "dependencia":
                selected_codes = []
                seen_codes = set()
                for item in values:
                    normalized_code = _normalize_dd(item)
                    if not normalized_code or normalized_code in seen_codes:
                        continue
                    seen_codes.add(normalized_code)
                    selected_codes.append(normalized_code)

                if not selected_codes:
                    continue

                column_expr = func.upper(func.coalesce(Transaccion.dependencia, ""))
                if len(selected_codes) == 1:
                    query = query.filter(column_expr == selected_codes[0])
                else:
                    query = query.filter(column_expr.in_(selected_codes))
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

    def _build_filter_options(field_key, filters, search_term="", limit=None, base_query=None):
        config = TRANSACTION_FILTERS.get(field_key)
        if not config or config["kind"] == "range":
            return [], False

        option_limit = limit or (250 if field_key == "ente_catalogo" else (100 if config["kind"] == "facet" else 12))
        base_query = _apply_transaccion_filters(
            base_query if base_query is not None else _user_transaccion_base_query(),
            filters,
            exclude_field=field_key,
        )
        column = config["column"]

        if field_key == "ente_catalogo":
            grouped_rows = (
                base_query.filter(
                    column.isnot(None),
                    func.length(func.trim(column)) > 0,
                )
                .with_entities(
                    column.label("value"),
                    func.count(Transaccion.id).label("count"),
                )
                .group_by(column)
                .all()
            )

            counts_by_value = {
                _normalize_catalog_sigla(value): int(count or 0)
                for value, count in grouped_rows
                if value is not None and str(value).strip()
            }
            selected_values = []
            seen_selected = set()
            for current_value in _get_filter_values(filters, field_key):
                normalized_value = _normalize_catalog_sigla(current_value)
                if not normalized_value or normalized_value in seen_selected:
                    continue
                seen_selected.add(normalized_value)
                selected_values.append(normalized_value)
            catalog_index = _build_catalogo_general_selection_index()
            catalog_codes = {_normalize_catalog_sigla(item["value"]) for item in catalog_index}
            restrict_extras = _user_has_restricted_catalog_selection()

            items = []
            for item in catalog_index:
                normalized_item_value = _normalize_catalog_sigla(item["value"])
                count = counts_by_value.get(normalized_item_value, 0)
                if not _ente_catalog_matches_search(item, search_term):
                    continue
                items.append(
                    {
                        "value": item["value"],
                        "label": item["label"],
                        "count": count,
                        "orden": item["orden"],
                        "nombre": item.get("nombre") or "",
                        "siglas": item.get("siglas") or item["value"],
                        "grupo_label": item.get("grupo_label") or "",
                        "ambito": "MUNICIPAL" if (item.get("grupo") or "") == "municipios" else "ESTATAL",
                    }
                )

            extras = []
            normalized_search = _normalize_text(search_term)
            for value, count in counts_by_value.items():
                if value in catalog_codes:
                    continue
                if restrict_extras:
                    continue
                label = value
                if normalized_search and normalized_search not in _normalize_text(label):
                    continue
                extras.append(
                    {
                        "value": value,
                        "label": label,
                        "count": count,
                        "orden": 999999,
                    }
                )

            items.extend(sorted(extras, key=lambda item: _alphanumeric_sort_key(item["label"])))
            items.sort(
                key=lambda item: (
                    0 if str(item.get("ambito") or "").strip().upper() == "ESTATAL"
                    else 1 if str(item.get("ambito") or "").strip().upper() == "MUNICIPAL"
                    else 2,
                    int(item.get("orden") or 999999),
                    _alphanumeric_sort_key(item["label"]),
                )
            )
            truncated = len(items) > option_limit
            visible_items = items[:option_limit]
            existing_values = {item["value"] for item in visible_items}
            missing_selected = []

            for current_value in selected_values:
                if current_value in existing_values:
                    continue

                current_count = counts_by_value.get(current_value, 0)

                catalog_item = next(
                    (
                        item
                        for item in catalog_index
                        if _normalize_catalog_sigla(item["value"]) == current_value
                    ),
                    None,
                )
                missing_selected.append(
                    {
                        "value": catalog_item["value"] if catalog_item else current_value,
                        "label": catalog_item["label"] if catalog_item else current_value,
                        "count": int(current_count or 0),
                        "nombre": catalog_item.get("nombre") if catalog_item else "",
                        "siglas": catalog_item.get("siglas") if catalog_item else current_value,
                        "grupo_label": catalog_item.get("grupo_label") if catalog_item else "",
                        "ambito": (
                            "MUNICIPAL"
                            if catalog_item and (catalog_item.get("grupo") or "") == "municipios"
                            else "ESTATAL"
                        ),
                    }
                )

            if missing_selected:
                visible_items = missing_selected + visible_items

            return [
                {
                    "value": item["value"],
                    "label": item["label"],
                    "count": int(item["count"] or 0),
                    "nombre": item.get("nombre") or "",
                    "siglas": item.get("siglas") or item["value"],
                    "grupo_label": item.get("grupo_label") or "",
                    "ambito": item.get("ambito") or "",
                    "orden": int(item.get("orden") or 999999),
                }
                for item in visible_items
            ], truncated

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

        rows = (
            grouped_query.with_entities(
                column.label("value"),
                func.count(Transaccion.id).label("count"),
            )
            .group_by(column)
            .all()
        )
        rows = sorted(
            [
                (value, count)
                for value, count in rows
                if value is not None and str(value).strip()
            ],
            key=lambda item: _alphanumeric_sort_key(item[0]),
        )
        items = [
            {
                "value": value,
                "label": value,
                "count": int(count or 0),
            }
            for value, count in rows[:option_limit]
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

    @app.route("/api/health")
    @app.route("/health")
    def health_check():
        return jsonify({"status": "ok", "service": "siif"}), 200

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if _is_authenticated():
            return redirect(url_for("index"))

        error = None
        next_url = _safe_next_url(request.values.get("next", ""))
        user_priority = {"luis": 0, "gabo": 1, "juan": 2, "miguel": 3}
        usuarios_activos = sorted(
            Usuario.query.filter(Usuario.activo.is_(True)).all(),
            key=lambda usuario: (
                user_priority.get((usuario.username or "").strip().lower(), 99),
                _get_user_display_name(
                    usuario.username,
                    usuario.nombre_completo or usuario.username or "",
                ).strip().lower(),
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
                    selected_display = _get_user_display_name(
                        current_username,
                        usuario_activo.nombre_completo or usuario_activo.username or "",
                    )
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
            preferred_user_display=preferred_user_display,
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
        return render_template(
            "index.html",
            catalogo_scope=_catalogo_selection_policy(),
        )

    @app.route("/reporte-online")
    def reporte_online():
        return render_template("reporte_online.html")

    @app.route("/reporte-resumen")
    def reporte_resumen():
        return redirect(url_for("reporte_online") + "#resumen-general")

    @app.route("/catalogo")
    def catalogo():
        return render_template(
            "catalogo.html",
            catalogo_scope=_catalogo_selection_policy(),
        )

    @app.route("/catalogo-entes")
    def catalogo_entes():
        return render_template("catalogo_entes.html")

    @app.route("/catalogo-fuentes")
    def catalogo_fuentes():
        return render_template("catalogo_fuentes.html")

    @app.route("/api/catalogo-general")
    def get_catalogo_general():
        try:
            return jsonify(_get_catalogo_general_selection_payload())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/catalogos-consulta")
    def get_catalogos_consulta():
        try:
            catalogos_disponibles = _get_allowed_catalogos_consulta()
            return jsonify({
                "catalogo_consulta_inicial": (
                    catalogos_disponibles[0]["id"] if catalogos_disponibles else ""
                ),
                "catalogos_consulta_disponibles": catalogos_disponibles,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/catalogos-consulta/<catalog_id>")
    def get_catalogos_consulta_detail(catalog_id):
        try:
            if catalog_id not in catalogos_consulta_definitions:
                return jsonify({"error": "Catálogo de consulta no encontrado"}), 404
            allowed_ids = {
                catalogo["id"]
                for catalogo in _get_allowed_catalogos_consulta()
            }
            if catalog_id not in allowed_ids:
                return jsonify({"error": "Catálogo de consulta no autorizado"}), 403
            return jsonify(_get_catalogo_consulta_detail(catalog_id))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==================== API DE CARGA ====================

    @app.route("/api/process", methods=["POST"])
    def process():
        try:
            files = request.files.getlist("archivo")
            usuario = request.form.get("usuario") or session.get("auth_user") or "sistema"
            tipo_archivo = request.form.get("tipo_archivo", "auxiliar").lower()
            catalog_item_id = request.form.get("catalogo_item_id") or request.form.get("ente_clave")
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

            selected_catalog_item = _find_allowed_catalog_item(catalog_item_id)
            if not selected_catalog_item:
                return jsonify({
                    "error": "Selecciona un ente o municipio autorizado del Catálogo General antes de procesar."
                }), 400

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
            _register_job(
                job_id,
                {
                    "progress": 0,
                    "message": "Iniciando...",
                    "done": False,
                    "error": None,
                    "current_file": None,
                    "lote_id": None,
                    "total_registros": 0,
                },
            )

            def progress_callback(pct, msg, current_file=None):
                payload = {
                    "progress": pct,
                    "message": msg,
                }
                if current_file is not None:
                    payload["current_file"] = current_file
                _update_job(job_id, **payload)

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
                            selected_ente=selected_catalog_item.get("label") or selected_catalog_item.get("nombre"),
                            selected_ente_siglas=selected_catalog_item.get("siglas"),
                            selected_ente_nombre=selected_catalog_item.get("nombre"),
                            selected_ente_grupo=selected_catalog_item.get("grupo"),
                        )

                        _update_job(
                            job_id,
                            lote_id=lote_id,
                            total_registros=total,
                            done=True,
                            progress=100,
                            message=f"✅ {total:,} registros guardados en BD",
                        )
                        _invalidate_stats_cache()

                except Exception as e:
                    _update_job(job_id, error=str(e), done=True)

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
            _register_job(
                job_id,
                {
                    "progress": 0,
                    "message": "Iniciando...",
                    "done": False,
                    "error": None,
                    "current_file": None,
                    "lote_id": None,
                    "total_registros": 0,
                },
            )

            def progress_callback(pct, msg, current_file=None):
                payload = {
                    "progress": pct,
                    "message": msg,
                }
                if current_file is not None:
                    payload["current_file"] = current_file
                _update_job(job_id, **payload)

            def process_files():
                try:
                    with app.app_context():
                        lote_id, total = process_files_to_database(
                            files_in_memory, usuario, progress_callback
                        )

                        _update_job(
                            job_id,
                            lote_id=lote_id,
                            total_registros=total,
                            done=True,
                            progress=100,
                            message=f"✅ {total:,} registros guardados en BD",
                        )

                except Exception as e:
                    _update_job(job_id, error=str(e), done=True)

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
        if request.args.get("format") == "json":
            payload = _get_job_snapshot(job_id)
            if payload is None:
                return jsonify({"error": "Trabajo no encontrado"}), 404
            return jsonify(payload)

        def generate():
            last_progress = -1
            max_wait = 300
            start_time = time.time()

            while True:
                if time.time() - start_time > max_wait:
                    yield f"data: {json.dumps({'progress': 100, 'message': 'Timeout', 'done': True})}\n\n"
                    break

                job = _get_job_snapshot(job_id)

                if not job:
                    time.sleep(0.1)
                    continue

                current_progress = job["progress"]
                message = job["message"]
                done = job["done"]
                error = job["error"]
                current_file = job["current_file"]
                lote_id = job["lote_id"]
                total_registros = job["total_registros"]

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
            current_username = (session.get("auth_user") or "").strip().lower()
            selected_siglas = _normalize_catalog_sigla(request.args.get("siglas"))
            selected_group = _normalize_text(request.args.get("grupo"))

            lotes_query = LoteCarga.query.order_by(LoteCarga.fecha_carga.desc())
            if current_username:
                lotes_query = lotes_query.filter(
                    func.lower(func.coalesce(LoteCarga.usuario, "")) == current_username
                )
            if selected_siglas:
                lotes_query = lotes_query.filter(
                    func.upper(func.coalesce(LoteCarga.ente_siglas_catalogo, "")) == selected_siglas
                )
            if selected_group:
                lotes_query = lotes_query.filter(
                    func.lower(func.coalesce(LoteCarga.ente_grupo_catalogo, "")) == selected_group
                )

            lotes = lotes_query.all()
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
                        "ente_siglas_catalogo": getattr(lote, "ente_siglas_catalogo", None),
                    }
                    archivos_map[nombre] = payload
                    archivos.append(payload)
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
            base_query = _apply_transaccion_filters(_user_transaccion_base_query(), filtros)
            query = base_query.order_by(Transaccion.fecha_transaccion.desc())
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)
            ente_catalogo_lookup = _get_ente_catalog_lookup()

            response_payload = {
                "transacciones": [
                    {
                        **t.to_dict(),
                        **_build_visible_balance_payload(t),
                        "ente": ente_catalogo_lookup.get(
                            _normalize_catalog_sigla(t.ente_siglas_catalogo),
                            t.ente_siglas_catalogo or "",
                        ),
                        "ente_catalogo": ente_catalogo_lookup.get(
                            _normalize_catalog_sigla(t.ente_siglas_catalogo),
                            t.ente_siglas_catalogo or "",
                        ),
                    }
                    for t in paginated.items
                ],
                "total": paginated.total,
                "pages": paginated.pages,
                "page": page,
            }

            if include_totals:
                response_payload.update(_build_balance_metrics(base_query))

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
            deps = _user_transaccion_base_query().with_entities(
                Transaccion.dependencia,
                func.count(Transaccion.id).label("total"),
            ).filter(
                Transaccion.dependencia.isnot(None)
            ).group_by(Transaccion.dependencia).order_by(Transaccion.dependencia).all()
            return jsonify({"dependencias": [{"nombre": d[0], "total": d[1]} for d in deps if d[0]]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/transacciones/resumen")
    def get_transacciones_resumen():
        try:
            username = (session.get("auth_user") or "").strip().lower()
            filtros = _sanitize_transaccion_filters(request.args)
            user_query = _apply_transaccion_filters(_user_transaccion_base_query(), filtros)

            def compute_resumen():
                return _build_balance_metrics(user_query)

            filtros_cache_key = json.dumps(filtros, sort_keys=True, ensure_ascii=False)
            payload = _get_cached_stats(
                f"resumen_{username}_{filtros_cache_key}",
                30,
                compute_resumen,
            )
            return jsonify(payload)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/reportes/generar", methods=["POST"])
    def generar_reporte():
        try:
            filtros = _sanitize_transaccion_filters(request.json or {})
            query = _apply_transaccion_filters(_user_transaccion_base_query(), filtros)

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
                **{
                    'SALDO INICIAL': _build_visible_balance_payload(t)["saldo_inicial"],
                    'CARGOS': _build_visible_balance_payload(t)["cargos"],
                    'ABONOS': _build_visible_balance_payload(t)["abonos"],
                    'SALDO FINAL': _build_visible_balance_payload(t)["saldo_final"],
                },
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
            username = (session.get("auth_user") or "").strip().lower()
            user_query = _user_transaccion_base_query()

            def compute_dashboard():
                stats = user_query.with_entities(
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
                    user_query.with_entities(
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

            payload = _get_cached_stats(f"dashboard_{username}", 30, compute_dashboard)
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
            catalog_order = {
                item.get("num"): int(item.get("orden") or 999999)
                for item in _flatten_catalogo_general()
                if item.get("num")
            }
            entes = Ente.query.filter_by(activo=True).order_by(Ente.clave).all()
            entes = _filter_entes_by_permissions(entes)
            entes.sort(
                key=lambda ente: (
                    0 if str(ente.ambito or "").strip().upper() == "ESTATAL" else 1,
                    catalog_order.get(str(ente.codigo or "").strip(), 999999),
                    str(ente.codigo or "").strip(),
                    str(ente.nombre or "").strip(),
                )
            )
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
