#!/bin/bash
# Script para restaurar un backup de SIPAC

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BACKUP_DIR="/home/gabo/backups/sipac"
DB_NAME="sipac_db"
DB_USER="sipac_user"

echo -e "${BLUE}=========================================="
echo "Restauración de Backup SIPAC"
echo "==========================================${NC}"
echo ""

# Verificar que existe el directorio de backups
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: Directorio de backups no existe${NC}"
    exit 1
fi

# Listar backups disponibles
echo "Backups disponibles:"
echo ""

BACKUPS=($(ls -t "$BACKUP_DIR"/sipac_*.backup 2>/dev/null))

if [ ${#BACKUPS[@]} -eq 0 ]; then
    echo -e "${RED}No hay backups disponibles${NC}"
    exit 1
fi

# Mostrar lista
for i in "${!BACKUPS[@]}"; do
    BACKUP_FILE="${BACKUPS[$i]}"
    BACKUP_DATE=$(stat -c %y "$BACKUP_FILE" | cut -d' ' -f1,2 | cut -d'.' -f1)
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "  [$i] $(basename $BACKUP_FILE)"
    echo "      Fecha: $BACKUP_DATE | Tamaño: $BACKUP_SIZE"
    echo ""
done

# Seleccionar backup
echo -n "Selecciona el número del backup a restaurar [0-$((${#BACKUPS[@]}-1))]: "
read SELECTION

if ! [[ "$SELECTION" =~ ^[0-9]+$ ]] || [ "$SELECTION" -lt 0 ] || [ "$SELECTION" -ge ${#BACKUPS[@]} ]; then
    echo -e "${RED}Selección inválida${NC}"
    exit 1
fi

SELECTED_BACKUP="${BACKUPS[$SELECTION]}"

echo ""
echo -e "${YELLOW}=========================================="
echo "ADVERTENCIA: Esta operación es DESTRUCTIVA"
echo "==========================================${NC}"
echo ""
echo "Se restaurará: $(basename $SELECTED_BACKUP)"
echo ""
echo -e "${RED}TODOS los datos actuales de la base de datos serán eliminados${NC}"
echo ""
read -p "¿Estás COMPLETAMENTE seguro? Escribe 'SI' para continuar: " CONFIRM

if [ "$CONFIRM" != "SI" ]; then
    echo "Operación cancelada"
    exit 0
fi

echo ""
echo "Iniciando restauración..."

# Detener servicio SIPAC si está corriendo
if systemctl is-active sipac > /dev/null 2>&1; then
    echo "Deteniendo servicio SIPAC..."
    sudo systemctl stop sipac
    RESTART_SERVICE=true
fi

# Crear backup de emergencia de la BD actual
echo "Creando backup de emergencia de la BD actual..."
EMERGENCY_BACKUP="${BACKUP_DIR}/emergency_$(date +%Y%m%d_%H%M%S).backup"
pg_dump -U "$DB_USER" -d "$DB_NAME" -F c -f "$EMERGENCY_BACKUP" 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Backup de emergencia creado: $EMERGENCY_BACKUP${NC}"
else
    echo -e "${YELLOW}⚠ No se pudo crear backup de emergencia (la BD podría no existir)${NC}"
fi

# Eliminar conexiones activas
echo "Cerrando conexiones activas..."
psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" 2>/dev/null

# Eliminar y recrear base de datos
echo "Eliminando base de datos actual..."
dropdb -U postgres "$DB_NAME" 2>/dev/null

echo "Creando base de datos nueva..."
createdb -U postgres -O "$DB_USER" "$DB_NAME"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error al crear base de datos${NC}"
    exit 1
fi

# Restaurar backup
echo "Restaurando backup..."
pg_restore -U "$DB_USER" -d "$DB_NAME" -v "$SELECTED_BACKUP" 2>&1 | grep -E "processing|creating|restoring"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Backup restaurado exitosamente${NC}"

    # Obtener estadísticas
    TRANS_COUNT=$(psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM transacciones;" | xargs)
    LOTES_COUNT=$(psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM lotes_carga;" | xargs)

    echo ""
    echo "Estadísticas de la BD restaurada:"
    echo "  Transacciones: $TRANS_COUNT"
    echo "  Lotes: $LOTES_COUNT"
else
    echo ""
    echo -e "${RED}✗ Error al restaurar backup${NC}"

    if [ -f "$EMERGENCY_BACKUP" ]; then
        echo ""
        echo "Puedes restaurar el backup de emergencia con:"
        echo "  $0"
        echo "  y seleccionar: $EMERGENCY_BACKUP"
    fi

    exit 1
fi

# Reiniciar servicio si estaba corriendo
if [ "$RESTART_SERVICE" = true ]; then
    echo ""
    echo "Reiniciando servicio SIPAC..."
    sudo systemctl start sipac

    if systemctl is-active sipac > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Servicio SIPAC reiniciado${NC}"
    else
        echo -e "${RED}✗ Error al reiniciar servicio${NC}"
        echo "Verifica los logs con: sudo journalctl -u sipac -n 50"
    fi
fi

echo ""
echo -e "${GREEN}=========================================="
echo "Restauración completada"
echo "==========================================${NC}"
