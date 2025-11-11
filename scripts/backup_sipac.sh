#!/bin/bash
# Script de respaldo automático para SIPAC
# Este script debe ejecutarse via cron

# Configuración
BACKUP_DIR="/home/gabo/backups/sipac"
DB_NAME="sipac_db"
DB_USER="sipac_user"
RETENTION_DAYS=30
LOG_FILE="/home/gabo/backups/sipac/backup.log"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función de logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Crear directorio de respaldo si no existe
mkdir -p "$BACKUP_DIR"

# Nombre del archivo de respaldo con fecha
FECHA=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/sipac_${FECHA}.backup"
BACKUP_SQL="${BACKUP_DIR}/sipac_${FECHA}.sql.gz"

log "=========================================="
log "Iniciando respaldo de SIPAC"
log "=========================================="

# Verificar que PostgreSQL está corriendo
if ! systemctl is-active --quiet postgresql; then
    log "${RED}ERROR: PostgreSQL no está corriendo${NC}"
    exit 1
fi

# Respaldo en formato custom (binario comprimido)
log "Creando respaldo en formato custom..."
if pg_dump -U "$DB_USER" -d "$DB_NAME" -F c -f "$BACKUP_FILE"; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "${GREEN}✓ Respaldo custom creado exitosamente: $BACKUP_FILE ($BACKUP_SIZE)${NC}"
else
    log "${RED}✗ Error al crear respaldo custom${NC}"
    exit 1
fi

# Respaldo en formato SQL (texto comprimido) - más portable
log "Creando respaldo en formato SQL..."
if pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_SQL"; then
    SQL_SIZE=$(du -h "$BACKUP_SQL" | cut -f1)
    log "${GREEN}✓ Respaldo SQL creado exitosamente: $BACKUP_SQL ($SQL_SIZE)${NC}"
else
    log "${RED}✗ Error al crear respaldo SQL${NC}"
fi

# Verificar integridad del respaldo
log "Verificando integridad del respaldo..."
if pg_restore -l "$BACKUP_FILE" > /dev/null 2>&1; then
    log "${GREEN}✓ Respaldo verificado correctamente${NC}"
else
    log "${RED}✗ El respaldo parece estar corrupto${NC}"
    exit 1
fi

# Eliminar respaldos antiguos
log "Limpiando respaldos antiguos (más de $RETENTION_DAYS días)..."
DELETED_COUNT=$(find "$BACKUP_DIR" -name "sipac_*.backup" -type f -mtime +$RETENTION_DAYS -delete -print | wc -l)
DELETED_SQL=$(find "$BACKUP_DIR" -name "sipac_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete -print | wc -l)
log "Eliminados $DELETED_COUNT respaldos .backup y $DELETED_SQL respaldos .sql.gz antiguos"

# Estadísticas del respaldo
log ""
log "Estadísticas de respaldos:"
log "  Total de respaldos: $(ls -1 ${BACKUP_DIR}/sipac_*.backup 2>/dev/null | wc -l)"
log "  Espacio utilizado: $(du -sh ${BACKUP_DIR} | cut -f1)"

# Obtener estadísticas de la base de datos
log ""
log "Estadísticas de la base de datos:"
DB_SIZE=$(psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));")
TRANS_COUNT=$(psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM transacciones;")
LOTES_COUNT=$(psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM lotes_carga;")

log "  Tamaño de BD: ${DB_SIZE}"
log "  Transacciones: ${TRANS_COUNT}"
log "  Lotes cargados: ${LOTES_COUNT}"

log ""
log "=========================================="
log "Respaldo completado exitosamente"
log "=========================================="

# Opcional: Enviar notificación por email (descomentar si tienes mail configurado)
# echo "Respaldo de SIPAC completado: $BACKUP_FILE ($BACKUP_SIZE)" | mail -s "Respaldo SIPAC - $(date +%Y-%m-%d)" admin@example.com

exit 0
