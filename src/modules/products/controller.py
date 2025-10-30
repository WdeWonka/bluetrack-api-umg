from fastapi import APIRouter, Depends, File, UploadFile, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from db.deps import get_db
from src.modules.products.service import (
    create_product,
    get_product,
    update_product,
    list_products,
    search_products,
    count_products,
    count_search_results,
    import_products_from_excel,
    export_products_to_excel,
    export_products_to_pdf
)
from src.utils.excel_formatter import ExcelImportError, create_template_excel
from src.modules.products.type import ProductCreate, ProductUpdate, ProductRead
from src.utils.http_response import HttpResponse
from src.utils.type_converters import decimal_to_str
from src.modules.auth.dependencies import require_role
from src.common.constants.roles import ADMIN
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/products",
    tags=["products"],
    dependencies=[Depends(require_role([ADMIN]))]
)


@router.post(
    "/",
    summary="Create a new product",
    response_description="Product created successfully"
)
def api_create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new product.

    **Required fields:**
    - nombre: Product name (3-100 characters)
    - precio: Price (must be greater than 0)
    - stock_total: Total stock (0-50,000 units)
    """
    try:
        product = create_product(db, product_data)
        logger.info(f"Product created successfully: {product.nombre}")
        return HttpResponse.created(
            response=ProductRead.model_validate(product).model_dump(mode='json')
        )

    except IntegrityError as ie:
        db.rollback()
        logger.error(f"Integrity error creating product: {str(ie)}")
        return HttpResponse.conflict(
            error="El producto ya existe en la base de datos"
        )

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error creating product: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al crear el producto"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating product: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al crear el producto"
        )


@router.get(
    "/search",
    summary="Search products by name",
    response_description="Search results retrieved successfully"
)
def api_search_products(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1, description="Search query (product name)"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page (max 50)")
):
    """
    Search products by name with pagination.

    **Query parameters:**
    - q: Search term (minimum 1 character)
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 50)
    """
    try:
        skip = (page - 1) * per_page
        results = search_products(db, query=q, skip=skip, limit=per_page)

        if not results:
            logger.info(f"No products found for search query: {q}")
            return HttpResponse.success(
                message=f"No products found matching '{q}'",
                response={
                    "products": [],
                    "search_query": q,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total_items": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "has_prev": False
                    }
                }
            )

        total_results = count_search_results(db, query=q)
        total_pages = (total_results + per_page - 1) // per_page

        logger.info(f"Found {len(results)} products for search query: {q}")
        return HttpResponse.success(
            message=f"Found {total_results} products matching '{q}'",
            response={
                "products": [
                    ProductRead.model_validate(p).model_dump(mode='json')
                    for p in results
                ],
                "search_query": q,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_results,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )

    except SQLAlchemyError as se:
        logger.error(
            f"Database error searching products with query '{q}': {str(se)}"
        )
        return HttpResponse.internal_server_error(
            error="Error de base de datos al buscar productos"
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error searching products with query '{q}': {str(e)}"
        )
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al buscar productos"
        )


@router.post(
    "/import",
    summary="Import products from Excel file",
    response_description="Products imported successfully"
)
async def api_import_products(
    file: UploadFile = File(
        ...,
        description="Excel file (.xlsx) with product data"
    ),
    db: Session = Depends(get_db)
):
    """
    Import multiple products from an Excel file.

    **Expected columns:**
    - nombre: Product name (3-100 characters)
    - precio: Price (must be > 0)
    - stock_total: Stock quantity (0-50,000)

    **Validations:**
    - Product names must be unique
    - Prices must be positive numbers
    - Stock must be between 0 and 50,000
    """
    # Validar que el archivo tenga nombre
    if not file.filename:
        logger.warning("File uploaded without filename")
        return HttpResponse.bad_request(error="El archivo no tiene nombre")

    # Validar extensión del archivo
    if not file.filename.endswith(('.xlsx', '.xls')):
        logger.warning(f"Invalid file type uploaded: {file.filename}")
        return HttpResponse.bad_request(
            error="Tipo de archivo inválido. Por favor sube un archivo Excel "
                  "(.xlsx o .xls)"
        )

    try:
        created_products, validation_errors, db_errors = (
            import_products_from_excel(file=file, db=db)
        )

        if not validation_errors and not db_errors:
            logger.info(
                f"All {len(created_products)} products imported successfully"
            )
            return HttpResponse.custom(
                message=f"Se crearon {len(created_products)} productos exitosamente",
                response={
                    "created_count": len(created_products),
                    "products": [
                        {
                            "nombre": product.nombre,
                            "precio": decimal_to_str(product.precio),
                            "stock_total": product.stock_total
                        }
                        for product in created_products
                    ]
                },
                status_code=201
            )

        elif validation_errors and not db_errors:
            logger.warning(
                f"Import failed with {len(validation_errors)} validation errors"
            )
            return HttpResponse.custom(
                message="El archivo contiene errores de validación. "
                        "No se creó ningún producto.",
                response={
                    "validation_errors": validation_errors,
                    "total_errors": len(validation_errors)
                },
                status_code=422
            )

        else:
            logger.info(
                f"Partial import: {len(created_products)} created, "
                f"{len(db_errors)} failed"
            )
            return HttpResponse.custom(
                message=f"Se crearon {len(created_products)} productos. "
                        f"{len(db_errors)} productos no se pudieron crear.",
                response={
                    "created_count": len(created_products),
                    "error_count": len(db_errors),
                    "created_products": [
                        {
                            "nombre": product.nombre,
                            "precio": decimal_to_str(product.precio),
                            "stock_total": product.stock_total
                        }
                        for product in created_products
                    ],
                    "db_errors": db_errors
                },
                status_code=200
            )

    except ExcelImportError as e:
        logger.error(f"Excel import error: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except Exception as e:
        logger.exception(f"Unexpected error during import: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al procesar el archivo"
        )


@router.get(
    "/export/excel",
    summary="Export all products to Excel",
    response_description="Excel file with all products"
)
def api_export_products_excel(db: Session = Depends(get_db)):
    """
    Export all products to an Excel file.

    **Returns:**
    - Excel file (.xlsx) with all product information
    - Columns: nombre, precio, stock_total
    """
    try:
        excel_content = export_products_to_excel(db)

        logger.info("Products exported to Excel successfully")
        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument."
                       "spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=productos.xlsx"
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting products to Excel: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los productos a Excel"
        )


@router.get(
    "/export/pdf",
    summary="Export all products to PDF",
    response_description="PDF file with all products"
)
def api_export_products_pdf(db: Session = Depends(get_db)):
    """
    Export all products to a PDF report.

    **Returns:**
    - PDF file with formatted table
    - Columns: Nombre, Precio, Stock Total
    """
    try:
        pdf_content = export_products_to_pdf(db)

        logger.info("Products exported to PDF successfully")
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=reporte_productos.pdf"
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting products to PDF: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los productos a PDF"
        )


@router.get(
    "/template",
    summary="Download Excel template for bulk product import",
    response_description="Excel template file"
)
def api_download_product_template():
    """
    Download an Excel template for bulk product import.

    **Returns:**
    - Excel template with required columns and example data
    - Use this template to prepare your bulk import file

    **Columns:**
    - nombre: Product name (3-100 characters)
    - precio: Price (must be greater than 0)
    - stock_total: Stock quantity (0-50,000 units)
    """
    try:
        template = create_template_excel(
            columns=["nombre", "precio", "stock_total"],
            example_data=[
                {
                    "nombre": "Garrafón 20 Litros",
                    "precio": "125.50",
                    "stock_total": "500"
                },
                {
                    "nombre": "Garrafón 10 Litros",
                    "precio": "75.00",
                    "stock_total": "300"
                },
                {
                    "nombre": "Botella 1 Litro",
                    "precio": "5.50",
                    "stock_total": "1000"
                }
            ],
            filename="template_productos.xlsx"
        )

        logger.info("Product template downloaded successfully")
        return Response(
            content=template.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument."
                       "spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=template_productos.xlsx"
            }
        )

    except Exception as e:
        logger.exception(f"Error creating product template: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al generar el template de productos"
        )


@router.get(
    "/{product_id}",
    summary="Get product by ID",
    response_description="Product details retrieved successfully"
)
def api_get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific product by its ID.

    **Path parameters:**
    - product_id: Unique identifier of the product
    """
    try:
        product = get_product(db, product_id)
        if not product:
            logger.warning(f"Product not found with ID: {product_id}")
            return HttpResponse.not_found(
                error=f"Product with ID {product_id} does not exist"
            )

        logger.info(f"Product retrieved successfully with ID: {product_id}")
        return HttpResponse.success(
            message="Product retrieved successfully",
            response=ProductRead.model_validate(product).model_dump(mode='json')
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error retrieving product {product_id}: {str(e)}"
        )
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al obtener el producto"
        )


@router.patch(
    "/{product_id}",
    summary="Update product information",
    response_description="Product updated successfully"
)
def api_update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing product (partial update).

    **Path parameters:**
    - product_id: Unique identifier of the product

    **Optional fields:**
    - nombre: New product name
    - precio: New price
    - stock_total: New stock quantity
    - activo: Active status (true/false)
    """
    try:
        product = update_product(db, product_id, product_data)
        if not product:
            logger.warning(f"Product not found for update with ID: {product_id}")
            return HttpResponse.not_found(
                error=f"Product with ID {product_id} does not exist"
            )

        logger.info(f"Product updated successfully with ID: {product_id}")
        return HttpResponse.updated(
            response=ProductRead.model_validate(product).model_dump(mode='json')
        )

    except IntegrityError as ie:
        db.rollback()
        logger.error(f"Integrity error updating product {product_id}: {str(ie)}")
        return HttpResponse.conflict(
            error="Datos duplicados en la base de datos"
        )

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(
            f"Database error updating product {product_id}: {str(se)}"
        )
        return HttpResponse.internal_server_error(
            error="Error de base de datos al actualizar el producto"
        )

    except Exception as e:
        db.rollback()
        logger.exception(
            f"Unexpected error updating product {product_id}: {str(e)}"
        )
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al actualizar el producto"
        )


@router.get(
    "/",
    summary="List all products with pagination",
    response_description="Paginated list of products retrieved successfully"
)
def api_list_products(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(
        10,
        ge=1,
        le=100,
        description="Items per page (max 100)"
    )
):
    """
    List all products with pagination support.

    **Query parameters:**
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)

    **Returns:**
    - List of products with pagination metadata
    """
    try:
        skip = (page - 1) * per_page
        products = list_products(db, skip=skip, limit=per_page)

        if not products:
            logger.info("No products found in the database")
            return HttpResponse.success(
                message="No products found",
                response={
                    "products": [],
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total_items": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "has_prev": False
                    }
                }
            )

        total_products = count_products(db)
        total_pages = (total_products + per_page - 1) // per_page

        logger.info(f"Retrieved {len(products)} products for page {page}")
        return HttpResponse.success(
            message=f"Retrieved {len(products)} products successfully",
            response={
                "products": [
                    ProductRead.model_validate(p).model_dump(mode='json')
                    for p in products
                ],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_products,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error listing products: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al listar productos"
        )

    except Exception as e:
        logger.exception(f"Unexpected error listing products: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al listar productos"
        )
