# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SIIF (Sistema Integral de Información Financiera) is a Flask web application for uploading, validating, and reviewing official financial data (auxiliares contables) from Mexican government entities. Users upload Excel files containing accounting transactions, which are parsed and stored in a database for reporting and analysis.

Live at: https://siif.omar-xyz.shop

## Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run development server (port 5009)
python app.py

# Run all tests
python -m pytest tests/

# Run a single test
python -m pytest tests/test_import_balance.py -v

# Analyze OPD Excel files (utility script)
python analyze_opd.py [batch_number]
```

## Architecture

**Single-file Flask app** (`app.py`) using the factory pattern (`create_app()`). All routes, helpers, and business logic live in this file (~2300 lines). No blueprints.

### Key files

- `app.py` — Application factory, all routes, view logic, filtering/search helpers, job tracking for async file processing
- `scripts/utils.py` — SQLAlchemy models, Excel parsing logic (`_read_one_excel`, `_read_one_excel_macro`), `process_files_to_database()` pipeline
- `config.py` — Flask config classes (Development/Production), selects via `FLASK_ENV`
- `catalogos/catalogo_general.json` — Master catalog of government entities (entes), loaded at startup
- `catalogos/*.xlsx` — Source catalog spreadsheets (Estatales, Municipales, Fuentes de Financiamientos)

### Database models (in `scripts/utils.py`)

- `Transaccion` — Accounting transactions with decomposed cuenta contable (genero/grupo/rubro/cuenta/subcuenta/dependencia/etc.)
- `LoteCarga` — Upload batch tracking (estado: procesando/completado/error)
- `Usuario` — User accounts with password hashes
- `ReporteGenerado` — Generated report records
- `Ente` — Government entity registry

### Data flow

1. User uploads `.xlsx` files via the web UI
2. `app.py` creates a background processing job (tracked via JSON snapshots in `/tmp`)
3. `process_files_to_database()` in `scripts/utils.py` parses Excel files, extracts transactions, and bulk-inserts into SQLite/PostgreSQL
4. Progress is streamed to the frontend via SSE (`/api/progress/<job_id>`)

### Frontend

Server-rendered Jinja2 templates (`templates/`) with vanilla JavaScript (`static/js/main.js`). No frontend build step. CSS in `static/css/`.

### User access control

Role-based visibility is hardcoded in `app.py`: certain users (juan, luis, miguel) have restricted catalog/entity access. The `_user_transaccion_base_query()` function applies per-user filters to all transaction queries.

### Database

SQLite in development (`instance/sipac_dev.db`), PostgreSQL in production. Configured via `DATABASE_URL` env var.
