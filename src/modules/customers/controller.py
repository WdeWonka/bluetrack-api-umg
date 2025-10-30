from fastapi import APIRouter, Depends, File, UploadFile, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from db.deps import get_db
from src.modules.customers.service import (
    create_customer,
    get_customer,
    update_customer,
    list_customers,
    search_customers,
    count_customers,
    count_search_results,
    import_customers_from_excel,
    export_customers_to_excel,
    export_customers_to_pdf
)
from src.utils.excel_formatter import ExcelImportError, create_template_excel
from src.modules.customers.type import CustomerCreate, CustomerUpdate, CustomerRead
from src.utils.type_converters import decimal_to_float
from src.utils.http_response import HttpResponse
from src.modules.auth.dependencies import require_role
from src.common.constants.roles import ADMIN
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(require_role(ADMIN))]
)




@router.post(
    "/",
    summary="Create a new customer",
    response_description="Customer created successfully"
)
def api_create_customer(
    customer_data: CustomerCreate,
    db: Session = Depends(get_db)
):
    try:
        customer = create_customer(db, customer_data)
        logger.info(f"Customer created successfully: {customer.nombre}")
        return HttpResponse.created(
            response=CustomerRead.model_validate(customer).model_dump(mode='json')
        )

    except IntegrityError as ie:
        db.rollback()
        logger.error(f"Integrity error creating customer: {str(ie)}")
        return HttpResponse.conflict(error="El cliente ya existe en la base de datos")

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error creating customer: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al crear el cliente")

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating customer: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al crear el cliente")



@router.get(
    "/search",
    summary="Search customers by name or address",
    response_description="Search results retrieved successfully"
)
def api_search_customers(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1, description="Search query (name or address)"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page (max 50)")
):
    try:
        skip = (page - 1) * per_page
        results = search_customers(db, query=q, skip=skip, limit=per_page)

        if not results:
            logger.info(f"No customers found for search query: {q} (page {page})")
            return HttpResponse.success(
                message=f"No customers found matching '{q}'",
                response={
                    "customers": [],
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

        logger.info(f"Found {len(results)} customers for search query: {q}")
        return HttpResponse.success(
            message=f"Found {total_results} customers matching '{q}'",
            response={
                "customers": [CustomerRead.model_validate(c).model_dump(mode='json') for c in results],
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
        logger.error(f"Database error searching customers with query '{q}': {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al buscar clientes")

    except Exception as e:
        logger.exception(f"Unexpected error searching customers with query '{q}': {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al buscar clientes")

@router.post(
    "/import",
    summary="Import customers from Excel file",
    response_description="Customers imported successfully"
)
async def api_import_customers(
    file: UploadFile = File(..., description="Excel file (.xlsx) with customer data"),
    db: Session = Depends(get_db)
):
    """
    Import multiple customers from an Excel file.

    **Expected columns:**
    - nombre: Customer name
    - direccion: Address
    - telefono: Phone number
    - latitud: Latitude
    - longitud: Longitude
    """
    # Validar que el archivo tenga nombre
    if not file.filename:
        logger.warning("File uploaded without filename")
        return HttpResponse.bad_request(error="El archivo no tiene nombre")

    # Validar extensión del archivo
    if not file.filename.endswith(('.xlsx', '.xls')):
        logger.warning(f"Invalid file type uploaded: {file.filename}")
        return HttpResponse.bad_request(
            error="Tipo de archivo inválido. Por favor sube un archivo Excel (.xlsx o .xls)"
        )

    try:
        created_customers, validation_errors, db_errors = import_customers_from_excel(
            file=file,
            db=db,
        )

        if not validation_errors and not db_errors:
            logger.info(f"All {len(created_customers)} customers imported successfully")
            return HttpResponse.custom(
                message=f"Se crearon {len(created_customers)} clientes exitosamente",
                response={
                    "created_count": len(created_customers),
                    "customers": [
                        {
                            "nombre": customer.nombre,
                            "direccion": customer.direccion,
                            "telefono": customer.telefono,
                            "latitud": decimal_to_float(customer.latitud),
                            "longitud": decimal_to_float(customer.longitud)
                        }
                        for customer in created_customers
                    ]
                },
                status_code=201
            )

        elif validation_errors and not db_errors:
            logger.warning(f"Import failed with {len(validation_errors)} validation errors")
            return HttpResponse.custom(
                message="El archivo contiene errores de validación. No se creó ningún cliente.",
                response={
                    "validation_errors": validation_errors,
                    "total_errors": len(validation_errors)
                },
                status_code=422
            )

        else:
            logger.info(f"Partial import: {len(created_customers)} created, {len(db_errors)} failed")
            return HttpResponse.custom(
                message=f"Se crearon {len(created_customers)} clientes. {len(db_errors)} clientes no se pudieron crear.",
                response={
                    "created_count": len(created_customers),
                    "error_count": len(db_errors),
                    "created_customers": [
                        {
                            "nombre": customer.nombre,
                            "direccion": customer.direccion,
                            "telefono": customer.telefono,
                            "latitud": decimal_to_float(customer.latitud),
                            "longitud": decimal_to_float(customer.longitud)
                        }
                        for customer in created_customers
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
    summary="Export all customers to Excel",
    response_description="Excel file with all customers"
)
def api_export_customers_excel(db: Session = Depends(get_db)):
    """
    Export all customers to an Excel file.

    **Returns:**
    - Excel file (.xlsx) with all customer information
    - Columns: nombre, direccion, telefono, latitud, longitud
    """
    try:
        excel_content = export_customers_to_excel(db)

        logger.info("Customers exported to Excel successfully")
        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=clientes.xlsx"
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting customers to Excel: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los clientes a Excel"
        )


@router.get(
    "/export/pdf",
    summary="Export all customers to PDF",
    response_description="PDF file with all customers"
)
def api_export_customers_pdf(db: Session = Depends(get_db)):
    """
    Export all customers to a PDF report.

    **Returns:**
    - PDF file with formatted table
    - Columns: Nombre, Dirección, Teléfono, Latitud, Longitud
    """
    try:
        pdf_content = export_customers_to_pdf(db)

        logger.info("Customers exported to PDF successfully")
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=reporte_clientes.pdf"
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting customers to PDF: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los clientes a PDF"
        )

@router.get(
    "/template",
    summary="Download Excel template for bulk customer import",
    response_description="Excel template file"
)
def api_download_customer_template():
    """
    Download an Excel template for bulk customer import.

    **Returns:**
    - Excel template with required columns and example data
    - Use this template to prepare your bulk import file

    **Columns:**
    - nombre: Customer name
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
                    "nombre": "Cliente Principal",
                    "direccion": "5ta Avenida 10-30 Zona 1, Guatemala",
                    "telefono": "23456789",
                    "latitud": "14.634915",
                    "longitud": "-90.506882"
                },
                {
                    "nombre": "Cliente Norte",
                    "direccion": "Calzada Roosevelt 15-45 Zona 11, Guatemala",
                    "telefono": "24567890",
                    "latitud": "14.613333",
                    "longitud": "-90.563056"
                },
                {
                    "nombre": "Cliente Sur",
                    "direccion": "Boulevard Liberación Km 8.5, Villa Nueva",
                    "telefono": "66789012",
                    "latitud": "14.525833",
                    "longitud": "-90.587500"
                }
            ],
            filename="template_clientes.xlsx"
        )

        logger.info("Customer template downloaded successfully")
        return Response(
            content=template.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=template_clientes.xlsx"
            }
        )

    except Exception as e:
        logger.exception(f"Error creating customer template: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al generar el template de clientes"
        )

@router.get(
    "/{customer_id}",
    summary="Get customer by ID",
    response_description="Customer details retrieved successfully"
)
def api_get_customer(
    customer_id: int,
    db: Session = Depends(get_db)
):
    try:
        customer = get_customer(db, customer_id)
        if not customer:
            logger.warning(f"Customer not found with ID: {customer_id}")
            return HttpResponse.not_found(error=f"Customer with ID {customer_id} does not exist")

        logger.info(f"Customer retrieved successfully with ID: {customer_id}")
        return HttpResponse.success(
            message="Customer retrieved successfully",
            response=CustomerRead.model_validate(customer).model_dump(mode='json')
        )

    except Exception as e:
        logger.exception(f"Unexpected error retrieving customer {customer_id}: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al obtener el cliente")


@router.put(
    "/{customer_id}",
    summary="Update customer information",
    response_description="Customer updated successfully"
)
def api_update_customer(
    customer_id: int,
    customer_data: CustomerUpdate,
    db: Session = Depends(get_db)
):
    try:
        customer = update_customer(db, customer_id, customer_data)
        if not customer:
            logger.warning(f"Customer not found for update with ID: {customer_id}")
            return HttpResponse.not_found(error=f"Customer with ID {customer_id} does not exist")

        logger.info(f"Customer updated successfully with ID: {customer_id}")
        return HttpResponse.updated(
            response=CustomerRead.model_validate(customer).model_dump(mode='json')
        )

    except IntegrityError as ie:
        db.rollback()
        logger.error(f"Integrity error updating customer {customer_id}: {str(ie)}")
        return HttpResponse.conflict(error="Datos duplicados en la base de datos")

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error updating customer {customer_id}: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al actualizar el cliente")

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error updating customer {customer_id}: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al actualizar el cliente")


@router.get(
    "/",
    summary="List all customers with pagination",
    response_description="Paginated list of customers retrieved successfully"
)
def api_list_customers(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page (max 100)")
):
    try:
        skip = (page - 1) * per_page
        customers = list_customers(db, skip=skip, limit=per_page)

        if not customers:
            logger.info("No customers found in the database")
            return HttpResponse.success(
                message="No customers found",
                response={
                    "customers": [],
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

        total_customers = count_customers(db)
        total_pages = (total_customers + per_page - 1) // per_page

        logger.info(f"Retrieved {len(customers)} customers for page {page}")
        return HttpResponse.success(
            message=f"Retrieved {len(customers)} customers successfully",
            response={
                "customers": [CustomerRead.model_validate(c).model_dump(mode='json') for c in customers],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_customers,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error listing customers: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al listar clientes")

    except Exception as e:
        logger.exception(f"Unexpected error listing customers: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al listar clientes")
