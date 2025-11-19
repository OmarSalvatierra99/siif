# SIPAC - Sistema de Procesamiento de Auxiliares Contables

Sistema web para procesar, analizar y generar reportes de transacciones contables desde archivos Excel.

## 🏗️ Arquitectura del Proyecto

```
SIPAC/
├── app/                          # Código de la aplicación
│   ├── __init__.py
│   ├── factory.py               # Application factory
│   ├── logging_config.py        # Configuración de logging
│   ├── models/                  # Modelos de base de datos
│   │   ├── __init__.py
│   │   ├── transaccion.py      # Modelo de transacciones
│   │   ├── lote_carga.py       # Modelo de lotes de carga
│   │   ├── usuario.py          # Modelo de usuarios
│   │   ├── reporte_generado.py # Modelo de reportes
│   │   └── ente.py             # Modelo de entes públicos
│   ├── routes/                  # Rutas y endpoints (Blueprints)
│   │   ├── __init__.py
│   │   ├── main.py             # Rutas de páginas principales
│   │   ├── upload.py           # Carga y procesamiento
│   │   ├── reports.py          # Generación de reportes
│   │   ├── entes.py            # Gestión de entes
│   │   └── api.py              # API de consultas
│   ├── services/                # Lógica de negocio
│   │   ├── __init__.py
│   │   ├── data_processor.py   # Procesador principal de datos
│   │   └── excel_reader.py     # Lector de archivos Excel
│   └── utils/                   # Utilidades
│       ├── __init__.py
│       ├── helpers.py          # Funciones auxiliares
│       ├── validators.py       # Validadores de datos
│       └── excel_parser.py     # Parser de cuentas contables
├── templates/                   # Plantillas HTML
├── static/                      # Archivos estáticos (CSS, JS)
├── scripts/                     # Scripts de deployment y mantenimiento
├── logs/                        # Archivos de log (generado automáticamente)
├── config.py                    # Configuración de la aplicación
├── run.py                       # Punto de entrada principal
├── requirements.txt             # Dependencias Python
├── .env                         # Variables de entorno (no versionado)
├── .env.example                 # Ejemplo de variables de entorno
└── CLAUDE.md                    # Documentación para Claude Code
```

## 🚀 Inicio Rápido

### Requisitos Previos

- Python 3.8+
- PostgreSQL 12+
- pip

### Instalación

1. **Clonar el repositorio**
```bash
git clone <repository-url>
cd SIPAC
```

2. **Crear entorno virtual**
```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

5. **Configurar PostgreSQL**
```bash
./scripts/setup_postgresql.sh
```

6. **Ejecutar la aplicación**
```bash
python run.py
```

La aplicación estará disponible en `http://localhost:5020`

## 📊 Características Principales

### Procesamiento de Datos
- **Lectura paralela** de múltiples archivos Excel
- **Descomposición automática** de cuentas contables de 21 caracteres
- **Cálculo de saldos acumulativos** por cuenta
- **Inserción optimizada** en base de datos por lotes
- **Seguimiento en tiempo real** del progreso de carga

### Consultas y Reportes
- **Filtros avanzados** por múltiples criterios
- **Generación de reportes Excel** con hasta 100,000 registros
- **Paginación eficiente** de resultados
- **Estadísticas del dashboard** en tiempo real

### Logging Completo
- **Logs rotativos** por día y tamaño
- **Niveles de log** configurables
- **Logs separados** para:
  - General (`logs/sipac.log`)
  - Errores (`logs/sipac_errors.log`)
  - Procesamiento de datos (`logs/data_processing.log`)

## 🔧 Configuración

### Variables de Entorno (.env)

```bash
# Entorno
FLASK_ENV=development

# Base de datos
DATABASE_URL=postgresql://usuario:password@localhost:5432/sipac_db

# Seguridad
SECRET_KEY=tu-clave-secreta-aleatoria

# Procesamiento
MAX_WORKERS=4          # Workers para lectura paralela
CHUNK_SIZE=1000        # Tamaño de lote para inserción BD
```

## 📝 API Endpoints

### Carga de Archivos
- `POST /api/process` - Cargar archivos Excel
- `GET /api/progress/<job_id>` - Stream de progreso (SSE)

### Consultas
- `GET /api/transacciones` - Listar transacciones con filtros
- `GET /api/dependencias/lista` - Lista de dependencias
- `GET /api/dashboard/stats` - Estadísticas del dashboard

### Reportes
- `POST /api/reportes/generar` - Generar reporte Excel

### Catálogo de Entes
- `GET /api/entes` - Listar entes
- `POST /api/entes` - Crear ente
- `PUT /api/entes/<id>` - Actualizar ente
- `DELETE /api/entes/<id>` - Eliminar ente

## 🗃️ Estructura de Base de Datos

### Tablas Principales

- **transacciones**: Transacciones contables con cuenta descompuesta
- **lotes_carga**: Seguimiento de lotes de archivos procesados
- **usuarios**: Usuarios del sistema (admin, auditor, consulta)
- **reportes_generados**: Auditoría de reportes generados
- **entes**: Catálogo de entes públicos

### Índices Optimizados

```sql
-- Índices compuestos para consultas frecuentes
idx_cuenta_fecha (cuenta_contable, fecha_transaccion)
idx_dependencia_fecha (dependencia, fecha_transaccion)
idx_lote_cuenta (lote_id, cuenta_contable)
```

## 🔍 Formato de Cuenta Contable

Las cuentas contables son códigos de 21 caracteres que se descomponen en:

```
Posición  | Componente
----------|--------------------
[0]       | Género
[1]       | Grupo
[2]       | Rubro
[3]       | Cuenta
[4]       | Subcuenta
[5:7]     | Dependencia
[7:9]     | Unidad Responsable
[9:11]    | Centro de Costo
[11:13]   | Proyecto Presupuestario
[13]      | Fuente
[14:16]   | SubFuente
[16]      | Tipo de Recurso
[17:21]   | Partida Presupuestal
```

## 🛠️ Scripts de Mantenimiento

### Desarrollo
```bash
./scripts/dev.sh                # Iniciar servidor de desarrollo
```

### Base de Datos
```bash
./scripts/setup_postgresql.sh   # Configurar PostgreSQL
./scripts/backup_sipac.sh       # Backup de base de datos
./scripts/restaurar_backup.sh   # Restaurar backup
```

### Deployment
```bash
./scripts/desplegar.sh          # Desplegar en producción
./scripts/install_service.sh    # Instalar como servicio systemd
```

## 📋 Logs

Los logs se generan automáticamente en el directorio `logs/`:

- **sipac.log**: Log general con rotación diaria (30 días de retención)
- **sipac_errors.log**: Solo errores (60 días de retención)
- **data_processing.log**: Procesamiento de datos (rotación por tamaño 10MB, 10 archivos)

### Niveles de Log

- **DEBUG**: Información detallada para desarrollo
- **INFO**: Eventos importantes del sistema
- **WARNING**: Advertencias (datos no válidos, etc.)
- **ERROR**: Errores que no detienen la aplicación
- **CRITICAL**: Errores críticos que requieren atención inmediata

## 🧪 Testing

```bash
# Ejecutar tests (cuando estén disponibles)
pytest

# Con cobertura
pytest --cov=app tests/
```

## 📄 Licencia

[Tu licencia aquí]

## 👥 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📞 Soporte

Para reportar problemas o solicitar nuevas características, por favor abre un issue en el repositorio.
