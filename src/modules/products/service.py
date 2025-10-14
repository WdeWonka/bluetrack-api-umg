from sqlalchemy.orm import Session
import logging
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from src.models.product import Product
from src.modules.products.type import ProductCreate, ProductUpdate, BulkProductImport
from src.utils.pdf_exporter import PDFReportGenerator
from typing import List, Tuple
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


def list_products(db: Session, skip: int = 0, limit: int = 10) -> list[Product]:
    """
    Lista productos con paginación

    Args:
        db: Sesión de base de datos
        skip: Número de registros a saltar (offset)
        limit: Número máximo de registros a retornar
    """
    return (
        db.query(Product)
        .order_by(Product.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_products(db: Session) -> int:
    """Cuenta el total de productos"""
    return db.query(func.count(Product.id)).scalar()


def search_products(
    db: Session,
    query: str,
    skip: int = 0,
    limit: int = 10
) -> list[Product]:
    """
    Busca productos por nombre con paginación

    Args:
        db: Sesión de base de datos
        query: Término de búsqueda
        skip: Número de registros a saltar
        limit: Número máximo de registros a retornar
    """
    search_pattern = f"%{query}%"
    return (
        db.query(Product)
        .filter(Product.nombre.ilike(search_pattern))
        .order_by(Product.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_search_results(db: Session, query: str) -> int:
    """Cuenta el total de resultados de búsqueda"""
    search_pattern = f"%{query}%"
    return (
        db.query(func.count(Product.id))
        .filter(Product.nombre.ilike(search_pattern))
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
    Exporta productos a un archivo Excel.

    Args:
        db: Sesión de base de datos

    Returns:
        bytes: Contenido del archivo Excel
    """
    try:
        # Obtener todos los productos ordenados por nombre
        products = db.query(Product).order_by(Product.nombre).all()

        if not products:
            logger.warning("No products found to export")
            data = []
        else:
            data = []
            for product in products:
                data.append({
                    "nombre": safe_title(product.nombre),
                    "precio": decimal_to_str(product.precio),
                    "stock_total": str(product.stock_total)  # ✨ int → str
                })

            logger.info(f"Exporting {len(products)} products to Excel")

        # Generar Excel
        excel_file = export_to_excel(
            data=data,
            filename="productos.xlsx",  # ✨ Corregido
            sheet_name="Productos"  # ✨ Corregido
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting products to Excel: {str(e)}")
        raise Exception(f"Error al exportar productos a Excel: {str(e)}")


def export_products_to_pdf(db: Session) -> bytes:
    """
    Exporta productos a un archivo PDF.

    Args:
        db: Sesión de base de datos

    Returns:
        bytes: Contenido del archivo PDF
    """
    try:
        # Obtener todos los productos ordenados por nombre
        products = db.query(Product).order_by(Product.nombre).all()

        if not products:
            logger.warning("No products found to export")
            data = []
        else:
            # Convertir a diccionarios
            data = []
            for product in products:
                data.append({
                    "nombre": safe_title(product.nombre),
                    "precio": f"Q{decimal_to_str(product.precio)}",  # ✨ Formato moneda
                    "stock_total": str(product.stock_total)  # ✨ int → str
                })

            logger.info(f"Exporting {len(products)} products to PDF")

        # Anchos personalizados para las columnas (en puntos)
        col_widths = [200.0, 100.0, 100.0]  # ✨ Ajustados

        # Generar PDF con anchos personalizados
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
