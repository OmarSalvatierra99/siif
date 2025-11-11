#!/bin/bash
# Script para desarrollo local - inicia la aplicación en modo desarrollo

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=========================================="
echo "SIPAC - Modo Desarrollo"
echo "==========================================${NC}"
echo ""

# Verificar entorno virtual
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo -e "${YELLOW}Entorno virtual no encontrado. Creando...${NC}"
    python3 -m venv "$SCRIPT_DIR/venv"
    source "$SCRIPT_DIR/venv/bin/activate"
    pip install --upgrade pip
    pip install -r "$SCRIPT_DIR/requirements.txt"
else
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Verificar .env
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${YELLOW}Archivo .env no encontrado${NC}"
    echo "Creando .env con valores por defecto..."
    cat > "$SCRIPT_DIR/.env" << EOF
DATABASE_URL=postgresql://sipac_user:sipac_password@localhost:5432/sipac_db
SECRET_KEY=$(openssl rand -hex 32)
FLASK_ENV=development
EOF
    echo -e "${GREEN}✓ Archivo .env creado${NC}"
fi

# Verificar PostgreSQL
if ! systemctl is-active --quiet postgresql; then
    echo -e "${YELLOW}PostgreSQL no está corriendo. Intentando iniciar...${NC}"
    sudo systemctl start postgresql
fi

# Exportar variables de entorno
export FLASK_ENV=development
export $(cat "$SCRIPT_DIR/.env" | xargs)

echo ""
echo "Configuración:"
echo "  Modo: development"
echo "  Puerto: 4095"
echo "  Base de datos: $(echo $DATABASE_URL | sed 's/:[^@]*@/:***@/')"
echo ""
echo -e "${GREEN}Iniciando aplicación...${NC}"
echo "Presiona Ctrl+C para detener"
echo ""
echo "URLs disponibles:"
echo "  - http://localhost:4095          (Carga de archivos)"
echo "  - http://localhost:4095/dashboard (Dashboard)"
echo "  - http://localhost:4095/reportes  (Reportes)"
echo ""
echo "----------------------------------------"
echo ""

# Iniciar aplicación
cd "$SCRIPT_DIR"
python app_mejorado.py
