# Repository Guidelines

## Project Structure & Module Organization
`app.py` is the main Flask entrypoint and application factory; it currently holds routes, view logic, filtering, and startup database checks. `scripts/utils.py` contains the SQLAlchemy models plus the Excel parsing and import pipeline. Server-rendered pages live in `templates/`, and frontend assets live in `static/css`, `static/js`, and `static/img`. Reference catalogs and sample spreadsheets are kept in `catalogos/` and `example_SIIF/`. Tests live in `tests/`. Runtime artifacts such as `instance/` and `log/` are generated locally and should stay untracked.

## Build, Test, and Development Commands
Use a local virtual environment:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

`python app.py` starts the development server on port `5009`. Run the full test suite with `python -m pytest tests/`. Run a focused test with `python -m pytest tests/test_import_balance.py -v`. Use `python analyze_opd.py <batch_number>` only for ad hoc spreadsheet inspection; there is no frontend build step in this repository.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, `snake_case` for functions/variables, and descriptive helper names. Private route helpers in `app.py` generally use a leading underscore. Keep template, CSS, and JS filenames feature-oriented and consistent, for example `catalogos_consulta.*`. No formatter or linter is configured in-repo, so match the current Flask/SQLAlchemy conventions and keep API field names stable.

## Testing Guidelines
Tests use `unittest` classes executed through `pytest` discovery. Name files `tests/test_*.py`, classes `*Tests`, and methods `test_*`. Prefer temporary SQLite databases and generated workbook fixtures over committed database files or production spreadsheets. New changes should cover both happy-path imports and validation or permission edge cases when applicable.

## Commit & Pull Request Guidelines
Recent history uses short, status-style commit subjects, sometimes with dates, such as `Working` or `27/03/2026 Finish SIIF structure and projects`. Keep commits brief but more specific than that, for example `Fix OPD catalog filtering`. Pull requests should summarize scope, note any schema or config impact, include the commands used for verification, and attach screenshots when changing templates or static assets.

## Configuration & Data Safety
Set `DATABASE_URL` and `SECRET_KEY` through environment variables outside local development. Do not commit `.env`, SQLite files, uploaded spreadsheets, or logs. Because `app.py` performs lightweight schema backfills on startup, call out any database-affecting change clearly in the PR.
