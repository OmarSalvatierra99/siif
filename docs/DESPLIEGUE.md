# Guía de Despliegue Rápido - SIPAC

Esta guía te ayudará a desplegar SIPAC en menos de 10 minutos.

## Opción 1: Despliegue Automático (Recomendado)

```bash
# 1. Clonar o descargar el proyecto
cd /home/gabo/portfolio/projects/sipac

# 2. Ejecutar script de despliegue
chmod +x desplegar.sh
./desplegar.sh
```

El script automático hará:
- ✅ Verificar dependencias del sistema
- ✅ Instalar y configurar PostgreSQL
- ✅ Crear entorno virtual de Python
- ✅ Instalar dependencias
- ✅ Inicializar base de datos
- ✅ Configurar servicio systemd (opcional)
- ✅ Configurar respaldos automáticos (opcional)

## Opción 2: Despliegue Manual

### Paso 1: Instalar Dependencias del Sistema

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql postgresql-contrib
```

### Paso 2: Configurar PostgreSQL

```bash
chmod +x setup_postgresql.sh
./setup_postgresql.sh
```

### Paso 3: Configurar Python

```bash
# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Paso 4: Inicializar Base de Datos

```bash
python << EOF
from app_mejorado import create_app
from models import db
app = create_app()
with app.app_context():
    db.create_all()
EOF
```

### Paso 5: Iniciar Aplicación

**Para desarrollo:**
```bash
./dev.sh
```

**Para producción (con systemd):**
```bash
chmod +x install_service.sh
sudo ./install_service.sh
```

## Scripts Disponibles

### Desarrollo

- **`./dev.sh`** - Inicia aplicación en modo desarrollo
  - Auto-configura entorno virtual
  - Carga variables de entorno
  - Hot reload habilitado

### Despliegue

- **`./desplegar.sh`** - Despliegue completo automático
- **`./setup_postgresql.sh`** - Configura PostgreSQL
- **`./install_service.sh`** - Instala servicio systemd

### Respaldos

- **`./backup_sipac.sh`** - Ejecuta respaldo manual
- **`./setup_backup_cron.sh`** - Configura respaldos automáticos
- **`./restaurar_backup.sh`** - Restaura un respaldo

### Mantenimiento

- **`./verificar_sistema.sh`** - Verifica estado del sistema
- **`python migrar_datos.py migrar /ruta/`** - Migra archivos Excel existentes

## Verificación Post-Instalación

```bash
# Verificar que todo funciona
./verificar_sistema.sh

# Ver estado del servicio
sudo systemctl status sipac

# Ver logs en tiempo real
sudo journalctl -u sipac -f
```

## Acceder a la Aplicación

Una vez desplegada, accede a:

- **Carga de archivos:** http://localhost:4095
- **Dashboard:** http://localhost:4095/dashboard
- **Reportes:** http://localhost:4095/reportes

## Configuración de Firewall (Opcional)

Si necesitas acceder desde otras máquinas:

```bash
# Abrir puerto 4095
sudo ufw allow 4095/tcp
sudo ufw enable
```

## Comandos Útiles

### Control del Servicio
```bash
sudo systemctl start sipac      # Iniciar
sudo systemctl stop sipac       # Detener
sudo systemctl restart sipac    # Reiniciar
sudo systemctl status sipac     # Ver estado
sudo systemctl enable sipac     # Habilitar inicio automático
sudo systemctl disable sipac    # Deshabilitar inicio automático
```

### Logs
```bash
# Ver logs completos
sudo journalctl -u sipac

# Ver últimos 50 logs
sudo journalctl -u sipac -n 50

# Seguir logs en tiempo real
sudo journalctl -u sipac -f

# Ver logs de PostgreSQL
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### Base de Datos
```bash
# Conectar a la base de datos
psql -U sipac_user -d sipac_db

# Ver tamaño de la base de datos
psql -U sipac_user -d sipac_db -c "SELECT pg_size_pretty(pg_database_size('sipac_db'));"

# Ver número de transacciones
psql -U sipac_user -d sipac_db -c "SELECT COUNT(*) FROM transacciones;"

# Backup manual
./backup_sipac.sh

# Restaurar backup
./restaurar_backup.sh
```

## Solución de Problemas

### PostgreSQL no inicia
```bash
sudo systemctl status postgresql
sudo journalctl -u postgresql -n 50
sudo systemctl restart postgresql
```

### Error de conexión a base de datos
```bash
# Verificar credenciales en .env
cat .env

# Verificar que existe la base de datos
psql -U postgres -l | grep sipac

# Recrear base de datos si es necesario
./setup_postgresql.sh
```

### Servicio no inicia
```bash
# Ver error específico
sudo journalctl -u sipac -n 50

# Verificar permisos
ls -la /home/gabo/portfolio/projects/sipac

# Verificar entorno virtual
source venv/bin/activate
python -c "import flask; print('OK')"
```

### Puerto en uso
```bash
# Ver qué proceso usa el puerto 4095
sudo netstat -tulpn | grep 4095

# Matar proceso si es necesario
sudo kill -9 <PID>
```

## Actualización

Para actualizar la aplicación:

```bash
# 1. Hacer backup
./backup_sipac.sh

# 2. Detener servicio
sudo systemctl stop sipac

# 3. Actualizar código
git pull  # o copiar nuevos archivos

# 4. Actualizar dependencias
source venv/bin/activate
pip install -r requirements.txt

# 5. Reiniciar servicio
sudo systemctl start sipac

# 6. Verificar
./verificar_sistema.sh
```

## Desinstalación

```bash
# 1. Detener y deshabilitar servicio
sudo systemctl stop sipac
sudo systemctl disable sipac
sudo rm /etc/systemd/system/sipac.service
sudo systemctl daemon-reload

# 2. Eliminar cron de backups
crontab -l | grep -v backup_sipac.sh | crontab -

# 3. Eliminar base de datos (CUIDADO: Esto borra todos los datos)
dropdb -U postgres sipac_db
dropuser -U postgres sipac_user

# 4. Eliminar archivos del proyecto
rm -rf /home/gabo/portfolio/projects/sipac

# 5. Eliminar backups (opcional)
rm -rf /home/gabo/backups/sipac
```

## Migración de Datos Existentes

Si tienes archivos Excel previos:

```bash
# Ver ayuda
python migrar_datos.py ayuda

# Migrar archivos de un directorio
python migrar_datos.py migrar /ruta/a/archivos/excel

# Verificar migración
python migrar_datos.py verificar

# Ver estado de lotes
python migrar_datos.py lotes
```

## Monitoreo

### Verificación Diaria
```bash
./verificar_sistema.sh
```

### Métricas de la Base de Datos
```bash
psql -U sipac_user -d sipac_db << EOF
-- Tamaño de la base de datos
SELECT pg_size_pretty(pg_database_size('sipac_db'));

-- Número de transacciones
SELECT COUNT(*) FROM transacciones;

-- Transacciones por mes
SELECT
    DATE_TRUNC('month', fecha_transaccion) as mes,
    COUNT(*) as total
FROM transacciones
GROUP BY mes
ORDER BY mes DESC
LIMIT 12;

-- Top 10 cuentas con más movimientos
SELECT
    cuenta_contable,
    COUNT(*) as movimientos
FROM transacciones
GROUP BY cuenta_contable
ORDER BY movimientos DESC
LIMIT 10;
EOF
```

## Soporte

- **Documentación completa:** README.md
- **Plan de implementación:** PLAN_IMPLEMENTACION.md
- **Resumen de mejoras:** RESUMEN_MEJORAS.md
- **Diagramas:** DIAGRAMAS.md

---

**Última actualización:** Noviembre 2024
**Versión:** 2.0
