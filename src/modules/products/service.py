from sqlalchemy.orm import Session
import logging
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from src.models.product import Product
from src.modules.products.type import ProductCreate, ProductUpdate, BulkProductImport
from src.utils.pdf_exporter import PDFReportGenerator
from typing import List, Tuple
from src.models.route import Route
from src.models.route_inventory import RouteInventory
from datetime import datetime
from reportlab.lib.pagesizes import letter
from src.utils.type_converters import decimal_to_str, safe_title
from src.utils.excel_formatter import (
    read_excel,
    convert_to_model_list,
    validate_no_duplicates,
    export_to_excel,
    ExcelImportError
)

logger = logging.getLogger(__name__)


def create_product(db: Session, product_data: ProductCreate) -> Product:
    """
    Crea un nuevo producto.

    Raises:
        SQLAlchemyError: Para errores de base de datos

    Returns:
        Product: Producto creado
    """
    product = Product(
        nombre=product_data.nombre,
        precio=product_data.precio,
        stock_total=product_data.stock_total
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def get_product(db: Session, product_id: int) -> Product | None:
    """Obtiene un producto por su ID"""
    return db.query(Product).filter(Product.id == product_id).first()


def update_product(
    db: Session,
    product_id: int,
    product_data: ProductUpdate
) -> Product | None:
    """
    Actualiza un producto existente.

    Raises:
        SQLAlchemyError: Para errores de base de datos

    Returns:
        Product | None: Producto actualizado o None si no existe
    """
    product = get_product(db, product_id)
    if not product:
        return None

    # Usar model_dump para obtener solo los campos enviados
    update_data = product_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product



def soft_delete_product(db: Session, product_id: int) -> Product:
    """
    Desactiva un producto (soft delete).
    Valida que el producto no esté en uso en rutas activas.
    Modifica nombre para permitir reutilización.

    Args:
        db: Sesión de base de datos
        product_id: ID del producto a desactivar

    Returns:
        Product: Producto desactivado

    Raises:
        ValueError: Si el producto no existe, ya está inactivo,
                   o está en uso en rutas activas
    """
    # 1. Obtener producto
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise ValueError(f"Producto con ID {product_id} no existe")

    if not product.activo:
        raise ValueError("El producto ya está inactivo")

    # 2. Verificar si está en uso en rutas PENDIENTES o EN_PROCESO
    rutas_activas = (
        db.query(Route)
        .join(RouteInventory)
        .filter(
            RouteInventory.producto_id == product_id,
            Route.estado.in_(['pendiente', 'en_proceso'])
        )
        .all()
    )

    if rutas_activas:
        rutas_nombres = [f"'{r.nombre}' (ID: {r.id})" for r in rutas_activas]
        raise ValueError(
            f"No se puede desactivar el producto '{product.nombre}' porque "
            f"está asignado a {len(rutas_activas)} ruta(s) activa(s): "
            f"{', '.join(rutas_nombres)}"
        )

    # 3. Guardar valores originales para logs
    original_nombre = product.nombre

    # 4. Timestamp único para evitar colisiones
    now = datetime.now()
    timestamp = now.strftime("%d%H%M%S") + str(now.microsecond)[:1]

    # 5. Desactivar y modificar nombre (máximo 120 caracteres)
    product.activo = False
    prefix = f"del_{timestamp}_"
    max_nombre_length = 120 - len(prefix)
    nombre_truncado = product.nombre[:max_nombre_length]
    product.nombre = f"{prefix}{nombre_truncado}"


    db.commit()
    db.refresh(product)

    logger.info(
        f"✅ Product soft deleted: ID={product.id}, "
        f"original_nombre='{original_nombre}'"
    )

    return product


def check_product_usage(db: Session, product_id: int) -> dict:
    """
    Verifica el uso de un producto en el sistema.
    Útil para mostrar advertencias antes de eliminar.

    Args:
        db: Sesión de base de datos
        product_id: ID del producto

    Returns:
        dict: Información sobre el uso del producto
    """
    from src.models.orders import Order

    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise ValueError(f"Producto con ID {product_id} no existe")

    # Contar rutas activas
    rutas_pendientes = (
        db.query(Route)
        .join(RouteInventory)
        .filter(
            RouteInventory.producto_id == product_id,
            Route.estado == 'pendiente'
        )
        .count()
    )

    rutas_en_proceso = (
        db.query(Route)
        .join(RouteInventory)
        .filter(
            RouteInventory.producto_id == product_id,
            Route.estado == 'en_proceso'
        )
        .count()
    )

    rutas_completadas = (
        db.query(Route)
        .join(RouteInventory)
        .filter(
            RouteInventory.producto_id == product_id,
            Route.estado == 'completada'
        )
        .count()
    )

    # Contar órdenes pendientes
    ordenes_pendientes = (
        db.query(Order)
        .filter(
            Order.producto_id == product_id,
            Order.asignada == False
        )
        .count()
    )

    tiene_uso_activo = (rutas_pendientes + rutas_en_proceso + ordenes_pendientes) > 0

    return {
        "producto_id": product_id,
        "nombre": product.nombre,
        "stock_actual": product.stock_total,
        "puede_eliminarse": not tiene_uso_activo,
        "uso": {
            "rutas_pendientes": rutas_pendientes,
            "rutas_en_proceso": rutas_en_proceso,
            "rutas_completadas": rutas_completadas,
            "ordenes_pendientes": ordenes_pendientes
        },
        "mensaje": (
            "El producto puede ser desactivado de forma segura"
            if not tiene_uso_activo
            else "⚠️ El producto está en uso activo. No se puede desactivar."
        )
    }

def list_products(db: Session, skip: int = 0, limit: int = 10) -> list[Product]:
    """
    Lista productos ACTIVOS con paginación.

    """
    return (
        db.query(Product)
        .filter(Product.activo == True)  #  Solo activos
        .order_by(Product.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

def count_products(db: Session) -> int:
    """
    Cuenta el total de productos ACTIVOS.

    """
    return (
        db.query(func.count(Product.id))
        .filter(Product.activo == True)  #  Solo activos
        .scalar()
    )


def search_products(
    db: Session,
    query: str,
    skip: int = 0,
    limit: int = 10
) -> list[Product]:
    """
    Busca productos ACTIVOS por nombre con paginación.

    """
    search_pattern = f"%{query}%"
    return (
        db.query(Product)
        .filter(
            Product.nombre.ilike(search_pattern),
            Product.activo == True  #  Solo activos
        )
        .order_by(Product.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_search_results(db: Session, query: str) -> int:
    """
    Cuenta el total de resultados de búsqueda (solo activos).

    """
    search_pattern = f"%{query}%"
    return (
        db.query(func.count(Product.id))
        .filter(
            Product.nombre.ilike(search_pattern),
            Product.activo == True  #  Solo activos
        )
        .scalar()
    )


def import_products_from_excel(
    file,
    db: Session,
) -> Tuple[List[Product], List[dict], List[dict]]:
    """
    Importa productos desde un archivo Excel.

    Args:
        file: Archivo Excel
        db: Sesión de base de datos

    Returns:
        Tuple con: productos creados, errores de validación, errores de DB
    """
    required_columns = ['nombre', 'precio', 'stock_total']

    try:
        # 1. Leer Excel
        df = read_excel(file, required_columns=required_columns)
        logger.info(f"Excel file read successfully. Found {len(df)} rows")

        # 2. Convertir a modelos Pydantic y validar
        items, validation_errors = convert_to_model_list(
            df,
            model=BulkProductImport,
            clean_data=True
        )

        if validation_errors:
            logger.warning(
                f"Found {len(validation_errors)} validation errors in Excel"
            )

        # 3. Validar duplicados DENTRO del Excel
        duplicate_errors = validate_no_duplicates(
            items,
            unique_fields=['nombre']
        )

        if duplicate_errors:
            logger.warning(
                f"Found {len(duplicate_errors)} duplicate entries in Excel"
            )
            validation_errors.extend(duplicate_errors)

        # 4. Si hay errores de validación, retornar sin crear productos
        if validation_errors:
            return [], validation_errors, []

        # 5. Intentar crear productos en la base de datos
        created_products = []
        db_errors = []

        for idx, item in enumerate(items):
            row_number = idx + 2  # +2 por header y índice base 0

            # Type assertion para ayudar al type checker
            assert isinstance(item, BulkProductImport)

            try:
                product_data = ProductCreate(
                    nombre=item.nombre,
                    precio=item.precio,
                    stock_total=item.stock_total
                )

                product = create_product(db, product_data)
                created_products.append(product)
                logger.info(f"Product created: {product.nombre}")

            except IntegrityError as ie:
                db.rollback()
                error_msg = str(ie.orig) if hasattr(ie, 'orig') else str(ie)

                # Determinar qué campo causó el error
                if 'nombre' in error_msg.lower():
                    field = 'nombre'
                else:
                    field = 'desconocido'

                db_errors.append({
                    "row": row_number,
                    "error": (
                        f"Ya existe un producto con este {field} "
                        f"en la base de datos"
                    ),
                    "data": {
                        "nombre": item.nombre,
                        "precio": str(item.precio),
                        "stock_total": item.stock_total
                    }
                })
                logger.warning(
                    f"Duplicate product at row {row_number}: {item.nombre}"
                )

            except ValueError as ve:
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error de validación: {str(ve)}",
                    "data": {
                        "nombre": item.nombre,
                        "precio": str(item.precio),
                        "stock_total": item.stock_total
                    }
                })
                logger.warning(
                    f"Validation error at row {row_number}: {str(ve)}"
                )

            except Exception as e:
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error inesperado: {str(e)}",
                    "data": {
                        "nombre": item.nombre,
                        "precio": str(item.precio),
                        "stock_total": item.stock_total
                    }
                })
                logger.error(
                    f"Unexpected error creating product at row {row_number}: "
                    f"{str(e)}"
                )

        logger.info(
            f"Import completed. Created: {len(created_products)}, "
            f"DB Errors: {len(db_errors)}"
        )
        return created_products, [], db_errors

    except ExcelImportError as e:
        logger.error(f"Excel import error: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during Excel import: {str(e)}")
        raise Exception(f"Error procesando el archivo Excel: {str(e)}")

def export_products_to_excel(db: Session) -> bytes:
    """
    Exporta productos ACTIVOS a un archivo Excel.

    """
    try:
        # Obtener solo productos ACTIVOS ordenados por nombre
        products = (
            db.query(Product)
            .filter(Product.activo == True)  #  Solo activos
            .order_by(Product.nombre)
            .all()
        )

        if not products:
            logger.warning("No active products found to export")
            data = []
        else:
            data = []
            for product in products:
                data.append({
                    "nombre": safe_title(product.nombre),
                    "precio": decimal_to_str(product.precio),
                    "stock_total": str(product.stock_total)
                })

            logger.info(f"Exporting {len(products)} active products to Excel")

        excel_file = export_to_excel(
            data=data,
            filename="productos.xlsx",
            sheet_name="Productos"
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting products to Excel: {str(e)}")
        raise Exception(f"Error al exportar productos a Excel: {str(e)}")


def export_products_to_pdf(db: Session) -> bytes:
    """
    Exporta productos ACTIVOS a un archivo PDF.

    """
    try:
        # Obtener solo productos ACTIVOS ordenados por nombre
        products = (
            db.query(Product)
            .filter(Product.activo == True)  #  Solo activos
            .order_by(Product.nombre)
            .all()
        )

        if not products:
            logger.warning("No active products found to export")
            data = []
        else:
            data = []
            for product in products:
                data.append({
                    "nombre": safe_title(product.nombre),
                    "precio": f"Q{decimal_to_str(product.precio)}",
                    "stock_total": str(product.stock_total)
                })

            logger.info(f"Exporting {len(products)} active products to PDF")

        col_widths = [200.0, 100.0, 100.0]

        generator = PDFReportGenerator(
            title="REPORTE DE PRODUCTOS",
            page_size=letter,
            author="Sistema",
            subject="reporte_productos.pdf"
        )

        pdf_bytes = generator.generate(
            headers=["Nombre", "Precio", "Stock Total"],
            data=data,
            col_widths=col_widths
        )
        return pdf_bytes

    except Exception as e:
        logger.exception(f"Error exporting products to PDF: {str(e)}")
        raise Exception(f"Error al exportar productos a PDF: {str(e)}")
