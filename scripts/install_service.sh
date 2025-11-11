#!/bin/bash
# Script para instalar el servicio systemd de SIPAC

echo "=========================================="
echo "Instalación de Servicio SIPAC"
echo "=========================================="

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar que se ejecuta con privilegios necesarios
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Este script necesita privilegios de superusuario${NC}"
    echo "Reejecutando con sudo..."
    sudo "$0" "$@"
    exit $?
fi

# Obtener el directorio actual
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${YELLOW}Directorio del proyecto: ${SCRIPT_DIR}${NC}"

# Verificar que existe el archivo de servicio
if [ ! -f "${SCRIPT_DIR}/sipac.service" ]; then
    echo -e "${RED}Error: No se encuentra sipac.service${NC}"
    exit 1
fi

# Copiar archivo de servicio
echo "Copiando archivo de servicio..."
cp "${SCRIPT_DIR}/sipac.service" /etc/systemd/system/sipac.service

# Recargar systemd
echo "Recargando systemd..."
systemctl daemon-reload

# Habilitar servicio
echo "Habilitando servicio para inicio automático..."
systemctl enable sipac.service

# Preguntar si iniciar ahora
read -p "¿Deseas iniciar el servicio ahora? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    echo "Iniciando servicio SIPAC..."
    systemctl start sipac.service

    sleep 2

    # Verificar estado
    if systemctl is-active --quiet sipac.service; then
        echo -e "${GREEN}✓ Servicio SIPAC iniciado correctamente${NC}"
        echo ""
        echo "Comandos útiles:"
        echo "  Ver estado:  sudo systemctl status sipac"
        echo "  Ver logs:    sudo journalctl -u sipac -f"
        echo "  Reiniciar:   sudo systemctl restart sipac"
        echo "  Detener:     sudo systemctl stop sipac"
    else
        echo -e "${RED}✗ Error al iniciar el servicio${NC}"
        echo "Ver logs con: sudo journalctl -u sipac -n 50"
        exit 1
    fi
else
    echo -e "${YELLOW}Servicio instalado pero no iniciado${NC}"
    echo "Para iniciarlo: sudo systemctl start sipac"
fi

echo ""
echo -e "${GREEN}=========================================="
echo "Instalación completada"
echo "==========================================${NC}"
