"""
Servicio principal de procesamiento de datos
"""
import pandas as pd
import uuid
import traceback
from typing import List, Tuple, Callable, Optional
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.logging_config import get_logger
from app.models import db, Transaccion, LoteCarga
from app.services.excel_reader import ExcelReader
from app.utils.excel_parser import parse_cuenta_contable
from app.utils.helpers import to_numeric_fast

logger = get_logger('app.services.data_processor')


class DataProcessor:
    """
    Procesador principal de archivos Excel para SIPAC

    Coordina:
    - Lectura paralela de archivos Excel
    - Descomposición de cuentas contables
    - Cálculo de saldos acumulativos
    - Inserción en base de datos por lotes
    - Reportes de progreso
    """

    def __init__(self, max_workers=4, chunk_size=1000):
        """
        Inicializa el procesador de datos

        Args:
            max_workers: Número máximo de threads para lectura paralela
            chunk_size: Tamaño de lote para inserción en BD
        """
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.excel_reader = ExcelReader()
        self.logger = logger

    def process_files(
        self,
        file_list: List[Tuple[str, BytesIO]],
        usuario: str = "sistema",
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[str, int]:
        """
        Procesa archivos Excel y los guarda en base de datos

        Args:
            file_list: Lista de tuplas (nombre_archivo, contenido_BytesIO)
            usuario: Usuario que realiza la carga
            progress_callback: Función callback para reportar progreso

        Returns:
            Tupla de (lote_id, total_registros)

        Raises:
            ValueError: Si no se puede procesar ningún archivo
            Exception: Para otros errores de procesamiento
        """
        lote_id = str(uuid.uuid4())

        self.logger.info("=" * 80)
        self.logger.info(f"Iniciando procesamiento de lote: {lote_id}")
        self.logger.info(f"Usuario: {usuario}")
        self.logger.info(f"Archivos a procesar: {len(file_list)}")
        self.logger.info("=" * 80)

        # Crear registro de lote
        lote = self._create_lote(lote_id, usuario, file_list)

        try:
            # Paso 1: Leer archivos
            self._report(5, f"Leyendo {len(file_list)} archivo(s)...", progress_callback)
            frames, archivos_procesados, archivos_fallidos = self._read_files(file_list)

            if not frames:
                error_msg = self._handle_no_files_processed(archivos_fallidos, lote)
                raise ValueError(error_msg)

            # Paso 2: Consolidar datos
            self._report(30, "Consolidando datos...", progress_callback)
            base_df = pd.concat(frames, ignore_index=True)
            self.logger.info(f"Total de registros consolidados: {len(base_df)}")

            # Paso 3: Procesar cuentas contables
            self._report(40, "Procesando cuentas contables...", progress_callback)
            base_df = self._process_cuentas_contables(base_df)

            # Paso 4: Convertir valores monetarios
            self._report(50, "Convirtiendo valores monetarios...", progress_callback)
            base_df = self._convert_monetary_values(base_df)

            # Paso 5: Calcular saldos acumulativos
            self._report(60, "Calculando saldos acumulativos...", progress_callback)
            base_df = self._calculate_balances(base_df)

            # Paso 6: Convertir fechas
            self._report(75, "Procesando fechas...", progress_callback)
            base_df = self._convert_dates(base_df)

            # Paso 7: Insertar en base de datos
            self._report(80, f"Insertando {len(base_df):,} registros en base de datos...", progress_callback)
            self._insert_into_database(base_df, lote_id, usuario, progress_callback)

            # Actualizar lote
            self._complete_lote(lote, len(base_df), len(archivos_procesados))

            self._report(100, f"✅ Completado: {len(base_df):,} registros insertados", progress_callback)

            self.logger.info("=" * 80)
            self.logger.info(f"Procesamiento completado exitosamente")
            self.logger.info(f"Lote ID: {lote_id}")
            self.logger.info(f"Total de registros: {len(base_df):,}")
            self.logger.info(f"Archivos procesados: {len(archivos_procesados)}")
            self.logger.info(f"Archivos fallidos: {len(archivos_fallidos)}")
            self.logger.info("=" * 80)

            return lote_id, len(base_df)

        except Exception as e:
            self._handle_error(lote, e)
            raise

    def _create_lote(self, lote_id: str, usuario: str, file_list: List) -> LoteCarga:
        """Crea el registro de lote inicial"""
        lote = LoteCarga(
            lote_id=lote_id,
            usuario=usuario,
            archivos=[f[0] for f in file_list],
            estado='procesando'
        )
        db.session.add(lote)
        db.session.commit()
        self.logger.info(f"Lote creado: {lote_id}")
        return lote

    def _read_files(self, file_list: List) -> Tuple[List, List, List]:
        """
        Lee archivos en paralelo

        Returns:
            Tupla de (frames, archivos_procesados, archivos_fallidos)
        """
        self.logger.info(f"Iniciando lectura paralela de {len(file_list)} archivos con {self.max_workers} workers")

        frames = []
        archivos_procesados = []
        archivos_fallidos = []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(file_list))) as executor:
            futures = {executor.submit(self.excel_reader.read_excel_file, f): f for f in file_list}

            for future in as_completed(futures):
                try:
                    df, filename = future.result()
                    if not df.empty:
                        df['archivo_origen'] = filename
                        frames.append(df)
                        archivos_procesados.append(filename)
                        self.logger.info(f"✓ Archivo procesado: {filename} ({len(df)} registros)")
                    else:
                        archivos_fallidos.append(filename)
                        self.logger.warning(f"✗ Archivo sin registros válidos: {filename}")
                except Exception as e:
                    file_info = futures[future]
                    self.logger.error(f"✗ Error procesando {file_info[0]}: {type(e).__name__} - {str(e)}")
                    self.logger.debug(f"Traceback: {traceback.format_exc()}")
                    archivos_fallidos.append(file_info[0])

        self.logger.info(f"Lectura completada: {len(archivos_procesados)} exitosos, {len(archivos_fallidos)} fallidos")
        return frames, archivos_procesados, archivos_fallidos

    def _process_cuentas_contables(self, df: pd.DataFrame) -> pd.DataFrame:
        """Procesa y descompone las cuentas contables"""
        self.logger.info("Descomponiendo cuentas contables en componentes...")

        componentes = df["cuenta_contable"].apply(parse_cuenta_contable)

        for key in ["genero", "grupo", "rubro", "cuenta", "subcuenta",
                    "dependencia", "unidad_responsable", "centro_costo",
                    "proyecto_presupuestario", "fuente", "subfuente",
                    "tipo_recurso", "partida_presupuestal"]:
            df[key] = componentes.apply(lambda x: x[key])

        self.logger.info(f"✓ Cuentas contables procesadas: {len(df['cuenta_contable'].unique())} únicas")
        return df

    def _convert_monetary_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convierte columnas monetarias a numérico"""
        self.logger.info("Convirtiendo valores monetarios...")

        df["saldo_inicial"] = to_numeric_fast(df["saldo_inicial"])
        df["cargos"] = to_numeric_fast(df["cargos"])
        df["abonos"] = to_numeric_fast(df["abonos"])

        # Estadísticas
        total_cargos = df["cargos"].sum()
        total_abonos = df["abonos"].sum()
        self.logger.info(f"✓ Valores convertidos - Total cargos: ${total_cargos:,.2f}, Total abonos: ${total_abonos:,.2f}")

        return df

    def _calculate_balances(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula saldos acumulativos por cuenta"""
        self.logger.info("Calculando saldos acumulativos por cuenta...")

        df["saldo_final"] = 0.0
        cuentas_unicas = df["cuenta_contable"].unique()

        self.logger.info(f"Procesando saldos para {len(cuentas_unicas)} cuentas")

        for i, cuenta in enumerate(cuentas_unicas, 1):
            if i % 100 == 0:
                self.logger.debug(f"Procesando cuenta {i}/{len(cuentas_unicas)}")

            mask = df["cuenta_contable"] == cuenta
            indices = df[mask].index

            saldo_actual = 0.0
            for j, idx in enumerate(indices):
                if j == 0:
                    # Primera transacción: usar saldo inicial del registro
                    saldo_actual = df.loc[idx, "saldo_inicial"] + df.loc[idx, "cargos"] - df.loc[idx, "abonos"]
                else:
                    # Transacciones siguientes: usar saldo final anterior
                    df.loc[idx, "saldo_inicial"] = saldo_actual
                    saldo_actual = saldo_actual + df.loc[idx, "cargos"] - df.loc[idx, "abonos"]

                df.loc[idx, "saldo_final"] = saldo_actual

        self.logger.info("✓ Saldos acumulativos calculados")
        return df

    def _convert_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convierte las fechas al formato correcto"""
        self.logger.info("Convirtiendo fechas...")

        df["fecha_transaccion"] = pd.to_datetime(df["fecha"], format="%d/%m/%Y", errors="coerce")

        # Contar fechas inválidas
        fechas_invalidas = df["fecha_transaccion"].isna().sum()
        if fechas_invalidas > 0:
            self.logger.warning(f"Se encontraron {fechas_invalidas} fechas inválidas")

        self.logger.info("✓ Fechas convertidas")
        return df

    def _insert_into_database(self, df: pd.DataFrame, lote_id: str, usuario: str,
                               progress_callback: Optional[Callable] = None):
        """Inserta registros en base de datos por lotes"""
        self.logger.info(f"Iniciando inserción de {len(df):,} registros en lotes de {self.chunk_size}")

        total_insertados = 0

        for i in range(0, len(df), self.chunk_size):
            chunk = df.iloc[i:i + self.chunk_size]

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

            try:
                db.session.bulk_save_objects(transacciones)
                db.session.commit()
                total_insertados += len(chunk)

                lote_num = (i // self.chunk_size) + 1
                total_lotes = (len(df) + self.chunk_size - 1) // self.chunk_size
                self.logger.debug(f"Lote {lote_num}/{total_lotes} insertado ({len(chunk)} registros)")

                # Reportar progreso
                progress_pct = 80 + int((total_insertados / len(df)) * 15)
                self._report(progress_pct, f"Insertados {total_insertados:,} de {len(df):,} registros", progress_callback)

            except Exception as e:
                self.logger.error(f"Error insertando lote: {type(e).__name__} - {str(e)}")
                self.logger.error(f"Traceback: {traceback.format_exc()}")
                db.session.rollback()
                raise

        self.logger.info(f"✓ Inserción completada: {total_insertados:,} registros")

    def _complete_lote(self, lote: LoteCarga, total_registros: int, archivos_procesados: int):
        """Marca el lote como completado"""
        lote.total_registros = total_registros
        lote.estado = 'completado'
        lote.mensaje = f'Procesados {total_registros:,} registros de {archivos_procesados} archivos'
        db.session.commit()
        self.logger.info(f"Lote {lote.lote_id} marcado como completado")

    def _handle_no_files_processed(self, archivos_fallidos: List, lote: LoteCarga) -> str:
        """Maneja el caso cuando no se procesa ningún archivo"""
        error_msg = f'No se pudo procesar ningún archivo válido. Archivos fallidos: {", ".join(archivos_fallidos)}'
        self.logger.error(error_msg)
        lote.estado = 'error'
        lote.mensaje = error_msg
        db.session.commit()
        return error_msg

    def _handle_error(self, lote: LoteCarga, error: Exception):
        """Maneja errores durante el procesamiento"""
        error_msg = f"{type(error).__name__}: {str(error)}"
        self.logger.error(f"Error fatal en procesamiento: {error_msg}")
        self.logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        lote.estado = 'error'
        lote.mensaje = error_msg
        db.session.commit()

    def _report(self, percentage: int, message: str, callback: Optional[Callable] = None):
        """Reporta progreso"""
        if callback:
            callback(percentage, message)
        self.logger.info(f"[{percentage}%] {message}")
