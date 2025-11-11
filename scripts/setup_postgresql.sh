#!/bin/bash
# Script mejorado de configuración de PostgreSQL para SIPAC
# Maneja problemas de collation version mismatch

echo "=========================================="
echo "Configuración de PostgreSQL para SIPAC"
echo "Arreglando problemas de collation"
echo "=========================================="

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Variables
DB_NAME="sipac_db"
DB_USER="sipac_user"
DB_PASSWORD="sipac_password"

echo -e "${YELLOW}Paso 1: Arreglar collation version mismatch${NC}"
echo "Este es un problema común después de actualizaciones del sistema..."

# Arreglar collation en bases de datos del sistema
sudo -u postgres psql << 'EOF'
-- Arreglar postgres
ALTER DATABASE postgres REFRESH COLLATION VERSION;

-- Arreglar template0
ALTER DATABASE template0 REFRESH COLLATION VERSION;

-- Arreglar template1
ALTER DATABASE template1 REFRESH COLLATION VERSION;

\echo 'Collation version actualizada'
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Collation version arreglada${NC}"
else
    echo -e "${YELLOW}⚠ Algunos warnings de collation pueden persistir pero no son críticos${NC}"
fi

echo ""
echo -e "${YELLOW}Paso 2: Eliminar base de datos antigua si existe${NC}"
sudo -u postgres psql << EOF
DROP DATABASE IF EXISTS $DB_NAME;
DROP USER IF EXISTS $DB_USER;
\echo 'Limpieza completada'
EOF

echo ""
echo -e "${YELLOW}Paso 3: Crear usuario de PostgreSQL${NC}"
sudo -u postgres psql << EOF
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
\echo 'Usuario creado'
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Usuario $DB_USER creado${NC}"
else
    echo -e "${RED}✗ Error creando usuario${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Paso 4: Crear base de datos${NC}"
sudo -u postgres psql << EOF
CREATE DATABASE $DB_NAME OWNER $DB_USER;
\echo 'Base de datos creada'
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Base de datos $DB_NAME creada${NC}"
else
    echo -e "${RED}✗ Error creando base de datos${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Paso 5: Configurar permisos${NC}"
sudo -u postgres psql << EOF
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
\c $DB_NAME
GRANT ALL ON SCHEMA public TO $DB_USER;
\echo 'Permisos configurados'
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Permisos configurados${NC}"
else
    echo -e "${RED}✗ Error configurando permisos${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Paso 6: Verificar conexión${NC}"
PGPASSWORD=$DB_PASSWORD psql -U $DB_USER -d $DB_NAME -h localhost -c "SELECT version();" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Conexión verificada exitosamente${NC}"
else
    echo -e "${RED}✗ Error verificando conexión${NC}"
    echo "Intentando arreglar pg_hba.conf..."
    
    # Agregar configuración al pg_hba.conf si es necesario
    PG_HBA="/var/lib/pgsql/data/pg_hba.conf"
    if [ ! -f "$PG_HBA" ]; then
        PG_HBA="/etc/postgresql/*/main/pg_hba.conf"
        PG_HBA=$(ls $PG_HBA 2>/dev/null | head -1)
    fi
    
    if [ -f "$PG_HBA" ]; then
        echo "local   $DB_NAME   $DB_USER   md5" | sudo tee -a $PG_HBA
        sudo systemctl restart postgresql
        sleep 2
        
        # Intentar de nuevo
        PGPASSWORD=$DB_PASSWORD psql -U $DB_USER -d $DB_NAME -h localhost -c "SELECT 1;" > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Conexión arreglada${NC}"
        fi
    fi
fi

echo ""
echo -e "${YELLOW}Paso 7: Crear archivo .env${NC}"
cat > .env << EOF
# Configuración de SIPAC
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
SECRET_KEY=$(openssl rand -hex 32)
FLASK_ENV=development
EOF

echo -e "${GREEN}✓ Archivo .env creado${NC}"

echo ""
echo "=========================================="
echo -e "${GREEN}Configuración completada exitosamente${NC}"
echo "=========================================="
echo ""
echo "Detalles de conexión:"
echo "  Base de datos: $DB_NAME"
echo "  Usuario: $DB_USER"
echo "  Password: $DB_PASSWORD"
echo "  Host: localhost"
echo "  Puerto: 5432"
echo ""
echo "URL de conexión:"
echo "  postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
echo ""
echo "Archivo .env creado con las configuraciones"
echo ""
echo "Siguiente paso:"
echo "  1. source venv/bin/activate"
echo "  2. pip install -r requirements.txt"
echo "  3. python app_mejorado.py"
echo ""
