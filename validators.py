"""
Validadores de datos para SIPAC
Aseguran la integridad y validez de los datos de entrada
"""
import os
import re
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime


class ValidationError(Exception):
    """Excepción personalizada para errores de validación"""
    pass


class FileValidator:
    """Validador para archivos subidos"""

    ALLOWED_EXTENSIONS = {'.xlsx', '.xls'}
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB

    @classmethod
    def validate_file(cls, filename: str, file_size: Optional[int] = None) -> None:
        """
        Valida un archivo

        Args:
            filename: Nombre del archivo
            file_size: Tamaño del archivo en bytes (opcional)

        Raises:
            ValidationError: Si el archivo no es válido
        """
        if not filename:
            raise ValidationError("Nombre de archivo vacío")

        # Validar extensión
        ext = os.path.splitext(filename)[1].lower()
        if ext not in cls.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Extensión '{ext}' no permitida. "
                f"Extensiones válidas: {', '.join(cls.ALLOWED_EXTENSIONS)}"
            )

        # Validar tamaño si se proporciona
        if file_size is not None and file_size > cls.MAX_FILE_SIZE:
            max_mb = cls.MAX_FILE_SIZE / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            raise ValidationError(
                f"Archivo demasiado grande ({actual_mb:.1f} MB). "
                f"Tamaño máximo: {max_mb:.0f} MB"
            )

    @classmethod
    def validate_files(cls, filenames: List[str]) -> None:
        """
        Valida múltiples archivos

        Args:
            filenames: Lista de nombres de archivos

        Raises:
            ValidationError: Si algún archivo no es válido
        """
        if not filenames:
            raise ValidationError("No se proporcionaron archivos")

        for filename in filenames:
            cls.validate_file(filename)


class TransaccionValidator:
    """Validador para datos de transacciones"""

    @staticmethod
    def validate_cuenta_contable(cuenta: str) -> None:
        """
        Valida el formato de una cuenta contable

        Args:
            cuenta: Cuenta contable a validar

        Raises:
            ValidationError: Si la cuenta no es válida
        """
        if not cuenta:
            raise ValidationError("Cuenta contable no puede estar vacía")

        # Remover caracteres no alfanuméricos para validación
        cuenta_limpia = re.sub(r'[^0-9A-Z]', '', cuenta.upper())

        if len(cuenta_limpia) > 21:
            raise ValidationError(
                f"Cuenta contable demasiado larga ({len(cuenta_limpia)} caracteres). "
                "Máximo: 21 caracteres"
            )

    @staticmethod
    def validate_fecha(fecha: Any) -> None:
        """
        Valida una fecha

        Args:
            fecha: Fecha a validar (string, datetime, etc.)

        Raises:
            ValidationError: Si la fecha no es válida
        """
        if not fecha:
            raise ValidationError("Fecha no puede estar vacía")

        # Intentar convertir a datetime si es string
        if isinstance(fecha, str):
            try:
                # Intentar formatos comunes
                for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                    try:
                        datetime.strptime(fecha, fmt)
                        return
                    except ValueError:
                        continue

                raise ValueError("Formato no reconocido")

            except ValueError:
                raise ValidationError(
                    f"Fecha '{fecha}' no tiene un formato válido. "
                    "Formatos aceptados: DD/MM/YYYY, YYYY-MM-DD"
                )

    @staticmethod
    def validate_monto(monto: Any, campo: str = "monto") -> None:
        """
        Valida un monto monetario

        Args:
            monto: Monto a validar
            campo: Nombre del campo para mensajes de error

        Raises:
            ValidationError: Si el monto no es válido
        """
        if monto is None:
            raise ValidationError(f"{campo} no puede ser None")

        try:
            valor = float(monto)
            if valor < 0:
                raise ValidationError(f"{campo} no puede ser negativo")
        except (ValueError, TypeError):
            raise ValidationError(f"{campo} '{monto}' no es un número válido")


class FiltrosValidator:
    """Validador para filtros de búsqueda"""

    CAMPOS_VALIDOS = {
        'cuenta_contable', 'dependencia', 'poliza', 'fecha_inicio', 'fecha_fin',
        'genero', 'grupo', 'rubro', 'cuenta', 'subcuenta',
        'unidad_responsable', 'centro_costo', 'proyecto_presupuestario',
        'fuente', 'subfuente', 'tipo_recurso', 'partida_presupuestal',
        'nombre_cuenta', 'beneficiario', 'descripcion', 'orden_pago'
    }

    @classmethod
    def validate_filtros(cls, filtros: Dict[str, Any]) -> None:
        """
        Valida un diccionario de filtros

        Args:
            filtros: Diccionario con filtros

        Raises:
            ValidationError: Si los filtros no son válidos
        """
        if not isinstance(filtros, dict):
            raise ValidationError("Los filtros deben ser un diccionario")

        # Validar que los campos sean reconocidos
        campos_invalidos = set(filtros.keys()) - cls.CAMPOS_VALIDOS
        if campos_invalidos:
            raise ValidationError(
                f"Campos de filtro no válidos: {', '.join(campos_invalidos)}"
            )

        # Validar fechas si están presentes
        if 'fecha_inicio' in filtros:
            TransaccionValidator.validate_fecha(filtros['fecha_inicio'])

        if 'fecha_fin' in filtros:
            TransaccionValidator.validate_fecha(filtros['fecha_fin'])

        # Validar que fecha_fin >= fecha_inicio
        if 'fecha_inicio' in filtros and 'fecha_fin' in filtros:
            try:
                inicio = datetime.fromisoformat(str(filtros['fecha_inicio']))
                fin = datetime.fromisoformat(str(filtros['fecha_fin']))

                if fin < inicio:
                    raise ValidationError(
                        "fecha_fin no puede ser anterior a fecha_inicio"
                    )
            except ValueError:
                # Las fechas ya fueron validadas individualmente
                pass

    @classmethod
    def validate_pagination(cls, page: int, per_page: int, max_per_page: int = 1000) -> None:
        """
        Valida parámetros de paginación

        Args:
            page: Número de página
            per_page: Registros por página
            max_per_page: Máximo de registros por página

        Raises:
            ValidationError: Si los parámetros no son válidos
        """
        if page < 1:
            raise ValidationError("page debe ser mayor o igual a 1")

        if per_page < 1:
            raise ValidationError("per_page debe ser mayor o igual a 1")

        if per_page > max_per_page:
            raise ValidationError(
                f"per_page no puede exceder {max_per_page}"
            )


class EnteValidator:
    """Validador para entidades públicas"""

    @staticmethod
    def validate_ente_data(data: Dict[str, Any], es_creacion: bool = True) -> None:
        """
        Valida datos de un ente

        Args:
            data: Diccionario con datos del ente
            es_creacion: Si es una creación (True) o actualización (False)

        Raises:
            ValidationError: Si los datos no son válidos
        """
        if not isinstance(data, dict):
            raise ValidationError("Los datos deben ser un diccionario")

        # Campos requeridos solo en creación
        if es_creacion:
            campos_requeridos = ['clave', 'codigo', 'nombre']

            for campo in campos_requeridos:
                if campo not in data or not data[campo]:
                    raise ValidationError(f"Campo '{campo}' es requerido")

        # Validar clave si está presente
        if 'clave' in data:
            clave = data['clave']
            if not clave or not str(clave).strip():
                raise ValidationError("La clave no puede estar vacía")

            if len(str(clave)) > 20:
                raise ValidationError(
                    f"La clave es demasiado larga ({len(str(clave))} caracteres). "
                    "Máximo: 20 caracteres"
                )

        # Validar nombre si está presente
        if 'nombre' in data:
            nombre = data['nombre']
            if not nombre or not str(nombre).strip():
                raise ValidationError("El nombre no puede estar vacío")

            if len(str(nombre)) > 255:
                raise ValidationError("El nombre es demasiado largo (máximo 255 caracteres)")

        # Validar ámbito si está presente
        if 'ambito' in data:
            ambitos_validos = ['ESTATAL', 'MUNICIPAL', 'FEDERAL']
            if data['ambito'] not in ambitos_validos:
                raise ValidationError(
                    f"Ámbito '{data['ambito']}' no válido. "
                    f"Valores válidos: {', '.join(ambitos_validos)}"
                )


def validate_request_data(
    data: Any,
    required_fields: Optional[List[str]] = None,
    optional_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Valida datos de una petición HTTP

    Args:
        data: Datos a validar
        required_fields: Campos requeridos
        optional_fields: Campos opcionales permitidos

    Returns:
        Diccionario con datos validados

    Raises:
        ValidationError: Si los datos no son válidos
    """
    if not data:
        raise ValidationError("No se proporcionaron datos")

    if not isinstance(data, dict):
        raise ValidationError("Los datos deben ser un objeto JSON")

    # Validar campos requeridos
    if required_fields:
        for field in required_fields:
            if field not in data or data[field] is None:
                raise ValidationError(f"Campo '{field}' es requerido")

    # Validar que solo se envíen campos permitidos
    if required_fields or optional_fields:
        allowed = set(required_fields or []) | set(optional_fields or [])
        extra_fields = set(data.keys()) - allowed

        if extra_fields:
            raise ValidationError(
                f"Campos no permitidos: {', '.join(extra_fields)}"
            )

    return data


def safe_int(value: Any, default: int = 0, min_value: Optional[int] = None) -> int:
    """
    Convierte un valor a entero de forma segura

    Args:
        value: Valor a convertir
        default: Valor por defecto si falla la conversión
        min_value: Valor mínimo permitido

    Returns:
        Valor convertido a entero
    """
    try:
        result = int(value)
        if min_value is not None and result < min_value:
            return default
        return result
    except (ValueError, TypeError):
        return default
