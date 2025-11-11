import pandas as pd
import numpy as np
import re
import logging
from datetime import datetime
from typing import List, Tuple, Callable, Optional
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from models import db, Transaccion, LoteCarga
import uuid
import traceback

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _norm(s):
    """Normaliza strings para comparación"""
    s = str(s or "").strip().lower()
    rep = {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u","ñ":"n"}
    for k,v in rep.items():
        s = s.replace(k,v)
    s = re.sub(r"\s+", " ", s)
    return s

def _split_cuenta_contable_vertical(cuenta_str):
    """Divide la cuenta contable en componentes"""
    s = str(cuenta_str).strip().upper()
    s = re.sub(r"[^0-9A-Z]", "", s).ljust(21, "0")
    
    return {
        "genero": s[0],
        "grupo": s[1],
        "rubro": s[2],
        "cuenta": s[3],
        "subcuenta": s[4],
        "dependencia": s[5:7],
        "unidad_responsable": s[7:9],
        "centro_costo": s[9:11],
        "proyecto_presupuestario": s[11:13],
        "fuente": s[13],
        "subfuente": s[14:16],
        "tipo_recurso": s[16],
        "partida_presupuestal": s[17:21],
    }

def _to_numeric_fast(s):
    """Convierte series a numérico de forma rápida"""
    return pd.to_numeric(
        s.astype(str).str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce"
    ).fillna(0.0)

def _read_one_excel(file_data):
    """Lee un archivo Excel y extrae las transacciones"""
    filename, file_content = file_data
    logger.info(f"Iniciando lectura de archivo: {filename}")
    file_content.seek(0)

    try:
        raw = pd.read_excel(file_content, header=None, dtype=str, engine="openpyxl")
        logger.info(f"Archivo leído exitosamente: {filename} ({len(raw)} filas)")
    except Exception as e:
        logger.error(f"Error al leer archivo {filename}: {type(e).__name__} - {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return pd.DataFrame(), filename
    
    if raw.empty or len(raw) < 2:
        logger.warning(f"Archivo vacío o muy pequeño: {filename} ({len(raw)} filas)")
        return pd.DataFrame(), filename

    # Buscar la fila de encabezados
    header_row_idx = None
    for idx in range(min(20, len(raw))):
        row_text = " ".join(raw.iloc[idx].fillna("").astype(str).str.lower())
        if "fecha" in row_text and ("poliza" in row_text or "saldo" in row_text):
            header_row_idx = idx
            logger.info(f"Encabezado encontrado en fila {idx} de {filename}")
            break

    if header_row_idx is None:
        logger.warning(f"No se encontró fila de encabezados en {filename}. Primeras 5 filas:")
        for i in range(min(5, len(raw))):
            logger.warning(f"  Fila {i}: {' | '.join(raw.iloc[i].fillna('').astype(str).tolist()[:5])}")
        return pd.DataFrame(), filename
    
    # Saltar las filas de encabezado
    start_idx = header_row_idx + 1
    next_row_text = " ".join(raw.iloc[start_idx].fillna("").astype(str).str.lower()) if start_idx < len(raw) else ""
    if "beneficiario" in next_row_text or "descripcion" in next_row_text or "no." in next_row_text:
        start_idx += 1
    
    # Procesar todas las filas
    records = []
    current_cuenta = None
    current_nombre = None
    current_saldo_inicial = None
    
    for idx in range(start_idx, len(raw)):
        row = raw.iloc[idx]
        first_col = str(row.iloc[0] if not pd.isna(row.iloc[0]) else "").strip()
        
        # Detectar línea de cuenta contable
        if "CUENTA CONTABLE:" in first_col.upper():
            parts = first_col.split(":", 1)
            if len(parts) > 1:
                cuenta_nombre = parts[1].strip()
                if " - " in cuenta_nombre:
                    current_cuenta, current_nombre = cuenta_nombre.split(" - ", 1)
                    current_cuenta = current_cuenta.strip()
                    current_nombre = current_nombre.strip()
                else:
                    current_cuenta = cuenta_nombre
                    current_nombre = ""
            current_saldo_inicial = None
            continue
        
        # Detectar línea de saldo inicial
        row_text_upper = " ".join(row.fillna("").astype(str)).upper()
        if "SALDO INICIAL CUENTA" in row_text_upper and current_cuenta:
            for col_idx in range(len(row)):
                val = str(row.iloc[col_idx] if not pd.isna(row.iloc[col_idx]) else "").strip()
                if val and any(c.isdigit() for c in val):
                    test_val = val.replace(",", "").replace(".", "").replace("-", "")
                    if test_val.replace(".", "").isdigit() or test_val.replace(".", "").replace("-", "").isdigit():
                        current_saldo_inicial = val
                        break
            continue
        
        # Ignorar filas vacías y totales
        if row.isna().all():
            continue
        row_text = " ".join(row.fillna("").astype(str)).lower()
        if any(skip in row_text for skip in ["saldo acumulado", "saldo final cuenta"]):
            continue
        
        if not current_cuenta:
            continue
        
        # Extraer datos de transacción
        try:
            fecha_raw = row.iloc[0] if not pd.isna(row.iloc[0]) else None
            if fecha_raw is None or pd.isna(fecha_raw):
                continue
            
            fecha = str(fecha_raw).strip()
            is_date = False
            if "/" in fecha or "-" in fecha:
                is_date = True
            else:
                try:
                    pd.to_datetime(fecha_raw, errors='raise')
                    is_date = True
                except:
                    pass
            
            if not is_date:
                continue
            
            try:
                fecha = pd.to_datetime(fecha_raw).strftime("%d/%m/%Y")
            except:
                pass
            
            poliza = str(row.iloc[1] if len(row) > 1 and not pd.isna(row.iloc[1]) else "").strip()
            
            # Analizar columnas
            col_data = []
            for i in range(2, min(len(row), 15)):
                val = str(row.iloc[i] if not pd.isna(row.iloc[i]) else "").strip()
                col_data.append({
                    'idx': i,
                    'value': val,
                    'is_empty': not val,
                    'is_numeric': False,
                    'is_monetary': False,
                    'numeric_value': None
                })
                
                if val:
                    cleaned = val.replace(",", "").replace(" ", "")
                    try:
                        num_val = float(cleaned)
                        col_data[-1]['is_numeric'] = True
                        col_data[-1]['numeric_value'] = num_val
                        has_comma = "," in val
                        has_decimal = "." in cleaned
                        is_zero_str = val.strip() == "0"
                        
                        if has_comma or has_decimal or is_zero_str:
                            col_data[-1]['is_monetary'] = True
                    except ValueError:
                        pass
            
            # Separar columnas
            text_cols = []
            op_col = None
            monetary_cols = []
            
            for col in col_data:
                if col['is_empty']:
                    continue
                elif col['is_monetary']:
                    monetary_cols.append(col)
                elif col['is_numeric'] and not col['is_monetary']:
                    if op_col is None and col['numeric_value'] and col['numeric_value'].is_integer():
                        op_col = col
                    else:
                        monetary_cols.append(col)
                else:
                    text_cols.append(col)
            
            if len(monetary_cols) < 2:
                continue
            
            # Extraer campos de texto
            beneficiario = ""
            descripcion = ""
            if len(text_cols) >= 2:
                beneficiario = text_cols[0]['value']
                descripcion = " ".join([c['value'] for c in text_cols[1:]])
            elif len(text_cols) == 1:
                descripcion = text_cols[0]['value']
            
            op = op_col['value'] if op_col else ""
            
            # Determinar columnas monetarias
            if len(monetary_cols) >= 4:
                saldo_inicial = monetary_cols[0]['value']
                cargos = monetary_cols[1]['value']
                abonos = monetary_cols[2]['value']
                saldo_final = monetary_cols[3]['value']
            elif len(monetary_cols) == 3:
                saldo_inicial = current_saldo_inicial if current_saldo_inicial else ""
                cargos = monetary_cols[0]['value']
                abonos = monetary_cols[1]['value']
                saldo_final = monetary_cols[2]['value']
            elif len(monetary_cols) == 2:
                saldo_inicial = current_saldo_inicial if current_saldo_inicial else ""
                cargos = ""
                abonos = monetary_cols[0]['value']
                saldo_final = monetary_cols[1]['value']
            else:
                continue
            
            # Crear registro
            record = {
                "cuenta_contable": current_cuenta,
                "nombre_cuenta": current_nombre,
                "fecha": fecha,
                "poliza": poliza,
                "beneficiario": beneficiario,
                "descripcion": descripcion,
                "orden_pago": op,
                "saldo_inicial": saldo_inicial,
                "cargos": cargos,
                "abonos": abonos,
                "saldo_final": saldo_final,
            }
            records.append(record)
        except Exception as e:
            logger.debug(f"Error procesando fila {idx} en {filename}: {str(e)}")
            continue

    if not records:
        logger.warning(f"No se encontraron transacciones válidas en {filename}")
        logger.warning(f"Total de filas procesadas: {len(raw) - start_idx}")
        return pd.DataFrame(), filename

    df = pd.DataFrame(records)
    logger.info(f"✓ Extraídas {len(df)} transacciones de {filename}")
    return df, filename


def process_files_to_database(
    file_list: List[Tuple[str, BytesIO]], 
    usuario: str = "sistema",
    progress_callback: Optional[Callable[[int, str], None]] = None
):
    """
    Procesa archivos Excel y guarda en base de datos
    Retorna el lote_id para tracking
    """
    def report(p, m):
        if progress_callback:
            progress_callback(p, m)
        else:
            print(f"[{p}%] {m}")
    
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
        report(5, f"Leyendo {len(file_list)} archivo(s)...")
        frames = []
        archivos_procesados = []
        archivos_fallidos = []

        with ThreadPoolExecutor(max_workers=min(4, len(file_list))) as ex:
            futures = {ex.submit(_read_one_excel, f): f for f in file_list}
            for f in as_completed(futures):
                try:
                    df, filename = f.result()
                    if not df.empty:
                        df['archivo_origen'] = filename
                        frames.append(df)
                        archivos_procesados.append(filename)
                        logger.info(f"Archivo procesado exitosamente: {filename}")
                    else:
                        archivos_fallidos.append(filename)
                        logger.warning(f"Archivo no generó registros: {filename}")
                except Exception as e:
                    file_info = futures[f]
                    logger.error(f"Error procesando archivo {file_info[0]}: {type(e).__name__} - {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    archivos_fallidos.append(file_info[0])
                    continue

        logger.info(f"Resumen: {len(archivos_procesados)} exitosos, {len(archivos_fallidos)} fallidos")

        if not frames:
            error_msg = f'No se pudo procesar ningún archivo válido. Archivos fallidos: {", ".join(archivos_fallidos)}'
            logger.error(error_msg)
            lote.estado = 'error'
            lote.mensaje = error_msg
            db.session.commit()
            raise ValueError(error_msg)
        
        base = pd.concat(frames, ignore_index=True)
        
        # Dividir cuenta contable
        report(30, "Procesando cuentas contables...")
        componentes = base["cuenta_contable"].apply(_split_cuenta_contable_vertical)
        for key in ["genero", "grupo", "rubro", "cuenta", "subcuenta",
                    "dependencia", "unidad_responsable", "centro_costo",
                    "proyecto_presupuestario", "fuente", "subfuente",
                    "tipo_recurso", "partida_presupuestal"]:
            base[key] = componentes.apply(lambda x: x[key])
        
        # Convertir columnas monetarias
        report(50, "Convirtiendo valores monetarios...")
        base["saldo_inicial"] = _to_numeric_fast(base["saldo_inicial"])
        base["cargos"] = _to_numeric_fast(base["cargos"])
        base["abonos"] = _to_numeric_fast(base["abonos"])
        
        # Calcular saldo final acumulativo por cuenta
        report(65, "Calculando saldos acumulativos...")
        base["saldo_final"] = 0.0
        
        for cuenta in base["cuenta_contable"].unique():
            mask = base["cuenta_contable"] == cuenta
            indices = base[mask].index
            
            saldo_actual = 0.0
            for i, idx in enumerate(indices):
                if i == 0:
                    saldo_actual = base.loc[idx, "saldo_inicial"] + base.loc[idx, "cargos"] - base.loc[idx, "abonos"]
                else:
                    base.loc[idx, "saldo_inicial"] = saldo_actual
                    saldo_actual = saldo_actual + base.loc[idx, "cargos"] - base.loc[idx, "abonos"]
                
                base.loc[idx, "saldo_final"] = saldo_actual
        
        # Convertir fechas
        base["fecha_transaccion"] = pd.to_datetime(base["fecha"], format="%d/%m/%Y", errors="coerce")
        
        # Insertar en base de datos en lotes
        report(80, f"Insertando {len(base):,} registros en base de datos...")
        logger.info(f"Iniciando inserción de {len(base)} registros en lotes de {1000}")

        chunk_size = 1000
        total_insertados = 0

        for i in range(0, len(base), chunk_size):
            chunk = base.iloc[i:i+chunk_size]

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
                logger.debug(f"Lote {i//chunk_size + 1} insertado correctamente ({len(chunk)} registros)")
            except Exception as e:
                logger.error(f"Error insertando lote {i//chunk_size + 1}: {type(e).__name__} - {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                db.session.rollback()
                raise

            total_insertados += len(chunk)
            progress_pct = 80 + int((total_insertados / len(base)) * 15)
            report(progress_pct, f"Insertados {total_insertados:,} de {len(base):,} registros")
        
        # Actualizar lote
        lote.total_registros = len(base)
        lote.estado = 'completado'
        lote.mensaje = f'Procesados {len(base):,} registros de {len(archivos_procesados)} archivos'
        db.session.commit()
        
        report(100, f"✅ Completado: {len(base):,} registros insertados en BD")
        
        logger.info(f"✓ Procesamiento completado: {len(base)} registros, lote_id={lote_id}")
        return lote_id, len(base)

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error fatal en procesamiento: {error_msg}")
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        lote.estado = 'error'
        lote.mensaje = error_msg
        db.session.commit()
        raise
