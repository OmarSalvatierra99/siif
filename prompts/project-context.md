# Contexto del proyecto — SIIF

## Descripción
Sistema de Información de Ingresos y Finanzas (SIPAC/SIIF) del OFS Tlaxcala. Procesa archivos Excel de SIIF para cargar transacciones contables, generar reportes de balances y comparativos.

## Arquitectura
- `create_app(config_name)` factory en `app.py`
- SQLAlchemy + SQLite (`sipac_dev.db`)
- Modelos: `Transaccion`, `LoteCarga`, `Usuario`, `ReporteGenerado`, `Ente`
- Catálogos en `catalogos/`

## Auth
RBAC por DB: `Usuario.query.filter(Usuario.activo.is_(True))` — usuarios en BD.  
`before_request` → `require_login()` — exento: `login`, `logout`, `static`, `health_check`.

## Estado de migración
- Migrado en wave 4 (2026-04-13)
- `log/` → `logs/`
- `/api/health` añadido (exento de auth)
- `SECRET_KEY` sin default hardcodeado
- `AGENTS.md`/`CLAUDE.md` movidos a `prompts/`
