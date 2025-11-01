from sqlalchemy.orm import Session
import re
import logging
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from src.models.customer import Customer
from src.modules.customers.type import CustomerCreate, CustomerUpdate
from src.utils.pdf_exporter import PDFReportGenerator
from pydantic import BaseModel, field_validator
from typing import List, Tuple
from reportlab.lib.pagesizes import letter
from decimal import Decimal
from src.utils.type_converters import decimal_to_str, safe_title, format_phone_gt


from src.utils.excel_formatter import (
    read_excel,
    convert_to_model_list,
    validate_no_duplicates,
    export_to_excel,
    ExcelImportError
)
logger = logging.getLogger(__name__)



from pydantic import BaseModel, field_validator
from pydantic import BaseModel, field_validator
from decimal import Decimal

class BulkCustomerImport(BaseModel):
    nombre: str
    direccion: str
    telefono: str
    latitud: Decimal
    longitud: Decimal

    @field_validator('telefono')
    @classmethod
    def limpiar_y_validar_telefono(cls, v):
        """
        Limpia el teléfono y valida que sea válido para Guatemala.
        Acepta formatos: 23671234, 2367-1234, 44567890, 4456-7890
        """
        if not v:
            raise ValueError("El teléfono es requerido")

        # Limpiar el teléfono (remover guiones, espacios, etc)
        telefono_limpio = format_phone_gt(v, "storage")

        # Validar que sea un número válido de 8 dígitos
        if not telefono_limpio.isdigit():
            raise ValueError(f"El teléfono debe contener solo números. Recibido: {v}")

        if len(telefono_limpio) != 8:
            raise ValueError(
                f"El teléfono debe tener 8 dígitos. "
                f"Recibido: {v} (limpio: {telefono_limpio})"
            )

        # Validar que empiece con números válidos de Guatemala
        prefijos_validos = ['2', '3', '4', '5', '6', '7']
        if telefono_limpio[0] not in prefijos_validos:
            raise ValueError(
                f"El teléfono debe empezar con {', '.join(prefijos_validos)}. "
                f"Recibido: {telefono_limpio}"
            )

        return telefono_limpio  # Retornar limpio para la DB

    @field_validator('nombre')
    @classmethod
    def validar_nombre(cls, v):
        """Valida que el nombre no esté vacío."""
        if not v or not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip()

    @field_validator('direccion')
    @classmethod
    def validar_direccion(cls, v):
        """Valida que la dirección no esté vacía."""
        if not v or not v.strip():
            raise ValueError("La dirección no puede estar vacía")
        return v.strip()
    @field_validator('latitud')
    @classmethod
    def validar_latitud(cls, v):
        """Valida que la latitud esté en rango válido para Guatemala."""
        if not -90 <= v <= 90:
            raise ValueError(f"Latitud inválida: {v}. Debe estar entre -90 y 90")
        # Rango aproximado de Guatemala
        if not 13.5 <= v <= 18.0:
            raise ValueError(
                f"Latitud fuera del rango de Guatemala: {v}. "
                f"Debe estar entre 13.5 y 18.0"
            )
        return v
    @field_validator('longitud')
    @classmethod
    def validar_longitud(cls, v):
        """Valida que la longitud esté en rango válido para Guatemala."""
        if not -180 <= v <= 180:
            raise ValueError(f"Longitud inválida: {v}. Debe estar entre -180 y 180")
        # Rango aproximado de Guatemala
        if not -92.5 <= v <= -88.0:
            raise ValueError(
                f"Longitud fuera del rango de Guatemala: {v}. "
                f"Debe estar entre -92.5 y -88.0"
            )
        return v


def create_customer(db: Session, customer_data: CustomerCreate) -> Customer:
    """
    Crea un nuevo almacén.

    Raises:
        SQLAlchemyError: Para errores de base de datos

    Returns:
        Customer: Cliente creado
    """
    customer = Customer(
        nombre=customer_data.nombre,
        direccion=customer_data.direccion,
        telefono=customer_data.telefono,
        latitud=customer_data.latitud,
        longitud=customer_data.longitud
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def get_customer(db: Session, customer_id: int) -> Customer | None:
    """Obtiene un cliente por su ID"""
    return db.query(Customer).filter(Customer.id == customer_id).first()


def update_customer(db: Session, customer_id: int, customer_data: CustomerUpdate) -> Customer | None:
    """
    Actualiza un cliente existente.

    Raises:
        SQLAlchemyError: Para errores de base de datos

    Returns:
        Customer | None: Cliente actualizado o None si no existe
    """
    customer = get_customer(db, customer_id)
    if not customer:
        return None

    if customer_data.nombre is not None:
        setattr(customer, "nombre", customer_data.nombre)
    if customer_data.direccion is not None:
        setattr(customer, "direccion", customer_data.direccion)
    if customer_data.telefono is not None:
        setattr(customer, "telefono", customer_data.telefono)
    if customer_data.latitud is not None:
        setattr(customer, "latitud", customer_data.latitud)
    if customer_data.longitud is not None:
        setattr(customer, "longitud", customer_data.longitud)

    db.commit()
    db.refresh(customer)
    return customer


def list_customers(db: Session, skip: int = 0, limit: int = 10) -> list[Customer]:
    """
    Lista clientes con paginación

    Args:
        db: Sesión de base de datos
        skip: Número de registros a saltar (offset)
        limit: Número máximo de registros a retornar
    """
    return (
        db.query(Customer)
        .order_by(Customer.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_customers(db: Session) -> int:
    """Cuenta el total de clientes"""
    return db.query(func.count(Customer.id)).scalar()


def search_customers(db: Session, query: str, skip: int = 0, limit: int = 10) -> list[Customer]:
    """
    Busca clientes por nombre o dirección con paginación

    Args:
        db: Sesión de base de datos
        query: Término de búsqueda
        skip: Número de registros a saltar
        limit: Número máximo de registros a retornar
    """
    search_pattern = f"%{query}%"
    return (
        db.query(Customer)
        .filter(
            or_(
                Customer.nombre.ilike(search_pattern),
                Customer.direccion.ilike(search_pattern),
                Customer.telefono.ilike(search_pattern)
            )
        )
        .order_by(Customer.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_search_results(db: Session, query: str) -> int:
    """Cuenta el total de resultados de búsqueda"""
    search_pattern = f"%{query}%"
    return (
        db.query(func.count(Customer.id))
        .filter(
            or_(
                Customer.nombre.ilike(search_pattern),
                Customer.direccion.ilike(search_pattern),
                Customer.telefono.ilike(search_pattern)
            )
        )
        .scalar()
    )


def import_customers_from_excel(
    file,
    db: Session,
) -> Tuple[List[Customer], List[dict], List[dict]]:

    required_columns = ['nombre', 'direccion', 'telefono', 'latitud', 'longitud']

    try:
        # 1. Leer Excel
        df = read_excel(file, required_columns=required_columns)
        logger.info(f"Excel file read successfully. Found {len(df)} rows")

        # 2. Convertir a modelos Pydantic y validar
        items, validation_errors = convert_to_model_list(
            df,
            model=BulkCustomerImport,
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
        created_customers = []
        db_errors = []

        for idx, item in enumerate(items):
            row_number = idx + 2

            assert isinstance(item, BulkCustomerImport)

            try:
                customer_data = CustomerCreate(
                    nombre=item.nombre,
                    direccion=item.direccion,
                    telefono=item.telefono,
                    latitud=item.latitud,
                    longitud=item.longitud
                )

                customer = create_customer(db, customer_data)
                created_customers.append(customer)
                logger.info(f"Customer created: {customer.nombre}")

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
                logger.error(f"Unexpected error creating customer at row {row_number}: {str(e)}")

        logger.info(f"Import completed. Created: {len(created_customers)}, DB Errors: {len(db_errors)}")
        return created_customers, [], db_errors

    except ExcelImportError as e:
        logger.error(f"Excel import error: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during Excel import: {str(e)}")
        raise Exception(f"Error procesando el archivo Excel: {str(e)}")


def export_customers_to_excel(db: Session) -> bytes:

    try:
        # Obtener todos los clientes ordenados por nombre
        customers = db.query(Customer).order_by(Customer.nombre).all()

        if not customers:
            logger.warning("No customers found to export")
            data = []
        else:
            data = []
            for c in customers:


                data.append({
                    "nombre": safe_title(c.nombre),
                    "direccion": safe_title(c.direccion),
                    "telefono": format_phone_gt(c.telefono, "display"),
                    "latitud": decimal_to_str(c.latitud),
                    "longitud": decimal_to_str(c.longitud)
                })

            logger.info(f"Exporting {len(customers)} customers to Excel")

        # Generar Excel
        excel_file = export_to_excel(
            data=data,
            filename="clientes.xlsx",
            sheet_name="Clientes"
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting customers to Excel: {str(e)}")
        raise Exception(f"Error al exportar clientes a Excel: {str(e)}")


def export_customers_to_pdf(db: Session) -> bytes:

    try:
        # Obtener todos los clientes ordenados por nombre
        customers = db.query(Customer).order_by(Customer.nombre).all()

        if not customers:
            logger.warning("No customers found to export")
            data = []
        else:
            # Convertir a diccionarios con el orden correcto y nombre capitalizado
            data = []
            for c in customers:
                data.append({
                    "nombre": safe_title(c.nombre),
                    "direccion": safe_title(c.direccion),
                    "telefono": format_phone_gt(c.telefono, "display"),
                    "latitud": decimal_to_str(c.latitud),
                    "longitud": decimal_to_str(c.longitud)
                })

            logger.info(f"Exporting {len(customers)} customers to PDF")

        # Anchos personalizados para las columnas (en puntos)
        # Nombre: 120, Dirección: 180, Teléfono: 90, Latitud: 70, Longitud: 70
        col_widths = [120.0, 180.0, 90.0, 70.0, 70.0]

        # Generar PDF con anchos personalizados
        generator = PDFReportGenerator(
            title="REPORTE DE CLIENTES",
            page_size=letter,
            author="Sistema",
            subject="reporte_clientes.pdf"
        )

        pdf_bytes = generator.generate(
            headers=["Nombre", "Direccion", "Telefono", "Latitud", "Longitud"],
            data=data,
            col_widths=col_widths
        )

        return pdf_bytes

    except Exception as e:
        logger.exception(f"Error exporting customers to PDF: {str(e)}")
        raise Exception(f"Error al exportar clientes a PDF: {str(e)}")
