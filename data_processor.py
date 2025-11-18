"""
Procesador de datos para SIPAC - Versión refactorizada
Maneja el procesamiento de archivos Excel y carga a base de datos
"""
import pandas as pd
import uuid
from typing import List, Tuple, Callable, Optional
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

from models import db, Transaccion, LoteCarga
from excel_parser import ExcelParser
from utils import (
    extract_cuenta_components, to_numeric_series,
    setup_logger, ProgressReporter
)


logger = setup_logger(__name__)


class DataProcessor:
    """Procesador principal de datos de SIPAC"""

    def __init__(self, chunk_size: int = 1000, max_workers: int = 4):
        """
        Inicializa el procesador

        Args:
            chunk_size: Tamaño de lote para inserción en BD
            max_workers: Número máximo de workers para procesamiento paralelo
        """
        self.chunk_size = chunk_size
        self.max_workers = max_workers
        self.excel_parser = ExcelParser()

    def read_excel_files(
        self,
        file_list: List[Tuple[str, BytesIO]],
        progress: ProgressReporter
    ) -> Tuple[List[pd.DataFrame], List[str], List[str]]:
        """
        Lee múltiples archivos Excel en paralelo

        Args:
            file_list: Lista de tuplas (filename, file_content)
            progress: Reporter de progreso

        Returns:
            Tupla (dataframes, archivos_exitosos, archivos_fallidos)
        """
        progress.report(5, f"Leyendo {len(file_list)} archivo(s)...")

        frames = []
        archivos_exitosos = []
        archivos_fallidos = []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(file_list))) as executor:
            futures = {
                executor.submit(self.excel_parser.parse_excel_file, f): f
                for f in file_list
            }

            for future in as_completed(futures):
                try:
                    df, filename = future.result()

                    if not df.empty:
                        df['archivo_origen'] = filename
                        frames.append(df)
                        archivos_exitosos.append(filename)
                        progress.info(f"✓ Procesado: {filename}")
                    else:
                        archivos_fallidos.append(filename)
                        progress.warning(f"✗ Sin datos: {filename}")

                except Exception as e:
                    file_info = futures[future]
                    archivos_fallidos.append(file_info[0])
                    progress.error(f"Error en {file_info[0]}: {type(e).__name__} - {str(e)}")
                    logger.error(traceback.format_exc())

        progress.info(f"Resumen: {len(archivos_exitosos)} exitosos, {len(archivos_fallidos)} fallidos")
        return frames, archivos_exitosos, archivos_fallidos

    def process_cuenta_components(self, df: pd.DataFrame, progress: ProgressReporter) -> pd.DataFrame:
        """
        Procesa y extrae componentes de cuentas contables

        Args:
            df: DataFrame con transacciones
            progress: Reporter de progreso

        Returns:
            DataFrame con componentes agregados
        """
        progress.report(30, "Extrayendo componentes de cuentas contables...")

        # Extraer componentes
        componentes = df["cuenta_contable"].apply(extract_cuenta_components)

        # Agregar columnas
        for key in ["genero", "grupo", "rubro", "cuenta", "subcuenta",
                    "dependencia", "unidad_responsable", "centro_costo",
                    "proyecto_presupuestario", "fuente", "subfuente",
                    "tipo_recurso", "partida_presupuestal"]:
            df[key] = componentes.apply(lambda x: x[key])

        return df

    def process_monetary_columns(self, df: pd.DataFrame, progress: ProgressReporter) -> pd.DataFrame:
        """
        Convierte columnas monetarias a valores numéricos

        Args:
            df: DataFrame con transacciones
            progress: Reporter de progreso

        Returns:
            DataFrame con valores numéricos
        """
        progress.report(50, "Convirtiendo valores monetarios...")

        df["saldo_inicial"] = to_numeric_series(df["saldo_inicial"])
        df["cargos"] = to_numeric_series(df["cargos"])
        df["abonos"] = to_numeric_series(df["abonos"])

        return df

    def calculate_running_balances(self, df: pd.DataFrame, progress: ProgressReporter) -> pd.DataFrame:
        """
        Calcula saldos finales acumulativos por cuenta

        Args:
            df: DataFrame con transacciones
            progress: Reporter de progreso

        Returns:
            DataFrame con saldos calculados
        """
        progress.report(65, "Calculando saldos acumulativos...")

        df["saldo_final"] = 0.0

        # Procesar por cuenta
        for cuenta in df["cuenta_contable"].unique():
            mask = df["cuenta_contable"] == cuenta
            indices = df[mask].index

            saldo_actual = 0.0
            for i, idx in enumerate(indices):
                if i == 0:
                    # Primera transacción de la cuenta
                    saldo_actual = (
                        df.loc[idx, "saldo_inicial"] +
                        df.loc[idx, "cargos"] -
                        df.loc[idx, "abonos"]
                    )
                else:
                    # Transacciones subsecuentes
                    df.loc[idx, "saldo_inicial"] = saldo_actual
                    saldo_actual = (
                        saldo_actual +
                        df.loc[idx, "cargos"] -
                        df.loc[idx, "abonos"]
                    )

                df.loc[idx, "saldo_final"] = saldo_actual

        return df

    def process_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convierte columnas de fecha a datetime

        Args:
            df: DataFrame con transacciones

        Returns:
            DataFrame con fechas procesadas
        """
        df["fecha_transaccion"] = pd.to_datetime(
            df["fecha"],
            format="%d/%m/%Y",
            errors="coerce"
        )
        return df

    def save_to_database(
        self,
        df: pd.DataFrame,
        lote_id: str,
        usuario: str,
        progress: ProgressReporter
    ) -> int:
        """
        Guarda transacciones en base de datos en lotes

        Args:
            df: DataFrame con transacciones
            lote_id: ID del lote de carga
            usuario: Usuario que realiza la carga
            progress: Reporter de progreso

        Returns:
            Número total de registros insertados
        """
        progress.report(80, f"Insertando {len(df):,} registros en base de datos...")

        total_insertados = 0

        for i in range(0, len(df), self.chunk_size):
            chunk = df.iloc[i:i+self.chunk_size]

            # Crear objetos Transaccion
            transacciones = []
            for _, row in chunk.iterrows():
                trans = Transaccion(
                    lote_id=lote_id,
                    archivo_origen=row['archivo_origen'],
                    usuario_carga=usuario,
                    cuenta_contable=row['cuenta_contable'],
                    nombre_cuenta=row['nombre_cuenta'],
                    genero=row['genero'],
                    grupo=row['grupo'],
                    rubro=row['rubro'],
                    cuenta=row['cuenta'],
                    subcuenta=row['subcuenta'],
                    dependencia=row['dependencia'],
                    unidad_responsable=row['unidad_responsable'],
                    centro_costo=row['centro_costo'],
                    proyecto_presupuestario=row['proyecto_presupuestario'],
                    fuente=row['fuente'],
                    subfuente=row['subfuente'],
                    tipo_recurso=row['tipo_recurso'],
                    partida_presupuestal=row['partida_presupuestal'],
                    fecha_transaccion=row['fecha_transaccion'],
                    poliza=row['poliza'],
                    beneficiario=row['beneficiario'],
                    descripcion=row['descripcion'],
                    orden_pago=row['orden_pago'],
                    saldo_inicial=row['saldo_inicial'],
                    cargos=row['cargos'],
                    abonos=row['abonos'],
                    saldo_final=row['saldo_final']
                )
                transacciones.append(trans)

            # Insertar en BD
            try:
                db.session.bulk_save_objects(transacciones)
                db.session.commit()
                logger.debug(f"Lote {i//self.chunk_size + 1} insertado ({len(chunk)} registros)")
            except Exception as e:
                logger.error(f"Error en inserción lote {i//self.chunk_size + 1}: {type(e).__name__} - {str(e)}")
                logger.error(traceback.format_exc())
                db.session.rollback()
                raise

            total_insertados += len(chunk)
            progress_pct = 80 + int((total_insertados / len(df)) * 15)
            progress.report(progress_pct, f"Insertados {total_insertados:,} de {len(df):,} registros")

        return total_insertados

    def process_files_to_database(
        self,
        file_list: List[Tuple[str, BytesIO]],
        usuario: str = "sistema",
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[str, int]:
        """
        Procesa archivos Excel y guarda en base de datos

        Args:
            file_list: Lista de tuplas (filename, file_content)
            usuario: Usuario que realiza la carga
            progress_callback: Función callback para progreso

        Returns:
            Tupla (lote_id, total_registros)

        Raises:
            ValueError: Si no se puede procesar ningún archivo
            Exception: Para otros errores durante el procesamiento
        """
        progress = ProgressReporter(progress_callback)
        lote_id = str(uuid.uuid4())

        # Crear registro de lote
        lote = LoteCarga(
            lote_id=lote_id,
            usuario=usuario,
            archivos=[f[0] for f in file_list],
            estado='procesando'
        )
        db.session.add(lote)
        db.session.commit()

        try:
            logger.info(f"Iniciando procesamiento de {len(file_list)} archivo(s)")

            # 1. Leer archivos Excel
            frames, archivos_exitosos, archivos_fallidos = self.read_excel_files(
                file_list, progress
            )

            if not frames:
                error_msg = f'No se procesó ningún archivo. Fallidos: {", ".join(archivos_fallidos)}'
                logger.error(error_msg)
                lote.estado = 'error'
                lote.mensaje = error_msg
                db.session.commit()
                raise ValueError(error_msg)

            # 2. Concatenar DataFrames
            df = pd.concat(frames, ignore_index=True)
            progress.info(f"Total de transacciones extraídas: {len(df):,}")

            # 3. Procesar componentes de cuenta
            df = self.process_cuenta_components(df, progress)

            # 4. Convertir valores monetarios
            df = self.process_monetary_columns(df, progress)

            # 5. Calcular saldos acumulativos
            df = self.calculate_running_balances(df, progress)

            # 6. Procesar fechas
            df = self.process_dates(df)

            # 7. Guardar en base de datos
            total_registros = self.save_to_database(df, lote_id, usuario, progress)

            # 8. Actualizar lote
            lote.total_registros = total_registros
            lote.estado = 'completado'
            lote.mensaje = (
                f'Procesados {total_registros:,} registros de {len(archivos_exitosos)} archivos. '
                f'Archivos exitosos: {", ".join(archivos_exitosos)}'
            )
            db.session.commit()

            progress.report(100, f"✅ Completado: {total_registros:,} registros guardados")
            logger.info(f"✓ Procesamiento completado: {total_registros:,} registros, lote_id={lote_id}")

            return lote_id, total_registros

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error fatal en procesamiento: {error_msg}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")

            lote.estado = 'error'
            lote.mensaje = error_msg
            db.session.commit()
            raise


# Función de compatibilidad con código existente
def process_files_to_database(
    file_list: List[Tuple[str, BytesIO]],
    usuario: str = "sistema",
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[str, int]:
    """
    Función wrapper para mantener compatibilidad con código existente

    Args:
        file_list: Lista de tuplas (filename, file_content)
        usuario: Usuario que realiza la carga
        progress_callback: Función callback para progreso

    Returns:
        Tupla (lote_id, total_registros)
    """
    processor = DataProcessor()
    return processor.process_files_to_database(file_list, usuario, progress_callback)
