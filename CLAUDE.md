# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SIPAC (Sistema de Procesamiento de Auxiliares Contables) is a Flask-based web application for processing and analyzing accounting transactions from Excel files. The system stores data in PostgreSQL and provides an interactive dashboard and reporting capabilities.

**Key Purpose:** Transform Excel-based accounting auxiliary files into a queryable database with visualization and reporting capabilities for auditors.

## Architecture

**3-Layer Architecture:**
- **Frontend:** HTML templates with vanilla JavaScript and Chart.js for visualization
- **Backend:** Flask REST API with SQLAlchemy ORM
- **Database:** PostgreSQL with optimized indexes for accounting queries

**Key Design Decisions:**
- Uses SQLAlchemy bulk operations for performance (1000 records per batch)
- Thread-based parallel processing for multiple Excel files
- Server-Sent Events (SSE) for real-time upload progress
- Composite indexes on frequently queried columns (cuenta_contable + fecha_transaccion, dependencia + fecha_transaccion)

## Common Development Commands

### Running the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Run development server (port 4095)
python app_mejorado.py
```

### Database Operations

```bash
# Create/recreate database tables
python -c "from app_mejorado import create_app; from models import db; app = create_app(); app.app_context().push(); db.create_all()"

# Migrate existing Excel files to database
python migrar_datos.py migrar /path/to/excel/files

# Verify database contents
python migrar_datos.py verificar

# Database backup
pg_dump -U sipac_user -d sipac_db -F c -f backup_sipac_$(date +%Y%m%d).backup

# Database restore
pg_restore -U sipac_user -d sipac_db -v backup_file.backup
```

### Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# Key dependencies:
# - Flask 3.0.0 + Flask-SQLAlchemy + Flask-CORS
# - psycopg2-binary (PostgreSQL driver)
# - pandas + openpyxl (Excel processing)
# - XlsxWriter (report generation)
```

## Code Structure

### Core Application Files

**app_mejorado.py** - Main Flask application
- Creates Flask app with `create_app(config_name)` factory pattern
- Defines all API endpoints and routes
- Manages job tracking for async file processing
- Implements SSE for progress updates

**models.py** - SQLAlchemy database models
- `Transaccion`: Main table with 24 columns including parsed account components
- `LoteCarga`: Tracks batch uploads with UUIDs
- `Usuario`: User management (future functionality)
- `ReporteGenerado`: Report generation history
- Important: Uses composite indexes for common queries

**data_processor.py** - Excel file processing logic
- `process_files_to_database()`: Main entry point for processing files
- Parallel file reading with ThreadPoolExecutor
- Bulk insertion using SQLAlchemy `bulk_save_objects()`
- Calculates cumulative balances per account (`saldo_inicial`, `saldo_final`)
- Parses 21-character accounting codes into 13 components

**config.py** - Configuration management
- `DevelopmentConfig` and `ProductionConfig` classes
- Database connection strings from environment variables
- Important settings: `CHUNK_SIZE=1000`, `MAX_CONTENT_LENGTH=500MB`

### Database Schema

**Transaccion Table Structure:**
- Accounting code components: genero, grupo, rubro, cuenta, subcuenta (positions 1-5 of 21-char code)
- Budget components: dependencia, unidad_responsable, centro_costo, proyecto_presupuestario, fuente, subfuente, tipo_recurso, partida_presupuestal (positions 6-21)
- Financial data: saldo_inicial, cargos, abonos, saldo_final (all Numeric(15,2))
- Metadata: lote_id (UUID), archivo_origen, fecha_carga

**Critical Indexes:**
- `idx_cuenta_fecha`: (cuenta_contable, fecha_transaccion) - Most common query pattern
- `idx_dependencia_fecha`: (dependencia, fecha_transaccion) - Department-based queries
- `idx_lote_cuenta`: (lote_id, cuenta_contable) - Batch tracking

## Working with the Codebase

### Adding New Filters to Dashboard

1. Update API endpoint in `app_mejorado.py` around line 140-180 (search for `@app.route("/api/transacciones")`)
2. Add filter logic to the query builder using SQLAlchemy `and_()` or `or_()`
3. Update `dashboard.html` to add UI elements for the new filter
4. Ensure new filter column has an index in `models.py` if it will be frequently queried

### Processing Excel Files

The system expects Excel files with this structure:
- Column headers normalized to lowercase without accents
- Required columns: cuenta_contable, fecha, saldo_inicial, cargos, abonos
- Optional: poliza, beneficiario, descripcion, orden_pago
- Multiple sheets supported (iterates through all sheets)

**Account Code Format:** 21 characters representing hierarchical accounting structure
- Example: `11101010101110101111` breaks down into 13 components
- Parsing logic in `_split_cuenta_contable_vertical()` in data_processor.py

### Generating Reports

Reports use `XlsxWriter` for Excel generation with formatting:
- Located in `app_mejorado.py` around line 220-280 (search for `/api/reportes/generar`)
- Applies filters similar to dashboard queries
- Limits: 100,000 records per report (configurable)
- Auto-formatting: currency, dates, bold headers

## Environment Configuration

Required `.env` file in project root:

```env
DATABASE_URL=postgresql://sipac_user:sipac_password@localhost:5432/sipac_db
SECRET_KEY=your-secret-key-here
FLASK_ENV=development  # or production
```

**Production Changes:**
- Set `FLASK_ENV=production`
- Use strong random `SECRET_KEY`
- Update database credentials
- Configure systemd service for auto-start

## Known Limitations and Considerations

1. **Memory Usage:** Processing large Excel files (>100MB) can consume significant memory
   - Adjust `CHUNK_SIZE` in config.py if needed
   - Monitor with `htop` during large uploads

2. **Cumulative Balance Calculation:** Assumes transactions are ordered by date within each account
   - Critical for correct `saldo_final` calculation
   - See `_calcular_saldos_acumulativos()` in data_processor.py

3. **No Authentication:** Current version has no login system
   - Users table exists but not actively used
   - Plan for future: Flask-Login integration

4. **Port 4095:** Hardcoded in app_mejorado.py
   - Change in `app.run(host='0.0.0.0', port=4095)` if needed

5. **Template Location:** HTML files in project root (not in `templates/` subdirectory)
   - Adjust if reorganizing: update `render_template()` calls

## Debugging Tips

**Database Connection Issues:**
```bash
# Test PostgreSQL is running
sudo systemctl status postgresql

# Test connection manually
psql -U sipac_user -d sipac_db -h localhost
```

**Empty Results in Dashboard:**
- Check if data was actually loaded: query `transacciones` table directly
- Verify date filters are not excluding all data
- Check browser console for JavaScript errors

**Slow Queries:**
```sql
-- Check missing indexes
EXPLAIN ANALYZE SELECT * FROM transacciones WHERE cuenta_contable = '11101' AND fecha_transaccion BETWEEN '2024-01-01' AND '2024-12-31';

-- Verify indexes exist
\d+ transacciones
```

**Excel Processing Errors:**
- Common issue: column name mismatch (check normalization in `_norm()`)
- Verify Excel file structure matches expected format
- Check logs for specific error messages during upload

## Testing

Currently no automated tests. Manual testing workflow:

1. Start application: `python app_mejorado.py`
2. Upload small test Excel file (2-3 rows)
3. Verify data appears in dashboard
4. Test filters individually
5. Generate test report with filters
6. Compare downloaded Excel with expected data

Future: Add pytest tests for data_processor.py functions and API endpoints.

## Deployment Notes

**Systemd Service Configuration:**
- Service file template in PLAN_IMPLEMENTACION.md
- Runs as dedicated user with virtual environment
- Auto-restart on failure
- Depends on postgresql.service

**Backup Strategy:**
- Daily pg_dump via cron at 2 AM
- Retention: 30 days
- Script: `setup_postgresql.sh` includes backup commands

**Performance Tuning:**
- PostgreSQL settings in PLAN_IMPLEMENTACION.md
- Recommended: 4GB RAM, SSD storage
- Monitor disk usage as transaction volume grows
