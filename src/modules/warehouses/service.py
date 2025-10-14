from sqlalchemy.orm import Session
import re
import logging
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from src.models.warehouse import Warehouse
from src.modules.warehouses.type import WarehouseCreate, WarehouseUpdate, BulkWarehouseImport
from src.utils.pdf_exporter import PDFReportGenerator
from typing import List, Tuple
from reportlab.lib.pagesizes import letter
from src.utils.type_converters import decimal_to_str, safe_title, format_phone_gt
from src.utils.excel_formatter import (
    read_excel,
    convert_to_model_list,
    validate_no_duplicates,
    export_to_excel,
    ExcelImportError
)

logger = logging.getLogger(__name__)

def create_warehouse(db: Session, warehouse_data: WarehouseCreate) -> Warehouse:
    """
    Crea un nuevo almacén.

    Raises:
        SQLAlchemyError: Para errores de base de datos

    Returns:
        Warehouse: Almacén creado
    """
    warehouse = Warehouse(
        nombre=warehouse_data.nombre,
        direccion=warehouse_data.direccion,
        telefono=warehouse_data.telefono,
        latitud=warehouse_data.latitud,
        longitud=warehouse_data.longitud
    )
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)
    return warehouse

def get_warehouse(db: Session, warehouse_id: int) -> Warehouse | None:
    """Obtiene un almacén por su ID"""
    return db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()

def update_warehouse(db: Session, warehouse_id: int, warehouse_data: WarehouseUpdate) -> Warehouse | None:
    """
    Actualiza un almacén existente.

    Raises:
        SQLAlchemyError: Para errores de base de datos

    Returns:
        Warehouse | None: Almacén actualizado o None si no existe
    """
    warehouse = get_warehouse(db, warehouse_id)
    if not warehouse:
        return None

    if warehouse_data.nombre is not None:
        setattr(warehouse, "nombre", warehouse_data.nombre)
    if warehouse_data.direccion is not None:
        setattr(warehouse, "direccion", warehouse_data.direccion)
    if warehouse_data.telefono is not None:
        setattr(warehouse, "telefono", warehouse_data.telefono)
    if warehouse_data.latitud is not None:
        setattr(warehouse, "latitud", warehouse_data.latitud)
    if warehouse_data.longitud is not None:
        setattr(warehouse, "longitud", warehouse_data.longitud)

    db.commit()
    db.refresh(warehouse)
    return warehouse

def list_warehouses(db: Session, skip: int = 0, limit: int = 10) -> list[Warehouse]:
    """
    Lista almacenes con paginación

    Args:
        db: Sesión de base de datos
        skip: Número de registros a saltar (offset)
        limit: Número máximo de registros a retornar
    """
    return (
        db.query(Warehouse)
        .order_by(Warehouse.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

def count_warehouses(db: Session) -> int:
    """Cuenta el total de almacenes"""
    return db.query(func.count(Warehouse.id)).scalar()

def search_warehouses(db: Session, query: str, skip: int = 0, limit: int = 10) -> list[Warehouse]:
    """
    Busca almacenes por nombre o dirección con paginación

    Args:
        db: Sesión de base de datos
        query: Término de búsqueda
        skip: Número de registros a saltar
        limit: Número máximo de registros a retornar
    """
    search_pattern = f"%{query}%"
    return (
        db.query(Warehouse)
        .filter(
            or_(
                Warehouse.nombre.ilike(search_pattern),
                Warehouse.direccion.ilike(search_pattern)
            )
        )
        .order_by(Warehouse.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

def count_search_results(db: Session, query: str) -> int:
    """Cuenta el total de resultados de búsqueda"""
    search_pattern = f"%{query}%"
    return (
        db.query(func.count(Warehouse.id))
        .filter(
            or_(
                Warehouse.nombre.ilike(search_pattern),
                Warehouse.direccion.ilike(search_pattern)
            )
        )
        .scalar()
    )

def import_warehouses_from_excel(
    file,
    db: Session,
) -> Tuple[List[Warehouse], List[dict], List[dict]]:

    required_columns = ['nombre', 'direccion', 'telefono', 'latitud', 'longitud']

    try:
        # 1. Leer Excel
        df = read_excel(file, required_columns=required_columns)
        logger.info(f"Excel file read successfully. Found {len(df)} rows")

        # 2. Convertir a modelos Pydantic y validar
        items, validation_errors = convert_to_model_list(
            df,
            model=BulkWarehouseImport,
            clean_data=True
        )

        if validation_errors:
            logger.warning(f"Found {len(validation_errors)} validation errors in Excel")

        # 3. Validar duplicados DENTRO del Excel
        duplicate_errors = validate_no_duplicates(
            items,
            unique_fields=['direccion', 'telefono']
        )

        if duplicate_errors:
            logger.warning(f"Found {len(duplicate_errors)} duplicate entries in Excel")
            validation_errors.extend(duplicate_errors)

        # 4. Si hay errores de validación, retornar sin crear usuarios
        if validation_errors:
            return [], validation_errors, []

        # 5. Intentar crear usuarios en la base de datos
        created_warehouses = []
        db_errors = []

        for idx, item in enumerate(items):
            row_number = idx + 2  # +2 por header y índice base 0

            # Type assertion para ayudar al type checker
            assert isinstance(item, BulkWarehouseImport)

            try:
                warehouse_data = WarehouseCreate(
                    nombre=item.nombre,
                    direccion=item.direccion,
                    telefono=item.telefono,
                    latitud=item.latitud,
                    longitud=item.longitud
                )

                warehouse = create_warehouse(db, warehouse_data)
                created_warehouses.append(warehouse)
                logger.info(f"Warehouse created: {warehouse.nombre}")

            except IntegrityError as ie:
                db.rollback()
                error_msg = str(ie.orig) if hasattr(ie, 'orig') else str(ie)

                # Determinar qué campo causó el error
                if 'direccion' in error_msg.lower():
                    field = 'direccion'
                elif 'telefono' in error_msg.lower():
                    field = 'telefono'
                else:
                    field = 'email/telefono'

                db_errors.append({
                    "row": row_number,
                    "error": f"Ya existe un almacen con este {field} en la base de datos",
                    "data": {
                        "nombre": item.nombre,
                        "direccion": item.direccion,
                        "telefono": item.telefono
                    }
                })
                logger.warning(f"Duplicate warehouse at row {row_number}: {item.direccion} / {item.telefono}")


            except ValueError as ve:
                # Errores de validación de contraseña que puedan escapar
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error de validación: {str(ve)}",
                    "data": {
                        "nombre": item.nombre,
                        "direccion": item.direccion,
                        "telefono": item.telefono
                    }
                })
                logger.warning(f"Validation error at row {row_number}: {str(ve)}")

            except Exception as e:
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error inesperado: {str(e)}",
                    "data": {
                        "nombre": item.nombre,
                        "direccion": item.direccion,
                        "telefono": item.telefono
                    }
                })
                logger.error(f"Unexpected error creating warehouse at row {row_number}: {str(e)}")

        logger.info(f"Import completed. Created: {len(created_warehouses)}, DB Errors: {len(db_errors)}")
        return created_warehouses, [], db_errors

    except ExcelImportError as e:
        logger.error(f"Excel import error: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during Excel import: {str(e)}")
        raise Exception(f"Error procesando el archivo Excel: {str(e)}")

def export_warehouses_to_excel(db: Session) -> bytes:

    try:
        # Obtener todos los almacenes ordenados por nombre
        warehouses = db.query(Warehouse).order_by(Warehouse.nombre).all()

        if not warehouses:
            logger.warning("No warehouses found to export")
            data = []
        else:
            data = []
            for wh in warehouses:


                data.append({
                    "nombre": safe_title(wh.nombre),
                    "direccion": safe_title(wh.direccion),
                    "telefono": format_phone_gt(wh.telefono, "display"),
                    "latitud": decimal_to_str(wh.latitud),
                    "longitud": decimal_to_str(wh.longitud)
                })

            logger.info(f"Exporting {len(warehouses)} warehouses to Excel")

        # Generar Excel
        excel_file = export_to_excel(
            data=data,
            filename="almacenes.xlsx",
            sheet_name="Almacenes"
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting warehouses to Excel: {str(e)}")
        raise Exception(f"Error al exportar almacenes a Excel: {str(e)}")

def export_warehouses_to_pdf(db: Session) -> bytes:

    try:
        # Obtener todos los almacenes ordenados por nombre
        warehouses = db.query(Warehouse).order_by(Warehouse.nombre).all()

        if not warehouses:
            logger.warning("No warehouses found to export")
            data = []
        else:
            # Convertir a diccionarios con el orden correcto y nombre capitalizado
            data = []
            for wh in warehouses:
                data.append({
                    "nombre": safe_title(wh.nombre),
                    "direccion": safe_title(wh.direccion),
                    "telefono": format_phone_gt(wh.telefono, "display"),
                    "latitud": decimal_to_str(wh.latitud),
                    "longitud": decimal_to_str(wh.longitud)
                })

            logger.info(f"Exporting {len(warehouses)} warehouses to PDF")

        # Anchos personalizados para las columnas (en puntos)
        # Nombre: 120, Dirección: 180, Teléfono: 90, Latitud: 70, Longitud: 70
        col_widths = [120.0, 180.0, 90.0, 70.0, 70.0]

        # Generar PDF con anchos personalizados
        generator = PDFReportGenerator(
            title="REPORTE DE ALMACENES",
            page_size=letter,
            author="Sistema",
            subject="reporte_almacenes.pdf"
        )

        pdf_bytes = generator.generate(
            headers=["Nombre", "Direccion", "Telefono", "Latitud", "Longitud"],
            data=data,
            col_widths=col_widths
        )

        return pdf_bytes

    except Exception as e:
        logger.exception(f"Error exporting warehouses to PDF: {str(e)}")
        raise Exception(f"Error al exportar almacenes a PDF: {str(e)}")
