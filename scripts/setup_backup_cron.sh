#!/bin/bash
# Script para configurar respaldos automáticos via cron

echo "=========================================="
echo "Configuración de Respaldos Automáticos"
echo "=========================================="

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup_sipac.sh"

# Verificar que existe el script de backup
if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo -e "${RED}Error: No se encuentra backup_sipac.sh${NC}"
    exit 1
fi

# Hacer ejecutable el script de backup
chmod +x "$BACKUP_SCRIPT"
echo -e "${GREEN}✓ Script de backup configurado como ejecutable${NC}"

# Crear directorio de respaldos
mkdir -p /home/gabo/backups/sipac
echo -e "${GREEN}✓ Directorio de respaldos creado${NC}"

# Verificar si ya existe una entrada en crontab
if crontab -l 2>/dev/null | grep -q "backup_sipac.sh"; then
    echo -e "${YELLOW}Ya existe una tarea programada para respaldos${NC}"
    echo "Tareas actuales:"
    crontab -l | grep backup_sipac.sh
    echo ""
    read -p "¿Deseas reemplazarla? (s/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        echo "Operación cancelada"
        exit 0
    fi
    # Eliminar entrada existente
    crontab -l | grep -v backup_sipac.sh | crontab -
fi

# Preguntar la hora para el respaldo
echo ""
echo "¿A qué hora deseas ejecutar el respaldo diario?"
read -p "Hora (0-23): " HOUR
read -p "Minuto (0-59): " MINUTE

# Validar entrada
if ! [[ "$HOUR" =~ ^[0-9]+$ ]] || [ "$HOUR" -lt 0 ] || [ "$HOUR" -gt 23 ]; then
    echo -e "${RED}Hora inválida${NC}"
    exit 1
fi

if ! [[ "$MINUTE" =~ ^[0-9]+$ ]] || [ "$MINUTE" -lt 0 ] || [ "$MINUTE" -gt 59 ]; then
    echo -e "${RED}Minuto inválido${NC}"
    exit 1
fi

# Agregar tarea a crontab
CRON_ENTRY="$MINUTE $HOUR * * * $BACKUP_SCRIPT >> /home/gabo/backups/sipac/backup.log 2>&1"

(crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -

echo ""
echo -e "${GREEN}✓ Respaldo automático configurado exitosamente${NC}"
echo ""
echo "Configuración:"
echo "  Hora de ejecución: $(printf "%02d:%02d" $HOUR $MINUTE) diariamente"
echo "  Script: $BACKUP_SCRIPT"
echo "  Directorio de respaldos: /home/gabo/backups/sipac"
echo "  Log: /home/gabo/backups/sipac/backup.log"
echo "  Retención: 30 días"
echo ""
echo "Para ver tareas programadas: crontab -l"
echo "Para editar manualmente: crontab -e"
echo "Para ver logs: tail -f /home/gabo/backups/sipac/backup.log"
echo ""
echo "Puedes probar el respaldo manualmente con:"
echo "  $BACKUP_SCRIPT"
echo ""

# Preguntar si ejecutar respaldo de prueba
read -p "¿Deseas ejecutar un respaldo de prueba ahora? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    echo "Ejecutando respaldo de prueba..."
    $BACKUP_SCRIPT
    echo ""
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Respaldo de prueba completado${NC}"
    else
        echo -e "${RED}✗ Error en respaldo de prueba${NC}"
    fi
fi

echo ""
echo -e "${GREEN}=========================================="
echo "Configuración completada"
echo "==========================================${NC}"
