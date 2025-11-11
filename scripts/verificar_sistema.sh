#!/bin/bash
# Script de verificación del sistema SIPAC
# Verifica que todos los componentes estén funcionando correctamente

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

echo -e "${BLUE}=========================================="
echo "Verificación del Sistema SIPAC"
echo "==========================================${NC}"
echo ""

# Función para verificar y reportar
check() {
    local name="$1"
    local command="$2"
    local type="${3:-error}"  # error o warning

    echo -n "Verificando $name... "

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        if [ "$type" = "error" ]; then
            echo -e "${RED}✗${NC}"
            ERRORS=$((ERRORS + 1))
        else
            echo -e "${YELLOW}⚠${NC}"
            WARNINGS=$((WARNINGS + 1))
        fi
        return 1
    fi
}

# === VERIFICACIONES DEL SISTEMA ===
echo -e "${BLUE}[1] Sistema Operativo${NC}"
check "Python 3" "python3 --version" error
check "PostgreSQL" "psql --version" error
check "pip" "pip --version" warning

# Verificar versión de Python
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null)
if [ ! -z "$PYTHON_VERSION" ]; then
    echo "    Python versión: $PYTHON_VERSION"
    # Verificar que sea >= 3.8
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)"; then
        echo -e "    ${GREEN}Versión de Python es compatible${NC}"
    else
        echo -e "    ${RED}Se requiere Python 3.8 o superior${NC}"
        ERRORS=$((ERRORS + 1))
    fi
fi

echo ""

# === VERIFICACIONES DE POSTGRESQL ===
echo -e "${BLUE}[2] PostgreSQL${NC}"
check "Servicio PostgreSQL activo" "systemctl is-active postgresql" error

if systemctl is-active postgresql > /dev/null 2>&1; then
    # Verificar base de datos
    if PGPASSWORD=sipac_password psql -U sipac_user -d sipac_db -c '\q' 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Base de datos accesible"

        # Obtener estadísticas
        TRANS_COUNT=$(PGPASSWORD=sipac_password psql -U sipac_user -d sipac_db -t -c "SELECT COUNT(*) FROM transacciones;" 2>/dev/null | xargs)
        LOTES_COUNT=$(PGPASSWORD=sipac_password psql -U sipac_user -d sipac_db -t -c "SELECT COUNT(*) FROM lotes_carga;" 2>/dev/null | xargs)
        DB_SIZE=$(PGPASSWORD=sipac_password psql -U sipac_user -d sipac_db -t -c "SELECT pg_size_pretty(pg_database_size('sipac_db'));" 2>/dev/null | xargs)

        echo "    Transacciones: $TRANS_COUNT"
        echo "    Lotes cargados: $LOTES_COUNT"
        echo "    Tamaño de BD: $DB_SIZE"
    else
        echo -e "${RED}✗${NC} No se puede conectar a la base de datos"
        echo "    Verifica credenciales en .env"
        ERRORS=$((ERRORS + 1))
    fi
fi

echo ""

# === VERIFICACIONES DEL PROYECTO ===
echo -e "${BLUE}[3] Archivos del Proyecto${NC}"
PROJECT_DIR="/home/gabo/portfolio/projects/sipac"

check "Directorio del proyecto" "[ -d $PROJECT_DIR ]" error
check "app_mejorado.py" "[ -f $PROJECT_DIR/app_mejorado.py ]" error
check "models.py" "[ -f $PROJECT_DIR/models.py ]" error
check "data_processor.py" "[ -f $PROJECT_DIR/data_processor.py ]" error
check "config.py" "[ -f $PROJECT_DIR/config.py ]" error
check "requirements.txt" "[ -f $PROJECT_DIR/requirements.txt ]" error
check "Archivo .env" "[ -f $PROJECT_DIR/.env ]" error
check "Directorio templates/" "[ -d $PROJECT_DIR/templates ]" error
check "template index.html" "[ -f $PROJECT_DIR/templates/index.html ]" error
check "template dashboard.html" "[ -f $PROJECT_DIR/templates/dashboard.html ]" error
check "template reportes.html" "[ -f $PROJECT_DIR/templates/reportes.html ]" error

echo ""

# === VERIFICACIONES DEL ENTORNO VIRTUAL ===
echo -e "${BLUE}[4] Entorno Virtual${NC}"
check "Directorio venv" "[ -d $PROJECT_DIR/venv ]" error

if [ -d "$PROJECT_DIR/venv" ]; then
    check "Python en venv" "[ -f $PROJECT_DIR/venv/bin/python ]" error
    check "pip en venv" "[ -f $PROJECT_DIR/venv/bin/pip ]" error

    # Verificar dependencias instaladas
    echo ""
    echo "Verificando dependencias Python..."

    source "$PROJECT_DIR/venv/bin/activate" 2>/dev/null

    REQUIRED_PACKAGES=("Flask" "Flask-SQLAlchemy" "Flask-CORS" "psycopg2" "pandas" "openpyxl" "XlsxWriter")

    for package in "${REQUIRED_PACKAGES[@]}"; do
        if python -c "import ${package,,}" 2>/dev/null; then
            echo -e "${GREEN}✓${NC} $package instalado"
        else
            echo -e "${RED}✗${NC} $package NO instalado"
            ERRORS=$((ERRORS + 1))
        fi
    done

    deactivate 2>/dev/null
fi

echo ""

# === VERIFICACIONES DEL SERVICIO ===
echo -e "${BLUE}[5] Servicio SIPAC${NC}"

if [ -f "/etc/systemd/system/sipac.service" ]; then
    echo -e "${GREEN}✓${NC} Archivo de servicio existe"

    if systemctl is-enabled sipac > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Servicio habilitado para inicio automático"
    else
        echo -e "${YELLOW}⚠${NC} Servicio NO habilitado para inicio automático"
        WARNINGS=$((WARNINGS + 1))
    fi

    if systemctl is-active sipac > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Servicio activo y ejecutándose"
    else
        echo -e "${YELLOW}⚠${NC} Servicio NO está ejecutándose"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠${NC} Servicio systemd no instalado"
    echo "    Ejecuta: sudo ./install_service.sh"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# === VERIFICACIONES DE RED ===
echo -e "${BLUE}[6] Conectividad${NC}"

# Verificar si el puerto está en uso
if netstat -tuln 2>/dev/null | grep -q ":4095 "; then
    echo -e "${GREEN}✓${NC} Puerto 4095 en uso (aplicación corriendo)"

    # Intentar hacer una petición HTTP
    if curl -s http://localhost:4095 > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Aplicación responde en http://localhost:4095"
    else
        echo -e "${YELLOW}⚠${NC} Puerto abierto pero aplicación no responde"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠${NC} Puerto 4095 no está en uso"
    echo "    La aplicación no está ejecutándose"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# === VERIFICACIONES DE RESPALDOS ===
echo -e "${BLUE}[7] Sistema de Respaldos${NC}"

check "Script de backup" "[ -f $PROJECT_DIR/backup_sipac.sh ]" warning
check "Directorio de backups" "[ -d /home/gabo/backups/sipac ]" warning

if [ -d "/home/gabo/backups/sipac" ]; then
    BACKUP_COUNT=$(ls -1 /home/gabo/backups/sipac/sipac_*.backup 2>/dev/null | wc -l)
    echo "    Respaldos disponibles: $BACKUP_COUNT"

    if [ $BACKUP_COUNT -gt 0 ]; then
        LATEST_BACKUP=$(ls -t /home/gabo/backups/sipac/sipac_*.backup 2>/dev/null | head -1)
        BACKUP_DATE=$(stat -c %y "$LATEST_BACKUP" 2>/dev/null | cut -d' ' -f1)
        echo "    Último respaldo: $BACKUP_DATE"
    fi
fi

# Verificar cron
if crontab -l 2>/dev/null | grep -q "backup_sipac.sh"; then
    echo -e "${GREEN}✓${NC} Respaldo automático configurado en cron"
else
    echo -e "${YELLOW}⚠${NC} Respaldo automático NO configurado"
    echo "    Ejecuta: ./setup_backup_cron.sh"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# === RESUMEN ===
echo -e "${BLUE}=========================================="
echo "Resumen de Verificación"
echo "==========================================${NC}"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ Sistema completamente funcional${NC}"
    echo "Todo está configurado correctamente."
    EXIT_CODE=0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ Sistema funcional con advertencias${NC}"
    echo "Advertencias: $WARNINGS"
    echo "El sistema funciona pero hay configuraciones opcionales pendientes."
    EXIT_CODE=0
else
    echo -e "${RED}✗ Sistema con errores${NC}"
    echo "Errores críticos: $ERRORS"
    echo "Advertencias: $WARNINGS"
    echo ""
    echo "Revisa los errores y ejecuta las correcciones necesarias."
    EXIT_CODE=1
fi

echo ""
echo "Comandos útiles:"
echo "  Ver logs de PostgreSQL: sudo tail -f /var/log/postgresql/postgresql-*.log"
echo "  Ver logs de SIPAC: sudo journalctl -u sipac -f"
echo "  Reiniciar servicio: sudo systemctl restart sipac"
echo "  Ver estado: sudo systemctl status sipac"
echo ""

exit $EXIT_CODE
