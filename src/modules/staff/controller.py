"""
Controlador para gestión de staff (operadores y vendedores).
"""
from typing import Optional
from fastapi import APIRouter, Depends, File, UploadFile, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from db.deps import get_db
from src.modules.staff.service import (
    create_user,
    get_user,
    update_user,
    list_users,
    search_users,
    count_users,
    count_search_results,
    get_available_sellers_by_date,
    get_all_sellers,
    import_users_from_excel,
    export_users_to_excel,
    export_users_to_pdf
)

from src.utils.excel_formatter import ExcelImportError, create_template_excel
from src.common.types.userType import StaffCreate, UserUpdate, UserRead
from src.common.constants.roles import ADMIN, OPERATOR, SELLER
from src.utils.http_response import HttpResponse
from src.modules.auth.dependencies import require_role

import logging

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/staff",
    tags=["Staff Management"]

)


# ============================================
# CRUD ENDPOINTS
# ============================================

@router.post(
    "/users",
    summary="Create a new staff user (operator or seller)",
    response_description="Staff user created successfully",
    dependencies=[Depends(require_role(ADMIN))]
)
def api_create_staff_user(
    user_data: StaffCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new staff user (operator or seller).

    **Required fields:**
    - nombre: Full name
    - dpi: National ID (13 digits)
    - email: Email address
    - password: Password (min 8 chars, 1 uppercase, 1 number)
    - rol: Either "operador" or "vendedor"
    """
    try:
        user = create_user(db, user_data)
        logger.info(f"Staff user created: {user.email} with role {user.rol}")
        return HttpResponse.created(
            response=UserRead.model_validate(user).model_dump(mode='json')
        )

    except ValueError as ve:
        logger.error(f"Validation error creating staff user: {str(ve)}")
        return HttpResponse.unprocessable_entity(error=str(ve))

    except IntegrityError:
        db.rollback()
        logger.error("Integrity error: duplicate email or DPI")
        return HttpResponse.conflict(
            error="El usuario ya existe en la base de datos (email o DPI duplicado)"
        )

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error creating staff user: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al crear el usuario"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating staff user: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al crear el usuario"
        )

@router.get(
    "/users",
    summary="List all staff users (operators and sellers) with pagination",
    response_description="Paginated list of staff users retrieved successfully",
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]
)
def api_list_staff_users(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page (max 100)")
):
    """
    List all staff users (both operators and sellers) with pagination.

    Returns ALL staff members without role filtering.
    """
    try:
        skip = (page - 1) * per_page
        users = list_users(db, skip=skip, limit=per_page)

        if not users or len(users) == 0:
            logger.info("No staff users found")
            return HttpResponse.success(
                message="No staff users found",
                response={
                    "users": [],
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

        total_users = count_users(db)
        total_pages = (total_users + per_page - 1) // per_page

        logger.info(f"Retrieved {len(users)} staff users for page {page}")
        return HttpResponse.success(
            message=f"Retrieved {len(users)} staff users successfully",
            response={
                "users": [UserRead.model_validate(user).model_dump(mode='json') for user in users],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_users,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error listing staff users: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al listar usuarios"
        )

    except Exception as e:
        logger.exception(f"Unexpected error listing staff users: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al listar usuarios"
        )

# IMPORTANTE: Esta ruta debe estar ANTES de /users/{user_id}
@router.get(
    "/users/search",
    summary="Search staff users by name or DPI",
    response_description="Search results retrieved successfully",
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]  # ✅ Admin y Operador
)
def api_search_staff_users(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1, description="Search query (name or DPI)"),
    role: Optional[str] = Query(None, description="Filter by role (optional)"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page (max 50)")
):
    """
    Search staff users by name or DPI, with optional role filter.

    - **q**: Search query (name or DPI)
    - **role**: Optional filter ('operador' or 'vendedor')
    - **page**: Page number
    - **per_page**: Items per page
    """
    try:
        # Validar rol si se especifica
        if role and role.lower() not in [OPERATOR.lower(), SELLER.lower()]:
            return HttpResponse.bad_request(
                error=f"Rol inválido. Debe ser '{OPERATOR}' o '{SELLER}'"
            )

        skip = (page - 1) * per_page
        results = search_users(db, query=q, role=role, skip=skip, limit=per_page)

        if not results or len(results) == 0:
            logger.info(f"No staff users found for search query: {q}")
            return HttpResponse.success(
                message=f"No users found matching '{q}'",
                response={
                    "users": [],
                    "search_query": q,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total_items": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "has_prev": False
                    },
                    "filter": {"role": role} if role else {}
                }
            )

        total_results = count_search_results(db, query=q, role=role)
        total_pages = (total_results + per_page - 1) // per_page

        logger.info(f"Found {len(results)} staff users for search query: {q}")
        return HttpResponse.success(
            message=f"Found {total_results} users matching '{q}'",
            response={
                "users": [UserRead.model_validate(user).model_dump(mode='json') for user in results],
                "search_query": q,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_results,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                },
                "filter": {"role": role} if role else {}
            }
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error searching staff users: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al buscar usuarios"
        )

    except Exception as e:
        logger.exception(f"Unexpected error searching staff users: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al buscar usuarios"
        )

# ============================================
# IMPORT / EXPORT ENDPOINTS
# ============================================


@router.get(
    "/users/export/excel",
    summary="Export staff users to Excel",
    response_description="Excel file with staff users",
    dependencies=[Depends(require_role(ADMIN))]  # ✅ Solo admin
)
def api_export_staff_excel(
    db: Session = Depends(get_db),
    role: str = Query(None, description="Filter by role: 'operador' or 'vendedor' (optional)")
):
    """
    Export staff users to an Excel file.

    - If **role** is not specified, exports both operators and sellers
    - If **role** is specified, exports only that role

    **Returns:**
    - Excel file (.xlsx) with user information
    - Columns: nombre, dpi, email, rol
    - Password is NOT included for security reasons
    """
    try:
        # Validar rol si se especifica
        if role and role.lower() not in [OPERATOR.lower(), SELLER.lower()]:
            return HttpResponse.bad_request(
                error=f"Rol inválido. Debe ser '{OPERATOR}' o '{SELLER}'"
            )

        excel_content = export_users_to_excel(db, role=role)

        filename = f"staff_{role if role else 'todos'}.xlsx"

        logger.info(f"Staff users exported to Excel successfully: {filename}")
        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting staff users to Excel: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los usuarios"
        )


@router.get(
    "/users/export/pdf",
    summary="Export staff users to PDF",
    response_description="PDF file with staff users",
    dependencies=[Depends(require_role(ADMIN))]  # ✅ Solo admin
)
def api_export_staff_pdf(
    db: Session = Depends(get_db),
    role: str = Query(None, description="Filter by role: 'operador' or 'vendedor' (optional)")
):
    """
    Export staff users to a PDF report.

    - If **role** is not specified, exports both operators and sellers
    - If **role** is specified, exports only that role

    **Returns:**
    - PDF file with formatted table
    - Columns: DPI, Nombre, Email, Rol
    """
    try:
        # Validar rol si se especifica
        if role and role.lower() not in [OPERATOR.lower(), SELLER.lower()]:
            return HttpResponse.bad_request(
                error=f"Rol inválido. Debe ser '{OPERATOR}' o '{SELLER}'"
            )

        pdf_content = export_users_to_pdf(db, role=role)

        filename = f"staff_{role if role else 'todos'}.pdf"

        logger.info(f"Staff users exported to PDF successfully: {filename}")
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting staff users to PDF: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los usuarios a PDF"
        )


@router.get(
    "/users/template",
    summary="Download Excel template for bulk import",
    response_description="Excel template file",
    dependencies=[Depends(require_role(ADMIN))]  # ✅ Solo admin
)
def api_download_template():
    """
    Download an Excel template for bulk staff import.

    **Returns:**
    - Excel template with required columns and example data
    - Columns: nombre, dpi, email, password, rol
    - Use this template to prepare your bulk import file
    """
    try:
        template = create_template_excel(
            columns=["nombre", "dpi", "email", "password", "rol"],
            example_data=[
                {
                    "nombre": "Juan Pérez López",
                    "dpi": "1234567890123",
                    "email": "juan.perez@example.com",
                    "password": "Admin123",
                    "rol": "operador"
                },
                {
                    "nombre": "María García Hernández",
                    "dpi": "9876543210987",
                    "email": "maria.garcia@example.com",
                    "password": "Secure456",
                    "rol": "vendedor"
                }
            ],
            filename="template_staff.xlsx"
        )

        logger.info("Staff template downloaded successfully")
        return Response(
            content=template.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=template_staff.xlsx"
            }
        )

    except Exception as e:
        logger.exception(f"Error creating template: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al generar el template"
        )



@router.post(
    "/users/import",
    summary="Import staff users from Excel file",
    response_description="Staff users imported successfully",
    dependencies=[Depends(require_role(ADMIN))]
)
async def api_import_staff(
    file: UploadFile = File(..., description="Excel file (.xlsx) with staff data"),
    db: Session = Depends(get_db)
):
    """
    Import multiple staff users from an Excel file.

    **Excel columns required:**
    - nombre: Full name
    - dpi: National ID (13 digits)
    - email: Email address
    - password: Password
    - rol: User role ('operador' or 'vendedor')

    **Download template**: GET /staff/users/template
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
        created_users, validation_errors, db_errors = import_users_from_excel(
            file=file,
            db=db
        )

        if not validation_errors and not db_errors:
            logger.info(f"All {len(created_users)} staff users imported successfully")
            return HttpResponse.custom(
                message=f"Se crearon {len(created_users)} usuarios exitosamente",
                response={
                    "created_count": len(created_users),
                    "users": [
                        {
                            "nombre": user.nombre,
                            "email": user.email,
                            "dpi": user.dpi,
                            "rol": user.rol
                        }
                        for user in created_users
                    ]
                },
                status_code=201
            )

        elif validation_errors and not db_errors:
            logger.warning(f"Import failed with {len(validation_errors)} validation errors")
            return HttpResponse.custom(
                message="El archivo contiene errores de validación. No se creó ningún usuario.",
                response={
                    "validation_errors": validation_errors,
                    "total_errors": len(validation_errors)
                },
                status_code=422
            )

        else:
            logger.info(f"Partial import: {len(created_users)} created, {len(db_errors)} failed")
            return HttpResponse.custom(
                message=f"Se crearon {len(created_users)} usuarios. {len(db_errors)} usuarios no se pudieron crear.",
                response={
                    "created_count": len(created_users),
                    "error_count": len(db_errors),
                    "created_users": [
                        {
                            "nombre": user.nombre,
                            "email": user.email,
                            "dpi": user.dpi,
                            "rol": user.rol
                        }
                        for user in created_users
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
    "/users/{user_id}",
    summary="Get staff user by ID",
    response_description="Staff user details retrieved successfully",
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]  # ✅ Admin y Operador
)
def api_get_staff_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve a specific staff user by their ID.

    - **user_id**: The ID of the staff user to retrieve
    """
    try:
        user = get_user(db, user_id)

        if not user:
            logger.warning(f"Staff user not found with ID: {user_id}")
            return HttpResponse.not_found(
                error=f"Usuario con ID {user_id} no encontrado o no es parte del staff"
            )

        logger.info(f"Staff user retrieved successfully with ID: {user_id}")
        return HttpResponse.success(
            message="Usuario encontrado",
            response=UserRead.model_validate(user).model_dump(mode='json')
        )

    except ValueError as ve:
        logger.error(f"Invalid user ID: {str(ve)}")
        return HttpResponse.bad_request(error="Invalid user ID format")

    except Exception as e:
        logger.exception(f"Unexpected error retrieving staff user {user_id}: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al obtener el usuario"
        )


@router.put(
    "/users/{user_id}",
    summary="Update staff user information",
    response_description="Staff user updated successfully",
    dependencies=[Depends(require_role(ADMIN))]  # ✅ Solo admin
)
def api_update_staff_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing staff user's information.

    ⚠️ **Note**: Cannot change user's role. To change role, create a new user.

    - **user_id**: The ID of the staff user to update
    - **user_data**: Updated user information (nombre, dpi, email, password)
    """
    try:
        user = update_user(db, user_id, user_data)

        if not user:
            logger.warning(f"Staff user not found for update with ID: {user_id}")
            return HttpResponse.not_found(
                error=f"Usuario con ID {user_id} no encontrado o no es parte del staff"
            )

        logger.info(f"Staff user updated successfully with ID: {user_id}")
        return HttpResponse.updated(
            response=UserRead.model_validate(user).model_dump(mode='json')
        )

    except ValueError as ve:
        db.rollback()
        logger.error(f"Validation error updating staff user {user_id}: {str(ve)}")
        return HttpResponse.unprocessable_entity(error=str(ve))

    except IntegrityError:
        db.rollback()
        logger.error(f"Integrity error updating staff user {user_id}")
        return HttpResponse.conflict(error="Email o DPI duplicado")

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error updating staff user {user_id}: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al actualizar el usuario"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error updating staff user {user_id}: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al actualizar el usuario"
        )


# ============================================
# ENDPOINTS ESPECÍFICOS PARA VENDEDORES
# ============================================

@router.get(
    "/sellers",
    summary="Get all active sellers (simple list)",
    response_description="List of all active sellers",
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]  # ✅ Admin y Operador
)
def api_get_all_sellers(db: Session = Depends(get_db)):
    """
    Get simple list of all active sellers.

    **Use case:** General dropdown selector (without availability check)

    **Returns:**
    - List of all active sellers with basic info
    """
    try:
        vendedores = get_all_sellers(db)

        logger.info(f"Retrieved {len(vendedores)} active sellers")
        return HttpResponse.success(
            message=f"Retrieved {len(vendedores)} sellers",
            response={
                "sellers": [
                    {
                        "id": v.id,
                        "nombre": v.nombre,
                        "email": v.email,
                        "dpi": v.dpi
                    }
                    for v in vendedores
                ],
                "total": len(vendedores)
            }
        )

    except Exception as e:
        logger.exception(f"Error getting sellers: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Error al obtener vendedores"
        )


@router.get(
    "/sellers/available",
    summary="Get available sellers for a specific date",
    response_description="List of available sellers",
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]  # ✅ Admin y Operador
)
def api_get_available_sellers(
    db: Session = Depends(get_db),
    fecha: str = Query(..., description="Date in format YYYY-MM-DD")
):
    """
    Get list of sellers that are available (not assigned to a route) on a specific date.

    **Parameters:**
    - fecha: Date to check availability (YYYY-MM-DD)

    **Returns:**
    - List of sellers not assigned to any route on that date

    **Use case:** Populate select dropdown when creating a new route

    **Example:** GET /staff/sellers/available?fecha=2025-10-28
    """
    try:
        vendedores = get_available_sellers_by_date(db, fecha)

        logger.info(f"Retrieved {len(vendedores)} available sellers for {fecha}")
        return HttpResponse.success(
            message=f"Found {len(vendedores)} available sellers",
            response={
                "fecha": fecha,
                "sellers": [
                    {
                        "id": v.id,
                        "nombre": v.nombre,
                        "email": v.email,
                        "dpi": v.dpi
                    }
                    for v in vendedores
                ],
                "total": len(vendedores)
            }
        )

    except ValueError as ve:
        logger.error(f"Date validation error: {str(ve)}")
        return HttpResponse.bad_request(error=str(ve))

    except Exception as e:
        logger.exception(f"Error getting available sellers: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Error al obtener vendedores disponibles"
        )


