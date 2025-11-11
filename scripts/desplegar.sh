#!/bin/bash
# Script maestro de despliegue de SIPAC
# Este script ejecuta todos los pasos necesarios para desplegar la aplicación

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ███████╗██╗██████╗  █████╗  ██████╗                    ║
║   ██╔════╝██║██╔══██╗██╔══██╗██╔════╝                    ║
║   ███████╗██║██████╔╝███████║██║                         ║
║   ╚════██║██║██╔═══╝ ██╔══██║██║                         ║
║   ███████║██║██║     ██║  ██║╚██████╗                    ║
║   ╚══════╝╚═╝╚═╝     ╚═╝  ╚═╝ ╚═════╝                    ║
║                                                           ║
║   Sistema de Procesamiento de Auxiliares Contables       ║
║   Script de Despliegue Automático                        ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo ""
echo "Este script configurará SIPAC desde cero."
echo ""

# Verificar sistema
echo -e "${BLUE}[1/8] Verificando sistema operativo...${NC}"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "Sistema: $NAME $VERSION"
else
    echo -e "${YELLOW}No se pudo detectar el sistema operativo${NC}"
fi
echo ""

# Verificar dependencias del sistema
echo -e "${BLUE}[2/8] Verificando dependencias del sistema...${NC}"

command -v python3 >/dev/null 2>&1 || {
    echo -e "${RED}Python 3 no está instalado${NC}"
    echo "Instálalo con: sudo apt install python3"
    exit 1
}

command -v psql >/dev/null 2>&1 || {
    echo -e "${YELLOW}PostgreSQL no está instalado${NC}"
    read -p "¿Deseas instalarlo ahora? (s/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        echo "Instalando PostgreSQL..."
        sudo apt update
        sudo apt install -y postgresql postgresql-contrib
    else
        echo "PostgreSQL es requerido. Saliendo..."
        exit 1
    fi
}

echo -e "${GREEN}✓ Dependencias del sistema OK${NC}"
echo ""

# Configurar PostgreSQL
echo -e "${BLUE}[3/8] Configurando PostgreSQL...${NC}"
if [ -f "$SCRIPT_DIR/setup_postgresql.sh" ]; then
    chmod +x "$SCRIPT_DIR/setup_postgresql.sh"
    bash "$SCRIPT_DIR/setup_postgresql.sh"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al configurar PostgreSQL${NC}"
        exit 1
    fi
else
    echo -e "${RED}No se encuentra setup_postgresql.sh${NC}"
    exit 1
fi
echo ""

# Crear entorno virtual
echo -e "${BLUE}[4/8] Configurando entorno virtual de Python...${NC}"
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv "$SCRIPT_DIR/venv"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al crear entorno virtual${NC}"
        exit 1
    fi
else
    echo "Entorno virtual ya existe"
fi

# Activar y actualizar pip
source "$SCRIPT_DIR/venv/bin/activate"
pip install --upgrade pip setuptools wheel
echo -e "${GREEN}✓ Entorno virtual configurado${NC}"
echo ""

# Instalar dependencias
echo -e "${BLUE}[5/8] Instalando dependencias de Python...${NC}"
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    pip install -r "$SCRIPT_DIR/requirements.txt"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al instalar dependencias${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Dependencias instaladas${NC}"
else
    echo -e "${RED}No se encuentra requirements.txt${NC}"
    exit 1
fi
echo ""

# Inicializar base de datos
echo -e "${BLUE}[6/8] Inicializando tablas de la base de datos...${NC}"
python << EOF
from app_mejorado import create_app
from models import db

app = create_app()
with app.app_context():
    db.create_all()
    print("Tablas creadas exitosamente")
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}Error al crear tablas${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Base de datos inicializada${NC}"
echo ""

# Configurar servicio systemd
echo -e "${BLUE}[7/8] Configurando servicio systemd...${NC}"
read -p "¿Deseas instalar SIPAC como servicio systemd? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    if [ -f "$SCRIPT_DIR/install_service.sh" ]; then
        chmod +x "$SCRIPT_DIR/install_service.sh"
        sudo bash "$SCRIPT_DIR/install_service.sh"
    else
        echo -e "${YELLOW}No se encuentra install_service.sh${NC}"
    fi
else
    echo "Servicio systemd no configurado"
fi
echo ""

# Configurar respaldos
echo -e "${BLUE}[8/8] Configurando respaldos automáticos...${NC}"
read -p "¿Deseas configurar respaldos automáticos? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    if [ -f "$SCRIPT_DIR/setup_backup_cron.sh" ]; then
        chmod +x "$SCRIPT_DIR/setup_backup_cron.sh"
        bash "$SCRIPT_DIR/setup_backup_cron.sh"
    else
        echo -e "${YELLOW}No se encuentra setup_backup_cron.sh${NC}"
    fi
else
    echo "Respaldos no configurados"
fi
echo ""

# Verificar sistema
echo -e "${BLUE}Ejecutando verificación del sistema...${NC}"
if [ -f "$SCRIPT_DIR/verificar_sistema.sh" ]; then
    chmod +x "$SCRIPT_DIR/verificar_sistema.sh"
    bash "$SCRIPT_DIR/verificar_sistema.sh"
fi
echo ""

# Resumen
echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║              ¡Despliegue Completado! 🎉                   ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo ""
echo "Próximos pasos:"
echo ""
echo "1. Iniciar la aplicación:"
echo "   Si instalaste el servicio systemd:"
echo "     sudo systemctl start sipac"
echo "     sudo systemctl status sipac"
echo ""
echo "   O manualmente:"
echo "     source venv/bin/activate"
echo "     python app_mejorado.py"
echo ""
echo "2. Acceder a la aplicación:"
echo "   - Carga de archivos:  http://localhost:4095"
echo "   - Dashboard:          http://localhost:4095/dashboard"
echo "   - Reportes:           http://localhost:4095/reportes"
echo ""
echo "3. Ver logs:"
echo "   Con systemd: sudo journalctl -u sipac -f"
echo "   Manual: ver output en la terminal"
echo ""
echo "4. Scripts útiles:"
echo "   - Verificar sistema: ./verificar_sistema.sh"
echo "   - Backup manual: ./backup_sipac.sh"
echo "   - Restaurar backup: ./restaurar_backup.sh"
echo "   - Migrar datos: python migrar_datos.py migrar /ruta/archivos"
echo ""
echo "Documentación completa: README.md"
echo ""
