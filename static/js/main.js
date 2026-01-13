/**
 * SIIF - Sistema de Procesamiento de Auxiliares Contables
 * JavaScript principal
 */

// ========== Utilidades de Formato ==========

/**
 * Formatea un número como moneda mexicana
 * @param {number} num - El número a formatear
 * @returns {string} Número formateado como moneda
 */
function formatNumber(num) {
    return new Intl.NumberFormat('es-MX', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(num);
}

/**
 * Formatea el tamaño de un archivo
 * @param {number} bytes - Tamaño en bytes
 * @returns {string} Tamaño formateado (B, KB, MB)
 */
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

/**
 * Formatea una fecha en formato local
 * @param {string|Date} date - Fecha a formatear
 * @param {object} options - Opciones de formato
 * @returns {string} Fecha formateada
 */
function formatDate(date, options = { year: 'numeric', month: 'short', day: 'numeric' }) {
    if (typeof date === 'string') {
        date = new Date(date);
    }
    return date.toLocaleDateString('es-MX', options);
}

// ========== Manejo de Mensajes ==========

/**
 * Muestra un mensaje al usuario
 * @param {string} elementId - ID del elemento donde mostrar el mensaje
 * @param {string} message - Mensaje a mostrar
 * @param {string} type - Tipo de mensaje (success, error, info)
 */
function showMessage(elementId, message, type = 'info') {
    const element = document.getElementById(elementId);
    if (!element) return;

    element.className = `status-message ${type}`;
    element.textContent = message;
    element.style.display = 'block';
}

/**
 * Oculta un mensaje
 * @param {string} elementId - ID del elemento a ocultar
 */
function hideMessage(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = 'none';
    }
}

// ========== Manejo de API ==========

/**
 * Realiza una petición GET a la API
 * @param {string} endpoint - Endpoint de la API
 * @param {object} params - Parámetros de consulta
 * @returns {Promise<object>} Respuesta de la API
 */
async function apiGet(endpoint, params = {}) {
    const url = new URL(endpoint, window.location.origin);
    Object.keys(params).forEach(key => {
        if (params[key] !== null && params[key] !== undefined && params[key] !== '') {
            url.searchParams.append(key, params[key]);
        }
    });

    const response = await fetch(url);
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Error ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

/**
 * Realiza una petición POST a la API
 * @param {string} endpoint - Endpoint de la API
 * @param {object} data - Datos a enviar
 * @returns {Promise<object>} Respuesta de la API
 */
async function apiPost(endpoint, data) {
    const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Error ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

/**
 * Realiza una petición POST multipart (para archivos)
 * @param {string} endpoint - Endpoint de la API
 * @param {FormData} formData - FormData con archivos
 * @returns {Promise<object>} Respuesta de la API
 */
async function apiPostFile(endpoint, formData) {
    const response = await fetch(endpoint, {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Error ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

// ========== Utilidades de Validación ==========

/**
 * Valida que un campo no esté vacío
 * @param {string} value - Valor a validar
 * @returns {boolean} True si es válido
 */
function isNotEmpty(value) {
    return value !== null && value !== undefined && value.trim() !== '';
}

/**
 * Valida que un valor sea una fecha válida
 * @param {string} dateString - Fecha en formato string
 * @returns {boolean} True si es válida
 */
function isValidDate(dateString) {
    const date = new Date(dateString);
    return date instanceof Date && !isNaN(date);
}

/**
 * Valida que un archivo sea Excel
 * @param {File} file - Archivo a validar
 * @returns {boolean} True si es Excel
 */
function isExcelFile(file) {
    return file.name.endsWith('.xlsx') || file.name.endsWith('.xls');
}

// ========== Utilidades de UI ==========

/**
 * Muestra/oculta un elemento por ID
 * @param {string} elementId - ID del elemento
 * @param {boolean} show - True para mostrar, false para ocultar
 */
function toggleElement(elementId, show) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = show ? 'block' : 'none';
    }
}

/**
 * Habilita/deshabilita un botón
 * @param {string} buttonId - ID del botón
 * @param {boolean} enabled - True para habilitar
 */
function toggleButton(buttonId, enabled) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = !enabled;
    }
}

/**
 * Scroll suave a un elemento
 * @param {string} elementId - ID del elemento
 */
function scrollToElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

/**
 * Limpia el contenido de un elemento
 * @param {string} elementId - ID del elemento
 */
function clearElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = '';
    }
}

// ========== Utilidades de Tabla ==========

/**
 * Crea una fila de tabla con datos
 * @param {Array<string>} data - Array con los datos de cada celda
 * @param {Array<string>} classes - Array opcional con clases CSS para cada celda
 * @returns {HTMLTableRowElement} Fila de tabla creada
 */
function createTableRow(data, classes = []) {
    const row = document.createElement('tr');
    data.forEach((cellData, index) => {
        const cell = document.createElement('td');
        cell.innerHTML = cellData;
        if (classes[index]) {
            cell.className = classes[index];
        }
        row.appendChild(cell);
    });
    return row;
}

/**
 * Limpia el tbody de una tabla
 * @param {string} tableId - ID de la tabla
 */
function clearTableBody(tableId) {
    const table = document.getElementById(tableId);
    if (table) {
        const tbody = table.querySelector('tbody');
        if (tbody) {
            tbody.innerHTML = '';
        }
    }
}

// ========== Utilidades de Descarga ==========

/**
 * Descarga un blob como archivo
 * @param {Blob} blob - Blob a descargar
 * @param {string} filename - Nombre del archivo
 */
function downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

/**
 * Descarga un archivo Excel desde un endpoint
 * @param {string} endpoint - URL del endpoint
 * @param {object} data - Datos a enviar
 * @param {string} filename - Nombre del archivo
 */
async function downloadExcelReport(endpoint, data, filename) {
    const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || 'Error al generar reporte');
    }

    const blob = await response.blob();
    downloadBlob(blob, filename);
}

// ========== Utilidades de Fecha ==========

/**
 * Obtiene la fecha de hace N días
 * @param {number} days - Número de días
 * @returns {string} Fecha en formato YYYY-MM-DD
 */
function getDateNDaysAgo(days) {
    const date = new Date();
    date.setDate(date.getDate() - days);
    return date.toISOString().split('T')[0];
}

/**
 * Obtiene la fecha actual en formato YYYY-MM-DD
 * @returns {string} Fecha actual
 */
function getTodayDate() {
    return new Date().toISOString().split('T')[0];
}

/**
 * Obtiene el primer día del mes actual
 * @returns {string} Fecha en formato YYYY-MM-DD
 */
function getFirstDayOfMonth() {
    const date = new Date();
    return new Date(date.getFullYear(), date.getMonth(), 1).toISOString().split('T')[0];
}

/**
 * Obtiene el primer día del año actual
 * @returns {string} Fecha en formato YYYY-MM-DD
 */
function getFirstDayOfYear() {
    const date = new Date();
    return new Date(date.getFullYear(), 0, 1).toISOString().split('T')[0];
}

// ========== Event Listeners Globales ==========

// Prevenir el submit de formularios por defecto si no se especifica lo contrario
document.addEventListener('DOMContentLoaded', () => {
    console.log('SIIF - Sistema de Procesamiento de Auxiliares Contables');
    console.log('JavaScript principal cargado correctamente');
});

// Manejo global de errores de red
window.addEventListener('online', () => {
    console.log('Conexión restaurada');
});

window.addEventListener('offline', () => {
    console.warn('Sin conexión a internet');
    alert('Se ha perdido la conexión a internet. Algunas funciones pueden no estar disponibles.');
});
