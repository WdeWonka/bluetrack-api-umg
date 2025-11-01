from fastapi import APIRouter, Depends, File, UploadFile, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from db.deps import get_db
from src.modules.warehouses.service import (
    create_warehouse,
    get_warehouse,
    update_warehouse,
    list_warehouses,
    search_warehouses,
    count_warehouses,
    count_search_results,
    import_warehouses_from_excel,
    export_warehouses_to_excel,
    export_warehouses_to_pdf
)
from src.utils.excel_formatter import ExcelImportError, create_template_excel
from src.modules.warehouses.type import WarehouseCreate, WarehouseUpdate, WarehouseRead
from src.utils.type_converters import decimal_to_float
from src.utils.http_response import HttpResponse
from src.modules.auth.dependencies import require_role
from src.common.constants.roles import ADMIN
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/warehouses",
    tags=["warehouses"],
    dependencies=[Depends(require_role(ADMIN))]
)




@router.post(
    "/",
    summary="Create a new warehouse",
    response_description="Warehouse created successfully"
)
def api_create_warehouse(
    warehouse_data: WarehouseCreate,
    db: Session = Depends(get_db)
):
    try:
        warehouse = create_warehouse(db, warehouse_data)
        logger.info(f"Warehouse created successfully: {warehouse.nombre}")
        return HttpResponse.created(
            response=WarehouseRead.model_validate(warehouse).model_dump(mode='json')
        )

    except IntegrityError as ie:
        db.rollback()
        logger.error(f"Integrity error creating warehouse: {str(ie)}")
        return HttpResponse.conflict(error="El almacén ya existe en la base de datos")

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error creating warehouse: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al crear el almacén")

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating warehouse: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al crear el almacén")



@router.get(
    "/search",
    summary="Search warehouses by name or address",
    response_description="Search results retrieved successfully"
)
def api_search_warehouses(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1, description="Search query (name or address)"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page (max 50)")
):
    try:
        skip = (page - 1) * per_page
        results = search_warehouses(db, query=q, skip=skip, limit=per_page)

        if not results:
            logger.info(f"No warehouses found for search query: {q}")
            return HttpResponse.success(
                message=f"No warehouses found matching '{q}'",
                response={
                    "warehouses": [],
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

        logger.info(f"Found {len(results)} warehouses for search query: {q}")
        return HttpResponse.success(
            message=f"Found {total_results} warehouses matching '{q}'",
            response={
                "warehouses": [WarehouseRead.model_validate(w).model_dump(mode='json') for w in results],
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
        logger.error(f"Database error searching warehouses with query '{q}': {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al buscar almacenes")

    except Exception as e:
        logger.exception(f"Unexpected error searching warehouses with query '{q}': {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al buscar almacenes")

@router.post(
    "/import",
    summary="Import warehouses from Excel file",
    response_description="Warehouses imported successfully"
)
async def api_import_warehouses(
    file: UploadFile = File(..., description="Excel file (.xlsx) with warehouse data"),
    db: Session = Depends(get_db)
):
    """
    Import multiple warehouses from an Excel file.

    **Expected columns:**
    - nombre: Warehouse name
    - direccion: Address
    - telefono: Phone number
    - latitud: Latitude
    - longitud: Longitude

    **Status Codes:**
    - 201: All warehouses imported successfully
    - 207: Partial import (some created, some failed)
    - 409: No warehouses imported (all duplicates)
    - 422: Validation errors in Excel format
    - 400: Invalid file or other errors
    """
    if not file.filename:
        logger.warning("File uploaded without filename")
        return HttpResponse.bad_request(error="El archivo no tiene nombre")

    if not file.filename.endswith(('.xlsx', '.xls')):
        logger.warning(f"Invalid file type uploaded: {file.filename}")
        return HttpResponse.bad_request(
            error="Tipo de archivo inválido. Por favor sube un archivo Excel (.xlsx o .xls)"
        )

    try:
        created_warehouses, validation_errors, db_errors = import_warehouses_from_excel(
            file=file,
            db=db,
        )

        # CASO 1: ❌ Errores de validación
        if validation_errors:
            logger.warning(f"Import failed with {len(validation_errors)} validation errors")
            return HttpResponse.custom(
                message="El archivo contiene errores de validación. No se creó ningún almacén.",
                response={
                    "created_count": 0,
                    "error_count": len(validation_errors),
                    "validation_errors": validation_errors,
                    "db_errors": []
                },
                status_code=422
            )

        # CASO 2: 🔴 NO se creó NINGÚN almacén (todos duplicados)
        if len(created_warehouses) == 0 and len(db_errors) > 0:
            logger.warning(f"Import failed: all {len(db_errors)} warehouses are duplicates")
            return HttpResponse.custom(
                message="Todos los almacenes ya existen en el sistema",
                response={
                    "created_count": 0,
                    "error_count": len(db_errors),
                    "validation_errors": [],
                    "db_errors": db_errors
                },
                status_code=409
            )

        # CASO 3: 🟡 Importación PARCIAL
        if len(created_warehouses) > 0 and len(db_errors) > 0:
            logger.info(f"Partial import: {len(created_warehouses)} created, {len(db_errors)} failed")
            return HttpResponse.custom(
                message=f"Se importaron {len(created_warehouses)} de {len(created_warehouses) + len(db_errors)} almacenes",
                response={
                    "created_count": len(created_warehouses),
                    "error_count": len(db_errors),
                    "created_warehouses": [
                        {
                            "nombre": warehouse.nombre,
                            "direccion": warehouse.direccion,
                            "telefono": warehouse.telefono,
                            "latitud": decimal_to_float(warehouse.latitud),
                            "longitud": decimal_to_float(warehouse.longitud)
                        }
                        for warehouse in created_warehouses
                    ],
                    "validation_errors": [],
                    "db_errors": db_errors
                },
                status_code=207
            )

        # CASO 4: ✅ TODOS los almacenes se crearon exitosamente
        logger.info(f"All {len(created_warehouses)} warehouses imported successfully")
        return HttpResponse.custom(
            message="Todos los almacenes importados correctamente",
            response={
                "created_count": len(created_warehouses),
                "error_count": 0,
                "created_warehouses": [
                    {
                        "nombre": warehouse.nombre,
                        "direccion": warehouse.direccion,
                        "telefono": warehouse.telefono,
                        "latitud": decimal_to_float(warehouse.latitud),
                        "longitud": decimal_to_float(warehouse.longitud)
                    }
                    for warehouse in created_warehouses
                ],
                "validation_errors": [],
                "db_errors": []
            },
            status_code=201
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
    summary="Export all warehouses to Excel",
    response_description="Excel file with all warehouses"
)
def api_export_warehouses_excel(db: Session = Depends(get_db)):
    """
    Export all warehouses to an Excel file.

    **Returns:**
    - Excel file (.xlsx) with all warehouse information
    - Columns: nombre, direccion, telefono, latitud, longitud
    """
    try:
        excel_content = export_warehouses_to_excel(db)

        logger.info("Warehouses exported to Excel successfully")
        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=almacenes.xlsx"
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting warehouses to Excel: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los almacenes a Excel"
        )


@router.get(
    "/export/pdf",
    summary="Export all warehouses to PDF",
    response_description="PDF file with all warehouses"
)
def api_export_warehouses_pdf(db: Session = Depends(get_db)):
    """
    Export all warehouses to a PDF report.

    **Returns:**
    - PDF file with formatted table
    - Columns: Nombre, Dirección, Teléfono, Latitud, Longitud
    """
    try:
        pdf_content = export_warehouses_to_pdf(db)

        logger.info("Warehouses exported to PDF successfully")
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=reporte_almacenes.pdf"
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting warehouses to PDF: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los almacenes a PDF"
        )

@router.get(
    "/template",
    summary="Download Excel template for bulk warehouse import",
    response_description="Excel template file"
)
def api_download_warehouse_template():
    """
    Download an Excel template for bulk warehouse import.

    **Returns:**
    - Excel template with required columns and example data
    - Use this template to prepare your bulk import file

    **Columns:**
    - nombre: Warehouse name
    - direccion: Complete address
    - telefono: Phone number (8 digits)
    - latitud: Latitude coordinate
    - longitud: Longitude coordinate
    """
    try:
        template = create_template_excel(
            columns=["nombre", "direccion", "telefono", "latitud", "longitud"],
            example_data=[
                {
                    "nombre": "Almacén Central",
                    "direccion": "5ta Avenida 10-30 Zona 1, Guatemala",
                    "telefono": "23456789",
                    "latitud": "14.634915",
                    "longitud": "-90.506882"
                },
                {
                    "nombre": "Bodega Norte",
                    "direccion": "Calzada Roosevelt 15-45 Zona 11, Guatemala",
                    "telefono": "24567890",
                    "latitud": "14.613333",
                    "longitud": "-90.563056"
                },
                {
                    "nombre": "Centro de Distribución Sur",
                    "direccion": "Boulevard Liberación Km 8.5, Villa Nueva",
                    "telefono": "66789012",
                    "latitud": "14.525833",
                    "longitud": "-90.587500"
                }
            ],
            filename="template_almacenes.xlsx"
        )

        logger.info("Warehouse template downloaded successfully")
        return Response(
            content=template.getvalue(),
            media_type="application/vnd.openxmlformats-oficedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=template_almacenes.xlsx"
            }
        )

    except Exception as e:
        logger.exception(f"Error creating warehouse template: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al generar el template de almacenes"
        )

@router.get(
    "/{warehouse_id}",
    summary="Get warehouse by ID",
    response_description="Warehouse details retrieved successfully"
)
def api_get_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db)
):
    try:
        warehouse = get_warehouse(db, warehouse_id)
        if not warehouse:
            logger.warning(f"Warehouse not found with ID: {warehouse_id}")
            return HttpResponse.not_found(error=f"Warehouse with ID {warehouse_id} does not exist")

        logger.info(f"Warehouse retrieved successfully with ID: {warehouse_id}")
        return HttpResponse.success(
            message="Warehouse retrieved successfully",
            response=WarehouseRead.model_validate(warehouse).model_dump(mode='json')
        )

    except Exception as e:
        logger.exception(f"Unexpected error retrieving warehouse {warehouse_id}: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al obtener el almacén")


@router.patch(
    "/{warehouse_id}",
    summary="Update warehouse information",
    response_description="Warehouse updated successfully"
)
def api_update_warehouse(
    warehouse_id: int,
    warehouse_data: WarehouseUpdate,
    db: Session = Depends(get_db)
):
    try:
        warehouse = update_warehouse(db, warehouse_id, warehouse_data)
        if not warehouse:
            logger.warning(f"Warehouse not found for update with ID: {warehouse_id}")
            return HttpResponse.not_found(error=f"Warehouse with ID {warehouse_id} does not exist")

        logger.info(f"Warehouse updated successfully with ID: {warehouse_id}")
        return HttpResponse.updated(
            response=WarehouseRead.model_validate(warehouse).model_dump(mode='json')
        )

    except IntegrityError as ie:
        db.rollback()
        logger.error(f"Integrity error updating warehouse {warehouse_id}: {str(ie)}")
        return HttpResponse.conflict(error="Datos duplicados en la base de datos")

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error updating warehouse {warehouse_id}: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al actualizar el almacén")

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error updating warehouse {warehouse_id}: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al actualizar el almacén")


@router.get(
    "/",
    summary="List all warehouses with pagination",
    response_description="Paginated list of warehouses retrieved successfully"
)
def api_list_warehouses(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page (max 100)")
):
    try:
        skip = (page - 1) * per_page
        warehouses = list_warehouses(db, skip=skip, limit=per_page)

        if not warehouses:
            logger.info("No warehouses found in the database")
            return HttpResponse.success(
                message="No warehouses found",
                response={
                    "warehouses": [],
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

        total_warehouses = count_warehouses(db)
        total_pages = (total_warehouses + per_page - 1) // per_page

        logger.info(f"Retrieved {len(warehouses)} warehouses for page {page}")
        return HttpResponse.success(
            message=f"Retrieved {len(warehouses)} warehouses successfully",
            response={
                "warehouses": [WarehouseRead.model_validate(w).model_dump(mode='json') for w in warehouses],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_warehouses,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error listing warehouses: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al listar almacenes")

    except Exception as e:
        logger.exception(f"Unexpected error listing warehouses: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al listar almacenes")
