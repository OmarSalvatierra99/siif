# SIPAC - Sistema de Procesamiento de Auxiliares Contables

Sistema web profesional con base de datos PostgreSQL, dashboard interactivo y generación de reportes.

## 🎯 Características Principales

### ✅ Funcionalidades

1. **Base de Datos PostgreSQL**
   - Almacenamiento persistente y escalable
   - Índices optimizados para consultas rápidas
   - Tracking de lotes de carga con UUID
   - Historial completo de transacciones

2. **Dashboard Interactivo**
   - Estadísticas en tiempo real
   - Gráficos de transacciones (Chart.js)
   - Filtros avanzados de búsqueda
   - Paginación de resultados
   - Visualización de top dependencias

3. **Sistema de Reportes**
   - Reportes predefinidos (mes, trimestre, año)
   - Reportes personalizados con múltiples filtros
   - Exportación a Excel con formato profesional
   - Límite configurable de registros

4. **API REST**
   - Endpoints para carga de datos
   - Consultas con filtros dinámicos
   - Estadísticas agregadas
   - Generación de reportes bajo demanda

## 📁 Estructura del Proyecto

```
sipac/
├── app_mejorado.py          # Aplicación Flask principal
├── models.py                # Modelos SQLAlchemy
├── config.py                # Configuración de la aplicación
├── data_processor.py        # Lógica de procesamiento de Excel
├── migrar_datos.py          # Script de migración de datos
├── requirements.txt         # Dependencias Python
├── .env                     # Variables de entorno (crear)
├── CLAUDE.md                # Guía para Claude Code
├── README.md                # Este archivo
│
├── templates/               # Plantillas HTML (Jinja2)
│   ├── base.html           # Plantilla base
│   ├── index.html          # Página de carga de archivos
│   ├── dashboard.html      # Dashboard interactivo
│   └── reportes.html       # Generación de reportes
│
├── static/                  # Archivos estáticos
│   ├── css/
│   │   └── style.css       # Estilos principales
│   ├── js/
│   │   └── main.js         # JavaScript común
│   └── img/
│       └── ofs_logo.png    # Logo de la organización
│
├── docs/                    # Documentación detallada
│   ├── INICIO_RAPIDO.md    # Guía de inicio rápido
│   ├── PLAN_IMPLEMENTACION.md  # Plan de implementación
│   ├── RESUMEN_MEJORAS.md  # Resumen de mejoras
│   ├── DIAGRAMAS.md        # Diagramas de arquitectura
│   ├── DESPLIEGUE.md       # Guía de despliegue
│   ├── SCRIPTS.md          # Documentación de scripts
│   └── INDICE.md           # Índice de documentación
│
├── scripts/                 # Scripts de utilidad
│   ├── setup_postgresql.sh     # Setup de PostgreSQL
│   ├── backup_sipac.sh         # Respaldo de BD
│   ├── restaurar_backup.sh     # Restauración de BD
│   ├── setup_backup_cron.sh    # Configurar cron para backups
│   ├── install_service.sh      # Instalar servicio systemd
│   ├── desplegar.sh           # Script de despliegue
│   ├── dev.sh                 # Modo desarrollo
│   └── verificar_sistema.sh    # Verificar estado del sistema
│
└── venv/                    # Entorno virtual Python (crear)
```

## 📋 Requisitos

- **Python:** 3.8 o superior
- **PostgreSQL:** 12 o superior
- **RAM:** 2GB mínimo (4GB recomendado)
- **Disco:** Según volumen de datos
- **SO:** Linux, macOS o Windows

## 🚀 Instalación Rápida

### 1. Clonar o preparar archivos

```bash
cd /ruta/a/sipac
```

### 2. Crear entorno virtual

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar PostgreSQL

**Opción A: Script automático (Linux)**

```bash
chmod +x setup_postgresql.sh
./setup_postgresql.sh
```

**Opción B: Manual**

```sql
-- Conectar a PostgreSQL
sudo -u postgres psql

-- Crear usuario y base de datos
CREATE USER sipac_user WITH PASSWORD 'sipac_password';
CREATE DATABASE sipac_db OWNER sipac_user;
GRANT ALL PRIVILEGES ON DATABASE sipac_db TO sipac_user;
\c sipac_db
GRANT ALL ON SCHEMA public TO sipac_user;
\q
```

### 5. Configurar variables de entorno

Crear archivo `.env`:

```env
DATABASE_URL=postgresql://sipac_user:sipac_password@localhost:5432/sipac_db
SECRET_KEY=tu-clave-secreta-aqui
FLASK_ENV=development
```

### 6. Iniciar la aplicación

```bash
python app_mejorado.py
```

**Accede a:**
- **Inicio:** http://localhost:4095
- **Dashboard:** http://localhost:4095/dashboard
- **Reportes:** http://localhost:4095/reportes

## 📖 Uso del Sistema

### 🔼 Carga de Archivos

1. Accede a la página principal
2. Arrastra o selecciona archivos Excel (.xlsx, .xls)
3. Haz clic en "Procesar archivos"
4. Observa el progreso en tiempo real
5. Los datos se guardan automáticamente en PostgreSQL

**Formato esperado del Excel:**
- Columnas: cuenta_contable, fecha, saldo_inicial, cargos, abonos, poliza, beneficiario, etc.
- Múltiples hojas soportadas
- Códigos de cuenta de 21 caracteres

### 📊 Dashboard

Muestra información en tiempo real:

- **Estadísticas:** Total de transacciones, cuentas, sumas de cargos/abonos
- **Gráficos:** Tendencias mensuales, top dependencias
- **Filtros:** Cuenta, dependencia, fechas, póliza, beneficiario
- **Tabla:** Resultados paginados con todos los detalles

### 📄 Generación de Reportes

Dos opciones:

1. **Reportes Rápidos:** Mes actual, trimestre, año completo
2. **Reportes Personalizados:** Configura todos los filtros disponibles

Los reportes se descargan en formato Excel con formato profesional.

## 🔧 API Endpoints

### Procesamiento de Archivos

```bash
POST /api/process
Content-Type: multipart/form-data
Body: archivo=file.xlsx

Response: { "job_id": "uuid" }
```

### Monitoreo de Progreso

```bash
GET /api/progress/{job_id}
# Server-Sent Events (SSE)
```

### Estadísticas

```bash
GET /api/dashboard/stats

Response: {
  "total_transacciones": 150000,
  "total_cuentas": 500,
  "suma_cargos": 50000000.00,
  "suma_abonos": 48000000.00,
  "transacciones_mes": [...]
}
```

### Consulta de Transacciones

```bash
GET /api/transacciones?page=1&per_page=50&cuenta_contable=11101&fecha_inicio=2024-01-01

Response: {
  "transacciones": [...],
  "total": 1000,
  "pages": 20,
  "current_page": 1
}
```

### Generación de Reportes

```bash
POST /api/reportes/generar
Content-Type: application/json

Body: {
  "fecha_inicio": "2024-01-01",
  "fecha_fin": "2024-12-31",
  "cuenta_contable": "11101"
}

Response: Excel file (binary)
```

## 🗄️ Base de Datos

### Tabla Principal: `transacciones`

Almacena todas las transacciones contables con:
- Componentes del código de cuenta (21 caracteres → 13 campos)
- Datos financieros: saldo inicial, cargos, abonos, saldo final
- Metadatos: fecha, póliza, beneficiario, descripción
- Trazabilidad: lote_id, archivo_origen, fecha_carga

**Índices optimizados:**
- `idx_cuenta_fecha`: (cuenta_contable, fecha_transaccion)
- `idx_dependencia_fecha`: (dependencia, fecha_transaccion)
- `idx_lote_cuenta`: (lote_id, cuenta_contable)

Ver documentación completa en `docs/PLAN_IMPLEMENTACION.md`.

## 🔐 Seguridad en Producción

1. **Cambiar credenciales por defecto**
2. **Usar SECRET_KEY seguro** (generado aleatoriamente)
3. **Configurar firewall** (UFW, iptables)
4. **Implementar HTTPS** (nginx + Let's Encrypt)
5. **Restringir acceso a PostgreSQL** (pg_hba.conf)
6. **Habilitar respaldos automáticos** (ver scripts/)

Ver guía completa en `docs/DESPLIEGUE.md`.

## 🔄 Respaldos

### Respaldo completo

```bash
pg_dump -U sipac_user -d sipac_db -F c -f backup_sipac_$(date +%Y%m%d).backup
```

### Restauración

```bash
pg_restore -U sipac_user -d sipac_db -v backup_sipac_20241110.backup
```

### Automatización

```bash
# Configurar respaldos automáticos diarios
chmod +x scripts/setup_backup_cron.sh
./scripts/setup_backup_cron.sh
```

## 🐛 Solución de Problemas

### PostgreSQL no se conecta

```bash
sudo systemctl status postgresql
sudo systemctl start postgresql
```

### Tablas no existen

```python
python
>>> from app_mejorado import create_app
>>> from models import db
>>> app = create_app()
>>> with app.app_context():
...     db.create_all()
```

### Error de memoria

Reducir `CHUNK_SIZE` en `config.py` o aumentar RAM.

### Formato de Excel incorrecto

Verificar que las columnas esperadas existan y los datos sean válidos.

## 📚 Documentación Adicional

- **Inicio Rápido:** `docs/INICIO_RAPIDO.md`
- **Arquitectura:** `docs/DIAGRAMAS.md`
- **Despliegue:** `docs/DESPLIEGUE.md`
- **Scripts:** `docs/SCRIPTS.md`
- **Guía Claude:** `CLAUDE.md` (para desarrollo con Claude Code)

## 🛠️ Desarrollo

### Estructura del código

- **Frontend:** HTML + Jinja2 + JavaScript vanilla
- **Backend:** Flask + SQLAlchemy
- **Base de datos:** PostgreSQL
- **Procesamiento:** Pandas + openpyxl
- **Reportes:** XlsxWriter
- **Gráficos:** Chart.js

### Agregar nuevas funcionalidades

Ver `CLAUDE.md` para guías de desarrollo específicas.

## 📞 Soporte

Para reportar problemas o sugerencias, contacta al equipo de desarrollo.

## 📄 Licencia

© Órgano de Fiscalización Superior del Estado de Tlaxcala

---

**Versión:** 2.0 (Sistema con BD PostgreSQL)
**Última actualización:** Noviembre 2024
