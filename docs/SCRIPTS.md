# Guía de Scripts de SIPAC

Esta guía describe todos los scripts disponibles en el proyecto SIPAC y cómo usarlos.

## Scripts de Despliegue

### `desplegar.sh` - Despliegue Automático Completo
**Descripción:** Script maestro que ejecuta todo el proceso de instalación y configuración.

**Uso:**
```bash
chmod +x desplegar.sh
./desplegar.sh
```

**Qué hace:**
- ✅ Verifica dependencias del sistema (Python, PostgreSQL)
- ✅ Ejecuta setup_postgresql.sh
- ✅ Crea entorno virtual de Python
- ✅ Instala dependencias desde requirements.txt
- ✅ Inicializa tablas de la base de datos
- ✅ Ofrece configurar servicio systemd
- ✅ Ofrece configurar respaldos automáticos
- ✅ Ejecuta verificación final del sistema

**Cuándo usarlo:** Primera instalación del sistema.

---

### `setup_postgresql.sh` - Configuración de PostgreSQL
**Descripción:** Instala y configura PostgreSQL con la base de datos y usuario de SIPAC.

**Uso:**
```bash
chmod +x setup_postgresql.sh
./setup_postgresql.sh
```

**Qué hace:**
- ✅ Verifica instalación de PostgreSQL
- ✅ Corrige problemas de collation si existen
- ✅ Crea usuario `sipac_user` con contraseña
- ✅ Crea base de datos `sipac_db`
- ✅ Configura permisos
- ✅ Genera archivo `.env` con credenciales

**Cuándo usarlo:** Primera instalación o para recrear la base de datos.

---

### `install_service.sh` - Instalación de Servicio Systemd
**Descripción:** Instala SIPAC como servicio systemd para ejecución automática.

**Uso:**
```bash
chmod +x install_service.sh
sudo ./install_service.sh
```

**Qué hace:**
- ✅ Copia archivo sipac.service a /etc/systemd/system/
- ✅ Recarga configuración de systemd
- ✅ Habilita inicio automático del servicio
- ✅ Ofrece iniciar el servicio inmediatamente

**Cuándo usarlo:** Para configurar SIPAC como servicio en producción.

**Requiere:** Privilegios de superusuario (sudo).

---

## Scripts de Desarrollo

### `dev.sh` - Modo Desarrollo
**Descripción:** Inicia la aplicación en modo desarrollo con configuración automática.

**Uso:**
```bash
./dev.sh
```

**Qué hace:**
- ✅ Verifica y crea entorno virtual si no existe
- ✅ Activa entorno virtual
- ✅ Verifica/crea archivo .env
- ✅ Verifica que PostgreSQL esté corriendo
- ✅ Exporta variables de entorno
- ✅ Inicia aplicación en modo desarrollo

**Cuándo usarlo:** Durante el desarrollo para probar cambios rápidamente.

**Características:**
- Hot reload habilitado
- Debug mode activado
- Logs detallados en consola

---

## Scripts de Respaldo

### `backup_sipac.sh` - Respaldo Manual
**Descripción:** Ejecuta un respaldo completo de la base de datos.

**Uso:**
```bash
./backup_sipac.sh
```

**Qué hace:**
- ✅ Verifica que PostgreSQL esté corriendo
- ✅ Crea respaldo en formato custom (.backup)
- ✅ Crea respaldo en formato SQL comprimido (.sql.gz)
- ✅ Verifica integridad del respaldo
- ✅ Elimina respaldos antiguos (>30 días)
- ✅ Muestra estadísticas de la base de datos
- ✅ Registra todo en log

**Ubicación de respaldos:** `/home/gabo/backups/sipac/`

**Cuándo usarlo:**
- Antes de actualizaciones importantes
- Antes de migraciones de datos grandes
- Como respaldo de emergencia

**Formatos generados:**
- `.backup` - Formato binario comprimido (para pg_restore)
- `.sql.gz` - Formato SQL comprimido (más portable)

---

### `setup_backup_cron.sh` - Configuración de Respaldos Automáticos
**Descripción:** Configura respaldos automáticos diarios via cron.

**Uso:**
```bash
./setup_backup_cron.sh
```

**Qué hace:**
- ✅ Hace ejecutable backup_sipac.sh
- ✅ Crea directorio de respaldos
- ✅ Verifica entradas existentes en crontab
- ✅ Pregunta hora de ejecución deseada
- ✅ Agrega tarea a crontab
- ✅ Ofrece ejecutar respaldo de prueba

**Cuándo usarlo:** Una vez después de la instalación en producción.

**Configuración por defecto:**
- Retención: 30 días
- Log: /home/gabo/backups/sipac/backup.log

---

### `restaurar_backup.sh` - Restauración de Respaldo
**Descripción:** Restaura la base de datos desde un respaldo previo.

**Uso:**
```bash
./restaurar_backup.sh
```

**Qué hace:**
- ✅ Lista todos los respaldos disponibles
- ✅ Permite seleccionar respaldo a restaurar
- ✅ Solicita confirmación (operación destructiva)
- ✅ Detiene servicio SIPAC si está corriendo
- ✅ Crea respaldo de emergencia de BD actual
- ✅ Elimina y recrea base de datos
- ✅ Restaura respaldo seleccionado
- ✅ Verifica restauración
- ✅ Reinicia servicio SIPAC

**Cuándo usarlo:**
- Recuperación ante desastres
- Rollback después de errores críticos
- Restauración de datos históricos

**⚠️ ADVERTENCIA:** Esta operación elimina todos los datos actuales de la base de datos.

---

## Scripts de Mantenimiento

### `verificar_sistema.sh` - Verificación del Sistema
**Descripción:** Ejecuta una verificación completa del sistema y reporta estado.

**Uso:**
```bash
./verificar_sistema.sh
```

**Qué verifica:**
1. **Sistema Operativo**
   - Python 3 (versión >= 3.8)
   - PostgreSQL
   - pip

2. **PostgreSQL**
   - Servicio activo
   - Conexión a base de datos
   - Estadísticas (transacciones, lotes, tamaño)

3. **Archivos del Proyecto**
   - app_mejorado.py, models.py, config.py, etc.
   - Directorio templates/
   - Templates HTML (index, dashboard, reportes)
   - Archivo .env

4. **Entorno Virtual**
   - Directorio venv/
   - Python y pip en venv
   - Dependencias instaladas (Flask, SQLAlchemy, pandas, etc.)

5. **Servicio SIPAC**
   - Archivo de servicio systemd
   - Estado habilitado/deshabilitado
   - Estado activo/inactivo

6. **Conectividad**
   - Puerto 4095 abierto
   - Aplicación respondiendo HTTP

7. **Sistema de Respaldos**
   - Scripts de backup
   - Directorio de backups
   - Respaldos existentes
   - Configuración de cron

**Salida:**
- ✓ Verde: Todo correcto
- ⚠ Amarillo: Advertencia (no crítico)
- ✗ Rojo: Error crítico

**Códigos de salida:**
- `0`: Sistema completamente funcional
- `1`: Errores críticos encontrados

**Cuándo usarlo:**
- Después de la instalación
- Después de actualizaciones
- Como verificación diaria en producción
- Para diagnosticar problemas

---

## Scripts de Datos

### `migrar_datos.py` - Migración de Datos
**Descripción:** Script Python para migrar archivos Excel existentes a la base de datos.

**Uso:**
```bash
# Ver ayuda
python migrar_datos.py ayuda

# Migrar archivos de un directorio
python migrar_datos.py migrar /ruta/a/archivos

# Verificar estado de la base de datos
python migrar_datos.py verificar

# Limpiar base de datos (¡CUIDADO!)
python migrar_datos.py limpiar
```

**Comandos disponibles:**

#### `migrar <directorio>`
Procesa todos los archivos .xlsx del directorio y los carga a la BD.
- Procesamiento en lotes
- Barra de progreso
- Manejo de errores
- Registro de lote en BD

#### `verificar`
Muestra estadísticas de la base de datos:
- Total de transacciones
- Total de cuentas únicas
- Suma de cargos y abonos
- Lotes cargados

#### `limpiar`
Elimina TODOS los datos de la base de datos.
⚠️ Solicita confirmación escribiendo "CONFIRMAR"

**Cuándo usarlo:**
- Migración inicial de datos históricos
- Carga masiva de archivos
- Verificación de integridad de datos

---

## Archivos de Configuración

### `sipac.service` - Archivo de Servicio Systemd
**Descripción:** Configuración del servicio systemd para SIPAC.

**Contenido clave:**
- Usuario: gabo
- WorkingDirectory: /home/gabo/portfolio/projects/sipac
- Comando: python app_mejorado.py desde venv
- Restart: always (reinicio automático)
- Dependencias: postgresql.service

**No editar directamente.** Usar install_service.sh para instalar.

---

### `.env` - Variables de Entorno
**Descripción:** Archivo con configuración sensible (no incluido en repositorio).

**Contenido requerido:**
```env
DATABASE_URL=postgresql://sipac_user:sipac_password@localhost:5432/sipac_db
SECRET_KEY=clave-secreta-aleatoria-aqui
FLASK_ENV=development  # o production
```

**Generación automática:** setup_postgresql.sh lo crea automáticamente.

---

## Flujo de Trabajo Recomendado

### Primera Instalación (Producción)
```bash
# 1. Despliegue automático
./desplegar.sh

# 2. Migrar datos existentes (opcional)
python migrar_datos.py migrar /ruta/a/archivos

# 3. Verificar sistema
./verificar_sistema.sh

# 4. Probar aplicación
curl http://localhost:4095
```

### Desarrollo
```bash
# 1. Iniciar en modo desarrollo
./dev.sh

# 2. Hacer cambios en el código

# 3. Recargar automáticamente (hot reload)

# 4. Verificar que funciona
./verificar_sistema.sh
```

### Mantenimiento Regular
```bash
# Verificación diaria
./verificar_sistema.sh

# Backup manual antes de cambios importantes
./backup_sipac.sh

# Ver logs
sudo journalctl -u sipac -n 50

# Reiniciar si es necesario
sudo systemctl restart sipac
```

### Recuperación ante Desastres
```bash
# 1. Detener servicio
sudo systemctl stop sipac

# 2. Restaurar backup
./restaurar_backup.sh

# 3. Verificar sistema
./verificar_sistema.sh

# 4. Reiniciar servicio
sudo systemctl start sipac
```

---

## Troubleshooting

### Script no es ejecutable
```bash
chmod +x nombre_script.sh
```

### Falta el entorno virtual
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### PostgreSQL no está corriendo
```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Base de datos no existe
```bash
./setup_postgresql.sh
```

### Permisos insuficientes
```bash
# Algunos scripts requieren sudo
sudo ./install_service.sh
```

---

## Resumen Rápido

| Script | Propósito | Cuándo Usar | Requiere Sudo |
|--------|-----------|-------------|---------------|
| `desplegar.sh` | Instalación completa | Primera vez | Parcial |
| `setup_postgresql.sh` | Configurar BD | Primera vez / Recrear BD | Parcial |
| `install_service.sh` | Instalar servicio | Producción | Sí |
| `dev.sh` | Desarrollo | Desarrollo diario | No |
| `backup_sipac.sh` | Backup manual | Antes de cambios | No |
| `setup_backup_cron.sh` | Config backups auto | Una vez en prod | No |
| `restaurar_backup.sh` | Restaurar BD | Emergencias | No |
| `verificar_sistema.sh` | Verificar estado | Diagnóstico | No |
| `migrar_datos.py` | Migrar Excel a BD | Carga inicial | No |

---

**Última actualización:** Noviembre 2024
**Versión:** 2.0
