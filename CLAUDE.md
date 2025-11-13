# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SIPAC (Sistema de Procesamiento de Auxiliares Contables) is a Flask-based web application for processing, analyzing, and reporting on accounting transactions from Excel files. The system parses complex accounting ledgers, breaks down 21-character accounting codes into components, and provides real-time data visualization and Excel report generation.

## Database Architecture

The application uses PostgreSQL with SQLAlchemy ORM. Database models in `models.py`:

- **Transaccion**: Core table storing accounting transactions with indexed fields for optimized queries
  - 21-character `cuenta_contable` is decomposed into 13 components (género, grupo, rubro, cuenta, subcuenta, dependencia, etc.)
  - Includes batch tracking via `lote_id`, transaction metadata, and financial amounts (saldo_inicial, cargos, abonos, saldo_final)
  - Composite indexes on `(cuenta_contable, fecha_transaccion)`, `(dependencia, fecha_transaccion)`, and `(lote_id, cuenta_contable)`

- **LoteCarga**: Tracks batch uploads with status, file lists, and record counts

- **Ente**: Catalog of public entities with unique clave/codigo identifiers

- **Usuario**: User management with roles (admin, auditor, consulta)

- **ReporteGenerado**: Tracks generated reports with filters and metadata

Database connection is configured via `DATABASE_URL` in `.env` (defaults to `postgresql://sipac_user:sipac_password@localhost:5432/sipac_db`).

## Data Processing Pipeline

The core processing logic is in `data_processor.py`:

1. **Excel Parsing** (`_read_one_excel`): Parses non-standard Excel files that use a custom format where:
   - "CUENTA CONTABLE:" headers identify account sections
   - "SALDO INICIAL CUENTA" rows provide starting balances
   - Transaction rows follow with dates, pólizas, beneficiarios, and monetary columns

2. **Account Code Decomposition** (`_split_cuenta_contable_vertical`): Breaks 21-char codes into positional components

3. **Balance Calculation**: Computes running balances (saldo_final) sequentially per account using: `saldo_actual = saldo_inicial + cargos - abonos`

4. **Bulk Insertion**: Inserts records in 1000-record chunks using `bulk_save_objects` for performance

5. **Progress Tracking**: Uses threading and job tracking for real-time upload feedback via Server-Sent Events

## Running the Application

### Development Mode

```bash
# Activate virtual environment
source venv/bin/activate

# Run development server (port 5020)
python app.py

# Or use the dev script
./scripts/dev.sh
```

The app runs on `http://localhost:5020` with the following pages:
- `/` - File upload interface
- `/reporte-online` - Interactive report generation
- `/catalogo-entes` - Entity catalog management

### Database Setup

```bash
# Setup PostgreSQL database
./scripts/setup_postgresql.sh

# The script creates user 'sipac_user' and database 'sipac_db'
```

### Environment Configuration

Create/edit `.env` file with:
```
DATABASE_URL=postgresql://sipac_user:sipac_password@localhost:5432/sipac_db
SECRET_KEY=<generated-key>
FLASK_ENV=development
```

## Key API Endpoints

### File Processing
- `POST /api/process` - Upload Excel files, returns `job_id` for tracking
- `GET /api/progress/<job_id>` - Server-Sent Events stream for upload progress

### Data Queries
- `GET /api/transacciones` - Paginated transactions with filters (cuenta_contable, dependencia, fecha_inicio, fecha_fin, poliza)
- `GET /api/dependencias/lista` - List distinct dependencias
- `GET /api/dashboard/stats` - Dashboard statistics (counts, sums, monthly aggregates)

### Reports
- `POST /api/reportes/generar` - Generate Excel report with filters (limited to 100,000 records)

### Entity Catalog
- `GET /api/entes` - List active entities
- `POST /api/entes` - Create entity
- `PUT /api/entes/<id>` - Update entity
- `DELETE /api/entes/<id>` - Soft delete entity

## Configuration & Settings

Config is in `config.py` with environment-specific classes:

- `MAX_CONTENT_LENGTH`: 500 MB max upload size
- `UPLOAD_EXTENSIONS`: `.xlsx, .xls` only
- `CHUNK_SIZE`: 1000 records per DB insertion batch
- `ITEMS_PER_PAGE`: 50 (default pagination)
- Database pooling and connection management via SQLAlchemy

## File Structure

- `app.py` - Flask app factory, routes, error handlers
- `models.py` - SQLAlchemy models
- `data_processor.py` - Excel parsing and batch processing logic
- `config.py` - Environment-based configuration
- `templates/` - Jinja2 HTML templates
- `scripts/` - Shell scripts for deployment, backup, database setup
  - `dev.sh` - Start development server
  - `setup_postgresql.sh` - Initialize database
  - `backup_sipac.sh` - Database backup utility
  - `cargar_entes.py` - Load entity catalog from data

## Important Implementation Notes

1. **Account Code Format**: The 21-character cuenta_contable must be parsed positionally (género at [0], grupo at [1], dependencia at [5:7], etc.). The format is critical for financial reporting.

2. **Excel Format Assumptions**: The parser expects a specific non-standard format with "CUENTA CONTABLE:" headers. If processing fails, check that input files match this format.

3. **Balance Calculation**: Saldo final is computed sequentially per account. Do not recalculate independently as it depends on transaction order.

4. **Batch Processing**: Use ThreadPoolExecutor (max 4 workers) for parallel Excel reading, but DB inserts are sequential to maintain data integrity.

5. **Progress Reporting**: The `/api/progress` endpoint uses SSE (Server-Sent Events) and requires jobs to be tracked in the in-memory `jobs` dictionary with thread-safe access via `jobs_lock`.

6. **Database Indexes**: Queries frequently filter by cuenta_contable, dependencia, and fecha_transaccion. Composite indexes are critical for performance at scale.
